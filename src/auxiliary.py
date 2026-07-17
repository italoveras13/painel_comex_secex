from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .utils import normalize_code_series, normalize_header, parse_business_day


class WorkbookSchemaError(ValueError):
    pass


@dataclass(frozen=True)
class AuxiliaryDimensions:
    ncm: pd.DataFrame
    country: pd.DataFrame
    unit: pd.DataFrame
    calendar_month: pd.DataFrame
    sheet_map: dict[str, str]


def _fold(text: object) -> str:
    value = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", value.strip().casefold())


def _find_sheet(
    xls: pd.ExcelFile,
    required: set[str],
    label: str,
) -> tuple[str, pd.DataFrame]:
    candidates: list[tuple[str, list[str]]] = []
    for sheet in xls.sheet_names:
        header = pd.read_excel(xls, sheet_name=sheet, nrows=0)
        normalized = [normalize_header(col) for col in header.columns]
        if required.issubset(set(normalized)):
            candidates.append((sheet, normalized))
    if not candidates:
        raise WorkbookSchemaError(
            f"Nenhuma aba de {label} contém as colunas obrigatórias: "
            f"{', '.join(sorted(required))}. Abas encontradas: {', '.join(xls.sheet_names)}"
        )
    # Se mais de uma aba servir, prefere a mais enxuta e depois a primeira no arquivo.
    chosen = min(candidates, key=lambda item: len(item[1]))[0]
    frame = pd.read_excel(xls, sheet_name=chosen, dtype=str)
    frame.columns = [normalize_header(col) for col in frame.columns]
    return chosen, frame


def _optional_code_description(
    xls: pd.ExcelFile,
    code_column: str,
    description_column: str,
    width: int,
    label: str,
) -> tuple[str | None, pd.DataFrame]:
    """Localiza uma tabela de descrição SH quando ela existir no workbook."""
    try:
        sheet, frame = _find_sheet(xls, {code_column, description_column}, label)
    except WorkbookSchemaError:
        return None, pd.DataFrame(columns=[code_column, description_column])
    frame = frame[[code_column, description_column]].copy()
    frame[code_column] = normalize_code_series(frame[code_column], width)
    frame = _assert_one_row_per_key(frame, code_column, label)
    return sheet, frame


def _assert_one_row_per_key(frame: pd.DataFrame, key: str, label: str) -> pd.DataFrame:
    frame = frame.dropna(subset=[key]).copy()
    value_cols = [col for col in frame.columns if col != key]
    conflicts = (
        frame.groupby(key, dropna=False)[value_cols]
        .nunique(dropna=True)
        .gt(1)
        .any(axis=1)
    )
    if conflicts.any():
        examples = ", ".join(conflicts[conflicts].index.astype(str)[:5])
        raise WorkbookSchemaError(
            f"A dimensão {label} possui mapeamentos conflitantes para a chave {key}. "
            f"Exemplos: {examples}. Isso poderia duplicar os totais no join."
        )
    return frame.drop_duplicates(subset=[key], keep="first")


def _macro_sector(code: object, name: object) -> str:
    code_text = str(code).strip().upper() if not pd.isna(code) else ""
    name_text = _fold(name) if not pd.isna(name) else ""
    if code_text == "A" or any(word in name_text for word in ("agricultura", "agropec", "pesca", "aquicultura")):
        return "Agropecuária"
    if code_text == "B" or "extrativ" in name_text:
        return "Indústria Extrativa"
    if code_text == "C" or "transforma" in name_text:
        return "Indústria de Transformação"
    return "Outros Produtos"


def _use_category(code: object, name: object) -> str:
    text = _fold(name) if not pd.isna(name) else ""
    if "capital" in text:
        return "Bens de Capital"
    if "intermed" in text:
        return "Bens Intermediários"
    if "consumo" in text:
        return "Bens de Consumo"
    if "combust" in text or "lubrificant" in text:
        return "Combustíveis e Lubrificantes"
    if text:
        return str(name).strip()
    return f"Categoria {str(code).strip()}" if not pd.isna(code) else "Não classificado"


