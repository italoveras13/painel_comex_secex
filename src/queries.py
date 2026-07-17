from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

import pandas as pd


FILTER_COLUMNS = {
    "sectors": "SETOR",
    "categories": "CATEGORIA_USO",
    "sh2": "CO_SH2",
    "sh4": "CO_SH4",
    "sh6": "CO_SH6",
    "ncm": "CO_NCM",
}

LEVELS = {
    "Setor": ("SETOR", "SETOR"),
    "Categoria de uso": ("CATEGORIA_USO", "CATEGORIA_USO"),
    "SH2": ("CO_SH2", "NO_SH2_POR"),
    "SH4": ("CO_SH4", "NO_SH4_POR"),
    "SH6": ("CO_SH6", "NO_SH6_POR"),
    "NCM": ("CO_NCM", "NO_NCM_POR"),
}


@dataclass(frozen=True)
class FilterState:
    flow: str = "EXP"
    year: int | None = None
    months: tuple[int, ...] = ()
    sectors: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    sh2: tuple[str, ...] = ()
    sh4: tuple[str, ...] = ()
    sh6: tuple[str, ...] = ()
    ncm: tuple[str, ...] = ()


def _connect(database: Path):
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError("DuckDB não está instalado.") from exc
    return duckdb.connect(str(database), read_only=True)


def database_token(database: Path) -> tuple[int, int]:
    stat = database.stat()
    return stat.st_mtime_ns, stat.st_size


def _placeholders(values: Iterable[object]) -> str:
    return ", ".join("?" for _ in values)


def _where(
    state: FilterState,
    *,
    include_year: bool = True,
    exclude: str | None = None,
    year_range: tuple[int, int] | None = None,
    include_flow: bool = True,
) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if include_flow:
        clauses.append("FLUXO = ?")
        params.append(state.flow)
    if year_range is not None:
        clauses.append("CO_ANO BETWEEN ? AND ?")
        params.extend(year_range)
    elif include_year and state.year is not None:
        clauses.append("CO_ANO = ?")
        params.append(state.year)
    if state.months and exclude != "months":
        clauses.append(f"CO_MES IN ({_placeholders(state.months)})")
        params.extend(state.months)
    for attribute, column in FILTER_COLUMNS.items():
        values = getattr(state, attribute)
        if values and exclude != attribute:
            clauses.append(f"{column} IN ({_placeholders(values)})")
            params.extend(values)
    return " AND ".join(clauses) if clauses else "1 = 1", params


def available_years(database: Path, flow: str) -> list[int]:
    with _connect(database) as con:
        rows = con.execute(
            "SELECT DISTINCT CO_ANO FROM fact_comex WHERE FLUXO = ? ORDER BY CO_ANO DESC",
            [flow],
        ).fetchall()
    return [int(row[0]) for row in rows]


def available_months(database: Path, flow: str, year: int) -> list[int]:
    with _connect(database) as con:
        rows = con.execute(
            """
            SELECT DISTINCT CO_MES
            FROM fact_comex
            WHERE FLUXO = ? AND CO_ANO = ?
            ORDER BY CO_MES
            """,
            [flow, year],
        ).fetchall()
    return [int(row[0]) for row in rows]


def filter_options(database: Path, state: FilterState, attribute: str) -> pd.DataFrame:
    if attribute not in FILTER_COLUMNS:
        raise ValueError(f"Filtro desconhecido: {attribute}")
    column = FILTER_COLUMNS[attribute]
    label_column = {
        "sectors": "SETOR",
        "categories": "CATEGORIA_USO",
        "sh2": "NO_SH2_POR",
        "sh4": "NO_SH4_POR",
        "sh6": "NO_SH6_POR",
        "ncm": "NO_NCM_POR",
    }[attribute]
    where, params = _where(state, exclude=attribute)
    with _connect(database) as con:
        frame = con.execute(
            f"""
            SELECT DISTINCT
                {column} AS CODIGO,
                coalesce({label_column}, {column}) AS DESCRICAO
            FROM vw_comex
            WHERE {where} AND {column} IS NOT NULL
            ORDER BY 2, 1
            """,
            params,
        ).df()
    frame["CODIGO"] = frame["CODIGO"].astype(str)
    frame["DESCRICAO"] = frame["DESCRICAO"].astype(str)
    return frame


