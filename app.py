"""Run with: streamlit run app.py"""
import hashlib

import duckdb
import streamlit as st
from openai import APIConnectionError, APIStatusError, AuthenticationError, RateLimitError

from config import load_settings
from data_store import DataStore
from documents import DocumentStore
from exports import results_to_excel
from rag import answer_question
from relationships import describe_relationships
from ui import apply_theme, render_brand, render_header, render_status, render_empty_state

st.set_page_config(page_title='Data & Knowledge | Chat', page_icon='📊', layout='wide')
apply_theme()
render_header()

try:
    settings = load_settings()
except ValueError as error:
    st.error(f'Invalid .env setting: {error}')
    st.stop()

st.session_state.setdefault('messages', [])
st.session_state.setdefault('store', None)
st.session_state.setdefault('fingerprint', None)
st.session_state.setdefault('documents', None)
st.session_state.setdefault('pdf_fingerprint', None)

with st.sidebar:
    render_brand()
    with st.container(key='data_upload'):
        st.subheader('Data files')
        uploads = st.file_uploader('Upload CSV / Excel files', type=['csv', 'xlsx', 'xls'],
                                   accept_multiple_files=True, label_visibility='collapsed',
                                   max_upload_size=settings.max_file_mb)
        st.caption(f'CSV, XLSX, XLS · Up to {settings.max_files} files · {settings.max_file_mb} MB each')
    with st.container(key='policy_upload'):
        st.subheader('Knowledge documents')
        pdf_uploads = st.file_uploader('Upload PDF knowledge / policy documents', type=['pdf'],
                                      accept_multiple_files=True, key='pdf_uploads', label_visibility='collapsed',
                                      max_upload_size=settings.max_file_mb)
        st.caption(f'PDF · Up to {settings.max_pdf_files} files · {settings.max_file_mb} MB each')
        st.caption('Searchable text only. Scanned pages need OCR.')
    with st.expander('How your data is used'):
        st.caption('Schemas, sample rows, questions, query results, and relevant PDF passages are sent '
                   'to OpenAI when you chat. Files are processed in this server’s memory.')
        st.caption(f'Model: {settings.model}')
    if not settings.api_key:
        st.warning('Add OPENAI_API_KEY to .env and restart Streamlit to enable chat.')
    if st.button('Clear conversation', width='stretch', key='clear_chat'):
        st.session_state.messages = []
        st.rerun()

# Rebuild only when file contents change. Never share user data via a global cache.
payloads = [(file.name, file.getvalue()) for file in uploads]
fingerprint = tuple((name, hashlib.sha256(content).hexdigest()) for name, content in payloads)
if fingerprint != st.session_state.fingerprint:
    if st.session_state.store is not None:
        st.session_state.store.close()
    st.session_state.store = None
    st.session_state.messages = []
    st.session_state.fingerprint = fingerprint
    st.session_state.pop('load_error', None)
    if payloads:
        candidate = DataStore(settings)
        try:
            with st.spinner('Reading files and preparing tables…'):
                candidate.load(payloads)
            st.session_state.store = candidate
        except Exception as error:
            candidate.close()
            st.session_state.load_error = f'Could not load these files: {error}'

if st.session_state.get('load_error'):
    st.error(st.session_state.load_error)

# PDF changes invalidate previous answers, while leaving spreadsheet tables loaded.
pdf_payloads = [(file.name, file.getvalue()) for file in pdf_uploads]
# Invalidate older chunk-based document state after the paragraph extraction update.
pdf_fingerprint = ('paragraphs-v1', tuple((name, hashlib.sha256(content).hexdigest()) for name, content in pdf_payloads))
if pdf_fingerprint != st.session_state.pdf_fingerprint:
    st.session_state.pdf_fingerprint = pdf_fingerprint
    st.session_state.documents = None
    st.session_state.messages = []
    st.session_state.pop('pdf_error', None)
    if pdf_payloads:
        try:
            with st.spinner('Extracting PDF knowledge…'):
                documents = DocumentStore(settings)
                documents.load(pdf_payloads)
            st.session_state.documents = documents
        except Exception as error:
            st.session_state.pdf_error = f'Could not load PDF knowledge: {error}'
if st.session_state.get('pdf_error'):
    st.error(st.session_state.pdf_error)
documents = st.session_state.documents
store = st.session_state.store
ready = bool((store or documents) and settings.api_key
             and not (st.session_state.get('pdf_error') or st.session_state.get('load_error')))
render_status(store, documents, ready)
if documents:
    with st.expander('Explore PDF knowledge'):
        st.dataframe(documents.documents, width='stretch', hide_index=True)
        for warning in documents.warnings:
            st.warning(warning)
        st.caption('PDF rules are provided to the AI when it plans queries. '
                   'Example: “Use the performance policy to classify employees and show the criteria applied.”')
