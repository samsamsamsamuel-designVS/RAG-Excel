"""Presentation-only styling for the grey and orange workspace."""
from pathlib import Path

import streamlit as st


def apply_theme():
    # Keep app behavior in app.py and the visual styling in one editable file.
    css = Path(__file__).with_name('styles.css').read_text()
    st.html(f'<style>{css}</style>')


def render_brand():
    st.html('<div class="workspace-brand"><span class="brand-bars" aria-hidden="true">'
            '<i></i><i></i><i></i></span><span>Data &amp; Knowledge</span></div>'
            '<div class="workspace-label">WORKSPACE</div>')


def render_header():
    st.html('<div class="workspace-breadcrumb">Workspace <span>/</span> <b>Chat</b></div>'
            '<h1 class="workspace-title">Chat with your data</h1>'
            '<p class="workspace-subtitle">Turn spreadsheets and policies into clear answers.</p>')


def render_status(store, documents, ready):
    tables = len(store.tables) if store else 0
    pdfs = len(documents.documents) if documents else 0
    rows = sum(t['rows'] for t in store.tables) if store else 0
    status = 'Ready' if ready else 'Add files to begin' if not (tables or pdfs) else 'Setup needed'
    st.html(f'<div class="workspace-status"><div class="source-chips">'
            f'<span class="source-chip">{tables} data {"table" if tables == 1 else "tables"}</span>'
            f'<span class="source-chip">{pdfs} PDF {"policy" if pdfs == 1 else "policies"}</span>'
            f'<span class="row-count">{rows:,} rows</span></div>'
            f'<span class="ready-badge"><span aria-hidden="true">●</span> {status}</span></div>')


def render_empty_state():
    st.html('<div class="empty-workspace"><span class="empty-symbol" aria-hidden="true">↗</span>'
            '<h2>Your next answer starts here.</h2>'
            '<p>Add a spreadsheet to explore your data. Include a PDF documents to put the results in context.</p>')
