"""Sales review workspace: an explicit period context shared by comparisons and follow-ups."""
from datetime import date
from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .period_analysis import compare_sales, drilldown
from .period_insights import PERIOD_NAMES, explain_period
from .period_intent import resolve_period_question
from .period_report import build_period_report


DIMENSION_NAMES = {'product': '商品', 'category': '品类'}
FIELD_NAMES = {
    'date': ('日期', '订单日期', '销售日期'),
    'revenue': ('销售额', '营收', '销售收入'),
    'profit': ('利润', '毛利', '毛利润'),
    'product': ('商品', '产品', '商品名称', '产品名称'),
    'category': ('品类', '类别', '商品类别', '产品类别'),
}


def _fields(frame):
    """Rename unambiguous common headers; retain the original data for legacy tabs."""
    renames = {}
    for key, aliases in FIELD_NAMES.items():
        if key in frame.columns:
            continue
        matches = [col for col in frame.columns if str(col).strip().casefold() in (key, *aliases)]
        if len(matches) == 1:
            renames[matches[0]] = key
    return frame.rename(columns=renames)


def _number(value, signed=False):
    if pd.isna(value):
        return '—'
    return format(value, '+,.2f' if signed else ',.2f').rstrip('0').rstrip('.')


def _pct(value, signed=False):
    if pd.isna(value):
        return '—'
    return format(value, '+.1%' if signed else '.1%')


def _kpis(comparison):
    previous, current, changes = comparison['previous'], comparison['current'], comparison['changes']
    columns = st.columns(3)
    for box, item, label in zip(columns, ('revenue', 'profit'), ('销售额', '利润')):
        with box:
            change = changes[item + '_growth']
            st.metric(label, _number(current[item]), None if pd.isna(change) else _pct(change, True))
            st.caption(f"上年同期 {_number(previous[item])}　·　差额 {_number(changes[item + '_delta'], True)}")
    with columns[2]:
        gap = changes['margin_pp']
        st.metric('毛利率', _pct(current['margin']), None if pd.isna(gap) else f'{gap:+.2f} 个百分点')
        st.caption(f"上年同期 {_pct(previous['margin'])}　·　利润合计 ÷ 销售额合计")


def _contributions(comparison):
    table = comparison['contributions']
    group_name = DIMENSION_NAMES[comparison['group_by']]
    st.subheader(f'哪些{group_name}贡献了全表的变化')
    metric = st.radio('查看贡献指标', ['销售额', '利润'], horizontal=True, key='review_chart_metric')
    field = 'delta_revenue' if metric == '销售额' else 'delta_profit'
    comparable = table.dropna(subset=[field]).copy()
    if len(comparable):
        plotted = comparable.loc[comparable[field].abs().nlargest(15).index].sort_values(field)
        series = plotted[field].astype(float)
        names = [escape(str(value)) for value in plotted['name']]
        # Use a numeric y-axis so identical-looking labels never merge categories.
        fig = go.Figure(go.Bar(
            x=series, y=list(range(len(plotted))), orientation='h', customdata=names,
            marker_color=['#157861' if value >= 0 else '#b95435' for value in series],
            hovertemplate='%{customdata}<br>同比差额 %{x:+,.2f}<extra></extra>',
        ))
        fig.update_layout(height=min(550, max(260, 33*len(plotted)+70)), showlegend=False,
                          plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=4,r=24,t=8,b=6),
                          xaxis=dict(title=f'{metric}同比差额', zeroline=True, zerolinecolor='#62757e',
                                     gridcolor='rgba(120,140,150,.18)', rangemode='tozero'),
                          yaxis=dict(tickmode='array', tickvals=list(range(len(plotted))),
                                     ticktext=names, automargin=True))
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        if len(comparable) > len(plotted):
            st.caption('图中展示绝对差额最大的 15 项；下表包含全部分组。')
    labels = {'name':group_name, 'prev_revenue':'上期销售额', 'curr_revenue':'本期销售额',
              'delta_revenue':'销售额差额', 'prev_profit':'上期利润', 'curr_profit':'本期利润',
              'delta_profit':'利润差额'}
    display = table[list(labels)].sort_values(field, ascending=False, na_position='last').rename(columns=labels)
    st.dataframe(display, use_container_width=True, hide_index=True)


