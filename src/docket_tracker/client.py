from __future__ import annotations
import time
from typing import Any
import httpx
from .models import DocketEntry, Document

BASE = "https://www.courtlistener.com/api/rest/v4"

class CourtListenerClient:
    def __init__(self, token: str, timeout: float = 30.0):
        if not token:
            raise ValueError("COURTLISTENER_TOKEN is required")
        self.client = httpx.Client(
            headers={"Authorization": f"Token {token}", "Accept": "application/json", "User-Agent": "court-docket-tracker/1.0"},
            timeout=timeout,
            follow_redirects=True,
        )

    def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        for attempt in range(4):
            response = self.client.get(url, params=params)
            if response.status_code == 429:
                wait = float(response.headers.get("Retry-After", "10"))
                time.sleep(min(wait, 60))
                continue
            if response.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            return response.json()
        raise RuntimeError(f"CourtListener request failed after retries: {url}")

    @staticmethod
    def _id_from_resource(value: Any) -> int | str | None:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            parts = [p for p in value.rstrip('/').split('/') if p]
            return int(parts[-1]) if parts and parts[-1].isdigit() else value
        return None

    def get_entries(self, docket_id: int, max_pages: int = 10) -> list[DocketEntry]:
        url = f"{BASE}/docket-entries/"
        params: dict[str, Any] | None = {"docket": docket_id, "order_by": "-date_filed,-entry_number", "page_size": 100}
        entries: list[DocketEntry] = []
        pages = 0
        while url and pages < max_pages:
            data = self._get(url, params)
            params = None
            for item in data.get("results", []):
                docs = []
                for d in item.get("recap_documents", []) or []:
                    doc_id = d.get("id") or self._id_from_resource(d.get("resource_uri")) or "unknown"
                    docs.append(Document(
                        id=doc_id,
                        description=d.get("description") or d.get("document_type") or "Document",
                        absolute_url=d.get("absolute_url"),
                        download_url=d.get("filepath_local") or d.get("download_url"),
                        page_count=d.get("page_count"),
                        attachment_number=d.get("attachment_number"),
                    ))
                entry_id = item.get("id") or self._id_from_resource(item.get("resource_uri")) or "unknown"
                entries.append(DocketEntry(
                    id=entry_id,
                    entry_number=str(item.get("entry_number") or "Unnumbered"),
                    date_filed=str(item.get("date_filed") or "Unknown"),
                    description=(item.get("description") or "").strip(),
                    absolute_url=item.get("absolute_url"),
                    date_modified=item.get("date_modified"),
                    documents=docs,
                    raw=item,
                ))
            url = data.get("next")
            pages += 1
        return entries
