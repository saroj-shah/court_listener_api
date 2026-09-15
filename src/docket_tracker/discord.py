from __future__ import annotations
import time
from datetime import datetime, timezone
import httpx
from .models import DocketEntry, Assessment

COLORS = {"HIGH": 0xD83C3E, "MEDIUM": 0xF0A500, "LOW": 0x95A5A6}

def build_payload(case: dict, entry: DocketEntry, a: Assessment, change: str) -> dict:
    base = "https://www.courtlistener.com"
    entry_url = entry.absolute_url or case["docket_url"]
    if entry_url.startswith("/"):
        entry_url = base + entry_url
    doc_links = []
    for d in entry.documents[:5]:
        url = d.download_url or d.absolute_url
        if url and url.startswith("/"):
            url = base + url
        if url:
            doc_links.append(f"[{d.description[:60]}]({url})")
    fields = [
        {"name": "Classification", "value": a.category.replace("_", " "), "inline": True},
        {"name": "Impact", "value": a.impact, "inline": True},
        {"name": "Confidence", "value": a.confidence, "inline": True},
        {"name": "Summary", "value": a.summary[:1000] or "No description supplied.", "inline": False},
        {"name": "Major points", "value": "\n".join(f"• {p}" for p in a.major_points)[:1000], "inline": False},
        {"name": "Why it matters", "value": a.why_it_matters[:1000], "inline": False},
        {"name": "Sources", "value": f"[Docket entry]({entry_url}) | [Case docket]({case['docket_url']})" + (("\n" + " | ".join(doc_links)) if doc_links else "\nPDF not available through the API."), "inline": False},
    ]
    return {"content": "@here" if a.impact == "HIGH" and a.court_decision else "",
            "allowed_mentions": {"parse": ["everyone"] if a.impact == "HIGH" and a.court_decision else []},
            "embeds": [{"title": f"{case['short_name']} | Entry {entry.entry_number} | {a.impact}",
                        "url": entry_url, "description": f"**{a.title}**\nFiled: {entry.date_filed}\nUpdate type: {change}",
                        "color": COLORS[a.impact], "fields": fields,
                        "footer": {"text": "Automated informational summary, not legal advice."},
                        "timestamp": datetime.now(timezone.utc).isoformat()}]}

def send(webhook_url: str, payload: dict):
    for attempt in range(4):
        r = httpx.post(webhook_url, params={"wait": "true"}, json=payload, timeout=30)
        if r.status_code == 429:
            wait = float(r.json().get("retry_after", 1))
            time.sleep(min(wait, 60)); continue
        if r.status_code >= 500:
            time.sleep(2 ** attempt); continue
        r.raise_for_status(); return
    raise RuntimeError("Discord delivery failed after retries")
