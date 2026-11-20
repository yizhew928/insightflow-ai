"""Run the actual Streamlit form, on-device planner and evidence selector over the synthetic workbook."""
import argparse
import csv
from datetime import date
from decimal import Decimal as D
from html import escape
import hashlib
import http.client
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from streamlit.testing.v1 import AppTest
from streamlit.runtime.media_file_storage import MediaFileKind
from streamlit.runtime.memory_media_file_storage import MemoryMediaFileStorage
from insightflow.period_report import build_period_report
from insightflow.data import load_tables
from insightflow.quality import profile
from insightflow.report import build_report


def oracle(rows, year, months, product=None):
    chosen = [r for r in rows if int(r['date'][:4]) == year and int(r['date'][5:7]) in months and
              (product is None or r['product'] == product)]
    revenue, profit = (sum(D(r[col]) for r in chosen) for col in ('revenue','profit'))
    return {'revenue':revenue, 'profit':profit, 'margin':profit/revenue, 'rows':len(chosen)}


def verify(window, ref):
    for key, value in ref.items():
        assert math.isclose(float(window[key]), float(value), rel_tol=1e-10, abs_tol=1e-10), (key, window, ref)


def check_group_rows(table, rows, yr, months, dim):
    for entry in table.itertuples():
        subset = [r for r in rows if r[dim] == entry.name]
        p,n = (oracle(subset, y, months) for y in [yr-1, yr])
        for metric in ['revenue', 'profit']:
            assert math.isclose(getattr(entry,'delta_'+metric), float(n[metric]-p[metric]))


def verify_download(app, label, filename, html):
    element = next(elem for elem in app.get('download_button') if elem.proto.label == label)
    storage = MemoryMediaFileStorage('/mock/media')
    identity = storage.load_and_get_id(html.encode(),'text/html',MediaFileKind.DOWNLOADABLE,filename=filename)
    assert identity in element.proto.url, 'Export must match actual download button'


def verify_export(app, comparison, detail, question):
    html = build_period_report(comparison, detail, source='business_demo.xlsx / Sales', question=question)
    assert '结果解读' in html and all(escape(line) in html for line in comparison['insights'])
    for label in ('下载本次复盘 HTML', '下载销售复盘报告'):
        verify_download(app, label, 'insightflow-sales-review.html', html)
    return html


def verify_category_question(app, rows):
    mode = app.radio(key='question_mode')
    mode.set_value(mode.options[1]).run()
    app.text_input(key='question_text').set_value('按类别统计销售额')
    app.button(key='run_question').click().run()
    assert not app.exception and not app.error, app.error
    assert app.radio(key='report_picker').value == 'Question answer'
    answer = app.session_state['question_analysis']
    assert answer['mode'] == 'Language model'
    expected = {}
    for row in rows:
        key = row['category']
        expected[key] = expected.get(key, 0) + D(row['revenue'])
    assert answer['result'].set_index('group_key')['value'].to_dict() == expected
    lines = answer['explanation']
    assert any('Accessories' in line and '4560' in line.replace(',', '') for line in lines), lines
    name = 'business_demo.xlsx'
    frame = load_tables((ROOT/'sample_data'/name).read_bytes(), name)['Sales']
    html = build_report(name, 'Sales', profile(frame), answer)
    assert all(escape(line) in html for line in lines)
    verify_download(app, 'Download HTML report', 'insightflow-report.html', html)
    print('PASS 本机模型分品类查询、结果解读与最终报告', lines, flush=True)
    return html, lines


