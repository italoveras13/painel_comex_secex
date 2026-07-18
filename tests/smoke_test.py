"""Testes leves que não dependem de Streamlit, Plotly ou DuckDB."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.auxiliary import load_auxiliary_dimensions  # noqa: E402
from src.charts import prepare_monthly_profile  # noqa: E402
from src.queries import FilterState, section301_exposure  # noqa: E402
import src.queries as queries_module  # noqa: E402
from src.utils import normalize_code_value, parse_business_day  # noqa: E402


def create_workbooks(directory: Path) -> tuple[Path, Path]:
    aux = directory / "TABELAS_AUXILIARES.xlsx"
    calendar = directory / "dados_calendario.xlsx"
    with pd.ExcelWriter(aux, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "CO_NCM": [1012100, 27090010, 87032100],
                "NO_NCM_POR": ["Animal reprodutor", "Óleo bruto", "Automóvel"],
                "CO_ISIC_SECAO": ["A", "B", "C"],
                "NO_ISIC_SECAO": ["Agricultura", "Indústrias extrativas", "Transformação"],
            }
        ).to_excel(writer, sheet_name="NCM_ISIC", index=False)
        pd.DataFrame(
            {
                "CO_NCM": [1012100, 27090010, 87032100],
                "CO_CGCE_N1": [2, 4, 1],
                "NO_CGCE_N1": ["Bens intermediários", "Combustíveis e Lubrificantes", "Bens de Capital"],
            }
        ).to_excel(writer, sheet_name="NCM_CGCE", index=False)
        pd.DataFrame(
            {
                "CO_NCM": [1012100, 27090010, 87032100],
                "CO_SH6": [10121, 270900, 870321],
                "NO_SH6_POR": ["Bovinos", "Óleos brutos", "Automóveis"],
                "CO_SH4": [101, 2709, 8703],
                "CO_SH2": [1, 27, 87],
            }
        ).to_excel(writer, sheet_name="NCM_SH", index=False)
        pd.DataFrame(
            {
                "CO_SH2": [1, 27, 87],
                "NO_SH2_POR": [
                    "Animais vivos",
                    "Combustíveis minerais, óleos minerais e produtos da sua destilação",
                    "Veículos automóveis, tratores e suas partes",
                ],
            }
        ).to_excel(writer, sheet_name="SH2", index=False)
        pd.DataFrame(
            {
                "CO_SH4": [101, 2709, 8703],
                "NO_SH4_POR": [
                    "Cavalos, asininos e muares, vivos",
                    "Óleos brutos de petróleo",
                    "Automóveis de passageiros",
                ],
            }
        ).to_excel(writer, sheet_name="SH4", index=False)
        pd.DataFrame(
            {
                "CO_PAIS": [23, 249],
                "NO_PAIS": ["Argentina", "Estados Unidos"],
                "CO_PAIS_ISOA3": ["ARG", "USA"],
            }
        ).to_excel(writer, sheet_name="PAIS", index=False)
        pd.DataFrame({"CO_UNID": [10, 11], "NO_UNID": ["Quilograma", "Número"]}).to_excel(
            writer, sheet_name="UNIDADE", index=False
        )
    with pd.ExcelWriter(calendar, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "CO_ANO": [2026, 2026, 2026, 2026],
                "CO_MES": [1, 1, 1, 1],
                "CO_DIA": [1, 2, 3, 4],
                "FERIADO": [1, 0, 0, 0],
                "NOME_FERIADO": ["Confraternização", None, None, None],
                "DIA_UTIL": [0, 1, "Sim", False],
            }
        ).to_excel(writer, sheet_name="Calendario", index=False)
    return aux, calendar


def main() -> None:
    assert normalize_code_value("123.0", 8) == "00000123"
    assert normalize_code_value("072", 3) == "072"
    assert parse_business_day("Sim") == 1
    assert parse_business_day("não") == 0

    with tempfile.TemporaryDirectory() as temp:
        aux, calendar = create_workbooks(Path(temp))
        dims = load_auxiliary_dimensions(aux, calendar)
        assert dims.ncm["CO_NCM"].tolist()[0] == "01012100"
        assert set(dims.ncm["SETOR"]) == {
            "Agropecuária",
            "Indústria Extrativa",
            "Indústria de Transformação",
        }
        assert dims.ncm.loc[dims.ncm["CO_SH2"] == "01", "NO_SH2_POR"].iloc[0] == "Animais vivos"
        assert dims.ncm.loc[dims.ncm["CO_SH4"] == "2709", "NO_SH4_POR"].iloc[0] == "Óleos brutos de petróleo"
        assert dims.country.loc[dims.country["NO_PAIS"] == "Argentina", "CO_PAIS"].iloc[0] == "023"
        assert int(dims.calendar_month["DIAS_UTEIS"].iloc[0]) == 2

    history = pd.DataFrame(
        {
            "ANO": [2024, 2025, 2026, 2024, 2025, 2026],
            "MES": [1, 1, 1, 2, 2, 2],
            "VALOR": [80, 100, 110, 50, 70, 60],
        }
    )
    profile = prepare_monthly_profile(history, 2026, (1, 2))
    assert profile["ATUAL"].tolist() == [110, 60]
    assert profile["MIN_5A"].tolist() == [80, 50]
    assert profile["MAX_5A"].tolist() == [100, 70]
    assert profile["ANTERIOR"].tolist() == [100, 70]
    assert profile["VAR_1A"].round(4).tolist() == [0.1, -0.1429]
    assert profile["MEDIA_5A"].tolist() == [90, 60]

    reference = pd.read_csv(
        ROOT / "data" / "reference" / "section301_exemptions_sh6.csv",
        sep=";",
        dtype={"CO_SH6": str},
        keep_default_na=False,
    )
    assert len(reference) == 1_229
    assert reference["CO_SH6"].nunique() == 1_229
    assert reference["CO_SH6"].str.len().eq(6).all()
    assert not reference["CO_SH6"].str.startswith(("98", "99")).any()

    tariff = pd.read_csv(ROOT / "data" / "reference" / "us_effective_tariff_brazil.csv", sep=";")
    tariff["DATA"] = pd.to_datetime(tariff["DATA"])
    assert len(tariff) == 89
    assert tariff["DATA"].is_monotonic_increasing and tariff["DATA"].is_unique
    assert tariff["DATA"].iloc[0] == pd.Timestamp("2019-01-01")
    assert tariff["DATA"].iloc[-1] == pd.Timestamp("2026-05-01")
    calculated_tariff = (
        tariff["DIREITOS_ADUANEIROS_USD"] / tariff["IMPORTACOES_CONSUMO_USD"] * 100
    )
    assert calculated_tariff.sub(tariff["TARIFA_EFETIVA_PCT"]).abs().max() < 1e-8
    assert round(float(tariff["TARIFA_EFETIVA_PCT"].iloc[-1]), 6) == 10.639953

    exports = pd.DataFrame(
        {
            "CO_NCM": ["02011000", "28041000", "01010100"],
            "NO_NCM_POR": ["Carne bovina", "Hidrogênio", "Produto sem correspondência"],
            "CO_SH6": ["020110", "280410", "010101"],
            "NO_SH6_POR": ["Carne bovina", "Hidrogênio", "Outro produto"],
            "VL_FOB": [100.0, 80.0, 20.0],
            "KG_LIQUIDO": [10.0, 8.0, 2.0],
        }
    )

    class FakeResult:
        def df(self):
            return exports.copy()

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args, **_kwargs):
            return FakeResult()

    original_connect = queries_module._connect
    queries_module._connect = lambda _database: FakeConnection()
    try:
        exposure = section301_exposure(
            Path("fake.duckdb"),
            FilterState(year=2026, months=(1,)),
            ROOT / "data" / "reference" / "section301_exemptions_sh6.csv",
        )
    finally:
        queries_module._connect = original_connect
    statuses = dict(zip(exposure["CO_SH6"], exposure["SITUACAO_301"], strict=True))
    assert statuses["020110"] == "Correspondência com isenção no SH6"
    assert statuses["280410"] == "Correspondência condicionada no SH6"
    assert statuses["010101"] == "Sem correspondência - potencialmente afetado"
    print("Smoke tests concluídos com sucesso.")


if __name__ == "__main__":
    main()