if store:
    with st.expander('Explore uploaded data'):
        selected = st.selectbox('Table', range(len(store.tables)), format_func=lambda i:
                               f'{store.tables[i]["table"]} — {store.tables[i]["file"]}'
                               + (f' / {store.tables[i]["sheet"]}' if store.tables[i]['sheet'] else ''))
        table = store.tables[selected]
        size_column, page_column = st.columns(2)
        with size_column:
            page_size = st.selectbox('Rows per page', [25, 50, 100, 250, 500], index=1)
        page_count = max(1, (table['rows'] + page_size - 1) // page_size)
        # Reset the page when the selected data or page size changes.
        page_context = (fingerprint, selected, page_size)
        if st.session_state.get('explorer_context') != page_context:
            st.session_state.explorer_context = page_context
            st.session_state.explorer_page = 1
        with page_column:
            page = st.number_input('Page', min_value=1, max_value=page_count,
                                   step=1, key='explorer_page')
        offset = (page - 1) * page_size
        # Browsing is independent of the smaller limit used for AI query results.
        preview = store.page(table['table'], offset, page_size)
        first_row = offset + 1 if table['rows'] else 0
        last_row = min(offset + page_size, table['rows'])
        st.caption(f'Rows {first_row:,}–{last_row:,} of {table["rows"]:,} · Page {page:,} of {page_count:,}')
        st.dataframe(preview, width='stretch', height=450, hide_index=True)
elif not documents:
    render_empty_state()


def render_message(message, index):
    with st.chat_message(message['role']):
        # The marker scopes bubble styling without depending on generated CSS classes.
        role = 'user' if message['role'] == 'user' else 'assistant'
        st.html(f'<span class="message-role-{role}"></span>')
        st.markdown(message['content'])
        knowledge = message.get('knowledge', {})
        if knowledge.get('evidence'):
            with st.expander('PDF evidence provided for this answer'):
                if knowledge.get('partial'):
                    st.warning('Only selected document passages were retrieved; other sections may contain additional conditions.')
                for warning in knowledge.get('warnings', []):
                    st.warning(warning)
                for evidence_index, passage in enumerate(knowledge['evidence']):
                    with st.container(key=f'evidence_{index}_{evidence_index}'):
                        # Source content stays in escaped native widgets, never raw HTML.
                        st.text(f'{passage["file"]} — page {passage["page"]}')
                        st.text(passage['text'])
        if 'sql' in message:
            relationships = describe_relationships(message['sql'], store.tables if store else [])
            if relationships:
                with st.expander('Table relationships used in this answer', expanded=True):
                    st.dataframe(relationships, width='stretch', hide_index=True)
                    st.caption('These are the joins used by this query. INNER JOIN keeps matching rows; '
                               'LEFT JOIN also keeps unmatched left rows; CROSS JOIN combines every pair of rows.')
            with st.expander('View SQL and supporting data'):
                st.dataframe(message['data'], width='stretch')
                with st.expander('View SQL'):
                    st.code(message['sql'], language='sql')
                if message['truncated']:
                    st.warning(f'Result capped at {settings.result_rows} rows. Ask for aggregates for complete totals.')
                st.download_button('Download results as Excel',
                                   results_to_excel(message['data']),
                                   file_name='query_results.xlsx',
                                   mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                   key=f'download_{index}', type='primary')


for index, message in enumerate(st.session_state.messages):
    render_message(message, index)

st.html('<p class="workspace-footer">Answers grounded in your uploaded files</p>')

question = st.chat_input('Ask a question about your files…',
                         disabled=not ((store or documents) and settings.api_key)
                         or bool(st.session_state.get('pdf_error') or st.session_state.get('load_error')),
                         max_chars=settings.question_chars)
if question and question.strip():
    history = list(st.session_state.messages)
    user_message = {'role': 'user', 'content': question.strip()}
    st.session_state.messages.append(user_message)
    render_message(user_message, len(history))
    try:
        with st.spinner('Querying your data and preparing an answer…'):
            reply = answer_question(question.strip(), history, store, settings, documents)
    except AuthenticationError:
        reply = {'role': 'assistant', 'content': 'OpenAI rejected the API key. Update .env and restart the app.'}
    except RateLimitError:
        reply = {'role': 'assistant', 'content': 'OpenAI rate or quota limit reached. Check your API billing or try again later.'}
    except APIConnectionError:
        reply = {'role': 'assistant', 'content': 'Could not reach OpenAI. Check your connection and try again.'}
    except APIStatusError as error:
        reply = {'role': 'assistant', 'content': f'OpenAI request failed (HTTP {error.status_code}). Check your model access and try again.'}
    except (ValueError, duckdb.Error) as error:
        reply = {'role': 'assistant', 'content': f'I could not safely answer that question: {error}. Try a more specific question.'}
    st.session_state.messages.append(reply)
    render_message(reply, len(st.session_state.messages) - 1)