def _product_kpis(detail):
    prior, current = detail['previous'], detail['current']
    st.subheader('商品追问')
    st.text(str(st.session_state['review_context']['product']))
    keys = ('revenue', 'profit', 'margin', 'revenue_share', 'profit_share', 'company_margin')
    labels = ('销售额', '利润', '商品毛利率', '占全表销售额', '占全表利润', '全表毛利率')
    rows = []
    for i, (key, label) in enumerate(zip(keys, labels)):
        fmt = _number if i < 2 else _pct
        rows.append({'指标':label, '上年同期':fmt(prior.get(key)), '本期':fmt(current.get(key))})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def _commit_answer(frame, req, question, source_mode, use_model):
    comparison = compare_sales(frame, req['year'], req['period'], req['group_by'])
    detail = drilldown(frame, req['year'], req['period'], req['product']) if req['action'] == 'product' else None
    try:
        findings = explain_period(comparison, detail, question=question, use_model=use_model)
        insight_mode = ('本机 AI 选取要点，数值由 SQL 计算'
                        if use_model and len(findings) > 1 else '计算摘要')
    except (ValueError, RuntimeError, OSError) as exc:
        if not use_model:
            raise
        findings = explain_period(comparison, detail, question=question, use_model=False)
        insight_mode = f'模型未返回可用要点，已展示计算摘要。{exc}'
    comparison['insights'] = findings
    comparison['insight_mode'] = insight_mode
    comparison['mode'] = source_mode
    st.session_state.update(review_context=req, review_detail=detail, review_comparison=comparison,
                            review_source_mode=source_mode, review_question_used=question,
                            review_error=None)
    if source_mode != '预设同期比较':
        st.session_state['report_preference'] = '销售复盘'


def _show_failure(exc):
    st.session_state['review_error'] = str(exc)
    st.session_state.pop('review_comparison', None)
    st.session_state.pop('review_detail', None)


def _default_window(frame):
    dates = pd.to_datetime(frame['date'], errors='coerce').dropna()
    if dates.empty:
        return date.today().year, 'H1'
    latest = dates.max()
    return int(latest.year), 'H1' if latest.month <= 6 else 'H2'


