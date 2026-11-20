"""Execute one SELECT locally with DuckDB external access disabled.

This is a local analysis guard, not a multi-tenant or denial-of-service sandbox.
"""
import duckdb


def run_query(tables: dict, sql: str, max_rows: int = 1000):
    if not 1 <= max_rows <= 10000:
        raise ValueError('max_rows must be between 1 and 10000.')
    if not isinstance(sql, str) or len(sql) > 20000:
        raise ValueError('SQL must be text of at most 20,000 characters.')
    con = duckdb.connect(database=':memory:', config={
        'enable_external_access': 'false', 'autoload_known_extensions': 'false',
        'autoinstall_known_extensions': 'false', 'memory_limit': '512MB', 'threads': '2'})
    try:
        for name, frame in tables.items():
            if not isinstance(name, str) or not name or name.startswith('_'):
                raise ValueError('Invalid table name.')
            con.register(name, frame)
        statements = con.extract_statements(sql)
        if len(statements) != 1 or str(statements[0].type) != 'StatementType.SELECT':
            raise ValueError('Only one SELECT query is allowed.')
        # The outer limit also applies to queries without a limit. A SELECT can still
        # be computationally expensive before the limit is applied.
        cleaned = statements[0].query.strip().rstrip(';').strip()
        return con.execute(f'SELECT * FROM ({cleaned}) AS insightflow_result LIMIT {int(max_rows)}').df()
    finally:
        con.close()
