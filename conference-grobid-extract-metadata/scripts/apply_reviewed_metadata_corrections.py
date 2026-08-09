"""Apply narrowly scoped, human-reviewed PDF metadata corrections.

The correction manifest must include the expected current title and author
sequence. This prevents a reviewed correction from being applied to a changed
or unrelated extraction result.
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from author_metadata.artifacts import author_csv_rows, export_paper_artifacts
from author_metadata.exporter import CSV_FIELDNAMES
from author_metadata.paper_fields import build_paper_relationship_summary


REVIEW_SOURCE = "human_reviewed_pdf"
REVIEW_STAGE = "reviewed_metadata_correction"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply evidence-backed metadata corrections after manual PDF review."
    )
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--corrections", type=Path, required=True)
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def corrected_authors(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    required = {"name", "email", "affiliations", "first_author", "co_first_author", "corresponding", "equal_contribution"}
    result = []
    for index, value in enumerate(values):
        missing = required - set(value)
        if missing:
            raise ValueError(f"corrected author {index} is missing fields: {sorted(missing)}")
        author = copy.deepcopy(value)
        author["order"] = index
        author["affiliation_source"] = REVIEW_SOURCE
        result.append(author)
    if not result:
        raise ValueError("reviewed correction cannot contain an empty author list")
    return result


def apply_correction(metadata: dict[str, Any], correction: dict[str, Any]) -> dict[str, Any]:
    expected_title = correction["expected_title"]
    expected_authors = correction["expected_authors"]
    current_authors = [author.get("name", "") for author in metadata.get("authors", [])]
    if metadata.get("title", "") != expected_title:
        raise ValueError(
            f"title changed since review: expected {expected_title!r}, got {metadata.get('title', '')!r}"
        )
    if current_authors != expected_authors:
        raise ValueError(
            f"author sequence changed since review: expected {expected_authors!r}, got {current_authors!r}"
        )

    result = copy.deepcopy(metadata)
    previous_authors = copy.deepcopy(result.get("authors", []))
    authors = corrected_authors(correction["authors"])
    result["authors"] = authors
    result.update(build_paper_relationship_summary(authors))

    extraction = result.setdefault("_extraction", {})
    resolved_codes = set(correction.get("resolved_review_codes", []))
    extraction["review_reasons"] = [
        reason
        for reason in extraction.get("review_reasons", [])
        if reason.get("code") not in resolved_codes
    ]
    evidence_id = f"reviewed_pdf:{correction['paper_id']}:author_affiliations"
    extraction.setdefault("evidence", []).append({
        "evidence_id": evidence_id,
        "source": REVIEW_SOURCE,
        "field": "author_affiliation_relation",
        "source_file": correction["source_file"],
        "page": correction.get("page", 1),
        "review_note": correction["review_note"],
        "authors": [author["name"] for author in authors],
        "relations": result["author_affiliation_relations"],
    })
    extraction.setdefault("decisions", []).append({
        "action": "apply_reviewed_pdf_author_affiliations",
        "stage": REVIEW_STAGE,
        "field": "authors",
        "source": REVIEW_SOURCE,
        "evidence_ids": [evidence_id],
        "previous": [author.get("name", "") for author in previous_authors],
        "selected": [author["name"] for author in authors],
    })
    extraction.setdefault("candidates", {}).setdefault("authors", {})["selected"] = copy.deepcopy(authors)
    return result


def make_backup(dataset_dir: Path, paper_ids: list[str]) -> Path:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup_dir = dataset_dir / "backups" / f"before_reviewed_corrections_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(dataset_dir / "paper_metadata.csv", backup_dir / "paper_metadata.csv")
    metadata_backup = backup_dir / "metadata_json"
    metadata_backup.mkdir()
    for paper_id in paper_ids:
        shutil.copy2(dataset_dir / "metadata_json" / f"{paper_id}.json", metadata_backup / f"{paper_id}.json")
    return backup_dir


def main() -> int:
    args = parse_args()
    dataset_dir = args.dataset_dir.resolve()
    manifest = read_json(args.corrections.resolve())
    corrections = manifest.get("corrections", [])
    if not corrections:
        raise SystemExit("correction manifest is empty")

    csv_path = dataset_dir / "paper_metadata.csv"
    csv_rows = read_csv(csv_path)
    correction_by_id = {item["paper_id"]: item for item in corrections}
    if len(correction_by_id) != len(corrections):
        raise SystemExit("correction manifest contains duplicate paper IDs")

    updated_metadata: dict[str, dict[str, Any]] = {}
    for paper_id, correction in correction_by_id.items():
        metadata_path = dataset_dir / "metadata_json" / f"{paper_id}.json"
        if not metadata_path.exists():
            raise SystemExit(f"metadata JSON is missing: {metadata_path}")
        try:
            updated_metadata[paper_id] = apply_correction(read_json(metadata_path), correction)
        except (KeyError, TypeError, ValueError) as exc:
            raise SystemExit(f"correction rejected for {paper_id}: {exc}") from exc

    backup_dir = make_backup(dataset_dir, list(correction_by_id))
    output_rows: list[dict[str, Any]] = []
    emitted: set[str] = set()
    for row in csv_rows:
        paper_id = row.get("paper_id", "")
        if paper_id not in updated_metadata:
            output_rows.append(row)
            continue
        if paper_id in emitted:
            continue
        metadata = updated_metadata[paper_id]
        output_rows.extend(
            row
            for author in metadata["authors"]
            for row in author_csv_rows(paper_id, metadata, author, manifest["conference"])
        )
        emitted.add(paper_id)
    missing_csv = set(updated_metadata) - emitted
    if missing_csv:
        raise SystemExit(f"corrected papers are missing from paper_metadata.csv: {sorted(missing_csv)}")

    for paper_id, metadata in updated_metadata.items():
        export_paper_artifacts(
            paper_id,
            metadata,
            dataset_dir / "metadata_json",
            dataset_dir / "evidence_json",
            dataset_dir / "candidate_json",
        )
    write_csv(csv_path, output_rows)
    print(json.dumps({
        "corrected_papers": len(updated_metadata),
        "paper_ids": list(updated_metadata),
        "backup": str(backup_dir),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
