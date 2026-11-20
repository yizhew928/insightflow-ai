import json
from datetime import date

import pytest

from insightflow import period_intent as subject

TODAY = date(2026, 11, 20)
PRODUCTS = ['Desk', 'Desk Lamp', 'Backpack', 'Notebook', 'Travel Mug']
CONTEXT = {'action': 'compare', 'year': 2026, 'period': 'H1', 'group_by': 'product', 'product': None}


def resolve(question, context=CONTEXT, model=False):
    return subject.resolve_period_question(question, context, PRODUCTS, today=TODAY, use_model=model)


def test_full_live_request_preserves_schema_and_does_not_send_catalog(monkeypatch):
    sent = []
    def stub(payload):
        sent.append(json.loads(payload['messages'][-1]['content']))
        return {'route': 'products'}
    monkeypatch.setattr(subject.local_model, '_post', stub)
    plan = resolve('今年上半年比去年同期表现怎么样，哪些商品贡献了变化？', None, True)
    assert plan == {**CONTEXT, 'mode': '本机语言模型'}
    assert len(sent) == 1
    assert all(name not in json.dumps(sent) for name in PRODUCTS)


def test_inherit_half_year_and_switch_product_or_dimension():
    first = resolve('只看 Backpack，它的毛利率怎么样？')
    assert (first['year'], first['period'], first['product']) == (2026,'H1','Backpack')
    assert resolve('它的利润贡献呢？', first)['product'] == 'Backpack'
    next_item = resolve('只看 Desk Lamp，它的毛利率怎么样？', first)
    assert next_item['product'] == 'Desk Lamp'
    next_window = resolve('比较 2025 年第四季度各品类的贡献', first)
    assert (next_window['action'], next_window['year'], next_window['period'], next_window['group_by'],
            next_window['product']) == ('compare',2025,'Q4','category',None)


@pytest.mark.parametrize('question,year,period', [
    ('Compare 2025 Q1 vs 2024 Q1 by product',2025,'Q1'),
    ('2025年下半年和上年同期销售额如何？',2025,'H2'),
    ('请按商品对比去年全年销售表现',2025,'FY'),
    ('2024年相比2023年各品类的利润表现',2024,'FY'),
    ('How did revenue compare in the second half of 2025?',2025,'H2'),
])
def test_resolve_dates(question, year, period):
    answer = resolve(question, None)
    assert (answer['year'], answer['period']) == (year,period)


@pytest.mark.parametrize('question,context', [
    ('只看不存在的商品，它的毛利率呢？',CONTEXT),
    ('它的表现怎么样？',CONTEXT),
    ('只看 Backpack，它的毛利率怎么样？',None),
    ('只看 Backpack、Desk Lamp，销售额是多少？',CONTEXT),
    ('只看 Backpack 和 Other，销量多少？',CONTEXT),
    ('今年上半年只看华东地区的表现',None),
    ('比较2026年第一季度和2025年第四季度',None),
    ('对比2023年与2026年全年销售额',None),
    ('对比2026年与2023年全年销售额',None),
    ('2026年2月到3月的销售表现',CONTEXT),
    ('Show year to date YTD sales',CONTEXT),
    ('Compare FY 2022 and 1799',CONTEXT),
    ('Compare 2026 Q5 profit',CONTEXT),
])
def test_unsupported_before_dispatch(monkeypatch, question, context):
    monkeypatch.setattr(subject.local_model, '_post', lambda _: pytest.fail('Unexpected model call'))
    with pytest.raises(ValueError):
        resolve(question,context,True)


def test_model_cannot_rewrite_explicit_scope(monkeypatch):
    monkeypatch.setattr(subject.local_model, '_post', lambda _: {'route': 'categories'})
    with pytest.raises(ValueError,match='映射'):
        resolve('比较2026年上半年各商品贡献',None,True)
    monkeypatch.setattr(subject.local_model, '_post', lambda _: {'route': 'products','year':2020})
    with pytest.raises(ValueError,match='有效'):
        resolve('比较2026年上半年各商品贡献',None,True)


def test_failed_model_is_not_replaced_with_rule_result(monkeypatch):
    def fail(_):
        raise ValueError('本机模型不可用')
    monkeypatch.setattr(subject.local_model, '_post', fail)
    with pytest.raises(ValueError, match='不可用'):
        resolve('比较2026年上半年各商品贡献', None, True)


@pytest.mark.parametrize('question', [
    '今年上半年黄金会员销售表现', 'How did profit compare for UnlistedWidget in 2026 Q2?',
    '比较本年上半年红色系列利润', 'Compare 2026 Q1 between Europe and Africa',
])
def test_rules_do_not_drop_unknown_scope(question):
    with pytest.raises(ValueError):
        resolve(question)


@pytest.mark.parametrize('model', [False, True])
@pytest.mark.parametrize('question,context,route,year,period', [
    ('只看 Backpack，毛利率比去年同期怎么样？', CONTEXT, 'one_product', 2026, 'H1'),
    ('只看 Backpack，毛利率比去年同期怎么样？', {**CONTEXT, 'year': 2023, 'period': 'Q3'},
     'one_product', 2023, 'Q3'),
    ('Compare 2026H1 to 2025H1 sales by product', None, 'products', 2026, 'H1'),
    ('比较2026Q1和2025Q1的销售额', None, 'products', 2026, 'Q1'),
    ('比较去年上半年的销售额', CONTEXT, 'products', 2025, 'H1'),
    ('Compare 2024Q2 revenue to the same period last year', CONTEXT, 'products', 2024, 'Q2'),
])
def test_prior_comparison_and_compact_dates(monkeypatch, model, question, context, route, year, period):
    calls = []
    def stub(payload):
        calls.append(payload)
        return {'route': route}
    monkeypatch.setattr(subject.local_model, '_post', stub)
    plan = resolve(question, context, model)
    assert (plan['year'], plan['period']) == (year, period)
    assert len(calls) == int(model)


@pytest.mark.parametrize('question', ['比较2026Q5与2025Q5的销售额', '比较2026H1与2025H2的销售额'])
def test_invalid_compact_comparisons_refuse_before_model(monkeypatch, question):
    monkeypatch.setattr(subject.local_model, '_post', lambda _: pytest.fail('Unexpected model call'))
    with pytest.raises(ValueError):
        resolve(question, CONTEXT, True)
