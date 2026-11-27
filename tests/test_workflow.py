"""Integration check for the workflow guide and shared state across navigation."""
import io
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


class WorkflowTests(unittest.TestCase):
    @patch('rag.OpenAI')
    @patch('streamlit.file_uploader')
    def test_guide_keeps_uploads_samples_and_chat_without_model_requests(self, uploader, client):
        upload = io.BytesIO(b'value\n1\n2\n')
        upload.name = 'extra.csv'
        uploader.side_effect = lambda label, **kwargs: [] if 'PDF' in label else [upload]
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run(timeout=20)
        next(button for button in app.button if button.key == 'load_samples').click().run(timeout=20)
        store = app.session_state['store']
        documents = app.session_state['documents']
        app.session_state['messages'] = [{'role': 'assistant', 'content': 'Previous answer'}]
        try:
            app.switch_page('workflow_page.py').run(timeout=20)
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.chat_input), 0)
            self.assertIs(app.session_state['store'], store)
            self.assertIs(app.session_state['documents'], documents)
            self.assertEqual(len(store.tables), 3)
            self.assertEqual(app.session_state['messages'][0]['content'], 'Previous answer')
            # The generated workflow replaces the HTML chart while retaining the walkthrough.
            html = ' '.join(element.proto.body for element in app.get('html'))
            self.assertNotIn('workflow-diagram', html)
            self.assertEqual(len(app.get('image')), 1)
            self.assertIn('updated app workflow', app.get('image')[0].proto.imgs[0].caption)
            prose = ' '.join(element.value for element in app.markdown)
            self.assertIn('BM25', prose)
            self.assertIn('OpenAI requests', prose)
            code = ' '.join(element.value for element in app.code)
            self.assertIn('request_query_plan()', code)
            self.assertIn('validate_sql()', code)
            self.assertIn('select_display_evidence()', code)
            self.assertEqual(len(app.code), 8)
            client.assert_not_called()
        finally:
            store.close()
