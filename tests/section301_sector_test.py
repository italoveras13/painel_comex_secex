"""Teste da análise de dependência setorial da Seção 301."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.queries import FilterState, section301_sector_impact  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        database = Path(temp) / "setores.duckdb"
        con = duckdb.connect(str(database))
        con.execute(
            """
            CREATE TABLE dim_ncm AS SELECT * FROM (VALUES
                ('01010100', 'A', 'Agricultura'),
                ('02011000', 'C', 'Indústrias de transformação'),
                ('03010100', 'C', 'Indústrias de transformação')
            ) t(CO_NCM, CO_ISIC_SECAO, NO_ISIC_SECAO)
            """
        )
        con.execute(
            """
            CREATE TABLE vw_comex AS SELECT * FROM (VALUES
                ('EXP', 2026, 1, '01010100', '010101', 'Agropecuária',
                 'USA', 'Estados Unidos', 60.0),
                ('EXP', 2026, 1, '01010100', '010101', 'Agropecuária',
                 'CHN', 'China', 20.0),
                ('EXP', 2026, 1, '03010100', '030101', 'Indústria de Transformação',
                 'USA', 'Estados Unidos', 100.0),
                ('EXP', 2026, 1, '02011000', '020110', 'Indústria de Transformação',
                 'USA', 'Estados Unidos', 50.0),
                ('EXP', 2026, 1, '03010100', '030101', 'Indústria de Transformação',
                 'CHN', 'China', 200.0),
                ('EXP', 2026, 1, '03010100', '030101', 'Indústria de Transformação',
                 'ARG', 'Argentina', 50.0)
            ) t(FLUXO, CO_ANO, CO_MES, CO_NCM, CO_SH6, SETOR,
                CO_PAIS_ISOA3, PAIS, VL_FOB)
            """
        )
        con.close()

        result = section301_sector_impact(
            database,
            FilterState(flow="IMP", year=2026, months=(1,)),
            ROOT / "data" / "reference" / "section301_exemptions_sh6.csv",
            "ISIC",
        )
        agriculture = result.loc[result["CO_ISIC_SECAO"] == "A"].iloc[0]
        industry = result.loc[result["CO_ISIC_SECAO"] == "C"].iloc[0]
        assert agriculture["EUA_MAIOR_CLIENTE"] == "Sim"
        assert agriculture["POSICAO_EUA"] == 1
        assert abs(agriculture["PARTICIPACAO_EUA"] - 0.75) < 1e-9
        assert industry["EUA_MAIOR_CLIENTE"] == "Não"
        assert industry["POSICAO_EUA"] == 2
        assert abs(industry["VALOR_POTENCIALMENTE_AFETADO"] - 100) < 1e-9
        assert abs(industry["EXPOSICAO_EXPORTACOES_SETOR"] - 0.25) < 1e-9
    print("Teste setorial da Seção 301 concluído com sucesso.")


if __name__ == "__main__":
    main()
