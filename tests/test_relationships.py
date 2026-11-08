"""Verify that displayed relationships faithfully describe executed joins."""
import unittest

from relationships import describe_relationships


class RelationshipTests(unittest.TestCase):
    tables = [
        {'table': 'table_1', 'file': 'sales.csv', 'sheet': None},
        {'table': 'table_2', 'file': 'customers.xlsx', 'sheet': 'Customers'},
    ]

    def test_inner_join_with_aliases(self):
        result = describe_relationships(
            'SELECT * FROM table_1 s INNER JOIN table_2 c ON s.customer_id = c.customer_id', self.tables)
        self.assertEqual(result[0]['Relationship'], 'INNER JOIN')
        self.assertIn('sales.csv (table_1) AS s', result[0]['Left source'])
        self.assertIn('customers.xlsx / Customers', result[0]['Right source'])
        self.assertEqual(result[0]['Matching condition'], 's.customer_id = c.customer_id')

    def test_using_and_multiple_joins(self):
        result = describe_relationships(
            'SELECT * FROM table_1 LEFT JOIN table_2 USING (customer_id) CROSS JOIN table_1 other', self.tables)
        self.assertEqual(result[0]['Relationship'], 'LEFT JOIN')
        self.assertEqual(result[0]['Matching condition'], 'Matching columns: customer_id')
        self.assertEqual(result[1]['Relationship'], 'CROSS JOIN')
        self.assertTrue(result[1]['Left source'].startswith('Joined result:'))

    def test_cte_and_nested_joins(self):
        result = describe_relationships(
            'WITH orders AS (SELECT * FROM table_1 JOIN table_2 USING (customer_id)) '
            'SELECT * FROM orders o JOIN table_2 c ON o.customer_id = c.customer_id', self.tables)
        self.assertEqual(len(result), 2)
        self.assertTrue(any('orders (query-defined source)' in row['Left source'] for row in result))

    def test_single_table_has_no_relationships(self):
        self.assertEqual(describe_relationships('SELECT * FROM table_1', self.tables), [])
