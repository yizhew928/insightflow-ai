"""Question-to-report journeys through the Streamlit widgets and bundled synthetic data."""
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app():
    instance = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
    assert not instance.exception
    return instance


def run_question(app):
    app.button(key='run_question').click().run()
    assert not app.exception


def test_question_export_tracks_question_and_sheet(app):
    assert '数据问答 · Ask' in [tab.label for tab in app.tabs]
    run_question(app)
    assert not app.error
    answer = app.session_state['question_analysis']
    sales = pd.read_csv(ROOT / 'sample_data/sales.csv')
    assert answer['result'].set_index('group_key')['value'].to_dict() == sales.groupby('category').revenue.sum().to_dict()
    assert any('SELECT' in block.value.upper() for block in app.code)
    assert [b for b in app.get('download_button') if b.proto.label == 'Download HTML report']
    app.text_input(key='question_text').set_value('How many rows?').run()
    assert 'question_analysis' not in app.session_state
    assert not [b for b in app.get('download_button') if b.proto.label == 'Download HTML report']
    run_question(app)
    assert app.session_state['question_analysis']['result'].iat[0, 0] == len(sales)
    next(s for s in app.selectbox if s.label == 'Sheet / table').select('Inventory').run()
    assert not app.exception and not [b for b in app.get('download_button') if b.proto.label == 'Download HTML report']
    assert app.text_input(key='question_text').value == '库存数量合计'
    run_question(app)
    inventory = pd.read_csv(ROOT / 'sample_data/inventory.csv')
    assert app.session_state['question_analysis']['result'].iat[0, 0] == inventory.stock_on_hand.sum()


def test_mode_and_failure_clear_previous_answer(app, monkeypatch):
    run_question(app)
    assert [b for b in app.get('download_button') if b.proto.label == 'Download HTML report']
    mode = app.radio(key='question_mode')
    mode.set_value(mode.options[1]).run()
    assert 'question_analysis' not in app.session_state
    assert not [b for b in app.get('download_button') if b.proto.label == 'Download HTML report']

    def unavailable():
        raise ValueError('Test local model unavailable')

    monkeypatch.setattr('insightflow.local_model.get_planner', unavailable)
    run_question(app)
    assert app.error and any('Test local model unavailable' in t.value for t in app.text)
    assert not [b for b in app.get('download_button') if b.proto.label == 'Download HTML report']
    app.radio(key='question_mode').set_value(mode.options[0]).run()
    assert not app.error
    app.text_input(key='question_text').set_value('Forecast next year using a regression').run()
    run_question(app)
    assert app.error and 'question_analysis' not in app.session_state
    assert not [b for b in app.get('download_button') if b.proto.label == 'Download HTML report']