def summary_metrics(database: Path, state: FilterState) -> dict[str, float | int | None]:
    where, params = _where(state)
    with _connect(database) as con:
        row = con.execute(
            f"""
            SELECT
                sum(VL_FOB) AS VL_FOB,
                sum(KG_LIQUIDO) AS KG_LIQUIDO,
                sum(QT_ESTAT) AS QT_ESTAT,
                CASE WHEN sum(KG_LIQUIDO) > 0
                     THEN sum(VL_FOB) / sum(KG_LIQUIDO) END AS FOB_POR_KG,
                count(*) AS REGISTROS,
                count(DISTINCT CO_NCM) AS NCMS,
                count(DISTINCT CO_PAIS) AS PAISES
            FROM vw_comex
            WHERE {where}
            """,
            params,
        ).fetchone()
    keys = ["VL_FOB", "KG_LIQUIDO", "QT_ESTAT", "FOB_POR_KG", "REGISTROS", "NCMS", "PAISES"]
    return dict(zip(keys, row, strict=True))


def hierarchy_table(
    database: Path,
    state: FilterState,
    level: str,
    limit: int = 500,
) -> pd.DataFrame:
    if level not in LEVELS:
        raise ValueError(f"Nível inválido: {level}")
    code, label = LEVELS[level]
    where, params = _where(state)
    with _connect(database) as con:
        frame = con.execute(
            f"""
            WITH agrupado AS (
                SELECT
                    {code} AS CODIGO,
                    coalesce({label}, {code}, 'Não classificado') AS DESCRICAO,
                    sum(KG_LIQUIDO) AS KG_LIQUIDO,
                    sum(VL_FOB) AS VL_FOB,
                    sum(QT_ESTAT) AS QT_ESTAT
                FROM vw_comex
                WHERE {where}
                GROUP BY 1, 2
            )
            SELECT
                *,
                CASE WHEN KG_LIQUIDO > 0 THEN VL_FOB / KG_LIQUIDO END AS FOB_POR_KG,
                CASE WHEN sum(VL_FOB) OVER () > 0
                     THEN VL_FOB / sum(VL_FOB) OVER () END AS PARTICIPACAO_FOB
            FROM agrupado
            ORDER BY VL_FOB DESC NULLS LAST
            LIMIT ?
            """,
            [*params, limit],
        ).df()
    return frame


def trade_balance_by_country(
    database: Path,
    state: FilterState,
) -> pd.DataFrame:
    """Calcula exportações, importações e saldo para o mesmo recorte."""
    if state.year is None:
        raise ValueError("Selecione um ano.")
    where, params = _where(state, include_flow=False)
    with _connect(database) as con:
        frame = con.execute(
            f"""
            WITH paises AS (
                SELECT
                    CO_PAIS,
                    PAIS,
                    sum(CASE WHEN FLUXO = 'EXP' THEN VL_FOB ELSE 0 END) AS EXPORTACOES,
                    sum(CASE WHEN FLUXO = 'IMP' THEN VL_FOB ELSE 0 END) AS IMPORTACOES
                FROM vw_comex
                WHERE {where} AND FLUXO IN ('EXP', 'IMP')
                GROUP BY CO_PAIS, PAIS
            )
            SELECT
                CO_PAIS,
                PAIS,
                EXPORTACOES,
                IMPORTACOES,
                EXPORTACOES - IMPORTACOES AS SALDO,
                EXPORTACOES + IMPORTACOES AS CORRENTE_COMERCIO,
                CASE
                    WHEN EXPORTACOES - IMPORTACOES > 0 THEN 'Superávit'
                    WHEN EXPORTACOES - IMPORTACOES < 0 THEN 'Déficit'
                    ELSE 'Zerado'
                END AS SITUACAO
            FROM paises
            WHERE EXPORTACOES <> 0 OR IMPORTACOES <> 0
            ORDER BY abs(EXPORTACOES - IMPORTACOES) DESC, PAIS
            """,
            params,
        ).df()
    return frame


