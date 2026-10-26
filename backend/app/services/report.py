"""Builds a self-contained, print-ready HTML report ("Save as PDF" from the
browser gives a clean multi-page PDF). All dynamic text is HTML-escaped."""
from __future__ import annotations

import datetime as dt
from html import escape as e

import pandas as pd

from . import analysis as an

LEVEL_ICON = {"warn": "!", "good": "✓", "info": "i"}


def _f(x, nd: int = 2) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, int):
        return f"{x:,}"
    if abs(x) >= 1000:
        return f"{x:,.0f}"
    return f"{x:,.{nd}f}".rstrip("0").rstrip(".")


def _hist_svg(h: dict, w: int = 250, ht: int = 84) -> str:
    counts = h.get("counts") or []
    if not counts:
        return ""
    mx = max(counts) or 1
    n = len(counts)
    gap = 2
    bw = (w - gap * (n - 1)) / n
    bars = []
    for i, c in enumerate(counts):
        bh = max(1.5, (c / mx) * (ht - 6))
        bars.append(f'<rect x="{i * (bw + gap):.1f}" y="{ht - bh:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="1.5" fill="#1F9E82"/>')
    return f'<svg viewBox="0 0 {w} {ht}" width="100%" height="{ht}" preserveAspectRatio="none">{"".join(bars)}</svg>'


def _bar_row(label: str, value: float, color: str = "#1F9E82", text: str | None = None, signed: bool = False) -> str:
    if signed:
        pct = min(50, abs(value) * 50)
        left = 50 if value >= 0 else 50 - pct
        col = "#1F9E82" if value >= 0 else "#C8792A"
        track = f'<div class="track signed"><i style="left:{left}%;width:{pct}%;background:{col}"></i><b></b></div>'
    else:
        track = f'<div class="track"><i style="left:0;width:{max(0, min(100, value))}%;background:{color}"></i></div>'
    return (f'<div class="brow"><span class="blabel">{e(label)}</span>{track}'
            f'<span class="bval">{e(text if text is not None else _f(value))}</span></div>')


def _score_color(score: float) -> str:
    return "#1F9E82" if score >= 85 else "#C8792A" if score >= 70 else "#B03A3A"


CSS = """
@font-face{font-family:'Fraunces';font-weight:500;src:url('/assets/fonts/fraunces-latin-500-normal.woff2') format('woff2');}
@font-face{font-family:'IBM Plex Sans';font-weight:400;src:url('/assets/fonts/ibm-plex-sans-latin-400-normal.woff2') format('woff2');}
@font-face{font-family:'IBM Plex Sans';font-weight:600;src:url('/assets/fonts/ibm-plex-sans-latin-600-normal.woff2') format('woff2');}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'IBM Plex Sans',Segoe UI,Arial,sans-serif;color:#14183B;background:#EEF0EC;font-size:13px;line-height:1.55;
  -webkit-print-color-adjust:exact;print-color-adjust:exact}
.toolbar{position:sticky;top:0;z-index:5;background:#14183B;color:#fff;display:flex;justify-content:space-between;align-items:center;padding:10px 24px}
.toolbar .brand{font-family:'Fraunces',Georgia,serif;font-size:18px}.toolbar .brand span{color:#2FD8AE}
.toolbar button{background:#2FD8AE;color:#14183B;border:0;border-radius:6px;padding:8px 16px;font:600 13px 'IBM Plex Sans',sans-serif;cursor:pointer}
.page{max-width:860px;margin:24px auto;background:#fff;padding:48px 52px;box-shadow:0 8px 30px rgba(20,24,59,.12)}
h1{font-family:'Fraunces',Georgia,serif;font-weight:500;font-size:30px;line-height:1.15}
h2{font-family:'Fraunces',Georgia,serif;font-weight:500;font-size:19px;margin:30px 0 10px;padding-bottom:6px;border-bottom:1px solid #E4E4DE}
.meta{color:#6B6F7B;margin-top:6px}
.lead{margin-top:18px;font-size:14px;color:#2A2F5C}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:14px}
.kpi{border:1px solid #E4E4DE;border-radius:8px;padding:10px 12px}.kpi small{display:block;color:#6B6F7B;font-size:11px}
.kpi b{font-size:20px;font-weight:600}
.score{display:flex;gap:22px;align-items:center;margin-top:6px}
.score .big{font-family:'Fraunces',Georgia,serif;font-size:54px;line-height:1}.score .big small{font-size:16px;color:#6B6F7B}
.grade{display:inline-block;padding:2px 10px;border-radius:20px;font-weight:600;font-size:12px;color:#fff}
.brow{display:grid;grid-template-columns:150px 1fr 70px;gap:10px;align-items:center;margin:7px 0}
.blabel{font-size:12px}.bval{text-align:right;font-variant-numeric:tabular-nums;font-size:12px;color:#2A2F5C}
.track{height:8px;background:#ECECE6;border-radius:4px;position:relative;overflow:hidden}.track i{position:absolute;top:0;bottom:0;border-radius:4px}
.track.signed b{position:absolute;left:50%;top:-2px;bottom:-2px;width:1px;background:#14183B}
table{width:100%;border-collapse:collapse;font-size:12px;margin-top:8px}
th{background:#14183B;color:#fff;text-align:left;font-weight:600;padding:7px 9px}
td{padding:6px 9px;border-bottom:1px solid #ECECE6;vertical-align:top}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.pill{display:inline-block;padding:1px 8px;border-radius:20px;font-size:11px;font-weight:600}
.high{background:#F6DADA;color:#8C2F2F}.medium{background:#FBEEE0;color:#8A4F12}.low{background:#E4F3EF;color:#166E5B}
.find{display:flex;gap:10px;margin:8px 0}.find .ic{flex:0 0 22px;height:22px;border-radius:50%;background:#E4F3EF;color:#166E5B;
  display:flex;align-items:center;justify-content:center;font-weight:600;font-size:12px}
.find.warn .ic{background:#FBEEE0;color:#8A4F12}.find p{color:#6B6F7B}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:10px}
.hcell{border:1px solid #E4E4DE;border-radius:8px;padding:9px 10px}.hcell b{font-size:12px;display:block;margin-bottom:4px}
.hcell small{color:#6B6F7B;font-size:10.5px}
.note{color:#6B6F7B;font-size:11.5px;margin-top:8px}
footer{margin-top:34px;padding-top:12px;border-top:1px solid #E4E4DE;color:#6B6F7B;font-size:11px;display:flex;justify-content:space-between}
section{break-inside:avoid-page}
@media print{body{background:#fff}.toolbar{display:none}.page{margin:0;box-shadow:none;padding:0;max-width:none}
  @page{size:A4;margin:16mm}h2{break-after:avoid}tr{break-inside:avoid}thead{display:table-header-group}}
"""


