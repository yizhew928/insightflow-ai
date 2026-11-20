from pathlib import Path
import pandas as pd
import pytest

from insightflow.questions import ask, UnsupportedQuestion


@pytest.fixture
def sales():
    return pd.read_csv(Path(__file__).resolve().parents[1] / 'sample_data' / 'sales.csv')


@pytest.mark.parametrize(('question', 'operation'), [
    ('总销售额是多少？', 'sum'), ('What is the average revenue?', 'mean'),
    ('最高销售额', 'max'), ('最低销售额', 'min'),
])
def test_single_metric(sales, question, operation):
    answer = ask(sales, question)
    assert answer['mode'] == 'Local rules'
    assert answer['result'].iat[0, 0] == pytest.approx(getattr(sales.revenue, operation)())


@pytest.mark.parametrize(('question', 'column', 'size'), [
    ('按类别统计销售额', 'category', 100), ('按类别汇总销售额', 'category', 100),
    ('Total revenue by category', 'category', 100),
    ('Top 3 products by revenue', 'product', 3), ('按销售额排名前3个产品', 'product', 3),
])
def test_grouping(sales, question, column, size):
    expected = (sales.groupby(column)['revenue'].sum().rename('value').reset_index()
                .sort_values(['value', column], ascending=[False, True]).head(size))
    result = ask(sales, question)['result']
    assert result['group_key'].tolist() == expected[column].tolist()
    assert result['value'].tolist() == expected['value'].tolist()


def test_inventory_and_count_prompts(sales):
    inventory = pd.DataFrame({'stock_on_hand': [20, 30]})
    for q in ['Total stock_on_hand', '库存数量合计']:
        assert ask(inventory, q)['result'].iat[0, 0] == 50
    for q in ['How many rows?', '有多少行？']:
        assert ask(sales, q)['result'].iat[0, 0] == len(sales)


def test_submitted_plan_has_no_row_payload_and_executes_on_current_data():
    frame = pd.DataFrame({'net "income"': [9, 4, 9], 'group_key': ['Q', 'R', 'Q']})
    def planner(question, schema):
        assert question == 'Rank earnings across segments'
        assert schema == {key: str(dtype) for key, dtype in frame.dtypes.items()}
        return {'operation': 'sum', 'metric': 'net "income"', 'group_by': 'group_key', 'limit': 1}
    output = ask(frame, 'Rank earnings across segments', planner)
    assert output['mode'] == 'Language model'
    assert output['result'].to_dict('records') == [{'group_key': 'Q', 'value': 18}]


@pytest.mark.parametrize('question', [
    'total revenue where product is lamp', 'total revenue since January', 'total revenue in Q1',
    'What is total revenue and profit?', '每月总销售额是多少？', '利润率是多少？',
    'How many distinct orders?', 'Top 0 products by revenue', 'top 101 products by revenue',
    'total revenue by unknown field',
])
def test_refuses_unhandled_semantics(sales, question):
    with pytest.raises(UnsupportedQuestion):
        ask(sales, question)


@pytest.mark.parametrize('plan', [
    {'operation': 'count', 'sql': 'SELECT 42'}, {'operation': 'count', 'metric': 'order_id'},
    {'operation': 'sum', 'metric': 'missing'}, {'operation': 'sum', 'metric': 'order_id'},
    {'operation': 'sum', 'metric': 'revenue', 'group_by': ['region']},
    {'operation': 'count', 'group_by': 'product', 'limit': True},
    {'operation': ['sum']}, {'unsupported': True}, None,
])
def test_model_plan_is_validated(sales, plan):
    with pytest.raises(UnsupportedQuestion):
        ask(sales, 'Tell me about the takings', lambda q, schema: plan)


def test_model_cannot_skip_common_scope_or_change_explicit_metric(sales):
    def should_not_be_called(*args):
        pytest.fail('Unsupported time filter must be refused before planning')
    with pytest.raises(UnsupportedQuestion):
        ask(sales, 'Total revenue last week?', should_not_be_called)
    with pytest.raises(UnsupportedQuestion, match='disagrees'):
        ask(sales, 'Total revenue?', lambda q, schema: {'operation': 'sum', 'metric': 'profit'})


def test_empty_sum_preserves_null():
    assert pd.isna(ask(pd.DataFrame({'amount': pd.Series([], dtype=float)}),
                       'Sum of amount')['result'].iat[0, 0])
