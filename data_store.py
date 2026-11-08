"""Load tabular uploads and execute validated, read-only queries locally."""
import io
import json
import re
import threading
from pathlib import Path

import duckdb
import pandas as pd
import sqlglot
from sqlglot import exp

from config import Settings


def normalize_columns(columns) -> list[str]:
    """Give duplicate, blank and punctuation-heavy headers unique SQL names."""
    used = set()
    result = []
    for index, column in enumerate(columns):
        base = re.sub(r'[^a-z0-9_]', '_', str(column).strip().lower()).strip('_')
        base = base or f'column_{index + 1}'
        if base[0].isdigit():
            base = 'col_' + base
        name, suffix = base, 2
        while name in used:
            name = f'{base}_{suffix}'
            suffix += 1
        used.add(name)
        result.append(name)
    return result


def validate_sql(sql: str, allowed_tables: set[str]) -> str:
    """Parse SQL, reject writes and table functions, then check table scope."""
    try:
        statements = sqlglot.parse(sql, read='duckdb')
    except sqlglot.errors.ParseError as error:
        raise ValueError('The generated SQL could not be parsed. Please rephrase the question.') from error
    if len(statements) != 1 or not isinstance(statements[0], (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise ValueError('Only a single SELECT query is allowed.')
    tree = statements[0]
    forbidden = (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Command, exp.Into)
    if any(isinstance(node, forbidden) for node in tree.walk()):
        raise ValueError('This query is not read-only.')
    if any(cte.args.get('recursive') for cte in tree.find_all(exp.With)):
        raise ValueError('Recursive queries are disabled.')
    ctes = {cte.alias.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier) or table.db or table.catalog:
            raise ValueError('External tables and table functions are disabled.')
        if table.name.lower() not in allowed_tables | ctes:
            raise ValueError(f'Unknown table: {table.name}')
    return tree.sql(dialect='duckdb')


class DataStore:
    """One private, in-memory database per Streamlit session/upload batch."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.connection = duckdb.connect(':memory:', config={
            'memory_limit': f'{settings.memory_mb}MB', 'threads': '2',
            'autoload_known_extensions': 'false', 'autoinstall_known_extensions': 'false',
        })
        self.tables = []

    def close(self):
        self.connection.close()

    def load(self, uploads: list[tuple[str, bytes]]):
        if not uploads or len(uploads) > self.settings.max_files:
            raise ValueError(f'Choose between 1 and {self.settings.max_files} files.')
        for filename, contents in uploads:
            if len(contents) > self.settings.max_file_mb * 1024 * 1024:
                raise ValueError(f'{filename}: exceeds the per-file size limit.')
            extension = Path(filename).suffix.lower()
            if extension == '.csv':
                frame = pd.read_csv(io.BytesIO(contents), encoding=self.settings.csv_encoding,
                                    nrows=self.settings.max_rows + 1)
                self._add(filename, None, frame)
            elif extension in {'.xlsx', '.xls'}:
                # Each worksheet becomes a separate table, preserving its source label.
                with pd.ExcelFile(io.BytesIO(contents)) as workbook:
                    for sheet in workbook.sheet_names:
                        frame = pd.read_excel(workbook, sheet_name=sheet,
                                              nrows=self.settings.max_rows + 1)
                        if len(frame.columns):
                            self._add(filename, sheet, frame)
            else:
                raise ValueError(f'Unsupported file type: {extension}')
        if not self.tables:
            raise ValueError('No tables were found in the uploaded files.')
        # Materialize Pandas data before disabling filesystem/replacement-scan access.
        self.connection.execute('SET enable_external_access = false')
        self.connection.execute('SET lock_configuration = true')
        if len(self.catalog()) > self.settings.context_chars:
            raise ValueError('Table descriptions exceed MAX_CONTEXT_CHARS. Upload fewer columns/files.')

    def _add(self, filename, sheet, frame):
        if len(self.tables) >= self.settings.max_tables:
            raise ValueError('Too many worksheets/tables. Increase MAX_TABLES or upload fewer files.')
        if len(frame) > self.settings.max_rows or len(frame.columns) > self.settings.max_columns:
            raise ValueError(f'{filename}: table exceeds configured row or column limits; no rows were silently dropped.')
        original = [str(column) for column in frame.columns]
        frame.columns = normalize_columns(frame.columns)
        table = f'table_{len(self.tables) + 1}'
        self.connection.register('_upload', frame)
        try:
            self.connection.execute(f'CREATE TABLE "{table}" AS SELECT * FROM _upload')
        finally:
            self.connection.unregister('_upload')
        columns = self.connection.execute(f'DESCRIBE "{table}"').fetchall()
        self.tables.append({
            'table': table, 'file': filename, 'sheet': sheet, 'rows': len(frame),
            'columns': [{'name': c[0], 'type': c[1], 'original': raw}
                        for c, raw in zip(columns, original)],
            'sample': json.loads(frame.head(self.settings.sample_rows).to_json(orient='records', date_format='iso')),
        })

    def catalog(self):
        return json.dumps(self.tables, ensure_ascii=False, default=str)

    def page(self, table: str, offset: int, page_size: int):
        """Browse a bounded page without applying the AI result-row limit."""
        if table not in {item['table'] for item in self.tables}:
            raise ValueError('Unknown table.')
        if offset < 0 or not 1 <= page_size <= 500:
            raise ValueError('Invalid page bounds.')
        return self.connection.execute(
            f'SELECT * FROM "{table}" ORDER BY rowid LIMIT ? OFFSET ?',
            [page_size, offset],
        ).fetchdf()

    def query(self, sql: str):
        safe_sql = validate_sql(sql, {t['table'] for t in self.tables})
        # LIMIT bounds returned rows, not the rows participating in an aggregate.
        bounded = f'SELECT * FROM ({safe_sql}) AS answer LIMIT {self.settings.result_rows + 1}'
        timer = threading.Timer(self.settings.query_timeout, self.connection.interrupt)
        timer.start()
        try:
            frame = self.connection.execute(bounded).fetchdf()
        finally:
            timer.cancel()
            timer.join()
        truncated = len(frame) > self.settings.result_rows
        return frame.head(self.settings.result_rows), truncated, safe_sql
