from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from .models import DocketEntry, Document

log = logging.getLogger(__name__)
BASE = "https://www.courtlistener.com/api/rest/v4"


class CourtListenerClient:
    def __init__(self, token: str, timeout: float = 30.0):
        if not token:
            raise ValueError("COURTLISTENER_TOKEN is required")
        self.token = token
        self.client = httpx.Client(
            headers={
                "Authorization": f"Token {token}",
                "Accept": "application/json",
                "User-Agent": "court-docket-tracker/3.1",
            },
            timeout=timeout,
            follow_redirects=True,
        )

    def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        for attempt in range(4):
            response = self.client.get(url, params=params)
            if response.status_code == 429:
                wait = float(response.headers.get("Retry-After", "20"))
                log.warning("Rate limited by CourtListener; sleeping %ss", wait)
                time.sleep(min(wait, 90))
                continue
            if response.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            return response.json()
        raise RuntimeError(f"CourtListener request failed after retries: {url}")

    @staticmethod
    def _id_from(value: Any) -> int | str | None:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            parts = [p for p in value.rstrip("/").split("/") if p]
            return int(parts[-1]) if parts and parts[-1].isdigit() else value
        return None

    @staticmethod
    def _text(value: Any, fallback: str = "") -> str:
        """Coerce any API value to a string. Guards against ints in description."""
        if value is None:
            return fallback
        text = str(value).strip()
        return text or fallback

    def get_entries(
        self,
        docket_id: int,
        filed_after: str | None = None,
        max_pages: int = 3,
    ) -> list[DocketEntry]:
        url = f"{BASE}/docket-entries/"
        params: dict[str, Any] | None = {
            "docket": docket_id,
            "order_by": "-date_filed",
            "page_size": 100,
        }
        if filed_after:
            params["date_filed__gte"] = filed_after

        entries: list[DocketEntry] = []
        pages = 0
        while url and pages < max_pages:
            data = self._get(url, params)
            params = None
            for item in data.get("results", []):
                documents = []
                for d in item.get("recap_documents") or []:
                    local = d.get("filepath_local")
                    documents.append(
                        Document(
                            id=d.get("id") or self._id_from(d.get("resource_uri")) or "unknown",
                            description=self._text(
                                d.get("description") or d.get("document_type"), "Document"
                            ),
                            absolute_url=d.get("absolute_url"),
                            download_url=local or d.get("download_url"),
                            page_count=d.get("page_count"),
                            is_available=bool(d.get("is_available") or local),
                            file_size=d.get("file_size"),
                        )
                    )
                entries.append(
                    DocketEntry(
                        id=item.get("id") or self._id_from(item.get("resource_uri")) or "unknown",
                        entry_number=self._text(item.get("entry_number"), "Unnumbered"),
                        date_filed=self._text(item.get("date_filed"), "Unknown"),
                        description=self._text(item.get("description")),
                        absolute_url=item.get("absolute_url"),
                        date_modified=item.get("date_modified"),
                        documents=documents,
                        raw=item,
                    )
                )
            url = data.get("next")
            pages += 1
        return entries