def load_auxiliary_dimensions(aux_workbook: Path, calendar_workbook: Path) -> AuxiliaryDimensions:
    if not aux_workbook.exists() or aux_workbook.stat().st_size == 0:
        raise FileNotFoundError(f"Arquivo auxiliar ausente ou vazio: {aux_workbook}")
    if not calendar_workbook.exists() or calendar_workbook.stat().st_size == 0:
        raise FileNotFoundError(f"Arquivo de calendário ausente ou vazio: {calendar_workbook}")

    xls = pd.ExcelFile(aux_workbook)
    sector_sheet, sector = _find_sheet(
        xls,
        {"CO_NCM", "CO_ISIC_SECAO", "NO_ISIC_SECAO"},
        "setor/ISIC",
    )
    category_sheet, category = _find_sheet(
        xls,
        {"CO_NCM", "CO_CGCE_N1", "NO_CGCE_N1"},
        "categoria de uso/CGCE",
    )
    sh_sheet, sh = _find_sheet(
        xls,
        {"CO_NCM", "CO_SH6", "NO_SH6_POR", "CO_SH4", "CO_SH2"},
        "hierarquia SH",
    )
    country_sheet, country = _find_sheet(
        xls,
        {"CO_PAIS", "NO_PAIS", "CO_PAIS_ISOA3"},
        "país",
    )
    unit_sheet, unit = _find_sheet(xls, {"CO_UNID", "NO_UNID"}, "unidade estatística")

    sector_cols = ["CO_NCM", "CO_ISIC_SECAO", "NO_ISIC_SECAO"]
    if "NO_NCM_POR" in sector.columns:
        sector_cols.append("NO_NCM_POR")
    sector = sector[sector_cols].copy()
    category = category[["CO_NCM", "CO_CGCE_N1", "NO_CGCE_N1"]].copy()
    sh_cols = ["CO_NCM", "CO_SH6", "NO_SH6_POR", "CO_SH4", "CO_SH2"]
    for optional_column in ("NO_SH4_POR", "NO_SH2_POR"):
        if optional_column in sh.columns:
            sh_cols.append(optional_column)
    if "NO_NCM_POR" in sh.columns and "NO_NCM_POR" not in sector.columns:
        sh_cols.append("NO_NCM_POR")
    sh = sh[sh_cols].copy()

    for frame in (sector, category, sh):
        frame["CO_NCM"] = normalize_code_series(frame["CO_NCM"], 8)
    sh["CO_SH6"] = normalize_code_series(sh["CO_SH6"], 6)
    sh["CO_SH4"] = normalize_code_series(sh["CO_SH4"], 4)
    sh["CO_SH2"] = normalize_code_series(sh["CO_SH2"], 2)

    sector = _assert_one_row_per_key(sector, "CO_NCM", "setor")
    category = _assert_one_row_per_key(category, "CO_NCM", "categoria")
    sh = _assert_one_row_per_key(sh, "CO_NCM", "SH")
    ncm = sector.merge(category, on="CO_NCM", how="outer", validate="one_to_one")
    ncm = ncm.merge(sh, on="CO_NCM", how="outer", validate="one_to_one", suffixes=("", "_SH"))
    if "NO_NCM_POR_SH" in ncm.columns:
        if "NO_NCM_POR" in ncm.columns:
            ncm["NO_NCM_POR"] = ncm["NO_NCM_POR"].fillna(ncm["NO_NCM_POR_SH"])
            ncm = ncm.drop(columns="NO_NCM_POR_SH")
        else:
            ncm = ncm.rename(columns={"NO_NCM_POR_SH": "NO_NCM_POR"})
    if "NO_NCM_POR" not in ncm.columns:
        ncm["NO_NCM_POR"] = pd.NA

    # O arquivo oficial normalmente traz as descrições de SH2 e SH4 em abas
    # próprias. A descoberta é feita pelas colunas para tolerar nomes de abas
    # diferentes entre versões do TABELAS_AUXILIARES.
    sh2_sheet, sh2_labels = _optional_code_description(
        xls, "CO_SH2", "NO_SH2_POR", 2, "descrição SH2"
    )
    sh4_sheet, sh4_labels = _optional_code_description(
        xls, "CO_SH4", "NO_SH4_POR", 4, "descrição SH4"
    )
    for code_column, description_column, labels in (
        ("CO_SH2", "NO_SH2_POR", sh2_labels),
        ("CO_SH4", "NO_SH4_POR", sh4_labels),
    ):
        if description_column in ncm.columns:
            if not labels.empty:
                lookup = labels.rename(columns={description_column: f"{description_column}_AUX"})
                ncm = ncm.merge(lookup, on=code_column, how="left", validate="many_to_one")
                ncm[description_column] = ncm[description_column].fillna(
                    ncm[f"{description_column}_AUX"]
                )
                ncm = ncm.drop(columns=f"{description_column}_AUX")
        elif not labels.empty:
            ncm = ncm.merge(labels, on=code_column, how="left", validate="many_to_one")
        else:
            ncm[description_column] = pd.NA
        ncm[description_column] = ncm[description_column].astype("string")
    ncm["SETOR"] = [
        _macro_sector(code, name)
        for code, name in zip(ncm["CO_ISIC_SECAO"], ncm["NO_ISIC_SECAO"], strict=False)
    ]
    ncm["CATEGORIA_USO"] = [
        _use_category(code, name)
        for code, name in zip(ncm["CO_CGCE_N1"], ncm["NO_CGCE_N1"], strict=False)
    ]

    country = country[["CO_PAIS", "NO_PAIS", "CO_PAIS_ISOA3"]].copy()
    country["CO_PAIS"] = normalize_code_series(country["CO_PAIS"], 3)
    country["PAIS"] = country["NO_PAIS"].fillna("País não identificado")
    country = _assert_one_row_per_key(country, "CO_PAIS", "país")

    unit = unit[["CO_UNID", "NO_UNID"]].copy()
    unit["CO_UNID"] = normalize_code_series(unit["CO_UNID"], 2)
    unit["UNIDADE"] = unit["NO_UNID"].fillna("Unidade não identificada")
    unit = _assert_one_row_per_key(unit, "CO_UNID", "unidade")

    calendar_xls = pd.ExcelFile(calendar_workbook)
    calendar_sheet, calendar = _find_sheet(
        calendar_xls,
        {"CO_ANO", "CO_MES", "CO_DIA", "DIA_UTIL"},
        "calendário",
    )
    calendar = calendar[["CO_ANO", "CO_MES", "CO_DIA", "DIA_UTIL"]].copy()
    for col in ("CO_ANO", "CO_MES", "CO_DIA"):
        calendar[col] = pd.to_numeric(calendar[col], errors="coerce").astype("Int64")
    calendar["DIA_UTIL_NUM"] = calendar["DIA_UTIL"].map(parse_business_day).astype("Int64")
    if calendar["DIA_UTIL_NUM"].isna().all():
        raise WorkbookSchemaError("Não foi possível interpretar nenhum valor de DIA_UTIL.")
    calendar = calendar.dropna(subset=["CO_ANO", "CO_MES", "CO_DIA"])
    calendar = calendar.drop_duplicates(["CO_ANO", "CO_MES", "CO_DIA"])
    calendar_month = (
        calendar.groupby(["CO_ANO", "CO_MES"], as_index=False)["DIA_UTIL_NUM"]
        .sum(min_count=1)
        .rename(columns={"CO_ANO": "ANO", "CO_MES": "MES", "DIA_UTIL_NUM": "DIAS_UTEIS"})
    )

    sheet_map = {
        "setor": sector_sheet,
        "categoria": category_sheet,
        "sh": sh_sheet,
        "sh2_descricao": sh2_sheet or "não localizada",
        "sh4_descricao": sh4_sheet or "não localizada",
        "pais": country_sheet,
        "unidade": unit_sheet,
        "calendario": calendar_sheet,
    }
    xls.close()
    calendar_xls.close()
    return AuxiliaryDimensions(
        ncm=ncm,
        country=country,
        unit=unit,
        calendar_month=calendar_month,
        sheet_map=sheet_map,
    )
