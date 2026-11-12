"""The cleaning pipeline: one function, `clean(df, config)`, returning
the cleaned frame plus a report of everything that changed.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, fields
from typing import Any

import pandas as pd

from . import text as T

DEFAULT_NULL_TOKENS = ("", "n/a", "na", "null", "none", "nan", "nil", "-", "--", "?", "undefined")
_WS = re.compile(r"\s+")
_NUM_NOISE = re.compile(r"[,\s$€£₦%]")
_LEADING_ZERO = re.compile(r"^[+-]?0\d")
_DATE_NAME = re.compile(r"(?:^|_)(?:date|time|timestamp|dob|at|on)(?:$|_)")
_CLEAN_SUFFIX = "_clean"
_TOKENS_SUFFIX = "_tokens"


@dataclass
class CleanConfig:
    """Every knob the pipeline has. All fields are optional."""

    # Columns
    drop_columns: list[str] = field(default_factory=list)
    id_columns: list[str] | None = None        # None = auto-detect
    text_columns: list[str] | None = None      # None = auto-detect
    date_columns: list[str] = field(default_factory=list)
    keep_as_text: list[str] = field(default_factory=list)   # never coerce to numbers
    numeric_columns: list[str] = field(default_factory=list)  # always coerce to numbers
    title_case_columns: list[str] = field(default_factory=list)  # e.g. person names
    # Missing data
    null_tokens: list[str] = field(default_factory=lambda: list(DEFAULT_NULL_TOKENS))
    required_columns: list[str] = field(default_factory=list)
    max_missing_ratio: float = 0.7             # drop rows emptier than this
    numeric_fill: str = "none"                 # none | median | mean | zero
    fill_values: dict[str, Any] = field(default_factory=dict)
    # Types and formats
    infer_numeric: bool = True
    numeric_threshold: float = 0.9             # share of values that must parse
    dayfirst: bool = False                     # 03/04/2026 = 3 April when True
    infer_dates: bool = True                   # detect date columns by name + content
    # Categories
    standardize_categories: bool = True
    category_max_unique: int = 30
    category_maps: dict[str, dict[str, str]] = field(default_factory=dict)
    # Text
    keep_raw_text: bool = True                 # write <col>_clean next to the original
    lowercase_text: bool = True
    strip_emoji: bool = True
    strip_handles: bool = True
    mask_pii: bool = False
    add_tokens: bool = False                   # add <col>_tokens (space-joined)
    remove_stopwords: bool = False             # only affects <col>_tokens
    min_text_length: int = 0                   # drop rows whose cleaned text is shorter
    # Duplicates
    drop_duplicates: bool = True
    dedupe_subset: list[str] | None = None     # None = every non-id column

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "CleanConfig":
        data = data or {}
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            raise ValueError(f"Unknown config keys: {', '.join(unknown)}")
        cfg = cls(**data)
        if cfg.numeric_fill not in {"none", "median", "mean", "zero"}:
            raise ValueError("numeric_fill must be one of: none, median, mean, zero")
        return cfg


def snake_case(name: Any) -> str:
    out = re.sub(r"[^0-9a-zA-Z]+", "_", str(name).strip()).strip("_").lower()
    return out or "column"


def _unique_names(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for n in names:
        if n in seen:
            seen[n] += 1
            out.append(f"{n}_{seen[n]}")
        else:
            seen[n] = 1
            out.append(n)
    return out


def _is_stringy(s: pd.Series) -> bool:
    vals = s.dropna()
    return len(vals) > 0 and all(isinstance(v, str) for v in vals)


def _obj(values, index) -> pd.Series:
    return pd.Series(list(values), index=index, dtype=object)


def clean(df: pd.DataFrame, config: CleanConfig | dict | None = None) -> tuple[pd.DataFrame, dict]:
    cfg = config if isinstance(config, CleanConfig) else CleanConfig.from_dict(config)
    report: dict[str, Any] = {"rows_in": int(len(df)), "columns_in": int(df.shape[1])}
    df = df.copy()

    # 1. Column names -> snake_case, unique.
    new_cols = _unique_names([snake_case(c) for c in df.columns])
    report["columns_renamed"] = {str(o): n for o, n in zip(df.columns, new_cols) if str(o) != n}
    df.columns = new_cols
    names = lambda cols: [snake_case(c) for c in (cols or [])]  # noqa: E731

    def existing(cols, label):
        cols = names(cols)
        missing = [c for c in cols if c not in df.columns]
        if missing:
            report.setdefault("warnings", []).append(f"{label}: column(s) not found: {', '.join(missing)}")
        return [c for c in cols if c in df.columns]

    # 2. Trim strings, turn null-like tokens into real missing values.
    null_tokens = {t.casefold() for t in cfg.null_tokens}
    counter = {"nulls": 0}

    def norm_cell(v):
        if v is None:
            return None
        if isinstance(v, (list, dict)):
            return json.dumps(v, sort_keys=True, ensure_ascii=False)
        if isinstance(v, str):
            s = _WS.sub(" ", v).strip()
            if s.casefold() in null_tokens:
                counter["nulls"] += 1
                return None
            return s
        try:
            if pd.isna(v):
                return None
        except (TypeError, ValueError):
            pass
        return v

    for c in df.columns:
        df[c] = _obj((norm_cell(v) for v in df[c]), df.index)
    report["null_tokens_replaced"] = counter["nulls"]

    # 3. Drop unwanted and fully empty columns / rows.
    drop = existing(cfg.drop_columns, "drop_columns")
    df = df.drop(columns=drop)
    empty_cols = [c for c in df.columns if df[c].isna().all()]
    df = df.drop(columns=empty_cols)
    before = len(df)
    df = df.dropna(how="all")
    report["columns_dropped"] = drop + empty_cols
    report["empty_rows_dropped"] = before - len(df)

    date_cols = existing(cfg.date_columns, "date_columns")
    keep_text = set(existing(cfg.keep_as_text, "keep_as_text"))
    explicit_text = existing(cfg.text_columns, "text_columns") if cfg.text_columns is not None else None
    if cfg.infer_dates:
        for c in df.columns:
            if c in date_cols or c in keep_text or c in (explicit_text or []) or not _DATE_NAME.search(c) or not _is_stringy(df[c]):
                continue
            vals = df[c].dropna().astype("string")
            if vals.str.fullmatch(r"[\d.,\s]+").all():
                continue  # plain numbers are not dates
            if pd.to_datetime(vals, errors="coerce", format="mixed", dayfirst=cfg.dayfirst).notna().mean() >= 0.6:
                date_cols.append(c)

    # 4. Numbers stored as text ("1,200", "$5", " 4 ") -> real numbers.
    report["numeric_columns"] = {}
    for c in df.columns:  # columns that already hold only numbers get a numeric dtype back
        vals = df[c].dropna()
        if len(vals) and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
            col = pd.to_numeric(df[c])
            df[c] = col.astype("Int64") if (col.dropna() % 1 == 0).all() else col
    if cfg.infer_numeric or cfg.numeric_columns:
        forced = set(existing(cfg.numeric_columns, "numeric_columns"))
        skip = (keep_text | set(date_cols) | set(explicit_text or [])) - forced
        for c in df.columns:
            if c in skip or not _is_stringy(df[c]) or (c not in forced and not cfg.infer_numeric):
                continue
            vals = df[c].dropna()
            if c not in forced and any(_LEADING_ZERO.match(v) for v in vals):
                continue  # zip codes, phone numbers, padded IDs
            parsed = pd.to_numeric(vals.map(lambda v: _NUM_NOISE.sub("", v)), errors="coerce")
            if c not in forced and parsed.notna().mean() < cfg.numeric_threshold:
                continue
            bad = vals[parsed.isna()]
            col = parsed.reindex(df.index)
            if (parsed.dropna() % 1 == 0).all():
                col = col.astype("Int64")
            df[c] = col
            report["numeric_columns"][c] = {
                "invalid_set_to_missing": int(len(bad)),
                "invalid_examples": sorted(set(bad))[:5],
            }

    # 5. Dates -> ISO 8601.
    report["date_columns"] = {}
    for c in date_cols:
        had = df[c].notna()
        parsed = pd.to_datetime(df[c].astype("string"), errors="coerce", format="mixed", dayfirst=cfg.dayfirst)
        bad = df.loc[had & parsed.isna(), c]
        fmt = "%Y-%m-%d" if (parsed.dropna().dt.normalize() == parsed.dropna()).all() else "%Y-%m-%dT%H:%M:%S"
        df[c] = _obj((None if pd.isna(v) else v.strftime(fmt) for v in parsed), df.index)
        report["date_columns"][c] = {
            "unparseable_set_to_missing": int(len(bad)),
            "unparseable_examples": sorted({str(v) for v in bad})[:5],
        }

    # 6. Work out which columns are IDs and which are free text.
    if cfg.id_columns is not None:
        id_cols = existing(cfg.id_columns, "id_columns")
    else:
        id_cols = [
            c for c in df.columns
            if (c in {"id", "uuid", "index"} or c.endswith("_id"))
            and df[c].notna().any() and df[c].dropna().is_unique
        ]
    if explicit_text is not None:
        text_cols = explicit_text
    else:
        text_cols = []
        for c in df.columns:
            if c in id_cols or c in date_cols or c in keep_text or not _is_stringy(df[c]):
                continue
            vals = df[c].dropna()
            if vals.map(len).mean() >= 25 and vals.map(lambda v: len(v.split())).mean() >= 4:
                text_cols.append(c)
    report["id_columns"] = id_cols
    report["text_columns"] = text_cols

    # 7. Category labels: apply explicit maps, then merge case/spacing variants.
    report["categories_standardized"] = {}
    maps = {snake_case(k): v for k, v in cfg.category_maps.items()}
    title_cols = set(existing(cfg.title_case_columns, "title_case_columns"))

    def label_rank(label: str) -> int:
        # Prefer "Electronics" over "ELECTRONICS" over "electronics".
        return 2 if label.islower() else 1 if label.isupper() and len(label) > 4 else 0

    for c in df.columns:
        if c in text_cols or c in id_cols or c in date_cols or not _is_stringy(df[c]):
            continue
        explicit = {k.casefold(): v for k, v in maps.get(c, {}).items()}
        new = _obj((explicit.get(v.casefold(), v) if isinstance(v, str) else None for v in df[c]), df.index)
        if c in title_cols:
            new = _obj((v.title() if isinstance(v, str) else None for v in new), df.index)
        vals = new.dropna()
        if cfg.standardize_categories and vals.nunique() <= cfg.category_max_unique and vals.nunique() < 0.5 * len(vals):
            counts = vals.value_counts()
            targets = set(explicit.values())
            ordered = sorted(counts.index, key=lambda v: (v not in targets, label_rank(v), -counts[v], v))
            canonical: dict[str, str] = {}
            for variant in ordered:
                canonical.setdefault(variant.casefold(), variant)
            new = _obj((canonical[v.casefold()] if isinstance(v, str) else None for v in new), df.index)
        changed = int((new.fillna("\0") != df[c].fillna("\0")).sum())
        df[c] = new
        if changed:
            report["categories_standardized"][c] = {"values_changed": changed, "labels": sorted(new.dropna().unique())}

    # 8. Text cleaning.
    for c in text_cols:
        cleaned = _obj(
            (
                None if not isinstance(v, str) else T.clean_text(
                    v, lowercase=cfg.lowercase_text, strip_emoji=cfg.strip_emoji,
                    strip_handles=cfg.strip_handles, mask_pii=cfg.mask_pii,
                ) or None
                for v in df[c]
            ),
            df.index,
        )
        target = c + _CLEAN_SUFFIX if cfg.keep_raw_text else c
        df[target] = cleaned
        if cfg.add_tokens:
            df[c + _TOKENS_SUFFIX] = _obj(
                (None if v is None else " ".join(T.tokenize(v, remove_stopwords=cfg.remove_stopwords)) for v in cleaned),
                df.index,
            )
    derived = {c + s for c in text_cols for s in (_CLEAN_SUFFIX, _TOKENS_SUFFIX)} & set(df.columns)
    base_cols = [c for c in df.columns if c not in derived]

    # 9. Missing data.
    dropped: dict[str, int] = {}
    required = existing(cfg.required_columns, "required_columns")
    if required:
        mask = df[required].isna().any(axis=1)
        dropped["missing_required"] = int(mask.sum())
        df = df[~mask]
    if len(df) and cfg.max_missing_ratio < 1:
        mask = df[base_cols].isna().mean(axis=1) > cfg.max_missing_ratio
        dropped["mostly_empty"] = int(mask.sum())
        df = df[~mask]
    if cfg.min_text_length > 0 and text_cols:
        clean_cols = [c + _CLEAN_SUFFIX if cfg.keep_raw_text else c for c in text_cols]
        lengths = pd.DataFrame({c: df[c].map(lambda v: len(v) if isinstance(v, str) else 0) for c in clean_cols})
        mask = (lengths < cfg.min_text_length).all(axis=1)
        dropped["text_too_short"] = int(mask.sum())
        df = df[~mask]

    filled: dict[str, int] = {}
    if cfg.numeric_fill != "none":
        for c in base_cols:
            if c in id_cols or not pd.api.types.is_numeric_dtype(df[c]) or not df[c].isna().any() or df[c].isna().all():
                continue
            value = {"median": df[c].median(), "mean": df[c].mean(), "zero": 0}[cfg.numeric_fill]
            if pd.api.types.is_integer_dtype(df[c]) and float(value) != int(value):
                df[c] = df[c].astype("Float64")
            filled[c] = int(df[c].isna().sum())
            df[c] = df[c].fillna(value)
    for c, value in {snake_case(k): v for k, v in cfg.fill_values.items()}.items():
        if c in df.columns and df[c].isna().any():
            filled[c] = filled.get(c, 0) + int(df[c].isna().sum())
            df[c] = df[c].where(df[c].notna(), value)
    report["values_filled"] = filled

    # 10. Duplicates (case, punctuation and whitespace insensitive on text).
    report["duplicates_removed"] = 0
    if cfg.drop_duplicates and len(df):
        subset = existing(cfg.dedupe_subset, "dedupe_subset") if cfg.dedupe_subset else [
            c for c in base_cols if c not in id_cols
        ]
        if subset:
            # Compare free text on its cleaned form so markup and emoji do not hide duplicates.
            source = {c: c + _CLEAN_SUFFIX if c in text_cols and cfg.keep_raw_text else c for c in subset}
            keys = pd.DataFrame({
                c: _obj(
                    ("\0" if pd.isna(v) else T.dedupe_key(v) if isinstance(v, str) else str(v) for v in df[source[c]]),
                    df.index,
                )
                for c in subset
            })
            dup = keys.duplicated(keep="first")
            report["duplicates_removed"] = int(dup.sum())
            df = df[~dup]

    df = df.reset_index(drop=True)
    report["rows_dropped"] = dropped
    report["rows_out"] = int(len(df))
    report["columns_out"] = list(df.columns)
    report["missing_after"] = {c: int(n) for c, n in df.isna().sum().items() if n}
    return df, report
