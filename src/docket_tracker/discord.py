from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx

from .models import Assessment, DocketEntry

BASE = "https://www.courtlistener.com"
COLORS = {"HIGH": 0xD83C3E, "MEDIUM": 0xF0A500, "LOW": 0x95A5A6}
DOTS = {"HIGH": "\U0001F534", "MEDIUM": "\U0001F7E0", "LOW": "\u26AA"}


def _abs(url: str | None) -> str | None:
    if not url:
        return None
    return url if url.startswith("http") else BASE + url


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "\u2026"


def build_payload(case: dict, entry: DocketEntry, a: Assessment, change: str) -> dict:
    entry_url = _abs(entry.absolute_url) or case["docket_url"]

    links = []
    for d in entry.documents[:4]:
        url = _abs(d.download_url or d.absolute_url)
        if url:
            label = _clip(d.description or "Document", 45)
            links.append(f"[{label}]({url})")

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
        analysis = "Docket text only \u2014 PDF not analyzed"
    fields.append({"name": "Analysis", "value": analysis, "inline": True})

    sources = f"[Docket entry]({entry_url}) \u2022 [Full docket]({case['docket_url']})"
    sources += "\n" + (" \u2022 ".join(links) if links else "PDF not yet available on CourtListener.")
    fields.append({"name": "Sources", "value": _clip(sources, 1024), "inline": False})

    escalate = a.impact == "HIGH" and a.court_decision
    return {
        "content": "@here" if escalate else "",
        "allowed_mentions": {"parse": ["everyone"] if escalate else []},
        "embeds": [{
            "title": _clip(f"{case['short_name']} \u2014 Entry {entry.entry_number}", 250),
            "url": entry_url,
            "description": _clip(
                f"**{a.title}**\nFiled: {entry.date_filed}  \u2022  Update: {change}", 400
            ),
            "color": COLORS[a.impact],
            "fields": fields,
            "footer": {"text": "Automated informational summary \u2014 not legal advice."},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
    }


def send(webhook_url: str, payload: dict) -> None:
    for attempt in range(4):
        response = httpx.post(webhook_url, params={"wait": "true"}, json=payload, timeout=30)
        if response.status_code == 429:
            wait = float(response.json().get("retry_after", 1))
            time.sleep(min(wait, 60))
            continue
        if response.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        response.raise_for_status()
        return
    raise RuntimeError("Discord delivery failed after retries")
