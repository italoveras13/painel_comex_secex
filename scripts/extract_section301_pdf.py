"""Extrai o Anexo II do aviso final da Seção 301 e consolida por SH6.

Uso:
    python scripts/extract_section301_pdf.py "caminho/arquivo.pdf"

O cruzamento SH6 é indicativo: uma linha HTSUS de 8/10 dígitos e uma NCM de
8 dígitos compartilham os seis primeiros dígitos, mas não são equivalentes em
seus desdobramentos nacionais.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd
import pdfplumber


ANNEX_FIRST_PAGE = 42
ANNEX_LAST_PAGE = 138
SOURCE_NAME = "Brazil 301 Final Action FRN 7-15-2026 final.pdf"


def _clean(value: object) -> str:
    return " ".join(str(value or "").replace("\n", " ").split())


def extract_annex(pdf_path: Path) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    with pdfplumber.open(pdf_path) as pdf:
        if len(pdf.pages) < ANNEX_LAST_PAGE:
            raise ValueError(
                f"O PDF possui {len(pdf.pages)} páginas; eram esperadas pelo menos {ANNEX_LAST_PAGE}."
            )
        for page_number in range(ANNEX_FIRST_PAGE, ANNEX_LAST_PAGE + 1):
            tables = pdf.pages[page_number - 1].extract_tables()
            if not tables:
                raise ValueError(f"Nenhuma tabela detectada na página {page_number}.")
            for table in tables:
                for row in table[1:]:
                    code = _clean(row[0])
                    description = _clean(row[1])
                    scope = _clean(row[2])
                    digits = re.sub(r"\D", "", code)
                    if digits and len(digits) in {8, 10}:
                        records.append(
                            {
                                "PAGINA_PDF": page_number,
                                "HTSUS": code,
                                "HTSUS_DIGITOS": digits,
                                "CO_SH6": digits[:6],
                                "DESCRICAO_EN": description,
                                "LIMITACAO_ESCOPO": scope,
                                "FONTE": SOURCE_NAME,
                            }
                        )
                    elif not code and description and records:
                        # Algumas descrições continuam no topo da página seguinte.
                        records[-1]["DESCRICAO_EN"] = (
                            f"{records[-1]['DESCRICAO_EN']} {description}"
                        ).strip()

    frame = pd.DataFrame(records)
    if frame.empty:
        raise ValueError("Nenhuma linha HTSUS foi extraída do Anexo II.")
    if frame["HTSUS_DIGITOS"].duplicated().any():
        duplicates = frame.loc[frame["HTSUS_DIGITOS"].duplicated(False), "HTSUS"].tolist()[:10]
        raise ValueError(f"Códigos HTSUS duplicados após a extração: {duplicates}")
    return frame


def aggregate_sh6(rows: pd.DataFrame) -> pd.DataFrame:
    products = rows.loc[pd.to_numeric(rows["CO_SH6"].str[:2]) <= 97].copy()

    def join_unique(series: pd.Series) -> str:
        return " | ".join(dict.fromkeys(value for value in series.astype(str) if value))

    grouped = (
        products.groupby("CO_SH6", as_index=False)
        .agg(
            QTD_LINHAS_HTSUS=("HTSUS", "size"),
            QTD_HTSUS_8=("HTSUS_DIGITOS", lambda values: sum(len(value) == 8 for value in values)),
            QTD_HTSUS_10=("HTSUS_DIGITOS", lambda values: sum(len(value) == 10 for value in values)),
            QTD_SEM_LIMITACAO=("LIMITACAO_ESCOPO", lambda values: sum(value == "" for value in values)),
            QTD_CONDICIONADAS=("LIMITACAO_ESCOPO", lambda values: sum(value != "" for value in values)),
            LIMITACOES_ESCOPO=("LIMITACAO_ESCOPO", join_unique),
            CODIGOS_HTSUS=("HTSUS", join_unique),
            DESCRICAO_HTSUS_EXEMPLO=("DESCRICAO_EN", "first"),
            PAGINA_INICIAL=("PAGINA_PDF", "min"),
            PAGINA_FINAL=("PAGINA_PDF", "max"),
        )
        .sort_values("CO_SH6")
    )
    grouped["TIPO_ESCOPO_SH6"] = "Sem limitação explícita"
    grouped.loc[grouped["QTD_SEM_LIMITACAO"].eq(0), "TIPO_ESCOPO_SH6"] = "Condicionado"
    grouped.loc[
        grouped["QTD_SEM_LIMITACAO"].gt(0) & grouped["QTD_CONDICIONADAS"].gt(0),
        "TIPO_ESCOPO_SH6",
    ] = "Misto"
    grouped["FONTE"] = SOURCE_NAME
    grouped["ANEXO"] = "Anexo II"
    grouped["DATA_VIGENCIA_GERAL"] = "2026-07-22"
    return grouped


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extrai as isenções do Anexo II por SH6")
    parser.add_argument("pdf", type=Path, help="PDF do aviso final da Seção 301")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "reference",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = extract_annex(args.pdf)
    sh6 = aggregate_sh6(rows)
    rows_path = args.output_dir / "section301_annex_ii_htsus.csv"
    sh6_path = args.output_dir / "section301_exemptions_sh6.csv"
    rows.to_csv(rows_path, index=False, sep=";", encoding="utf-8-sig")
    sh6.to_csv(sh6_path, index=False, sep=";", encoding="utf-8-sig")
    print(f"{len(rows):,} linhas HTSUS salvas em {rows_path}")
    print(f"{len(sh6):,} códigos SH6 salvos em {sh6_path}")


if __name__ == "__main__":
    main()
