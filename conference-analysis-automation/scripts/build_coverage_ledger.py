from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "generated-data" / "coverage"
DEFAULT_EXPECTED_COUNTS = ROOT / "generated-data" / "coverage" / "expected_paper_counts.csv"
DEFAULT_CFP_DIR = ROOT / "generated-data" / "cfp" / "output"
DEFAULT_AUTHOR_ROLES_DIR = ROOT / "generated-data" / "author-roles"
SEARCH_ROOTS = (ROOT / "generated-data" / "extraction", ROOT / "data")

sys.path.insert(0, str(ROOT / "conference-paper-extraction" / "scripts"))
from conference_registry import CONFERENCES  # noqa: E402


@dataclass(frozen=True)
class ArtifactSet:
    raw_json: Path | None = None
    validation_report: Path | None = None
    author_affiliations: Path | None = None
    affiliation_queue: Path | None = None


def read_json(path: Path | None) -> Any:
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def read_csv_rows(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_expected_counts(path: Path | None) -> dict[str, int]:
    rows = read_csv_rows(path)
    expected: dict[str, int] = {}
    for row in rows:
        key = row.get("conference_key", "").strip()
        value = row.get("expected_papers", "").strip()
        if not key or not value:
            continue
        try:
            expected[key] = int(value)
        except ValueError:
            continue
    return expected


def load_cfp_status(cfp_dir: Path | None) -> dict[str, str]:
    if cfp_dir is None:
        return {}
    events = read_csv_rows(cfp_dir / "conference_events.csv")
    editions = read_csv_rows(cfp_dir / "conference_edition_metadata.csv")
    events_by_key: dict[str, list[dict[str, str]]] = {}
    editions_by_key: dict[str, list[dict[str, str]]] = {}
    for row in events:
        key = row.get("conference_key", "").strip()
        if key:
            events_by_key.setdefault(key, []).append(row)
    for row in editions:
        key = row.get("conference_key", "").strip()
        if key:
            editions_by_key.setdefault(key, []).append(row)

    statuses: dict[str, str] = {}
    for key in CONFERENCES:
        key_events = events_by_key.get(key, [])
        key_editions = editions_by_key.get(key, [])
        if not key_events and not key_editions:
            statuses[key] = "missing"
            continue
        review_rows = [row for row in key_events + key_editions if str(row.get("needs_review", "")).lower() == "true"]
        dated_events = [row for row in key_events if row.get("event_date", "").strip()]
        conference_dates = {
            row.get("event_type", "")
            for row in key_events
            if row.get("event_type") in {"conference_start", "conference_end"} and row.get("event_date", "").strip()
        }
        deadline_events = [row for row in key_events if "deadline" in row.get("event_type", "") and row.get("event_date", "").strip()]
        if review_rows:
            statuses[key] = "needs_review"
        elif dated_events and conference_dates and deadline_events:
            statuses[key] = "complete_unverified"
        else:
            statuses[key] = "partial"
    return statuses


def load_author_role_status(author_roles_dir: Path | None) -> dict[tuple[str, int], str]:
    if author_roles_dir is None:
        return {}
    rows = read_csv_rows(author_roles_dir / "paper_author_roles.csv")
    by_conference_year: dict[tuple[str, int], list[dict[str, str]]] = {}
    for row in rows:
        conference = row.get("conference", "").strip()
        year_text = row.get("year", "").strip()
        if not conference or not year_text:
            continue
        try:
            year = int(float(year_text))
        except ValueError:
            continue
        by_conference_year.setdefault((conference, year), []).append(row)

    statuses: dict[tuple[str, int], str] = {}
    for key, grouped in by_conference_year.items():
        if not grouped:
            statuses[key] = "missing"
            continue
        has_first = any(row.get("is_first_author", "").lower() == "true" for row in grouped)
        has_participant = any(row.get("is_participating_author", "").lower() == "true" for row in grouped)
        has_corresponding = any(row.get("is_corresponding_author", "").lower() == "true" for row in grouped)
        has_equal = any(row.get("is_equal_contribution", "").lower() == "true" for row in grouped)
        if has_first and has_participant and has_corresponding and has_equal:
            statuses[key] = "complete_unverified"
        elif has_first and has_participant and has_corresponding:
            statuses[key] = "corresponding_author_available"
        elif has_first and has_participant:
            statuses[key] = "first_author_only"
        elif has_participant:
            statuses[key] = "participant_only"
        else:
            statuses[key] = "missing"
    return statuses


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def candidate_paths(key: str) -> ArtifactSet:
    raw_candidates: list[Path] = []
    report_candidates: list[Path] = []
    author_candidates: list[Path] = []
    queue_candidates: list[Path] = []
    for root in SEARCH_ROOTS:
        raw_candidates.extend(root.glob(f"**/{key}_papers.json"))
        raw_candidates.extend(root.glob(f"**/by_conference/{key}/papers.json"))
        report_candidates.extend(root.glob(f"**/{key}_validation_report.json"))
        report_candidates.extend(root.glob(f"**/by_conference/{key}/validation_report.json"))
        author_candidates.extend(root.glob(f"**/{key}_author_affiliations_expanded.csv"))
        author_candidates.extend(root.glob(f"**/{key}_author_affiliations.csv"))
        author_candidates.extend(root.glob(f"**/by_conference/{key}/author_affiliations_expanded.csv"))
        author_candidates.extend(root.glob(f"**/by_conference/{key}/author_affiliations.csv"))
        queue_candidates.extend(root.glob(f"**/{key}_affiliation_resolution_queue.csv"))
        queue_candidates.extend(root.glob(f"**/by_conference/{key}/affiliation_resolution_queue.csv"))
    return ArtifactSet(
        raw_json=pick_newest(raw_candidates),
        validation_report=pick_newest(report_candidates),
        author_affiliations=pick_best_author_csv(author_candidates),
        affiliation_queue=pick_newest(queue_candidates),
    )


def pick_newest(paths: list[Path]) -> Path | None:
    if not paths:
        return None
    return sorted(paths, key=lambda path: path.stat().st_mtime, reverse=True)[0]


def pick_best_author_csv(paths: list[Path]) -> Path | None:
    if not paths:
        return None
    expanded = [path for path in paths if path.name.endswith("_author_affiliations_expanded.csv")]
    return pick_newest(expanded or paths)


def normalize_match_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold().rstrip(".")


def coerce_papers(raw_payload: Any) -> list[dict[str, Any]]:
    if isinstance(raw_payload, dict):
        papers = raw_payload.get("acceptedPapers") or raw_payload.get("papers") or []
    elif isinstance(raw_payload, list):
        papers = raw_payload
    else:
        papers = []
    return [paper for paper in papers if isinstance(paper, dict)]


def paper_id_for(index: int, paper: dict[str, Any]) -> str:
    for field in ("paperId", "paper_id", "key", "id"):
        value = str(paper.get(field, "")).strip()
        if value:
            return value
    return f"row_{index}"


def title_for(paper: dict[str, Any]) -> str:
    return str(paper.get("title") or paper.get("name") or "").strip()


def author_count_for(paper: dict[str, Any]) -> int:
    authors = paper.get("authors")
    if isinstance(authors, list):
        return len(authors)
    if isinstance(authors, str):
        return len([part for part in authors.split(";") if part.strip()]) or 1
    author = paper.get("author")
    if isinstance(author, str) and author.strip():
        return len([part for part in author.split(";") if part.strip()]) or 1
    return 0


def artifact_presence(path: Path | None) -> str:
    return "present" if path and path.exists() else "missing"


def status_from_counts(present: bool, total: int, issue_count: int = 0) -> str:
    if not present:
        return "missing"
    if total <= 0:
        return "partial"
    if issue_count > 0:
        return "needs_review"
    return "complete_unverified"


def paper_count_match_status(expected: int | None, observed: int) -> tuple[str, int | str]:
    if expected is None:
        return "missing_expected_count", ""
    delta = observed - expected
    if delta == 0:
        return "matches_expected", delta
    return "count_mismatch", delta


def contract_version(report: dict[str, Any]) -> str:
    if not report:
        return "unknown"
    if "classified_author_rows" in report or "resolved_country_rows" in report:
        return "author_affiliation_country_v1"
    return "unknown"


def build_paper_completeness(
    conference: str,
    year: int,
    papers: list[dict[str, Any]],
    author_rows: list[dict[str, str]],
    queue_rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    rows_by_paper: dict[str, list[dict[str, str]]] = {}
    for row in author_rows:
        paper_id = row.get("paper_id", "").strip()
        title = row.get("title", "").strip()
        article_tag = row.get("article_tag", "").strip()
        keys = [paper_id, title, normalize_match_text(title)]
        if article_tag and "-" in article_tag:
            keys.append(article_tag.split("-", 1)[1])
            keys.append(normalize_match_text(article_tag.split("-", 1)[1]))
        for key in {candidate for candidate in keys if candidate}:
            rows_by_paper.setdefault(key, []).append(row)

    queued = {
        key
        for row in queue_rows
        for key in (row.get("paper_id", "").strip(), row.get("title", "").strip(), normalize_match_text(row.get("title", "")))
        if key
    }
    completeness_rows: list[dict[str, object]] = []
    for index, paper in enumerate(papers, start=1):
        paper_id = paper_id_for(index, paper)
        title = title_for(paper)
        matched_rows = rows_by_paper.get(paper_id) or rows_by_paper.get(title) or rows_by_paper.get(normalize_match_text(title)) or []
        source_authors = author_count_for(paper)
        authors_with_affiliation = sum(1 for row in matched_rows if row.get("inst", "").strip())
        authors_with_country = sum(1 for row in matched_rows if row.get("country", "").strip() and row.get("country") != "Unknown")
        missing_affiliations = max(source_authors - authors_with_affiliation, 0) if source_authors else 0
        unknown_country = sum(1 for row in matched_rows if row.get("country") == "Unknown")
        issue_codes: list[str] = []
        if paper_id in queued or title in queued:
            issue_codes.append("affiliation_queue")
        if source_authors and authors_with_affiliation < source_authors:
            issue_codes.append("missing_affiliations")
        if unknown_country:
            issue_codes.append("unknown_country")
        if not matched_rows:
            issue_codes.append("no_author_affiliation_rows")
        status = "complete_unverified" if not issue_codes else "needs_review"
        completeness_rows.append(
            {
                "conference": conference,
                "year": year,
                "paper_id": paper_id,
                "title": title,
                "source_author_count": source_authors,
                "extracted_author_rows": len(matched_rows),
                "authors_with_affiliation": authors_with_affiliation,
                "authors_with_country": authors_with_country,
                "has_first_author": any(str(row.get("author_order", "")) == "0" for row in matched_rows),
                "has_corresponding_author": False,
                "missing_affiliation_count": missing_affiliations,
                "unknown_country_count": unknown_country,
                "completeness_status": status,
                "issue_codes": ";".join(issue_codes),
            }
        )
    return completeness_rows


def build_ledger(
    expected_counts: dict[str, int],
    cfp_statuses: dict[str, str],
    author_role_statuses: dict[tuple[str, int], str],
    min_year: int | None = None,
    max_year: int | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    ledger: list[dict[str, object]] = []
    tasks: list[dict[str, object]] = []
    paper_audit: list[dict[str, object]] = []
    generated_at = datetime.now(timezone.utc).isoformat()

    selected_conferences = [
        (key, conference)
        for key, conference in CONFERENCES.items()
        if (min_year is None or conference.year >= min_year)
        and (max_year is None or conference.year <= max_year)
    ]
    for key, conference in sorted(selected_conferences, key=lambda item: (item[1].family, item[1].conference, item[1].year)):
        artifacts = candidate_paths(key)
        report = read_json(artifacts.validation_report) or {}
        raw_payload = read_json(artifacts.raw_json)
        papers = coerce_papers(raw_payload)
        author_rows = read_csv_rows(artifacts.author_affiliations)
        queue_rows = read_csv_rows(artifacts.affiliation_queue)

        papers_count = int(report.get("papers_count") or len(papers) or 0)
        expected_papers = expected_counts.get(key)
        count_status, paper_count_delta = paper_count_match_status(expected_papers, papers_count)
        expanded_author_rows = int(report.get("expanded_author_rows") or len(author_rows) or 0)
        mismatch_issues = int(report.get("affiliation_mismatch_issues") or len(queue_rows) or 0)
        papers_without_affiliation = int(report.get("papers_without_affiliation_data") or 0)
        resolved_country_rows = int(report.get("resolved_country_rows") or report.get("classified_author_rows") or 0)
        unresolved_country_rows = int(report.get("unresolved_country_rows") or 0)

        paper_status = status_from_counts(artifacts.raw_json is not None, papers_count)
        if paper_status == "complete_unverified" and count_status == "matches_expected":
            paper_status = "complete_verified"
        elif paper_status == "complete_unverified" and count_status == "count_mismatch":
            paper_status = "needs_review"
        affiliation_status = status_from_counts(expanded_author_rows > 0, expanded_author_rows, mismatch_issues + papers_without_affiliation)
        country_status = status_from_counts(resolved_country_rows > 0, resolved_country_rows, unresolved_country_rows)
        role_status = author_role_statuses.get((conference.conference, conference.year)) or ("first_author_only" if expanded_author_rows else "missing")
        cfp_status = cfp_statuses.get(key, "missing")
        version = contract_version(report)

        ledger.append(
            {
                "conference_key": key,
                "conference": conference.conference,
                "year": conference.year,
                "family": conference.family,
                "backend": conference.backend,
                "paper_metadata_status": paper_status,
                "affiliation_status": affiliation_status,
                "country_status": country_status,
                "role_status": role_status,
                "cfp_status": cfp_status,
                "raw_json_status": artifact_presence(artifacts.raw_json),
                "validation_report_status": artifact_presence(artifacts.validation_report),
                "author_affiliations_status": artifact_presence(artifacts.author_affiliations),
                "affiliation_queue_status": artifact_presence(artifacts.affiliation_queue),
                "contract_version": version,
                "expected_papers": expected_papers if expected_papers is not None else "",
                "paper_count_match_status": count_status,
                "paper_count_delta": paper_count_delta,
                "source_papers": len(papers),
                "reported_papers": papers_count,
                "expanded_author_rows": expanded_author_rows,
                "resolved_country_rows": resolved_country_rows,
                "unresolved_country_rows": unresolved_country_rows,
                "affiliation_mismatch_issues": mismatch_issues,
                "papers_without_affiliation_data": papers_without_affiliation,
                "raw_json_path": str(artifacts.raw_json or ""),
                "validation_report_path": str(artifacts.validation_report or ""),
                "generated_at": generated_at,
            }
        )

        add_backfill_tasks(tasks, key, conference.conference, conference.year, paper_status, affiliation_status, country_status, role_status, cfp_status, version, count_status)
        paper_audit.extend(build_paper_completeness(conference.conference, conference.year, papers, author_rows, queue_rows))

    return ledger, tasks, paper_audit


def add_backfill_tasks(
    tasks: list[dict[str, object]],
    key: str,
    conference: str,
    year: int,
    paper_status: str,
    affiliation_status: str,
    country_status: str,
    role_status: str,
    cfp_status: str,
    version: str,
    count_status: str,
) -> None:
    task_specs = []
    if paper_status == "missing":
        task_specs.append(("fetch_papers", "high", "paper metadata is missing"))
    if affiliation_status in {"missing", "partial", "needs_review"}:
        task_specs.append(("fetch_affiliations", "high", f"affiliation status is {affiliation_status}"))
    if country_status in {"missing", "partial", "needs_review"}:
        task_specs.append(("normalize_country", "medium", f"country status is {country_status}"))
    if role_status != "complete_verified":
        task_specs.append(("extract_author_roles", "medium", f"role status is {role_status}"))
    if cfp_status == "missing":
        task_specs.append(("extract_cfp", "medium", "conference CFP metadata is missing"))
    if count_status == "missing_expected_count":
        task_specs.append(("add_expected_paper_count", "low", "official expected paper count is missing"))
    elif count_status == "count_mismatch":
        task_specs.append(("verify_paper_count", "high", "reported paper count differs from expected count"))

    for task_type, priority, reason in task_specs:
        tasks.append(
            {
                "task_id": f"{key}:{task_type}",
                "conference_key": key,
                "conference": conference,
                "year": year,
                "task_type": task_type,
                "priority": priority,
                "reason": reason,
                "suggested_backend": "manual_or_existing_backend",
                "status": "pending",
            }
        )


def write_report(path: Path, ledger: list[dict[str, object]], tasks: list[dict[str, object]], paper_audit: list[dict[str, object]]) -> None:
    total = len(ledger)
    missing_papers = sum(1 for row in ledger if row["paper_metadata_status"] == "missing")
    affiliation_needs_work = sum(1 for row in ledger if row["affiliation_status"] != "complete_unverified")
    cfp_missing = sum(1 for row in ledger if row["cfp_status"] == "missing")
    missing_expected = sum(1 for row in ledger if row["paper_count_match_status"] == "missing_expected_count")
    count_mismatch = sum(1 for row in ledger if row["paper_count_match_status"] == "count_mismatch")
    incomplete_papers = sum(1 for row in paper_audit if row["completeness_status"] != "complete_unverified")
    lines = [
        "# Conference Coverage Report",
        "",
        "## Summary",
        "",
        f"- registered_conference_years: {total}",
        f"- missing_paper_metadata: {missing_papers}",
        f"- affiliation_needs_work: {affiliation_needs_work}",
        f"- cfp_missing: {cfp_missing}",
        f"- missing_expected_paper_counts: {missing_expected}",
        f"- paper_count_mismatches: {count_mismatch}",
        f"- generated_backfill_tasks: {len(tasks)}",
        f"- audited_papers: {len(paper_audit)}",
        f"- papers_needing_review: {incomplete_papers}",
        "",
        "## Highest Priority Tasks",
        "",
    ]
    high_tasks = [task for task in tasks if task["priority"] == "high"][:20]
    if not high_tasks:
        lines.append("- No high priority tasks.")
    for task in high_tasks:
        lines.append(f"- {task['task_id']}: {task['reason']}")
    lines.extend(["", "## Notes", "", "- expected_papers comes from an optional expected-count CSV; missing values produce low-priority add_expected_paper_count tasks.", "- role_status is computed from generated-data/author-roles when paper_author_roles.csv exists.", "- cfp_status is computed from generated-data/cfp/output when CFP event or edition rows exist."])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_expected_counts_template(path: Path, ledger: list[dict[str, object]]) -> None:
    rows = []
    for row in ledger:
        rows.append(
            {
                "conference_key": row["conference_key"],
                "conference": row["conference"],
                "year": row["year"],
                "expected_papers": row["expected_papers"],
                "observed_papers": row["reported_papers"],
                "source_url": "",
                "notes": "",
            }
        )
    write_csv(path, rows, ["conference_key", "conference", "year", "expected_papers", "observed_papers", "source_url", "notes"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build conference coverage ledger and backfill task files.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--expected-counts", type=Path, default=DEFAULT_EXPECTED_COUNTS, help="Optional CSV with conference_key,expected_papers columns")
    parser.add_argument("--cfp-dir", type=Path, default=DEFAULT_CFP_DIR, help="Directory containing CFP output CSV files")
    parser.add_argument("--author-roles-dir", type=Path, default=DEFAULT_AUTHOR_ROLES_DIR, help="Directory containing paper_author_roles.csv")
    parser.add_argument("--min-year", type=int, default=2020, help="Minimum conference year to include.")
    parser.add_argument("--max-year", type=int, default=2025, help="Maximum conference year to include.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    expected_counts = load_expected_counts(args.expected_counts.resolve())
    cfp_statuses = load_cfp_status(args.cfp_dir.resolve())
    author_role_statuses = load_author_role_status(args.author_roles_dir.resolve())
    ledger, tasks, paper_audit = build_ledger(
        expected_counts,
        cfp_statuses,
        author_role_statuses,
        args.min_year,
        args.max_year,
    )
    write_csv(
        output_dir / "conference_coverage_ledger.csv",
        ledger,
        [
            "conference_key",
            "conference",
            "year",
            "family",
            "backend",
            "paper_metadata_status",
            "affiliation_status",
            "country_status",
            "role_status",
            "cfp_status",
            "raw_json_status",
            "validation_report_status",
            "author_affiliations_status",
            "affiliation_queue_status",
            "contract_version",
            "expected_papers",
            "paper_count_match_status",
            "paper_count_delta",
            "source_papers",
            "reported_papers",
            "expanded_author_rows",
            "resolved_country_rows",
            "unresolved_country_rows",
            "affiliation_mismatch_issues",
            "papers_without_affiliation_data",
            "raw_json_path",
            "validation_report_path",
            "generated_at",
        ],
    )
    write_csv(output_dir / "backfill_tasks.csv", tasks, ["task_id", "conference_key", "conference", "year", "task_type", "priority", "reason", "suggested_backend", "status"])
    write_expected_counts_template(output_dir / "expected_paper_counts_template.csv", ledger)
    write_csv(
        output_dir / "paper_completeness_audit.csv",
        paper_audit,
        [
            "conference",
            "year",
            "paper_id",
            "title",
            "source_author_count",
            "extracted_author_rows",
            "authors_with_affiliation",
            "authors_with_country",
            "has_first_author",
            "has_corresponding_author",
            "missing_affiliation_count",
            "unknown_country_count",
            "completeness_status",
            "issue_codes",
        ],
    )
    write_report(output_dir / "coverage_report.md", ledger, tasks, paper_audit)


if __name__ == "__main__":
    main()