def section301_exposure(
    database: Path,
    state: FilterState,
    reference_csv: Path,
) -> pd.DataFrame:
    """Cruza exportações brasileiras aos EUA com as isenções do Anexo II por SH6."""
    if state.year is None:
        raise ValueError("Selecione um ano.")
    if not reference_csv.exists():
        raise FileNotFoundError(f"Referência da Seção 301 não encontrada: {reference_csv}")

    export_state = replace(state, flow="EXP")
    where, params = _where(export_state)
    with _connect(database) as con:
        exports = con.execute(
            f"""
            SELECT
                CO_NCM,
                coalesce(NO_NCM_POR, CO_NCM) AS NO_NCM_POR,
                CO_SH6,
                coalesce(NO_SH6_POR, CO_SH6) AS NO_SH6_POR,
                sum(VL_FOB) AS VL_FOB,
                sum(KG_LIQUIDO) AS KG_LIQUIDO
            FROM vw_comex
            WHERE {where}
              AND CO_PAIS_ISOA3 = 'USA'
              AND CO_SH6 IS NOT NULL
            GROUP BY CO_NCM, NO_NCM_POR, CO_SH6, NO_SH6_POR
            ORDER BY VL_FOB DESC NULLS LAST
            """,
            params,
        ).df()
    if exports.empty:
        return exports

    reference = pd.read_csv(
        reference_csv,
        sep=";",
        dtype={"CO_SH6": "string"},
        keep_default_na=False,
    )
    reference["CO_SH6"] = reference["CO_SH6"].str.zfill(6)
    merged = exports.merge(reference, on="CO_SH6", how="left", validate="many_to_one")
    matched = merged["QTD_LINHAS_HTSUS"].notna()
    scope_type = merged["TIPO_ESCOPO_SH6"].fillna("")
    merged["SITUACAO_301"] = "Sem correspondência - potencialmente afetado"
    merged.loc[matched, "SITUACAO_301"] = "Correspondência com isenção no SH6"
    merged.loc[matched & scope_type.eq("Condicionado"), "SITUACAO_301"] = (
        "Correspondência condicionada no SH6"
    )
    merged.loc[matched & scope_type.eq("Misto"), "SITUACAO_301"] = "Correspondência mista no SH6"

    scope_translation = {
        "Ex": "Somente o produto descrito no Anexo II",
        "Pharma": "Somente uso farmacêutico",
        "Aircraft": "Somente aeronaves civis e artigos abrangidos",
    }

    def translate_scope(value: object) -> str:
        if value is None or pd.isna(value):
            return ""
        parts = [part.strip() for part in str(value).split("|") if part.strip()]
        return " | ".join(scope_translation.get(part, part) for part in parts)

    merged["LIMITACOES_PT"] = merged["LIMITACOES_ESCOPO"].map(translate_scope)
    total = merged["VL_FOB"].sum(min_count=1)
    merged["PARTICIPACAO_FOB_EUA"] = merged["VL_FOB"] / total if total and total > 0 else pd.NA
    merged["QTD_LINHAS_HTSUS"] = merged["QTD_LINHAS_HTSUS"].fillna(0).astype(int)
    for column in ("CODIGOS_HTSUS", "DESCRICAO_HTSUS_EXEMPLO", "LIMITACOES_PT"):
        merged[column] = merged[column].fillna("")
    return merged.sort_values("VL_FOB", ascending=False, na_position="last")


