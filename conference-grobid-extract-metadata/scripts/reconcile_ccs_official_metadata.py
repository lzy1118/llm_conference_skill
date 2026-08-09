from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
PAPER_EXTRACTION_SCRIPTS = WORKSPACE_ROOT / "conference-paper-extraction" / "scripts"
GROBID_SCRIPTS = WORKSPACE_ROOT / "conference-grobid-extract-metadata" / "scripts"
for script_dir in (PAPER_EXTRACTION_SCRIPTS, GROBID_SCRIPTS):
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))

import build_paper_metadata_with_affiliations as paper_builder
import security_affiliation_sources as security
from author_metadata.artifacts import new_metrics, update_metrics
from author_metadata.paper_fields import build_paper_relationship_summary


OFFICIAL_URL = "https://www.sigsac.org/ccs/CCS2021/accepted-papers.html"
CSV_FIELDS = [
    "paper_id",
    "year",
    "conference",
    "title",
    "author",
    "author_rank",
    "affiliations",
    "emails",
    "first_author",
    "co_first_author",
    "corresponding",
    "equal_contribution",
]
REVIEW_FIELDS = ["paper_id", "source_file", "code", "field", "author", "stage", "details"]
RESOLVED_REVIEW_FIELDS = {"author", "authors", "affiliations"}
OFFICIAL_SOURCE = "ccs_official_accepted_papers"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild CCS 2021 author-affiliation rows from the official accepted-papers page."
    )
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument(
        "--raw-papers",
        type=Path,
        default=WORKSPACE_ROOT / "generated-data/extraction/raw/by_conference/ccs_2021/papers.json",
        help="DBLP paper list used only as a title/author crosswalk when the official and PDF titles differ.",
    )
    parser.add_argument(
        "--metadata-seed-dir",
        type=Path,
        default=None,
        help="Optional prior metadata_json directory used to preserve emails and author roles on a rerun.",
    )
    parser.add_argument("--apply", action="store_true", help="Apply changes after all quality gates pass.")
    return parser.parse_args()


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def group_current_rows(rows: list[dict[str, str]]) -> OrderedDict[str, list[dict[str, str]]]:
    grouped: OrderedDict[str, list[dict[str, str]]] = OrderedDict()
    for row in rows:
        paper_id = row.get("paper_id", "")
        if not paper_id:
            raise ValueError("paper_metadata.csv contains a row without paper_id")
        grouped.setdefault(paper_id, []).append(row)
    for paper_rows in grouped.values():
        paper_rows.sort(key=lambda row: int(row.get("author_rank") or 0))
    return grouped


def official_authors(entry: dict[str, Any]) -> list[str]:
    return paper_builder.official_entry_authors(entry)


def make_lookup(entries: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, ...], dict[str, Any]]]:
    by_title: dict[str, dict[str, Any]] = {}
    by_authors: dict[tuple[str, ...], dict[str, Any]] = {}
    for entry in entries:
        title_key = security.official_title_key(str(entry.get("title", "")))
        authors_key = paper_builder.author_tuple(official_authors(entry))
        if title_key:
            if title_key in by_title:
                raise ValueError(f"ambiguous normalized title: {entry.get('title', '')}")
            by_title[title_key] = entry
        if authors_key:
            by_authors.setdefault(authors_key, entry)
    return by_title, by_authors


def current_paper(paper_rows: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "title": paper_rows[0].get("title", ""),
        "authors": [row.get("author", "") for row in paper_rows],
    }


