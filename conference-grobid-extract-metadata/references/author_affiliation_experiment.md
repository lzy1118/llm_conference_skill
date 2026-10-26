# Author-affiliation Skill experiment

Build a 500-paper manual validation queue from any GROBID dataset:

```bash
python3 scripts/evaluate_author_affiliation_skill.py \
  --metadata-dir /absolute/path/to/metadata_json [/another/metadata_json ...] \
  --build-template /absolute/path/to/annotations.jsonl --limit 500
```

For each JSONL row, replace pending `gold_pairs: null` with a reviewed list of
`{"author": "...", "affiliation": "..."}` objects. Use `[]` only when the
paper has been reviewed and has no valid author-affiliation edges. Set
`layout_tags` to the applicable values from `superscript`,
`multiple_affiliation`, `shared_affiliation`, `footnote`, and `multi-column`,
or to `[]` after review when none apply. Leave prediction fields unchanged.
The GROBID baseline is read from `_extraction.evidence` or the sibling
`evidence_json` artifact. `grobid_pairs: null` means raw TEI author evidence is
unavailable; that baseline is omitted from metrics rather than copied from
repaired output.
To measure ablations, replace each pending null with reviewed prediction lists
in `ablation_pairs.remove_layout_rules`,
`ablation_pairs.remove_evidence_validation`, and
`ablation_pairs.remove_domain_rules`. Rows whose `gold_pairs` remain null are
skipped, and the CLI reports how many rows were evaluated.

Run the completed annotation set:

```bash
python3 scripts/evaluate_author_affiliation_skill.py \
  --input /absolute/path/to/annotations.jsonl \
  --output-dir /absolute/path/to/experiment-results
```

The output contains `results.csv` (per-paper records), `summary.csv` (P/R/F1
and ablation `delta_f1`), `results.tex`, and `f1_comparison.png`. Metrics are
micro-averaged over exact `(author, affiliation)` edges. This evaluates the
Skill framework's ability to recover complex metadata relations; it is not an
institution entity-linking benchmark.
