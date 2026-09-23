# Court Docket Tracker v3

Monitors **CLINIC v. Rubio, 1:26-cv-00858 (S.D.N.Y.)** on CourtListener, downloads the
filed PDF, summarizes it with grounding checks, and posts to Discord with the PDF attached.

> Informational summaries only. Not legal advice. Every alert links to the source.

## What v3 fixes

### 1. Old filings were being posted as new (the critical bug)

**Cause:** RECAP is crowd-sourced. When someone with PACER access uploads a document
for an August entry *today*, CourtListener adds it and the entry's fingerprint changes.
v2 saw "changed" and alerted — correctly by its own logic, but the result was August
filings arriving in your Discord in September.

**Fix:** a recency window. `MAX_AGE_DAYS=21` means any entry filed more than 21 days
ago is **recorded silently and never alerted**, no matter what changed about it. The
API is also asked for `date_filed__gte=<cutoff>` so old entries aren't even fetched.

Log line when this triggers:

```
Entry 88 skipped: filed 2026-08-05 (49 days old, limit 21)
```

Entries with an unparseable date are never suppressed, so nothing is lost silently.

### 2. PDF availability is now stated explicitly

Every alert carries a **Document** field with one of five honest states:

| State | Message |
|---|---|
| Downloaded, text extracted | ✅ Available — 12 pages, 1.4 MB. Text extracted and summarized. |
| Downloaded, image scan | ⚠️ Available, but scanned — no text layer, so it was not summarized. |
| On docket, not in RECAP | ❌ Not available — listed on the docket, but no free copy in RECAP yet. |
| No document on the entry | ❌ Not available — no document attached to this docket entry. |
| Fetch failed | ⚠️ Download failed — marked available but could not be retrieved. |

### 3. The PDF itself is attached to the Discord message

Files up to `DISCORD_UPLOAD_LIMIT_MB` (default 8 MB, under Discord's 10 MB free-server
ceiling) are uploaded via multipart so you can read the filing without leaving Discord.
Larger files fall back to a link automatically, and a `413` response also falls back
rather than failing.

### 4. Old databases upgrade themselves

`StateStore` now runs `PRAGMA table_info` and adds any missing columns. The
`no such column: pdf_hash` crash cannot recur.

## Setup

```bash
pip install -e .
cp .env.example .env     # fill in your three keys
```

**Critical first step after upgrading** — reset state so the window applies cleanly:

```bash
rm tracker.db
docket-tracker --initialize
```

Then preview and go live:

```bash
DRY_RUN=true docket-tracker
docket-tracker
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `COURTLISTENER_TOKEN` | required | API auth |
| `DISCORD_WEBHOOK_URL` | required unless dry run | Alert destination |
| `OPENAI_API_KEY` | optional | Enables AI summarization |
| `OPENAI_MODEL` | `gpt-5.6-terra` | Model ID |
| `MAX_AGE_DAYS` | `21` | **Recency window.** Older filings never alert |
| `ATTACH_PDF` | `true` | Upload the PDF to Discord |
| `DISCORD_UPLOAD_LIMIT_MB` | `8` | Attachment size ceiling |
| `USE_AI` | `true` | Master AI switch |
| `AI_MIN_IMPACT` | `MEDIUM` | Minimum pre-screen impact to spend an AI call |
| `SEND_LOW_IMPACT` | `true` | Send LOW alerts at all |
| `DRY_RUN` | `false` | Print instead of posting |
| `DB_PATH` | `tracker.db` | SQLite state |

### Tuning the window

- `MAX_AGE_DAYS=7` — only the last week. Tightest, best if you check daily.
- `MAX_AGE_DAYS=21` — default. Tolerates a few days of downtime without missing filings.
- `MAX_AGE_DAYS=60` — loose; you'll see more backfill noise.

### Backfill mode

To deliberately review older entries:

```bash
DRY_RUN=true docket-tracker --backfill
```

`--backfill` ignores the window. Never combine it with a live run unless you want
those older entries posted.

## Anti-hallucination design

1. **Grounding** — the model only sees text extracted from the filed PDF.
2. **Structured Outputs** — response locked to a strict JSON schema.
3. **Quote verification** — every point must carry a verbatim quote from the PDF;
   points whose quotes don't exist are deleted.
4. **Confidence downgrade** — under 50% verification forces `LOW`.
5. **Fallback** — any failure reverts to the deterministic classifier.

Plus a hard rule: if the model marks a filing as a party request and not a court
decision, impact is capped at `MEDIUM`. A motion asking for a stay can never be
reported as a stay being granted.

## Tests

```bash
PYTHONPATH=src pytest -q
```

24 tests covering the recency window (including the August/September boundary),
all five PDF states, attachment vs. link fallback, Discord field limits, quote
verification, and v1→v3 database migration.

## Known limits

- Scanned PDFs are flagged, not OCR'd.
- RECAP lags PACER, so a filing may exist on PACER before the tracker sees it.
- Quote verification catches fabricated evidence, not a subtly wrong reading of
  real text. Read the attached PDF before acting on a HIGH alert.
