"""InsightFlow AI: local data analysis with inspectable calculations."""
from html import escape
from pathlib import Path
import hashlib
import pandas as pd
import plotly.express as px
import streamlit as st
from insightflow.data import load_tables
from insightflow.quality import profile
from insightflow.templates import REQUIRED, run_template
from insightflow.sql import run_query
from insightflow.report import build_report
from insightflow.explanations import explain_result
from insightflow.type_inference import _classify_column
from insightflow.questions import ask
from insightflow.period_ui import render_period_review
from insightflow.period_report import build_period_report


def clear_analyses():
    for key in ('analysis', 'sql_analysis', 'question_analysis', 'question_context',
                'question_text', 'question_error', 'report_preference', 'report_picker'):
        st.session_state.pop(key, None)


def show_explanation(lines):
    st.subheader('结果解读')
    for line in lines:
        st.markdown(f'<p>{escape(str(line))}</p>', unsafe_allow_html=True)


def remember_report_choice():
    st.session_state['report_preference'] = st.session_state['report_picker']


def example_questions(columns):
    if {'revenue', 'category'}.issubset(columns):
        return '按类别统计销售额', 'Total revenue by category'
    if 'stock_on_hand' in columns:
        return '库存数量合计', 'Total stock_on_hand'
    return '有多少行？', 'How many rows?'

st.set_page_config(page_title='InsightFlow AI V3', page_icon='📊', layout='wide')
st.title('InsightFlow AI V3')
with st.sidebar:
    st.header('Data source')
    source = st.radio('Choose data', ['Synthetic demo workbook', 'Upload CSV or XLSX'],
                      on_change=clear_analyses)
    upload = st.file_uploader('CSV or Excel workbook', type=['csv', 'xlsx']) if source.startswith('Upload') else None
    st.caption('Data stays in this local app. Limit: 20 MB, 100,000 rows, 200 columns and 20 sheets.')

if source.startswith('Upload') and upload is None:
    st.info('Upload a CSV or XLSX file, or select the synthetic demo workbook.')
    st.stop()
path = Path(__file__).parent / 'sample_data' / 'business_demo.xlsx'
try:
    content = upload.getvalue() if upload else path.read_bytes()
    filename = upload.name if upload else path.name
    tables = load_tables(content, filename)
except Exception as exc:
    st.error(f'Could not load this file: {exc}')
    st.stop()
if not tables:
    st.warning('No worksheets were found.')
    st.stop()
with st.sidebar:
    sheet = st.selectbox('Sheet / table', list(tables))
df = tables[sheet]
signature = (source, filename, hashlib.sha256(content).hexdigest(), sheet)
if st.session_state.get('source_signature') != signature:
    st.session_state['source_signature'] = signature
    clear_analyses()
if not len(df.columns):
    st.warning('This sheet is empty. Choose a sheet with column headers.')
    st.stop()
quality = profile(df)
review_tab, questions, preview, business, charts, sql_tab, report_tab = st.tabs([
    '销售复盘', '数据问答 · Ask', 'Data & quality', 'Business templates', 'Charts', 'SQL explorer', '最终报告',
])
with review_tab:
    render_period_review(df, signature, filename, sheet)
