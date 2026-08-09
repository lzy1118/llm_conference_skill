"""Replay PDF-backed co-first and corresponding-author detection.

The script preserves paper, author, affiliation, email, and abstract data. It only
recomputes author-role fields and their audit artifacts. Dry-run is the default.
"""

from __future__ import annotations

import argparse
import copy
import csv
import html
import json
import re
import logging
import shutil
import warnings
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

from author_metadata.artifacts import (
    author_csv_rows,
    new_metrics,
    review_csv_rows,
    update_metrics,
)
from author_metadata.exporter import CSV_FIELDNAMES, REVIEW_FIELDNAMES
from author_metadata.paper_fields import build_paper_relationship_summary
from author_metadata.pdf_context import load_pdf_context
from author_metadata.role_linking import apply_author_roles, extract_role_hints


ROLE_FIELDS = {
    "first_author",
    "co_first_author",
    "corresponding",
    "equal_contribution",
}
ROLE_EVIDENCE_SOURCE = "pdf_role_linking"
ROLE_DECISION_ACTION = "apply_pdf_author_roles"
REPORT_FIELDS = [
    "paper_id",
    "title",
    "equal_contribution_authors_before",
    "equal_contribution_authors_after",
    "corresponding_authors_before",
    "corresponding_authors_after",
    "role_evidence",
    "review_reasons",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recompute PDF-backed co-first and corresponding-author roles without rerunning GROBID."
    )
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--conference", default="ccs")
    parser.add_argument(
        "--pdf-dir",
        type=Path,
        help="Optional current PDF directory used when an older paper_index points to stale paths.",
    )
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def role_names(authors: list[dict[str, Any]], field: str) -> list[str]:
    return [author.get("name", "") for author in authors if author.get(field)]


def csv_author_names(rows: list[dict[str, str]]) -> list[str]:
    """Collapse one-row-per-affiliation CSV data back to author order."""
    names: list[str] = []
    previous_key: tuple[str, str] | None = None
    for row in rows:
        affiliation_rank = (row.get("affiliation_rank") or "").strip()
        key = ((row.get("author_rank") or "").strip(), row.get("author", ""))
        if affiliation_rank and affiliation_rank != "0":
            previous_key = key
            continue
        if not affiliation_rank and key == previous_key:
            continue
        names.append(row.get("author", ""))
        previous_key = key
    return names


def non_role_projection(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": metadata.get("title", ""),
        "year": metadata.get("year", ""),
        "abstract": metadata.get("abstract", ""),
        "authors": [
            {key: copy.deepcopy(value) for key, value in author.items() if key not in ROLE_FIELDS}
            for author in metadata.get("authors", [])
        ],
    }


def load_tei_root(path: str):
    if not path or not Path(path).exists():
        return None
    try:
        return ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None


def title_key(value: str) -> str:
    text = html.unescape(str(value or "")).casefold()
    return re.sub(r"[^a-z0-9]+", "", text)


def title_tokens(value: str) -> set[str]:
    text = html.unescape(str(value or "")).casefold()
    return {token for token in re.findall(r"[a-z]{3,}", text) if token not in {"the", "and", "for", "with"}}


def build_pdf_lookups(pdf_dir: Path | None) -> tuple[dict[str, list[Path]], dict[str, list[Path]]]:
    title_lookup: dict[str, list[Path]] = {}
    number_lookup: dict[str, list[Path]] = {}
    if not pdf_dir or not pdf_dir.is_dir():
        return title_lookup, number_lookup
    for path in sorted(pdf_dir.rglob("*.pdf")):
        prefix = re.match(r"^(\d+)[_-]", path.stem)
        stem = re.sub(r"^\d+[_-]", "", path.stem)
        key = title_key(stem)
        if key:
            title_lookup.setdefault(key, []).append(path)
        if prefix:
            number_lookup.setdefault(str(int(prefix.group(1))), []).append(path)
    return title_lookup, number_lookup


