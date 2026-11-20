"""Deterministic business templates: SQL and formulas accompany each result."""
from .sql import run_query
from .explanations import explain_result

REQUIRED = {'sales': ['revenue'], 'profit': ['revenue', 'profit'],
            'inventory': ['product', 'stock_on_hand', 'reorder_level'],
            'customers': ['customer_id', 'revenue']}


def quote(name):
    return '"' + str(name).replace('"', '""') + '"'


def run_template(df, template, mapping):
    if template not in REQUIRED:
        raise ValueError('Unknown template.')
    missing = [field for field in REQUIRED[template] if field not in mapping or mapping[field] not in df.columns]
    if missing:
        raise ValueError('Required fields missing: ' + ', '.join(missing))
    col = lambda key: quote(mapping[key])
    num = lambda key: f'TRY_CAST({col(key)} AS DOUBLE)'
    if template == 'sales':
        if mapping.get('date') in df.columns:
            sql = f'SELECT CAST({col("date")} AS VARCHAR) AS period, SUM({num("revenue")}) AS revenue, COUNT(*) AS records FROM data GROUP BY 1 ORDER BY 1 LIMIT 1000'
            formulas = ['Revenue = sum of mapped revenue values; grouped by the supplied date field (no automatic date bucketing).', 'Records = number of rows per date; non-numeric revenue is excluded from sums.']
        else:
            sql = f'SELECT SUM({num("revenue")}) AS revenue, COUNT(*) AS records FROM data'
            formulas = ['Revenue = sum of mapped revenue values; non-numeric values are excluded.', 'Records = number of rows.']
    elif template == 'profit':
        sql = f'SELECT SUM({num("revenue")}) AS revenue, SUM({num("profit")}) AS profit, SUM({num("profit")}) / NULLIF(SUM({num("revenue")}), 0) AS profit_margin FROM data'
        formulas = ['Revenue = sum of revenue; profit = sum of profit.', 'Profit margin = total profit / total revenue; NULL when total revenue is zero. Non-numeric values are excluded.']
    elif template == 'inventory':
        sql = f'SELECT {col("product")} AS product, {num("stock_on_hand")} AS stock_on_hand, {num("reorder_level")} AS reorder_level, {num("stock_on_hand")} <= {num("reorder_level")} AS reorder_needed FROM data ORDER BY stock_on_hand ASC NULLS LAST LIMIT 1000'
        formulas = ['Reorder needed = stock on hand ≤ reorder level, per row; NULL if either value is missing or non-numeric.']
    else:
        sql = f'SELECT {col("customer_id")} AS customer_id, SUM({num("revenue")}) AS revenue, COUNT(*) AS records FROM data GROUP BY 1 ORDER BY revenue DESC NULLS LAST LIMIT 1000'
        formulas = ['Customer revenue = sum of revenue per customer; non-numeric values are excluded.', 'Records = number of rows per customer.']
    analysis = {'title': template.title(), 'template': template, 'sql': sql,
                'result': run_query({'data': df}, sql), 'formulas': formulas}
    analysis['explanation'] = explain_result(analysis)
    return analysis
