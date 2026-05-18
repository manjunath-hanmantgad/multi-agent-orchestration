"""Document parsing service for supported file types."""

from __future__ import annotations

import logging
from pathlib import Path

import pdfplumber
from docx import Document

logger = logging.getLogger(__name__)


class DocumentParserError(RuntimeError):
    """Raised when document parsing fails."""


class UnsupportedFileTypeError(DocumentParserError):
    """Raised when parser receives an unsupported file type."""


class DocumentParser:
    """Extract text and metadata from PDF, DOCX, and TXT files."""

    def parse(self, file_path: str) -> dict[str, object]:
        """Parse supported file and return text with metadata."""
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise DocumentParserError(f"File not found: {file_path}")
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            text, page_count = _parse_pdf(path)
        elif suffix == ".docx":
            text, page_count = _parse_docx(path)
        elif suffix == ".txt":
            text, page_count = _parse_txt(path)
        else:
            raise UnsupportedFileTypeError(f"Unsupported file type: {suffix or 'unknown'}")
        return {
            "text": text,
            "metadata": {
                "page_count": page_count,
                "file_type": suffix.lstrip("."),
                "size_bytes": path.stat().st_size,
            },
        }


def _parse_pdf(path: Path) -> tuple[str, int]:
    """Extract text and page count from PDF."""
    try:
        with pdfplumber.open(path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages).strip(), len(pages)
    except (OSError, ValueError) as exc:
        logger.exception(
            "document_parse_failed workflow_id=%s stage=%s error_type=%s",
            "-",
            "pdf",
            type(exc).__name__,
        )
        raise DocumentParserError(f"Failed to parse PDF: {path}") from exc


def _parse_docx(path: Path) -> tuple[str, int]:
    """Extract text and section count from DOCX."""
    try:
        doc = Document(path)
        lines = [paragraph.text for paragraph in doc.paragraphs if paragraph.text]
        page_count = max(1, len(doc.sections))
        return "\n".join(lines).strip(), page_count
    except (OSError, ValueError) as exc:
        logger.exception(
            "document_parse_failed workflow_id=%s stage=%s error_type=%s",
            "-",
            "docx",
            type(exc).__name__,
        )
        raise DocumentParserError(f"Failed to parse DOCX: {path}") from exc


def _parse_txt(path: Path) -> tuple[str, int]:
    """Extract text from plain text files."""
    try:
        text = path.read_text(encoding="utf-8")
        page_count = max(1, text.count("\f") + 1)
        return text.strip(), page_count
    except OSError as exc:
        logger.exception(
            "document_parse_failed workflow_id=%s stage=%s error_type=%s",
            "-",
            "txt",
            type(exc).__name__,
        )
        raise DocumentParserError(f"Failed to parse TXT: {path}") from exc
