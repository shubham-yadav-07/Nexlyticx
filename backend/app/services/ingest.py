"""Robust CSV reading: encoding + delimiter detection, header clean-up,
size limits and automatic date detection."""
from __future__ import annotations

import csv
import io
import re
import warnings

import pandas as pd

from .. import config

_DATE_RE = re.compile(
    r"^\s*(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|"
    r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})([ T]\d{1,2}:\d{2}(:\d{2})?)?\s*$"
)


class IngestError(ValueError):
    """Raised with a message that is safe to show to the end user."""


def _decode(raw: bytes) -> tuple[str, str]:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    raise IngestError("Could not decode the file. Please save it as UTF-8 CSV.")


def _sniff_delimiter(text: str) -> str:
    sample = text[:8192]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def _clean_columns(cols) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for i, c in enumerate(cols):
        name = re.sub(r"\s+", " ", str(c)).strip() or f"column_{i + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1
        out.append(name)
    return out


def _looks_like_dates(series: pd.Series) -> bool:
    sample = series.dropna().astype(str).head(60)
    if len(sample) < 3:
        return False
    return sample.map(lambda v: bool(_DATE_RE.match(v))).mean() >= 0.9


def _convert_dates(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if df[col].dtype == object and _looks_like_dates(df[col]):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                parsed = pd.to_datetime(df[col], errors="coerce")
            if parsed.notna().sum() >= 0.9 * df[col].notna().sum():
                df[col] = parsed
    return df


def read_csv_bytes(raw: bytes, enforce_limits: bool = True) -> pd.DataFrame:
    if not raw or not raw.strip():
        raise IngestError("The file is empty.")
    if enforce_limits and len(raw) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise IngestError(f"File is larger than the {config.MAX_UPLOAD_MB} MB limit.")

    text, enc = _decode(raw)
    sep = _sniff_delimiter(text)
    try:
        df = pd.read_csv(io.StringIO(text), sep=sep, nrows=(config.MAX_ROWS + 1) if enforce_limits else None, low_memory=False)
    except pd.errors.EmptyDataError as exc:
        raise IngestError("The file has no readable data.") from exc
    except Exception as exc:  # noqa: BLE001 - surface a friendly message
        raise IngestError("This doesn't look like a valid CSV file.") from exc

    if enforce_limits and len(df) > config.MAX_ROWS:
        raise IngestError(f"Too many rows (limit is {config.MAX_ROWS:,}). Please upload a smaller file or a sample.")

    df.columns = _clean_columns(df.columns)
    junk = [c for c in df.columns if c.lower().startswith("unnamed") and df[c].isna().all()]
    df = df.drop(columns=junk)
    df = df.dropna(how="all")

    if df.empty or df.shape[1] == 0:
        raise IngestError("The file has no usable rows or columns.")
    if enforce_limits and df.shape[1] > config.MAX_COLS:
        raise IngestError(f"Too many columns (limit is {config.MAX_COLS}).")

    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].map(lambda v: v.strip() if isinstance(v, str) else v)
        df[col] = df[col].replace("", pd.NA)
    df = df.reset_index(drop=True)
    return _convert_dates(df)
