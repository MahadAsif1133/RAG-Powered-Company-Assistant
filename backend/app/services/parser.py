from __future__ import annotations

import io
import logging
import mimetypes
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED_TYPES = {".pdf", ".docx", ".txt", ".doc"}


def parse_document(content: bytes, filename: str) -> str:
    """
    Parse a document (PDF, DOCX, TXT) into plain text.

    Strategy (per file type):
      PDF  → try `unstructured` first → fall back to `pypdf`
      DOCX → try `unstructured` first → fall back to `python-docx`
      TXT  → decode directly (UTF-8 with errors='replace')

    Returns a single plain-text string. Raises ValueError for unsupported types.
    """
    suffix = Path(filename).suffix.lower()

    if suffix not in SUPPORTED_TYPES:
        raise ValueError(
            f"Unsupported file type: '{suffix}'. Supported: {', '.join(SUPPORTED_TYPES)}"
        )

    if suffix == ".txt":
        return content.decode("utf-8", errors="replace").strip()

    if suffix == ".pdf":
        return _parse_pdf(content, filename)

    if suffix in {".docx", ".doc"}:
        return _parse_docx(content, filename)

    raise ValueError(f"Unhandled extension: {suffix}")


# ── PDF ──────────────────────────────────────────────────────

def _parse_pdf(content: bytes, filename: str) -> str:
    """Try unstructured; fall back to pypdf."""
    text = _parse_pdf_unstructured(content, filename)
    if text and len(text.strip()) > 50:
        return text

    logger.info("Falling back to pypdf for '%s'", filename)
    return _parse_pdf_pypdf(content)


def _parse_pdf_unstructured(content: bytes, filename: str) -> str:
    try:
        from unstructured.partition.pdf import partition_pdf  # type: ignore

        elements = partition_pdf(file=io.BytesIO(content))
        return "\n\n".join(str(el) for el in elements if str(el).strip())
    except Exception as exc:
        logger.warning("unstructured PDF parse failed for '%s': %s", filename, exc)
        return ""


def _parse_pdf_pypdf(content: bytes) -> str:
    try:
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(content))
        pages = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages.append(page_text.strip())
        return "\n\n".join(pages)
    except Exception as exc:
        logger.error("pypdf parse failed: %s", exc)
        return ""


# ── DOCX ─────────────────────────────────────────────────────

def _parse_docx(content: bytes, filename: str) -> str:
    """Try unstructured; fall back to python-docx."""
    text = _parse_docx_unstructured(content, filename)
    if text and len(text.strip()) > 50:
        return text

    logger.info("Falling back to python-docx for '%s'", filename)
    return _parse_docx_python_docx(content)


def _parse_docx_unstructured(content: bytes, filename: str) -> str:
    try:
        from unstructured.partition.docx import partition_docx  # type: ignore

        elements = partition_docx(file=io.BytesIO(content))
        return "\n\n".join(str(el) for el in elements if str(el).strip())
    except Exception as exc:
        logger.warning("unstructured DOCX parse failed for '%s': %s", filename, exc)
        return ""


def _parse_docx_python_docx(content: bytes) -> str:
    try:
        import docx  # python-docx

        doc = docx.Document(io.BytesIO(content))
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    except Exception as exc:
        logger.error("python-docx parse failed: %s", exc)
        return ""
