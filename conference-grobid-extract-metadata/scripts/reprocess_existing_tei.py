"""Rebuild metadata artifacts from existing TEI files and source PDFs.

This intentionally skips GROBID inference.  It is useful when repair/layout rules
change but the staged PDFs and TEI headers are already complete.
"""

import argparse
import csv
import json
from pathlib import Path

from author_metadata.exporter import (
    export_abstract_csv,
    export_csv,
    export_json,
    export_review_queue,
    write_index,
)
from author_metadata.artifacts import (
    abstract_csv_row,
    author_csv_rows,
    export_paper_artifacts,
    new_metrics,
    review_csv_rows,
    update_metrics,
)
from author_metadata.pdf_context import load_pdf_context
from author_metadata.pipeline import load_conference_strategy, process_paper


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--conference", required=True)
    parser.add_argument("--years", nargs="+", required=True)
    return parser.parse_args()


def read_index(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def process_year(source_root, output_root, conference, year, strategy):
    source_dir = source_root / f"author_metadata_dataset_{year}"
    output_dir = output_root / f"author_metadata_dataset_{year}"
    metadata_dir = output_dir / "metadata_json"
    evidence_dir = output_dir / "evidence_json"
    candidate_dir = output_dir / "candidate_json"
    for path in (metadata_dir, evidence_dir, candidate_dir):
        path.mkdir(parents=True, exist_ok=True)

    index_rows = read_index(source_dir / "paper_index.csv")
    staged_rows = [row for row in index_rows if row.get("status") == "staged"]
    csv_rows = []
    abstract_rows = []
    review_rows = []
    output_index = []
    metrics = new_metrics(len(staged_rows), include_extended=True)

    for row in staged_rows:
        paper_id = row["paper_id"]
        pdf_path = Path(row["source_path"])
        tei_path = source_dir / "tei_header_xml" / f"{paper_id}.tei.xml"
        try:
            metadata = process_paper(
                str(pdf_path),
                load_pdf_context(str(pdf_path)),
                str(tei_path),
                conference_name=conference,
                year_hint=str(year),
                strategy=strategy,
            )
            metadata["year"] = str(year)
            export_paper_artifacts(
                paper_id,
                metadata,
                metadata_dir,
                evidence_dir,
                candidate_dir,
            )
            extraction = metadata.get("_extraction", {})
            reasons = extraction.get("review_reasons", [])
            update_metrics(metrics, metadata)
            abstract_rows.append(abstract_csv_row(metadata, conference, fallback_title=paper_id, fallback_year=str(year)))
            review_rows.extend(review_csv_rows(paper_id, row.get("source_file", ""), reasons))
            for author in metadata.get("authors", []):
                csv_rows.extend(author_csv_rows(paper_id, metadata, author, conference))
        except Exception as exc:
            metrics["parse_errors"] += 1
            abstract_rows.append({
                "conference": conference,
                "year": str(year),
                "title": paper_id,
                "abstract": "",
            })
            review_rows.append({
                "paper_id": paper_id,
                "source_file": row.get("source_file", ""),
                "code": "parse_error",
                "field": "paper",
                "author": "",
                "stage": "reprocess_existing_tei",
                "details": json.dumps({"error": str(exc)}, ensure_ascii=False),
            })

        output_index.append({
            **row,
            "stage_pdf": str(pdf_path),
            "tei_xml": str(tei_path),
            "metadata_json": str(metadata_dir / f"{paper_id}.json"),
            "evidence_json": str(evidence_dir / f"{paper_id}.json"),
            "candidate_json": str(candidate_dir / f"{paper_id}.json"),
        })

    export_csv(output_dir / "paper_metadata.csv", csv_rows)
    export_abstract_csv(output_dir / "conference_year_paper_abstract.csv", abstract_rows)
    export_review_queue(output_dir / "review_queue.csv", review_rows)
    export_json(output_dir / "extraction_metrics.json", metrics)
    write_index(output_dir / "paper_index.csv", output_dir / "skipped_files.csv", output_index)
    print(
        f"{year}: papers={metrics['papers_processed']}/{metrics['papers_total']} "
        f"authors={metrics['authors_exported']} parse_errors={metrics['parse_errors']} "
        f"review={len(review_rows)}"
    )


def main():
    args = parse_args()
    source_root = Path(args.source_root).resolve()
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    strategy = load_conference_strategy(args.conference)
    for year in args.years:
        process_year(source_root, output_root, args.conference, year, strategy)


if __name__ == "__main__":
    main()