with questions:
    st.subheader('询问当前工作表 · Ask this sheet')
    st.text(f'{filename}  /  {sheet}   ·   {len(df):,} rows')
    modes = ['本地规则 · Local rules', '本机语言模型 · Local LLM']
    mode = st.radio('分析方式 · Analysis mode', modes, horizontal=True, key='question_mode')
    if mode == modes[0]:
        st.caption('支持行数、总和、平均、极值及按列分组排名。可直接输入列名。')
    else:
        st.caption('本机模型根据问题和列结构拟定计算方式，数值由本地 SQL 查询得出。')
    zh_example, en_example = example_questions(df.columns)
    question = st.text_input('问题 · Question', value=zh_example, key='question_text', max_chars=500)
    st.caption(f'English example: {en_example}')
    context = (signature, mode, question.strip())
    if st.session_state.get('question_context') != context:
        st.session_state['question_context'] = context
        st.session_state.pop('question_analysis', None)
        st.session_state.pop('question_error', None)
    submitted = st.button('分析问题 · Run question', type='primary', key='run_question',
                          disabled=not question.strip())
    first_demo = ('opened_demo' not in st.session_state and source == 'Synthetic demo workbook'
                  and sheet == 'Sales' and mode == modes[0] and question == zh_example)
    if first_demo:
        st.session_state['opened_demo'] = True
    if first_demo or submitted:
        st.session_state.pop('question_analysis', None)
        st.session_state.pop('question_error', None)
        try:
            planner = None
            if mode == modes[1]:
                from insightflow.local_model import get_planner
                planner = get_planner()
            with st.spinner('正在计算 · Running query…'):
                answer = ask(df, question.strip(), planner=planner)
            answer['formulas'] = [f"Analysis mode: {answer['mode']}", *answer['formulas']]
            st.session_state['question_analysis'] = answer
            if submitted:
                st.session_state['report_preference'] = 'Question answer'
        except Exception as exc:
            st.session_state['question_error'] = str(exc)
    if 'question_error' in st.session_state:
        st.error('本次提问未得到结果 · Question could not be answered.')
        st.text(st.session_state['question_error'])
    answer = st.session_state.get('question_analysis')
    if answer:
        show_explanation(answer['explanation'])
        if answer['result'].shape == (1, 1):
            value = answer['result'].iat[0, 0]
            st.metric('结果 · Answer', 'NULL' if pd.isna(value) else str(value))
        else:
            st.dataframe(answer['result'], hide_index=True, use_container_width=True)
        st.caption(f"分析方式 · {answer['mode']}　｜　可在「最终报告」下载本次结果与解读。")
        with st.expander('计算依据 · Executed SQL', expanded=True):
            st.code(answer['sql'], language='sql')
            for note in answer['formulas'][1:]:
                st.text(note)
with preview:
    m = st.columns(4)
    for box, label, value in zip(m, ['Rows', 'Columns', 'Missing cells', 'Duplicate rows'], [quality['rows'], quality['columns'], quality['missing_cells'], quality['duplicate_rows']]):
        box.metric(label, value)
    st.subheader('Preview')
    st.dataframe(df.head(100), use_container_width=True)
    st.subheader('Column profile')
    st.dataframe(quality['column_stats'], use_container_width=True, hide_index=True)
    st.caption('Missing means null/blank as interpreted by pandas; duplicate rows exclude the first occurrence. Data is not changed.')
with business:
    template = st.selectbox('Analysis template', [name.title() for name in REQUIRED]).lower()
    required = REQUIRED[template]
    st.write('Map the required fields to the current sheet. Numbers must be parseable as numbers.')
    mapping = {}
    for field in required + (['date'] if template == 'sales' else []):
        options = ['— not mapped —'] + list(df.columns)
        default = options.index(field) if field in options else 0
        value = st.selectbox(field + (' (optional)' if field == 'date' else ''), options, index=default, key=f'map_{sheet}_{template}_{field}')
        if value != options[0]:
            mapping[field] = value
    if st.button('Run analysis', type='primary'):
        try:
            st.session_state['analysis'] = run_template(df, template, mapping)
            st.session_state['report_preference'] = 'Business template'
        except Exception as exc:
            st.session_state.pop('analysis', None)
            st.error(str(exc))
    analysis = st.session_state.get('analysis')
    if analysis:
        st.subheader('Last run: ' + analysis['title'] + ' results')
        st.caption('These results reflect the mapping used when you last clicked Run analysis.')
        show_explanation(analysis['explanation'])
        st.dataframe(analysis['result'], use_container_width=True, hide_index=True)
        st.markdown('**Calculation basis**')
        for formula in analysis['formulas']:
            st.write('• ' + formula)
        st.code(analysis['sql'], language='sql')
        st.caption('Results display at most 1,000 rows. Validate field meaning and units before use.')
