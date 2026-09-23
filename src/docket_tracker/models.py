from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class Document:
    id: int | str
    description: str
    absolute_url: str | None = None
    download_url: str | None = None
    page_count: int | None = None
    is_available: bool = False
    file_size: int | None = None


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

    def filed_date(self) -> date | None:
        """Parse date_filed into a date object, or None if unparseable."""
        try:
            return datetime.strptime(self.date_filed[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None

    def age_days(self, today: date | None = None) -> int | None:
        filed = self.filed_date()
        if filed is None:
            return None
        return (( today or date.today()) - filed).days


@dataclass
class PdfStatus:
    """What we know about the document attached to an entry."""
    state: str                      # see constants below
    document: Document | None = None
    data: bytes | None = None
    text: str = ""
    pages: int = 0
    size: int = 0
    url: str | None = None
    sha256: str | None = None

    # State constants
    NONE_LISTED = "none_listed"           # entry has no document records at all
    NOT_AVAILABLE = "not_available"       # listed but not in RECAP (PACER-only)
    DOWNLOAD_FAILED = "download_failed"   # listed + marked available, fetch failed
    SCANNED = "scanned"                   # downloaded but no text layer
    TEXT_READY = "text_ready"             # downloaded and text extracted

    @property
    def is_downloaded(self) -> bool:
        return self.state in {self.SCANNED, self.TEXT_READY}

    @property
    def has_text(self) -> bool:
        return self.state == self.TEXT_READY and len(self.text) >= 400


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
