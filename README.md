# Court Docket Tracker

A production-minded Python monitor for **CLINIC v. Rubio, 1:26-cv-00858 (S.D.N.Y.)**. It polls CourtListener's v4 docket-entry API, detects new entries and later document attachments, applies transparent impact rules, and posts concise Discord embeds.

> Informational summaries only. This software does not provide legal advice and does not predict outcomes.

## Features

- CourtListener token authentication
- New-entry and changed-entry detection
- SQLite persistence and document-aware fingerprints
- HIGH / MEDIUM / LOW impact classification
- Distinguishes a party's motion from a court decision
- Discord embeds with source links and controlled `@here`
- HTTP timeout, retry, and 429 handling
- Dry-run and initialize modes
- Automated tests
- GitHub Actions schedule every 30 minutes at minutes 17 and 47

## 1. Create credentials

1. Create a CourtListener account and copy the API token from the account settings.
2. In Discord, open the target channel's settings, select **Integrations**, create a webhook, and copy its URL.
3. Treat both values as secrets.

## 2. Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
# Edit .env with actual secrets
```

Initialize the database without sending alerts for every historical filing:

```bash
docket-tracker --initialize
```

Test the full formatting without posting to Discord:

```bash
DRY_RUN=true docket-tracker
```

Run normally:

```bash
docket-tracker
```

## 3. Deploy with GitHub Actions

1. Create a **private GitHub repository** and push this project.
2. Go to **Settings > Secrets and variables > Actions**.
3. Add `COURTLISTENER_TOKEN` and `DISCORD_WEBHOOK_URL`.
4. Open **Actions > Monitor court docket > Run workflow**.
5. Select `initialize=true` for the first run. This prevents historical-alert spam.
6. Run again with `initialize=false` to verify normal operation.

The workflow commits `state/tracker.db` to the private repository after each run. For a larger or public deployment, replace this with PostgreSQL or another durable private store.

## Impact policy

- **HIGH:** court-issued order or judgment granting/denying consequential relief, dismissal, final judgment, injunction, stay decision, vacatur, remand, or major merits disposition.
- **MEDIUM:** a party requests consequential relief, a notice of appeal, substantive briefing, an implementation report, a hearing, or a meaningful scheduling event.
- **LOW:** appearance, service, transcript, summons, redaction, clerical correction, or other routine administration.

The classifier deliberately treats a **motion to stay** as MEDIUM and an **order granting or denying that motion** as HIGH.

## Configuration

Edit `config/cases.yaml` to add another docket. Required keys are `name`, `short_name`, `case_number`, `courtlistener_docket_id`, and `docket_url`.

Environment variables:

- `COURTLISTENER_TOKEN`: required
- `DISCORD_WEBHOOK_URL`: required unless `DRY_RUN=true`
- `DB_PATH`: defaults to `tracker.db`
- `DRY_RUN`: prints payloads instead of sending
- `SEND_LOW_IMPACT`: defaults to `true`

## Test

```bash
pytest -q
```

## Operational notes

- CourtListener/RECAP can lag PACER. The alert reports only what the API exposes.
- A filename or external social-media attachment is not treated as an official docket event.
- Existing entries are re-alerted only when their fingerprint changes, such as when a PDF becomes available.
- `@here` is used only for HIGH-impact entries that look like court decisions.
- Review `src/docket_tracker/classifier.py` as the case evolves. Legal event classification is heuristic.
