# Court Docket Tracker v2 — AI summarization

Monitors **CLINIC v. Rubio, 1:26-cv-00858 (S.D.N.Y.)** on CourtListener, downloads the
filed PDF, summarizes it with an OpenAI model under strict anti-hallucination controls,
and posts a concise alert to Discord.

> Informational summaries only. Not legal advice. Every alert links to the source document.

## What changed from v1

| | v1 | v2 |
|---|---|---|
| Summary text | Raw docket description, truncated | AI summary of the actual PDF |
| Key points | Template facts | Extracted from document, each quote-verified |
| PDF | Ignored | Downloaded and text-extracted |
| Deadlines | None | Extracted when stated in the document |
| Cost | ₹0 | ~₹0–80/month (see below) |

## The anti-hallucination design

This is the part that matters for a legal tracker. Five layers:

1. **Grounding** — the model only receives text extracted from the filed PDF. No web access, no memory, and it is instructed never to use outside knowledge.
2. **Structured Outputs** — the response is constrained to a strict JSON schema, so the impact value can only ever be `HIGH`, `MEDIUM`, or `LOW` and required fields can't go missing. <cite>turn8search65</cite>
3. **Quote verification** — every key point must carry a 10–25 word verbatim quote from the PDF. `summarizer.verify()` normalizes and searches for each quote in the source. **Points whose quotes don't exist are silently deleted.** This is the single most important safeguard — a fabricated claim cannot survive it.
4. **Confidence downgrade** — if under 50% of points verify, confidence is forced to `LOW`.
5. **Automatic fallback** — if all points fail, the PDF is a scan, the download fails, or the API errors, the system falls back to the deterministic v1 classifier rather than sending anything unverified.

Plus a hard rule the model cannot override: if `party_request` is true and `court_decision` is false, impact is capped at `MEDIUM`. A motion asking for a stay can never be reported as a stay being granted.

## Model choice

Set `OPENAI_MODEL` in `.env`. The default is `gpt-5.6-terra`, which balances intelligence and cost. Alternatives from the current lineup: `gpt-5.6-luna` (cheapest, $0.20/$1.20 per Mtok), `gpt-5.6-sol` (flagship, $4/$20), `gpt-6-astra` (most capable, $10/$50). <cite>turn8search60</cite><cite>turn8search61</cite>

For docket summarization, **Terra is the right default** — court filings are dense but not reasoning-intensive to summarize, and Luna occasionally blurs the motion-versus-order distinction that matters most here.

## Cost control

Three mechanisms keep the AI bill near zero:

- **`AI_MIN_IMPACT=MEDIUM`** — the free rule-based classifier pre-screens every entry first. Notices of appearance and transcript orders never reach the model.
- **PDF hash deduplication** — a given PDF is summarized exactly once. Re-runs and metadata changes don't re-bill.
- **Text cap** — input is capped at 120,000 characters.

Realistic cost: a 30-page filing is roughly 20k input tokens plus ~700 output. At Terra pricing that is about **$0.05 per substantive filing**. This docket sees a handful of qualifying filings per month, so expect **under $1/month**.

## Setup

### 1. Get the API key

Create a key at platform.openai.com, add billing credit, and add to `.env`:

```env
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-5.6-terra
USE_AI=true
AI_MIN_IMPACT=MEDIUM
```

Keep `COURTLISTENER_TOKEN` and `DISCORD_WEBHOOK_URL` as they already are.

### 2. Install and test

```bash
cd court-docket-tracker
source .venv/bin/activate
pip install -e .


#deleting the last row of db
sqlite3 tracker.db "DELETE FROM entries WHERE rowid IN (SELECT rowid FROM entries ORDER BY first_seen DESC LIMIT 1);"


# dowload db as csv
sqlite3 -header -csv tracker.db "SELECT * FROM entries;"> entries.csv

#db info table data
sqlite3 tracker.db "PRAGMA table_info(entries);"

# Preview without posting to Discord and without touching saved state
rm -f tracker.db
DRY_RUN=true docket-tracker
```

Look for `"Analysis": "AI summary of filed PDF (...)"` and a `Quote verification` percentage in the output. If you instead see `Docket text only — PDF not analyzed`, the entry had no downloadable PDF on CourtListener — that's expected for many entries and is not an error.

### 3. Go live

```bash
docket-tracker --initialize   # reset state, no alerts
docket-tracker                # live
```

### 4. GitHub Actions

Add a third repository secret, `OPENAI_API_KEY`, alongside the two you already have. The workflow is already wired for it.

Note the schedule is now **hourly** (`17 * * * *`) rather than twice hourly, to stay well inside CourtListener's free-tier limit of 125 requests/day.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `COURTLISTENER_TOKEN` | required | CourtListener API auth |
| `DISCORD_WEBHOOK_URL` | required unless dry run | Alert destination |
| `OPENAI_API_KEY` | optional | Enables AI summarization |
| `OPENAI_MODEL` | `gpt-5.6-terra` | Model ID |
| `USE_AI` | `true` | Master switch |
| `AI_MIN_IMPACT` | `MEDIUM` | Minimum pre-screen impact to spend an AI call |
| `SEND_LOW_IMPACT` | `true` | Send LOW alerts at all |
| `DRY_RUN` | `false` | Print payload instead of posting |
| `DB_PATH` | `tracker.db` | SQLite state file |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

## Tests

```bash
PYTHONPATH=src pytest -q
```

10 tests cover impact rules, the motion-vs-order distinction, quote verification (including a hallucinated-quote rejection case), PDF-hash deduplication, and Discord field-length limits.

## Known limits

- Scanned PDFs with no text layer are detected and skipped rather than guessed at; add OCR if you need them.
- CourtListener/RECAP lags PACER, so a filing may exist on PACER hours before the tracker can see it.
- Quote verification catches fabricated *evidence*, not a subtly wrong *interpretation* of real text. Always read the linked PDF before acting on a HIGH alert.
