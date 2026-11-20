"""User journey and HTML escaping checks using synthetic inputs only."""
from pathlib import Path
import pandas as pd
from streamlit.testing.v1 import AppTest
from insightflow.quality import profile
from insightflow.report import build_report


def widget(widgets, label):
    return next(item for item in widgets if item.label == label)


def test_report_escapes_untrusted_text():
    payload = '<script>alert("x")</script>'
    data = pd.DataFrame({'name': [payload], 'amount': [7]})
    quality = profile(data)
    analysis = {'title': payload, 'sql': 'SELECT ' + payload, 'formulas': [payload], 'result': data}
    html = build_report(payload, payload, quality, analysis)
    assert payload not in html
    assert '&lt;script&gt;' in html
    assert 'SELECT &lt;script&gt;' in html
    assert 'Data quality' in html and 'Calculation evidence' in html


def test_demo_ui_workflow():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=30).run()
    assert not app.exception
    assert widget(app.metric, 'Rows').value == '72'
    widget(app.button, 'Run analysis').click().run()
    assert not app.exception and not app.error
    assert app.session_state['analysis']['title'] == 'Sales'
    assert 'SUM' in app.session_state['analysis']['sql']
    assert app.get('download_button')
    widget(app.text_area, 'SQL').set_value('SELECT COUNT(*) AS n FROM data')
    widget(app.button, 'Run SQL').click().run()
    assert not app.exception and not app.error
    assert app.session_state['sql_analysis']['result']['n'].iloc[0] == 72
    widget(app.radio, 'Report analysis').set_value('SQL query').run()
    assert app.get('download_button')
    assert any('Ready: SQL query' in item.value for item in app.markdown)
    widget(app.selectbox, 'Sheet / table').select('Inventory').run()
    assert not app.exception and not app.error
    assert 'analysis' not in app.session_state
    assert 'sql_analysis' not in app.session_state
    widget(app.selectbox, 'Analysis template').select('Inventory').run()
    widget(app.button, 'Run analysis').click().run()
    assert not app.exception and not app.error
    assert app.session_state['analysis']['title'] == 'Inventory'
    assert 'reorder_needed' in app.session_state['analysis']['result']
    widget(app.selectbox, 'Sheet / table').select('Sales').run()
    widget(app.selectbox, 'Analysis template').select('Customers').run()
    widget(app.button, 'Run analysis').click().run()
    assert not app.exception and not app.error
    assert app.session_state['analysis']['title'] == 'Customers'
    assert not app.session_state['analysis']['result'].empty
