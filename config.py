"""Read editable settings without exposing the API key in the interface."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    api_key: str
    model: str
    api_timeout: int
    max_files: int
    max_file_mb: int
    max_tables: int
    max_rows: int
    max_columns: int
    result_rows: int
    query_timeout: int
    memory_mb: int
    sample_rows: int
    history_messages: int
    question_chars: int
    context_chars: int
    csv_encoding: str
    max_pdf_files: int = 5
    max_pdf_pages: int = 100
    max_pdf_chars: int = 500000
    pdf_context_chars: int = 24000
    plan_max_tokens: int = 8000
    plan_retry_max_tokens: int = 16000
    answer_max_tokens: int = 4000


def load_settings() -> Settings:
    # Existing environment variables take precedence over the local .env file.
    load_dotenv(Path(__file__).with_name('.env'))

    def number(name: str, default: int) -> int:
        value = int(os.getenv(name, str(default)))
        if value < 1:
            raise ValueError(f'{name} must be a positive integer.')
        return value

    return Settings(
        api_key=os.getenv('OPENAI_API_KEY', '').strip(),
        model=os.getenv('OPENAI_MODEL', 'gpt-4.1-mini'),
        api_timeout=number('OPENAI_TIMEOUT_SECONDS', 60),
        max_files=number('MAX_FILES', 10),
        max_file_mb=number('MAX_FILE_MB', 20),
        max_tables=number('MAX_TABLES', 30),
        max_rows=number('MAX_ROWS_PER_TABLE', 100000),
        max_columns=number('MAX_COLUMNS', 100),
        result_rows=number('MAX_RESULT_ROWS', 200),
        query_timeout=number('QUERY_TIMEOUT_SECONDS', 15),
        memory_mb=number('DUCKDB_MEMORY_MB', 512),
        sample_rows=number('SAMPLE_ROWS', 3),
        history_messages=number('HISTORY_MESSAGES', 10),
        question_chars=number('MAX_QUESTION_CHARS', 4000),
        context_chars=number('MAX_CONTEXT_CHARS', 60000),
        csv_encoding=os.getenv('CSV_ENCODING', 'utf-8-sig'),
        max_pdf_files=number('MAX_PDF_FILES', 5),
        max_pdf_pages=number('MAX_PDF_PAGES', 100),
        max_pdf_chars=number('MAX_PDF_CHARS', 500000),
        pdf_context_chars=number('PDF_CONTEXT_CHARS', 24000),
        plan_max_tokens=number('PLAN_MAX_OUTPUT_TOKENS', 8000),
        plan_retry_max_tokens=number('PLAN_RETRY_MAX_OUTPUT_TOKENS', 16000),
        answer_max_tokens=number('ANSWER_MAX_OUTPUT_TOKENS', 4000),
    )
