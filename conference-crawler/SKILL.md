---
name: conference-crawler
description: Crawl conference proceedings and download paper PDFs for ASIACRYPT, CRYPTO, EUROCRYPT, NDSS, USENIX Security, IEEE S&P, and CCS, with resumable downloads, browser-backed access for IEEE/ACM pages, PDF deduplication, official-paper matching, and curated/review output. Use when collecting conference PDFs or preparing verified PDF inputs for GROBID metadata extraction.
---

# Conference PDF Crawler

Use this skill to collect conference paper PDFs and prepare them for downstream metadata extraction. The crawler is networked and may require an existing Chrome session for IEEE or ACM pages. Treat downloaded files as unverified until the cleaning manifest has been reviewed.

## Repository layout

The implementation lives under `conference-crawler/scripts`:

- `spider-pdf/run.sh`: single conference dispatch entry point.
- `spider-pdf/spider.py`: selects the backend and URL list.
- `spider-pdf/core.py`: DBLP, IEEE S&P, and ACM/CCS crawling logic.
- `download/clean_and_classify_pdfs.py`: title matching, SHA-256 deduplication, filtering, and curation.
- `download/official_accepted_papers.csv`: official paper list used by the cleaning stage.
- `spider-pdf/*_urls.txt`: manually reviewed proceedings URL lists.

Do not use `download/main.py` as the crawler entry point; it is only a placeholder.

## Supported conferences and backends

| Conference argument | Backend | URL file |
|---|---|---|
| `asiacrypt` | DBLP/Springer PDF resolution | `asiacrypt_urls.txt` |
| `crypto` | DBLP/Springer PDF resolution | `crypto_urls.txt` |
| `eurocrypt` | DBLP/Springer PDF resolution | `eurocrypt_urls.txt` |
| `ndss` | DBLP/PDF resolution | `ndss_urls.txt` |
| `usenix_security` | DBLP/PDF resolution | `usenix_security_urls.txt` |
| `ieee_s&p` | IEEE browser workflow | `ieee_s&p_urls.txt` |
| `ccs` | ACM browser workflow | `ccs_urls.txt` |

Use the exact argument spelling above. The shell entry point rejects unsupported conference names.

## Runtime and browser setup

The download subproject requires Python 3.13 and its own dependencies. Prefer the bundled environment; if it is absent, use `uv` from the download project:

```bash
CRAWLER_ROOT=/absolute/path/to/conference-crawler
PY="$CRAWLER_ROOT/scripts/download/.venv/bin/python"
test -x "$PY" || PY="uv run --project $CRAWLER_ROOT/scripts/download python"
```

For DBLP/Springer crawling, ordinary HTTP requests are used. For IEEE S&P and CCS, configure a Chrome driver/profile when the site requires an authenticated or interactive session:

```bash
export CHROMEDRIVER_PATH=/absolute/path/to/chromedriver   # optional
export SELENIUM_USER_DATA_DIR=/absolute/path/to/chrome-profile
```

Do not put credentials in URL files, scripts, or generated CSVs. Use a dedicated browser profile when possible.

## Download workflow

1. Inspect the relevant `*_urls.txt` file and confirm the conference/year scope.
2. Run one conference and a small year subset first. Keep the default sleeps unless a site owner explicitly permits a lower rate.
3. Let the crawler reuse existing PDFs and CSV statuses. Use `--force` only when a deliberate re-download is required.
4. Skip any record whose title contains `workshop` (case-insensitive) before resolving a PDF URL; retain it in the result CSV with status `skipped_workshop`.
5. Inspect the generated summary CSV and failed/missing PDF statuses.
6. Run the cleaning stage against the download root and official paper table.
7. Review `metadata/paper_manifest.csv` before passing accepted PDFs to GROBID.

Example commands from the repository root:

```bash
conference-crawler/scripts/spider-pdf/run.sh crypto --years 2020,2021
conference-crawler/scripts/spider-pdf/run.sh ndss --years 2024 --sleep 2 --toc-sleep 8
conference-crawler/scripts/spider-pdf/run.sh 'ieee_s&p' --start-year 2024
conference-crawler/scripts/spider-pdf/run.sh ccs --years 2024 --user-data-dir /absolute/path/to/chrome-profile
```

For CCS, `--years` filters the proceedings URL list before any browser or PDF request.

The crawler writes PDFs and batch summaries below `conference-crawler/scripts/download` by default. Existing flat layouts are reused; new downloads may be placed under `conference/year/<toc-slug>/pdfs/`.
Set `CONFERENCE_DOWNLOAD_DIR` to an empty batch directory when a run must not consume existing
summaries or metadata. After crawling, use `scripts/download/build_official_list_from_results.py`
to build the cleaning input from that batch's newly fetched DBLP result CSVs instead of reusing the
project-wide official table.

