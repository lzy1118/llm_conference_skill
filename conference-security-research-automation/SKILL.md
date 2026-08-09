---
name: conference-security-research-automation
description: Run the reproducible conference security-paper pipeline from PDFs through GROBID metadata, raw affiliation splitting, AffilGood normalization, and the 15-column final display table. Use when collecting or updating a conference/year dataset under generated-data.
---

# Security Research Automation

Run extraction from the repository root:

```bash
python3 conference-security-research-automation/scripts/run_pipeline.py --conference CCS --year 2025 \
  --pdf-dir /absolute/path/to/curated/ccs/2025/accepted \
  --pdf-manifest /absolute/path/to/download/metadata/paper_manifest.csv
```

When the skill is installed outside the repository, run it while the repository is the current directory,
or pass `--repo-root /absolute/path/to/llm_conference_skill`. The environment variable
`LLM_CONFERENCE_SKILL_ROOT` provides the same override for recurring automation.

The runner supports seven conferences: `ASIACRYPT`, `CRYPTO`, `EUROCRYPT`,
`CCS`, `IEEE_S&P`, `NDSS`, and `USENIX_SECURITY`. All seven use the same GROBID
PDF extraction and affiliation-normalization stages. The four security
conferences additionally use official-web metadata reconciliation; the three
LNCS conferences retain the GROBID PDF record as the primary metadata source.
It runs these stages in order:

1. Extract the PDF with GROBID, pdfplumber, and pypdf as the primary record.
2. Match the PDF record to the official conference website for supplementary metadata.
3. Fill only missing titles, author lists, or affiliations from a trusted unique match. Preserve every
   non-empty PDF value and record author-list or affiliation conflicts as diagnostics.
4. Replay PDF role linking after web supplementation so co-first and corresponding-author flags use
   the final author names.
5. Continue automatically through affiliation splitting, AffilGood/ROR normalization, institution
   reference fill, final export, and optional analytics.

If the official website and its local cache are unavailable, record that status and continue with the
PDF extraction. The supplementary website must not become a hard dependency of the PDF pipeline.

Use `--reuse-extraction` to continue from an existing PDF extraction dataset without rerunning GROBID.
When a crawler manifest is available, pass `--pdf-manifest` together with the reviewed
`curated/.../accepted` directory. The runner verifies accepted filenames and SHA-256 values,
then copies the manifest into the GROBID batch directory as `source_pdf_manifest.csv`.

For consecutive conference/year updates, repeat `--batch CONFERENCE:YEAR` instead of launching
the runner separately. Batch mode prepares every batch independently, runs all unresolved
affiliations through one shared AffilGood model instance, and then completes each batch's merge,
quality gates, final export, and optional analysis. It preserves the same per-conference/year paths:

```bash
python3 conference-security-research-automation/scripts/run_pipeline.py \
  --batch ASIACRYPT:2025 --batch CRYPTO:2025 --batch EUROCRYPT:2025 \
  --pdf-manifest /absolute/path/to/download/metadata/paper_manifest.csv
```

`--pdf-dir` remains a single-batch option because one directory cannot represent multiple batches.
Without an explicit directory, the runner first uses
`conference-crawler/scripts/download/curated/<conference>/<year>/accepted` and automatically validates
it against `conference-crawler/scripts/download/metadata/paper_manifest.csv`; the legacy
`generated-data/pdf/<conference>/<year>` path remains a fallback. Model weights are loaded once per
batch runner invocation, so unrelated later updates should be added to the same command when practical.

Outputs follow the required contract: `generated-data/full_output/<conference>/<year>/author_metadata_dataset_<year>/`, `generated-data/extraction_raw/<conference>/<year>/<conference>_<year>_raw作者机构拆分.csv`, `generated-data/extraction_spilt/<conference>/<year>/<conference>_<year>_作者机构拆分_output.csv`, `generated-data/extraction_affilgood/<conference>/<year>/<conference>_<year>_affilgood_作者机构拆分_output.csv`, and `generated-data/extraction_final/<conference>/<year>/<conference>_<year>_final.csv`. Use the concrete lowercase conference slug in every generated path; do not encode umbrella labels such as three/four conferences in filenames. Institution processing is ordered as `prepare-only split -> AffilGood/ROR -> institution_raw post-fill`: the initial pass separates explicit PDF country/location evidence and obvious subunits without querying the institution table, AffilGood supplies the primary identity, and the final matcher fills only incomplete fields. It merges by stable `record_id` without overwriting stronger evidence. Deterministic post-match statuses distinguish reviewed rules, unique country-context identities, atomic composites, non-institutional markers, and unknown organizations. The runner writes `extraction_spilt/<conference>/<year>/<conference>_<year>_institution_match_report.json` and stops unless both `review_required` and `blank_country_actionable` are zero. It passes the full AffilGood table—not the 15-column author-affiliation export—to analytics. Use `--institution-table` to select a reviewed table explicitly, `--dry-run` to inspect commands, and `--skip-analysis` when the analysis skill is unavailable. The runner selects a local Python 3.11+ runtime automatically; override it with `--python`.

Before reporting completion, verify the final CSV has exactly 15 columns and that its `country` values are copied from `affilgood_location_country`. Preserve `emails`, `co_first_author`, and `equal_contribution` exactly from the upstream row. The `orcid` column is required but may be blank. Use `conference-analysis-automation` as the single facade for optional country, institution, author, trend, collaboration, audit, report, and visualization work. Run `conference-benchmark-comparison` only after two or more comparable analysis summaries exist; it is a cross-run comparison rather than a single-batch stage.