def render_period_review(frame, signature, filename, sheet):
    if st.session_state.get('review_signature') != signature:
        for key in list(st.session_state):
            if key.startswith('review_'):
                del st.session_state[key]
        st.session_state['review_signature'] = signature
    frame = _fields(frame)
    dimensions = [group for group in DIMENSION_NAMES if group in frame]
    st.subheader('销售同期复盘')
    if not dimensions or not {'date', 'revenue', 'profit'}.issubset(frame):
        st.info('请选择 Sales 或上传销售明细表。复盘需要日期、销售额、利润，以及商品或品类列。')
        return
    products = sorted(set(frame['product'].dropna().astype(str))) if 'product' in frame else []
    if 'review_initialized' not in st.session_state:
        st.session_state['review_initialized'] = True
        try:
            year, period = _default_window(frame)
            req = dict(action='compare', year=year, period=period, group_by=dimensions[0], product=None)
            _commit_answer(frame, req, f'{year} 年{PERIOD_NAMES[period]}与上年同期比较', '预设同期比较', False)
        except (ValueError, RuntimeError, TypeError, OverflowError) as exc:
            _show_failure(exc)

    overview = st.container()
    with st.form('review_ask_form'):
        question = st.text_input('提问或继续追问', '今年上半年比去年同期表现怎么样，哪些商品贡献了变化？',
                                 key='review_question', max_chars=500)
        submit = st.form_submit_button('分析问题或追问', type='primary')
    selected_mode = st.radio('复盘问答方式', ['本机 AI', '本地规则'], horizontal=True, key='review_mode')
    context = st.session_state.get('review_context')
    if submit:
        try:
            if not question.strip():
                raise ValueError('请输入希望比较的期间或想追问的商品。')
            use_model = selected_mode == '本机 AI'
            with st.spinner('解读问题并核对同期数据…'):
                req = resolve_period_question(question, context, products, today=date.today(), use_model=use_model)
                if req['group_by'] not in dimensions:
                    raise ValueError(f"当前工作表缺少{DIMENSION_NAMES.get(req['group_by'], req['group_by'])}列。")
                _commit_answer(frame, req, question, '本机 AI' if use_model else '本地规则', use_model)
        except (ValueError, RuntimeError, TypeError, OSError, OverflowError) as exc:
            _show_failure(exc)
    context = st.session_state.get('review_context') or {}
    with st.expander('手动选择期间、分组或商品'):
        with st.form('review_manual_form'):
            left, middle, right = st.columns(3)
            year = left.number_input('本期年份', 1901, 2200, min(2200,max(1901,context.get('year',date.today().year))), key='review_year')
            period_label = middle.selectbox('比较期间', list(PERIOD_NAMES.values()),
                                      index=list(PERIOD_NAMES).index(context.get('period','H1')), key='review_period')
            period = next(code for code, label in PERIOD_NAMES.items() if label == period_label)
            group_label = right.selectbox('贡献分组', [DIMENSION_NAMES[key] for key in dimensions],
                                    index=dimensions.index(context.get('group_by')) if context.get('group_by') in dimensions else 0,
                                    key='review_group')
            group = next(code for code in dimensions if DIMENSION_NAMES[code] == group_label)
            # Keep the all-products option distinct even when a product has that name.
            all_products = '全部商品'
            while all_products in products:
                all_products += '（汇总）'
            product = st.selectbox('同时查看商品', [all_products, *products], key='review_product') if products else None
            if product == all_products:
                product = None
            apply = st.form_submit_button('应用选择')
        if apply:
            req = dict(action='product' if product else 'compare',year=int(year),period=period,
                       group_by=group,product=product)
            try:
                _commit_answer(frame, req, f'{year} 年{PERIOD_NAMES[period]}同期复盘', '手动选择', False)
            except (ValueError, RuntimeError, TypeError, OverflowError) as exc:
                _show_failure(exc)
    if st.session_state.get('review_error'):
        st.warning('本次分析未完成。')
        st.text(st.session_state['review_error'])
        return
    comparison = st.session_state.get('review_comparison')
    if comparison is None:
        return
    detail = st.session_state['review_detail']
    with overview:
        st.markdown(
            '<div style="color:#41635a;font-size:0.94rem;font-weight:600;margin:.1rem 0 .9rem">'
            f"{escape(sheet)}　·　本期 {escape(comparison['current_label'])}　｜　"
            f"同期 {escape(comparison['previous_label'])}</div>", unsafe_allow_html=True)
        for warning in dict.fromkeys([*comparison['warnings'], *(detail['warnings'] if detail else [])]):
            st.warning(str(warning))
        if detail:
            st.markdown('<strong>商品指标 · ' + escape(str(detail['product'])) + '</strong>',
                        unsafe_allow_html=True)
        _kpis(detail if detail else comparison)
        st.subheader('结果解读')
        paragraphs = ''.join(f'<p style="margin:.25rem 0 .55rem">{escape(str(line))}</p>'
                             for line in comparison['insights'])
        st.markdown(
            '<section style="border-left:4px solid #157861;padding:.45rem 1rem;margin:.4rem 0">'
            + paragraphs + '</section>', unsafe_allow_html=True)
        st.markdown(
            '<small>' + escape(comparison['insight_mode']) + '　｜　'
            + escape(st.session_state['review_source_mode']) + '：'
            + escape(st.session_state['review_question_used']) + '</small>', unsafe_allow_html=True)
    if detail:
        _product_kpis(detail)
    elif products:
        candidate = 'Backpack' if 'Backpack' in products else products[0]
        st.markdown('<small>可继续追问：“只看 ' + escape(candidate) + '，它的毛利率怎么样？”</small>',
                    unsafe_allow_html=True)
    _contributions(comparison)
    with st.expander('查看覆盖月份与计算 SQL'):
        st.caption('上传表中的利润列应为毛利，即销售额扣除销售成本；金额须使用同一单位。')
        for label, side in (('本期', 'current'), ('上年同期', 'previous')):
            period = comparison[side]
            st.text(f"{label}：{period['rows']} 行 · 有记录的月份：{', '.join(period['months']) or '无'}")
        st.code(comparison['sql'], language='sql')
        if detail:
            st.code(detail['sql'], language='sql')
    html = build_period_report(comparison, detail, source=f'{filename} / {sheet}',
                               question=st.session_state['review_question_used'])
    st.download_button('下载本次复盘 HTML', html, file_name='insightflow-sales-review.html',
                       mime='text/html', key='review_download')
