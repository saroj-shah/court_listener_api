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

WWW = "https://www.courtlistener.com"
STORAGE = "https://storage.courtlistener.com"
MAX_DOWNLOAD = 40 * 1024 * 1024
MAX_CHARS = 120_000

# CourtListener rejects plain scripted hotlinks to www/recap with 403.
# A browser-like UA plus the storage host is what actually works.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36 court-docket-tracker/3.1"
)


def absolute(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("http"):
        return url
    return f"{WWW}/{url.lstrip('/')}"


def candidate_urls(raw: str | None) -> list[str]:
    """Build an ordered list of URLs to try for one document.

    `filepath_local` comes back as a bare path like
    `recap/gov.uscourts.nysd.657161/gov.uscourts.nysd.657161.87.0.pdf`.
    That path is served from storage.courtlistener.com; requesting it from
    www.courtlistener.com returns 403 for scripted clients.
    """
    if not raw:
        return []

    if raw.startswith("http"):
        urls = [raw]
        if "www.courtlistener.com/recap/" in raw:
            urls.append(raw.replace("https://www.courtlistener.com/", f"{STORAGE}/"))
        return urls

    path = raw.lstrip("/")
    return [f"{STORAGE}/{path}", f"{WWW}/{path}"]


def fetch_pdf(
    raw_url: str,
    token: str | None = None,
    timeout: float = 90.0,
) -> tuple[bytes | None, str | None]:
    """Try each candidate URL. Return (pdf_bytes, working_url)."""
    headers = {
        "User-Agent": BROWSER_UA,
        "Accept": "application/pdf,*/*",
        "Referer": WWW + "/",
    }
    if token:
        headers["Authorization"] = f"Token {token}"

    last_status = None
    for url in candidate_urls(raw_url):
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                response = client.get(url, headers=headers)
        except Exception as exc:
            log.warning("PDF fetch error for %s: %s", url, exc)
            continue

        last_status = response.status_code
        if response.status_code != 200:
            log.info("PDF fetch %s for %s", response.status_code, url)
            continue
        if len(response.content) > MAX_DOWNLOAD:
            log.warning("PDF too large (%s bytes) at %s", len(response.content), url)
            return None, url
        if not response.content.startswith(b"%PDF"):
            log.info("Response at %s is not a PDF", url)
            continue
        return response.content, url

    log.warning("All PDF candidates failed for %s (last status %s)", raw_url, last_status)
    return None, absolute(raw_url)


def pick_document(documents: list[Document]) -> tuple[Document | None, str]:
    if not documents:
        return None, PdfStatus.NONE_LISTED

    available = [d for d in documents if d.is_available and d.download_url]
    if not available:
        return documents[0], PdfStatus.NOT_AVAILABLE

    best = max(available, key=lambda d: (d.page_count or 0, d.file_size or 0))
    return best, "available"


def extract_text(data: bytes) -> tuple[str, int]:
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
    if pages <= 0:
        return False
    return len(text.strip()) < 10 * pages


def resolve(documents: list[Document], token: str | None = None) -> PdfStatus:
    """Full pipeline: pick -> download -> extract -> classify state."""
    document, state = pick_document(documents)

    if state in {PdfStatus.NONE_LISTED, PdfStatus.NOT_AVAILABLE}:
        return PdfStatus(
            state=state,
            document=document,
            url=absolute(document.absolute_url) if document else None,
        )

    data, working_url = fetch_pdf(document.download_url, token=token)
    if not data:
        return PdfStatus(
            state=PdfStatus.DOWNLOAD_FAILED,
            document=document,
            url=absolute(document.absolute_url) or working_url,
        )

    text, pages = extract_text(data)
    scanned = is_scanned(text, pages)
    return PdfStatus(
        state=PdfStatus.SCANNED if scanned else PdfStatus.TEXT_READY,
        document=document,
        data=data,
        text="" if scanned else text,
        pages=pages,
        size=len(data),
        url=working_url,
        sha256=content_hash(data),
    )


def safe_filename(entry_number, description) -> str:
    """Filesystem-safe PDF filename. Accepts non-string inputs defensively."""
    entry_number = str(entry_number if entry_number is not None else "unknown")
    description = str(description) if description is not None else ""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", description or "document").strip("-").lower()
    slug = slug[:50] or "document"
    entry_slug = re.sub(r"[^A-Za-z0-9]+", "-", entry_number).strip("-") or "unknown"
    return f"entry-{entry_slug}-{slug}.pdf"
