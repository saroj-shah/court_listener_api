"""Grounded AI summarization of court filings.

Safety design:
  1. The model only sees text extracted from the filed PDF.
  2. Output is constrained to a strict JSON schema.
  3. Every point must carry a verbatim quote from the source.
  4. Quotes that do not appear in the source are deleted.
  5. If all points fail, the AI result is discarded for the rule-based one.
  6. The model may never predict outcomes.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time

import httpx

log = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5.6-terra"
API_URL = "https://api.openai.com/v1/responses"

SYSTEM_PROMPT = """You are a legal docket analyst producing factual, neutral summaries of \
US federal court filings for a notification system.

STRICT RULES:
- Describe ONLY what the supplied document text says. Never use outside knowledge.
- Never predict how a judge will rule or what will happen next.
- Carefully distinguish: (a) what a PARTY argues or requests, versus (b) what the
  COURT has actually ordered or decided. Never describe a party's motion as a ruling.
- Every major point must include a short verbatim `evidence` quote copied EXACTLY
  from the document text, 10-25 words long.
- If the text does not support a field, return an empty string or empty list.
- Write plainly. No legal advice. No speculation.

IMPACT RUBRIC:
- HIGH: the COURT granted/denied consequential relief - injunction, stay, TRO,
  final judgment, dismissal, vacatur, remand, class certification, summary judgment,
  or an order imposing binding compliance obligations.
- MEDIUM: a party REQUESTS consequential relief; notice of appeal; substantive
  briefing; implementation/status report; hearing or meaningful scheduling change.
- LOW: routine administration - appearance, service, transcript, summons,
  redaction, clerical correction, fee entry.

A motion to stay is MEDIUM. An order granting or denying that stay is HIGH."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "document_type", "classification", "impact", "confidence",
        "short_description", "major_points", "why_it_matters",
        "deadlines", "court_decision", "party_request",
    ],
    "properties": {
        "document_type": {"type": "string"},
        "classification": {
            "type": "string",
            "enum": [
                "DECISION_OR_ORDER", "EMERGENCY_RELIEF", "STAY_OR_INJUNCTION",
                "APPEAL", "MERITS_BRIEFING", "IMPLEMENTATION_OR_COMPLIANCE",
                "EVIDENCE_OR_DECLARATION", "SCHEDULING", "TRANSCRIPT",
                "ADMINISTRATIVE", "UNKNOWN",
            ],
        },
        "impact": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
        "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
        "short_description": {"type": "string"},
        "major_points": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["point", "evidence"],
                "properties": {
                    "point": {"type": "string"},
                    "evidence": {"type": "string"},
                },
            },
        },
        "why_it_matters": {"type": "string"},
        "deadlines": {"type": "array", "maxItems": 5, "items": {"type": "string"}},
        "court_decision": {"type": "boolean"},
        "party_request": {"type": "boolean"},
    },
}


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", re.sub(r"\s+", " ", text.lower())).strip()


def verify(result: dict, source_text: str) -> tuple[dict, float]:
    """Drop unsupported points. Return (filtered_result, grounding_ratio)."""
    haystack = _normalize(source_text)
    points = result.get("major_points") or []
    kept = []
    for item in points:
        quote = _normalize(item.get("evidence", ""))
        words = quote.split()
        if len(words) < 4:
            continue
        if quote in haystack or " ".join(words[:8]) in haystack:
            kept.append(item)
    ratio = len(kept) / len(points) if points else 0.0
    result["major_points"] = kept
    return result, ratio


def summarize(
    document_text: str,
    entry_description: str,
    case_name: str,
    api_key: str,
    model: str | None = None,
    timeout: float = 120.0,
) -> dict | None:
    if not api_key or not document_text or len(document_text) < 400:
        return None

    model = model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
    user_content = (
        f"CASE: {case_name}\n"
        f"DOCKET ENTRY DESCRIPTION: {entry_description or 'Not provided'}\n\n"
        f"--- BEGIN DOCUMENT TEXT ---\n{document_text}\n--- END DOCUMENT TEXT ---"
    )
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "docket_filing_summary",
                "strict": True,
                "schema": SCHEMA,
            }
        },
    }

    raw = None
    for attempt in range(3):
        try:
            response = httpx.post(
                API_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=timeout,
            )
        except Exception as exc:
            log.warning("AI request error: %s", exc)
            time.sleep(2 ** attempt)
            continue

        if response.status_code == 429 or response.status_code >= 500:
            time.sleep(float(response.headers.get("retry-after", 2 ** attempt)))
            continue
        if response.status_code != 200:
            log.error("AI request failed %s: %s", response.status_code, response.text[:400])
            return None
        raw = response.json()
        break

    if raw is None:
        return None

    text = raw.get("output_text")
    if not text:
        fragments = []
        for block in raw.get("output", []):
            for piece in block.get("content", []) or []:
                if piece.get("type") in {"output_text", "text"} and piece.get("text"):
                    fragments.append(piece["text"])
        text = "".join(fragments)
    if not text:
        log.error("AI response contained no text output")
        return None

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        log.error("AI returned non-JSON output")
        return None

    result, ratio = verify(result, document_text)
    if not result["major_points"]:
        log.warning("All AI points failed grounding; discarding AI summary")
        return None
    if ratio < 0.5:
        result["confidence"] = "LOW"

    if result.get("party_request") and not result.get("court_decision"):
        if result.get("impact") == "HIGH":
            result["impact"] = "MEDIUM"

    result["_grounding_ratio"] = round(ratio, 2)
    result["_model"] = model
    return result
