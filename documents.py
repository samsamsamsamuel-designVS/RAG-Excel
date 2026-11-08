"""Extract page-cited PDF passages and retrieve context locally, without uploads to a vector service."""
import io
import json
import math
import re
from collections import Counter

from pypdf import PdfReader

from config import Settings


def terms(text):
    return re.findall(r'\w+', text.lower())


def split_paragraphs(text: str) -> list[str]:
    """Keep paragraph boundaries; split unusually long blocks without overlap."""
    paragraphs = []
    for block in re.split(r'\n\s*\n', text):
        block = block.strip()
        while len(block) > 1800:
            # Prefer a sentence boundary, then a line/word boundary for dense PDFs.
            cut = block.rfind('. ', 600, 1800)
            cut = cut + 1 if cut != -1 else max(block.rfind('\n', 600, 1800), block.rfind(' ', 600, 1800))
            cut = cut if cut > 0 else 1800
            paragraphs.append(block[:cut].strip())
            block = block[cut:].strip()
        if block:
            paragraphs.append(block)
    return paragraphs


class DocumentStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.chunks = []
        self.documents = []
        self.warnings = []

    def load(self, uploads: list[tuple[str, bytes]]):
        if len(uploads) > self.settings.max_pdf_files:
            raise ValueError(f'Upload at most {self.settings.max_pdf_files} PDF files.')
        total_chars = 0
        for file_index, (filename, content) in enumerate(uploads, 1):
            if len(content) > self.settings.max_file_mb * 1024 * 1024:
                raise ValueError(f'{filename}: exceeds the file size limit.')
            if not content.startswith(b'%PDF-'):
                raise ValueError(f'{filename}: not a valid PDF file.')
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted:
                raise ValueError(f'{filename}: upload an unencrypted copy.')
            if len(reader.pages) > self.settings.max_pdf_pages:
                raise ValueError(f'{filename}: exceeds MAX_PDF_PAGES.')
            count_before = len(self.chunks)
            for page_number, page in enumerate(reader.pages, 1):
                text = (page.extract_text(extraction_mode='layout') or '').strip()
                if not text:
                    self.warnings.append(f'{filename}, page {page_number}: no readable text; images/scans require OCR.')
                    continue
                total_chars += len(text)
                if total_chars > self.settings.max_pdf_chars:
                    raise ValueError('PDF text exceeds MAX_PDF_CHARS. Upload fewer or shorter documents.')
                # Paragraph IDs let the UI show precise evidence, not whole documents.
                for paragraph_number, paragraph in enumerate(split_paragraphs(text), 1):
                    self.chunks.append({'id': f'PDF{file_index}-p{page_number}-para{paragraph_number}',
                                        'file': filename, 'page': page_number,
                                        'text': paragraph})
            if len(self.chunks) == count_before:
                raise ValueError(f'{filename}: no extractable text. Run OCR and upload a searchable PDF.')
            self.documents.append({'file': filename, 'pages': len(reader.pages)})

    def retrieve(self, question: str, history: list) -> dict:
        """Use all passages for short policies; rank longer collections with BM25."""
        budget = self.settings.pdf_context_chars
        if len(json.dumps(self.chunks)) <= budget:
            return {'passages': self.chunks, 'partial': False, 'warnings': self.warnings}
        # Recent user questions help resolve follow-ups like "Now only Sales".
        query = question + ' ' + ' '.join(m['content'] for m in history[-4:] if m['role'] == 'user')
        query_terms = set(terms(query))
        counts = [Counter(terms(chunk['text'] + ' ' + chunk['file'])) for chunk in self.chunks]
        average = sum(sum(c.values()) for c in counts) / max(1, len(counts))
        frequencies = Counter(term for c in counts for term in c)

        def score(index):
            c = counts[index]
            length = sum(c.values())
            return sum(math.log(1 + (len(counts) - frequencies[t] + .5) / (frequencies[t] + .5))
                       * c[t] * 2.5 / (c[t] + 1.5 * (.25 + .75 * length / average))
                       for t in query_terms if c[t])

        selected, used = [], 2
        for index in sorted(range(len(counts)), key=score, reverse=True):
            chunk = self.chunks[index]
            size = len(json.dumps(chunk)) + 2
            if used + size <= budget:
                selected.append(chunk)
                used += size
        if not selected:
            raise ValueError('PDF_CONTEXT_CHARS is too small for a document passage.')
        return {'passages': selected, 'partial': True, 'warnings': self.warnings}
