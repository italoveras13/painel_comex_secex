from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import pandas as pd


MONTH_NAMES = {
    1: "jan",
    2: "fev",
    3: "mar",
    4: "abr",
    5: "mai",
    6: "jun",
    7: "jul",
    8: "ago",
    9: "set",
    10: "out",
    11: "nov",
    12: "dez",
}


def normalize_header(value: Any) -> str:
    """Normaliza cabeçalhos sem remover os sublinhados usados pela SECEX."""
    return re.sub(r"\s+", "_", str(value).strip().upper())


def normalize_code_value(value: Any, width: int) -> str | None:
    """Converte códigos lidos por Excel/CSV em texto com zeros à esquerda."""
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return None
    # Excel costuma transformar identificadores inteiros em "123.0".
    if re.fullmatch(r"[+-]?\d+\.0+", text):
        text = text.split(".", 1)[0]
    text = re.sub(r"\D", "", text)
    return text.zfill(width) if text else None


def normalize_code_series(series: pd.Series, width: int) -> pd.Series:
    return series.map(lambda value: normalize_code_value(value, width)).astype("string")


def parse_business_day(value: Any) -> int | None:
    """Interpreta DIA_UTIL nos formatos 0/1, booleano, sim/não ou útil/não útil."""
    if value is None or pd.isna(value):
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(float(value) > 0)
    text = str(value).strip().casefold()
    positive = {"1", "sim", "s", "true", "verdadeiro", "util", "útil"}
    negative = {"0", "nao", "não", "n", "false", "falso", "inutil", "não útil"}
    if text in positive:
        return 1
    if text in negative:
        return 0
    return None


def detect_text_encoding(path: Path, sample_size: int = 1_000_000) -> str:
    """Escolhe uma codificação aceita por DuckDB para os CSVs."""
    sample = path.read_bytes()[:sample_size]
    for encoding in ("utf-8",):
        try:
            sample.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            pass
    # cp1252 é um subconjunto prático para os arquivos do Comex Stat.
    try:
        sample.decode("cp1252")
        return "windows-1252"
    except UnicodeDecodeError:
        return "latin-1"


def fingerprint(path: Path) -> str:
    """Fingerprint barato: caminho resolvido, tamanho e mtime em nanossegundos."""
    stat = path.stat()
    raw = f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode()
    return hashlib.sha256(raw).hexdigest()


def sql_literal(value: str | Path) -> str:
    """Escapa uma string para uso como literal SQL (não para identificadores)."""
    return "'" + str(value).replace("'", "''") + "'"


def format_compact(value: float | int | None, prefix: str = "") -> str:
    if value is None or pd.isna(value):
        return "—"
    number = float(value)
    for divisor, suffix in ((1e12, " tri"), (1e9, " bi"), (1e6, " mi"), (1e3, " mil")):
        if abs(number) >= divisor:
            return f"{prefix}{number / divisor:,.2f}{suffix}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{prefix}{number:,.0f}".replace(",", ".")
