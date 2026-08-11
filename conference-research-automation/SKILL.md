---
name: conference-research-automation
description: Run an extensible PDF-first conference-paper metadata pipeline through one compatible entry point. Use for any conference-paper dataset when reviewed PDFs are available, and automatically apply conference-specific enrichment only when a registered example profile exists.
---

# Conference Research Automation

Use `scripts/run_pipeline.py` as the conference-neutral entry point for paper datasets. The repository
contains example profiles that have been exercised on ASIACRYPT, CRYPTO, EUROCRYPT, CCS, IEEE S&P,
NDSS, and USENIX Security, but those examples are not the anchor or boundary of the pipeline.

Every conference follows the shared PDF-first contract:

1. Extract paper and author metadata from PDFs with GROBID and PDF evidence.
2. Link author roles from the PDF record.
3. Split raw affiliations.
4. Normalize institutions and locations with AffilGood/ROR and reviewed reference data.
5. Generate the final author-affiliation table and optional analysis outputs.

Known profiles add narrowly scoped behavior without changing the common contract:

- CCS, IEEE S&P, NDSS, and USENIX Security use the registered official-web reconciliation stage.
- ASIACRYPT, CRYPTO, and EUROCRYPT use the existing LNCS/cryptography path and primary-institution rules.
- Every other conference uses the generic PDF-first path. Its PDF record remains authoritative unless a
  conference-specific adapter is added later.

When source discovery/crawling is available, prepare collection readiness upstream with
`conference-crawler/scripts/batch_runner.py` and inspect
`conference-crawler/scripts/download/metadata/conference_collection_manifest.csv`. This skill starts
from reviewed local PDFs; it does not require the paper source to be one of the historical examples.

Run an existing example profile:

```bash
python3 conference-research-automation/scripts/run_pipeline.py \
  --conference crypto \
  --year 2025
```

Run any other conference-paper dataset without editing a whitelist:

```bash
python3 conference-research-automation/scripts/run_pipeline.py \
  --conference "ACM SIGCOMM" \
  --year 2025 \
  --pdf-dir /absolute/path/to/sigcomm/2025/pdfs
```

Conference labels are normalized to stable lowercase path slugs, for example `ACM SIGCOMM` becomes
`acm_sigcomm`. Generated artifacts continue to use
`generated-data/<stage>/<conference-slug>/<year>/`.

Use `--dry-run` to inspect the selected chain. Use `--reuse-extraction` to continue from an existing
`full_output/<conference-slug>/<year>/author_metadata_dataset_<year>` directory. Use
`--skip-analysis` when only extraction and normalization outputs are required.

Supporting all conference-paper datasets means the common PDF pipeline accepts any valid conference
label and reviewed PDF corpus. It does not imply that every publisher website has a dedicated crawler
or metadata reconciler. Require a reviewed PDF input, and add a conference-specific adapter only when
its publication format or official source needs behavior beyond the common pipeline.
