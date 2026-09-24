from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class Document:
    id: int | str
    description: str = ""
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
        try:
            return datetime.strptime(str(self.date_filed)[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None

    def age_days(self, today: date | None = None) -> int | None:
        filed = self.filed_date()
        if filed is None:
            return None
        return ((today or date.today()) - filed).days


@dataclass
class PdfStatus:
    state: str
    document: Document | None = None
    data: bytes | None = None
    text: str = ""
    pages: int = 0
    size: int = 0
    url: str | None = None
    sha256: str | None = None

    NONE_LISTED = "none_listed"
    NOT_AVAILABLE = "not_available"
    DOWNLOAD_FAILED = "download_failed"
    SCANNED = "scanned"
    TEXT_READY = "text_ready"

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
    source: str = "rules"
    deadlines: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    grounding: float | None = None
    model: str | None = None
