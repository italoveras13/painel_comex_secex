from __future__ import annotations

import argparse
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .etl import _create_indexes_and_view, _import_duckdb
from .utils import sql_literal


@dataclass(frozen=True)
class WebDatabaseResult:
    source: Path
    output: Path
    source_rows: int
    web_rows: int
    source_size: int
    web_size: int

    @property
    def reduction_rows(self) -> float:
        return 1 - self.web_rows / self.source_rows if self.source_rows else 0.0

    @property
    def reduction_size(self) -> float:
        return 1 - self.web_size / self.source_size if self.source_size else 0.0


def _format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"


def _validate_totals(con) -> None:
    metrics = ("QT_ESTAT", "KG_LIQUIDO", "VL_FOB", "VL_FRETE", "VL_SEGURO")
    expressions = ", ".join(f"sum({column})" for column in metrics)
    source = con.execute(
        f"SELECT FLUXO, {expressions} FROM source_db.fact_comex GROUP BY FLUXO ORDER BY FLUXO"
    ).fetchall()
    target = con.execute(
        f"SELECT FLUXO, {expressions} FROM fact_comex GROUP BY FLUXO ORDER BY FLUXO"
    ).fetchall()
    if [row[0] for row in source] != [row[0] for row in target]:
        raise RuntimeError("Os fluxos do banco web diferem do banco completo.")
    for source_row, target_row in zip(source, target, strict=True):
        for column, original, aggregated in zip(metrics, source_row[1:], target_row[1:], strict=True):
            if original is None and aggregated is None:
                continue
            if original is None or aggregated is None or not math.isclose(
                float(original), float(aggregated), rel_tol=1e-11, abs_tol=1e-4
            ):
                raise RuntimeError(
                    f"Falha de validação em {source_row[0]}/{column}: "
                    f"completo={original}, web={aggregated}."
                )


