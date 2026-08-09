---
name: conference-clean-paper-metadata
description: Check, repair, and enrich paper-author metadata CSV files from GROBID or PDF extraction. Use when Codex is asked to audit, clean, validate, or update academic paper author rows with fields such as year, conference, title, author, author_rank, affiliations, emails, first_author, co_first_author, corresponding, equal_contribution, abstract, doi, laboratory, department, or institution; especially for co-first/equal-contribution logic, author ordering, fake authors from extraction, malformed names, affiliations, emails, OCR artifacts, and adding abstracts/DOIs or segmented TEI organizations from local GROBID outputs.
---

# Clean Paper Metadata

## Workflow

1. Audit first, then edit. Run `scripts/audit_author_metadata.py <csv>` to identify structural problems and high-risk extraction candidates. Do not bulk edit based only on regex output.
2. Treat one paper as the unit of repair. Group rows by `(year, conference, title)` and preserve all unrelated rows.
3. Verify suspicious rows against primary local evidence when available: the source PDF first page, TEI header XML, metadata JSON, or year-level `paper_metadata.csv`. Prefer PDF first-page author block and footnotes over derived CSVs when they disagree.
4. Make narrow edits only after evidence is clear. Re-run the audit after every edit batch.
5. Report what was changed and what remains as unresolved candidates.

Resolve `<skill-dir>` as the directory containing this `SKILL.md`. Do not assume a user-specific
absolute installation path.

## Automated Collection Gate

1. Run the audit before any in-place enrichment:

   ```bash
   SKILL_DIR=/absolute/path/to/conference-clean-paper-metadata
   python3 "$SKILL_DIR/scripts/audit_author_metadata.py" /absolute/path/paper_metadata.csv
   ```

2. Interpret exit status `0` as no blocking structural findings, `1` as detected metadata findings, and
   `2` as missing required columns or inconsistent row widths. Treat every other nonzero result as a task
   failure. Preserve the report as a batch artifact.
3. Run enrichment scripts with `--dry-run` first and capture coverage. Do not write when output roots are
   missing, normalized title keys are ambiguous, or unmatched-paper coverage exceeds the pipeline's
   explicit acceptance threshold.
4. Copy or snapshot the CSV before in-place enrichment. Verify row count and paper keys are unchanged
   afterward, then run the audit again.
5. Do not auto-repair evidence-dependent findings such as fake authors, co-first roles, corresponding
   authors, fragmented affiliations, or malformed grouped emails from regex signals alone. Route them to
   manual review or an evidence-backed repair stage.
6. Run `$conference-affiliation-normalizer` only after extraction repair is accepted. Keep raw publication wording in
   `affiliations`; write normalized institutions to separate structured fields.

## Core Rules

- `author_rank` is zero-based order within a paper.
- A normal paper has exactly one `author_rank=0`, and only that row has `first_author=true`.
- A co-first/equal-contribution paper has at least two rows with:
  - `author_rank=0`
  - `first_author=true`
  - `co_first_author=true`
  - `equal_contribution=true`
- `co_first_author=true` implies `equal_contribution=true`, `first_author=true`, and rank `0`.
- A source may explicitly mark equal contribution among later authors without claiming joint first authorship. In that case keep normal author order, set only `equal_contribution=true`, and require at least two evidence-linked authors.
- If multiple co-first authors share rank `0`, renumber subsequent authors continuously from `1`.
- `corresponding=true` is independent of first authorship. It can apply to first authors, later authors, or multiple authors,
  but only with an explicit PDF/TEI name, symbol, envelope, or footnote mapping. An email alone is not sufficient;
  absent a marker, keep `false` and route the paper to review.

## Repair Heuristics

Use these as candidates, not final proof:

- A single row with `co_first_author=true/equal_contribution=true` is invalid. Check the PDF footnote for the missing co-first author rather than simply clearing the flag.
- Rows whose `author` contains braces, digits, slashes, institution words, email fragments, or strings like `Edu`, `University`, `Keccak`, `Sha3`, `Csiro` are likely extraction artifacts.
- Names shaped like a detached initial plus a name, such as `B Fermi`, `B Kang`, or `S Ruthi Sekar`, may be OCR spacing/order errors. Confirm with the PDF and with same-email occurrences in other papers before changing.
- Duplicate or impossible authors within one paper often indicate that an email brace group or affiliation line was parsed as authors. Check the PDF author block and delete false rows only when the true author list is clear.
- Incomplete affiliations such as `University, Melbourne, Australia` may need the missing institution prefix from the PDF.
- Malformed emails usually contain spaces, missing `@`, brace fragments, or punctuation from grouped email syntax. Reconstruct only when the PDF clearly gives the address.

