from html import escape
from pathlib import Path

import pandas as pd
import pytest

from insightflow import period_insights
from insightflow.period_analysis import compare_sales, drilldown
from insightflow.period_report import build_period_report

DEMO = Path(__file__).resolve().parents[1] / 'sample_data/sales.csv'


def test_driver_selection_requires_verified_evidence_in_both_directions(monkeypatch):
    result = compare_sales(pd.read_csv(DEMO), 2026, 'H1')

    def choose(request):
        fields = request['response_format']['schema']['properties']
        assert set(fields['priority']['enum']) == {'revenue_down', 'profit_down'}
        assert set(fields['secondary']['enum']) == {'revenue_up', 'profit_up'}
        return {'priority': 'revenue_down', 'secondary': 'revenue_up'}

    monkeypatch.setattr(period_insights, '_post', choose)
    findings = period_insights.explain_period(result, question='哪些商品贡献了变化？', use_model=True)
    assert 'Backpack' in findings[1] and '240' in findings[1]
    assert 'Desk Lamp' in findings[2] and '120' in findings[2]
    monkeypatch.setattr(period_insights, '_post', lambda _: {'priority': 'unsupported', 'secondary': 'profit_up'})
    with pytest.raises(ValueError, match='可核验'):
        period_insights.explain_period(result, question='哪些商品贡献了变化？', use_model=True)


def test_export_escapes_data_retains_product_warning_and_scoped_metrics():
    data = pd.read_csv(DEMO)
    name = 'New <sample> & "item"'
    data.loc[(data['date'] >= '2026') & (data['product'] == 'Backpack'), 'product'] = name
    comparison = compare_sales(data, 2026, 'H1')
    detail = drilldown(data, 2026, 'H1', name)
    comparison['mode'], comparison['insight_mode'] = '手动选择', '计算摘要'
    html = build_period_report(comparison, detail, source='<ledger>', question='<question>')
    assert name not in html and '<question>' not in html and '<ledger>' not in html
    assert escape(name) in html and '&lt;question&gt;' in html
    assert '所选商品无记录' in html and '计算摘要' in html
    assert html.index('商品追问') < html.index('全表经营指标')
    assert '36.70%' in html and '33.40%' in html and '49.44%' in html


def test_period_text_explains_margin_and_opposing_movements_in_same_report():
    data = pd.read_csv(DEMO)
    result = compare_sales(data, 2026, 'H1')
    facts = period_insights.explain_period(result)
    assert all(term in facts[0] for term in ('2026 年上半年', '2025 年上半年', '4.85%', '基本持平'))
    assert '合计减少 500' in facts[1] and 'Backpack' in facts[1]
    assert '合计增加 200' in facts[2] and 'Desk Lamp' in facts[2]
    result['insights'] = facts
    report = build_period_report(result)
    assert report.count('>结果解读<') == 1
    assert all(f'<p>{escape(fact)}</p>' in report for fact in facts)
    detail = drilldown(data, 2026, 'H1', 'Backpack')
    product_facts = period_insights.explain_period(result, detail)
    assert '毛利率两期均为 45.00%' in product_facts[0] and '减少 240' in product_facts[0]
    assert '低于整体 4.44 个百分点' in product_facts[1] and '36.70%' in product_facts[2]


def test_missing_window_names_actual_period_instead_of_interpreting_a_decline():
    data = pd.read_csv(DEMO)
    result = compare_sales(data, 2025, 'H1')
    facts = period_insights.explain_period(result)
    assert len(facts) == 1 and '2024 年上半年没有交易记录' in facts[0]
    assert '减少' not in facts[0]
