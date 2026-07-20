from __future__ import annotations

import logging
import re
from io import BytesIO

logger = logging.getLogger(__name__)

MIN_RESUME_CHARS = 80


def extract_pdf_text(data: bytes) -> str:
    """Extract text from a PDF using PyMuPDF first, then pypdf as fallback."""
    text = ""
    errors: list[str] = []

    try:
        text = _extract_with_pymupdf(data)
    except Exception as exc:
        errors.append(f"pymupdf: {exc}")
        logger.warning("PyMuPDF extraction failed: %s", exc)

    if len(text.strip()) < MIN_RESUME_CHARS:
        try:
            text = _extract_with_pypdf(data)
        except Exception as exc:
            errors.append(f"pypdf: {exc}")
            logger.warning("pypdf extraction failed: %s", exc)

    cleaned = clean_resume_text(text)
    if len(cleaned) < MIN_RESUME_CHARS:
        detail = "; ".join(errors) if errors else "too little extractable text"
        raise ValueError(
            "Could not extract enough text from the PDF resume "
            f"({detail}). Try uploading a text-based PDF or a Markdown/TXT resume."
        )
    return cleaned


def _extract_with_pymupdf(data: bytes) -> str:
    import fitz  # PyMuPDF

    doc = fitz.open(stream=data, filetype="pdf")
    parts: list[str] = []
    try:
        for page in doc:
            # "text" is reading-order; good for most resumes
            parts.append(page.get_text("text") or "")
    finally:
        doc.close()
    return "\n".join(parts)


def _extract_with_pypdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def clean_resume_text(text: str) -> str:
    """Normalize resume text so chunking/embeddings work better."""
    if not text:
        return ""

    # Normalize newlines and non-breaking spaces
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\u200b", "")

    # Fix common PDF ligature / encoding artifacts
    replacements = {
        "ﬁ": "fi",
        "ﬂ": "fl",
        "ﬀ": "ff",
        "ﬃ": "ffi",
        "ﬄ": "ffl",
        "�": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)

    # Join hyphenated line breaks: "recogni-\ntion" -> "recognition"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    # Collapse soft line wraps inside paragraphs (keep blank lines as section breaks)
    lines = [ln.strip() for ln in text.split("\n")]
    paragraphs: list[str] = []
    buf: list[str] = []
    for ln in lines:
        if not ln:
            if buf:
                paragraphs.append(_join_wrapped_lines(buf))
                buf = []
            continue
        buf.append(ln)
    if buf:
        paragraphs.append(_join_wrapped_lines(buf))

    text = "\n\n".join(p for p in paragraphs if p.strip())

    # Promote common resume headings so chunker/retriever can latch onto them
    text = _promote_headings(text)

    # Collapse excessive spaces (but not newlines)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _join_wrapped_lines(lines: list[str]) -> str:
    if not lines:
        return ""
    out = lines[0]
    for ln in lines[1:]:
        # If previous ends mid-sentence / mid-word-ish, join with space
        if out.endswith(("-", "/")):
            out = out[:-1] + ln
        else:
            out = out + " " + ln
    return out.strip()


_HEADING_RE = re.compile(
    r"^(education|experience|work experience|professional experience|employment|"
    r"skills|technical skills|projects|research|publications|certifications|"
    r"certification|summary|profile|objective|awards|leadership)\s*$",
    re.I,
)


def _promote_headings(text: str) -> str:
    lines = text.split("\n")
    out: list[str] = []
    for ln in lines:
        stripped = ln.strip()
        if _HEADING_RE.match(stripped):
            out.append("")
            out.append(f"# {stripped.title()}")
            out.append("")
        else:
            out.append(ln)
    return "\n".join(out)