## Title Issues

Treat title normalization separately from author metadata unless the user asks to fix titles.

- Common OCR candidates include ` -` before subtitle text, stray dots before math tokens (`. SIS`, `. Z 2 k`, `. BatchQMA`), and split words such as `R andom` or `Argumen ts`.
- Do not blindly remove spaces around math notation; some extracted math spacing is meaningful or at least not safely inferable.

## Abstract and DOI Enrichment

When the user asks to add abstracts or DOI values to raw author CSV files:

1. Prefer local GROBID outputs over web lookup.
2. Use `metadata_json/*.json` for `abstract`; it is already paper-level and should be repeated on every author row for that paper.
3. Use the matching TEI header XML for DOI, typically `<idno type="DOI">...</idno>`.
4. Match paper records by `(year, conference, title)`. If exact matching fails, report unmatched papers rather than guessing.
5. Add `abstract` and `doi` as final columns if missing; update them in place if present.
6. Preserve row order and all existing author-level fields.
7. After enrichment, verify row count is unchanged and report coverage: papers matched, papers missing abstract, papers missing DOI.

The extraction pipeline also writes a paper-level `conference_year_paper_abstract.csv` beside
`paper_metadata.csv`, with exactly `conference,year,title,abstract`. Prefer this table for paper-level
abstract analysis instead of reconstructing it from repeated author rows.

Run:

```bash
python3 "$SKILL_DIR/scripts/enrich_abstract_doi.py" path/to/file.csv
```

For a combined CSV containing multiple conferences, pass all relevant output roots if auto-detection is not enough:

```bash
python3 "$SKILL_DIR/scripts/enrich_abstract_doi.py" path/to/file.csv \
  --full-output /path/to/asiacrypt_full_output \
  --full-output /path/to/crypto_full_output \
  --full-output /path/to/eurocrypt_full_output
```

## Organization Segment Enrichment

When the user asks to extract TEI `laboratory`, `department`, or `institution` segments:

1. Use TEI header XML from local `*_full_output/author_metadata_dataset_*/tei_header_xml`.
2. For each TEI `<author>`, collect `orgName` values by `type`:
   - `orgName type="laboratory"` -> `laboratory`
   - `orgName type="department"` -> `department`
   - `orgName type="institution"` -> `institution`
3. Match to CSV rows by `(year, conference, title)` and author name. If name matching fails but author order is safe, fall back to author order within the same paper.
4. If an author has multiple affiliations, join values of the same type with `; ` and deduplicate while preserving order.
5. Add `laboratory`, `department`, and `institution` as final columns if missing; update them in place if present.
6. Preserve row order and all existing fields.

Run:

```bash
python3 "$SKILL_DIR/scripts/enrich_tei_org_segments.py" path/to/file.csv
```

For combined CSVs, pass all relevant output roots if needed:

```bash
python3 "$SKILL_DIR/scripts/enrich_tei_org_segments.py" path/to/file.csv \
  --full-output /path/to/asiacrypt_full_output \
  --full-output /path/to/crypto_full_output \
  --full-output /path/to/eurocrypt_full_output
```

## Evidence Pattern

When source PDFs are available, extract the first page text and inspect the author block and footnotes. Useful evidence includes:

- `(B)` or envelope markers for corresponding authors.
- Footnotes like `A and B declare equal contribution` or `A and B are co-first authors`.
- Grouped emails like `{a,b}@domain`, which can identify names and missing emails.
- Numbered affiliations that restore incomplete institution names.

## Script

Run:

```bash
python3 "$SKILL_DIR/scripts/audit_author_metadata.py" path/to/file.csv
```

The script prints:

- CSV structure and blank counts.
- rank/first-author/co-first/equal-contribution rule violations.
- duplicate author rows within a paper.
- malformed email candidates.
- suspicious author-name candidates.
- likely OCR/title candidates.
