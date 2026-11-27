"""The updated workflow image and a code-backed walkthrough of the app."""
from pathlib import Path

import streamlit as st


# The walkthrough expands the stages shown in the workflow image.
STEPS = [
    {
        'number': '1', 'title': 'Load HR data', 'summary': 'Excel / CSV → Pandas → DuckDB',
        'detail': 'Upload CSV, XLSX, or XLS files, or load the bundled sample files. Pandas reads '
        'each file or worksheet. Column names are normalized and made unique; inferred data types '
        'and configured limits are checked. Each worksheet becomes a separate in-memory DuckDB '
        'table. The catalog records its source, schema, and a few example rows. This preparation '
        'does not automatically repair missing values or inconsistent business data.',
        'code': 'app.py: upload handling and file fingerprints\n'
                'samples.py: load_sample_files(), combine_files()\n'
                'data_store.py: DataStore.load(), _add(), normalize_columns(), catalog()',
    },
    {
        'number': '2', 'title': 'Prepare policy knowledge', 'summary': 'Searchable PDF → page-cited paragraphs',
        'detail': 'pypdf extracts text from the uploaded PDFs. The code splits it into paragraphs '
        'and preserves each filename and page number. Very long blocks become smaller excerpts. '
        'Empty pages are reported; image-only documents require OCR before upload. Changing '
        'either spreadsheets or documents clears old chat answers.',
        'code': 'app.py: PDF loading and state reset\n'
                'documents.py: DocumentStore.load(), split_paragraphs()',
    },
    {
        'number': '3', 'title': 'Ask a question and retrieve context',
        'summary': 'Your question + recent chat + relevant policy context',
        'detail': 'The question enters answer_question() with a bounded conversation history. '
        'For short PDFs, retrieve() includes the extracted paragraphs within the context budget. '
        'For longer collections it uses BM25 keyword ranking to select passages, with recent user '
        'questions helping resolve follow-ups. This implementation uses lexical retrieval; '
        'it does not create embeddings or a vector database.',
        'code': 'app.py: st.chat_input(), answer_question() call\n'
                'rag.py: answer_question()\n'
                'documents.py: DocumentStore.retrieve(), terms()',
    },
    {
        'number': '4', 'title': 'Prepare a policy-aware SQL plan',
        'summary': 'OpenAI combines the question, table catalog, and PDF evidence',
        'detail': 'The model receives the table names, columns, sample rows, question, recent '
        'conversation, and retrieved policy text. It returns a structured QueryPlan containing '
        'SQL or a clarification. Policy thresholds and formulas can become SQL conditions or '
        'calculations. The app checks response completion and validates the JSON schema, retrying '
        'an incomplete or malformed plan once. No partial SQL is executed.',
        'code': 'rag.py: QueryPlan, request_query_plan(), answer_question()',
    },
    {
        'number': '5', 'title': 'Validate and run the query',
        'summary': 'Read-only SQL → DuckDB calculations → result rows',
        'detail': 'SQLGlot parses the query and checks that it is a single read-only statement '
        'over permitted tables. External tables and table functions are rejected. DuckDB executes '
        'the validated query locally with external access disabled, a query timeout, and a memory '
        'limit. Aggregations run over the full matching dataset; MAX_RESULT_ROWS limits the '
        'returned rows after calculation. The model never calculates totals from preview rows.',
        'code': 'data_store.py: validate_sql(), DataStore.query()',
    },
    {
        'number': '6', 'title': 'Generate the grounded answer',
        'summary': 'Query results + policy evidence → explanation with source references',
        'detail': 'A second OpenAI request explains the SQL results using the available PDF '
        'evidence and source mapping. Instructions require source references and disclosure '
        'of truncated results. answer_text() checks that the response finished. If only PDFs '
        'are uploaded, the document-answer route skips SQL. A document-only question or '
        'clarification may also return without SQL when tables are present. Model interpretations '
        'can still be wrong, so the app exposes the supporting rows and query for inspection.',
        'code': 'rag.py: answer_question(), answer_text()',
    },
    {
        'number': '7', 'title': 'Select the evidence to display',
        'summary': 'Relevant paragraph IDs → exact source excerpts',
        'detail': 'A separate model request selects up to six paragraphs directly related to '
        'the question, answer, and SQL. The code resolves selected IDs to the original source '
        'text, removes duplicates, and discards unknown IDs. When nothing relevant is selected '
        'or selection fails, the evidence panel is hidden. This small display selection is '
        'separate from the broader policy context used to plan the query.',
        'code': 'rag.py: EvidenceSelection, select_display_evidence(), attach_evidence()',
    },
    {
        'number': '8', 'title': 'Inspect and export the result',
        'summary': 'Answer + evidence + relationships + Excel download',
        'detail': 'Streamlit renders the answer, policy excerpts, supporting data, and SQL. '
        'SQL joins are parsed into a relationship table showing the sources, join type, and '
        'matching condition. Excel downloads are created in memory using Pandas and openpyxl. '
        'The data explorer uses page() to browse all table rows separately from the smaller '
        'AI result limit.',
        'code': 'app.py: render_chat(), render_message()\n'
                'relationships.py: describe_relationships()\n'
                'exports.py: results_to_excel()\n'
                'data_store.py: DataStore.page()',
    },
]


