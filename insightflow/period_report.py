"""Portable, offline HTML for the same comparison and product scope as the dashboard."""
from html import escape
from .period_insights import display, explain_period


def e(value):
    return escape(str(value), quote=True)


def table(headers, rows):
    head = ''.join(f'<th scope="col">{e(h)}</th>' for h in headers)
    body = ''.join('<tr>'+''.join(f'<td>{e(cell)}</td>' for cell in row)+'</tr>' for row in rows)
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _chart(comp):
    frame = comp['contributions'].dropna(subset=['delta_revenue']).copy()
    if frame.empty:
        return '<p>两个期间均有数据时显示贡献图。</p>'
    # The table retains all groups even when the display is limited.
    order = frame['delta_revenue'].abs().sort_values(ascending=False, kind='stable').head(12).index
    frame = frame.loc[order]
    largest = max(float(frame.delta_revenue.abs().max()), 1e-12)
    rows = []
    for row in frame.itertuples():
        v = float(row.delta_revenue)
        length = 50 * abs(v) / largest
        left = 50-length if v<0 else 50
        sign = 'negative' if v<0 else 'positive'
        rows.append(f'<div class="bar"><span>{e(row.name)}</span><div class="track"><i class="{sign}" style="left:{left:.3f}%;width:{length:.3f}%"></i></div><b>{v:+,.2f}</b></div>')
    return '<figure aria-label="各组对销售额变化的贡献">' + ''.join(rows) + '<figcaption>中心线为零。按变化金额的绝对值展示最多 12 项，完整分解见下表。</figcaption></figure>'


def build_period_report(comparison, detail=None, *, source='', question=''):
    c = comparison
    periods = [c['previous_label'],c['current_label']]
    p, n, diff = c['previous'],c['current'],c['changes']
    parts = ['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>InsightFlow · 销售同比复盘</title><style>',
    'body{max-width:920px;margin:0 auto;padding:28px 5%;color:#183c3a;background:#faf9f5;font:16px/1.65 system-ui,sans-serif}h1,h2{line-height:1.25}h1{font-size:2.3em}h2{margin-top:2em}p,li{max-width:85ch}.muted,figcaption{color:#516765;font-size:.88em}section{padding:16px 0;border-bottom:1px solid #c5d0cb}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}td,th{white-space:nowrap;text-align:right;border-bottom:1px solid #d6ddda;padding:7px 10px}th:first-child,td:first-child{text-align:left}th{background:#e8eee9}.bar{display:grid;grid-template-columns:minmax(65px,1fr) 3fr minmax(56px,.8fr);gap:12px;align-items:center}.bar b{text-align:right;font-variant-numeric:tabular-nums}.track{position:relative;height:22px;background:linear-gradient(90deg,transparent 49.8%,#8a9b94 50%,transparent 50.2%)}.track i{position:absolute;height:12px;top:5px}.negative{background:#b85742}.positive{background:#196c60}figure{margin:1em 0}pre{padding:14px;background:#eaf0ec;white-space:pre-wrap;overflow-wrap:anywhere}@media print{body{background:white}tr{break-inside:avoid}}',
    '</style><main><h1>销售同比复盘</h1>',f'<p>{e(periods[1])} 对比 {e(periods[0])}</p>',
    f'<p class="muted">{e(source)}</p>']
    if question:
        parts.append(f'<p><strong>问题</strong>　{e(question)}</p>')
    parts.append('<section aria-labelledby="interpretation"><h2 id="interpretation">结果解读</h2>')
    for line in c.get('insights') or explain_period(c,detail):
        parts.append(f'<p>{e(line)}</p>')
    if c.get('insight_mode'):
        parts.append(f'<p class="muted">{e(c.get("mode", ""))} · {e(c["insight_mode"])}</p>')
    parts.append('</section>')
    for warning in dict.fromkeys([*c['warnings'], *(detail['warnings'] if detail else [])]):
        parts.append(f'<p><strong>数据范围</strong>　{e(warning)}</p>')
    if detail is not None:
        dp, dn = detail['previous'], detail['current']
        specs = [('销售额','revenue','amount'), ('利润','profit','amount'), ('毛利率','margin','rate'),
                 ('占全部销售额','revenue_share','rate'), ('占全部利润','profit_share','rate'),
                 ('全表毛利率','company_margin','rate')]
        parts.extend([f'<h2>商品追问 · {e(detail["product"])}</h2>',
                      table(['指标', *periods], [(title,display(dp[k],style),display(dn[k],style))
                                             for title,k,style in specs])])
    parts.extend(['<h2>全表经营指标</h2>',table(['指标',*periods,'变动','同比'],[
        ['销售额',display(p['revenue']),display(n['revenue']),display(diff['revenue_delta']),display(diff['revenue_growth'],'rate')],
        ['利润',display(p['profit']),display(n['profit']),display(diff['profit_delta']),display(diff['profit_growth'],'rate')],
        ['毛利率',display(p['margin'],'rate'),display(n['margin'],'rate'),display(diff['margin_pp'],'pp'),'—']])])
    label='商品' if c['group_by']=='product' else '品类'
    rows=((r.name,*[display(x) for x in (r.prev_revenue,r.curr_revenue,r.delta_revenue,r.prev_profit,r.curr_profit,r.delta_profit)]) for r in c['contributions'].itertuples())
    parts.extend([f'<h2>全表按{label}分解变化</h2>',_chart(c),table([label,'上期销售额','本期销售额','销售额贡献','上期利润','本期利润','利润贡献'],rows)])
    parts.extend(['<h2>覆盖与计算依据</h2>',table(['期间','有交易记录的月份','交易行数'],[(name,'、'.join(map(str,part['months'])) or '无',part['rows']) for name,part in zip(periods,[p,n])]),
                  '<p>毛利率＝毛利合计 ÷ 销售额合计。利润列按毛利解释，金额沿用源表单位。各组金额差额相加可核对整体变动。未报告的数值显示为 —。</p>',f'<pre>{e(c["sql"])}</pre>'])
    if detail is not None:
        parts.append(f'<pre>{e(detail["sql"])}</pre>')
    return ''.join(parts)+'</main></html>'
