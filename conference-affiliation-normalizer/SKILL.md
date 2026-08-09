---
name: conference-affiliation-normalizer
description: Normalize raw research affiliation strings from scraped paper metadata into structured institutions, subunits, locations, languages, confidence scores, and identifiers using AffilGood plus reviewed personal alias, typo, ROR, country, and scoped paper-author rules. Use when Codex is enriching publication records, cleaning affiliation columns in CSV/JSONL/TXT files, preparing institution data for deduplication or analytics, applying reviewed institutional corrections, or adding an affiliation-normalization stage to an automated collection pipeline.
---

# Affiliation Normalizer

## Workflow

Use this skill as the affiliation enrichment stage in a paper or metadata ingestion pipeline. This
project copy bundles an AffilGood source/runtime directory and data entry; an external checkout may
still be supplied when desired.

Resolve `<skill-dir>` as the directory containing this `SKILL.md`. Set `AFFILGOOD_DIR` when using an
editable checkout; otherwise use the Python environment where `affilgood` is installed.

1. Confirm the source file contains raw affiliation text. Prefer JSONL with one record per line.
2. Read `references/schema.md` when choosing fields or merging outputs into a larger dataset.
3. For split CSV input, parse explicit terminal country and known city components with
   `scripts/match_institution_reference_csv.py --prepare-only`; do not query `institution_raw.csv`
   before AffilGood.
4. Run `scripts/run_affilgood.py` for the prepared rows. AffilGood/ROR output is the primary identity
   source.
5. Run `scripts/match_institution_reference_csv.py` again on the merged AffilGood CSV to fill only
   missing institution, ROR, country, or city values from `institution_raw.csv`.
6. Apply the bundled reviewed rules by default. Read `references/personal-rule-policy.md` before adding or broadening a rule.
   Keep the fixed English display names `Shanghai Qi Zhi Institute` and `Zhongguancun Laboratory`; normalize their reviewed spelling variants before producing institution statistics.
7. Preserve source identifiers such as `record_id`, `paper_id`, `author`, `doi`, or row number so downstream stages can merge results and scoped rules can match safely.
8. Write failed rows with `status: "error"` instead of dropping them.
9. For a user-facing display table, run `scripts/generate_final_view.py` on the conference
   AffilGood CSV. The display `country` must copy `affilgood_location_country` exactly; do not
   fall back to a legacy `country` column or infer it from affiliation text.

For split author-affiliation CSV files, run the matcher in `--prepare-only` mode before AffilGood. It
writes stable `record_id` values, separates high-confidence country/location evidence, and retains
obvious subunits without querying `institution_raw.csv`. After AffilGood has been merged by
`record_id`, run the matcher again in its default mode. It preserves every non-empty AffilGood/ROR
field and uses `institution_raw.csv` only to fill incomplete results.

## Processing order

Execute the stages in this order; do not let a later heuristic overwrite stronger evidence:

1. Read source rows and preserve a stable identifier.
2. For split CSV automation, extract only explicit terminal countries and known terminal cities; preserve their raw evidence and never infer a country from a city alone.
3. Generate full, component, contiguous-component, and parenthetical institution candidates, but defer
   institution-table matching until AffilGood has run.
4. Accept AffilGood/ROR identity first. When multiple identities are explicitly aligned to
   multiple institution or country components, split them into separate analytics components;
   retain the raw composite for audit. Components without a reliable identity are residuals and
   are discarded from rankings and displays.
5. Use `institution_raw.csv` only after AffilGood, and only to fill incomplete fields. Never replace a
   non-empty AffilGood institution, ROR, country, or city.
6. Apply reviewed personal rules from `references/personal-rules.json`.
7. Resolve deterministic cases to auditable terminal statuses and never replace non-empty explicit or
   reviewed values during merge. Use `not_applicable_noninstitutional` for explicit non-institutional
   markers and `unknown_organization` when no reviewed identity exists.
8. Write one JSONL result for every input row, including `ok`, `skipped`, or `error` status.
9. Join results back by `record_id`; never join by output row order.

For analytics facts, the preparation stage also collapses obvious OCR whitespace and case variants in
author names (for example `Xiaoyun Wang`, `Xiaoyun WAng`, and `Xiaoyun Wa Ng`) to one stable
`author_key`. The source `author` and raw affiliation text remain available for audit.

Keep the raw affiliation and original input row unchanged. Standard names, ROR identifiers, countries,
and cities are enrichment fields, not replacements for source text.

