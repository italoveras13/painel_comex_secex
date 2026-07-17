from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .auxiliary import AuxiliaryDimensions, load_auxiliary_dimensions
from .utils import detect_text_encoding, fingerprint, normalize_header, sql_literal


FACT_REQUIRED = {
    "CO_ANO",
    "CO_MES",
    "CO_NCM",
    "CO_UNID",
    "CO_PAIS",
    "SG_UF_NCM",
    "CO_VIA",
    "CO_URF",
    "QT_ESTAT",
    "KG_LIQUIDO",
    "VL_FOB",
}


@dataclass(frozen=True)
class EtlResult:
    files_loaded: int
    files_skipped: int
    rows_loaded: int
    database: Path
    sheet_map: dict[str, str]


def _import_duckdb():
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError(
            "DuckDB não está instalado. Execute: pip install -r requirements.txt"
        ) from exc
    return duckdb


def _resolve_single_file(directory: Path, patterns: tuple[str, ...], label: str) -> Path:
    found: list[Path] = []
    for pattern in patterns:
        found.extend(directory.glob(pattern))
    found = sorted({path.resolve() for path in found if path.is_file()})
    if not found:
        raise FileNotFoundError(f"Nenhum arquivo de {label} encontrado em {directory}")
    if len(found) > 1:
        names = ", ".join(path.name for path in found)
        raise ValueError(f"Mais de um arquivo candidato para {label}: {names}")
    return found[0]


def discover_fact_files(raw_dir: Path) -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    for flow, folder in (("EXP", raw_dir / "exp"), ("IMP", raw_dir / "imp")):
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.csv")):
            if re.search(rf"^{flow}_\d{{4}}", path.name, flags=re.IGNORECASE):
                files.append((flow, path.resolve()))
    if not files:
        raise FileNotFoundError(
            f"Nenhum EXP_AAAA.csv ou IMP_AAAA.csv encontrado sob {raw_dir}"
        )
    return files


def _read_csv_header(path: Path, encoding: str) -> set[str]:
    pandas_encoding = {
        "windows-1252": "cp1252",
        "latin-1": "latin1",
    }.get(encoding, encoding)
    frame = pd.read_csv(path, sep=";", encoding=pandas_encoding, nrows=0)
    return {normalize_header(col) for col in frame.columns}


