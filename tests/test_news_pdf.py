"""C13 NI08 PDF extraction must preserve evidence and disclose missing pages."""
import io
import subprocess

import pytest
from pypdf import PdfWriter
from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject

from seraph.news.enrichment import extract_article
from seraph.news.http_feed import FeedFetchError
from seraph.news.pdf_text import extract_pdf


def pdf(*, blank=False, extra_blank=False):
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    if not blank:
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
            NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):
            DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        content = DecodedStreamObject()
        content.set_data(b'BT /F1 12 Tf 50 700 Td (The Board adopts the capital rule. '
                         b'The rate increases from 5 percent to 10 percent. '
                         b'The measure takes effect on 18 October 2026.) Tj ET')
        page[NameObject('/Contents')] = writer._add_object(content)
    if extra_blank:
        writer.add_blank_page(width=612, height=792)
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


def test_pdf_text_is_extracted_in_child_with_page_boundaries():
    text, partial = extract_article(pdf(), 'application/pdf')
    assert '[Page 1]' in text and '5 percent to 10 percent' in text
    assert not partial


def test_blank_pdf_reports_ocr_requirement():
    with pytest.raises(FeedFetchError, match='OCR required'):
        extract_article(pdf(blank=True), 'application/pdf')


def test_partially_scanned_pdf_is_not_reported_complete():
    text, partial = extract_article(pdf(extra_blank=True), 'application/pdf')
    assert 'Board' in text and partial


def test_extraction_timeout_does_not_hang_worker(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('pdf', kwargs['timeout'])
    monkeypatch.setattr(subprocess, 'run', timeout)
    with pytest.raises(TimeoutError, match='deadline'):
        extract_pdf(b'%PDF-', seconds=.1)


def test_oversized_pdf_is_rejected_before_spawning(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('spawned'))
    with pytest.raises(ValueError, match='8 MiB'):
        extract_pdf(b' ' * (8*1024*1024+1))
