"""Copilot: turns a plain-English question into a real statistical analysis.

This is intentionally NOT a wrapper around a hosted LLM. It runs offline,
needs no API key, and cannot invent numbers: every figure in an answer is
computed by analysis.py and only *phrased* here.

How it works
  1. detect which dataset columns the question mentions (handles
     "blood pressure" -> BloodPressure, case and underscores);
  2. match the question to an intent with keyword patterns;
  3. run the matching analysis; return text + evidence + a small chart.

Confidence is honest: hypothesis tests report their p-value and a
"statistical confidence" of (1 - p); exact calculations (means, counts)
are labelled "Exact calculation" instead of showing a made-up percentage.

Optional LLM upgrade: pass the returned dict (never the raw data) to an LLM
and ask it to rephrase only. Keep these numbers as the single source of truth.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
from scipy import stats

from ..core.utils import rnd
from . import analysis as an

EXACT = "Exact calculation"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _variants(col: str) -> set[str]:
    split = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", col)
    return {v for v in (_norm(col), _norm(split)) if v}


def mentioned_columns(df: pd.DataFrame, q: str) -> list[str]:
    qn = f" {_norm(q)} "
    hits = []
    for c in df.columns:
        for v in _variants(c):
            pos = qn.find(f" {v} ")
            if pos >= 0:
                hits.append((pos, -len(v), c))
                break
    hits.sort()
    seen, out = set(), []
    for _, _, c in hits:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _f(x, nd: int = 2) -> str:
    if x is None:
        return "n/a"
    if abs(x) >= 1000:
        return f"{x:,.0f}"
    return f"{x:,.{nd}f}".rstrip("0").rstrip(".") if isinstance(x, float) else f"{x:,}"


def _conf(p: float) -> tuple[int | None, str]:
    if p < 0.05:
        c = int(min(99, round(100 * (1 - p))))
        return c, f"Statistical confidence {c}% ({an.fmt_p(p)})"
    return None, f"Not statistically significant ({an.fmt_p(p)})"


def _cohen(d: float) -> str:
    a = abs(d)
    return "large" if a >= 0.8 else "medium" if a >= 0.5 else "small" if a >= 0.2 else "negligible"


def _resp(answer, intent, *, evidence=None, label=EXACT, confidence=None, chart=None):
    return {"answer": answer, "intent": intent, "evidence": evidence or [], "confidence": confidence,
            "confidence_label": label, "chart": chart, "suggestions": []}


def suggestions(df: pd.DataFrame, target: str | None) -> list[str]:
    nums = sorted(an.numeric_cols(df, include_binary=False), key=lambda c: -df[c].nunique())  # continuous first
    cats = an.categorical_cols(df, 12)
    group = target if (target and an.is_binary(df[target])) else (cats[0] if cats else None)
    dts = an.datetime_cols(df)
    out = []
    if target and an.kind_of(df[target]) == "numeric":
        out.append(f"What affects {target}?")
    if nums:
        out.append(f"Show the distribution of {nums[0]}")
    other = next((n for n in nums if n != target), nums[0] if nums else None)
    if group and other:
        out.append(f"Compare {other} by {group}")
    if dts and nums:
        out.append(f"Is {nums[0]} seasonal?")
    out += ["Which columns have missing values?", "Are there any outliers?", "Give me a summary of this data"]
    seen, uniq = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


# ------------------------------------------------------------------ handlers
def _pick_value_col(df, ctx, exclude=()):
    for c in ctx["cols"]:
        if c not in exclude and an.kind_of(df[c]) == "numeric" and not an.is_binary(df[c]):
            return c
    t = ctx["target"]
    if t and t not in exclude and an.kind_of(df[t]) == "numeric" and not an.is_binary(df[t]):
        return t
    return next((c for c in an.numeric_cols(df, include_binary=False) if c not in exclude), None)


def h_quality(df, ctx):
    q = ctx["quality"]()
    ql = ctx["q"].lower()
    cols = ctx["cols"]
    if cols and re.search(r"missing|null|empty", ql):
        c = cols[0]
        n = int(df[c].isna().sum())
        pct = 100 * n / max(1, len(df))
        return _resp(f"{c} has {n:,} missing value(s), which is {_f(pct)}% of {len(df):,} rows.", "quality",
                     evidence=[f"{n:,} empty cells"])
    top = q["issues"][:3]
    if top:
        text = (f"The data trust score is {q['score']}/100 ({q['grade']}). Biggest concerns: "
                + "; ".join(i["title"] for i in top) + ". The Clean & prep page can fix these in a few clicks.")
    else:
        text = f"The data trust score is {q['score']}/100 ({q['grade']}). No significant issues found."
    chart = {"type": "bar", "title": "Quality dimensions (0-100)",
             "labels": [d["label"] for d in q["dimensions"]], "values": [d["score"] for d in q["dimensions"]]}
    return _resp(text, "quality", evidence=[f"{d['label']}: {d['score']}" for d in q["dimensions"][:4]], chart=chart)


def h_outliers(df, ctx):
    cols = [c for c in ctx["cols"] if an.kind_of(df[c]) == "numeric"]
    if cols:
        c = cols[0]
        oi = an.outlier_info(df[c])
        if not oi:
            return _resp(f"{c} has too few distinct values to define outliers.", "outliers")
        return _resp(f"{c} has {oi['count']:,} outlier(s) ({_f(oi['pct'])}% of values) outside the normal range "
                     f"[{_f(oi['low'])}, {_f(oi['high'])}] (1.5 x IQR rule).", "outliers",
                     evidence=[f"{oi['count']:,} values", f"limits {_f(oi['low'])} to {_f(oi['high'])}"])
    rows = [(c, an.outlier_info(df[c])) for c in an.numeric_cols(df, include_binary=False)]
    rows = sorted([(c, o) for c, o in rows if o and o["count"]], key=lambda r: -r[1]["pct"])[:6]
    if not rows:
        return _resp("No numeric column has outliers under the 1.5 x IQR rule.", "outliers")
    worst = rows[0]
    return _resp(f"{worst[0]} has the most outliers ({_f(worst[1]['pct'])}% of values). "
                 f"{len(rows)} column(s) have at least one. Outliers aren't always errors, so check before removing.",
                 "outliers", evidence=[f"{c}: {o['count']:,} ({_f(o['pct'])}%)" for c, o in rows[:4]],
                 chart={"type": "bar", "title": "Outlier share by column (%)", "labels": [c for c, _ in rows],
                        "values": [o["pct"] for _, o in rows]})


def h_seasonality(df, ctx):
    dts = an.datetime_cols(df)
    if not dts:
        return _resp("This dataset has no date column, so seasonality can't be tested. "
                     "Add a date column (e.g. order_date) and re-upload.", "seasonality")
    val = _pick_value_col(df, ctx)
    if not val:
        return _resp("I need a numeric column to test for seasonality.", "seasonality")
    r = an.seasonality_check(df, dts[0], val)
    if not r["available"]:
        return _resp(r["reason"], "seasonality")
    conf, label = _conf(r["p"])
    if r["is_seasonal"]:
        text = (f"Yes, {val} is seasonal: it peaks in {' and '.join(r['peak_months'])} "
                f"({_f(r['peak_lift_pct'])}% above its average) and is lowest in {' and '.join(r['low_months'])}.")
    else:
        text = (f"No clear seasonality in {val}. Monthly averages differ, but not by more than random variation "
                f"would explain.")
    return _resp(text, "seasonality", confidence=conf, label=label,
                 evidence=[an.fmt_p(r["p"]), f"F = {r['f']}", "one-way ANOVA across calendar months"],
                 chart={"type": "bar", "title": f"Average {val} by month", "labels": list(r["monthly"].keys()),
                        "values": list(r["monthly"].values())})


def h_trend(df, ctx):
    dts = an.datetime_cols(df)
    if not dts:
        return None
    val = _pick_value_col(df, ctx)
    if not val:
        return None
    r = an.trend_check(df, dts[0], val)
    if not r["available"]:
        return _resp(r["reason"], "trend")
    conf, label = _conf(r["p"])
    direction = "rising" if r["slope"] > 0 else "falling"
    if r["significant"]:
        change = f" ({r['change_pct']:+.1f}% from first to last period)" if r["change_pct"] is not None else ""
        text = f"{val} shows a statistically significant {direction} trend{change}. The linear trend explains {_f(100 * r['r2'])}% of the variation."
    else:
        text = f"There is no statistically significant trend in {val}. It moves up and down without a consistent direction."
    return _resp(text, "trend", confidence=conf, label=label,
                 evidence=[an.fmt_p(r["p"]), f"R² = {r['r2']}", f"{r['periods']} periods"],
                 chart={"type": "line", "title": f"{val} over time", "labels": r["labels"], "values": r["values"]})


def _group_cols(df, ctx):
    group, value = None, None
    for c in ctx["cols"]:
        s = df[c]
        k = an.kind_of(s)
        is_group = k == "categorical" or an.is_binary(s) or (k == "numeric" and s.nunique() <= 6)
        if is_group and group is None:
            group = c
        elif k == "numeric" and s.nunique() > 6 and value is None:
            value = c
    return group, value


def h_compare(df, ctx):
    group, value = _group_cols(df, ctx)
    if not group or not value:
        return None
    work = df[[group, value]].dropna()
    sizes = work.groupby(group)[value].size().sort_values(ascending=False)
    keep = [g for g in sizes.index[:8] if sizes[g] >= 2]
    if len(keep) < 2:
        return _resp(f"{group} doesn't have at least two groups with enough rows to compare.", "compare")
    samples = [work.loc[work[group] == g, value].values for g in keep]
    means = [float(s.mean()) for s in samples]
    chart = {"type": "bar", "title": f"Average {value} by {group}", "labels": [str(g) for g in keep],
             "values": [rnd(m) for m in means]}
    if len(keep) == 2:
        t, p = stats.ttest_ind(samples[0], samples[1], equal_var=False)
        pooled = np.sqrt((samples[0].var(ddof=1) + samples[1].var(ddof=1)) / 2)
        d = (means[0] - means[1]) / pooled if pooled else 0.0
        conf, label = _conf(float(p))
        text = (f"Average {value} is {_f(means[0])} for {group} = {keep[0]} versus {_f(means[1])} for {group} = {keep[1]} "
                f"(difference {_f(means[0] - means[1])}). ")
        text += (f"The difference is statistically significant, with a {_cohen(d)} effect size (Cohen's d = {abs(d):.2f})."
                 if p < 0.05 else "That difference is not statistically significant.")
        ev = [an.fmt_p(float(p)), f"Cohen's d = {abs(d):.2f}", "Welch t-test", f"n = {len(work):,}"]
    else:
        f_stat, p = stats.f_oneway(*samples)
        conf, label = _conf(float(p))
        hi, lo = keep[int(np.argmax(means))], keep[int(np.argmin(means))]
        text = (f"Average {value} is highest for {group} = {hi} ({_f(max(means))}) and lowest for {lo} ({_f(min(means))}). "
                + ("The groups differ significantly." if p < 0.05 else "The groups do not differ significantly."))
        ev = [an.fmt_p(float(p)), f"F = {f_stat:.2f}", "one-way ANOVA", f"{len(keep)} groups"]
    return _resp(text, "compare", confidence=conf, label=label, evidence=ev, chart=chart)


def h_correlation(df, ctx):
    nums = [c for c in ctx["cols"] if an.kind_of(df[c]) == "numeric"]
    if len(nums) >= 2:
        r = an.pearson(df[nums[0]], df[nums[1]])
        if not r:
            return _resp("Those columns don't have enough varying data to correlate.", "correlation")
        conf, label = _conf(r["p"])
        sign = "positive" if r["r"] > 0 else "negative"
        text = (f"{nums[0]} and {nums[1]} have a {an.strength(r['r'])} {sign} correlation (r = {r['r']:+.2f}). "
                + ("It is statistically significant. " if r["p"] < 0.05 else "It is not statistically significant. ")
                + "Correlation shows association, not cause.")
        pair = df[[nums[0], nums[1]]].dropna()
        sample = pair.sample(min(len(pair), 300), random_state=3)
        return _resp(text, "correlation", confidence=conf, label=label,
                     evidence=[f"r = {r['r']:+.2f}", an.fmt_p(r["p"]), f"n = {r['n']:,}"],
                     chart={"type": "scatter", "title": f"{nums[1]} vs {nums[0]}",
                            "points": [[rnd(a), rnd(b)] for a, b in sample.values.tolist()]})
    tgt = nums[0] if nums else ctx["target"]
    if not tgt or an.kind_of(df[tgt]) != "numeric":
        return _resp("Tell me which numeric column to analyse, for example 'What affects <column>?'.", "correlation")
    res = an.correlations_with(df, tgt, 6)
    if not res["available"]:
        return _resp(res["reason"], "correlation")
    sig = [x for x in res["results"] if x["significant"]]
    if not sig:
        return _resp(f"No other numeric column has a statistically significant linear relationship with {tgt}.",
                     "correlation", label="Not statistically significant")
    top = sig[0]
    conf, label = _conf(top["p"])
    rest = ", ".join(f"{x['column']} ({x['r']:+.2f})" for x in sig[1:3])
    text = (f"The strongest linear relationship with {tgt} is {top['column']} (r = {top['r']:+.2f}, {top['strength']}, "
            f"{an.fmt_p(top['p'])}, n = {top['n']:,})." + (f" Next: {rest}." if rest else "")
            + " Correlation shows association, not cause.")
    return _resp(text, "correlation", confidence=conf, label=label,
                 evidence=[f"{x['column']}: r = {x['r']:+.2f}" for x in sig[:4]],
                 chart={"type": "bar", "title": f"Correlation with {tgt}", "labels": [x["column"] for x in res["results"]],
                        "values": [x["r"] for x in res["results"]], "signed": True})


def h_distribution(df, ctx):
    c = ctx["cols"][0] if ctx["cols"] else ctx["target"]
    if not c:
        return None
    s = df[c]
    if an.kind_of(s) != "numeric":
        return h_breakdown(df, {**ctx, "cols": [c]})
    cl = s.dropna()
    skew = float(cl.skew()) if len(cl) > 2 else 0.0
    shape = ("right-skewed" if skew > 0.5 else "left-skewed" if skew < -0.5 else "roughly symmetric")
    hint = " The median describes a typical value better than the mean." if abs(skew) > 1 else ""
    text = (f"{c} ranges from {_f(float(cl.min()))} to {_f(float(cl.max()))} with a median of {_f(float(cl.median()))} "
            f"(mean {_f(float(cl.mean()))}, std {_f(float(cl.std()))}). It is {shape} (skew {skew:.2f}).{hint}")
    h = an.histogram(s)
    chart = ({"type": "hist", "title": f"Distribution of {c}", **{k: v for k, v in h.items() if k != "type"},
              "hist_type": h["type"]} if h["type"] != "empty" else None)
    oi = an.outlier_info(s)
    ev = [f"n = {len(cl):,}", f"skew {skew:.2f}"] + ([f"{oi['count']:,} outliers"] if oi and oi["count"] else [])
    return _resp(text, "distribution", evidence=ev, chart=chart)


_STAT_WORDS = [("median", "median"), ("average", "mean"), ("mean", "mean"), ("highest", "max"), ("maximum", "max"),
               ("max", "max"), ("lowest", "min"), ("minimum", "min"), ("min", "min"), ("deviation", "std"),
               ("std", "std"), ("total", "sum"), ("sum", "sum")]


def h_stat(df, ctx):
    ql = ctx["q"].lower()
    if re.search(r"\b(rows|records|entries|observations|samples)\b", ql):
        return _resp(f"The dataset has {len(df):,} rows.", "stat", evidence=[f"{df.shape[1]} columns"])
    if re.search(r"\bhow many columns\b|number of columns", ql):
        return _resp(f"The dataset has {df.shape[1]} columns.", "stat")
    cols = [c for c in ctx["cols"] if an.kind_of(df[c]) == "numeric"]
    if not cols:
        c = ctx["cols"][0] if ctx["cols"] else None
        if c is not None:
            n = int(df[c].nunique())
            return _resp(f"{c} has {n:,} distinct value(s) across {int(df[c].notna().sum()):,} non-empty rows.", "stat")
        return None
    c = cols[0]
    s = df[c].dropna()
    stat = next((fn for w, fn in _STAT_WORDS if w in ql), None)
    if stat is None:
        return None
    val = float(getattr(s, stat)())
    names = {"mean": "average", "median": "median", "max": "maximum", "min": "minimum", "std": "standard deviation", "sum": "total"}
    return _resp(f"The {names[stat]} of {c} is {_f(val)} (based on {len(s):,} non-empty rows).", "stat",
                 evidence=[f"n = {len(s):,}", f"mean {_f(float(s.mean()))}", f"median {_f(float(s.median()))}"])


def h_breakdown(df, ctx):
    c = next((c for c in ctx["cols"] if an.kind_of(df[c]) == "categorical" or an.is_binary(df[c])), None)
    if c is None:
        cats = an.categorical_cols(df, 40)
        c = cats[0] if cats else None
    if c is None:
        return None
    vc = an.value_counts(df[c], 8)
    if not vc["labels"]:
        return None
    text = (f"{vc['labels'][0]} is the most common {c} ({_f(vc['pct'][0], 1)}% of {vc['total']:,} records). "
            f"There are {vc['distinct']} distinct value(s) in total.")
    return _resp(text, "breakdown", evidence=[f"{l}: {p}%" for l, p in zip(vc["labels"][:4], vc["pct"][:4])],
                 chart={"type": "bar", "title": f"{c} breakdown", "labels": vc["labels"], "values": vc["counts"]})


def h_summary(df, ctx):
    p = an.profile(df)
    q = ctx["quality"]()
    ins = an.insights(df, ctx["target"], q)[1:4]
    text = (f"This dataset has {p['rows']:,} rows and {p['columns']} columns ({p['numeric']} numeric, "
            f"{p['categorical']} categorical, {p['datetime']} date). Its data trust score is {q['score']}/100 ({q['grade']}).")
    if ins:
        text += " Key findings: " + " ".join(i["title"] + "." for i in ins)
    return _resp(text, "summary", evidence=[i["title"] for i in ins])


def h_help(df, ctx):
    return _resp("I can describe a column, compare groups (e.g. 'Compare BMI by Outcome'), find what drives a column "
                 "('What affects Glucose?'), test trends and seasonality when there's a date column, check outliers "
                 "and data quality, and summarise the dataset. Every answer is calculated from your data.", "help")


INTENTS = [
    ("help", r"^(hi|hello|hey|help)\b|what can you|what do you do", h_help),
    ("quality", r"missing|null|empty|data quality|quality|health|trust|clean|duplicate|dirty|incomplete", h_quality),
    ("outliers", r"outlier|anomal|extreme|unusual", h_outliers),
    ("seasonality", r"season|time of (the )?year|peak month|monthly pattern", h_seasonality),
    ("trend", r"trend|over time|growth|growing|declin|rising|falling|increas|decreas", h_trend),
    ("compare", r"compare|versus|\bvs\b|differ|difference|\bby\b|between|across|\bper\b|each", h_compare),
    ("correlation", r"correlat|driver|relationship|influenc|affect|impact|depend|predict|associat|related|important|factor|cause|why", h_correlation),
    ("distribution", r"distribut|histogram|spread|skew|shape|range|variab", h_distribution),
    ("stat", r"average|mean|median|max|min|highest|lowest|std|deviation|sum|total|how many|count|number of", h_stat),
    ("breakdown", r"breakdown|split|share|proportion|mix|percent|composition|categories", h_breakdown),
    ("summary", r"summar|overview|describe|about|what is|tell me|insight|finding|key|explain", h_summary),
]


def answer(df: pd.DataFrame, question: str, target: str | None = None, quality_fn=None) -> dict:
    q = question.strip()
    cols = mentioned_columns(df, q)
    if target not in df.columns:
        target = an.guess_target(df)
    memo: dict = {}

    def quality():
        if "q" not in memo:
            memo["q"] = quality_fn() if quality_fn else an.quality(df)
        return memo["q"]

    ctx = {"q": q, "cols": cols, "target": target, "quality": quality}
    ql = q.lower()
    result = None
    for name, pattern, handler in INTENTS:
        if re.search(pattern, ql):
            result = handler(df, ctx)
            if result is not None:
                break
    if result is None and cols:
        result = h_distribution(df, ctx)
    if result is None:
        result = _resp("I couldn't match that to an analysis I can run on this data. Try one of the suggestions below, "
                       "or ask about a specific column.", "unknown", label="No analysis run")
    result["suggestions"] = [s for s in suggestions(df, target) if s.lower() != ql][:3]
    return result
