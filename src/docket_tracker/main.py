from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
import yaml
from dotenv import load_dotenv
from .client import CourtListenerClient
from .classifier import assess
from .discord import build_payload, send
from .state import StateStore

def bool_env(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}

def run(config_path: str, initialize: bool = False) -> int:
    load_dotenv()
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    client = CourtListenerClient(os.getenv("COURTLISTENER_TOKEN", ""))
    store = StateStore(os.getenv("DB_PATH", "tracker.db"))
    webhook = os.getenv("DISCORD_WEBHOOK_URL", "")
    dry_run = bool_env("DRY_RUN")
    send_low = bool_env("SEND_LOW_IMPACT", True)
    failures = 0
    for case in config.get("cases", []):
        if not case.get("enabled", True): continue
        try:
            entries = client.get_entries(int(case["courtlistener_docket_id"]))
            entries.sort(key=lambda e: (e.date_filed, str(e.entry_number), str(e.id)))
            for entry in entries:
                change = store.status(int(case["courtlistener_docket_id"]), entry)
                if change == "unchanged": continue
                if initialize:
                    store.save(int(case["courtlistener_docket_id"]), entry, False); continue
                a = assess(entry)
                if a.impact == "LOW" and not send_low:
                    store.save(int(case["courtlistener_docket_id"]), entry, False); continue
                payload = build_payload(case, entry, a, change)
                if dry_run:
                    print(json.dumps(payload, indent=2))
                else:
                    if not webhook: raise ValueError("DISCORD_WEBHOOK_URL is required unless DRY_RUN=true")
                    send(webhook, payload)
                store.save(int(case["courtlistener_docket_id"]), entry, True)
        except Exception as exc:
            failures += 1
            print(f"ERROR monitoring {case.get('short_name')}: {exc}", file=sys.stderr)
    return 1 if failures else 0

def cli():
    p = argparse.ArgumentParser(description="CourtListener docket to Discord tracker")
    p.add_argument("--config", default="config/cases.yaml")
    p.add_argument("--initialize", action="store_true", help="Save current entries without alerting")
    args = p.parse_args()
    raise SystemExit(run(args.config, args.initialize))

if __name__ == "__main__": cli()
