"""Download and extract text from CourtListener/RECAP PDFs.

Only fetches documents CourtListener already hosts for free. Never touches
PACER directly, so it can never incur PACER page fees.
"""
from __future__ import annotations

import hashlib
import io
import logging
import re

import httpx

from .models import Document, PdfStatus

log = logging.getLogger(__name__)

BASE = "https://www.courtlistener.com"
MAX_DOWNLOAD = 40 * 1024 * 1024   # refuse to download beyond this
MAX_CHARS = 120_000               # hard cap on text handed to the model


def absolute(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("http"):
        return url
    if url.startswith("/"):
        return BASE + url
    return f"{BASE}/{url}"


def pick_document(documents: list[Document]) -> tuple[Document | None, str]:
    """Choose the best document and report availability.

    Returns (document, state) where state is a PdfStatus constant.
    """
    if not documents:
        return None, PdfStatus.NONE_LISTED

    available = [d for d in documents if d.is_available and d.download_url]
    if not available:
        # Documents exist on the docket but RECAP has no free copy.
        return documents[0], PdfStatus.NOT_AVAILABLE

    best = max(available, key=lambda d: (d.page_count or 0, d.file_size or 0))
    return best, "available"


def fetch_pdf(url: str, timeout: float = 90.0) -> bytes | None:
    target = absolute(url)
    if not target:
        return None
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(target, headers={"User-Agent": "court-docket-tracker/3.0"})
        if response.status_code != 200:
            log.warning("PDF fetch returned %s for %s", response.status_code, target)
            return None
        if len(response.content) > MAX_DOWNLOAD:
            log.warning("PDF too large (%s bytes)", len(response.content))
            return None
        if not response.content.startswith(b"%PDF"):
            log.warning("Response at %s is not a PDF", target)
            return None
        return response.content
    except Exception as exc:
        log.warning("PDF fetch failed for %s: %s", target, exc)
        return None


def extract_text(data: bytes) -> tuple[str, int]:
    """Return (clean_text, page_count). Empty text means extraction failed."""
    try:
        from pypdf import PdfReader
    except ImportError:
        log.error("pypdf is not installed")
        return "", 0

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = len(reader.pages)
        chunks: list[str] = []
        total = 0
        for index, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            if text.strip():
                chunk = f"\n[PAGE {index}]\n{text}"
                chunks.append(chunk)
                total += len(chunk)
            if total > MAX_CHARS:
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
    """Almost no extractable text means the PDF is an image scan."""
    if pages <= 0:
        return False
    return len(text.strip()) < 10 * pages


def resolve(documents: list[Document]) -> PdfStatus:
    """Full pipeline: pick -> download -> extract -> classify state."""
    document, state = pick_document(documents)

    if state in {PdfStatus.NONE_LISTED, PdfStatus.NOT_AVAILABLE}:
        return PdfStatus(
            state=state,
            document=document,
            url=absolute(document.absolute_url) if document else None,
        )

    url = absolute(document.download_url)
    data = fetch_pdf(document.download_url)
    if not data:
        return PdfStatus(state=PdfStatus.DOWNLOAD_FAILED, document=document, url=url)

    text, pages = extract_text(data)
    scanned = is_scanned(text, pages)
    return PdfStatus(
        state=PdfStatus.SCANNED if scanned else PdfStatus.TEXT_READY,
        document=document,
        data=data,
        text="" if scanned else text,
        pages=pages,
        size=len(data),
        url=url,
        sha256=content_hash(data),
    )


def safe_filename(entry_number: str, description: str) -> str:
    """Build a readable, filesystem-safe PDF filename for the Discord upload."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", (description or "document")).strip("-").lower()
    slug = slug[:50] or "document"
    return f"entry-{entry_number}-{slug}.pdf"
