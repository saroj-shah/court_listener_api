# Court Docket Tracker v3.1

Monitors **CLINIC v. Rubio, 1:26-cv-00858 (S.D.N.Y.)** on CourtListener, downloads the
filed PDF, summarizes it with grounding checks, and posts to Discord with the PDF attached.

> Informational summaries only. Not legal advice. Every alert links to the source.

## What v3.1 fixes

### 1. Crash: `TypeError: expected string or bytes-like object, got 'int'`

The run died at Entry 94. CourtListener returned an **integer** where a document
description was expected, and `safe_filename()` passed it straight to `re.sub()`.

Fixed in two places: `safe_filename()` now coerces both arguments with `str()`, and
`CourtListenerClient._text()` normalizes every API string field at ingestion so a
stray int can never reach the formatting layer again.

### 2. Every PDF download returned 403

`filepath_local` comes back as a bare path:

```
recap/gov.uscourts.nysd.657161/gov.uscourts.nysd.657161.87.0.pdf
```

v3.0 prefixed that with `www.courtlistener.com`, which **rejects scripted hotlinks
with 403**. Those files are served from `storage.courtlistener.com`.

`candidate_urls()` now tries the storage host first, falls back to www, sends a
browser-style User-Agent and Referer, and attaches your API token. If every
candidate fails, the alert says *"Could not download — CourtListener refused the
automated request"* with a manual link, rather than claiming the file was missing.

### 3. Party filings were labelled "Court decision"

Entries 85, 86, 90 and 91 are motions and briefs filed by the parties, but all four
showed **Posture: Court decision**. The old check matched `"opinion"` or `"judgment"`
*anywhere* in the text — and `"EMERGENCY MOTION to Enforce Judgment re: 83
Memorandum & Opinion"` contains both words while being a party filing.

`detect_posture()` now reads how the entry **opens**, which is where federal docket
text declares its type. Verified against your real entries:

| Entry | Text begins | v3.0 | v3.1 |
|---|---|---|---|
| 83 | OPINION AND ORDER | Court decision | Court decision ✓ |
| 85 | EMERGENCY MOTION | Court decision ✗ | **Party filing** ✓ |
| 86 | EMERGENCY MEMORANDUM | Court decision ✗ | **Party filing** ✓ |
| 87 | ORDER: | Court decision | Court decision ✓ |
| 90 | RESPONSE to Motion | Court decision ✗ | **Party filing** ✓ |
| 91 | REPLY MEMORANDUM | Court decision ✗ | **Party filing** ✓ |

This also stops false `@here` pings, which only fire on HIGH + court decision.

### 4. Quieter logs and a run summary

`httpx` request logging is silenced, and each run ends with:

```
Done. alerted=3 skipped_old=11 pdf_ok=2 pdf_failed=1 ai_summaries=2
```

## Upgrade

```bash
cd court-docket-tracker
# replace src/, tests/, config/, .github/, README.md from the zip
pip install -e .

rm tracker.db
docket-tracker --initialize
DRY_RUN=true docket-tracker      # should print nothing
```

Then verify the PDF fix on one real document:

```bash
DRY_RUN=true docket-tracker --backfill 2>&1 | grep -E "pdf_ok|pdf_failed|Available"
```

`pdf_ok` above zero means downloads work now.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `COURTLISTENER_TOKEN` | required | API auth, also sent with PDF requests |
| `DISCORD_WEBHOOK_URL` | required unless dry run | Alert destination |
| `OPENAI_API_KEY` | optional | Enables AI summarization |
| `OPENAI_MODEL` | `gpt-5.6-terra` | Model ID |
| `MAX_AGE_DAYS` | `21` | Filings older than this never alert |
| `ATTACH_PDF` | `true` | Upload the PDF to Discord |
| `DISCORD_UPLOAD_LIMIT_MB` | `8` | Attachment ceiling |
| `USE_AI` | `true` | Master AI switch |
| `AI_MIN_IMPACT` | `MEDIUM` | Minimum impact to spend an AI call |
| `SEND_LOW_IMPACT` | `true` | Send LOW alerts at all |
| `DRY_RUN` | `false` | Print instead of posting |
| `DB_PATH` | `tracker.db` | SQLite state |

## Document states

| State | Discord message |
|---|---|
| Downloaded, text extracted | ✅ Available — 12 pages, 1.4 MB. Text extracted and summarized. |
| Downloaded, image scan | ⚠️ Available, but scanned — no text layer, not summarized. |
| On docket, not in RECAP | ❌ Not available — no free copy in RECAP yet. |
| No document on the entry | ❌ Not available — no document attached. |
| All URLs refused | ⚠️ Could not download — CourtListener refused the automated request. |

## Anti-hallucination design

1. The model only sees text extracted from the filed PDF.
2. Output is locked to a strict JSON schema.
3. Every point must carry a verbatim quote; unmatched quotes are deleted.
4. Under 50% verification forces confidence to LOW.
5. Any failure falls back to the deterministic classifier.

Hard rule the model cannot override: a party request that is not a court decision
is capped at MEDIUM impact.

## Tests

```bash
PYTHONPATH=src pytest -q
```

34 tests. Regression coverage for all three v3.1 bugs: `test_posture.py` replays the
real misclassified entries, `test_pdf_urls.py` covers the storage-host resolution and
the int-description crash, `test_recency.py` covers the August/September boundary.

## Known limits

- Scanned PDFs are flagged, not OCR'd.
- RECAP lags PACER; a filing may exist on PACER before the tracker sees it.
- Some documents are genuinely PACER-only and will never download. That is reported
  honestly rather than guessed at.
- Quote verification catches fabricated evidence, not a subtly wrong reading of real
  text. Read the attached PDF before acting on a HIGH alert.