def section301_sector_impact(
    database: Path,
    state: FilterState,
    reference_csv: Path,
    level: str = "ISIC",
) -> pd.DataFrame:
    """Mede exposição e dependência dos EUA por setor macro ou seção ISIC.

    A exposição potencial considera exportações aos EUA cujo SH6 não possui
    correspondência no Anexo II. A dependência usa todas as exportações do
    grupo para comparar os EUA com os demais destinos.
    """
    if state.year is None:
        raise ValueError("Selecione um ano.")
    if not reference_csv.exists():
        raise FileNotFoundError(f"Referência da Seção 301 não encontrada: {reference_csv}")
    if level not in {"SETOR", "ISIC"}:
        raise ValueError(f"Nível setorial inválido: {level}")

    export_state = replace(state, flow="EXP")
    where, params = _where(export_state)
    if level == "SETOR":
        dimensions = ["SETOR"]
    else:
        dimensions = ["SETOR", "CO_ISIC_SECAO", "NO_ISIC_SECAO"]
    dimension_sql = ", ".join(dimensions)

    reference = pd.read_csv(
        reference_csv,
        sep=";",
        usecols=["CO_SH6"],
        dtype={"CO_SH6": "string"},
        keep_default_na=False,
    ).drop_duplicates("CO_SH6")
    reference["CO_SH6"] = reference["CO_SH6"].str.zfill(6)

    with _connect(database) as con:
        con.register("_section301_ref", reference)
        try:
            frame = con.execute(
                f"""
                WITH filtrado AS (
                    SELECT *
                    FROM vw_comex
                    WHERE {where}
                ),
                base AS (
                    SELECT
                        f.SETOR,
                        coalesce(cast(n.CO_ISIC_SECAO AS VARCHAR), 'N/C') AS CO_ISIC_SECAO,
                        coalesce(n.NO_ISIC_SECAO, 'Não classificado') AS NO_ISIC_SECAO,
                        f.CO_PAIS_ISOA3,
                        f.PAIS,
                        f.CO_SH6,
                        sum(f.VL_FOB) AS VALOR
                    FROM filtrado f
                    LEFT JOIN dim_ncm n USING (CO_NCM)
                    GROUP BY 1, 2, 3, 4, 5, 6
                ),
                destinos AS (
                    SELECT
                        {dimension_sql}, CO_PAIS_ISOA3, PAIS, sum(VALOR) AS VALOR
                    FROM base
                    GROUP BY {dimension_sql}, CO_PAIS_ISOA3, PAIS
                ),
                ranking AS (
                    SELECT *, dense_rank() OVER (
                        PARTITION BY {dimension_sql}
                        ORDER BY VALOR DESC NULLS LAST
                    ) AS POSICAO
                    FROM destinos
                ),
                mundo AS (
                    SELECT {dimension_sql}, sum(VALOR) AS EXPORTACOES_MUNDO
                    FROM destinos
                    GROUP BY {dimension_sql}
                ),
                eua AS (
                    SELECT
                        {dimension_sql},
                        sum(b.VALOR) AS EXPORTACOES_EUA,
                        sum(CASE WHEN r.CO_SH6 IS NULL THEN b.VALOR ELSE 0 END)
                            AS VALOR_POTENCIALMENTE_AFETADO
                    FROM base b
                    LEFT JOIN _section301_ref r USING (CO_SH6)
                    WHERE b.CO_PAIS_ISOA3 = 'USA'
                    GROUP BY {dimension_sql}
                ),
                posicao_eua AS (
                    SELECT {dimension_sql}, min(POSICAO) AS POSICAO_EUA
                    FROM ranking
                    WHERE CO_PAIS_ISOA3 = 'USA'
                    GROUP BY {dimension_sql}
                ),
                principal AS (
                    SELECT
                        {dimension_sql},
                        string_agg(PAIS, ' / ' ORDER BY PAIS) AS PRINCIPAL_DESTINO
                    FROM ranking
                    WHERE POSICAO = 1
                    GROUP BY {dimension_sql}
                )
                SELECT
                    m.*,
                    p.PRINCIPAL_DESTINO,
                    pe.POSICAO_EUA,
                    CASE WHEN pe.POSICAO_EUA = 1 THEN 'Sim' ELSE 'Não' END
                        AS EUA_MAIOR_CLIENTE,
                    e.EXPORTACOES_EUA,
                    e.EXPORTACOES_EUA / nullif(m.EXPORTACOES_MUNDO, 0)
                        AS PARTICIPACAO_EUA,
                    e.VALOR_POTENCIALMENTE_AFETADO,
                    e.VALOR_POTENCIALMENTE_AFETADO / nullif(e.EXPORTACOES_EUA, 0)
                        AS PARTICIPACAO_AFETADA_NOS_EUA,
                    e.VALOR_POTENCIALMENTE_AFETADO / nullif(m.EXPORTACOES_MUNDO, 0)
                        AS EXPOSICAO_EXPORTACOES_SETOR
                FROM mundo m
                INNER JOIN eua e USING ({dimension_sql})
                LEFT JOIN posicao_eua pe USING ({dimension_sql})
                LEFT JOIN principal p USING ({dimension_sql})
                WHERE e.EXPORTACOES_EUA > 0
                ORDER BY e.VALOR_POTENCIALMENTE_AFETADO DESC NULLS LAST
                """,
                params,
            ).df()
        finally:
            con.unregister("_section301_ref")
    if "POSICAO_EUA" in frame.columns:
        frame["POSICAO_EUA"] = frame["POSICAO_EUA"].astype("Int64")
    return frame


