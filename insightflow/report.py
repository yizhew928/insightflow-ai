"""Standalone, escaped HTML export with a static chart and reproducible evidence."""
from html import escape
import math
import pandas as pd
from .explanations import explain_result


def _bar_chart(df):
    numeric = list(df.select_dtypes(include='number').columns)
    if not numeric or df.empty:
        return '<p>No numeric result available for a chart.</p>'
    column = 'value' if {'group_key', 'value'} == set(df.columns) and 'value' in numeric else numeric[0]
    values = pd.to_numeric(df[column], errors='coerce').head(12)
    finite = [abs(float(v)) for v in values if pd.notna(v) and math.isfinite(float(v))]
    scale = max(finite, default=0) or 1
    bars = []
    for index, val in values.items():
        if pd.isna(val) or not math.isfinite(float(val)):
            continue
        label = str(df.loc[index].iloc[0])[:60]
        width = round(abs(float(val)) / scale * 360, 1)
        bars.append(f'<div class="bar-row"><span>{escape(label)}</span><div class="track"><div class="bar" style="width:{width}px"></div></div><strong>{float(val):,.2f}</strong></div>')
    return '<h3>' + escape(str(column)) + ' (first 12 rows)</h3>' + ''.join(bars)


def build_report(source_name, sheet_name, quality, analysis):
    e = lambda value: escape(str(value), quote=True)
    result = analysis['result']
    formulas = ''.join(f'<li>{e(f)}</li>' for f in analysis['formulas'])
    lines = analysis.get('explanation') or explain_result(analysis)
    explanation = ''.join(f'<p>{e(line)}</p>' for line in lines)
    title = e(analysis['title'])
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>InsightFlow AI Report</title><style>
body{{font:16px system-ui,sans-serif;color:#172235;max-width:1100px;margin:40px auto;padding:0 20px;line-height:1.55}}h1,h2{{color:#193b58}}.meta{{color:#526579}}.card{{background:#f3f7fa;border-radius:10px;padding:20px;margin:20px 0;overflow:auto}}table{{border-collapse:collapse;font-size:14px}}th,td{{padding:8px;border:1px solid #d7e1e8;text-align:left}}th{{background:#e3eef2}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}.bar-row{{display:flex;gap:12px;align-items:center;margin:8px 0}}.bar-row>span{{width:160px;overflow:hidden}}.track{{width:360px;max-width:45%;background:#e7eff2}}.bar{{max-width:100%;height:16px;background:#137f81}}
</style></head><body><h1>InsightFlow AI — {title}</h1><p class="meta">Source: {e(source_name)} · Sheet/table: {e(sheet_name)} · Local, deterministic calculation</p>
<section class="card" lang="zh-CN" aria-labelledby="explanation"><h2 id="explanation">结果解读</h2>{explanation}</section>
<section class="card"><h2>Analysis results</h2>{result.to_html(index=False, escape=True, na_rep='NULL')} {_bar_chart(result)}</section>
<section class="card"><h2>Data quality</h2><p>Rows: {int(quality['rows'])} · Columns: {int(quality['columns'])} · Missing cells: {int(quality['missing_cells'])} · Duplicate rows: {int(quality['duplicate_rows'])}</p>{quality['column_stats'].to_html(index=False, escape=True)}</section>
<section class="card"><h2>Calculation evidence</h2><ul>{formulas}</ul><h3>Executed SQL</h3><pre>{e(analysis['sql'])}</pre><p>Only the displayed result (up to 1,000 rows) is included. Check the source data, field mapping and assumptions before making decisions.</p></section></body></html>'''
