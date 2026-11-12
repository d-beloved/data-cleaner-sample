"""Read and write CSV, TSV, Excel, JSON and JSON Lines."""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import BinaryIO

import pandas as pd

SUPPORTED = (".csv", ".tsv", ".txt", ".xlsx", ".xls", ".json", ".jsonl", ".ndjson")


def _suffix(name: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError(f"Unsupported file type '{suffix or name}'. Use one of: {', '.join(SUPPORTED)}")
    return suffix


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def read_table(source: str | Path | bytes | BinaryIO, name: str | None = None) -> pd.DataFrame:
    """Load a dataset. `name` gives the file type when `source` is bytes or a stream."""
    if isinstance(source, (str, Path)):
        name = name or str(source)
        raw = Path(source).read_bytes()
    elif isinstance(source, bytes):
        raw = source
    else:
        raw = source.read()
    if not name:
        raise ValueError("A file name is needed to detect the format")
    suffix = _suffix(name)
    if not raw.strip():
        raise ValueError("The file is empty")

    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(io.BytesIO(raw), dtype=object)

    text = _decode(raw)
    if suffix in {".csv", ".tsv", ".txt"}:
        sep = "\t" if suffix == ".tsv" else None  # None = sniff , ; | or tab
        return pd.read_csv(io.StringIO(text), sep=sep, engine="python", dtype=str, keep_default_na=False)
    if suffix in {".jsonl", ".ndjson"}:
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
        return pd.json_normalize(records)

    data = json.loads(text)
    if isinstance(data, dict):
        lists = [v for v in data.values() if isinstance(v, list)]
        if len(lists) == 1:  # {"data": [...]} style wrapper
            data = lists[0]
        else:
            data = [data]
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        raise ValueError("JSON must be a list of objects, or an object wrapping one list")
    return pd.json_normalize(data)


def to_records(df: pd.DataFrame) -> list[dict]:
    """JSON-safe rows: missing values become null, numpy types become plain ones."""
    return json.loads(df.to_json(orient="records", date_format="iso", force_ascii=False))


def write_table(df: pd.DataFrame, path: str | Path) -> None:
    path = Path(path)
    suffix = _suffix(path.name)
    if suffix in {".xlsx", ".xls"}:
        df.to_excel(path, index=False)
    elif suffix in {".jsonl", ".ndjson"}:
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in to_records(df)) + "\n", encoding="utf-8")
    elif suffix == ".json":
        path.write_text(json.dumps(to_records(df), ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        df.to_csv(path, index=False, sep="\t" if suffix == ".tsv" else ",", encoding="utf-8")
