"""Evidence display must never fall back to dumping the retrieval context."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from pathlib import Path

from streamlit.testing.v1 import AppTest

from config import load_settings
from documents import split_paragraphs
from rag import select_display_evidence


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.settings = load_settings()
        self.knowledge = {'passages': [
            {'id': 'p1', 'file': 'policy.pdf', 'page': 1, 'text': 'Two consecutive B grades qualify.'},
            {'id': 'p2', 'file': 'policy.pdf', 'page': 1, 'text': 'Travel expenses need receipts.'},
        ]}

    def choose(self, ids):
        self.client.responses.create.return_value = SimpleNamespace(
            status='completed', output_text=json.dumps({'paragraph_ids': ids}))
        return select_display_evidence(self.client, self.settings, 'Who qualifies for promotion?',
                                       'Two B grades qualify.', self.knowledge)

    def test_only_selected_paragraph_is_shown(self):
        selected = self.choose(['p1'])
        self.assertEqual(selected, [self.knowledge['passages'][0]])
        self.assertNotIn('Travel', selected[0]['text'])

    def test_irrelevant_content_returns_empty(self):
        self.assertEqual(self.choose([]), [])

    def test_hallucinated_and_duplicate_ids_are_not_displayed(self):
        self.assertEqual(self.choose(['p1', 'invented', 'p1']), [self.knowledge['passages'][0]])

    def test_malformed_selection_never_falls_back_to_full_document(self):
        self.client.responses.create.return_value = SimpleNamespace(status='completed', output_text='bad json')
        self.assertEqual(select_display_evidence(self.client, self.settings, 'question', 'answer', self.knowledge), [])

    def test_paragraph_boundaries_preserved(self):
        self.assertEqual(split_paragraphs('First paragraph\ncontinued.\n\nSecond paragraph.'),
                         ['First paragraph\ncontinued.', 'Second paragraph.'])
        long_text = 'A long sentence. ' * 200
        paragraphs = split_paragraphs(long_text)
        self.assertTrue(all(len(p) <= 1800 for p in paragraphs))
        self.assertEqual(' '.join(paragraphs).split(), long_text.split())

    def test_empty_evidence_panel_is_hidden(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run()
        app.session_state['messages'] = [{'role': 'assistant', 'content': 'No matching PDF evidence.',
                                         'knowledge': {**self.knowledge, 'evidence': []}}]
        app.run()
        self.assertFalse(any(e.label == 'PDF evidence provided for this answer' for e in app.expander))
        app.session_state['messages'] = [{'role': 'assistant', 'content': 'B grades qualify.',
                                         'knowledge': {**self.knowledge, 'evidence': [self.knowledge['passages'][0]]}}]
        app.run()
        panels = [e for e in app.expander if e.label == 'PDF evidence provided for this answer']
        self.assertEqual(len(panels), 1)
        shown = ' '.join(item.value for item in panels[0].text)
        self.assertIn('Two consecutive B', shown)
        self.assertNotIn('Travel', shown)
        self.assertEqual(len(app.exception), 0)