Treat one source `affiliation_rank` as one auditable source record. When AffilGood returns multiple
semicolon- or pipe-delimited organizations with aligned identities, emit one analytics fact and
institution-table identity per resolved component, while preserving the complete raw composite.
Unaligned or unrecognized components are residuals and must not be shown or counted. A reviewed
composite such as `Laboratoire LIP (U. Lyon, ENS de Lyon, CNRS, ENSL, Inria, UCBL)` is split only
when its components have reliable identities; otherwise the unresolved fragments are dropped.

Standalone organizational units such as `School of ...`, `Department of ...`, `Faculty of ...`,
`College of ...`, `Division of ...`, `Laboratory of ...`, or `Institute of Cyberspace Security`
are treated as secondary units. They remain in
`affiliation_subunits` (and the raw `affiliations` field) but cannot be selected as the primary
institution unless a parent institution is also present and matched. Rows containing only such a
unit are retained for audit with no primary institution identity and are excluded from institution
rankings.

Reviewed standalone institutions are exceptions to the secondary-unit rule. An exact `State Key
Laboratory of Cryptology` affiliation is matched as its own institution. The composite phrases
`Institute of Information Engineering, Chinese Academy of Sciences` and `Institute of Information
Engineering, CAS` are matched to the reviewed `Institute of Information Engineering` record as one
institution; the parent academy is not counted separately for that row.

## Three IACR conferences: current input

For `CRYPTO`, `EUROCRYPT`, and `ASIACRYPT`, use the current consolidated author-affiliation file at
`outputs/crypto_2020_2025_author_affiliations/三大密码会_2020-2025_作者机构元数据.csv`.
Do not use retired snapshot directories or paper-experiment outputs as normalization inputs.

## Four security conferences: primary institution extraction

For `CCS`, `IEEE S&P`, `NDSS`, and `USENIX Security`, use
`scripts/extract_security_primary_institutions.py` after the post-AffilGood
`institution_raw.csv` fill. Apply country supplementation first, then the country-compatible
AffilGood/ROR identity, then `institution_raw.csv`, reviewed supplements, and the final supplement
queue. A missing ROR is not incomplete when the row already has one unique reviewed
`institution_raw.csv` local ID; send it to the supplement queue only when both the ROR and reviewed
local institution identity are absent.

```bash
python3 conference-affiliation-normalizer/scripts/extract_security_primary_institutions.py \
  --input-dir generated-data/security_2020_2025_institution_extraction_20260731/extraction_affilgood_postmatched \
  --output-dir generated-data/security_2020_2025_institution_extraction_20260731/primary_institution \
  --institution-table generated-data/institution_raw.csv
```

When adding observed institution aliases back to `institution_raw.csv`, run
`scripts/supplement_institution_aliases_same_id.py`. Append each alias as a separate row and preserve
the original institution row unchanged. Reuse `conference_id` and `conference_final_id` only when one
existing identity is confirmed by local ID or country-compatible ROR/name evidence. Never merge the
alias text into the original row and never mint a new ID for an alias; unresolved or conflicting aliases
go to the review queue.

## Split CSV and final display workflow

For the conference automation contract, first enrich the already split author-affiliation CSV with the
reviewed institution table:

```bash
python3 scripts/match_institution_reference_csv.py \
  --input generated-data/extraction_raw/ccs/2025/ccs_2025_raw作者机构拆分.csv \
  --output generated-data/extraction_spilt/ccs/2025/ccs_2025_作者机构拆分_output.csv \
  --institution-table generated-data/institution_raw.csv \
  --report generated-data/extraction_spilt/ccs/2025/ccs_2025_institution_match_report.json \
  --prepare-only
```

After merging AffilGood results, run the same command without `--prepare-only`, using the merged
AffilGood CSV as `--input` and a new output path. The default mode is the post-AffilGood institution
reference stage.

After running AffilGood only for unresolved rows and merging results by `record_id`, generate the display
table from the merged `*affilgood*作者机构拆分_output.csv`:

```bash
python3 scripts/generate_final_view.py \
  --input generated-data/extraction_affilgood/ccs/2025/ccs_2025_affilgood_作者机构拆分_output.csv \
  --conference CCS --year 2025 \
  --output generated-data/extraction_final/ccs/2025/ccs_2025_final.csv
```

The display output has exactly these fields: `paper_id`, `year`, `conference`, `title`, `author`,
`author_rank`, `affiliation_rank`, `affiliations`, `emails`, `first_author`, `co_first_author`,
`corresponding`, `equal_contribution`, `country`, and `orcid`. Preserve `emails`,
`co_first_author`, and `equal_contribution` exactly from the upstream row. The `orcid` column is
required but may be blank. The `country` value must come only from
`affilgood_location_country`. Name it `<conference>_final.csv` without a year filter, or
`<conference>_<year>_final.csv` with one.

