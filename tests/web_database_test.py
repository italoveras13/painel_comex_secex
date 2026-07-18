"""Valida a geração do banco agregado para publicação."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.etl import _create_indexes_and_view  # noqa: E402
from src.queries import (  # noqa: E402
    FilterState,
    country_composition,
    country_ranking,
    hierarchy_table,
    monthly_history,
    section301_state_impact,
    summary_metrics,
)
from src.web_database import build_web_database  # noqa: E402


def _create_source(database: Path) -> None:
    con = duckdb.connect(str(database))
    con.execute(
        """
        CREATE TABLE etl_files (
            source_file VARCHAR, flow VARCHAR, fingerprint VARCHAR,
            rows_loaded BIGINT, loaded_at TIMESTAMP
        );
        INSERT INTO etl_files VALUES ('EXP_2026.csv', 'EXP', 'abc', 4, current_timestamp);

        CREATE TABLE dim_ncm AS SELECT * FROM (VALUES
            ('01010100', 'Agropecuária', 'Bens Intermediários', '01', 'Animais vivos',
             '0101', 'Animais', '010101', 'Animais reprodutores', 'Animal reprodutor',
             'A', 'Agricultura'),
            ('02011000', 'Indústria de Transformação', 'Bens de Consumo', '02', 'Carnes',
             '0201', 'Carnes bovinas', '020110', 'Carne bovina', 'Carne bovina fresca',
             'C', 'Indústrias de transformação')
        ) t(CO_NCM, SETOR, CATEGORIA_USO, CO_SH2, NO_SH2_POR, CO_SH4, NO_SH4_POR,
            CO_SH6, NO_SH6_POR, NO_NCM_POR, CO_ISIC_SECAO, NO_ISIC_SECAO);

        CREATE TABLE dim_country AS SELECT * FROM (VALUES
            ('249', 'Estados Unidos', 'USA'), ('160', 'China', 'CHN')
        ) t(CO_PAIS, PAIS, CO_PAIS_ISOA3);
        CREATE TABLE dim_unit AS SELECT * FROM (VALUES ('10', 'Quilograma')) t(CO_UNID, UNIDADE);
        CREATE TABLE dim_calendar_month AS SELECT * FROM (VALUES (2026, 1, 21)) t(ANO, MES, DIAS_UTEIS);

        CREATE TABLE fact_comex (
            FLUXO VARCHAR, CO_ANO INTEGER, CO_MES INTEGER, CO_NCM VARCHAR,
            CO_UNID VARCHAR, CO_PAIS VARCHAR, SG_UF_NCM VARCHAR, CO_VIA VARCHAR,
            CO_URF VARCHAR, QT_ESTAT DOUBLE, KG_LIQUIDO DOUBLE, VL_FOB DOUBLE,
            VL_FRETE DOUBLE, VL_SEGURO DOUBLE, SOURCE_FILE VARCHAR
        );
        INSERT INTO fact_comex VALUES
            ('EXP', 2026, 1, '01010100', '10', '249', 'SP', '01', '0000001', 2, 20, 100, NULL, NULL, 'EXP_2026.csv'),
            ('EXP', 2026, 1, '01010100', '10', '249', 'MG', '04', '0000002', 3, 30, 150, NULL, NULL, 'EXP_2026.csv'),
            ('EXP', 2026, 1, '01010100', '10', '160', 'SP', '01', '0000001', 4, 40, 200, NULL, NULL, 'EXP_2026.csv'),
            ('EXP', 2026, 1, '02011000', '10', '249', 'GO', '07', '0000003', 5, 50, 300, NULL, NULL, 'EXP_2026.csv');
        """
    )
    _create_indexes_and_view(con)
    con.execute("CHECKPOINT")
    con.close()


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        source = Path(temp) / "comex.duckdb"
        output = Path(temp) / "comex_web.duckdb"
        _create_source(source)
        result = build_web_database(source, output, memory_limit="256MB", threads=1)
        assert result.source_rows == 4
        assert result.web_rows == 4

        con = duckdb.connect(str(output), read_only=True)
        states = {
            row[0]
            for row in con.execute("SELECT DISTINCT SG_UF_NCM FROM fact_comex").fetchall()
        }
        con.close()
        assert states == {"GO", "MG", "SP"}

        state = FilterState(flow="EXP", year=2026, months=(1,))
        source_summary = summary_metrics(source, state)
        web_summary = summary_metrics(output, state)
        for metric in ("VL_FOB", "KG_LIQUIDO", "QT_ESTAT"):
            assert source_summary[metric] == web_summary[metric]

        source_hierarchy = hierarchy_table(source, state, "Setor")
        web_hierarchy = hierarchy_table(output, state, "Setor")
        assert source_hierarchy[["CODIGO", "VL_FOB"]].equals(
            web_hierarchy[["CODIGO", "VL_FOB"]]
        )
        source_ranking = country_ranking(source, state, "VL_FOB")
        web_ranking = country_ranking(output, state, "VL_FOB")
        assert source_ranking[["CO_PAIS", "VALOR"]].equals(
            web_ranking[["CO_PAIS", "VALOR"]]
        )
        composition = country_composition(output, state, "249", "SETOR").set_index("CODIGO")
        assert composition.loc["Agropecuária", "VL_FOB"] == 250
        assert composition.loc["Indústria de Transformação", "VL_FOB"] == 300
        price_history, _ = monthly_history(output, state, "FOB_POR_KG", False)
        assert round(float(price_history.loc[0, "VALOR"]), 6) == round(750 / 140, 6)
        states = section301_state_impact(
            output,
            state,
            ROOT / "data" / "reference" / "section301_exemptions_sh6.csv",
        ).set_index("UF")
        assert states.loc["SP", "POSICAO_EUA"] == 2
        assert states.loc["MG", "POSICAO_EUA"] == 1
        assert states.loc["SP", "VALOR_POTENCIALMENTE_AFETADO"] == 100
        assert states.loc["GO", "VALOR_POTENCIALMENTE_AFETADO"] == 0
    print("Teste do comex_web.duckdb concluído com sucesso.")


if __name__ == "__main__":
    main()
