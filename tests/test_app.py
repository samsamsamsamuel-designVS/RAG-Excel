"""Offline behavior checks: no API key or paid requests required."""
import io
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from config import load_settings
from data_store import DataStore, normalize_columns, validate_sql
from rag import QueryPlan, answer_question


class DataTests(unittest.TestCase):
    def setUp(self):
        self.settings = load_settings()
        self.store = DataStore(self.settings)
        self.store.load([('sales.csv', b'customer_id,revenue\n1,10\n2,20\n1,30\n'),
                         ('customers.csv', b'customer_id,name\n1,Alice\n2,Bob\n')])

    def tearDown(self):
        self.store.close()

    def test_join_and_aggregate(self):
        result, truncated, _ = self.store.query(
            'SELECT c.name, SUM(s.revenue) AS total FROM table_1 s '
            'JOIN table_2 c USING (customer_id) GROUP BY c.name ORDER BY total DESC')
        self.assertEqual(result.iloc[0]['name'], 'Alice')
        self.assertEqual(result.iloc[0]['total'], 40)
        self.assertFalse(truncated)

    def test_reject_unsafe_queries(self):
        for sql in ['DROP TABLE table_1', 'SELECT 1; SELECT 2',
                    "SELECT * FROM read_csv('/etc/passwd')", 'SELECT * FROM duckdb_tables()',
                    'SELECT * FROM information_schema.tables', 'SELECT * FROM missing',
                    'COPY table_1 TO \'/tmp/leak.csv\'']:
            with self.subTest(sql=sql), self.assertRaises(ValueError):
                validate_sql(sql, {'table_1', 'table_2'})

    def test_cte_allowed(self):
        frame, _, _ = self.store.query('WITH x AS (SELECT * FROM table_1) SELECT SUM(revenue) AS total FROM x')
        self.assertEqual(frame.iloc[0]['total'], 60)

    def test_column_collisions(self):
        self.assertEqual(normalize_columns(['A', 'a', 'a_2', '', '1st']),
                         ['a', 'a_2', 'a_2_2', 'column_4', 'col_1st'])

    def test_oversized_table_rejected(self):
        from dataclasses import replace
        store = DataStore(replace(self.settings, max_rows=1))
        try:
            with self.assertRaisesRegex(ValueError, 'exceeds configured'):
                store.load([('too_large.csv', b'value\n1\n2\n')])
        finally:
            store.close()

    def test_external_access_disabled(self):
        self.assertFalse(self.store.connection.execute(
            "SELECT current_setting('enable_external_access')").fetchone()[0])
        with self.assertRaises(Exception):
            self.store.connection.execute('SET enable_external_access = true')

    def test_excel_multiple_sheets(self):
        content = io.BytesIO()
        with pd.ExcelWriter(content, engine='openpyxl') as writer:
            pd.DataFrame({'value': [1, 2]}).to_excel(writer, sheet_name='First', index=False)
            pd.DataFrame({'value': [3]}).to_excel(writer, sheet_name='Second', index=False)
        store = DataStore(self.settings)
        try:
            store.load([('book.xlsx', content.getvalue())])
            self.assertEqual([t['sheet'] for t in store.tables], ['First', 'Second'])
        finally:
            store.close()

    def test_result_cap_preserves_aggregates(self):
        from dataclasses import replace
        self.store.settings = replace(self.settings, result_rows=1)
        frame, truncated, _ = self.store.query('SELECT * FROM table_1')
        self.assertEqual(len(frame), 1)
        self.assertTrue(truncated)
        frame, truncated, _ = self.store.query('SELECT SUM(revenue) AS total FROM table_1')
        self.assertEqual(frame.iloc[0]['total'], 60)
        self.assertFalse(truncated)

    @patch('rag.OpenAI')
    def test_rag_retrieves_evidence(self, mock_openai):
        client = MagicMock()
        mock_openai.return_value.__enter__.return_value = client
        plan = QueryPlan(
            sql='SELECT SUM(revenue) AS total FROM table_1', clarification='')
        client.responses.create.side_effect = [SimpleNamespace(status='completed', output=[], output_text=plan.model_dump_json()), SimpleNamespace(status='completed', output_text='Total revenue is 60 (sales.csv).')]
        answer = answer_question('Total revenue?', [], self.store, self.settings)
        self.assertEqual(answer['data'].iloc[0]['total'], 60)
        self.assertIn('60', client.responses.create.call_args.kwargs['input'])

    @patch('rag.OpenAI')
    def test_clarification_skips_query(self, mock_openai):
        client = mock_openai.return_value.__enter__.return_value
        plan = QueryPlan(
            sql='', clarification='Which date column should I use?')
        client.responses.create.return_value = SimpleNamespace(status='completed', output=[], output_text=plan.model_dump_json())
        answer = answer_question('Compare last year', [], self.store, self.settings)
        self.assertIn('Which date', answer['content'])
        client.responses.create.assert_called_once()


class UITests(unittest.TestCase):
    def test_initial_screen(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run(timeout=20)
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(app.chat_input[0].disabled)

    @patch('rag.OpenAI')
    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key-not-real'})
    def test_chat_with_loaded_data(self, mock_openai):
        client = mock_openai.return_value.__enter__.return_value
        plan = QueryPlan(
            sql='SELECT SUM(revenue) AS total FROM table_1', clarification='')
        client.responses.create.side_effect = [SimpleNamespace(status='completed', output=[], output_text=plan.model_dump_json()), SimpleNamespace(status='completed', output_text='Revenue is 30.')]
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run(timeout=20)
        store = DataStore(load_settings())
        store.load([('sales.csv', b'revenue\n10\n20\n')])
        try:
            app.session_state['store'] = store
            app.run()
            app.chat_input[0].set_value('What is total revenue?').run(timeout=20)
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.chat_message), 2)
            self.assertIn('Revenue is 30', app.session_state['messages'][-1]['content'])
        finally:
            store.close()


if __name__ == '__main__':
    unittest.main()
