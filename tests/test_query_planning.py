"""Regression checks for incomplete and malformed structured responses."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from config import load_settings
from rag import QueryPlan, answer_question, answer_text, request_query_plan


def response(text, status='completed', reason=None, output=None):
    return SimpleNamespace(status=status, output_text=text, output=output or [],
                           incomplete_details=SimpleNamespace(reason=reason))


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.settings = load_settings()
        self.client = MagicMock()
        self.valid = QueryPlan(sql='SELECT 1', clarification='').model_dump_json()

    def plan(self):
        return request_query_plan(self.client, self.settings, instructions='Plan SQL', input='test')

    def test_truncated_response_retries_with_more_tokens(self):
        self.client.responses.create.side_effect = [
            response('{"sql":"WITH normalized AS (', 'incomplete', 'max_output_tokens'),
            response(self.valid),
        ]
        self.assertEqual(self.plan().sql, 'SELECT 1')
        calls = self.client.responses.create.call_args_list
        self.assertEqual(calls[0].kwargs['max_output_tokens'], self.settings.plan_max_tokens)
        self.assertEqual(calls[1].kwargs['max_output_tokens'], self.settings.plan_retry_max_tokens)
        self.assertEqual(calls[0].kwargs['input'], calls[1].kwargs['input'])
        self.assertTrue(calls[0].kwargs['text']['format']['schema']['additionalProperties'] is False)

    def test_malformed_completed_json_retries_then_sanitizes_error(self):
        self.client.responses.create.return_value = response('{"sql":"PRIVATE partial SQL')
        with self.assertRaisesRegex(ValueError, 'invalid query plan twice') as caught:
            self.plan()
        self.assertNotIn('PRIVATE', str(caught.exception))
        self.assertEqual(self.client.responses.create.call_count, 2)

    def test_valid_json_with_incomplete_status_is_not_accepted(self):
        self.client.responses.create.return_value = response(self.valid, 'incomplete', 'max_output_tokens')
        with self.assertRaisesRegex(ValueError, 'output limit after a retry'):
            self.plan()

    def test_refusal_is_not_retried(self):
        refusal = SimpleNamespace(content=[SimpleNamespace(type='refusal')])
        self.client.responses.create.return_value = response('', output=[refusal])
        with self.assertRaisesRegex(ValueError, 'declined'):
            self.plan()
        self.client.responses.create.assert_called_once()

    def test_other_incomplete_reason_is_not_retried(self):
        self.client.responses.create.return_value = response('', 'incomplete', 'content_filter')
        with self.assertRaisesRegex(ValueError, 'stopped before completion'):
            self.plan()
        self.client.responses.create.assert_called_once()

    @patch('rag.OpenAI')
    def test_failed_plan_never_reaches_database(self, mock_openai):
        client = mock_openai.return_value.__enter__.return_value
        client.responses.create.return_value = response(self.valid, 'incomplete', 'max_output_tokens')
        store = MagicMock()
        store.catalog.return_value = '[]'
        with self.assertRaises(ValueError):
            answer_question('test', [], store, self.settings)
        store.query.assert_not_called()

    def test_truncated_explanation_is_not_presented_as_complete(self):
        with self.assertRaisesRegex(ValueError, 'explanation did not finish'):
            answer_text(response('partial answer', 'incomplete', 'max_output_tokens'))
