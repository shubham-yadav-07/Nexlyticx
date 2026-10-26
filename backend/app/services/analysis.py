"""Deterministic statistical engine.

Everything the API returns is computed here with pandas / NumPy / SciPy on
the uploaded data. There is no LLM in this file: results are reproducible
and every number can be traced back to a formula.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
from scipy import stats

from ..core.utils import rnd

ID_NAME_RE = re.compile(r"(^id$|_id$|^id_|^index$|^unnamed|^row ?(no|num|number)?$)", re.I)
TARGET_NAMES = ("outcome", "target", "label", "class", "churn", "survived", "diagnosis", "default",
                "y", "price", "revenue", "sales", "salary", "income", "score", "rating", "status")
SUM_HINTS = ("revenue", "sales", "amount", "total", "orders", "quantity", "qty", "spend", "cost", "profit", "count")

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# --------------------------------------------------------------------------
# Column typing
# --------------------------------------------------------------------------
def kind_of(s: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(s):
        return "categorical"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime"
    if pd.api.types.is_numeric_dtype(s):
        return "numeric"
    n = int(s.notna().sum())
    u = int(s.nunique())
    if n > 0 and u / n > 0.9 and u > 50:
        return "text"
    return "categorical"


def is_binary(s: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s) and s.nunique(dropna=True) == 2


def is_id_like(name: str, s: pd.Series) -> bool:
    if not pd.api.types.is_numeric_dtype(s):
        return False
    s = s.dropna()
    if len(s) < 5 or not np.allclose(s, np.round(s)):
        return False
    if bool(ID_NAME_RE.search(name)) and s.nunique() == len(s):
        return True
    return s.nunique() == len(s) and (s.is_monotonic_increasing or s.is_monotonic_decreasing) and len(s) > 30


def numeric_cols(df: pd.DataFrame, include_binary: bool = True) -> list[str]:
    out = []
    for c in df.columns:
        s = df[c]
        if kind_of(s) != "numeric" or is_id_like(c, s) or s.nunique(dropna=True) <= 1:
            continue
        if not include_binary and is_binary(s):
            continue
        out.append(c)
    return out


def datetime_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if kind_of(df[c]) == "datetime"]


def categorical_cols(df: pd.DataFrame, max_unique: int = 60) -> list[str]:
    return [c for c in df.columns if kind_of(df[c]) == "categorical" and 1 < df[c].nunique() <= max_unique]


def guess_target(df: pd.DataFrame) -> str | None:
    norm = {re.sub(r"[^a-z0-9]", "", c.lower()): c for c in df.columns}
    for name in TARGET_NAMES:
        if name in norm and kind_of(df[norm[name]]) in ("numeric", "categorical") and df[norm[name]].nunique() > 1:
            return norm[name]
    nums = numeric_cols(df)
    if not nums:
        cats = categorical_cols(df, 12)
        return cats[0] if cats else None
    last = df.columns[-1]
    if last in nums and is_binary(df[last]):
        return last
    for c in nums:
        if is_binary(df[c]):
            return c
    return nums[-1]


def target_options(df: pd.DataFrame) -> list[str]:
    nums = numeric_cols(df)
    return nums + [c for c in categorical_cols(df, 25) if c not in nums]


def default_agg(col: str) -> str:
    return "sum" if any(h in col.lower() for h in SUM_HINTS) else "mean"


# --------------------------------------------------------------------------
# Profiling
# --------------------------------------------------------------------------
def column_profile(df: pd.DataFrame, c: str) -> dict:
    s = df[c]
    k = kind_of(s)
    n = len(s)
    d = {"name": c, "kind": k, "binary": is_binary(s), "dtype": str(s.dtype),
         "missing": int(s.isna().sum()), "missing_pct": rnd(100 * s.isna().sum() / n if n else 0, 2),
         "unique": int(s.nunique(dropna=True))}
    if k == "numeric":
        d.update(mean=rnd(s.mean()), std=rnd(s.std()), min=rnd(s.min()), max=rnd(s.max()), median=rnd(s.median()))
    elif k == "datetime":
        d.update(min=str(s.min())[:10] if s.notna().any() else None, max=str(s.max())[:10] if s.notna().any() else None)
    else:
        vc = s.value_counts(dropna=True)
        if len(vc):
            d.update(top=str(vc.index[0]), top_pct=rnd(100 * vc.iloc[0] / max(1, s.notna().sum()), 1))
    return d


def profile(df: pd.DataFrame) -> dict:
    n, m = df.shape
    cols = [column_profile(df, c) for c in df.columns]
    kinds = [c["kind"] for c in cols]
    missing_cells = int(df.isna().sum().sum())
    return {
        "rows": int(n), "columns": int(m),
        "numeric": kinds.count("numeric"), "categorical": kinds.count("categorical") + kinds.count("text"),
        "datetime": kinds.count("datetime"),
        "missing_cells": missing_cells,
        "missing_pct": rnd(100 * missing_cells / (n * m) if n * m else 0, 2),
        "duplicate_rows": int(df.duplicated().sum()),
        "memory_kb": int(df.memory_usage(deep=True).sum() / 1024),
        "column_profiles": cols,
    }


# --------------------------------------------------------------------------
# Data quality ("trust score")
# --------------------------------------------------------------------------
def suspicious_zero_cols(df: pd.DataFrame) -> dict[str, dict]:
    """Columns where 0 is probably a placeholder for 'unknown' (e.g. a blood
    pressure of 0). Heuristic: a continuous-looking, non-negative column where
    zero sits far below the smallest real value."""
    out: dict[str, dict] = {}
    for c in numeric_cols(df, include_binary=False):
        s = df[c].dropna()
        if s.nunique() < 15:
            continue
        zeros = int((s == 0).sum())
        if zeros == 0 or zeros / len(s) > 0.8 or (s < 0).any():
            continue
        nz = s[s != 0]
        if nz.empty:
            continue
        integer = bool(np.allclose(nz, np.round(nz)))
        mn, med = float(nz.min()), float(nz.median())
        if (integer and mn <= 2) or med <= 0 or mn / med < 0.08:
            continue
        out[c] = {"count": zeros, "pct": rnd(100 * zeros / len(s), 2), "min_nonzero": rnd(mn)}
    return out


def outlier_info(s: pd.Series) -> dict | None:
    s = s.dropna()
    if len(s) < 8 or s.nunique() <= 2:
        return None
    q1, q3 = s.quantile([0.25, 0.75])
    iqr = q3 - q1
    if iqr == 0:
        return None
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    cnt = int(((s < lo) | (s > hi)).sum())
    return {"count": cnt, "pct": rnd(100 * cnt / len(s), 2), "low": rnd(lo), "high": rnd(hi)}


def _mixed_type_cols(df: pd.DataFrame) -> list[str]:
    out = []
    for c in df.select_dtypes(include="object").columns:
        s = df[c].dropna().astype(str)
        if len(s) < 10:
            continue
        share = pd.to_numeric(s.str.replace(",", "", regex=False), errors="coerce").notna().mean()
        if 0.05 < share < 0.95:
            out.append(c)
    return out


def grade_for(score: float, has_high_issue: bool = False) -> str:
    """A dataset with a high-severity issue is never graded better than
    'Needs attention', however good the average looks."""
    if has_high_issue:
        return "Needs attention"
    if score >= 95:
        return "Excellent"
    if score >= 85:
        return "Good"
    if score >= 70:
        return "Fair"
    return "Needs attention"


def quality(df: pd.DataFrame) -> dict:
    n, m = df.shape
    cells = max(1, n * m)
    miss = df.isna().sum()
    missing_cells = int(miss.sum())
    dup_rows = int(df.duplicated().sum())
    zeros = suspicious_zero_cols(df)
    invalid_cells = sum(v["count"] for v in zeros.values())
    max_zero_share = max([v["pct"] / 100 for v in zeros.values()], default=0)

    outliers = {}
    for c in numeric_cols(df, include_binary=False):
        oi = outlier_info(df[c])
        if oi:
            outliers[c] = oi
    outlier_cells = sum(o["count"] for o in outliers.values())
    num_cells = max(1, n * max(1, len(numeric_cols(df, include_binary=False))))

    constant = [c for c in df.columns if df[c].nunique(dropna=True) <= 1]
    mixed = _mixed_type_cols(df)

    completeness = 100 * (1 - missing_cells / cells)
    uniqueness = 100 * (1 - dup_rows / max(1, n))
    validity = 100 * (1 - (0.5 * invalid_cells / cells + 0.5 * max_zero_share))
    consistency = 100 * (1 - (len(constant) + len(mixed)) / max(1, m))
    outlier_score = 100 - min(100, 3 * 100 * outlier_cells / num_cells)

    dims = [
        {"key": "completeness", "label": "Completeness", "weight": 25, "score": rnd(max(0, completeness), 1),
         "detail": f"{missing_cells:,} of {cells:,} cells are empty."},
        {"key": "validity", "label": "Validity", "weight": 30, "score": rnd(max(0, validity), 1),
         "detail": (f"{invalid_cells:,} cells hold a suspicious 0 in {len(zeros)} column(s)." if zeros
                    else "No placeholder values detected.")},
        {"key": "uniqueness", "label": "Uniqueness", "weight": 15, "score": rnd(max(0, uniqueness), 1),
         "detail": f"{dup_rows:,} duplicate row(s)."},
        {"key": "consistency", "label": "Consistency", "weight": 15, "score": rnd(max(0, consistency), 1),
         "detail": f"{len(constant)} constant and {len(mixed)} mixed-type column(s)."},
        {"key": "outliers", "label": "Outliers", "weight": 15, "score": rnd(max(0, outlier_score), 1),
         "detail": f"{outlier_cells:,} extreme values (IQR rule) across numeric columns."},
    ]
    score = round(sum(d["weight"] * d["score"] for d in dims) / 100, 1)

    issues: list[dict] = []
    for c in df.columns:
        if miss[c] == 0:
            continue
        pct = 100 * miss[c] / max(1, n)
        sev = "high" if pct >= 20 else "medium" if pct >= 5 else "low"
        k = kind_of(df[c])
        if k == "numeric":
            fix = {"type": "fill_missing", "columns": [c], "strategy": "median"}
        elif k == "datetime":
            fix = {"type": "drop_missing_rows", "columns": [c]}
        else:
            fix = {"type": "fill_missing", "columns": [c], "strategy": "mode"}
        issues.append({"severity": sev, "type": "missing", "columns": [c], "sort": pct,
                       "title": f"{c}: {rnd(pct, 1)}% missing",
                       "detail": f"{int(miss[c]):,} empty value(s). Filling or dropping them avoids biased results.",
                       "fix": fix})
    if dup_rows:
        pct = 100 * dup_rows / n
        issues.append({"severity": "high" if pct >= 5 else "medium", "type": "duplicates", "columns": [], "sort": pct,
                       "title": f"{dup_rows:,} duplicate row(s)",
                       "detail": "Exact copies of other rows inflate counts and averages.",
                       "fix": {"type": "drop_duplicates"}})
    for c, v in zeros.items():
        sev = "high" if v["pct"] >= 20 else "medium" if v["pct"] >= 5 else "low"
        issues.append({"severity": sev, "type": "suspicious_zeros", "columns": [c], "sort": v["pct"],
                       "title": f"{c}: {v['pct']}% zeros look like missing data",
                       "detail": f"{v['count']:,} zero(s), but the smallest real value is {v['min_nonzero']}. "
                                 "A zero here is probably a placeholder for 'not recorded'.",
                       "fix": {"type": "zeros_to_nan", "columns": [c]}})
    for c, o in outliers.items():
        if o["pct"] >= 1:
            issues.append({"severity": "medium" if o["pct"] >= 10 else "low", "type": "outliers", "columns": [c],
                           "sort": o["pct"], "title": f"{c}: {o['pct']}% extreme values",
                           "detail": f"{o['count']:,} value(s) outside [{o['low']}, {o['high']}]. "
                                     "Capping reduces their pull on averages.",
                           "fix": {"type": "cap_outliers", "columns": [c]}})
    for c in constant:
        issues.append({"severity": "low", "type": "constant", "columns": [c], "sort": 0,
                       "title": f"{c}: only one distinct value", "detail": "A constant column carries no information.",
                       "fix": {"type": "drop_columns", "columns": [c]}})
    for c in mixed:
        issues.append({"severity": "medium", "type": "mixed_types", "columns": [c], "sort": 0,
                       "title": f"{c}: mixes numbers and text",
                       "detail": "Review this column manually; it can break calculations.", "fix": None})
    issues.sort(key=lambda i: (SEVERITY_ORDER[i["severity"]], -i["sort"]))
    for i in issues:
        i.pop("sort", None)

    per_col = [{"column": c, "missing_pct": rnd(100 * miss[c] / max(1, n), 2),
                "zero_pct": zeros.get(c, {}).get("pct", 0), "outlier_pct": outliers.get(c, {}).get("pct", 0)}
               for c in df.columns]

    has_high = any(i["severity"] == "high" for i in issues)
    return {"score": score, "grade": grade_for(score, has_high), "dimensions": dims, "issues": issues, "per_column": per_col,
            "totals": {"missing_cells": missing_cells, "duplicate_rows": dup_rows,
                       "invalid_cells": invalid_cells, "outlier_cells": outlier_cells}}


# --------------------------------------------------------------------------
# Statistics helpers
# --------------------------------------------------------------------------
def pearson(a: pd.Series, b: pd.Series) -> dict | None:
    pair = pd.concat([a, b], axis=1).dropna()
    if len(pair) < 5 or pair.iloc[:, 0].nunique() < 2 or pair.iloc[:, 1].nunique() < 2:
        return None
    r, p = stats.pearsonr(pair.iloc[:, 0], pair.iloc[:, 1])
    return {"r": rnd(r, 3), "p": float(p), "n": int(len(pair))}


def strength(r: float) -> str:
    a = abs(r)
    if a >= 0.8:
        return "very strong"
    if a >= 0.6:
        return "strong"
    if a >= 0.4:
        return "moderate"
    if a >= 0.2:
        return "weak"
    return "negligible"


def fmt_p(p: float) -> str:
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


def correlations_with(df: pd.DataFrame, target: str, top_n: int = 8) -> dict:
    if target not in df.columns or kind_of(df[target]) != "numeric":
        return {"available": False, "reason": "Pick a numeric focus column to see correlations."}
    rows = []
    for c in numeric_cols(df):
        if c == target:
            continue
        res = pearson(df[c], df[target])
        if res:
            rows.append({"column": c, "r": res["r"], "p": rnd(res["p"], 6), "n": res["n"],
                         "significant": bool(res["p"] < 0.05), "strength": strength(res["r"])})
    if not rows:
        return {"available": False, "reason": "No other numeric columns to compare."}
    rows.sort(key=lambda r: abs(r["r"]), reverse=True)
    return {"available": True, "target": target, "results": rows[:top_n]}


def correlation_matrix(df: pd.DataFrame, max_cols: int = 18) -> dict:
    cols = sorted(numeric_cols(df), key=lambda c: -df[c].notna().sum())[:max_cols]
    if len(cols) < 2:
        return {"available": False, "reason": "Need at least two numeric columns."}
    corr = df[cols].corr()
    pairs = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            v = corr.iloc[i, j]
            if pd.notna(v):
                pairs.append({"a": cols[i], "b": cols[j], "r": rnd(v, 3)})
    pairs.sort(key=lambda p: abs(p["r"]), reverse=True)
    return {"available": True, "labels": cols, "matrix": [[rnd(v, 3) for v in row] for row in corr.values.tolist()],
            "top_pairs": pairs[:10]}


def describe_numeric(df: pd.DataFrame) -> list[dict]:
    rows = []
    for c in numeric_cols(df):
        s = df[c].dropna()
        if s.empty:
            continue
        q1, med, q3 = s.quantile([0.25, 0.5, 0.75])
        rows.append({"column": c, "count": int(s.count()), "mean": rnd(s.mean()), "std": rnd(s.std()),
                     "min": rnd(s.min()), "q1": rnd(q1), "median": rnd(med), "q3": rnd(q3), "max": rnd(s.max()),
                     "skew": rnd(s.skew(), 2) if len(s) > 2 else None})
    return rows


def histogram(s: pd.Series, bins: int = 20) -> dict:
    s = s.dropna()
    if s.empty:
        return {"type": "empty"}
    if s.nunique() <= 12:
        vc = s.value_counts().sort_index()
        return {"type": "discrete",
                "labels": [str(rnd(v, 3) if isinstance(v, float) else v) for v in vc.index],
                "counts": [int(x) for x in vc.values]}
    counts, edges = np.histogram(s, bins=max(5, min(60, bins)))
    return {"type": "continuous", "edges": [rnd(e, 4) for e in edges], "counts": [int(c) for c in counts]}


def value_counts(s: pd.Series, top: int = 15) -> dict:
    vc = s.value_counts(dropna=True)
    total = int(vc.sum())
    head = vc.head(top)
    other = int(vc.iloc[top:].sum()) if len(vc) > top else 0
    return {"labels": [str(i) for i in head.index], "counts": [int(v) for v in head.values],
            "pct": [rnd(100 * v / max(1, total), 1) for v in head.values], "other": other, "total": total,
            "distinct": int(len(vc))}


def column_detail(df: pd.DataFrame, col: str) -> dict:
    s = df[col]
    k = kind_of(s)
    d = {"column": col, "kind": k, "profile": column_profile(df, col)}
    if k == "numeric":
        clean = s.dropna()
        d["hist"] = histogram(s)
        d["outliers"] = outlier_info(s)
        d["skew"] = rnd(clean.skew(), 2) if len(clean) > 2 else None
        d["quantiles"] = {str(q): rnd(clean.quantile(q / 100)) for q in (5, 25, 50, 75, 95)} if len(clean) else {}
        d["suspicious_zeros"] = suspicious_zero_cols(df).get(col)
    elif k == "datetime":
        d["range"] = {"min": str(s.min())[:10], "max": str(s.max())[:10]}
        monthly = s.dropna().dt.to_period("M").value_counts().sort_index()
        d["by_period"] = {"labels": [str(p) for p in monthly.index], "counts": [int(c) for c in monthly.values]}
    else:
        d["counts"] = value_counts(s)
    return d


# --------------------------------------------------------------------------
# Chart builder
# --------------------------------------------------------------------------
def _agg(grouped, how: str):
    return getattr(grouped, how)()


def chart_data(df: pd.DataFrame, spec: dict) -> dict:
    kind = spec.get("type")
    x, y, how = spec.get("x"), spec.get("y"), spec.get("agg") or "mean"
    for name in (x, y):
        if name and name not in df.columns:
            raise ValueError(f"Column '{name}' not found.")
    if how not in ("mean", "sum", "median", "min", "max", "count"):
        raise ValueError("Unsupported aggregation.")

    if kind == "histogram":
        if not x or kind_of(df[x]) != "numeric":
            raise ValueError("Histogram needs a numeric X column.")
        h = histogram(df[x], int(spec.get("bins") or 20))
        return {"type": "histogram", "x": x, "title": f"Distribution of {x}", "hist_type": h["type"],
                **{k: v for k, v in h.items() if k != "type"}}

    if kind == "bar":
        if not x:
            raise ValueError("Choose a column for the X axis.")
        top = int(spec.get("top") or 15)
        sx = df[x]
        if kind_of(sx) == "numeric" and sx.nunique() > 20:
            sx = pd.cut(sx, bins=10).astype(str)
        elif kind_of(sx) == "datetime":
            sx = sx.dt.to_period("M").astype(str)
        if not y or how == "count":
            vc = sx.value_counts().head(top)
            return {"type": "bar", "x": x, "y": None, "title": f"Count by {x}",
                    "labels": [str(i) for i in vc.index], "values": [int(v) for v in vc.values], "ylabel": "Count"}
        if kind_of(df[y]) != "numeric":
            raise ValueError("Y must be a numeric column.")
        g = _agg(pd.DataFrame({"x": sx, "y": df[y]}).dropna().groupby("x")["y"], how)
        g = g.sort_values(ascending=False).head(top)
        return {"type": "bar", "x": x, "y": y, "title": f"{how.title()} of {y} by {x}",
                "labels": [str(i) for i in g.index], "values": [rnd(v) for v in g.values], "ylabel": f"{how} of {y}"}

    if kind == "scatter":
        if not x or not y or kind_of(df[x]) != "numeric" or kind_of(df[y]) != "numeric":
            raise ValueError("Scatter needs two numeric columns.")
        pair = df[[x, y]].dropna()
        if len(pair) < 3:
            raise ValueError("Not enough complete rows.")
        res = pearson(pair[x], pair[y])
        sample = pair.sample(min(len(pair), 600), random_state=7)
        slope, intercept = np.polyfit(pair[x], pair[y], 1)
        return {"type": "scatter", "x": x, "y": y, "title": f"{y} vs {x}", "n": int(len(pair)),
                "points": [[rnd(a), rnd(b)] for a, b in sample.values.tolist()],
                "fit": {"slope": rnd(slope, 6), "intercept": rnd(intercept, 6)},
                "r": res["r"] if res else None, "p": rnd(res["p"], 6) if res else None}

    if kind == "line":
        if not y or kind_of(df[y]) != "numeric":
            raise ValueError("Line charts need a numeric Y column.")
        if x and kind_of(df[x]) == "datetime":
            work = df[[x, y]].dropna().set_index(x).sort_index()
            span = (work.index.max() - work.index.min()).days if len(work) else 0
            freq = "D" if span <= 60 else "W" if span <= 400 else "MS"
            agg = _agg(work[y].resample(freq), spec.get("agg") or default_agg(y))
            return {"type": "line", "x": x, "y": y, "title": f"{y} over time",
                    "labels": [str(i.date()) for i in agg.index], "values": [rnd(v) for v in agg.values], "ylabel": y}
        work = df[[y]].dropna() if not x else df[[x, y]].dropna().sort_values(x)
        step = max(1, len(work) // 300)
        work = work.iloc[::step]
        labels = [str(i) for i in (work.index if not x else work[x])]
        return {"type": "line", "x": x or "row", "y": y, "title": f"{y} by {x or 'row order'}",
                "labels": labels, "values": [rnd(v) for v in work[y].values], "ylabel": y}

    raise ValueError("Unsupported chart type.")


# --------------------------------------------------------------------------
# Seasonality / trend (copilot + overview)
# --------------------------------------------------------------------------
def seasonality_check(df: pd.DataFrame, date_col: str, value_col: str) -> dict:
    work = df[[date_col, value_col]].dropna()
    if len(work) < 24:
        return {"available": False, "reason": "Not enough rows to test seasonality."}
    work = work.assign(month=work[date_col].dt.month)
    groups = [g[value_col].values for _, g in work.groupby("month") if len(g) >= 2]
    if len(groups) < 3:
        return {"available": False, "reason": "Need data from at least three different calendar months."}
    f, p = stats.f_oneway(*groups)
    avg = work.groupby("month")[value_col].mean().sort_values(ascending=False)
    overall = work[value_col].mean()
    lift = rnd(100 * (avg.iloc[0] - overall) / overall, 1) if overall else 0
    return {"available": True, "is_seasonal": bool(p < 0.05), "p": float(p), "f": rnd(f, 2),
            "peak_months": [MONTHS[m - 1] for m in avg.head(2).index],
            "low_months": [MONTHS[m - 1] for m in avg.tail(2).index],
            "peak_lift_pct": lift, "monthly": {MONTHS[m - 1]: rnd(v) for m, v in avg.sort_index().items()}}


def trend_check(df: pd.DataFrame, date_col: str, value_col: str) -> dict:
    work = df[[date_col, value_col]].dropna().set_index(date_col).sort_index()
    if len(work) < 8:
        return {"available": False, "reason": "Not enough rows to assess a trend."}
    span = (work.index.max() - work.index.min()).days
    freq = "W" if span <= 400 else "MS"
    series = _agg(work[value_col].resample(freq), default_agg(value_col))
    series = series[series.notna()]
    if len(series) < 4:
        return {"available": False, "reason": "Not enough time periods to assess a trend."}
    res = stats.linregress(np.arange(len(series)), series.values.astype(float))
    first = series.iloc[0]
    return {"available": True, "slope": rnd(res.slope, 4), "r2": rnd(res.rvalue ** 2, 3), "p": float(res.pvalue),
            "significant": bool(res.pvalue < 0.05), "periods": len(series),
            "labels": [str(i.date()) for i in series.index], "values": [rnd(v) for v in series.values],
            "change_pct": rnd(100 * (series.iloc[-1] - first) / abs(first), 1) if first else None}


# --------------------------------------------------------------------------
# Insights + overview
# --------------------------------------------------------------------------
def insights(df: pd.DataFrame, target: str | None, q: dict | None = None) -> list[dict]:
    out: list[dict] = []
    q = q or quality(df)
    n, m = df.shape
    out.append({"level": "info", "title": f"{n:,} rows and {m} columns",
                "detail": f"{len(numeric_cols(df))} numeric, {len(categorical_cols(df))} categorical, "
                          f"{len(datetime_cols(df))} date column(s)."})

    zero_issues = [i for i in q["issues"] if i["type"] == "suspicious_zeros"]
    if zero_issues:
        names = ", ".join(i["columns"][0] for i in zero_issues[:4])
        out.append({"level": "warn", "title": "Hidden missing values detected",
                    "detail": f"Zeros in {names} look like placeholders, not real measurements. "
                              "Convert them to missing before analysing."})
    high = [i for i in q["issues"] if i["severity"] == "high" and i["type"] == "missing"]
    if high:
        out.append({"level": "warn", "title": f"{len(high)} column(s) are mostly incomplete",
                    "detail": ", ".join(i["columns"][0] for i in high[:4]) + " have 20%+ empty values."})
    if q["totals"]["duplicate_rows"]:
        out.append({"level": "warn", "title": f"{q['totals']['duplicate_rows']:,} duplicate rows",
                    "detail": "Remove them in Clean & prep so totals and averages aren't inflated."})

    if target and target in df.columns:
        s = df[target]
        if is_binary(s):
            vc = s.value_counts(normalize=True)
            top = vc.iloc[0]
            out.append({"level": "warn" if top > 0.8 else "info",
                        "title": f"{target} is {'imbalanced' if top > 0.8 else 'reasonably balanced'}",
                        "detail": " / ".join(f"{k}: {100 * v:.1f}%" for k, v in vc.items()) + "."})
        corr = correlations_with(df, target, 3)
        if corr["available"]:
            strong = [r for r in corr["results"] if r["significant"] and abs(r["r"]) >= 0.3]
            if strong:
                out.append({"level": "good", "title": f"Strongest link to {target}: {strong[0]['column']}",
                            "detail": "; ".join(f"{r['column']} (r = {r['r']:+.2f})" for r in strong[:3]) + "."})
            else:
                out.append({"level": "info", "title": f"No strong linear driver of {target}",
                            "detail": "No numeric column has |r| >= 0.3. Relationships may be non-linear."})

    skewed = [c for c in numeric_cols(df, include_binary=False) if abs(df[c].skew()) > 1.5]
    if skewed:
        out.append({"level": "info", "title": f"{len(skewed)} heavily skewed column(s)",
                    "detail": ", ".join(skewed[:4]) + ". Medians describe these better than means."})
    return out[:7]


def overview(df: pd.DataFrame, target: str | None, qual: dict) -> dict:
    prof = profile(df)
    prof.pop("column_profiles")
    tgt = target if target in df.columns else guess_target(df)

    dist = None
    if tgt:
        s = df[tgt]
        if kind_of(s) == "numeric":
            dist = {"column": tgt, "kind": "numeric", **histogram(s)}
        else:
            dist = {"column": tgt, "kind": "categorical", "type": "bars", **value_counts(s, 10)}

    secondary = None
    dts, nums = datetime_cols(df), numeric_cols(df)
    if dts and nums:
        val = tgt if tgt in nums and not is_binary(df[tgt]) else next((c for c in nums if not is_binary(df[c])), None)
        if val:
            tr = trend_check(df, dts[0], val)
            if tr["available"]:
                secondary = {"kind": "trend", "column": val, "date": dts[0], "labels": tr["labels"], "values": tr["values"]}
    if secondary is None:
        cats = [c for c in categorical_cols(df, 40) if c != tgt]
        if cats:
            secondary = {"kind": "breakdown", "column": cats[0], **value_counts(df[cats[0]], 8)}

    corr = correlations_with(df, tgt, 6) if tgt else {"available": False, "reason": "No focus column."}
    return {"profile": prof, "quality": qual, "target": tgt, "target_options": target_options(df),
            "insights": insights(df, tgt, qual),
            "charts": {"distribution": dist, "correlation": corr, "secondary": secondary}}


# --------------------------------------------------------------------------
# Cleaning
# --------------------------------------------------------------------------
def _require_cols(df: pd.DataFrame, cols: list[str]) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"Column(s) not found: {', '.join(missing)}")


def apply_cleaning(df: pd.DataFrame, ops: list[dict]) -> tuple[pd.DataFrame, list[str]]:
    df = df.copy()
    log: list[str] = []
    for op in ops:
        t = op.get("type")
        cols = list(op.get("columns") or [])
        _require_cols(df, cols)

        if t == "drop_duplicates":
            before = len(df)
            df = df.drop_duplicates().reset_index(drop=True)
            log.append(f"Removed {before - len(df):,} duplicate row(s).")

        elif t == "drop_columns":
            if not cols:
                raise ValueError("Choose at least one column to drop.")
            df = df.drop(columns=cols)
            log.append(f"Dropped column(s): {', '.join(cols)}.")

        elif t == "drop_missing_rows":
            before = len(df)
            df = df.dropna(subset=cols or None).reset_index(drop=True)
            log.append(f"Removed {before - len(df):,} row(s) with missing values"
                       + (f" in {', '.join(cols)}." if cols else "."))

        elif t == "zeros_to_nan":
            for c in cols or list(suspicious_zero_cols(df).keys()):
                if kind_of(df[c]) != "numeric":
                    raise ValueError(f"'{c}' is not numeric.")
                n0 = int((df[c] == 0).sum())
                df[c] = df[c].replace(0, np.nan)
                log.append(f"Marked {n0:,} zero(s) in {c} as missing.")

        elif t == "cap_outliers":
            for c in cols or [c for c in numeric_cols(df, include_binary=False) if outlier_info(df[c])]:
                oi = outlier_info(df[c])
                if not oi:
                    continue
                df[c] = df[c].clip(lower=oi["low"], upper=oi["high"])
                log.append(f"Capped {oi['count']:,} extreme value(s) in {c} to [{oi['low']}, {oi['high']}].")

        elif t == "fill_missing":
            strategy = op.get("strategy") or "median"
            for c in cols or [c for c in df.columns if df[c].isna().any()]:
                n_missing = int(df[c].isna().sum())
                if n_missing == 0:
                    continue
                k = kind_of(df[c])
                strat = "mode" if (k != "numeric" and strategy in ("mean", "median")) else strategy
                if strat == "mean":
                    val = df[c].mean()
                elif strat == "median":
                    val = df[c].median()
                elif strat == "zero":
                    val = 0
                elif strat == "constant":
                    val = op.get("value")
                    if val is None or val == "":
                        raise ValueError("Provide a value to fill with.")
                    if k == "numeric":
                        val = float(val)
                else:
                    mode = df[c].mode(dropna=True)
                    if mode.empty:
                        continue
                    val = mode.iloc[0]
                df[c] = df[c].fillna(val)
                shown = rnd(val, 3) if isinstance(val, (int, float, np.number)) else val
                log.append(f"Filled {n_missing:,} missing value(s) in {c} with {strat} ({shown}).")
                if n_missing / max(1, len(df)) > 0.2:
                    log.append(f"Caution: {c} had {100 * n_missing / len(df):.0f}% of its values filled with one number, which flattens "
                               "its spread and can make real values look extreme. Consider dropping the column or leaving the gaps.")
        else:
            raise ValueError(f"Unknown cleaning step '{t}'.")
    if not log:
        log.append("No changes were needed.")
    return df, log
