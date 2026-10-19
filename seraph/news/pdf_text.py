"""C13 NI08 — time-bounded PDF text extraction in a disposable process.

No OCR or table interpretation is claimed. Preserve page boundaries; report
blank/scanned pages and page/character caps as incomplete text. HTTP retrieval
and its rights checks remain owned by the enrichment caller.
"""
import io
import json
from pathlib import Path
import subprocess
import sys

MAX_BYTES = 8 * 1024 * 1024
MAX_PAGES = 50
MAX_CHARACTERS = 200_000
MAX_PAGE_STREAM = 4 * 1024 * 1024


def _extract(raw):
    from pypdf import PdfReader
    if len(raw) > MAX_BYTES:
        raise ValueError('PDF exceeds 8 MiB limit')
    reader = PdfReader(io.BytesIO(raw))
    if reader.is_encrypted:
        raise ValueError('encrypted PDF unavailable')
    parts, size = [], 0
    incomplete = len(reader.pages) > MAX_PAGES
    for index, page in enumerate(reader.pages[:MAX_PAGES], start=1):
        contents = page.get_contents()
        if contents is not None and len(contents.get_data()) > MAX_PAGE_STREAM:
            raise ValueError('PDF page exceeds extraction stream limit')
        text = page.extract_text() or ''
        if not text.strip():
            incomplete = True
            continue
        parts.append(f'[Page {index}]\n{text}')
        size += len(parts[-1]) + 2
        if size > MAX_CHARACTERS:
            incomplete = True
            break
    if not parts:
        raise ValueError('PDF has no extractable text; OCR required')
    return '\n\n'.join(parts)[:MAX_CHARACTERS], incomplete


def extract_pdf(raw, *, seconds=10):
    if len(raw) > MAX_BYTES:
        raise ValueError('PDF exceeds 8 MiB limit')
    if seconds <= 0:
        raise TimeoutError('PDF extraction deadline exhausted')
    try:
        result = subprocess.run([sys.executable, str(Path(__file__).resolve())],
            input=raw, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=seconds, check=False)
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError('PDF extraction deadline exhausted') from exc
    if result.returncode:
        raise ValueError('PDF extractor failed or required dependency is missing')
    payload = json.loads(result.stdout)
    if payload.get('error'):
        raise ValueError(payload['error'])
    return payload['text'], payload['incomplete']


if __name__ == '__main__':
    try:
        text, incomplete = _extract(sys.stdin.buffer.read(MAX_BYTES+1))
        payload = dict(text=text, incomplete=incomplete)
    except Exception as exc:
        payload = dict(error=f'{type(exc).__name__}: {exc}')
    sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