def enrich_metadata_roles(
    metadata: dict[str, Any],
    pdf_context,
    tei_root=None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = copy.deepcopy(metadata)
    before_projection = non_role_projection(result)
    old_authors = copy.deepcopy(result.get("authors", []))
    names = [author.get("name", "") for author in old_authors if author.get("name")]
    email_map = {
        author.get("name", ""): author.get("email", "")
        for author in old_authors
        if author.get("name")
    }
    hints = extract_role_hints(tei_root, pdf_context, names, email_map)
    result["authors"] = apply_author_roles(copy.deepcopy(old_authors), hints)
    result.update(build_paper_relationship_summary(result["authors"]))

    if non_role_projection(result) != before_projection:
        raise ValueError("role replay changed non-role metadata")

    extraction = result.setdefault("_extraction", {})
    extraction["review_reasons"] = [
        reason
        for reason in extraction.get("review_reasons", [])
        if reason.get("stage") != "role_linking"
    ] + list(hints.get("review_reasons", []))
    extraction["evidence"] = [
        evidence
        for evidence in extraction.get("evidence", [])
        if evidence.get("source") != ROLE_EVIDENCE_SOURCE
    ]
    for index, evidence in enumerate(hints.get("role_evidence", [])):
        extraction["evidence"].append({
            "evidence_id": f"pdf:author_role:{index}",
            "source": ROLE_EVIDENCE_SOURCE,
            "field": "author_role",
            **evidence,
        })

    selected = {
        "equal_contribution_names": sorted(hints.get("equal_contribution_names", set())),
        "corresponding_names": sorted(hints.get("corresponding_names", set())),
        "role_evidence": hints.get("role_evidence", []),
        "confidence": "high" if not hints.get("review_reasons") else "review_required",
    }
    extraction.setdefault("candidates", {})["pdf_author_roles"] = selected
    extraction["decisions"] = [
        decision
        for decision in extraction.get("decisions", [])
        if decision.get("action") != ROLE_DECISION_ACTION
    ]
    extraction["decisions"].append({
        "action": ROLE_DECISION_ACTION,
        "stage": "role_linking",
        "field": "author_roles",
        "source": ROLE_EVIDENCE_SOURCE,
        "previous_equal_contribution_names": role_names(old_authors, "equal_contribution"),
        "selected_equal_contribution_names": role_names(result["authors"], "equal_contribution"),
        "previous_corresponding_names": role_names(old_authors, "corresponding"),
        "selected_corresponding_names": role_names(result["authors"], "corresponding"),
    })
    return result, selected


def make_backup(dataset_dir: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup_dir = dataset_dir / "backups" / f"before_pdf_author_roles_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    for name in ("paper_metadata.csv", "review_queue.csv", "extraction_metrics.json"):
        source = dataset_dir / name
        if source.exists():
            shutil.copy2(source, backup_dir / name)
    for name in ("metadata_json", "evidence_json", "candidate_json"):
        source = dataset_dir / name
        if source.is_dir():
            shutil.copytree(source, backup_dir / name)
    return backup_dir


def main() -> int:
    args = parse_args()
    logging.disable(logging.CRITICAL)
    warnings.filterwarnings("ignore")
    dataset_dir = args.dataset_dir.resolve()
    required = [dataset_dir / "paper_index.csv", dataset_dir / "paper_metadata.csv", dataset_dir / "metadata_json"]
    if any(not path.exists() for path in required):
        raise SystemExit("dataset is missing paper_index.csv, paper_metadata.csv, or metadata_json")

    index_rows = [row for row in read_csv(dataset_dir / "paper_index.csv") if row.get("status") == "staged"]
    current_csv_rows = read_csv(dataset_dir / "paper_metadata.csv")
    metrics_path = dataset_dir / "extraction_metrics.json"
    previous_metrics = read_json(metrics_path) if metrics_path.exists() else {}
    current_csv_by_paper: dict[str, list[dict[str, str]]] = {}
    for csv_row in current_csv_rows:
        current_csv_by_paper.setdefault(csv_row.get("paper_id", ""), []).append(csv_row)
    if not index_rows:
        raise SystemExit("paper_index.csv has no staged papers")
    if len({row["paper_id"] for row in index_rows}) != len(index_rows):
        raise SystemExit("paper_index.csv contains duplicate paper_id values")
    pdf_title_lookup, pdf_number_lookup = build_pdf_lookups(
        args.pdf_dir.expanduser().resolve() if args.pdf_dir else None
    )

    enriched: list[tuple[dict[str, str], dict[str, Any]]] = []
    report_rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for row in index_rows:
        paper_id = row["paper_id"]
        metadata_path = dataset_dir / "metadata_json" / f"{paper_id}.json"
        pdf_path = Path(row.get("stage_pdf", ""))
        # Older batches kept absolute paths into a temporary collection run.
        # Prefer the dataset-local staged copy when that path is no longer valid.
        if not pdf_path.exists():
            local_pdf = dataset_dir / "pdf_stage" / row.get("source_file", "")
            if local_pdf.exists():
                pdf_path = local_pdf
        if not pdf_path.exists() and metadata_path.exists() and pdf_title_lookup:
            metadata_for_lookup = read_json(metadata_path)
            matches = pdf_title_lookup.get(title_key(metadata_for_lookup.get("title", "")), [])
            if len(matches) == 1:
                pdf_path = matches[0]
            else:
                number_match = re.search(r"p(\d+)$", paper_id)
                numbered = pdf_number_lookup.get(str(int(number_match.group(1))), []) if number_match else []
                if len(numbered) == 1:
                    filename_title = re.sub(r"^\d+[_-]", "", numbered[0].stem)
                    if len(title_tokens(metadata_for_lookup.get("title", "")) & title_tokens(filename_title)) >= 2:
                        pdf_path = numbered[0]
        if not metadata_path.exists() or not pdf_path.exists():
            errors.append(f"{paper_id}: missing metadata JSON or staged PDF")
            continue
        try:
            metadata = read_json(metadata_path)
            csv_names = csv_author_names(current_csv_by_paper.get(paper_id, []))
            metadata_names = [author.get("name", "") for author in metadata.get("authors", [])]
            if csv_names != metadata_names:
                raise ValueError("paper_metadata.csv author sequence differs from metadata_json")
            updated, selected = enrich_metadata_roles(
                metadata,
                load_pdf_context(str(pdf_path)),
                load_tei_root(row.get("tei_xml", "")),
            )
        except Exception as exc:
            errors.append(f"{paper_id}: {type(exc).__name__}: {exc}")
            continue
        enriched.append((row, updated))
        report_rows.append({
            "paper_id": paper_id,
            "title": updated.get("title", ""),
            "equal_contribution_authors_before": "; ".join(role_names(metadata.get("authors", []), "equal_contribution")),
            "equal_contribution_authors_after": "; ".join(role_names(updated.get("authors", []), "equal_contribution")),
            "corresponding_authors_before": "; ".join(role_names(metadata.get("authors", []), "corresponding")),
            "corresponding_authors_after": "; ".join(role_names(updated.get("authors", []), "corresponding")),
            "role_evidence": json.dumps(selected["role_evidence"], ensure_ascii=False),
            "review_reasons": json.dumps(updated.get("_extraction", {}).get("review_reasons", []), ensure_ascii=False),
        })

    if errors or len(enriched) != len(index_rows):
        preview = "\n".join(errors[:20])
        raise SystemExit(f"role replay quality gate failed ({len(errors)} errors):\n{preview}")

    authors_after = sum(len(metadata.get("authors", [])) for _, metadata in enriched)
    csv_authors_before = sum(
        len(csv_author_names(rows)) for rows in current_csv_by_paper.values()
    )
    if authors_after != csv_authors_before:
        raise SystemExit(
            f"author count gate failed: csv_authors={csv_authors_before} metadata={authors_after}"
        )

    report_name = "pdf_author_role_enrichment.csv" if args.apply else "pdf_author_role_enrichment_dry_run.csv"
    report_path = dataset_dir / report_name
    write_csv(report_path, REPORT_FIELDS, report_rows)
    summary = {
        "mode": "apply" if args.apply else "dry-run",
        "papers": len(enriched),
        "authors": authors_after,
        "equal_contribution_papers": sum(bool(role_names(metadata["authors"], "equal_contribution")) for _, metadata in enriched),
        "equal_contribution_authors": sum(len(role_names(metadata["authors"], "equal_contribution")) for _, metadata in enriched),
        "corresponding_papers": sum(bool(role_names(metadata["authors"], "corresponding")) for _, metadata in enriched),
        "corresponding_authors": sum(len(role_names(metadata["authors"], "corresponding")) for _, metadata in enriched),
        "ambiguous_role_papers": sum(
            any(reason.get("stage") == "role_linking" for reason in metadata.get("_extraction", {}).get("review_reasons", []))
            for _, metadata in enriched
        ),
        "report": str(report_path),
    }
    if not args.apply:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    backup_dir = make_backup(dataset_dir)
    csv_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    metrics = new_metrics(len(enriched), include_extended=True)
    for row, metadata in enriched:
        paper_id = row["paper_id"]
        source_file = row.get("source_file", "")
        update_metrics(metrics, metadata)
        review_rows.extend(
            review_csv_rows(
                paper_id,
                source_file,
                metadata.get("_extraction", {}).get("review_reasons", []),
            )
        )
        csv_rows.extend(
            row
            for author in metadata.get("authors", [])
            for row in author_csv_rows(paper_id, metadata, author, args.conference)
        )
        write_json(dataset_dir / "metadata_json" / f"{paper_id}.json", metadata)
        extraction = metadata.get("_extraction", {})
        write_json(
            dataset_dir / "evidence_json" / f"{paper_id}.json",
            {"paper_id": paper_id, "evidence": extraction.get("evidence", [])},
        )
        write_json(
            dataset_dir / "candidate_json" / f"{paper_id}.json",
            {
                "paper_id": paper_id,
                "candidates": extraction.get("candidates", {}),
                "decisions": extraction.get("decisions", []),
            },
        )

    metrics.update({
        "pdf_role_replayed_papers": len(enriched),
        "equal_contribution_papers": summary["equal_contribution_papers"],
        "equal_contribution_authors": summary["equal_contribution_authors"],
        "corresponding_papers": summary["corresponding_papers"],
        "corresponding_authors": summary["corresponding_authors"],
        "ambiguous_role_papers": summary["ambiguous_role_papers"],
    })
    for key, value in previous_metrics.items():
        if key not in metrics:
            metrics[key] = value
    write_csv(dataset_dir / "paper_metadata.csv", CSV_FIELDNAMES, csv_rows)
    write_csv(dataset_dir / "review_queue.csv", REVIEW_FIELDNAMES, review_rows)
    write_json(metrics_path, metrics)
    summary["backup"] = str(backup_dir)
    summary["review_reasons_after"] = len(review_rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
