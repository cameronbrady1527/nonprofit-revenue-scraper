# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this is

`nonprofit-benchmark`: a data pipeline + Streamlit dashboard for benchmarking
nonprofit executive compensation. It builds a 501(c)(3) roster from the IRS
Business Master File, records each org's newest Form 990 from ProPublica, fills
in per-person Part VII compensation from the IRS e-file XML bulk dataset, and
serves a peer-comparison dashboard.

The benchmark figure is each org's **highest-paid executive's Form 990 Part VII
column D compensation** — never summed across people.

> Note: this project was rewritten from an earlier ProPublica scraper (async
> scrapers, Tkinter monitor, Gemini PDF parsing). Those files are gone. Ignore any
> stale references to `launch_with_monitor.py`, `async_nonprofit_scraper.py`, etc.

## Architecture

Strict split between **pure logic** (no I/O, no network, deterministic) and thin
**I/O shells**. Transports are injected so the pure logic is tested offline.

Pipeline data flow (all via the `pipeline` CLI in `cli.py`):

1. `init` — create the SQLite database (`benchmark.db`).
2. `seed --state XX` — `bmf.py`: download + parse the IRS BMF; store 501(c)(3) orgs.
3. `fetch --state XX` — `propublica.py` per-EIN; `filing_selector.py` picks each
   org's newest filing and classifies it `api` (structured data present) or `pdf`
   (numbers only in the 990 itself).
4. `sync-irs --year YYYY` — `efile_sync.py`: download the IRS e-file index for a
   **processing year**, read each bulk-ZIP central directory (HTTP range, not full
   download), and populate `efile_cache.py` (SQLite, default `irs_cache.db`) with
   `object_id -> (zip_url, member)`. Tax year N ≈ processing year N+1.
5. `parse --state XX` — `parse_scheduler.py` chooses unparsed `pdf` filings within
   the revenue band; for each, `efile_cache.resolve` → `efile_fetch.py` range-pulls
   the XML → `efile_xml.py` parses 990/990-EZ/990-PF → `FilingExtraction` →
   `db.record_parse_success`.

Dashboard (`dashboard/app.py`, Streamlit): reads the DB only. Peer filtering,
your-org percentile, expansion advisor, Excel export. Presentation-only — every
number comes from `db.query_peers_for_filters` and the pure `benchmark.py` engine.

### Key modules

- `extraction.py` — `FilingExtraction` / `ExecutiveRecord`, the shared parser
  result type (so persistence never depends on the data source).
- `efile_xml.py` — pure XML parser; element paths validated against real IRS
  returns (990: `CYTotalRevenueAmt` + `Form990PartVIISectionAGrp`; 990-EZ:
  `TotalRevenueAmt` + `OfficerDirectorTrusteeEmplGrp`; 990-PF: `TotalRevAndExpnssAmt`
  + `OfficerDirTrstKeyEmplGrp`). Matches tags by local name (namespace-agnostic).
- `benchmark.py` / `expansion.py` / `excel_export.py` — pure engines.
- `db.py` / `models.py` — SQLAlchemy; schema kept portable to PostgreSQL/Supabase.
- `gemini_parser.py` — legacy PDF path, optional `gemini` extra, **unused** by the
  pipeline (ProPublica's PDF host is behind a Cloudflare challenge). Kept only so
  the optional code path and its tests still import.

## Why IRS XML, not PDFs

ProPublica's API has revenue but not per-person Part VII comp, and its
`download-filing` PDF endpoint now returns a Cloudflare challenge (HTTP 403). The
IRS e-file XML is the public, complete, key-free source for electronically filed
990/990-EZ/990-PF (e-filing mandatory since tax year 2020). Paper-filed scanned
returns have no XML and are left unparsed.

## Commands

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dashboard,dev]"          # core + dashboard + tests

pipeline init
pipeline seed     --state NY
pipeline fetch    --state NY               # --limit N to scope
pipeline sync-irs --year 2024 --year 2025
pipeline parse    --state NY               # --limit / --retry-failed / --revenue-min/max

streamlit run src/nonprofit_benchmark/dashboard/app.py

pytest                                     # full suite, offline
```

## Conventions

- Keep the pure/IO split. New network code goes in a thin shell with an injectable
  transport; the logic it feeds is a separate pure function with its own test.
- Every behavior change ships with a test; the suite must stay offline and fast.
- Compensation columns (org=D, related=E, other=F) stay separate; never sum across
  people or columns into one figure.
- SQLite only uses constructs that port unchanged to PostgreSQL/Supabase.