def _create_schema(con) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS etl_files (
            source_file VARCHAR PRIMARY KEY,
            flow VARCHAR NOT NULL,
            fingerprint VARCHAR NOT NULL,
            rows_loaded BIGINT NOT NULL,
            loaded_at TIMESTAMP NOT NULL
        );

        CREATE TABLE IF NOT EXISTS fact_comex (
            FLUXO VARCHAR NOT NULL,
            CO_ANO INTEGER NOT NULL,
            CO_MES INTEGER NOT NULL,
            CO_NCM VARCHAR NOT NULL,
            CO_UNID VARCHAR,
            CO_PAIS VARCHAR,
            SG_UF_NCM VARCHAR,
            CO_VIA VARCHAR,
            CO_URF VARCHAR,
            QT_ESTAT DOUBLE,
            KG_LIQUIDO DOUBLE,
            VL_FOB DOUBLE,
            VL_FRETE DOUBLE,
            VL_SEGURO DOUBLE,
            SOURCE_FILE VARCHAR NOT NULL
        );
        """
    )


def _replace_dimensions(con, dims: AuxiliaryDimensions) -> None:
    registrations = {
        "_ncm_df": dims.ncm,
        "_country_df": dims.country,
        "_unit_df": dims.unit,
        "_calendar_df": dims.calendar_month,
    }
    try:
        for name, frame in registrations.items():
            con.register(name, frame)
        con.execute("CREATE OR REPLACE TABLE dim_ncm AS SELECT * FROM _ncm_df")
        con.execute("CREATE OR REPLACE TABLE dim_country AS SELECT * FROM _country_df")
        con.execute("CREATE OR REPLACE TABLE dim_unit AS SELECT * FROM _unit_df")
        con.execute("CREATE OR REPLACE TABLE dim_calendar_month AS SELECT * FROM _calendar_df")
    finally:
        for name in registrations:
            try:
                con.unregister(name)
            except Exception:
                pass


def _numeric_sql(column: str) -> str:
    # Os fatos oficiais usam inteiros sem separador decimal; o replace também
    # tolera vírgula em arquivos derivados.
    return f"try_cast(replace(trim({column}), ',', '.') AS DOUBLE)"


def _load_fact_file(con, flow: str, path: Path, encoding: str) -> int:
    source = str(path.resolve())
    path_sql = sql_literal(path.resolve())
    source_sql = sql_literal(source)
    encoding_sql = sql_literal(encoding)
    has_import_values = flow == "IMP"
    freight = _numeric_sql("VL_FRETE") if has_import_values else "CAST(NULL AS DOUBLE)"
    insurance = _numeric_sql("VL_SEGURO") if has_import_values else "CAST(NULL AS DOUBLE)"

    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE _new_fact AS
        SELECT
            {sql_literal(flow)} AS FLUXO,
            try_cast(trim(CO_ANO) AS INTEGER) AS CO_ANO,
            try_cast(trim(CO_MES) AS INTEGER) AS CO_MES,
            lpad(trim(CO_NCM), 8, '0') AS CO_NCM,
            lpad(trim(CO_UNID), 2, '0') AS CO_UNID,
            lpad(trim(CO_PAIS), 3, '0') AS CO_PAIS,
            upper(trim(SG_UF_NCM)) AS SG_UF_NCM,
            lpad(trim(CO_VIA), 2, '0') AS CO_VIA,
            lpad(trim(CO_URF), 7, '0') AS CO_URF,
            {_numeric_sql('QT_ESTAT')} AS QT_ESTAT,
            {_numeric_sql('KG_LIQUIDO')} AS KG_LIQUIDO,
            {_numeric_sql('VL_FOB')} AS VL_FOB,
            {freight} AS VL_FRETE,
            {insurance} AS VL_SEGURO,
            {source_sql} AS SOURCE_FILE
        FROM read_csv_auto(
            {path_sql},
            delim=';',
            header=true,
            all_varchar=true,
            sample_size=-1,
            encoding={encoding_sql}
        )
        WHERE try_cast(trim(CO_ANO) AS INTEGER) IS NOT NULL
          AND try_cast(trim(CO_MES) AS INTEGER) BETWEEN 1 AND 12
          AND trim(CO_NCM) <> '';
        """
    )
    rows = int(con.execute("SELECT count(*) FROM _new_fact").fetchone()[0])
    if rows == 0:
        raise ValueError(f"O arquivo não produziu linhas válidas: {path}")

    years = [row[0] for row in con.execute("SELECT DISTINCT CO_ANO FROM _new_fact ORDER BY 1").fetchall()]
    match = re.search(r"_(\d{4})", path.name)
    if match and years != [int(match.group(1))]:
        raise ValueError(
            f"Ano no nome de {path.name} ({match.group(1)}) difere dos anos internos: {years}"
        )

    con.execute("BEGIN TRANSACTION")
    try:
        con.execute("DELETE FROM fact_comex WHERE SOURCE_FILE = ?", [source])
        con.execute("INSERT INTO fact_comex SELECT * FROM _new_fact")
        con.execute("DELETE FROM etl_files WHERE source_file = ?", [source])
        con.execute(
            "INSERT INTO etl_files VALUES (?, ?, ?, ?, ?)",
            [source, flow, fingerprint(path), rows, datetime.now(timezone.utc).replace(tzinfo=None)],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return rows


def _create_indexes_and_view(con, *, create_indexes: bool = True) -> None:
    if create_indexes:
        con.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_fact_year_month ON fact_comex (FLUXO, CO_ANO, CO_MES);
        CREATE INDEX IF NOT EXISTS idx_fact_ncm ON fact_comex (CO_NCM);
        CREATE INDEX IF NOT EXISTS idx_fact_country ON fact_comex (CO_PAIS);
            """
        )

    con.execute(
        """
        CREATE OR REPLACE VIEW vw_comex AS
        SELECT
            f.*,
            coalesce(n.SETOR, 'Não classificado') AS SETOR,
            coalesce(n.CATEGORIA_USO, 'Não classificado') AS CATEGORIA_USO,
            n.CO_SH2,
            n.NO_SH2_POR,
            n.CO_SH4,
            n.NO_SH4_POR,
            n.CO_SH6,
            n.NO_SH6_POR,
            n.NO_NCM_POR,
            coalesce(p.PAIS, 'País não identificado') AS PAIS,
            p.CO_PAIS_ISOA3,
            coalesce(u.UNIDADE, 'Unidade não identificada') AS UNIDADE,
            c.DIAS_UTEIS
        FROM fact_comex f
        LEFT JOIN dim_ncm n USING (CO_NCM)
        LEFT JOIN dim_country p USING (CO_PAIS)
        LEFT JOIN dim_unit u USING (CO_UNID)
        LEFT JOIN dim_calendar_month c
          ON f.CO_ANO = c.ANO AND f.CO_MES = c.MES;
        """
    )


def run_etl(project_dir: Path, rebuild: bool = False) -> EtlResult:
    duckdb = _import_duckdb()
    project_dir = project_dir.resolve()
    raw_dir = project_dir / "data" / "raw"
    # "AUX" é um nome reservado no Windows e não pode ser usado de forma
    # confiável como pasta. "auxiliares" mantém o projeto compatível com
    # Windows, Linux e contêineres.
    aux_dir = raw_dir / "auxiliares"
    database = project_dir / "data" / "processed" / "comex.duckdb"
    database.parent.mkdir(parents=True, exist_ok=True)

    aux_file = _resolve_single_file(
        aux_dir,
        ("TABELAS_AUXILIARES*.xlsx", "tabelas_auxiliares*.xlsx"),
        "tabelas auxiliares",
    )
    calendar_file = _resolve_single_file(
        aux_dir,
        ("dados_calendario*.xlsx", "DADOS_CALENDARIO*.xlsx"),
        "calendário",
    )
    dims = load_auxiliary_dimensions(aux_file, calendar_file)
    fact_files = discover_fact_files(raw_dir)

    if rebuild and database.exists():
        database.unlink()

    con = duckdb.connect(str(database))
    loaded = skipped = rows_loaded = 0
    try:
        con.execute("SET preserve_insertion_order = false")
        _create_schema(con)
        _replace_dimensions(con, dims)
        metadata = {
            row[0]: row[1]
            for row in con.execute("SELECT source_file, fingerprint FROM etl_files").fetchall()
        }
        current_sources = {str(path.resolve()) for _, path in fact_files}
        stale_sources = set(metadata).difference(current_sources)
        for source in stale_sources:
            con.execute("DELETE FROM fact_comex WHERE SOURCE_FILE = ?", [source])
            con.execute("DELETE FROM etl_files WHERE source_file = ?", [source])

        for flow, path in fact_files:
            current_fingerprint = fingerprint(path)
            if metadata.get(str(path.resolve())) == current_fingerprint:
                skipped += 1
                continue
            encoding = detect_text_encoding(path)
            columns = _read_csv_header(path, encoding)
            required = set(FACT_REQUIRED)
            if flow == "IMP":
                required |= {"VL_FRETE", "VL_SEGURO"}
            missing = required.difference(columns)
            if missing:
                raise ValueError(f"Colunas ausentes em {path.name}: {', '.join(sorted(missing))}")
            rows_loaded += _load_fact_file(con, flow, path, encoding)
            loaded += 1

        _create_indexes_and_view(con)
        con.execute("CHECKPOINT")
    finally:
        con.close()

    return EtlResult(
        files_loaded=loaded,
        files_skipped=skipped,
        rows_loaded=rows_loaded,
        database=database,
        sheet_map=dims.sheet_map,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ETL incremental dos microdados SECEX")
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Diretório raiz do projeto",
    )
    parser.add_argument("--rebuild", action="store_true", help="Reconstrói o banco do zero")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = run_etl(args.project_dir, rebuild=args.rebuild)
    print(
        f"ETL concluído: {result.files_loaded} arquivo(s) carregado(s), "
        f"{result.files_skipped} ignorado(s), {result.rows_loaded:,} linhas novas."
    )
    print(f"Banco: {result.database}")
    print("Abas usadas:", result.sheet_map)


if __name__ == "__main__":
    main()