def build_web_database(
    source: Path,
    output: Path,
    *,
    force: bool = False,
    memory_limit: str = "2GB",
    threads: int = 4,
) -> WebDatabaseResult:
    """Cria um DuckDB mensal agregado por fluxo, NCM e país.

    O arquivo completo nunca é modificado. A saída só substitui um arquivo
    existente quando ``force=True`` e depois que toda a validação termina.
    """
    duckdb = _import_duckdb()
    source = source.resolve()
    output = output.resolve()
    if not source.exists():
        raise FileNotFoundError(
            f"Banco completo não encontrado: {source}. Execute run_etl.py primeiro."
        )
    if source == output:
        raise ValueError("O banco web deve ter caminho diferente do banco completo.")
    if output.exists() and not force:
        raise FileExistsError(
            f"O banco web já existe: {output}. Use --force para recriá-lo."
        )
    if threads < 1:
        raise ValueError("O número de threads deve ser pelo menos 1.")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f"{output.stem}.building{output.suffix}")
    spill_directory = output.parent / "duckdb_web_tmp"
    spill_directory.mkdir(parents=True, exist_ok=True)
    if temporary.exists():
        temporary.unlink()

    source_rows = 0
    web_rows = 0
    con = duckdb.connect(str(temporary))
    try:
        con.execute(f"SET memory_limit = {sql_literal(memory_limit)}")
        con.execute(f"SET threads = {int(threads)}")
        con.execute("SET preserve_insertion_order = false")
        con.execute(f"SET temp_directory = {sql_literal(spill_directory)}")
        con.execute(f"ATTACH {sql_literal(source)} AS source_db (READ_ONLY)")

        required = {
            row[0]
            for row in con.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_catalog = 'source_db'
                """
            ).fetchall()
        }
        missing = {
            "fact_comex",
            "etl_files",
            "dim_ncm",
            "dim_country",
            "dim_unit",
            "dim_calendar_month",
        }.difference(required)
        if missing:
            raise RuntimeError(
                "O banco completo não possui as tabelas necessárias: " + ", ".join(sorted(missing))
            )

        source_rows = int(con.execute("SELECT count(*) FROM source_db.fact_comex").fetchone()[0])
        if source_rows == 0:
            raise RuntimeError("O banco completo não possui registros de comércio exterior.")

        print(f"Agregando {source_rows:,} registros por fluxo, ano, mês, NCM e país...")
        con.execute(
            """
            CREATE TABLE fact_comex AS
            WITH agregado AS (
                SELECT
                    FLUXO,
                    CO_ANO,
                    CO_MES,
                    CO_NCM,
                    CO_PAIS,
                    sum(QT_ESTAT) AS QT_ESTAT,
                    sum(KG_LIQUIDO) AS KG_LIQUIDO,
                    sum(VL_FOB) AS VL_FOB,
                    sum(VL_FRETE) AS VL_FRETE,
                    sum(VL_SEGURO) AS VL_SEGURO
                FROM source_db.fact_comex
                GROUP BY FLUXO, CO_ANO, CO_MES, CO_NCM, CO_PAIS
            )
            SELECT
                FLUXO,
                CO_ANO,
                CO_MES,
                CO_NCM,
                CAST(NULL AS VARCHAR) AS CO_UNID,
                CO_PAIS,
                CAST(NULL AS VARCHAR) AS SG_UF_NCM,
                CAST(NULL AS VARCHAR) AS CO_VIA,
                CAST(NULL AS VARCHAR) AS CO_URF,
                QT_ESTAT,
                KG_LIQUIDO,
                VL_FOB,
                VL_FRETE,
                VL_SEGURO,
                'COMEX_WEB_AGREGADO'::VARCHAR AS SOURCE_FILE
            FROM agregado
            ORDER BY FLUXO, CO_ANO, CO_MES, CO_NCM, CO_PAIS
            """
        )
        for table in ("etl_files", "dim_ncm", "dim_country", "dim_unit", "dim_calendar_month"):
            con.execute(f"CREATE TABLE {table} AS SELECT * FROM source_db.{table}")

        con.execute(
            """
            CREATE TABLE web_database_info (
                generated_at TIMESTAMP,
                source_database VARCHAR,
                source_rows BIGINT,
                aggregation_level VARCHAR
            )
            """
        )
        con.execute(
            "INSERT INTO web_database_info VALUES (?, ?, ?, ?)",
            [
                datetime.now(timezone.utc).replace(tzinfo=None),
                str(source),
                source_rows,
                "FLUXO + CO_ANO + CO_MES + CO_NCM + CO_PAIS",
            ],
        )

        # A tabela já é ordenada pelas chaves mais consultadas. Índices ART
        # aumentariam o arquivo publicado e são dispensáveis nessa versão.
        _create_indexes_and_view(con, create_indexes=False)
        web_rows = int(con.execute("SELECT count(*) FROM fact_comex").fetchone()[0])
        _validate_totals(con)
        con.execute("ANALYZE")
        con.execute("DETACH source_db")
        con.execute("CHECKPOINT")
    except Exception:
        con.close()
        if temporary.exists():
            temporary.unlink()
        raise
    else:
        con.close()

    os.replace(temporary, output)
    try:
        spill_directory.rmdir()
    except OSError:
        pass
    result = WebDatabaseResult(
        source=source,
        output=output,
        source_rows=source_rows,
        web_rows=web_rows,
        source_size=source.stat().st_size,
        web_size=output.stat().st_size,
    )
    print("Validação concluída: totais de quantidade, peso e valores preservados.")
    print(f"Linhas: {result.source_rows:,} -> {result.web_rows:,} ({result.reduction_rows:.1%} menor)")
    size_change = (
        f"{result.reduction_size:.1%} menor"
        if result.reduction_size >= 0
        else f"{-result.reduction_size:.1%} maior"
    )
    print(
        f"Tamanho: {_format_bytes(result.source_size)} -> {_format_bytes(result.web_size)} "
        f"({size_change})"
    )
    print(f"Banco web: {result.output}")
    if result.web_size <= 100 * 1024**2:
        print("Publicação: o arquivo cabe no GitHub comum (até 100 MB).")
    elif result.web_size <= 2 * 1024**3:
        print("Publicação: use Git LFS; o arquivo supera 100 MB, mas não 2 GB.")
    else:
        print(
            "Publicação: o arquivo ainda supera 2 GB e não cabe como um único objeto "
            "no Git LFS dos planos GitHub Free/Pro."
        )
    return result


def build_parser() -> argparse.ArgumentParser:
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Gera um DuckDB agregado e otimizado para publicação web."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=project / "data" / "processed" / "comex.duckdb",
        help="Banco completo criado pelo ETL",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=project / "data" / "processed" / "comex_web.duckdb",
        help="Arquivo DuckDB agregado de saída",
    )
    parser.add_argument("--force", action="store_true", help="Substitui a saída existente")
    parser.add_argument(
        "--memory-limit",
        default="2GB",
        help="Limite de memória do DuckDB; o excedente usa disco temporário",
    )
    parser.add_argument("--threads", type=int, default=4, help="Threads usadas na agregação")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    build_web_database(
        args.source,
        args.output,
        force=args.force,
        memory_limit=args.memory_limit,
        threads=args.threads,
    )
