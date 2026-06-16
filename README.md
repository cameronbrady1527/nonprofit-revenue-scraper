# Nonprofit Executive Compensation Benchmark

A data pipeline and dashboard for benchmarking nonprofit executive pay. It builds
a local roster of 501(c)(3) organizations from the IRS Business Master File,
pulls their most recent Form 990 financials from ProPublica, fills in per-person
executive compensation from the IRS's machine-readable e-file XML, and serves a
peer-comparison dashboard so an organization can see where its executive
compensation sits relative to similar nonprofits.

The benchmark figure for each organization is its **highest-paid executive's
Form 990 Part VII column D compensation** — never a sum across people.

## How it works

```
seed (IRS BMF)     fetch (ProPublica)      sync-irs (IRS bulk)    parse (e-file XML)    dashboard
501(c)(3) roster   newest filing per org   index + ZIP locations  exec comp for         peer benchmark
for a state        (API or PDF source)     of every e-filed 990   PDF-only filings      + Excel export
```

Where the numbers come from: ProPublica's API already carries total revenue (and
aggregate officer pay) for many filings. The *per-person* Part VII compensation —
the actual benchmark — is not in that API, and ProPublica's PDF host is behind a
Cloudflare challenge. So `parse` instead reads the IRS's official e-file **XML**,
which contains the full Part VII table for every electronically filed return
(mandatory for 990s since tax year 2020). The IRS publishes this only as national
bulk ZIPs, so `sync-irs` indexes each return's location once and `parse` then
HTTP-range-fetches just the XML it needs — no multi-gigabyte download, no AI, no
rate limits.

The codebase separates **pure logic** (no I/O — XML/index parsing, filing
selection, the benchmark engine, the expansion advisor, Excel rendering) from
**thin I/O shells** (HTTP clients, the e-file fetcher, the database, the CLI).
Storage is SQLite, restricted to constructs that port unchanged to
PostgreSQL/Supabase.

## Requirements

- Python 3.12+
- Internet access. All data sources (IRS BMF, ProPublica API, IRS e-file XML) are
  public and need no API key.

## Installation

```bash
git clone https://github.com/cameronbrady1527/nonprofit-revenue-scraper.git
cd nonprofit-revenue-scraper

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# Core pipeline only:
pip install -e .
# With the dashboard and/or test extras:
pip install -e ".[dashboard,dev]"
```

## Usage

The pipeline is a single console command (`pipeline`). Run the steps in order for
a state; each writes to the same SQLite database (default `benchmark.db`).

```bash
pipeline init                       # create the database
pipeline seed     --state NY        # download the IRS BMF roster of 501(c)(3)s
pipeline fetch    --state NY        # record each org's newest ProPublica filing
pipeline sync-irs --year 2024 --year 2025   # cache IRS e-file XML locations
pipeline parse    --state NY        # extract exec comp from e-file XML
```

`sync-irs` downloads the IRS index for each **processing year** and reads the
bulk-ZIP directories into a local cache (`irs_cache.db`). A return for tax year N
is usually processed in year N+1, so sync the year(s) *after* the tax years you
care about. It's a one-time refresh shared across states; re-run it to pick up
newly released filings.

Useful flags:

- `--db PATH` — use a database file other than `benchmark.db`
- `--cache PATH` — e-file cache location for `sync-irs` / `parse` (default `irs_cache.db`)
- `seed --file path.csv` — ingest a local BMF CSV instead of downloading
- `fetch --limit N` / `parse --limit N` — process only the first N records
- `fetch --workers N` / `parse --workers N` — concurrent requests (default 8).
  `fetch` runs ProPublica calls in parallel and auto-throttles if it gets
  rate-limited (heavy 429s slow the pool rather than failing); `parse` fetches
  e-file XML concurrently, grouped by ZIP. Both are ~5× faster than sequential.
- `parse --retry-failed` — re-attempt filings whose previous parse failed
- `parse --revenue-min / --revenue-max` — only parse orgs near a revenue band

> Coverage note: `parse` handles electronically filed 990, 990-EZ, and 990-PF
> returns. Paper-filed scanned returns (rare since e-filing became mandatory) have
> no XML and are left unparsed.

Then launch the dashboard (requires the `dashboard` extra and a populated database):

```bash
streamlit run src/nonprofit_benchmark/dashboard/app.py
```

(A `.streamlit/config.toml` is included so the dashboard loads cleanly on WSL2,
where the browser↔server WebSocket otherwise stalls on the loading screen.)

In the dashboard you can filter peers by state, revenue range, and NTEE
category; enter your own organization (by EIN, name search, or manually) to see
its **percentile** against the peer set; accept **expansion** suggestions when a
filter returns too few peers; and export the filtered view to Excel.

## Project structure

```
src/nonprofit_benchmark/
├── cli.py              # `pipeline` entry point (init / seed / fetch / sync-irs / parse)
├── bmf.py              # IRS Business Master File download + parse
├── propublica.py       # ProPublica Nonprofit Explorer per-EIN client
├── filing_selector.py  # pick each org's newest filing; classify api vs pdf
├── parse_scheduler.py  # decide which filings to parse (status + revenue band)
├── efile_index.py      # parse the IRS e-file index CSV (pure)
├── efile_cache.py      # SQLite cache of object_id -> ZIP location
├── efile_sync.py       # build the cache: index + ZIP directories (I/O shell)
├── efile_fetch.py      # HTTP-range fetch one 990 XML from a bulk ZIP (I/O shell)
├── efile_xml.py        # parse 990 / 990-EZ / 990-PF XML -> FilingExtraction (pure)
├── extraction.py       # shared result schema (revenue + executives)
├── benchmark.py        # Benchmark Engine: rows + summary statistics (pure)
├── expansion.py        # Expansion Advisor: filter-widening proposals (pure)
├── excel_export.py     # render the filtered view to .xlsx (pure)
├── db.py / models.py   # SQLite persistence and ORM models
├── gemini_parser.py    # legacy PDF-parsing path (optional `gemini` extra; unused by the pipeline)
└── dashboard/app.py    # Streamlit benchmarking dashboard
tests/                  # pytest suite (run with `pytest`)
```

## Testing

```bash
pip install -e ".[dev]"
pytest
```

The suite is fast and offline — the index download, ZIP directory reads, and
e-file fetch transport are all injected, so tests exercise the parsing and
error-handling logic without touching the network.

## Data sources & ethics

All data comes from public IRS Form 990 filings: the IRS Business Master File,
the ProPublica Nonprofit Explorer API, and the IRS e-file XML bulk dataset. No
API keys, private data, or donor information are involved. Intended for research,
journalism, grant-making, and nonprofit-sector analysis.

## License

MIT — see [LICENSE](LICENSE).