In the display table, `affiliations` contains the reviewed `primary_institution` when that field is
available. The raw affiliation remains unchanged in the source enrichment table. If a primary field
is unavailable, fall back to the AffilGood standard institution, then the observed AffilGood name,
and only then the raw affiliation text.

## Institution-reference policy

Treat `institution_raw.csv` as a reviewed project dictionary, not a universal global registry:

- A reviewed pattern for `CISPA` always resolves its institution component to `Helmholtz Center for Information Security` (`https://ror.org/02njgxr09`). The same canonical form must be retained in both the runtime rules and `institution_raw.csv` aliases.

- Match exact normalized observed or canonical names first.
- When the raw observed name and a model-expanded canonical name select different records, prefer the raw exact match.
- Collapse duplicate table rows only when their stable local ID and country are both equal.
- Accept one stable institution identity only when it is compatible with explicit country evidence; require country context for short acronyms.
- For multiple candidates, preserve the source `affiliation_rank` as one deterministic atomic identity.
- Keep `_institution_reference_review` only when deterministic resolution itself fails.
- Treat `conference_id` and `conference_final_id` as auditable local references, never as global IDs.
- Do not infer a missing institution from a city, email domain, acronym, or fuzzy string when the table has no unique match.
- Do not let a matched country suppress AffilGood when the institution remains unresolved.
- Require both `review_required` and `blank_country_actionable` to be zero before downstream publication.

## Automated quality gate

After a run, inspect JSONL before downstream analytics. Block publication or institution statistics when
`error > 0`, when the error rate exceeds the pipeline threshold, or when unresolved reference reviews
have not been accepted. `skipped` rows are not failures, but must be counted and reported.

```bash
PYTHON=/absolute/path/to/python3.11
"$PYTHON" -c 'import json,sys,collections; c=collections.Counter(); [((c.update([r.get("status","error")]), c.update(["reference_review"]) if r.get("affilgood",{}).get("_institution_reference_review") else None)) for r in map(json.loads, open(sys.argv[1], encoding="utf-8"))]; print(c)' \
  /absolute/path/results.jsonl
```

## Quick Start

The Skill includes an AffilGood runtime and project-local data entry:

```bash
SKILL_DIR=/absolute/path/to/conference-affiliation-normalizer
AFFILGOOD_DIR="$SKILL_DIR/affilgood-runtime"
AFFILGOOD_DATA_DIR="$SKILL_DIR/affilgood-data"
PYTHON=/absolute/path/to/python3.11
"$PYTHON" \
  "$SKILL_DIR/scripts/run_affilgood.py" \
  --input affiliations.jsonl \
  --output affiliations.normalized.jsonl \
  --affilgood-path "$AFFILGOOD_DIR" \
  --data-dir "$AFFILGOOD_DATA_DIR" \
  --id-field record_id \
  --affiliation-field affiliation
```

The bundled rules are enabled by default. Use `--no-personal-rules` for a pure AffilGood baseline, or
`--personal-rules /path/to/rules.json` to use a reviewed replacement rule set. Successful results list
applied rule IDs under `affilgood._personal_rules`.

The bundled `references/institution_raw.csv` snapshot is the primary exact-reference table. When the
`--affilgood-path` project is supplied, the default lookup prefers its `data/institution_raw.csv`;
override it with `--institution-table` or `AFFILGOOD_INSTITUTION_TABLE`. Matches are recorded under
`affilgood._institution_reference`; ambiguous same-name candidates are recorded under
`affilgood._institution_reference_review` and are not auto-selected.

Refresh the bundled snapshot only from a reviewed project table:

```bash
SOURCE_AFFILGOOD_DIR=/absolute/path/to/reviewed/affilgood-project
cp "$SOURCE_AFFILGOOD_DIR/data/institution_raw.csv" "$SKILL_DIR/references/institution_raw.csv"
```

Record the refresh date and validate the skill after replacing the snapshot.

For CSV input:

```bash
"$PYTHON" \
  "$SKILL_DIR/scripts/run_affilgood.py" \
  --input papers.csv \
  --input-format csv \
  --output papers.affiliations.jsonl \
  --id-field paper_id \
  --affiliation-field affiliation \
  --affilgood-path "$AFFILGOOD_DIR" \
  --data-dir "$AFFILGOOD_DATA_DIR"
```

For plain text input, each non-empty line is treated as one affiliation and the output id is the 1-based line number.

## Input and option guide

