from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def open_app():
    app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=45).run()
    assert not app.exception
    return app


def apply_button(app, label):
    next(b for b in app.button if b.label == label).click().run()
    assert not app.exception


def submit_question(app, text):
    app.text_input(key='review_question').set_value(text)
    apply_button(app, '分析问题或追问')


def has_review_export(app):
    return any(b.proto.label == '下载本次复盘 HTML' for b in app.get('download_button'))


def test_default_then_followup_keeps_period_and_clears_on_new_sheet():
    app = open_app()
    assert app.tabs[0].label == '销售复盘'
    assert app.radio(key='review_mode').value == '本机 AI'
    assert app.session_state['review_source_mode'] == '预设同期比较'
    before = app.session_state['review_comparison']
    assert before['year'] == 2026 and before['period'] == 'H1' and has_review_export(app)
    assert sum(before['contributions'].delta_revenue) == before['changes']['revenue_delta']
    app.radio(key='review_mode').set_value('本地规则').run()
    submit_question(app, '2026年第一季度销售额与上年同期相比怎么样？')
    assert app.session_state['review_context']['period'] == 'Q1'
    submit_question(app, '只看 Backpack，它的毛利率怎么样？')
    detail = app.session_state['review_detail']
    assert detail['product'] == 'Backpack' and detail['period'] == 'Q1'
    csv = pd.read_csv(ROOT/'sample_data/sales.csv')
    rows = csv[(csv['date'] >= '2026-01-01') & (csv['date'] < '2026-04-01') & (csv['product'] == 'Backpack')]
    assert detail['current']['margin'] == pytest.approx(rows.profit.sum()/rows.revenue.sum())
    assert has_review_export(app)
    submit_question(app, '只看不存在的商品，预测明年需求')
    assert app.session_state['review_error'] and 'review_detail' not in app.session_state
    assert not has_review_export(app)
    next(s for s in app.selectbox if s.label=='Sheet / table').select('Inventory').run()
    assert not app.exception and 'review_context' not in app.session_state and not has_review_export(app)


def test_manual_period_and_category_and_missing_baseline():
    app = open_app()
    app.selectbox(key='review_group').set_value('品类')
    app.selectbox(key='review_period').set_value('第一季度')
    apply_button(app, '应用选择')
    assert app.session_state['review_context']['period'] == 'Q1'
    assert app.session_state['review_comparison']['group_by'] == 'category'
    app.number_input(key='review_year').set_value(2025)
    apply_button(app, '应用选择')
    comp = app.session_state['review_comparison']
    assert comp['previous']['revenue'] is None and comp['changes']['revenue_delta'] is None
    assert app.warning
