from dataclasses import dataclass, field
from typing import Any


@dataclass
class Document:
    id: int | str
    description: str
    absolute_url: str | None = None
    download_url: str | None = None
    page_count: int | None = None
    is_available: bool = False


@dataclass
class DocketEntry:
    id: int | str
    entry_number: str
    date_filed: str
    description: str
    absolute_url: str | None = None
    date_modified: str | None = None
    documents: list[Document] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Assessment:
    category: str
    impact: str
    confidence: str
    title: str
    summary: str
    major_points: list[str]
    why_it_matters: str
    court_decision: bool
    party_request: bool
    source: str = "rules"          # "rules" or "ai"
    deadlines: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    grounding: float | None = None
    model: str | None = None
