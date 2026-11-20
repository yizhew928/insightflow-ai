"""Black-box checks for the local, synthetic-data MVP."""
from io import BytesIO

import pandas as pd
import pytest
from openpyxl import Workbook
from pandas.testing import assert_frame_equal

from insightflow.data import load_tables
from insightflow.quality import profile
from insightflow.sql import run_query


def test_csv_import_preserves_data():
    tables = load_tables('item,amount\n苹果,12\n梨,8\n'.encode(), 'sales.csv')
    assert len(tables) == 1
    data = next(iter(tables.values()))
    assert list(data.columns) == ['item', 'amount']
    assert data['item'].tolist() == ['苹果', '梨']
    assert data['amount'].sum() == 20


def test_excel_import_reads_all_sheets_including_empty_sheet():
    book = Workbook()
    first = book.active
    first.title = 'Sales 2026'
    first.append(['product', 'amount'])
    first.append(['Desk', 120])
    second = book.create_sheet('Inventory')
    second.append(['product', 'stock'])
    second.append(['Chair', 3])
    book.create_sheet('Empty')
    stream = BytesIO()
    book.save(stream)
    tables = load_tables(stream.getvalue(), 'demo.xlsx')
    assert {'Sales 2026', 'Inventory'} <= set(tables)
    assert tables['Sales 2026']['amount'].tolist() == [120]
    assert tables['Inventory']['stock'].tolist() == [3]
    # An empty worksheet may be omitted or represented by an empty table.
    assert 'Empty' not in tables or tables['Empty'].empty


def test_unrecognized_file_type_is_rejected():
    with pytest.raises((ValueError, TypeError)):
        load_tables(b'col\nvalue\n', 'sample.txt')


def test_quality_profile_does_not_modify_data():
    data = pd.DataFrame({'product': ['A', 'A', None], 'amount': [10.0, 10.0, None]})
    before = data.copy(deep=True)
    result = profile(data)
    assert isinstance(result, dict)
    assert_frame_equal(data, before)


def test_sql_returns_correct_grouped_results_and_respects_limit():
    data = pd.DataFrame({'category': ['A', 'A', 'B'], 'amount': [10, 20, 5]})
    result = run_query({'sales': data}, 'SELECT category, SUM(amount) AS total FROM sales GROUP BY category ORDER BY category')
    assert result['category'].tolist() == ['A', 'B']
    assert result['total'].tolist() == [30, 5]
    limited = run_query({'sales': data}, 'SELECT * FROM sales ORDER BY amount', max_rows=2)
    assert len(limited) == 2
    assert limited['amount'].tolist() == [5, 10]


@pytest.mark.parametrize('query', [
    'SELECT 1; SELECT 2',
    'CREATE TABLE unexpected AS SELECT 1',
    'DELETE FROM sales',
    'PRAGMA version',
    "ATTACH ':memory:' AS other",
])
def test_sql_rejects_multiple_statements_and_non_read_queries(query):
    with pytest.raises(Exception):
        run_query({'sales': pd.DataFrame({'amount': [1]})}, query)


def test_sql_cannot_read_local_files(tmp_path):
    secret = tmp_path / 'secret.csv'
    secret.write_text('secret\nprivate_value\n', encoding='utf-8')
    path = str(secret).replace("'", "''")
    with pytest.raises(Exception):
        run_query({'sales': pd.DataFrame({'amount': [1]})}, f"SELECT * FROM read_csv_auto('{path}')")


def test_sql_cannot_write_local_files(tmp_path):
    destination = tmp_path / 'export.csv'
    path = str(destination).replace("'", "''")
    with pytest.raises(Exception):
        run_query({'sales': pd.DataFrame({'amount': [1]})}, f"COPY sales TO '{path}' (HEADER, DELIMITER ',')")
    assert not destination.exists()


def test_quality_profile_counts_missing_and_duplicates():
    data = pd.DataFrame({'product': ['A', 'A', None], 'amount': [10.0, 10.0, None]})
    result = profile(data)
    assert result['rows'] == 3
    assert result['columns'] == 2
    assert result['duplicate_rows'] == 1
    assert result['missing_cells'] == 2
    stats = result['column_stats'].set_index('column')
    assert stats.loc['product', 'missing'] == 1
    assert stats.loc['amount', 'missing'] == 1


def test_sales_template_reports_a_reproducible_sum():
    from insightflow.templates import run_template
    data = pd.DataFrame({'sales_amount': [100.0, 50.0, 0.0]})
    report = run_template(data, 'sales', {'revenue': 'sales_amount'})
    assert isinstance(report['result'], pd.DataFrame)
    assert 150.0 in report['result'].select_dtypes('number').to_numpy()
    assert report['sql'] and report['formulas']


def test_profit_template_handles_zero_revenue():
    from insightflow.templates import run_template
    data = pd.DataFrame({'sales': [0.0, 0.0], 'earnings': [5.0, 7.0]})
    report = run_template(data, 'profit', {'revenue': 'sales', 'profit': 'earnings'})
    assert report['sql'] and report['formulas']
    result = report['result']
    assert 12.0 in result.select_dtypes('number').to_numpy()
    assert result.isna().any().any()


def test_template_rejects_missing_required_mapping():
    from insightflow.templates import run_template
    with pytest.raises(ValueError):
        run_template(pd.DataFrame({'other': [1]}), 'profit', {})


def test_inventory_template_flags_low_stock_and_unknown():
    from insightflow.templates import run_template
    data = pd.DataFrame({'item': ['A', 'B', 'C'], 'stock': [2, 8, None], 'threshold': [3, 3, 3]})
    report = run_template(data, 'inventory', {'product': 'item', 'stock_on_hand': 'stock', 'reorder_level': 'threshold'})
    result = report['result'].set_index('product')
    assert bool(result.loc['A', 'reorder_needed'])
    assert not bool(result.loc['B', 'reorder_needed'])
    assert pd.isna(result.loc['C', 'reorder_needed'])


def test_customer_template_groups_revenue():
    from insightflow.templates import run_template
    data = pd.DataFrame({'client': ['a', 'a', 'b'], 'sales': [10, 12, 4]})
    result = run_template(data, 'customers', {'customer_id': 'client', 'revenue': 'sales'})['result'].set_index('customer_id')
    assert result.loc['a', 'revenue'] == 22
    assert result.loc['a', 'records'] == 2
    assert result.loc['b', 'revenue'] == 4


def test_template_quotes_column_names_as_identifiers():
    from insightflow.templates import run_template
    name = 'revenue"; SELECT 999; --'
    data = pd.DataFrame({name: [5, 7]})
    report = run_template(data, 'sales', {'revenue': name})
    assert report['result']['revenue'].iloc[0] == 12


@pytest.mark.parametrize('limit', [0, -1, 10001])
def test_sql_rejects_out_of_range_limits(limit):
    with pytest.raises(ValueError):
        run_query({'sales': pd.DataFrame({'amount': [1]})}, 'SELECT * FROM sales', max_rows=limit)
