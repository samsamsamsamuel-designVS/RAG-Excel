"""Regression tests for truncated explanations and preservation of query results."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from config import load_settings
from data_store import DataStore
from rag import AnswerLimitError, QueryPlan, answer_question, request_answer


def response(text, status='completed', reason=None, output=None):
    return SimpleNamespace(status=status, output_text=text, output=output or [],
                           incomplete_details=SimpleNamespace(reason=reason))


class AnswerRetryTests(unittest.TestCase):
    def setUp(self):
        self.settings = load_settings()
        self.client = MagicMock()

    def request(self, events=None):
        return request_answer(self.client, self.settings, instructions='Use only the evidence.',
                              input='evidence', on_progress=events.append if events is not None else None)

    def test_completed_answer_is_not_retried(self):
        self.client.responses.create.return_value = response('Complete answer.')
        self.assertEqual(self.request(), 'Complete answer.')
        self.client.responses.create.assert_called_once()

    def test_length_limit_retries_with_same_evidence_and_larger_budget(self):
        self.client.responses.create.side_effect = [
            response('Unfinished text', 'incomplete', 'max_output_tokens'), response('Finished answer.')]
        events = []
        self.assertEqual(self.request(events), 'Finished answer.')
        self.assertEqual(len(events), 1)
        calls = self.client.responses.create.call_args_list
        self.assertEqual(calls[0].kwargs['input'], calls[1].kwargs['input'])
        self.assertEqual(calls[0].kwargs['max_output_tokens'], self.settings.answer_max_tokens)
        self.assertEqual(calls[1].kwargs['max_output_tokens'],
                         max(self.settings.answer_max_tokens, self.settings.answer_retry_max_tokens))
        self.assertIn('source citations', calls[1].kwargs['instructions'])
        self.assertNotIn('Unfinished text', calls[1].kwargs['input'])

    def test_two_length_failures_stop(self):
        self.client.responses.create.return_value = response('partial', 'incomplete', 'max_output_tokens')
        with self.assertRaises(AnswerLimitError):
            self.request()
        self.assertEqual(self.client.responses.create.call_count, 2)

    def test_content_filter_is_not_retried(self):
        self.client.responses.create.return_value = response('', 'incomplete', 'content_filter')
        with self.assertRaisesRegex(ValueError, 'stopped before completion'):
            self.request()
        self.client.responses.create.assert_called_once()

    def test_refusal_is_not_retried(self):
        self.client.responses.create.return_value = response('', output=[
            SimpleNamespace(content=[SimpleNamespace(type='refusal')])])
        with self.assertRaisesRegex(ValueError, 'declined'):
            self.request()
        self.client.responses.create.assert_called_once()

    def test_empty_completed_answer_is_not_retried(self):
        self.client.responses.create.return_value = response('')
        with self.assertRaisesRegex(ValueError, 'no answer'):
            self.request()
        self.client.responses.create.assert_called_once()

    @patch('rag.OpenAI')
    def test_query_runs_once_and_data_survives_explanation_failures(self, mock_openai):
        client = mock_openai.return_value.__enter__.return_value
        plan = QueryPlan(sql='SELECT SUM(revenue) AS total FROM table_1', clarification='')
        client.responses.create.side_effect = [response(plan.model_dump_json()),
            response('partial 1', 'incomplete', 'max_output_tokens'),
            response('partial 2', 'incomplete', 'max_output_tokens')]
        store = DataStore(self.settings)
        store.load([('sales.csv', b'revenue\n10\n20\n')])
        try:
            with patch.object(store, 'query', wraps=store.query) as query:
                result = answer_question('Total revenue?', [], store, self.settings)
            query.assert_called_once()
            self.assertTrue(result['explanation_incomplete'])
            self.assertEqual(result['data'].iloc[0]['total'], 30)
            self.assertEqual(result['sql'], 'SELECT SUM(revenue) AS total FROM table_1')
            self.assertNotIn('partial 2', result['content'])
            self.assertIn('Excel', result['content'])
        finally:
            store.close()

    @patch('rag.OpenAI')
    def test_pdf_only_answer_uses_retry(self, mock_openai):
        client = mock_openai.return_value.__enter__.return_value
        client.responses.create.side_effect = [response('partial', 'incomplete', 'max_output_tokens'),
                                              response('Complete PDF answer.'),
                                              response('{"paragraph_ids": []}')]
        docs = MagicMock()
        docs.retrieve.return_value = {'passages': [{'id': 'p1', 'file': 'policy.pdf', 'page': 1,
                                                  'text': 'Policy rule.'}], 'partial': False, 'warnings': []}
        result = answer_question('Explain this policy', [], None, self.settings, docs)
        self.assertEqual(result['content'], 'Complete PDF answer.')
        self.assertNotIn('sql', result)