def run(save):
    conn = http.client.HTTPConnection('127.0.0.1',18089,timeout=5)
    try:
        conn.request('GET','/v1/models')
        model = json.load(conn.getresponse())['data'][0]['id']
        assert model == 'insightflow-qwen2.5-7b', model
    finally:
        conn.close()
    with (ROOT/'sample_data/sales.csv').open() as f:
        rows = list(csv.DictReader(f))
    app = AppTest.from_file(str(ROOT/'app.py'),default_timeout=150).run()
    assert not app.exception, app.exception
    assert app.radio(key='review_mode').value == '本机 AI'
    submit = lambda: next(b for b in app.button if b.label == '分析问题或追问').click().run()
    records = []
    if date.today().year == 2026:
        first = '今年上半年比去年同期表现怎么样，哪些商品贡献了变化？'
    else:
        first = '2026 年上半年比去年同期表现怎么样，哪些商品贡献了变化？'
    cases = [(first, 'H1','product',None,range(1,7)),
             ('只看 Backpack，它的毛利率怎么样？', 'H1','product','Backpack',range(1,7)),
             ('只看 Backpack，毛利率比去年同期怎么样？', 'H1','product','Backpack',range(1,7)),
             ('比较 2026 年第一季度与去年同期，按品类分析销售额和利润的变化', 'Q1','category',None,range(1,4))]
    pages = {}
    for question, period, dimension, product, months in cases:
        started=time.monotonic()
        app.text_input(key='review_question').set_value(question)
        submit()
        assert not app.exception, app.exception
        assert not app.session_state['review_error'], app.session_state['review_error']
        comp=app.session_state['review_comparison']; det=app.session_state['review_detail']
        assert (comp['year'],comp['period'],comp['group_by'])==(2026,period,dimension)
        assert comp['mode']=='本机 AI' and 'AI' in comp['insight_mode'], comp['insight_mode']
        assert len(comp['insights'])>=2
        if question == first:
            assert any('负向贡献' in line for line in comp['insights'])
            assert any('正向贡献' in line for line in comp['insights'])
        verify(comp['previous'],oracle(rows,2025,months)); verify(comp['current'],oracle(rows,2026,months))
        check_group_rows(comp['contributions'],rows,2026,months,dimension)
        for m in ('revenue','profit'):
            assert math.isclose(comp['contributions']['delta_'+m].sum(),comp['changes'][m+'_delta'])
        if product:
            assert det['product']==product
            for side,year in [('previous',2025),('current',2026)]:
                expected=oracle(rows,year,months,product)
                verify(det[side],expected)
                for m in ('revenue','profit'):
                    assert math.isclose(det[side][m+'_share'],float(expected[m]/oracle(rows,year,months)[m]))
        else:
            assert det is None
        html=verify_export(app,comp,det,question)
        if period=='H1':
            pages.setdefault('product-review.html' if product else 'sales-review.html',html)
        records.append({'question':question,'mode':comp['mode'],'interpretation':comp['insight_mode'],
                        'context':app.session_state['review_context'],'seconds':round(time.monotonic()-started,2),
                        'previous':comp['previous'],'current':comp['current'],'changes':comp['changes'],
                        'detail':({'product':product,'previous':det['previous'],'current':det['current']} if product else None),
                        'contributions':comp['contributions'].to_dict('records'),'insights':comp['insights'],
                        'download_sha256':hashlib.sha256(html.encode()).hexdigest()})
        print('PASS',question,comp['insights'],flush=True)
    app.text_input(key='review_question').set_value('只看华东地区的销售额')
    submit()
    assert app.session_state['review_error'] and 'review_comparison' not in app.session_state
    print('PASS unsupported regional filter declined',flush=True)
    pages['category-query.html'], category_lines = verify_category_question(app, rows)
    next(s for s in app.selectbox if s.label=='Sheet / table').select('Inventory').run()
    assert 'review_context' not in app.session_state and not app.exception
    print('PASS switching sheets clears review context',flush=True)
    if save:
        for name,html in pages.items():
            (ROOT/'docs'/name).write_text(html,encoding='utf-8')
        (ROOT/'run/live-v3.json').write_text(json.dumps({'model':model,'data':'synthetic','answers':records,
            'category_question_explanation':category_lines,
            'rejection_and_context_reset':True},indent=2,ensure_ascii=False)+'\n',encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    run(parser.parse_args().write)
