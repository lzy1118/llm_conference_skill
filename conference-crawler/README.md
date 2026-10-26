# Conference Crawler

This project now has a two-layer shape:

1. Source Discovery
2. Crawling and metadata extraction

## Source Discovery

The source discovery layer automatically resolves conference proceedings entry points based on conference identity and year. It separates conference-specific source resolution from downstream crawling and metadata extraction.

中文：

源发现层负责根据会议标识和年份自动定位论文集入口，将会议来源解析与后续论文抓取过程解耦。

Each resolver returns the same normalized record shape:

```json
{
  "conference": "neurips",
  "year": 2024,
  "source": "neurips",
  "backend": "neurips",
  "url": "https://papers.nips.cc/paper_files/paper/2024",
  "status": "success"
}
```

This keeps `spider.py` stable when adding new conference resolvers.

## CFP deadline observations

The deadline collector is separate from proceedings discovery and currently has configured official CFP URL templates for CRYPTO, NeurIPS, and ICML. It extracts only explicitly labeled abstract, full-paper, or submission deadlines; notification and camera-ready dates are not treated as submission deadlines.

```bash
python conference-crawler/scripts/source-discovery/deadlines.py \
  --conferences crypto,neurips,icml \
  --years 2024,2025
```

`--years` accepts comma-separated years, for example `2024,2025`. The output defaults to `conference-crawler/scripts/download/metadata/conference_deadline_observations.csv`; provide `--output` to choose another path. Records retain the CFP URL, final URL, observation time, source SHA-256, extracted date, timezone text, and matching evidence text. A changed page version is retained as a separate observation. `no_deadline_found`, `no_configured_source`, and fetch failures remain explicit statuses rather than fabricated dates. WWW currently has no built-in official CFP template; a single conference/year can use `--source-url` while its official source is reviewed.

The collector records what the page states when fetched. It does not infer the first/original deadline from later extensions or archived versions, and parsed dates must be checked against the retained evidence before publication.

## Test report

Metadata-only smoke tests write a JSON report at:

`scripts/download/metadata/discovery_test_report.json`

It can be used to compare yearly paper counts and detect unexpected drops.
Each entry includes the conference, year, backend, discovered URL count, parsed paper count, and pass/fail status.

## Batch collection experiments

The formal metadata-only production entry point is:

```bash
python conference-crawler/scripts/batch_runner.py \
  --conferences crypto,www,neurips,icml \
  --years 2024-2025
```

Conference metadata is configured in:

`configs/conferences.yaml`

The runner writes:

- `scripts/download/metadata/batch_metadata_report.json`
- `scripts/download/metadata/conference_collection_manifest.csv`

The batch runner does not download PDFs. It only validates source discovery,
metadata parsing, paper counts, and collection readiness for the requested
conference/year combinations.