def monthly_history(
    database: Path,
    state: FilterState,
    metric: str,
    daily_average: bool,
    history_years: int = 5,
) -> tuple[pd.DataFrame, list[int]]:
    if state.year is None:
        raise ValueError("Selecione um ano.")
    if metric not in {"VL_FOB", "KG_LIQUIDO"}:
        raise ValueError("Métrica mensal inválida.")
    first_year = state.year - history_years
    where, params = _where(
        state,
        include_year=False,
        year_range=(first_year, state.year),
    )
    numerator = f"sum({metric})"
    value_expr = (
        f"CASE WHEN max(DIAS_UTEIS) > 0 THEN {numerator} / max(DIAS_UTEIS) END"
        if daily_average
        else numerator
    )
    with _connect(database) as con:
        frame = con.execute(
            f"""
            SELECT CO_ANO AS ANO, CO_MES AS MES, {value_expr} AS VALOR,
                   max(DIAS_UTEIS) AS DIAS_UTEIS
            FROM vw_comex
            WHERE {where}
            GROUP BY CO_ANO, CO_MES
            ORDER BY CO_ANO, CO_MES
            """,
            params,
        ).df()
    historical_years = sorted(
        int(value)
        for value in frame.loc[frame["ANO"] < state.year, "ANO"].dropna().unique()
    )
    return frame, historical_years


