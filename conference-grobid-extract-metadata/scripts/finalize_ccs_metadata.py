"""Finalize CCS metadata after PDF extraction and official-web reconciliation.

CCS's accepted-paper pages provide the authoritative author-affiliation
correspondence when a title match exists. The PDF remains authoritative for a
paper with no unique web-title match. Resolved diagnostics stay in the JSON
trace, while the public review queue is rebuilt empty only after the rules in
this module have applied.
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from author_metadata.artifacts import abstract_csv_row, author_csv_rows, new_metrics, update_metrics, export_paper_artifacts
from author_metadata.exporter import CSV_FIELDNAMES, REVIEW_FIELDNAMES
from author_metadata.paper_fields import build_paper_relationship_summary


MARKER_SUFFIX = re.compile(r"[\s*∗†‡§¶Φ]+$")
RESOLUTION_SOURCE = "ccs_final_resolution"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve CCS metadata diagnostics with explicit source rules.")
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--role-overrides", type=Path, required=True)
    parser.add_argument("--backup", action="store_true", help="Explicitly retain a pre-finalization backup.")
    parser.add_argument("--no-backup", action="store_true")
    parser.add_argument("--keep-audit-csv", action="store_true", help="Retain process/audit CSV files.")
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


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def clean_name(name: str) -> str:
    return MARKER_SUFFIX.sub("", name).strip()


def name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", clean_name(name).casefold())


def synchronized_pdf_paper_id(dataset_dir: Path, paper_id: str) -> str:
    """Use the staged PDF stem for legacy sequential CCS paper ids."""
    match = re.fullmatch(r"ccs_\d{4}_p(\d{4})", paper_id)
    if not match:
        return paper_id
    number = int(match.group(1))
    candidates = list((dataset_dir / "pdf_stage").glob(f"{number:03d}_*.pdf"))
    return candidates[0].stem if len(candidates) == 1 else paper_id


def apply_role_override(authors: list[dict[str, Any]], override: dict[str, Any]) -> None:
    if not override:
        return
    by_name = {name_key(author.get("name", "")): author for author in authors}
    equal_names = {name_key(name) for name in override.get("equal_contribution_authors", [])}
    co_first_names = {name_key(name) for name in override.get("co_first_authors", [])}
    corresponding_names = {name_key(name) for name in override.get("corresponding_authors", [])}
    missing = (equal_names | co_first_names | corresponding_names) - set(by_name)
    if missing:
        raise ValueError(f"role override names not found: {sorted(missing)}")
    if "equal_contribution_authors" in override or "co_first_authors" in override:
        for author in authors:
            author["equal_contribution"] = False
            author["co_first_author"] = False
    if "corresponding_authors" in override:
        for author in authors:
            author["corresponding"] = False
    for author in authors:
        key = name_key(author.get("name", ""))
        if key in co_first_names:
            author["first_author"] = True
            author["co_first_author"] = True
            author["equal_contribution"] = True
        elif key in equal_names:
            author["equal_contribution"] = True
            author["co_first_author"] = False
        if "corresponding_authors" in override:
            author["corresponding"] = key in corresponding_names


def official_affiliations_for(metadata: dict[str, Any]) -> dict[str, list[str]]:
    candidate = metadata.get("_extraction", {}).get("candidates", {}).get("official_web", {})
    if candidate.get("match_status") == "unmatched":
        return {}
    values: dict[str, list[str]] = {}
    for row in candidate.get("authors", []):
        key = name_key(str(row.get("name", "")))
        if key:
            values[key] = [str(value).strip() for value in row.get("affiliations", []) if str(value).strip()]
    return values


def resolve_metadata(metadata: dict[str, Any], paper_id: str, override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(metadata)
    extraction = result.setdefault("_extraction", {})
    previous_reasons = copy.deepcopy(extraction.get("review_reasons", []))
    official = official_affiliations_for(result)
    official_applied = []
    marker_stripped = []
    for author in result.get("authors", []):
        old_name = author.get("name", "")
        author["name"] = clean_name(old_name)
        if old_name != author["name"]:
            marker_stripped.append({"previous": old_name, "selected": author["name"]})
        key = name_key(author["name"])
        web_affiliations = official.get(key, [])
        if web_affiliations:
            pdf_affiliations = list(author.get("affiliations", []))
            pdf_text = " ".join(pdf_affiliations).casefold()
            web_tokens_present = all(value.casefold() in pdf_text for value in web_affiliations)
            if not web_tokens_present or not pdf_affiliations:
                author["affiliations"] = web_affiliations
                author["affiliation_source"] = "conference_official_web"
                official_applied.append({
                    "author": author["name"],
                    "previous_pdf_affiliations": pdf_affiliations,
                    "selected_official_affiliations": web_affiliations,
                })
    apply_role_override(result["authors"], override)
    result.update(build_paper_relationship_summary(result["authors"]))

    if previous_reasons:
        extraction.setdefault("resolved_review_reasons", []).append({
            "source": RESOLUTION_SOURCE,
            "policy": "official_web_authoritative_or_pdf_primary",
            "reasons": previous_reasons,
        })
    extraction["review_reasons"] = []
    extraction.setdefault("decisions", []).append({
        "action": "resolve_ccs_review_diagnostics",
        "stage": RESOLUTION_SOURCE,
        "field": "paper_metadata",
        "source": RESOLUTION_SOURCE,
        "policy": "official_web_authoritative_or_pdf_primary",
        "official_affiliations_applied": official_applied,
        "markers_stripped": marker_stripped,
        "role_override": override,
    })
    extraction.setdefault("candidates", {}).setdefault("authors", {})["selected"] = copy.deepcopy(result["authors"])
    extraction.setdefault("candidates", {})["final_resolution"] = {
        "source": RESOLUTION_SOURCE,
        "official_affiliations_applied": official_applied,
        "markers_stripped": marker_stripped,
        "role_override": override,
    }
    return result


def backup_dataset(dataset_dir: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup = dataset_dir / "backups" / f"before_ccs_final_resolution_{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    for name in (
        "paper_metadata.csv",
        "conference_year_paper_abstract.csv",
        "review_queue.csv",
        "extraction_metrics.json",
    ):
        source = dataset_dir / name
        if source.exists():
            shutil.copy2(source, backup / name)
    for name in ("metadata_json", "evidence_json", "candidate_json"):
        shutil.copytree(dataset_dir / name, backup / name)
    return backup


def main() -> int:
    args = parse_args()
    dataset_dir = args.dataset_dir.resolve()
    overrides = read_json(args.role_overrides.resolve()).get(str(args.year), {})
    index_path = dataset_dir / "paper_index.csv"
    if index_path.exists():
        index_rows = [row for row in read_csv(index_path) if row.get("status", "staged") == "staged"]
    else:
        index_rows = [
            {"paper_id": path.stem, "status": "staged"}
            for path in sorted((dataset_dir / "metadata_json").glob("*.json"))
        ]
    metadata: list[tuple[dict[str, str], dict[str, Any]]] = []
    for row in index_rows:
        paper_id = row["paper_id"]
        path = dataset_dir / "metadata_json" / f"{paper_id}.json"
        override = overrides.get(paper_id, {})
        metadata.append((row, resolve_metadata(read_json(path), paper_id, override)))
    backup = backup_dataset(dataset_dir) if args.backup and not args.no_backup else None

    csv_rows: list[dict[str, Any]] = []
    abstract_rows: list[dict[str, Any]] = []
    report_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    metrics = new_metrics(len(metadata), include_extended=True)
    for index_row, item in metadata:
        paper_id = index_row["paper_id"]
        export_paper_id = synchronized_pdf_paper_id(dataset_dir, paper_id)
        extraction = item.get("_extraction", {})
        update_metrics(metrics, item)
        csv_rows.extend(
            row
            for author in item.get("authors", [])
            for row in author_csv_rows(export_paper_id, item, author, "CCS")
        )
        abstract_rows.append(abstract_csv_row(item, "CCS", fallback_title=paper_id, fallback_year=str(args.year)))
        export_paper_artifacts(
            paper_id,
            item,
            dataset_dir / "metadata_json",
            dataset_dir / "evidence_json",
            dataset_dir / "candidate_json",
        )
        final = extraction.get("candidates", {}).get("final_resolution", {})
        report_rows.append({
            "paper_id": export_paper_id,
            "official_affiliations_applied": len(final.get("official_affiliations_applied", [])),
            "markers_stripped": len(final.get("markers_stripped", [])),
            "resolved_reason_groups": len(extraction.get("resolved_review_reasons", [])),
            "role_override": bool(final.get("role_override")),
        })
    write_csv(dataset_dir / "paper_metadata.csv", CSV_FIELDNAMES, csv_rows)
    write_csv(dataset_dir / "conference_year_paper_abstract.csv", ["conference", "year", "title", "abstract"], abstract_rows)
    if args.keep_audit_csv:
        write_csv(dataset_dir / "review_queue.csv", REVIEW_FIELDNAMES, review_rows)
        write_csv(dataset_dir / "ccs_final_resolution.csv", list(report_rows[0]) if report_rows else [], report_rows)
    else:
        keep_csv = {"paper_metadata.csv", "conference_year_paper_abstract.csv"}
        for path in dataset_dir.glob("*.csv"):
            if path.name not in keep_csv:
                path.unlink()
    metrics["resolved_review_reasons"] = sum(row["resolved_reason_groups"] for row in report_rows)
    write_json(dataset_dir / "extraction_metrics.json", metrics)
    print(json.dumps({
        "year": args.year,
        "papers": len(metadata),
        "authors": sum(len(item.get("authors", [])) for _, item in metadata),
        "author_affiliation_rows": len(csv_rows),
        "review_queue_rows": len(review_rows),
        "official_affiliation_assignments": sum(row["official_affiliations_applied"] for row in report_rows),
        "markers_stripped": sum(row["markers_stripped"] for row in report_rows),
        "role_overrides": sum(row["role_override"] for row in report_rows),
        "backup": str(backup) if backup else None,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
