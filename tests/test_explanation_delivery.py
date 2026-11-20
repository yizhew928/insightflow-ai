from html import escape
from pathlib import Path

from streamlit.runtime.media_file_storage import MediaFileKind
from streamlit.runtime.memory_media_file_storage import MemoryMediaFileStorage
from streamlit.testing.v1 import AppTest

from insightflow.data import load_tables
from insightflow.quality import profile
from insightflow.report import build_report


ROOT = Path(__file__).resolve().parents[1]


def test_latest_query_explanation_matches_the_report_preview_and_download():
    app = AppTest.from_file(str(ROOT / 'app.py')).run()
    assert app.radio(key='report_picker').value == '销售复盘'
    app.button(key='run_question').click().run()
    assert app.radio(key='report_picker').value == 'Question answer'
    workbook = ROOT / 'sample_data/business_demo.xlsx'
    quality = profile(load_tables(workbook.read_bytes(), workbook.name)['Sales'])

    def check_report(state_key, tab_name):
        assert not app.exception
        analysis = app.session_state[state_key]
        html = build_report(workbook.name, 'Sales', quality, analysis)
        for tab in [next(t for t in app.tabs if t.label == tab_name), app.tabs[-1]]:
            visible = [m.value for m in tab.markdown]
            assert any(h.value == '结果解读' for h in tab.subheader)
            for line in analysis['explanation']:
                paragraph = f'<p>{escape(line)}</p>'
                assert paragraph in visible and paragraph in html
        storage = MemoryMediaFileStorage('/mock/media')
        file_id = storage.load_and_get_id(html.encode(), 'text/html', MediaFileKind.DOWNLOADABLE,
                                          filename='insightflow-report.html')
        button = next(b for b in app.tabs[-1].get('download_button') if b.proto.label == 'Download HTML report')
        assert file_id in button.proto.url

    check_report('question_analysis', '数据问答 · Ask')
    next(b for b in app.button if b.label == 'Run analysis').click().run()
    assert app.radio(key='report_picker').value == 'Business template'
    check_report('analysis', 'Business templates')
    app.text_area[0].set_value("SELECT '<item>' AS label, SUM(revenue) AS total FROM data")
    next(b for b in app.button if b.label == 'Run SQL').click().run()
    assert app.radio(key='report_picker').value == 'SQL query'
    check_report('sql_analysis', 'SQL explorer')
    app.radio(key='report_picker').set_value('Question answer').run()
    assert app.radio(key='report_picker').value == 'Question answer'
    check_report('question_analysis', '数据问答 · Ask')
    app.text_area[0].set_value('SELECT 1').run()
    assert 'sql_analysis' not in app.session_state
    assert 'SQL query' not in app.radio(key='report_picker').options
