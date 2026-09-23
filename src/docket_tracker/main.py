from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path

import yaml
from dotenv import load_dotenv

from . import classifier, pdf_extractor, summarizer
from .client import CourtListenerClient
from .discord import DEFAULT_UPLOAD_LIMIT, build_payload, send
from .models import PdfStatus
from .state import StateStore

log = logging.getLogger("docket_tracker")

RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def bool_env(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


def int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def analyze(entry, case, pdf: PdfStatus, api_key, use_ai, store, docket_id):
    """Return (assessment, ai_used)."""
    if not use_ai or not api_key or not pdf.has_text:
        return classifier.assess(entry, pdf), False

    if not store.needs_ai(docket_id, entry, pdf.sha256):
        log.info("Entry %s: this PDF was already summarized", entry.entry_number)
        return classifier.assess(entry, pdf), False

    result = summarizer.summarize(
        document_text=pdf.text,
        entry_description=entry.description,
        case_name=case["name"],
        api_key=api_key,
        model=os.getenv("OPENAI_MODEL"),
    )
    if not result:
        return classifier.assess(entry, pdf), False

    return classifier.from_ai(result, entry), True


def run(config_path: str, initialize: bool = False, backfill: bool = False) -> int:
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
    attach_pdf = bool_env("ATTACH_PDF", True)
    upload_limit = int_env("DISCORD_UPLOAD_LIMIT_MB", 8) * 1024 * 1024

    # --- Recency guard -------------------------------------------------
    # Entries older than this are recorded silently and never alerted.
    # This is what stops RECAP backfills of old filings from being posted
    # as if they were fresh court activity.
    max_age = int_env("MAX_AGE_DAYS", 21)
    today = date.today()
    cutoff = today - timedelta(days=max_age)
    filed_after = None if backfill else cutoff.isoformat()

    log.info(
        "AI %s | recency window %s days (on or after %s)%s",
        f"on ({os.getenv('OPENAI_MODEL', summarizer.DEFAULT_MODEL)})" if use_ai else "off",
        max_age,
        cutoff.isoformat(),
        " | BACKFILL MODE" if backfill else "",
    )

    failures = 0
    for case in config.get("cases", []):
        if not case.get("enabled", True):
            continue
        docket_id = int(case["courtlistener_docket_id"])
        try:
            entries = client.get_entries(docket_id, filed_after=filed_after)
            entries.sort(key=lambda e: (e.date_filed, str(e.entry_number)))
            log.info("%s: %d entries retrieved", case["short_name"], len(entries))

            for entry in entries:
                change = store.status(docket_id, entry)
                if change == "unchanged":
                    continue

                if initialize:
                    store.save(docket_id, entry, notified=False)
                    continue

                # --- recency gate ---
                age = entry.age_days(today)
                if age is not None and age > max_age and not backfill:
                    log.info(
                        "Entry %s skipped: filed %s (%d days old, limit %d)",
                        entry.entry_number, entry.date_filed, age, max_age,
                    )
                    store.save(docket_id, entry, notified=False)
                    continue

                # --- cheap pre-screen decides whether to spend an AI call ---
                prescreen = classifier.assess(entry)
                worth_ai = use_ai and RANK[prescreen.impact] >= RANK.get(ai_min, 1)

                # --- resolve the document (download + extract) ---
                if worth_ai or attach_pdf:
                    pdf = pdf_extractor.resolve(entry.documents)
                else:
                    document, state = pdf_extractor.pick_document(entry.documents)
                    pdf = PdfStatus(state=state if state != "available" else PdfStatus.NOT_AVAILABLE,
                                    document=document)

                assessment, ai_used = analyze(
                    entry, case, pdf, api_key, worth_ai, store, docket_id
                )

                if assessment.impact == "LOW" and not send_low:
                    store.save(docket_id, entry, False, pdf.sha256, ai_used, pdf.state)
                    continue

                payload, file_bytes, filename = build_payload(
                    case, entry, assessment, change, pdf,
                    upload_limit if attach_pdf else 0,
                )

                if dry_run:
                    print(json.dumps(payload, indent=2, ensure_ascii=False))
                    if filename:
                        print(f"[would attach {filename}, {pdf.size} bytes]")
                else:
                    if not webhook:
                        raise ValueError("DISCORD_WEBHOOK_URL is required unless DRY_RUN=true")
                    send(webhook, payload, file_bytes, filename)
                    log.info(
                        "Alerted entry %s (%s, %s, pdf=%s%s)",
                        entry.entry_number, assessment.impact, assessment.source,
                        pdf.state, ", attached" if filename else "",
                    )

                store.save(docket_id, entry, True, pdf.sha256, ai_used, pdf.state)
        except Exception as exc:
            failures += 1
            log.exception("Failed monitoring %s: %s", case.get("short_name"), exc)

    return 1 if failures else 0


def cli():
    parser = argparse.ArgumentParser(description="CourtListener docket to Discord tracker")
    parser.add_argument("--config", default="config/cases.yaml")
    parser.add_argument("--initialize", action="store_true",
                        help="Record current entries without sending alerts")
    parser.add_argument("--backfill", action="store_true",
                        help="Ignore the recency window (use with --initialize or DRY_RUN)")
    args = parser.parse_args()
    raise SystemExit(run(args.config, args.initialize, args.backfill))


if __name__ == "__main__":
    cli()
