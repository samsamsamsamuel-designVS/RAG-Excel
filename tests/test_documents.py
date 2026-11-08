"""Offline PDF retrieval and policy-to-SQL integration checks."""
import io
import json
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from streamlit.testing.v1 import AppTest

from config import load_settings
from data_store import DataStore
from documents import DocumentStore
from rag import QueryPlan, answer_question


def pdf_bytes(texts):
    """Build tiny text PDFs in memory as parser fixtures, without external assets."""
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                                 NameObject('/Subtype'): NameObject('/Type1'),
                                 NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):
            DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject()
        text = text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        stream.set_data(f'BT /F1 12 Tf 40 720 Td ({text}) Tj ET'.encode())
        page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.settings = load_settings()
        self.docs = DocumentStore(self.settings)
        self.docs.load([('policy.pdf', pdf_bytes([
            'Performance policy: a score of at least 80 qualifies for Excellent.',
            'Scores below 80 are Standard. Apply this rule to the score column.',
        ]))])

    def test_extraction_and_page_citations(self):
        result = self.docs.retrieve('Which employees are Excellent?', [])
        self.assertFalse(result['partial'])
        self.assertEqual([p['page'] for p in result['passages']], [1, 2])
        self.assertIn('at least 80', result['passages'][0]['text'])

    def test_bounded_retrieval(self):
        self.docs.settings = replace(self.settings, pdf_context_chars=250)
        result = self.docs.retrieve('Excellent', [])
        self.assertTrue(result['partial'])
        self.assertLessEqual(len(json.dumps(result['passages'])), 250)
        self.assertIn('Excellent', result['passages'][0]['text'])

    def test_invalid_empty_and_oversized_documents(self):
        with self.assertRaisesRegex(ValueError, 'valid PDF'):
            DocumentStore(self.settings).load([('bad.pdf', b'not a PDF')])
        with self.assertRaisesRegex(ValueError, 'OCR'):
            DocumentStore(self.settings).load([('scan.pdf', pdf_bytes(['']))])
        with self.assertRaisesRegex(ValueError, 'MAX_PDF_PAGES'):
            DocumentStore(replace(self.settings, max_pdf_pages=1)).load([
                ('long.pdf', pdf_bytes(['one', 'two']))])

    def test_empty_page_warning(self):
        docs = DocumentStore(self.settings)
        docs.load([('mixed.pdf', pdf_bytes(['Rule: 80', '']))])
        self.assertIn('page 2', docs.warnings[0])

    @patch('rag.OpenAI')
    def test_policy_reaches_planning_and_answer(self, mock_openai):
        client = mock_openai.return_value.__enter__.return_value
        plan = QueryPlan(
            sql='SELECT employee, score FROM table_1 WHERE score >= 80 ORDER BY score DESC', clarification='')
        client.responses.create.side_effect = [SimpleNamespace(status='completed', output=[], output_text=plan.model_dump_json()), SimpleNamespace(status='completed', output_text='A and B qualify [policy.pdf, p. 1].'), SimpleNamespace(status='completed', output_text=json.dumps({'paragraph_ids': [self.docs.chunks[0]['id']]}))]
        store = DataStore(self.settings)
        store.load([('employees.csv', b'employee,score\nA,90\nB,80\nC,79\n')])
        try:
            answer = answer_question('Which employees are Excellent under the policy?', [], store, self.settings, self.docs)
            self.assertEqual(answer['data']['employee'].tolist(), ['A', 'B'])
            for call in client.responses.create.call_args_list[:2]:
                context = json.loads(call.kwargs['input'])
                self.assertIn('at least 80', context['knowledge']['passages'][0]['text'])
            self.assertEqual(answer['knowledge']['passages'][0]['file'], 'policy.pdf')
        finally:
            store.close()

    @patch('rag.OpenAI')
    def test_pdf_only(self, mock_openai):
        client = mock_openai.return_value.__enter__.return_value
        client.responses.create.return_value = SimpleNamespace(status='completed', output_text='Excellent starts at 80 [policy.pdf, p. 1].')
        answer = answer_question('What is Excellent?', [], None, self.settings, self.docs)
        self.assertIn('80', answer['content'])
        self.assertNotIn('text', client.responses.create.call_args_list[0].kwargs)

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    @patch('streamlit.file_uploader')
    def test_pdf_upload_and_removal_reset_state(self, uploader):
        file = io.BytesIO(pdf_bytes(['A score of 80 qualifies.']))
        file.name = 'policy.pdf'
        uploader.side_effect = lambda label, **kwargs: [file] if 'PDF' in label else []
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run()
        self.assertEqual(len(app.exception), 0)
        self.assertIsNotNone(app.session_state['documents'])
        self.assertFalse(app.chat_input[0].disabled)
        app.session_state['messages'] = [{'role': 'assistant', 'content': 'Old policy answer'}]
        uploader.side_effect = lambda label, **kwargs: []
        app.run()
        self.assertIsNone(app.session_state['documents'])
        self.assertEqual(app.session_state['messages'], [])
        self.assertTrue(app.chat_input[0].disabled)
