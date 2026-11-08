# Chat with your spreadsheets

A commented Python + Streamlit application using Pandas, DuckDB, and the OpenAI API.
Upload multiple `.csv`, `.xlsx`, or `.xls` files, ask questions conversationally, and
inspect or download the SQL results behind each answer as an Excel (`.xlsx`) workbook.
When an answer uses joins, an expanded relationships panel shows the source files
and worksheets, SQL aliases, join types, and matching conditions from the executed
query. These describe the query's joins, not verified primary/foreign-key constraints.

## Run locally

Python 3.11–3.13 is recommended (newer Python versions may lack dependency wheels).

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

An editable `.env` is already included. Set `OPENAI_API_KEY` to your OpenAI API key.
If recreating the project from version control, copy `.env.example` to `.env` first.
The key is kept server-side, and `.env` is excluded from Git.

```bash
streamlit run app.py
```

Open the localhost URL printed by Streamlit. Upload files, inspect their inferred
data, and type a question. API calls require
an OpenAI account with API access and billing; choose a model available to your
account via `OPENAI_MODEL`. The default is `gpt-4.1-mini`.

Example questions:

- What are total sales by region, ordered highest first?
- Which products had the largest month-over-month revenue change?
- Join orders and customers on customer_id and show sales by customer.
- Now show only the top five.

Try uploading both CSVs from `sample_data/` first. Total revenue should be 5,140;
joining on `customer_id` gives Aster Labs 1,440 and Cedar School 2,400.

## How retrieval works

This is **SQL-based RAG** for structured data. It does not build a vector index.
Pandas reads files; each worksheet becomes a separate DuckDB table. The model
receives table schemas and a few sample rows, then plans a query. The application
validates and executes that query locally. A second model call explains the
retrieved results. Full-table SQL aggregation avoids calculating totals from a
small vector-search sample. For semantic similarity across long text documents,
a separate embeddings retrieval pipeline would be needed for semantic similarity.
PDF knowledge retrieval in this app uses local lexical ranking as described below.

## PDF policies and knowledge

Use **Upload PDF knowledge / policy documents**, directly below the spreadsheet
uploader. Upload an employee spreadsheet and a searchable policy PDF, then ask:

> Using the uploaded performance policy, show each employee's performance category,
> calculated score, and the policy criteria used.

The app extracts text with page references, splits it into paragraphs,
and supplies that evidence to **both SQL planning and answer generation**. The AI
is instructed to apply policy thresholds and formulas to full spreadsheet tables,
ask about ambiguous mappings or conflicting rules, and cite PDF filenames/pages.
The **PDF evidence provided for this answer** expander shows up to six directly
relevant source paragraphs selected against the question, answer, and SQL. Source
text and page references are preserved; duplicate or unknown paragraph IDs are
discarded. The panel is hidden if nothing relevant is selected. Broader context
may still be supplied for planning so definitions and exceptions remain available.
This relevance check adds one model call for answers with PDF context. If selection
fails, the answer remains available and the evidence panel is hidden. Dense blocks
without paragraph breaks are divided into bounded excerpts at sentence/word boundaries.
PDF-only questions also work without a spreadsheet.

Short documents are included in full (as extracted text). Longer collections use
BM25 lexical retrieval within `PDF_CONTEXT_CHARS`; the UI labels partial retrieval.
Lexical retrieval can miss paraphrases, distant definitions, or exceptions. Review
the cited policy and SQL for consequential uses. Text extraction may alter complex
table layouts. Scanned/image-only PDFs require OCR beforehand; unreadable pages
are reported, and encrypted or wholly unreadable PDFs are rejected.

Editable `.env` settings: `MAX_PDF_FILES` (5), `MAX_PDF_PAGES` (100 per document),
`MAX_PDF_CHARS` (500000 total extracted characters), `PDF_CONTEXT_CHARS` (24000).
`MAX_FILE_MB` also applies to PDFs. PDF changes clear chat history; spreadsheets
remain loaded. A failed upload blocks chat until corrected or removed so an answer
cannot silently ignore a selected policy.