def build_report(name: str, df: pd.DataFrame, qual: dict, target: str | None) -> str:
    ov = an.overview(df, target, qual)
    prof = ov["profile"]
    tgt = ov["target"]
    now = dt.datetime.now(dt.timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    profiles = an.profile(df)["column_profiles"]
    desc = an.describe_numeric(df)
    cm = an.correlation_matrix(df)

    score = qual["score"]
    top_issue = qual["issues"][0]["title"] if qual["issues"] else "no significant issues"
    lead = (f"This report analyses <b>{e(name)}</b>: {prof['rows']:,} rows across {prof['columns']} columns "
            f"({prof['numeric']} numeric, {prof['categorical']} categorical, {prof['datetime']} date). "
            f"The data trust score is <b>{score}/100 ({e(qual['grade'])})</b>; the most important issue is: "
            f"<i>{e(top_issue)}</i>.")

    kpis = "".join(f'<div class="kpi"><small>{e(k)}</small><b>{e(v)}</b></div>' for k, v in [
        ("Rows", f"{prof['rows']:,}"), ("Columns", str(prof["columns"])),
        ("Missing cells", f"{prof['missing_cells']:,} ({_f(prof['missing_pct'])}%)"),
        ("Duplicate rows", f"{prof['duplicate_rows']:,}")])

    dims = "".join(_bar_row(d["label"], d["score"], _score_color(d["score"]), f"{_f(d['score'], 1)} / 100") for d in qual["dimensions"])
    dim_notes = "".join(f"<li><b>{e(d['label'])}</b> (weight {d['weight']}%): {e(d['detail'])}</li>" for d in qual["dimensions"])

    if qual["issues"]:
        rows = "".join(
            f"<tr><td><span class='pill {i['severity']}'>{e(i['severity'])}</span></td><td><b>{e(i['title'])}</b><br>"
            f"<span style='color:#6B6F7B'>{e(i['detail'])}</span></td></tr>" for i in qual["issues"][:14])
        issues = f"<table><thead><tr><th style='width:80px'>Severity</th><th>Issue and why it matters</th></tr></thead><tbody>{rows}</tbody></table>"
        if len(qual["issues"]) > 14:
            issues += f"<p class='note'>{len(qual['issues']) - 14} lower-priority issue(s) not shown.</p>"
    else:
        issues = "<p class='note'>No data quality issues were detected.</p>"

    findings = "".join(
        f"<div class='find {i['level']}'><span class='ic'>{LEVEL_ICON.get(i['level'], 'i')}</span>"
        f"<div><b>{e(i['title'])}</b><p>{e(i['detail'])}</p></div></div>" for i in ov["insights"])

    col_rows = []
    for c in profiles:
        if c["kind"] == "numeric":
            summ = f"mean {_f(c['mean'])}, range {_f(c['min'])} to {_f(c['max'])}"
        elif c["kind"] == "datetime":
            summ = f"{c.get('min')} to {c.get('max')}"
        else:
            summ = f"top: {c.get('top', 'n/a')} ({_f(c.get('top_pct'), 1)}%)"
        col_rows.append(f"<tr><td><b>{e(c['name'])}</b></td><td>{e(c['kind'])}{' (binary)' if c['binary'] else ''}</td>"
                        f"<td class='n'>{_f(c['missing_pct'], 1)}%</td><td class='n'>{c['unique']:,}</td><td>{e(summ)}</td></tr>")
    columns_tbl = ("<table><thead><tr><th>Column</th><th>Type</th><th class='n'>Missing</th><th class='n'>Unique</th>"
                   f"<th>Summary</th></tr></thead><tbody>{''.join(col_rows)}</tbody></table>")

    num_tbl = ""
    if desc:
        r = "".join(f"<tr><td><b>{e(d['column'])}</b></td>" + "".join(
            f"<td class='n'>{_f(d[k])}</td>" for k in ("count", "mean", "std", "min", "median", "max", "skew")) + "</tr>"
            for d in desc[:20])
        num_tbl = ("<table><thead><tr><th>Column</th><th class='n'>Count</th><th class='n'>Mean</th><th class='n'>Std</th>"
                   "<th class='n'>Min</th><th class='n'>Median</th><th class='n'>Max</th><th class='n'>Skew</th></tr></thead>"
                   f"<tbody>{r}</tbody></table>")

    rel = ""
    if ov["charts"]["correlation"].get("available"):
        c = ov["charts"]["correlation"]
        rel += f"<p class='note'>Pearson correlation with <b>{e(c['target'])}</b> (focus column):</p>"
        rel += "".join(_bar_row(r["column"], r["r"], text=f"{r['r']:+.2f}", signed=True) for r in c["results"])
    elif cm.get("available") is False:
        rel += f"<p class='note'>{e(cm.get('reason', ''))}</p>"
    if cm.get("available"):
        pairs = "".join(f"<tr><td>{e(p['a'])}</td><td>{e(p['b'])}</td><td class='n'>{p['r']:+.2f}</td></tr>" for p in cm["top_pairs"][:6])
        rel += ("<p class='note' style='margin-top:14px'>Strongest pairwise relationships among numeric columns:</p>"
                f"<table><thead><tr><th>Column A</th><th>Column B</th><th class='n'>r</th></tr></thead><tbody>{pairs}</tbody></table>")

    hists = []
    for c in an.numeric_cols(df)[:9]:
        h = an.histogram(df[c], 14)
        if h.get("counts"):
            sk = df[c].skew()
            hists.append(f"<div class='hcell'><b>{e(c)}</b>{_hist_svg(h)}<small>median {_f(float(df[c].median()))}, skew {_f(float(sk), 1)}</small></div>")
    dist = f"<div class='grid'>{''.join(hists)}</div>" if hists else "<p class='note'>No numeric columns to chart.</p>"

    body = f"""
<div class="toolbar"><div class="brand">Nexlytic<span>X</span></div><button type="button" id="print-btn">Print / Save as PDF</button></div>
<div class="page">
  <h1>Data Analysis Report</h1>
  <p class="meta">{e(name)} &middot; generated {e(now)}</p>
  <p class="lead">{lead}</p>
  <div class="kpis">{kpis}</div>

  <section><h2>1. Data trust score</h2>
    <div class="score"><div class="big" style="color:{_score_color(score)}">{_f(score, 1)}<small> / 100</small></div>
      <div><span class="grade" style="background:{_score_color(score)}">{e(qual['grade'])}</span>
      <p class="note">A weighted blend of five quality dimensions, calculated directly from the data.</p></div></div>
    <div style="margin-top:10px">{dims}</div>
    <ul class="note" style="margin:8px 0 0 18px">{dim_notes}</ul>
  </section>

  <section><h2>2. Issues and recommendations</h2>{issues}</section>
  <section><h2>3. Key findings</h2>{findings}</section>
  <section><h2>4. Column profile</h2>{columns_tbl}</section>
  {f'<section><h2>5. Numeric summary</h2>{num_tbl}</section>' if num_tbl else ''}
  <section><h2>6. Relationships</h2>{rel or "<p class='note'>Not enough numeric columns.</p>"}</section>
  <section><h2>7. Distributions</h2>{dist}</section>

  <section><h2>Method and limitations</h2>
    <p class="note">All figures are computed with pandas and SciPy on the uploaded file; nothing is estimated by a language model.
    Outliers use the 1.5 x IQR rule. "Suspicious zeros" is a heuristic: a zero far below the smallest real value in a
    continuous, non-negative column is flagged as a likely placeholder, so verify it against your domain knowledge.
    Correlation shows association, not causation, and only linear relationships are measured. Statistical tests assume
    reasonably independent rows.</p></section>
  <footer><span>NexlyticX</span><span>{e(now)}</span></footer>
</div>
<script>document.getElementById('print-btn').addEventListener('click',function(){{window.print()}});</script>
"""
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Report - {e(name)}</title><style>{CSS}</style></head><body>{body}</body></html>')