def country_ranking(
    database: Path,
    state: FilterState,
    metric: str,
    top_n: int = 15,
    comparison_years: int = 2,
) -> pd.DataFrame:
    if state.year is None:
        raise ValueError("Selecione um ano.")
    if metric not in {"VL_FOB", "KG_LIQUIDO"}:
        raise ValueError("Métrica do ranking inválida.")
    where, params = _where(
        state,
        include_year=False,
        year_range=(state.year - comparison_years, state.year),
    )
    with _connect(database) as con:
        raw = con.execute(
            f"""
            SELECT CO_ANO AS ANO, CO_PAIS, PAIS, sum({metric}) AS VALOR
            FROM vw_comex
            WHERE {where}
            GROUP BY CO_ANO, CO_PAIS, PAIS
            """,
            params,
        ).df()
    if raw.empty:
        return pd.DataFrame(columns=["CO_PAIS", "PAIS", "VALOR", "PARTICIPACAO"])

    names = (
        raw.sort_values("ANO")
        .drop_duplicates("CO_PAIS", keep="last")[["CO_PAIS", "PAIS"]]
        .set_index("CO_PAIS")
    )
    pivot = raw.pivot_table(index="CO_PAIS", columns="ANO", values="VALOR", aggfunc="sum")
    current = pivot.get(state.year, pd.Series(index=pivot.index, dtype=float)).rename("VALOR")
    result = names.join(current, how="right")
    total = result["VALOR"].sum(min_count=1)
    result["PARTICIPACAO"] = result["VALOR"] / total if total and total > 0 else pd.NA
    for lag in range(1, comparison_years + 1):
        previous = pivot.get(state.year - lag, pd.Series(index=pivot.index, dtype=float))
        denominator = previous.where(previous != 0)
        result[f"VAR_{lag}A"] = result["VALOR"].sub(previous).div(denominator)
    result = (
        result.reset_index()
        .sort_values("VALOR", ascending=False, na_position="last")
        .head(top_n)
    )
    return result


def quality_report(database: Path) -> pd.DataFrame:
    with _connect(database) as con:
        rows = con.execute(
            """
            SELECT 'Registros na fato' AS INDICADOR, count(*)::DOUBLE AS VALOR
            FROM fact_comex
            UNION ALL
            SELECT 'NCM sem classificação', count(*)::DOUBLE
            FROM vw_comex WHERE SETOR = 'Não classificado'
            UNION ALL
            SELECT 'País sem descrição', count(*)::DOUBLE
            FROM vw_comex WHERE PAIS = 'País não identificado'
            UNION ALL
            SELECT 'Registros sem dias úteis', count(*)::DOUBLE
            FROM vw_comex WHERE DIAS_UTEIS IS NULL OR DIAS_UTEIS <= 0
            UNION ALL
            SELECT 'Registros SH2 sem descrição', count(*)::DOUBLE
            FROM vw_comex WHERE CO_SH2 IS NOT NULL AND NO_SH2_POR IS NULL
            UNION ALL
            SELECT 'Registros SH4 sem descrição', count(*)::DOUBLE
            FROM vw_comex WHERE CO_SH4 IS NOT NULL AND NO_SH4_POR IS NULL
            UNION ALL
            SELECT 'Registros SH6 sem descrição', count(*)::DOUBLE
            FROM vw_comex WHERE CO_SH6 IS NOT NULL AND NO_SH6_POR IS NULL
            UNION ALL
            SELECT 'Arquivos processados', count(*)::DOUBLE
            FROM etl_files
            """
        ).df()
        files = con.execute(
            """
            SELECT flow AS FLUXO, source_file AS ARQUIVO, rows_loaded AS LINHAS, loaded_at AS CARREGADO_EM
            FROM etl_files ORDER BY flow, source_file
            """
        ).df()
    total = rows.loc[rows["INDICADOR"] == "Registros na fato", "VALOR"].squeeze()
    rows["PERCENTUAL"] = rows.apply(
        lambda row: row["VALOR"] / total
        if total and row["INDICADOR"] in {
            "NCM sem classificação",
            "País sem descrição",
            "Registros sem dias úteis",
            "Registros SH2 sem descrição",
            "Registros SH4 sem descrição",
            "Registros SH6 sem descrição",
        }
        else pd.NA,
        axis=1,
    )
    rows.attrs["files"] = files
    return rows


def without_downstream_filters(state: FilterState, attribute: str) -> FilterState:
    """Limpa níveis inferiores ao alterar um filtro hierárquico."""
    order = ["sectors", "categories", "sh2", "sh4", "sh6", "ncm"]
    index = order.index(attribute)
    updates = {name: () for name in order[index + 1 :]}
    return replace(state, **updates)
