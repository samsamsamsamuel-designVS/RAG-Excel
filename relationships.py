"""Describe joins from the executed SQL, rather than guessing relationships."""
import sqlglot
from sqlglot import exp


def describe_relationships(sql: str, tables: list[dict]) -> list[dict]:
    catalog = {table['table']: table for table in tables}

    def label(source):
        if isinstance(source, exp.Table):
            table = catalog.get(source.name)
            if table:
                name = table['file']
                if table.get('sheet'):
                    name += f" / {table['sheet']}"
                name += f' ({source.name})'
            else:
                name = f'{source.name} (query-defined source)'
        else:
            name = 'Subquery'
        if source.alias:
            name += f' AS {source.alias}'
        return name

    relationships = []
    tree = sqlglot.parse_one(sql, read='duckdb')
    # Inspect each SELECT separately so nested queries retain their own joins.
    for select in tree.find_all(exp.Select):
        source = select.args.get('from_')
        if source is None:
            continue
        left = label(source.this)
        for join in select.args.get('joins', []):
            right = label(join.this)
            on = join.args.get('on')
            using = join.args.get('using')
            method = join.args.get('method', '')
            parts = [method, join.args.get('side', ''), join.args.get('kind', '')]
            join_type = ' '.join(part for part in parts if part).upper()
            if not join_type:
                join_type = 'INNER' if on is not None or using else 'CROSS'
            if on is not None:
                condition = on.sql(dialect='duckdb')
            elif using:
                condition = 'Matching columns: ' + ', '.join(column.sql(dialect='duckdb') for column in using)
            elif method.upper() == 'NATURAL':
                condition = 'All columns with matching names (NATURAL JOIN)'
            else:
                condition = 'No matching condition (all row combinations)'
            relationships.append({'Left source': left, 'Relationship': f'{join_type} JOIN',
                                  'Right source': right, 'Matching condition': condition})
            # Later joins operate on the preceding joined result, not just the first table.
            left = f'Joined result: {left} + {right}'
    return relationships
