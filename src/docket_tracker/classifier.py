"""Deterministic classifier. Used for pre-screening and as the AI fallback."""
from __future__ import annotations

import re

from .models import Assessment, DocketEntry, PdfStatus

# A court-issued document announces itself at the START of the docket text.
# Matching "opinion" anywhere is wrong: "EMERGENCY MOTION to Enforce Judgment
# re: 83 Memorandum & Opinion" is a party filing that merely cites an opinion.
COURT_PREFIXES = (
    "order", "opinion", "memorandum opinion", "memorandum & opinion",
    "memorandum and order", "opinion and order", "judgment", "clerk's judgment",
    "clerk's rule", "decision", "minute entry", "text only order",
    "amended order", "scheduling order", "so ordered",
)
PARTY_PREFIXES = (
    "motion", "emergency motion", "letter motion", "consent letter motion",
    "notice", "response", "reply", "memorandum of law", "emergency memorandum",
    "declaration", "affidavit", "brief", "status report", "letter",
    "stipulation", "exhibit", "proposed", "joint",
)

HIGH_DECISIONS = (
    "final judgment", "preliminary injunction", "temporary restraining order",
    "stay is granted", "stay is denied", "is granted", "is denied",
    "granted in part", "vacated", "vacatur", "dismissed", "class certification",
    "summary judgment", "remanded",
)
MEDIUM_EVENTS = (
    "motion to stay", "notice of appeal", "motion for", "motion to", "opposition",
    "reply memorandum", "status report", "oral argument", "hearing", "brief",
    "declaration", "affidavit", "scheduling order", "letter motion", "response to motion",
    "conference", "memorandum of law",
)
LOW_EVENTS = (
    "notice of appearance", "certificate of service", "transcript", "civil cover sheet",
    "summons", "pro hac vice", "redaction", "filing error", "clerk's certificate",
    "mailing", "receipt",
)

PDF_LABELS = {
    PdfStatus.NONE_LISTED: "No document attached to this entry (text-only docket entry).",
    PdfStatus.NOT_AVAILABLE: "Document listed on the docket but no free copy in RECAP yet.",
    PdfStatus.DOWNLOAD_FAILED: "Document listed as available but could not be downloaded.",
    PdfStatus.SCANNED: "PDF downloaded but it is a scan with no text layer.",
    PdfStatus.TEXT_READY: "PDF downloaded and text extracted.",
}


def _has(text: str, terms: tuple[str, ...]) -> bool:
    return any(t in text for t in terms)


def _starts_with(text: str, prefixes: tuple[str, ...]) -> bool:
    return any(text.startswith(p) for p in prefixes)


def detect_posture(description: str) -> tuple[bool, bool]:
    """Return (court_decision, party_request) based on how the entry OPENS."""
    text = re.sub(r"\s+", " ", description.lower()).strip()
    text = text.lstrip("*_ ")

    if _starts_with(text, PARTY_PREFIXES):
        return False, True
    if _starts_with(text, COURT_PREFIXES):
        return True, False

    # Fall back to weaker signals only if the opening was inconclusive.
    court = bool(re.search(r"\b(so ordered|hereby ordered)\b", text))
    party = bool(re.search(r"\b(document filed by|filed by)\b", text))
    if court and not party:
        return True, False
    if party:
        return False, True
    return False, False


def assess(entry: DocketEntry, pdf: PdfStatus | None = None) -> Assessment:
    text = re.sub(r"\s+", " ", entry.description.lower()).strip()
    court_decision, party_request = detect_posture(entry.description)

    if court_decision and _has(text, HIGH_DECISIONS):
        impact, category, confidence = "HIGH", "DECISION_OR_ORDER", "MEDIUM"
        title = "Court order or decision"
        why = "The court appears to have issued relief or a ruling that may change the case's operative status."
    elif court_decision:
        impact, category, confidence = "MEDIUM", "DECISION_OR_ORDER", "MEDIUM"
        title = "Court order"
        why = "The court issued an order; review it for deadlines or procedural requirements."
    elif _has(text, LOW_EVENTS):
        impact, category, confidence = "LOW", "ADMINISTRATIVE", "HIGH"
        title = "Routine docket administration"
        why = "This appears administrative and does not itself resolve substantive relief."
    elif _has(text, MEDIUM_EVENTS):
        impact, confidence = "MEDIUM", "MEDIUM"
        if "appeal" in text:
            category, title = "APPEAL", "Appeal-related filing"
        elif "stay" in text or "injunction" in text:
            category, title = "STAY_OR_INJUNCTION", "Filing concerning a stay or injunction"
        elif "status report" in text:
            category, title = "IMPLEMENTATION_OR_COMPLIANCE", "Implementation or status report"
        elif any(k in text for k in ("hearing", "oral argument", "scheduling", "conference")):
            category, title = "SCHEDULING", "Scheduling update"
        else:
            category, title = "MERITS_BRIEFING", "Substantive filing"
        why = "This may affect briefing, implementation, appellate review, or the timing of the next decision."
    else:
        impact, category, confidence = "LOW", "UNKNOWN", "LOW"
        title = "New docket filing"
        why = "The description does not clearly indicate a substantive ruling; review the source document."

    points = []
    if court_decision:
        points.append("Filed by the court \u2014 this is an order or judgment.")
    elif party_request:
        points.append("Filed by a party \u2014 this is a request, not a ruling.")
    points.append(f"Docket entry {entry.entry_number}, filed {entry.date_filed}.")
    if pdf is not None:
        points.append(PDF_LABELS.get(pdf.state, "Document status unknown."))

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
