# Affiliation Normalizer Schema

## Input

Prefer JSONL with one record per line:

```json
{"record_id":"paper-001","affiliation":"MIT, Cambridge, USA"}
{"record_id":"paper-002","affiliation":"Tsinghua University, Beijing, China"}
```

Required fields:

- `affiliation`: raw affiliation string, configurable with `--affiliation-field`.

Recommended fields:

- `record_id`: stable upstream id, configurable with `--id-field`.
- `paper_id`, `doi`, `source_url`, or other provenance fields. These are preserved under `source_record` unless `--no-source-record` is used.

CSV input is supported with a header row. TXT input treats each non-empty line as one affiliation and uses the 1-based line number as `record_id`.

## Output

The script writes JSONL. Successful rows have this shape:

```json
{
  "record_id": "paper-001",
  "affiliation": "MIT, Cambridge, USA",
  "status": "ok",
  "affilgood": {
    "raw_text": "MIT, Cambridge, USA",
    "outputs": [
      {
        "input": "MIT, Cambridge, USA",
        "institutions": [],
        "subunits": [],
        "location": {},
        "language": null,
        "confidence": null
      }
    ]
  },
  "source_record": {
    "record_id": "paper-001",
    "affiliation": "MIT, Cambridge, USA"
  }
}
```

Skipped rows:

```json
{"record_id":"paper-003","affiliation":"","status":"skipped","error":"empty affiliation"}
```

Failed rows:

```json
{"record_id":"paper-004","affiliation":"...","status":"error","error":"exception message"}
```

## Merge Rules

Use `record_id` as the primary join key. If source data lacks a stable id, add one before running the script rather than relying on file order.

## Split CSV pre-normalization fields

The split CSV matcher preserves `affiliations` unchanged and may add:

- `country`, `country_raw`, `country_source`, `country_confidence`
- `city`
- `affiliation_institution_candidate`
- `affiliation_subunits`, `affiliation_unmatched_components`
- `institution_reference_match_method`, `institution_reference_confidence`
- `institution_reference_status`, `institution_reference_review`

Only explicit terminal country names or reviewed institution records may fill country before AffilGood.
An explicit country is evidence for disambiguation, not proof that the institution is resolved.

## Primary Institution Reference

The bundled `institution_raw.csv` is the first exact-reference layer for split CSV automation. Parse
explicit location components and generate institution candidates before matching. The current project
table is preferred when available; otherwise the bundled snapshot is used. Override it with
`--institution-table` or `AFFILGOOD_INSTITUTION_TABLE`.

Reference matching checks the observed and canonical institution names. A unique exact match can supply
the reviewed standard name, ROR ID, country, and city. Country evidence selects a candidate only when it
leaves one identity; otherwise the full source `affiliation_rank` is retained as one deterministic
atomic identity rather than selecting one component.

Use these status values in split CSV outputs:

- `pending_affilgood`: prepare-only pass; institution-table lookup is intentionally deferred.
- `affilgood_resolved`: AffilGood supplied a complete institution, country, and ROR identity.
- `matched_after_affilgood`: institution_raw supplied a unique missing value after AffilGood.
- `resolved_reviewed_rule`: a reviewed exact or paper-author scoped rule completed the row.
- `resolved_unique_identity`: one stable identity was retained while preserving explicit country context.
- `resolved_atomic_composite`: multiple candidates were retained as one hashed atomic identity.
- `not_applicable_noninstitutional`: the source explicitly denotes no institutional affiliation.
- `unknown_organization`: the source organization is retained without inventing a reviewed identity.

`ambiguous_after_affilgood`, `conflict_after_affilgood`, and a non-empty
`institution_reference_review` are failure states after the automated post-match stage.

Send all prepared rows to AffilGood. During the post-AffilGood merge, fill only blank values from
`institution_raw.csv`; never overwrite a non-empty AffilGood field.

One `affiliation_rank` is atomic. Preserve multiple AffilGood organizations in that row as one
semicolon-delimited composite label and one downstream `institution_key`. Institution-reference
matching may select a reviewed full-composite record, but must not select one component as the identity
of the entire row.

The table fields have these meanings:

- `affilgood_institutions`: observed institution wording from the project dataset.
- `affilgood_standard_institutions`: reviewed/canonical wording when available.
- `affilgood_ror_ids`: reviewed ROR identifier, when available.
- `affilgood_location_country`, `affilgood_location_city`: reviewed location evidence.
- `conference_id`, `conference_final_id`: project-local reference IDs, not global identifiers.
- `affilgood_standardization_source`, `notes`: provenance and review notes.

For downstream analytics, the most commonly used AffilGood fields are:

- `affilgood.outputs[].institutions[].name`
- `affilgood.outputs[].institutions[].id`
- `affilgood.outputs[].institutions[].confidence`
- `affilgood.outputs[].location.country`
- `affilgood.outputs[].location.city`
- `affilgood.outputs[].confidence`

## Three-IACR primary institution output

The CRYPTO/EUROCRYPT/ASIACRYPT primary-institution post-processor appends:

- `primary_institution`, `primary_country`, `primary_ror_id`, `primary_city`
- `primary_institution_source`, `primary_country_source`
- `primary_match_status`: `complete` or `needs_supplement`
- `primary_review_reason`: a semicolon-separated set of `missing_primary_institution`,
  `missing_country`, and `missing_ror`

Resolve country before country-aware AffilGood/ROR selection. Use `institution_raw.csv` only after the
AffilGood/ROR result is incomplete, and use reviewed supplements after the institution table. Do not
publish an incomplete row as resolved; retain it in the supplement queue.
