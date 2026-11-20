import pandas as pd
import pytest

from insightflow.explanations import explain_result
from insightflow.questions import ask
from insightflow.sql import run_query
from insightflow.templates import run_template


def text(analysis):
    assert analysis['explanation'] == explain_result(analysis)
    return '\n'.join(analysis['explanation'])


def test_scalar_uses_the_requested_operation_and_non_null_denominator():
    frame = pd.DataFrame({'revenue': [30, None, 10]})
    assert '平均值为 20' in text(ask(frame, 'average revenue'))
    assert '3 行记录中 2 个' in text(ask(frame, 'max revenue'))
    assert '3 行记录' in text(ask(frame, '有多少行'))
    assert '为空' in text(ask(frame.iloc[:0], 'sum revenue'))
    assert '0 行记录' in text(ask(frame.iloc[:0], 'How many rows?'))


def test_grouped_ties_and_limits_do_not_imply_full_sheet_shares():
    frame = pd.DataFrame({'category': ['甲', '乙', '丙', '丁'], 'revenue': [12, 12, 9, 7]})
    all_groups = text(ask(frame, '按品类统计销售额'))
    assert '并列最高' in all_groups and '「甲」' in all_groups and '「乙」' in all_groups
    assert '40' in all_groups and '30.00%' in all_groups
    ranked = text(ask(frame, 'Top 1 categories by revenue'))
    assert '最多显示 1 组' in ranked and '本次返回 1 组' in ranked
    assert '%' not in ranked and '独占' not in ranked


def test_null_groups_negative_values_and_averages_avoid_fabricated_shares():
    frame = pd.DataFrame({'group': [None, 'x'], 'score': [-10, -5]})
    assert '「x」' in text(ask(frame, 'average score by group'))
    assert '其次是「空值」，为 -10' in text(ask(frame, 'sum score by group'))
    assert '%' not in text(ask(frame, 'sum score by group'))
    frame['score'] = float('nan')
    assert '无法排序' in text(ask(frame, 'sum score by group'))
    assert '无法比较分组' in text(ask(frame.iloc[:0], 'sum score by group'))


def test_templates_describe_mapped_outputs_and_unknown_inventory():
    frame = pd.DataFrame({'d': ['day X', 'day X', 'day Y'], 'r': [70, 30, 25],
                          'p': [25, 10, 15], 'id': ['x', 'x', 'y']})
    sales = text(run_template(frame, 'sales', {'revenue': 'r', 'date': 'd'}))
    assert 'day X' in sales and '100' in sales and '25' in sales
    assert '125' in text(run_template(frame, 'sales', {'revenue': 'r'}))
    assert '40.00%' in text(run_template(frame, 'profit', {'revenue': 'r', 'profit': 'p'}))
    assert '「x」' in text(run_template(frame, 'customers', {'revenue': 'r', 'customer_id': 'id'}))
    inventory = pd.DataFrame({'product': ['A', 'A', 'B'], 'stock_on_hand': [2, 5, None],
                              'reorder_level': [2, 4, 8]})
    content = text(run_template(inventory, 'inventory', {col: col for col in inventory.columns}))
    assert '1 条的库存数量' in content and '1 条记录缺少' in content and '「A」' in content


@pytest.mark.parametrize(('sql', 'expect'), [
    ('SELECT 42 AS "新指标"', '「新指标」的结果为 42'),
    ('SELECT NULL as "未知"', '结果为 空值'),
    ('SELECT [1, 2] AS "列表"', '列表'),
    ("SELECT {'a': 2} AS detail", 'detail'),
    ('SELECT FALSE as flag', 'False'),
    ('SELECT * FROM range(2000)', '1,000 行展示上限'),
    ('SELECT * FROM range(3)', '最小值是 0，最大值是 2'),
    ('SELECT * FROM range(0)', '没有返回记录'),
])
def test_sql_explains_actual_returned_values_without_assuming_business_meaning(sql, expect):
    content = '\n'.join(explain_result({'sql': sql, 'result': run_query({}, sql)}))
    assert expect in content and '销售' not in content
