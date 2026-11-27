"""Exercise demo loading with the actual bundled files and existing uploads."""
import io
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from samples import combine_files, load_sample_files


class SampleTests(unittest.TestCase):
    def test_bundle_and_duplicate_uploads(self):
        tables, pdfs = load_sample_files()
        self.assertEqual(len(tables), 2)
        self.assertEqual(len(pdfs), 1)
        self.assertTrue(pdfs[0][1].startswith(b'%PDF-'))
        self.assertEqual(combine_files(tables, tables), tables)

    @patch('streamlit.file_uploader')
    def test_load_persist_and_remove_samples_keeps_uploads(self, uploader):
        upload = io.BytesIO(b'value\n1\n2\n')
        upload.name = 'my_upload.csv'
        uploader.side_effect = lambda label, **kwargs: [] if 'PDF' in label else [upload]
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run(timeout=20)
        self.assertEqual(len(app.session_state['store'].tables), 1)
        app.session_state['messages'] = [{'role': 'assistant', 'content': 'Old answer'}]
        next(button for button in app.button if button.key == 'load_samples').click().run(timeout=20)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.session_state['store'].tables), 3)
        self.assertEqual(sum(t['rows'] for t in app.session_state['store'].tables), 152)
        self.assertEqual(len(app.session_state['documents'].documents), 1)
        self.assertEqual(app.session_state['messages'], [])
        app.run(timeout=20)
        self.assertEqual(len(app.session_state['store'].tables), 3)
        next(button for button in app.button if button.key == 'remove_samples').click().run(timeout=20)
        self.assertEqual(len(app.exception), 0)
        self.assertIsNone(app.session_state['sample_files'])
        self.assertIsNone(app.session_state['documents'])
        self.assertEqual([t['file'] for t in app.session_state['store'].tables], ['my_upload.csv'])
        app.session_state['store'].close()
