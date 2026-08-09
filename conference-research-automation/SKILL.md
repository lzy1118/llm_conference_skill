---
name: conference-research-automation
description: Run the PDF-first metadata pipeline for the seven current conference cases through one compatible entry point.
---

# Conference Research Automation

Use `scripts/run_pipeline.py` as the common entry for ASIACRYPT, CRYPTO, EUROCRYPT, CCS,
IEEE S&P, NDSS, and USENIX Security. PDF files are the main input. Conference websites remain
supplementary sources inside the existing conference-specific stages.

The common entry is additive. The existing four-security-conference command remains available and
its arguments and execution order are unchanged. Both entries use
`generated-data/<stage>/<conference>/<year>/` for generated artifacts. The common entry delegates those
four conferences to that script and selects the shared LNCS extraction strategy plus the existing
crypto primary-institution rules for the three cryptography conferences.

```bash
python3 conference-research-automation/scripts/run_pipeline.py \
  --conference crypto \
  --year 2025
```

Use `--dry-run` to inspect the selected chain. Use `--reuse-extraction` to continue from an existing
`full_output/<conference>/<year>/author_metadata_dataset_<year>` directory.
