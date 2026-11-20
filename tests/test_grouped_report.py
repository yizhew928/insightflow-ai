import pandas as pd
from insightflow.report import _bar_chart


def test_numeric_group_ids_label_bars_and_measure_sets_height():
    result = pd.DataFrame({'group_key':[101, 202], 'value':[12, 6]})
    chart = _bar_chart(result)
    assert '<h3>value' in chart and '<span>202</span>' in chart and '<strong>6.00</strong>' in chart
