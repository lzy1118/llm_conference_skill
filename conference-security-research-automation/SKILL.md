---
name: conference-security-research-automation
description: Run the reusable conference PDF-to-data pipeline from GROBID metadata through affiliation splitting, AffilGood/ROR normalization, the 15-column final table, and optional analysis. Use for any conference/year paper dataset with reviewed PDFs; registered repository examples may add optional enrichments but are not a whitelist.
---

# Conference PDF Research Automation

The folder name is retained for backward compatibility. The runner itself is conference-neutral.

Run extraction from the repository root:

```bash
python3 conference-security-research-automation/scripts/run_pipeline.py --conference CCS --year 2025 \
  --pdf-dir /absolute/path/to/curated/ccs/2025/accepted \
  --pdf-manifest /absolute/path/to/download/metadata/paper_manifest.csv
```

When the skill is installed outside the repository, run it while the repository is the current directory,
or pass `--repo-root /absolute/path/to/llm_conference_skill`. The environment variable
`LLM_CONFERENCE_SKILL_ROOT` provides the same override for recurring automation.

The runner accepts any conference label. It normalizes the label to a stable slug, such as
`ACM SIGCOMM` to `acm_sigcomm`, and uses that slug in generated paths. ASIACRYPT, CRYPTO,
EUROCRYPT, CCS, IEEE S&P, NDSS, and USENIX Security are repository examples with exercised
profiles; they are not the complete supported set and should not be treated as the pipeline anchor.
All conference-paper datasets use the same GROBID PDF extraction and affiliation-normalization
stages. Registered examples may add supplementary enrichment: the four security examples use
official-web metadata reconciliation, while datasets without a registered adapter retain the GROBID
PDF record as the primary source.

Run a generic conference with reviewed PDFs:

```bash
python3 conference-security-research-automation/scripts/run_pipeline.py \
  --conference "ACM SIGCOMM" --year 2025 \
  --pdf-dir /absolute/path/to/sigcomm/2025/pdfs
```

Do not add a conference to a whitelist merely to run the common pipeline. Add a conference-specific
adapter only when its official metadata source or paper format needs behavior beyond the shared stages.
It runs these stages in order:

1. Extract the PDF with GROBID, pdfplumber, and pypdf as the primary record.
2. When a registered adapter exists, match the PDF record to the official conference website for
   supplementary metadata; otherwise skip this optional stage.
3. Fill only missing titles, author lists, or affiliations from a trusted unique match. Preserve every
   non-empty PDF value and record author-list or affiliation conflicts as diagnostics.
4. Replay PDF role linking after web supplementation so co-first and corresponding-author flags use
   the final author names.
5. Continue automatically through affiliation splitting, AffilGood/ROR normalization, institution
   reference fill, final export, and optional analytics.

If a registered official website adapter or its local cache is unavailable, record that status and
continue with PDF extraction. A supplementary website must not become a hard dependency of the
conference-neutral pipeline.

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
  --batch "ACM SIGCOMM:2025" --batch "NeurIPS:2025" \
  --pdf-manifest /absolute/path/to/download/metadata/paper_manifest.csv
```

`--pdf-dir` remains a single-batch option because one directory cannot represent multiple batches.
For a single batch without an explicit directory, the runner first uses
`conference-crawler/scripts/download/curated/<conference>/<year>/accepted` and automatically validates
it against `conference-crawler/scripts/download/metadata/paper_manifest.csv`; the legacy
`generated-data/pdf/<conference>/<year>` path remains a fallback. Model weights are loaded once per
batch runner invocation, so unrelated later updates should be added to the same command when practical.

The generic runner starts from reviewed local PDFs. Supporting an arbitrary conference does not mean
the crawler can automatically discover every proceedings website. When crawler coverage is unavailable,
provide `--pdf-dir` and optionally `--pdf-manifest` explicitly.

For collection-first experiments, run source discovery and metadata-only readiness upstream in
`conference-crawler` and inspect `conference-crawler/scripts/download/metadata/conference_collection_manifest.csv`.
After PDFs are downloaded, cleaned, and reviewed, pass the curated accepted PDF directory and
`paper_manifest.csv` into this runner. The collection manifest is a readiness/provenance artifact;
the reviewed PDF manifest remains the quality gate before GROBID.

Outputs follow the required contract: `generated-data/full_output/<conference>/<year>/author_metadata_dataset_<year>/`, `generated-data/extraction_raw/<conference>/<year>/<conference>_<year>_raw作者机构拆分.csv`, `generated-data/extraction_spilt/<conference>/<year>/<conference>_<year>_作者机构拆分_output.csv`, `generated-data/extraction_affilgood/<conference>/<year>/<conference>_<year>_affilgood_作者机构拆分_output.csv`, and `generated-data/extraction_final/<conference>/<year>/<conference>_<year>_final.csv`. Use the concrete lowercase conference slug in every generated path; do not encode umbrella labels such as three/four conferences in filenames. Institution processing is ordered as `prepare-only split -> AffilGood/ROR -> institution_raw post-fill`: the initial pass separates explicit PDF country/location evidence and obvious subunits without querying the institution table, AffilGood supplies the primary identity, and the final matcher fills only incomplete fields. It merges by stable `record_id` without overwriting stronger evidence. Deterministic post-match statuses distinguish reviewed rules, unique country-context identities, atomic composites, non-institutional markers, and unknown organizations. The runner writes `extraction_spilt/<conference>/<year>/<conference>_<year>_institution_match_report.json` and stops unless both `review_required` and `blank_country_actionable` are zero. It passes the full AffilGood table—not the 15-column author-affiliation export—to analytics. Use `--institution-table` to select a reviewed table explicitly, `--dry-run` to inspect commands, and `--skip-analysis` when the analysis skill is unavailable. The runner selects a local Python 3.11+ runtime automatically; override it with `--python`.

Before reporting completion, verify the final CSV has exactly 15 columns and that its `country` values are copied from `affilgood_location_country`. Preserve `emails`, `co_first_author`, and `equal_contribution` exactly from the upstream row. The `orcid` column is required but may be blank. Use `conference-analysis-automation` as the single facade for optional country, institution, author, trend, collaboration, audit, report, and visualization work. Run `conference-benchmark-comparison` only after two or more comparable analysis summaries exist; it is a cross-run comparison rather than a single-batch stage.