def find_entry_with_method(
    paper: dict[str, Any],
    by_title: dict[str, dict[str, Any]],
    by_authors: dict[tuple[str, ...], dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    title_key = security.official_title_key(str(paper.get("title", "")))
    if title_key and title_key in by_title:
        return by_title[title_key], "normalized_title_exact"
    authors_key = paper_builder.author_tuple(paper_builder.raw_author_names(paper))
    if authors_key and authors_key in by_authors:
        return by_authors[authors_key], "author_sequence_exact"
    entry = paper_builder.find_official_entry(paper, by_title, by_authors)
    return (entry, "title_author_fuzzy") if entry else (None, "")


def build_match_plan(
    grouped_rows: OrderedDict[str, list[dict[str, str]]],
    official_entries: list[dict[str, Any]],
    raw_papers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    official_by_title, official_by_authors = make_lookup(official_entries)
    raw_by_title, raw_by_authors = make_lookup(raw_papers)

    raw_to_official: dict[int, tuple[dict[str, Any], str]] = {}
    for raw_paper in raw_papers:
        official_entry, method = find_entry_with_method(raw_paper, official_by_title, official_by_authors)
        if official_entry is None:
            raise ValueError(f"raw paper did not match official page: {raw_paper.get('title', '')}")
        raw_to_official[id(raw_paper)] = (official_entry, method)

    plan: list[dict[str, Any]] = []
    used_official_ids: set[str] = set()
    for paper_id, paper_rows in grouped_rows.items():
        paper = current_paper(paper_rows)
        official_entry, direct_method = find_entry_with_method(paper, official_by_title, official_by_authors)
        if direct_method not in {"normalized_title_exact", "author_sequence_exact"}:
            raw_paper, raw_method = find_entry_with_method(paper, raw_by_title, raw_by_authors)
            if raw_paper is not None:
                official_entry, official_method = raw_to_official[id(raw_paper)]
                direct_method = f"dblp_crosswalk:{raw_method}:{official_method}"
        if official_entry is None:
            official_entry, direct_method = find_entry_with_method(paper, official_by_title, official_by_authors)
        if official_entry is None:
            raise ValueError(f"current paper did not match official page: {paper.get('title', '')}")

        official_id = str(official_entry.get("paperId", ""))
        if not official_id or official_id in used_official_ids:
            raise ValueError(f"official entry was matched more than once: {official_entry.get('title', '')}")
        used_official_ids.add(official_id)
        plan.append(
            {
                "paper_id": paper_id,
                "paper_rows": paper_rows,
                "official_entry": official_entry,
                "match_method": direct_method,
            }
        )

    if len(plan) != len(grouped_rows) or len(used_official_ids) != len(official_entries):
        raise ValueError(
            f"coverage gate failed: current={len(grouped_rows)}, plan={len(plan)}, "
            f"official={len(official_entries)}, used={len(used_official_ids)}"
        )
    return plan


def compact_name(value: str) -> str:
    return "".join(char for char in str(value).casefold() if char.isalnum())


def assign_old_authors(
    official_names: list[str],
    old_authors: list[dict[str, Any]],
) -> list[dict[str, Any] | None]:
    """Map legacy rows without spreading grouped role/email evidence."""
    assignments: list[dict[str, Any] | None] = [None] * len(official_names)
    used_old: set[int] = set()
    for official_index, official_name in enumerate(official_names):
        exact = [
            (index, author)
            for index, author in enumerate(old_authors)
            if index not in used_old and security.names_match(official_name, str(author.get("name", "")))
        ]
        if len(exact) == 1:
            old_index, author = exact[0]
            assignments[official_index] = author
            used_old.add(old_index)

    for old_index, author in enumerate(old_authors):
        if old_index in used_old:
            continue
        old_key = compact_name(str(author.get("name", "")))
        if not old_key:
            continue
        contained = [
            index
            for index, official_name in enumerate(official_names)
            if assignments[index] is None and compact_name(official_name) in old_key
        ]
        if contained:
            assignments[contained[0]] = author
            used_old.add(old_index)
    return assignments


def official_rows(entry: dict[str, Any]) -> list[dict[str, Any]]:
    rows = entry.get("official_affiliations") or []
    authors = official_authors(entry)
    if len(rows) != len(authors):
        raise ValueError(f"official author-affiliation coverage mismatch: {entry.get('title', '')}")
    result = []
    for index, (author_name, row) in enumerate(zip(authors, rows)):
        row_name = security.clean_author_name(str(row.get("name", "")))
        affiliations = security.normalize_affiliation_values(row.get("affiliations", []))
        if not security.names_match(author_name, row_name) or not affiliations:
            raise ValueError(f"invalid official author-affiliation row: {entry.get('title', '')} #{index}")
        result.append({"name": author_name, "affiliations": affiliations})
    return result


def rebuild_metadata(
    metadata: dict[str, Any],
    entry: dict[str, Any],
    match_method: str,
) -> dict[str, Any]:
    old_authors = metadata.get("authors", [])
    rebuilt_authors: list[dict[str, Any]] = []
    rows = official_rows(entry)
    old_assignments = assign_old_authors([row["name"] for row in rows], old_authors)
    for index, official_row in enumerate(rows):
        old_author = old_assignments[index]
        co_first = bool((old_author or {}).get("co_first_author", False))
        equal_contribution = bool((old_author or {}).get("equal_contribution", False))
        rebuilt_authors.append(
            {
                "order": index,
                "name": official_row["name"],
                "email": str((old_author or {}).get("email", "")),
                "affiliations": list(official_row["affiliations"]),
                "affiliation_source": OFFICIAL_SOURCE,
                "first_author": index == 0 or co_first,
                "co_first_author": co_first,
                "equal_contribution": equal_contribution,
                "corresponding": bool((old_author or {}).get("corresponding", False)),
            }
        )

    metadata["authors"] = rebuilt_authors
    metadata.update(build_paper_relationship_summary(rebuilt_authors))
    extraction = metadata.setdefault("_extraction", {})
    extraction["review_reasons"] = [
        reason
        for reason in extraction.get("review_reasons", [])
        if reason.get("field") not in RESOLVED_REVIEW_FIELDS
    ]
    extraction["evidence"] = [
        evidence
        for evidence in extraction.get("evidence", [])
        if evidence.get("source") != OFFICIAL_SOURCE
    ]
    extraction["evidence"].extend(
        {
            "evidence_id": f"official_web:author:{index}",
            "source": OFFICIAL_SOURCE,
            "source_url": OFFICIAL_URL,
            "field": "author_affiliation_relation",
            "order": index,
            "author": row["name"],
            "affiliations": row["affiliations"],
        }
        for index, row in enumerate(rows)
    )
    candidates = extraction.setdefault("candidates", {})
    candidates["official_web_author_affiliations"] = rows
    extraction["decisions"] = [
        decision
        for decision in extraction.get("decisions", [])
        if decision.get("action") != "replace_author_affiliations_from_ccs_official"
    ]
    extraction["decisions"].append(
        {
            "action": "replace_author_affiliations_from_ccs_official",
            "stage": "official_web_reconciliation",
            "field": "authors",
            "source": OFFICIAL_SOURCE,
            "source_url": OFFICIAL_URL,
            "match_method": match_method,
            "previous_author_count": len(old_authors),
            "selected_author_count": len(rebuilt_authors),
            "source_repairs": entry.get("source_repairs", []),
        }
    )
    extraction["official_web"] = {
        "source": OFFICIAL_SOURCE,
        "source_url": OFFICIAL_URL,
        "official_title": entry.get("title", ""),
        "match_method": match_method,
        "source_repairs": entry.get("source_repairs", []),
    }
    return metadata


def csv_rows_from_metadata(paper_id: str, metadata: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for author in metadata.get("authors", []):
        rows.append(
            {
                "paper_id": paper_id,
                "year": metadata.get("year", ""),
                "conference": "ccs",
                "title": metadata.get("title", ""),
                "author": author.get("name", ""),
                "author_rank": author.get("order", ""),
                "affiliations": "; ".join(author.get("affiliations", [])),
                "emails": author.get("email", ""),
                "first_author": str(bool(author.get("first_author"))).lower(),
                "co_first_author": str(bool(author.get("co_first_author"))).lower(),
                "corresponding": str(bool(author.get("corresponding"))).lower(),
                "equal_contribution": str(bool(author.get("equal_contribution"))).lower(),
            }
        )
    return rows


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


def build_report_rows(plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in plan:
        current = item["paper_rows"]
        entry = item["official_entry"]
        rows.append(
            {
                "paper_id": item["paper_id"],
                "local_title": current[0].get("title", ""),
                "official_title": entry.get("title", ""),
                "match_method": item["match_method"],
                "old_author_count": len(current),
                "official_author_count": len(official_authors(entry)),
                "old_authors": json.dumps([row.get("author", "") for row in current], ensure_ascii=False),
                "official_authors": json.dumps(official_authors(entry), ensure_ascii=False),
                "official_affiliations": json.dumps(entry.get("official_affiliations", []), ensure_ascii=False),
                "source_repairs": json.dumps(entry.get("source_repairs", []), ensure_ascii=False),
            }
        )
    return rows


def source_files_by_paper(dataset_dir: Path) -> dict[str, str]:
    path = dataset_dir / "paper_index.csv"
    if not path.exists():
        return {}
    return {row.get("paper_id", ""): row.get("source_file", "") for row in load_csv_rows(path)}


def review_rows_from_metadata(paper_id: str, metadata: dict[str, Any], source_file: str) -> list[dict[str, Any]]:
    rows = []
    for reason in metadata.get("_extraction", {}).get("review_reasons", []):
        details = {
            key: value
            for key, value in reason.items()
            if key not in {"code", "field", "author", "stage"}
        }
        rows.append(
            {
                "paper_id": paper_id,
                "source_file": source_file,
                "code": reason.get("code", "review_required"),
                "field": reason.get("field", ""),
                "author": reason.get("author", ""),
                "stage": reason.get("stage", ""),
                "details": json.dumps(details, ensure_ascii=False, sort_keys=True),
            }
        )
    return rows


def make_backup(dataset_dir: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup_dir = dataset_dir / "backups" / f"before_ccs_official_{stamp}"
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
    dataset_dir = args.dataset_dir.resolve()
    csv_path = dataset_dir / "paper_metadata.csv"
    metadata_dir = dataset_dir / "metadata_json"
    if not csv_path.exists() or not metadata_dir.is_dir() or not args.raw_papers.exists():
        raise SystemExit("dataset, metadata_json, or raw DBLP papers are missing")

    current_rows = load_csv_rows(csv_path)
    grouped_rows = group_current_rows(current_rows)
    raw_papers = json.loads(args.raw_papers.read_text(encoding="utf-8"))
    official_entries = security.fetch_ccs_official_entries(2021)
    if len(grouped_rows) != 196 or len(raw_papers) != 196 or len(official_entries) != 196:
        raise SystemExit(
            f"coverage gate failed: current={len(grouped_rows)}, raw={len(raw_papers)}, official={len(official_entries)}"
        )
    if any(not official_rows(entry) for entry in official_entries):
        raise SystemExit("official page has an incomplete author-affiliation entry")

    plan = build_match_plan(grouped_rows, official_entries, raw_papers)
    report_rows = build_report_rows(plan)
    report_name = "ccs_official_reconciliation.csv" if args.apply else "ccs_official_reconciliation_dry_run.csv"
    report_path = dataset_dir / report_name
    write_csv(report_path, list(report_rows[0]), report_rows)

    summary = {
        "mode": "apply" if args.apply else "dry-run",
        "papers": len(plan),
        "authors_before": len(current_rows),
        "authors_after": sum(len(official_authors(item["official_entry"])) for item in plan),
        "official_affiliations_nonempty": sum(
            len(official_rows(item["official_entry"])) for item in plan
        ),
        "separator_repairs": sum(
            sum(int(repair.get("count", 0)) for repair in item["official_entry"].get("source_repairs", []))
            for item in plan
        ),
        "report": str(report_path),
    }
    if not args.apply:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    backup_dir = make_backup(dataset_dir)
    all_csv_rows: list[dict[str, Any]] = []
    all_review_rows: list[dict[str, Any]] = []
    rebuilt_metadata: list[tuple[str, dict[str, Any]]] = []
    source_files = source_files_by_paper(dataset_dir)
    metadata_seed_dir = (args.metadata_seed_dir or metadata_dir).resolve()
    metrics = new_metrics(len(plan), include_extended=True)

    for item in plan:
        paper_id = item["paper_id"]
        metadata_path = metadata_seed_dir / f"{paper_id}.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata = rebuild_metadata(metadata, item["official_entry"], item["match_method"])
        rebuilt_metadata.append((paper_id, metadata))
        all_csv_rows.extend(csv_rows_from_metadata(paper_id, metadata))
        all_review_rows.extend(review_rows_from_metadata(paper_id, metadata, source_files.get(paper_id, "")))
        update_metrics(metrics, metadata)

    metrics.update(
        {
            "official_web_reconciled_papers": len(plan),
            "official_web_affiliation_rows": len(all_csv_rows),
            "official_web_separator_repairs": summary["separator_repairs"],
        }
    )
    write_csv(csv_path, CSV_FIELDS, all_csv_rows)
    write_csv(dataset_dir / "review_queue.csv", REVIEW_FIELDS, all_review_rows)
    write_json(dataset_dir / "extraction_metrics.json", metrics)
    write_json(
        dataset_dir / "official_web_evidence" / "ccs_2021.json",
        {
            "conference": "ccs",
            "year": 2021,
            "source_url": OFFICIAL_URL,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "entries": official_entries,
        },
    )
    for paper_id, metadata in rebuilt_metadata:
        write_json(metadata_dir / f"{paper_id}.json", metadata)
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

    summary["backup"] = str(backup_dir)
    summary["review_reasons_after"] = len(all_review_rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
