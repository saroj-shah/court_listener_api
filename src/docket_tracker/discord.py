from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import httpx

from .models import Assessment, DocketEntry, PdfStatus
from .pdf_extractor import safe_filename

log = logging.getLogger(__name__)

BASE = "https://www.courtlistener.com"
COLORS = {"HIGH": 0xD83C3E, "MEDIUM": 0xF0A500, "LOW": 0x95A5A6}
DOTS = {"HIGH": "\U0001F534", "MEDIUM": "\U0001F7E0", "LOW": "\u26AA"}

# Discord's default upload ceiling for a non-boosted server is 10 MB.
# Stay under it so the multipart POST is never rejected.
DEFAULT_UPLOAD_LIMIT = 8 * 1024 * 1024


def _abs(url: str | None) -> str | None:
    if not url:
        return None
    return url if url.startswith("http") else BASE + url


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "\u2026"


def _human_size(num: int) -> str:
    if num <= 0:
        return "unknown size"
    mb = num / (1024 * 1024)
    return f"{mb:.1f} MB" if mb >= 0.1 else f"{num // 1024} KB"


def describe_pdf(pdf: PdfStatus, attached: bool, upload_limit: int) -> str:
    """Human-readable, honest statement of document availability."""
    if pdf.state == PdfStatus.NONE_LISTED:
        return "\u274C **Not available** \u2014 no document attached to this docket entry."
    if pdf.state == PdfStatus.NOT_AVAILABLE:
        line = "\u274C **Not available** \u2014 listed on the docket, but no free copy in RECAP yet."
        if pdf.url:
            line += f"\n[View entry on CourtListener]({pdf.url})"
        return line
    if pdf.state == PdfStatus.DOWNLOAD_FAILED:
        line = "\u26A0\uFE0F **Download failed** \u2014 marked available but could not be retrieved."
        if pdf.url:
            line += f"\n[Try directly]({pdf.url})"
        return line

    size = _human_size(pdf.size)
    pages = f"{pdf.pages} page{'s' if pdf.pages != 1 else ''}" if pdf.pages else "unknown length"

    if pdf.state == PdfStatus.SCANNED:
        head = f"\u26A0\uFE0F **Available, but scanned** \u2014 {pages}, {size}. No text layer, so it was not summarized."
    else:
        head = f"\u2705 **Available** \u2014 {pages}, {size}. Text extracted and summarized."

    if attached:
        head += "\nPDF attached to this message."
    elif pdf.size > upload_limit:
        head += f"\nToo large to attach (limit {_human_size(upload_limit)}); use the link below."

    if pdf.url:
        head += f"\n[Download PDF]({pdf.url})"
    return head


def build_embed(
    case: dict,
    entry: DocketEntry,
    a: Assessment,
    change: str,
    pdf: PdfStatus,
    attached: bool,
    upload_limit: int,
) -> dict:
    entry_url = _abs(entry.absolute_url) or case["docket_url"]

    fields = [
        {"name": "Classification", "value": a.category.replace("_", " ").title(), "inline": True},
        {"name": "Impact", "value": f"{DOTS[a.impact]} {a.impact}", "inline": True},
        {"name": "Confidence", "value": a.confidence, "inline": True},
        {"name": "Summary", "value": _clip(a.summary, 1000) or "No description supplied.", "inline": False},
    ]

    if a.major_points:
        fields.append({
            "name": "Key points",
            "value": _clip("\n".join(f"\u2022 {p}" for p in a.major_points), 1024),
            "inline": False,
        })
    if a.deadlines:
        fields.append({
            "name": "Dates and deadlines mentioned",
            "value": _clip("\n".join(f"\u2022 {d}" for d in a.deadlines), 512),
            "inline": False,
        })
    if a.why_it_matters:
        fields.append({"name": "Why it matters", "value": _clip(a.why_it_matters, 700), "inline": False})

    fields.append({
        "name": "Document",
        "value": _clip(describe_pdf(pdf, attached, upload_limit), 1024),
        "inline": False,
    })

    posture = (
        "Court decision" if a.court_decision
        else "Party request \u2014 not a ruling" if a.party_request
        else "Docket activity"
    )
    fields.append({"name": "Posture", "value": posture, "inline": True})

    if a.source == "ai":
        analysis = f"AI summary of filed PDF ({a.model})"
        if a.grounding is not None:
            analysis += f"\nQuote verification: {int(a.grounding * 100)}%"
    else:
        analysis = "Docket text only \u2014 PDF not summarized"
    fields.append({"name": "Analysis", "value": analysis, "inline": True})

    fields.append({
        "name": "Sources",
        "value": _clip(f"[Docket entry]({entry_url}) \u2022 [Full docket]({case['docket_url']})", 1024),
        "inline": False,
    })

    return {
        "title": _clip(f"{case['short_name']} \u2014 Entry {entry.entry_number}", 250),
        "url": entry_url,
        "description": _clip(
            f"**{a.title}**\nFiled: {entry.date_filed}  \u2022  Update: {change}", 400
        ),
        "color": COLORS[a.impact],
        "fields": fields,
        "footer": {"text": "Automated informational summary \u2014 not legal advice."},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def build_payload(
    case: dict,
    entry: DocketEntry,
    a: Assessment,
    change: str,
    pdf: PdfStatus | None = None,
    upload_limit: int = DEFAULT_UPLOAD_LIMIT,
) -> tuple[dict, bytes | None, str | None]:
    """Return (payload, file_bytes, filename). file_bytes is None when nothing is attached."""
    pdf = pdf or PdfStatus(state=PdfStatus.NONE_LISTED)

    attach = bool(pdf.data) and 0 < pdf.size <= upload_limit
    filename = safe_filename(entry.entry_number, pdf.document.description if pdf.document else "")

    escalate = a.impact == "HIGH" and a.court_decision
    payload = {
        "content": "@here" if escalate else "",
        "allowed_mentions": {"parse": ["everyone"] if escalate else []},
        "embeds": [build_embed(case, entry, a, change, pdf, attach, upload_limit)],
    }
    if attach:
        payload["attachments"] = [{"id": 0, "filename": filename}]

    return payload, (pdf.data if attach else None), (filename if attach else None)


def send(
    webhook_url: str,
    payload: dict,
    file_bytes: bytes | None = None,
    filename: str | None = None,
) -> None:
    """Post to Discord. Uses multipart when a PDF is attached."""
    for attempt in range(4):
        try:
            if file_bytes and filename:
                response = httpx.post(
                    webhook_url,
                    params={"wait": "true"},
                    data={"payload_json": json.dumps(payload)},
                    files={"files[0]": (filename, file_bytes, "application/pdf")},
                    timeout=120,
                )
            else:
                response = httpx.post(
                    webhook_url, params={"wait": "true"}, json=payload, timeout=30
                )
        except Exception as exc:
            log.warning("Discord post error: %s", exc)
            time.sleep(2 ** attempt)
            continue

        if response.status_code == 429:
            try:
                wait = float(response.json().get("retry_after", 1))
            except Exception:
                wait = 2 ** attempt
            time.sleep(min(wait, 60))
            continue
        if response.status_code == 413 and file_bytes:
            # Attachment rejected as too large: retry without the file.
            log.warning("Discord rejected the attachment as too large; sending links only")
            payload.pop("attachments", None)
            return send(webhook_url, payload)
        if response.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        response.raise_for_status()
        return
    raise RuntimeError("Discord delivery failed after retries")