with charts:
    st.subheader('Explore the current data')
    numeric = list(df.select_dtypes(include='number').columns)
    if not numeric or df.empty:
        st.info('A non-empty numeric column is needed for charts.')
    else:
        x = st.selectbox('X axis', list(df.columns))
        y = st.selectbox('Y axis (numeric)', numeric)
        inferred = _classify_column(df[x], df[x].dropna())
        recommended = 'Line' if inferred == 'datetime' else ('Scatter' if x in numeric else 'Bar')
        st.caption(f'Recommended: {recommended} based on the X-axis type; choose another if appropriate.')
        choices = ['Bar', 'Line', 'Scatter']
        chart_type = st.radio('Chart type', choices, index=choices.index(recommended), horizontal=True)
        chart_data = df.head(1000)
        if chart_type == 'Bar':
            fig = px.bar(chart_data, x=x, y=y)
        elif chart_type == 'Line':
            fig = px.line(chart_data, x=x, y=y)
        else:
            fig = px.scatter(chart_data, x=x, y=y)
        fig.update_layout(template='plotly_white', margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)
        st.caption('Charts show the first 1,000 source rows, without aggregation. Sort or aggregate using SQL for other views.')
with sql_tab:
    st.write('Query the selected sheet as `data`. Only one SELECT is allowed; external file and network access are disabled.')
    query = st.text_area('SQL', 'SELECT * FROM data LIMIT 10', height=120)
    if query != st.session_state.get('sql_analysis', {}).get('sql'):
        st.session_state.pop('sql_analysis', None)
    if st.button('Run SQL'):
        try:
            result = run_query({'data': df}, query)
            analysis = {'title': 'SQL query', 'sql': query, 'result': result,
                        'formulas': ['Results are produced by the SQL query shown below.']}
            analysis['explanation'] = explain_result(analysis)
            st.session_state['sql_analysis'] = analysis
            st.session_state['report_preference'] = 'SQL query'
        except Exception as exc:
            st.session_state.pop('sql_analysis', None)
            st.error(f'Query failed: {exc}')
    if st.session_state.get('sql_analysis'):
        show_explanation(st.session_state['sql_analysis']['explanation'])
        st.dataframe(st.session_state['sql_analysis']['result'], use_container_width=True, hide_index=True)
        st.caption('Output capped at 1,000 rows; expensive queries can still consume resources.')
with report_tab:
    reports = {'销售复盘': 'review_comparison', 'Question answer': 'question_analysis', 'Business template': 'analysis',
               'SQL query': 'sql_analysis'}
    options = [label for label, key in reports.items() if st.session_state.get(key)]
    if not options:
        st.info('Ask a question, run a business template, or run a SQL query to create a report.')
    else:
        preferred = st.session_state.get('report_preference')
        if preferred not in options:
            if preferred:
                st.caption('上次所选分析没有可导出的当前结果。下方列出这张工作表上已有的其他结果。')
            preferred = options[0]
        st.session_state['report_picker'] = preferred
        kind = st.radio('Report analysis', options, horizontal=True, key='report_picker',
                        on_change=remember_report_choice)
        analysis = st.session_state[reports[kind]]
        if kind == '销售复盘':
            question_used = st.session_state['review_question_used']
            st.text(question_used)
            show_explanation(analysis['insights'])
            html = build_period_report(analysis, st.session_state.get('review_detail'),
                                       source=f'{filename} / {sheet}', question=question_used)
            st.download_button('下载销售复盘报告', html, file_name='insightflow-sales-review.html',
                               mime='text/html', key='report_review_download')
        else:
            html = build_report(filename, sheet, quality, analysis)
            ready = f"Ready: {analysis['title']} · {len(analysis['result'])} result rows"
            if kind == 'Question answer':
                st.text(ready)
            else:
                st.write(ready)
            show_explanation(analysis['explanation'])
            st.download_button('Download HTML report', html, file_name='insightflow-report.html', mime='text/html')
