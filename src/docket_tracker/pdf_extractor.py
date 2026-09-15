"""Download and extract text from RECAP/CourtListener PDFs.

Only fetches documents CourtListener already hosts for free. It never touches
PACER directly, so it can never incur PACER page fees.
"""
from __future__ import annotations

import hashlib
import io
import logging
import re

import httpx

log = logging.getLogger(__name__)

BASE = "https://www.courtlistener.com"
MAX_BYTES = 25 * 1024 * 1024  # skip anything larger than 25 MB
MAX_CHARS = 120_000           # hard cap on text handed to the model


def absolute(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("http"):
        return url
    if url.startswith("/"):
        return BASE + url
    return f"{BASE}/{url}"


def fetch_pdf(url: str, timeout: float = 60.0) -> bytes | None:
    """Return raw PDF bytes, or None if unavailable."""
    target = absolute(url)
    if not target:
        return None
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(
                target,
                headers={"User-Agent": "court-docket-tracker/2.0"},
            )
        if response.status_code != 200:
            log.warning("PDF fetch returned %s for %s", response.status_code, target)
            return None
        if len(response.content) > MAX_BYTES:
            log.warning("PDF too large (%s bytes), skipping", len(response.content))
            return None
        if not response.content.startswith(b"%PDF"):
            log.warning("Response at %s is not a PDF", target)
            return None
        return response.content
    except Exception as exc:  # network, TLS, redirect loops
        log.warning("PDF fetch failed for %s: %s", target, exc)
        return None


def extract_text(data: bytes) -> tuple[str, int]:
    """Return (clean_text, page_count). Empty text means extraction failed."""
    try:
        from pypdf import PdfReader
    except ImportError:
        log.error("pypdf is not installed; cannot extract PDF text")
        return "", 0

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = len(reader.pages)
        chunks: list[str] = []
        for index, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            if text.strip():
                chunks.append(f"\n[PAGE {index}]\n{text}")
            if sum(len(c) for c in chunks) > MAX_CHARS:
                break
        raw = "".join(chunks)
    except Exception as exc:
        log.warning("PDF parsing failed: %s", exc)
        return "", 0

    cleaned = re.sub(r"[ \t]+", " ", raw)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned[:MAX_CHARS], pages


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_scanned(text: str, pages: int) -> bool:
    """Heuristic: almost no extractable text means the PDF is an image scan."""
    if pages <= 0:
        return False
    return len(text) < 200 * pages * 0.05