PDFs are parsed locally and held in session memory. Retrieved passages are sent
to OpenAI when asking questions. There is no OCR or external vector database.
Extraction reference: [pypdf text extraction](https://pypdf.readthedocs.io/en/latest/user/extract-text.html).

Table IDs (`table_1`, etc.) map to original filenames and worksheet names in the
data explorer. Browse every row using the page selector and adjustable page size;
the fixed-height data grid supports scrolling. Column names are normalized and
made unique. CSV uses comma delimiters and the configured encoding.
Excel formulas rely on values saved by Excel; recalculate and save the workbook
before uploading if cached formula values are missing. Dates and mixed types
depend on Pandas inference; review the schema before asking date-related questions.

## Configuration

Edit `.env`, then restart Streamlit. Existing process environment variables override
the file. `.env.example` documents every setting. Main controls:

| Setting | Purpose |
| --- | --- |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | Authentication and model |
| `OPENAI_TIMEOUT_SECONDS` | Timeout per API attempt (one retry permitted) |
| `PLAN_MAX_OUTPUT_TOKENS` | Initial SQL planning output budget, default 8000 |
| `PLAN_RETRY_MAX_OUTPUT_TOKENS` | Budget for one incomplete/malformed-plan retry, default 16000 |
| `ANSWER_MAX_OUTPUT_TOKENS` | Explanation output budget, default 4000 |
| `MAX_FILES`, `MAX_FILE_MB`, `MAX_TABLES` | Upload limits |
| `MAX_ROWS_PER_TABLE`, `MAX_COLUMNS` | Reject oversized tables without silently truncating |
| `MAX_RESULT_ROWS` | Cap displayed and model-visible query results |
| `QUERY_TIMEOUT_SECONDS`, `DUCKDB_MEMORY_MB` | Query time and database memory limits |
| `SAMPLE_ROWS` | Example rows per table sent for SQL planning |
| `HISTORY_MESSAGES` | Recent conversation messages included in each question |
| `MAX_QUESTION_CHARS`, `MAX_CONTEXT_CHARS` | Bound question and data context sizes |
| `CSV_ENCODING` | CSV decoding, default `utf-8-sig` |

The application rejects contexts above the configured size rather than silently
omitting tables. Query output limits apply after aggregation; a sum still includes
the entire source table. Upload changes reset the conversation to avoid stale answers.
Query plans are checked for response completion before JSON validation or SQL execution.
A plan cut off at its output limit is regenerated once with the larger budget; partial
SQL is never executed. Malformed completed plans also get one retry. Refusals and
other incomplete reasons are not retried. Response budgets include any model reasoning
tokens. Raising them may increase latency and cost. Restart Streamlit after editing `.env`.

## Files and checks

The grey-and-orange interface is configured in `.streamlit/config.toml` (native
Streamlit colors), `styles.css` (layout and component styling), and `ui.py` (visual
helpers). Uploaded text is rendered through native widgets rather than raw HTML.

- `app.py`: Streamlit upload, data explorer, conversation, and error messages.
- `config.py`: Environment configuration and validation.
- `data_store.py`: Pandas import, source mapping, SQL validation, DuckDB execution.
- `rag.py`: Structured query planning and evidence-grounded answer generation.
- `tests/test_app.py`: Offline integration tests, including mocked OpenAI responses.

```bash
python -m unittest discover -s tests -v
```

## Data handling and limits

Uploaded data is held in server memory in a database private to the Streamlit
session; there is no persistent upload storage or global data cache. Reloading or
ending a session may lose the data and chat. Removing/replacing uploads closes the
old database. Schemas, sample cells, recent chat, and bounded query results are sent
to OpenAI when the user asks a question; no opt-in checkbox is required. Requests use
`store=False`; this does not override the provider's applicable data policies.

SQL is parsed and restricted to a single read-only query over loaded tables;
DuckDB external access and extension loading are disabled. Query execution has a
timeout and memory limit. These are defense-in-depth controls, not a complete
sandbox for hostile public uploads. Pandas/Excel parsing and Streamlit session
memory are outside DuckDB's memory limit. This is a local prototype: add
authentication, process isolation, deployment-wide quotas, and lifecycle cleanup
before exposing it as a multi-user public service. Model-generated SQL can still
misinterpret business meaning; inspect the supporting query for important decisions.

API implementation reference: [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
Database configuration reference: [DuckDB configuration](https://duckdb.org/docs/stable/configuration/overview).