| Need | Options |
|---|---|
| JSONL/CSV/TXT | `--input`, `--input-format`, `--affiliation-field` |
| Stable joins | `--id-field`; preserve `paper_id`, `doi`, and `author` in source rows |
| Current project table | `--affilgood-path /path/to/affilgood` |
| Alternate table snapshot | `--institution-table /path/to/institution_raw.csv` |
| Baseline comparison | `--no-personal-rules --no-institution-table` |
| CPU automation | `--device cpu --batch-size 16` or a measured batch size |
| Fast extraction without ROR | `--no-entity-linking` |
| Default entity disambiguation | `--reranker cross_encoder` |
| Low-confidence LLM disambiguation | `--llm-judge` or `--llm-judge Qwen/Qwen2.5-1.5B-Instruct` |
| Diagnostic evidence | `--return-debug --verbose` |

Use Python 3.11+ for the bundled AffilGood runtime. Use `--check-setup` before a large job. It verifies the bundled AffilGood import, required ML modules, and data cache without
loading the processing models. A normal run must stop when the NER model, entity linker, or geocoder silently fails to initialize; an all-empty `status=ok` output is not success. An external AffilGood checkout and data directory can still be supplied
with `--affilgood-path` and `--data-dir`.

## AffilGood Setup

The Skill bundles AffilGood source and model/data files, but not a platform-specific virtualenv. Install
the Python dependencies in a Python 3.11+ environment, then run the Skill with that environment's
Python executable.

```bash
pip install -e "$AFFILGOOD_DIR"
```

The script also calls `affilgood.data_manager.ensure_data()` before processing, so it can download/cache required ROR and FAISS data when network access is available. To reuse an existing data cache, set `AFFILGOOD_DATA_DIR` or pass `--data-dir`.

Check import and data availability without loading the heavy processing models:

```bash
"$PYTHON" \
  "$SKILL_DIR/scripts/run_affilgood.py" \
  --affilgood-path "$AFFILGOOD_DIR" \
  --check-setup
```

## Runtime Choices

- Use `--batch-size` to control memory and throughput.
- Use `--device cpu` for predictable local automation, or `--device cuda` when the host has a configured GPU.
- Use `--no-entity-linking` only when a fast NER/location-only pass is enough.
- Keep `--reranker cross_encoder` for the default cascade. Add `--llm-judge` only when the local
  instruction model is available; it performs listwise disambiguation for candidates below
  `--llm-threshold` and is substantially heavier than the default path.
- Use `--no-normalization` only when geocoding or location normalization should be skipped.
- Use `--add-nuts` when European NUTS region enrichment is needed.
- Use `--return-debug` only for diagnostics because the output becomes much larger.

## Output Handling

Treat the output JSONL as an enrichment artifact. Join it back to upstream records by `record_id`; do not rely on row order alone when the upstream workflow can retry, shard, or concatenate jobs.

Use the top-level `status` field for orchestration:

- `ok`: AffilGood returned a result.
- `skipped`: the source row had an empty affiliation.
- `error`: the row failed; inspect `error`.

Keep raw affiliation text unchanged. Treat personal rules as a post-processing layer and do not copy
project-local `INST####` identifiers into new datasets as global IDs. They may be retained under the
auditable `institution_reference` block only as references to this table. Send ambiguous acronyms,
conflicting countries, and fuzzy-only matches to review.

## Final display table

Create the fixed 15-column display export after institution reference matching and AffilGood fallback:

```bash
python3 scripts/generate_final_view.py \
  --input generated-data/extraction_affilgood/ccs/2025/ccs_2025_affilgood_作者机构拆分_output.csv \
  --conference CCS \
  --year 2025 \
  --output generated-data/extraction_final/ccs/2025/ccs_2025_final.csv
```

The output is `CCS_2025_final.csv`. Without `--year`, it is `CCS_final.csv`. Its columns are:

```text
paper_id,year,conference,title,author,author_rank,affiliation_rank,affiliations,emails,
first_author,co_first_author,corresponding,equal_contribution,country,orcid
```

Rows outside the requested conference or year are excluded. A blank
`affilgood_location_country` remains blank in `country`. The quality gate separates intentional
non-institutional blanks from actionable missing countries and requires the latter to be zero.
The `emails`, `co_first_author`, and `equal_contribution` values are copied without rewriting;
missing `orcid` values are emitted as blank strings.

## Updating the Skill data

When the reviewed project table changes, refresh the bundled snapshot and validate the skill:

```bash
SOURCE_AFFILGOOD_DIR=/absolute/path/to/reviewed/affilgood-project
cp "$SOURCE_AFFILGOOD_DIR/data/institution_raw.csv" "$SKILL_DIR/references/institution_raw.csv"
"$PYTHON" "$CODEX_HOME/skills/.system/skill-creator/scripts/quick_validate.py" "$SKILL_DIR"
```

Update `personal-rules.json` only for stable, reviewed rules. Do not copy one-off conference output
repair scripts into the default matcher.
