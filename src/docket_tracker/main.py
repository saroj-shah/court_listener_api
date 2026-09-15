from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from . import classifier, pdf_extractor, summarizer
from .client import CourtListenerClient
from .discord import build_payload, send
from .state import StateStore

log = logging.getLogger("docket_tracker")


def bool_env(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


def pick_document(entry):
    """Choose the most substantive downloadable document on the entry."""
    available = [d for d in entry.documents if d.is_available and d.download_url]
    if not available:
        return None
    return max(available, key=lambda d: (d.page_count or 0))


def analyze(entry, case, api_key, use_ai, store, docket_id):
    """Return (assessment, pdf_hash, ai_used)."""
    if not use_ai or not api_key:
        return classifier.assess(entry), None, False

    document = pick_document(entry)
    if not document:
        log.info("Entry %s: no downloadable PDF; using rule-based summary", entry.entry_number)
        return classifier.assess(entry), None, False

    data = pdf_extractor.fetch_pdf(document.download_url)
    if not data:
        return classifier.assess(entry), None, False

    pdf_hash = pdf_extractor.content_hash(data)
    if not store.needs_ai(docket_id, entry, pdf_hash):
        log.info("Entry %s: PDF already summarized", entry.entry_number)
        return classifier.assess(entry), pdf_hash, False

    text, pages = pdf_extractor.extract_text(data)
    if pdf_extractor.is_scanned(text, pages):
        log.warning("Entry %s: PDF appears to be a scan with no text layer", entry.entry_number)
        return classifier.assess(entry), pdf_hash, False

    result = summarizer.summarize(
        document_text=text,
        entry_description=entry.description,
        case_name=case["name"],
        api_key=api_key,
        model=os.getenv("OPENAI_MODEL"),
    )
    if not result:
        return classifier.assess(entry), pdf_hash, False

    return classifier.from_ai(result, entry), pdf_hash, True


def run(config_path: str, initialize: bool = False) -> int:
    load_dotenv()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    client = CourtListenerClient(os.getenv("COURTLISTENER_TOKEN", ""))
    store = StateStore(os.getenv("DB_PATH", "tracker.db"))
    webhook = os.getenv("DISCORD_WEBHOOK_URL", "")
    api_key = os.getenv("OPENAI_API_KEY", "")
    dry_run = bool_env("DRY_RUN")
    send_low = bool_env("SEND_LOW_IMPACT", True)
    use_ai = bool_env("USE_AI", True) and bool(api_key)
    ai_min = os.getenv("AI_MIN_IMPACT", "MEDIUM").upper()
    rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}

    if use_ai:
        log.info("AI summarization enabled (model: %s)", os.getenv("OPENAI_MODEL", summarizer.DEFAULT_MODEL))
    else:
        log.info("AI summarization disabled; using rule-based classifier")

    failures = 0
    for case in config.get("cases", []):
        if not case.get("enabled", True):
            continue
        docket_id = int(case["courtlistener_docket_id"])
        try:
            entries = client.get_entries(docket_id)
            entries.sort(key=lambda e: (e.date_filed, str(e.entry_number)))
            log.info("%s: %d entries retrieved", case["short_name"], len(entries))

            for entry in entries:
                change = store.status(docket_id, entry)
                if change == "unchanged":
                    continue
                if initialize:
                    store.save(docket_id, entry, notified=False)
                    continue

                # Cheap pre-screen decides whether the filing deserves an AI call.
                prescreen = classifier.assess(entry)
                worth_ai = use_ai and rank[prescreen.impact] >= rank.get(ai_min, 1)

                assessment, pdf_hash, ai_used = analyze(
                    entry, case, api_key, worth_ai, store, docket_id
                )

                if assessment.impact == "LOW" and not send_low:
                    store.save(docket_id, entry, False, pdf_hash, ai_used)
                    continue

                payload = build_payload(case, entry, assessment, change)
                if dry_run:
                    print(json.dumps(payload, indent=2, ensure_ascii=False))
                else:
                    if not webhook:
                        raise ValueError("DISCORD_WEBHOOK_URL is required unless DRY_RUN=true")
                    send(webhook, payload)
                    log.info("Alerted entry %s (%s, %s)", entry.entry_number,
                             assessment.impact, assessment.source)

                store.save(docket_id, entry, True, pdf_hash, ai_used)
        except Exception as exc:
            failures += 1
            log.exception("Failed monitoring %s: %s", case.get("short_name"), exc)

    return 1 if failures else 0


def cli():
    parser = argparse.ArgumentParser(description="CourtListener docket to Discord tracker")
    parser.add_argument("--config", default="config/cases.yaml")
    parser.add_argument("--initialize", action="store_true",
                        help="Record current entries without sending alerts")
    args = parser.parse_args()
    raise SystemExit(run(args.config, args.initialize))


if __name__ == "__main__":
    cli()