When a conference year has multiple proceedings volumes, merge them only after every volume finishes.
Run `scripts/download/merge_volume_pdfs.py` to sort by numeric volume and then by the paper order in
each result CSV. Exclude proceedings/front-matter rows and number papers globally with three digits,
for example `001_New Attacks on LowMC Instances with a Single Plaintext_Ciphertext Pair.pdf`.
Require `missing=0` before handing the merged directory to GROBID.

## Cleaning and official-list matching

Run the deterministic cleaning stage after downloading:

```bash
CRAWLER_ROOT=/absolute/path/to/conference-crawler
uv run --project "$CRAWLER_ROOT/scripts/download" python \
  "$CRAWLER_ROOT/scripts/download/clean_and_classify_pdfs.py"
```

Override paths when operating on a copied dataset:

```bash
CONFERENCE_DOWNLOAD_DIR=/absolute/path/to/download \
CONFERENCE_OFFICIAL_CSV=/absolute/path/to/official_accepted_papers.csv \
uv run --project /absolute/path/to/conference-crawler/scripts/download python \
/absolute/path/to/conference-crawler/scripts/download/clean_and_classify_pdfs.py
```

For the repository's default layout, raw PDFs are under `download/pdf/`, so
point the scanner at that directory while keeping curated outputs under
`download/`:

```bash
CONFERENCE_DOWNLOAD_DIR=/absolute/path/to/conference-crawler/scripts/download/pdf \
CONFERENCE_CLEAN_OUTPUT_DIR=/absolute/path/to/conference-crawler/scripts/download \
CONFERENCE_OFFICIAL_CSV=/absolute/path/to/conference-crawler/scripts/download/official_accepted_papers.csv \
python /absolute/path/to/conference-crawler/scripts/download/clean_and_classify_pdfs.py
```

For an isolated conference/year batch inside a shared PDF root, also set:

```bash
CONFERENCE_FILTER=ccs \
CONFERENCE_YEAR_FILTER=2025 \
CONFERENCE_CLEAN_OUTPUT_DIR=/absolute/path/to/collection-run/cleaning \
CONFERENCE_DOWNLOAD_DIR=/absolute/path/to/shared/pdf \
CONFERENCE_OFFICIAL_CSV=/absolute/path/to/official_accepted_papers.csv \
uv run --project /absolute/path/to/conference-crawler/scripts/download python \
  /absolute/path/to/conference-crawler/scripts/download/clean_and_classify_pdfs.py
```

The cleaning stage:

- accepts flat and nested PDF layouts;
- normalizes titles only for matching and preserves original files;
- computes SHA-256 and excludes duplicate files;
- excludes obvious workshop, poster, demo, tutorial, keynote, proceedings, and similar non-paper PDFs;
- accepts matches with fuzzy title score `>= 92`;
- sends scores `80-91` to `needs_review_possible_match`;
- sends lower scores and unmatched papers to `needs_review`;
- writes accepted files to `curated/<conference>/<year>/accepted/`;
- writes review/excluded files under corresponding `curated` directories;
- writes `metadata/official_accepted_papers_clean.csv` and `metadata/paper_manifest.csv`.

Do not treat a fuzzy match as proof of identity. Review the manifest, especially title score, conference, year, SHA-256, and reason, before downstream extraction.

## Handoff to GROBID

Pass only reviewed accepted PDFs to `$conference-grobid-extract-metadata`. Keep each conference/year batch isolated:

```bash
python3 /absolute/path/to/conference-grobid-extract-metadata/scripts/extract_paper_metadata.py \
  --input-dir /absolute/path/to/curated/ccs/2024/accepted \
  --output-dir /absolute/path/to/grobid-data \
  --conference ccs
```

Before statistics or normalization, audit the generated `paper_metadata.csv` with `$conference-clean-paper-metadata`. Preserve `paper_manifest.csv`, GROBID evidence, and review queues as provenance artifacts.

## Safety and quality gates

- Do not crawl a broad year range until a one-year sample succeeds.
- Respect site terms, robots guidance, authentication boundaries, and conservative request rates.
- Never overwrite a prior batch without an explicit archive or output directory change.
- A non-empty error/missing-PDF status, an unexpected paper-count drop, or a large review queue is a stop-and-review condition.
- Do not infer acceptance from a filename alone; use the official list plus manual review.
- Keep raw downloads separate from curated PDFs and never feed raw unreviewed PDFs directly into final statistics.

## Troubleshooting

- `No module named ...`: run through `uv run --project conference-crawler/scripts/download` or the bundled `.venv` Python, not system Python 3.9.
- IEEE/CCS browser failures: verify Chrome, driver, profile path, and login state; retry a single year with a fresh profile.
- Missing PDF URLs: retain the summary row and inspect the source proceedings page; do not fabricate a URL.
- Duplicate or wrong-title files: inspect `metadata/paper_manifest.csv` and use the SHA-256/title evidence before rerunning with `--force`.
