"""Deterministic fallback classifier, used when no PDF text or AI is available."""
from __future__ import annotations

import re

from .models import Assessment, DocketEntry

HIGH_DECISIONS = (
    "final judgment", "preliminary injunction", "temporary restraining order",
    "stay is granted", "stay is denied", "motion is granted", "motion is denied",
    "vacated", "vacatur", "dismissed", "class certification", "summary judgment",
    "remanded", "so ordered",
)
COURT_MARKERS = ("order", "judgment", "memorandum decision", "opinion", "minute entry", "so ordered")
MEDIUM_EVENTS = (
    "motion to stay", "notice of appeal", "motion for", "motion to", "opposition",
    "reply memorandum", "status report", "oral argument", "hearing", "brief",
    "declaration", "scheduling order", "letter motion",
)
LOW_EVENTS = (
    "notice of appearance", "certificate of service", "transcript", "civil cover sheet",
    "summons", "pro hac vice", "redaction", "filing error", "clerk's certificate",
    "mailing", "receipt",
)


def _has(text: str, terms: tuple[str, ...]) -> bool:
    return any(t in text for t in terms)


def assess(entry: DocketEntry) -> Assessment:
    text = re.sub(r"\s+", " ", entry.description.lower()).strip()
    court_decision = _has(text, COURT_MARKERS) and not text.startswith(("proposed order", "motion"))
    party_request = any(k in text for k in ("motion", "requests", "application", "letter"))

    if _has(text, HIGH_DECISIONS) and court_decision:
        impact, category, confidence = "HIGH", "DECISION_OR_ORDER", "MEDIUM"
        title = "Court order or decision"
        why = "The court appears to have issued relief or a ruling that may change the case's operative status."
    elif _has(text, MEDIUM_EVENTS):
        impact, confidence = "MEDIUM", "MEDIUM"
        if "appeal" in text:
            category, title = "APPEAL", "Appeal-related filing"
        elif "stay" in text or "injunction" in text:
            category, title = "STAY_OR_INJUNCTION", "Filing concerning a stay or injunction"
        elif "status report" in text:
            category, title = "IMPLEMENTATION_OR_COMPLIANCE", "Implementation or status report"
        elif any(k in text for k in ("hearing", "oral argument", "scheduling")):
            category, title = "SCHEDULING", "Scheduling update"
        else:
            category, title = "MERITS_BRIEFING", "Substantive filing"
        why = "This may affect briefing, implementation, appellate review, or the timing of the next decision."
    elif _has(text, LOW_EVENTS):
        impact, category, confidence = "LOW", "ADMINISTRATIVE", "HIGH"
        title = "Routine docket administration"
        why = "This appears administrative and does not itself resolve substantive relief."
    else:
        impact, category, confidence = "LOW", "UNKNOWN", "LOW"
        title = "New docket filing"
        why = "The description does not clearly indicate a substantive ruling; review the source document."

    if party_request and impact == "HIGH" and not court_decision:
        impact = "MEDIUM"
        why = "A party requested significant relief, but the description does not show the court granted or denied it."

    points = []
    if party_request and not court_decision:
        points.append("Appears to be a party filing, not a court ruling.")
    if court_decision:
        points.append("Description indicates a court-issued order or judgment.")
    points.append(f"Docket entry {entry.entry_number}, filed {entry.date_filed}.")
    available = sum(1 for d in entry.documents if d.is_available)
    points.append(f"{len(entry.documents)} linked document(s); {available} available to download.")

    return Assessment(
        category=category,
        impact=impact,
        confidence=confidence,
        title=title,
        summary=entry.description[:600] or "A new docket entry was added.",
        major_points=points[:4],
        why_it_matters=why,
        court_decision=court_decision,
        party_request=party_request,
        source="rules",
    )


def from_ai(result: dict, entry: DocketEntry) -> Assessment:
    """Convert a verified AI result into an Assessment."""
    points = [p["point"] for p in result.get("major_points", [])]
    evidence = [p["evidence"] for p in result.get("major_points", [])]
    return Assessment(
        category=result.get("classification", "UNKNOWN"),
        impact=result.get("impact", "LOW"),
        confidence=result.get("confidence", "LOW"),
        title=result.get("document_type") or "Court filing",
        summary=result.get("short_description", "")[:900],
        major_points=points,
        why_it_matters=result.get("why_it_matters", ""),
        court_decision=bool(result.get("court_decision")),
        party_request=bool(result.get("party_request")),
        source="ai",
        deadlines=result.get("deadlines", []),
        evidence=evidence,
        grounding=result.get("_grounding_ratio"),
        model=result.get("_model"),
    )