def render_workflow():
    st.html('<div class="workspace-breadcrumb">Workspace <span>/</span> <b>How it works</b></div>'
            '<h1 class="workspace-title">How the HR Data Assistant works</h1>'
            '<p class="workspace-subtitle">From employee data and policy knowledge to an answer you can inspect.</p>')

    # Resolve from this file so the page works regardless of the launch directory.
    image = Path(__file__).parent / 'output' / 'imagegen' / 'How the HR Data Assistant Works - Updated.png'
    if image.is_file():
        # Inset the image so its artwork does not meet the grey page edge directly.
        with st.container(key='workflow_image'):
            st.image(str(image), width='stretch', caption='How the HR Data Assistant Works — updated app workflow')
    else:
        st.warning('The updated workflow image is missing from output/imagegen.')

    st.subheader('How each step runs in the code')
    st.markdown('The walkthrough below expands the stages in the image. `app.py` coordinates the interface and session state; '
                '`rag.py` coordinates retrieval, model requests, and query execution.')
    for step in STEPS:
        with st.container(border=True, key=f'guide_step_{step["number"]}'):
            st.markdown(f'### {step["number"]}. {step["title"]}')
            st.markdown(step['detail'])
            st.caption('Code responsible for this step')
            st.code(step['code'], language=None, wrap_lines=True)

    with st.container(border=True, key='guide_example'):
        st.subheader('Example: promotion shortlisting')
        st.markdown(
            '**Question:** “Using the promotion policy, which employees are shortlisted?”\n\n'
            '1. Load the two sample workbooks and the policy PDF (**steps 1–2**).\n'
            '2. Retrieve the rule covering the two review years (**step 3**).\n'
            '3. Generate a query that applies the policy’s Grade B-or-above criteria and '
            'manual-review exceptions (**step 4**). The criteria come from the PDF, not hard-coded app rules.\n'
            '4. Validate and execute that query over the employee tables (**step 5**).\n'
            '5. Explain the result, select the relevant policy paragraphs, and display the '
            'supporting rows with an Excel download (**steps 6–8**).'
        )
    with st.container(border=True, key='guide_settings'):
        st.subheader('Settings, progress, and data handling')
        st.markdown(
            '**Configuration:** `config.py → load_settings()` reads `.env` and environment '
            'variables for the API key, model, upload limits, context limits, and timeouts. '
            'The key stays on the server.\n\n'
            '**Live progress:** `app.py → show_progress()` receives events from `rag.py`. '
            'The activity panel starts expanded and collapses when the answer is ready. '
            'It reports processing steps rather than private model reasoning.\n\n'
            '**Presentation:** `ui.py`, `styles.css`, and `.streamlit/config.toml` control '
            'the responsive grey-and-orange interface. This guide is implemented in `workflow_page.py`.\n\n'
            '**Local work:** Pandas parsing, PDF extraction, retrieval ranking, and DuckDB '
            'queries run on the Streamlit server. Uploaded data and conversation state are '
            'held in the current session.\n\n'
            '**OpenAI requests:** Questions send the needed table catalog, example rows, '
            'recent chat, retrieved PDF context, and bounded query results to the API. '
            'Evidence selection adds a model request when PDF context is available. '
            'Opening this guide makes no model requests.'
        )


if __name__ == '__main__':
    render_workflow()
