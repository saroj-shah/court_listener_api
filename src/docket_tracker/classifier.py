from __future__ import annotations
import re
from .models import DocketEntry, Assessment

HIGH_DECISIONS = (
    "final judgment", "preliminary injunction", "temporary restraining order", "tro granted",
    "motion to stay is granted", "motion to stay is denied", "stay granted", "stay denied",
    "vacated", "dismissed", "class certification", "summary judgment", "remanded",
)
COURT_MARKERS = ("order", "judgment", "memorandum decision", "opinion", "minute entry")
MEDIUM_EVENTS = (
    "motion to stay", "notice of appeal", "motion for", "opposition", "reply memorandum",
    "status report", "oral argument", "hearing", "brief", "declaration", "scheduling order",
)
LOW_EVENTS = (
    "notice of appearance", "certificate of service", "transcript", "civil cover sheet",
    "summons", "pro hac vice", "redaction", "filing error", "clerk's certificate",
)

def _contains(text: str, terms: tuple[str, ...]) -> bool:
    return any(t in text for t in terms)

def assess(entry: DocketEntry) -> Assessment:
    text = re.sub(r"\s+", " ", entry.description.lower()).strip()
    court_decision = _contains(text, COURT_MARKERS) and not text.startswith(("proposed order", "motion"))
    party_request = "motion" in text or "requests" in text or "application" in text

    if _contains(text, HIGH_DECISIONS) and court_decision:
        impact, category, confidence = "HIGH", "DECISION_OR_ORDER", "HIGH"
        title = "Significant court decision or order"
        why = "The court appears to have issued relief or a merits ruling that may change the case's operative status."
    elif _contains(text, MEDIUM_EVENTS):
        impact, confidence = "MEDIUM", "HIGH"
        if "appeal" in text:
            category, title = "APPEAL", "Appeal-related filing"
        elif "stay" in text or "injunction" in text:
            category, title = "STAY_OR_INJUNCTION", "Request concerning a stay or injunction"
        elif "status report" in text:
            category, title = "IMPLEMENTATION_OR_COMPLIANCE", "Implementation or status report"
        elif "hearing" in text or "oral argument" in text or "scheduling" in text:
            category, title = "SCHEDULING", "Material scheduling update"
        else:
            category, title = "MERITS_BRIEFING", "Substantive filing"
        why = "This may affect briefing, implementation, appellate review, or the timing of the next major decision."
    elif _contains(text, LOW_EVENTS):
        impact, category, confidence = "LOW", "ADMINISTRATIVE", "HIGH"
        title = "Routine docket administration"
        why = "This appears procedural or administrative and does not itself resolve substantive relief."
    else:
        impact, category, confidence = "LOW", "UNKNOWN", "MEDIUM"
        title = "New docket filing"
        why = "The entry does not clearly indicate a substantive ruling; review the source document for context."

    if party_request and impact == "HIGH" and not court_decision:
        impact = "MEDIUM"
        why = "A party requested significant relief, but the description does not show that the court granted or denied it."

    summary = entry.description[:500] if entry.description else "A new docket entry was added."
    points = []
    if party_request:
        points.append("This appears to be a party request, not a court ruling.")
    if court_decision:
        points.append("The docket description indicates a court-issued order or judgment.")
    points.append(f"Filed on {entry.date_filed}; docket entry {entry.entry_number}.")
    points.append(f"{len(entry.documents)} linked document(s) identified by the API.")
    return Assessment(category, impact, confidence, title, summary, points[:4], why, court_decision, party_request)
