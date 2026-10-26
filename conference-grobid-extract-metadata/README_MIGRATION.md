# Grobid Extract Metadata Bundle

This directory now contains everything needed to move the metadata extraction
workflow into a larger project:

- `scripts/`
  - metadata extraction script
- `references/`
  - TEI structure notes
- `grobid-runtime/`
  - filtered GROBID runtime needed to run local PDF-to-TEI extraction

## Suggested Migration Unit

If you want to migrate this workflow elsewhere, copy the whole
`conference-grobid-extract-metadata/` directory.

By default, the script resolves project data paths relative to:

- `conference-grobid-extract-metadata/scripts/`
- sibling project directory `../data/`

So after migration, keep this layout if you want it to work without edits:

```text
your-project/
├── data/
│   ├── raw_data/
│   ├── author_metadata_dataset/
│   │   ├── pdf_stage/
│   │   ├── tei_header_xml/
│   │   ├── metadata_json/
│   │   ├── evidence_json/
│   │   ├── candidate_json/
│   │   ├── paper_index.csv
│   │   ├── review_queue.csv
│   │   ├── extraction_metrics.json
│   │   └── skipped_files.csv
│   └── paper_metadata.csv
└── conference-grobid-extract-metadata/
    ├── scripts/
    ├── references/
    └── grobid-runtime/
```

If your target project uses a different data location, set:

```bash
GROBID_METADATA_DATA_DIR=/path/to/data
```

## Notes

- `grobid-runtime/` is a filtered runtime, not the full upstream repository.
- It keeps the pieces needed for local GROBID service execution:
  - `grobid-home/`
  - `grobid-core/`
  - `grobid-service/`
  - Gradle wrapper/build files
- The top-level `/Users/liziyu/code/grobid/grobid-runtime` copy was left in
  place for safety. It can be removed later if you confirm nothing else points
  to it.
