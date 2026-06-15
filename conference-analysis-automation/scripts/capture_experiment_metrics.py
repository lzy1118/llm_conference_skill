from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXTRACTION_DIR = ROOT / "generated-data" / "extraction"
DEFAULT_COVERAGE_DIR = ROOT / "generated-data" / "coverage"
DEFAULT_OUTPUT_DIR = ROOT / "generated-data" / "reports" / "experiment_metrics"

CRYPTO_CONFERENCES = {"ASIACRYPT", "CRYPTO", "EUROCRYPT"}
SECURITY_CONFERENCES = {"USENIX_SECURITY", "NDSS", "IEEE_S&P", "CCS"}

SUMMARY_FIELDS = [
    "snapshot_id",
    "variant_id",
    "variant_label",
    "phase",
    "acquisition_method",
    "skill_stack",
    "change_summary",
    "tags",
    "conference_years",
    "papers_count",
    "audited_papers",
    "papers_with_author_rows",
    "papers_with_full_affiliation_coverage",
    "papers_complete_unverified",
    "papers_with_quality_warnings",
    "papers_needing_review",
    "papers_without_affiliation_data",
    "papers_with_partial_affiliation_coverage",
    "papers_with_author_affiliation_match_failed",
    "expanded_author_rows",
    "classified_author_rows",
    "single_country_resolved_rows",
    "multiple_country_rows",
    "unresolved_country_rows",
    "paper_any_author_row_rate",
    "paper_full_affiliation_coverage_rate",
    "paper_complete_unverified_rate",
    "paper_quality_warning_rate",
    "author_row_known_or_multiple_rate",
    "author_row_single_country_rate",
    "author_row_unknown_rate",
    "crypto_papers",
    "crypto_single_country_resolved_rows",
    "security_papers",
    "security_single_country_resolved_rows",
    "generated_at",
    "extraction_dir",
    "coverage_dir",
    "notes",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture a comparable experiment metrics snapshot")
    parser.add_argument("--variant-id", required=True, help="Stable id, e.g. baseline_llm_v1 or security_parser_fix_v3")
    parser.add_argument("--variant-label", required=True, help="Human-readable label for tables")
    parser.add_argument("--phase", default="", help="Optional phase, e.g. baseline / logic_fix / ablation")
    parser.add_argument("--acquisition-method", default="", help="Short description of how data was acquired")
    parser.add_argument("--skill-stack", default="", help="Short description of enabled skills / tools / fallback stack")
    parser.add_argument("--change-summary", default="", help="Short summary of what changed in this variant")
    parser.add_argument("--tags", default="", help="Comma-separated tags")
    parser.add_argument("--notes", default="", help="Free-form notes")
    parser.add_argument("--extraction-dir", type=Path, default=DEFAULT_EXTRACTION_DIR)
    parser.add_argument("--coverage-dir", type=Path, default=DEFAULT_COVERAGE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def append_csv(path: Path, row: dict[str, object], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in fieldnames})


def safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def sum_int(rows: list[dict[str, Any]], key: str) -> int:
    total = 0
    for row in rows:
        try:
            total += int(float(row.get(key, 0) or 0))
        except (TypeError, ValueError):
            continue
    return total


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    reports_dir = args.extraction_dir / "output" / "by_conference"
    report_paths = sorted(reports_dir.glob("*/validation_report.json"))
    reports = [read_json(path) for path in report_paths]
    ledger_rows = read_csv_rows(args.coverage_dir / "conference_coverage_ledger.csv")
    paper_rows = read_csv_rows(args.coverage_dir / "paper_completeness_audit.csv")

    crypto_reports = [row for row in reports if str(row.get("conference", "")) in CRYPTO_CONFERENCES]
    security_reports = [row for row in reports if str(row.get("conference", "")) in SECURITY_CONFERENCES]

    audited_papers = len(paper_rows)
    papers_with_author_rows = sum(1 for row in paper_rows if int(row.get("extracted_author_rows", 0) or 0) > 0)
    papers_with_full_affiliation_coverage = sum(1 for row in paper_rows if row.get("coverage_status") == "complete_unverified")
    papers_complete_unverified = sum(1 for row in paper_rows if row.get("completeness_status") == "complete_unverified")
    papers_with_quality_warnings = sum(1 for row in paper_rows if row.get("quality_status") != "complete_unverified")
    papers_needing_review = sum(1 for row in paper_rows if row.get("completeness_status") != "complete_unverified")

    conference_years = len(reports)
    papers_count = sum_int(reports, "papers_count")
    papers_without_affiliation_data = sum_int(reports, "papers_without_affiliation_data")
    papers_with_partial_affiliation_coverage = sum_int(reports, "papers_with_partial_affiliation_coverage")
    papers_with_author_affiliation_match_failed = sum_int(reports, "papers_with_author_affiliation_match_failed")
    expanded_author_rows = sum_int(reports, "expanded_author_rows")
    classified_author_rows = sum_int(reports, "classified_author_rows")
    single_country_resolved_rows = sum_int(reports, "single_country_resolved_rows")
    multiple_country_rows = sum_int(reports, "multiple_country_rows")
    unresolved_country_rows = sum_int(reports, "unresolved_country_rows")

    snapshot_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{args.variant_id}"
    generated_at = datetime.now(timezone.utc).isoformat()

    return {
        "snapshot_id": snapshot_id,
        "variant_id": args.variant_id,
        "variant_label": args.variant_label,
        "phase": args.phase,
        "acquisition_method": args.acquisition_method,
        "skill_stack": args.skill_stack,
        "change_summary": args.change_summary,
        "tags": args.tags,
        "notes": args.notes,
        "generated_at": generated_at,
        "extraction_dir": str(args.extraction_dir),
        "coverage_dir": str(args.coverage_dir),
        "conference_years": conference_years,
        "papers_count": papers_count,
        "audited_papers": audited_papers,
        "papers_with_author_rows": papers_with_author_rows,
        "papers_with_full_affiliation_coverage": papers_with_full_affiliation_coverage,
        "papers_complete_unverified": papers_complete_unverified,
        "papers_with_quality_warnings": papers_with_quality_warnings,
        "papers_needing_review": papers_needing_review,
        "papers_without_affiliation_data": papers_without_affiliation_data,
        "papers_with_partial_affiliation_coverage": papers_with_partial_affiliation_coverage,
        "papers_with_author_affiliation_match_failed": papers_with_author_affiliation_match_failed,
        "expanded_author_rows": expanded_author_rows,
        "classified_author_rows": classified_author_rows,
        "single_country_resolved_rows": single_country_resolved_rows,
        "multiple_country_rows": multiple_country_rows,
        "unresolved_country_rows": unresolved_country_rows,
        "paper_any_author_row_rate": safe_rate(papers_with_author_rows, audited_papers),
        "paper_full_affiliation_coverage_rate": safe_rate(papers_with_full_affiliation_coverage, audited_papers),
        "paper_complete_unverified_rate": safe_rate(papers_complete_unverified, audited_papers),
        "paper_quality_warning_rate": safe_rate(papers_with_quality_warnings, audited_papers),
        "author_row_known_or_multiple_rate": safe_rate(classified_author_rows, expanded_author_rows),
        "author_row_single_country_rate": safe_rate(single_country_resolved_rows, expanded_author_rows),
        "author_row_unknown_rate": safe_rate(unresolved_country_rows, expanded_author_rows),
        "crypto_papers": sum_int(crypto_reports, "papers_count"),
        "crypto_single_country_resolved_rows": sum_int(crypto_reports, "single_country_resolved_rows"),
        "security_papers": sum_int(security_reports, "papers_count"),
        "security_single_country_resolved_rows": sum_int(security_reports, "single_country_resolved_rows"),
        "groups": {
            "crypto": {
                "conference_years": len(crypto_reports),
                "papers_count": sum_int(crypto_reports, "papers_count"),
                "expanded_author_rows": sum_int(crypto_reports, "expanded_author_rows"),
                "classified_author_rows": sum_int(crypto_reports, "classified_author_rows"),
                "single_country_resolved_rows": sum_int(crypto_reports, "single_country_resolved_rows"),
                "multiple_country_rows": sum_int(crypto_reports, "multiple_country_rows"),
                "unresolved_country_rows": sum_int(crypto_reports, "unresolved_country_rows"),
                "papers_without_affiliation_data": sum_int(crypto_reports, "papers_without_affiliation_data"),
                "papers_with_partial_affiliation_coverage": sum_int(crypto_reports, "papers_with_partial_affiliation_coverage"),
            },
            "security": {
                "conference_years": len(security_reports),
                "papers_count": sum_int(security_reports, "papers_count"),
                "expanded_author_rows": sum_int(security_reports, "expanded_author_rows"),
                "classified_author_rows": sum_int(security_reports, "classified_author_rows"),
                "single_country_resolved_rows": sum_int(security_reports, "single_country_resolved_rows"),
                "multiple_country_rows": sum_int(security_reports, "multiple_country_rows"),
                "unresolved_country_rows": sum_int(security_reports, "unresolved_country_rows"),
                "papers_without_affiliation_data": sum_int(security_reports, "papers_without_affiliation_data"),
                "papers_with_partial_affiliation_coverage": sum_int(security_reports, "papers_with_partial_affiliation_coverage"),
            },
        },
        "artifact_counts": {
            "conference_coverage_ledger_rows": len(ledger_rows),
            "paper_completeness_rows": len(paper_rows),
            "validation_report_files": len(report_paths),
        },
    }


def render_snapshot_markdown(snapshot: dict[str, Any]) -> str:
    lines = [
        f"# Experiment Snapshot: {snapshot['variant_label']}",
        "",
        f"- snapshot_id: `{snapshot['snapshot_id']}`",
        f"- variant_id: `{snapshot['variant_id']}`",
        f"- phase: `{snapshot.get('phase', '')}`",
        f"- generated_at: `{snapshot['generated_at']}`",
        f"- acquisition_method: {snapshot.get('acquisition_method', '')}",
        f"- skill_stack: {snapshot.get('skill_stack', '')}",
        f"- change_summary: {snapshot.get('change_summary', '')}",
        f"- tags: {snapshot.get('tags', '')}",
        "",
        "## Core Metrics",
        "",
        f"- conference_years: {snapshot['conference_years']}",
        f"- papers_count: {snapshot['papers_count']}",
        f"- audited_papers: {snapshot['audited_papers']}",
        f"- papers_with_author_rows: {snapshot['papers_with_author_rows']} ({snapshot['paper_any_author_row_rate']:.2%})",
        f"- papers_with_full_affiliation_coverage: {snapshot['papers_with_full_affiliation_coverage']} ({snapshot['paper_full_affiliation_coverage_rate']:.2%})",
        f"- papers_complete_unverified: {snapshot['papers_complete_unverified']} ({snapshot['paper_complete_unverified_rate']:.2%})",
        f"- papers_with_quality_warnings: {snapshot['papers_with_quality_warnings']} ({snapshot['paper_quality_warning_rate']:.2%})",
        f"- papers_without_affiliation_data: {snapshot['papers_without_affiliation_data']}",
        f"- papers_with_partial_affiliation_coverage: {snapshot['papers_with_partial_affiliation_coverage']}",
        f"- expanded_author_rows: {snapshot['expanded_author_rows']}",
        f"- classified_author_rows: {snapshot['classified_author_rows']} ({snapshot['author_row_known_or_multiple_rate']:.2%})",
        f"- single_country_resolved_rows: {snapshot['single_country_resolved_rows']} ({snapshot['author_row_single_country_rate']:.2%})",
        f"- multiple_country_rows: {snapshot['multiple_country_rows']}",
        f"- unresolved_country_rows: {snapshot['unresolved_country_rows']} ({snapshot['author_row_unknown_rate']:.2%})",
        "",
        "## Group Metrics",
        "",
        f"- crypto papers: {snapshot['groups']['crypto']['papers_count']}",
        f"- crypto single_country_resolved_rows: {snapshot['groups']['crypto']['single_country_resolved_rows']}",
        f"- security papers: {snapshot['groups']['security']['papers_count']}",
        f"- security single_country_resolved_rows: {snapshot['groups']['security']['single_country_resolved_rows']}",
    ]
    if snapshot.get("notes"):
        lines.extend(["", "## Notes", "", snapshot["notes"]])
    return "\n".join(lines) + "\n"


def ensure_registry_template(path: Path) -> None:
    if path.exists():
        return
    rows = [
        {
            "variant_id": "baseline_initial",
            "variant_label": "Initial Baseline",
            "phase": "baseline",
            "acquisition_method": "TODO: describe original acquisition path",
            "skill_stack": "TODO",
            "change_summary": "Original implementation before later parser / matching / cache fixes",
            "tags": "baseline,needs_manual_fill",
            "notes": "Fill this row after locating the original artifact snapshot or historical metrics.",
        },
        {
            "variant_id": "current_logic_plus_skills",
            "variant_label": "Current Logic + Skills",
            "phase": "improved",
            "acquisition_method": "Venue parser + fallback APIs + registry/override normalization",
            "skill_stack": "parser_fixes,name_matching,partial_gap_fill,cache_refresh,registry_rules",
            "change_summary": "Current maintained pipeline after logic and parser corrections",
            "tags": "current,comparison_target",
            "notes": "Update after each major metric-changing revision.",
        },
    ]
    write_csv(
        path,
        rows,
        ["variant_id", "variant_label", "phase", "acquisition_method", "skill_stack", "change_summary", "tags", "notes"],
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    ensure_registry_template(output_dir / "variant_registry_template.csv")
    snapshot = build_snapshot(args)

    snapshot_json_path = output_dir / "snapshots" / f"{snapshot['snapshot_id']}.json"
    snapshot_md_path = output_dir / "snapshots" / f"{snapshot['snapshot_id']}.md"
    snapshot_json_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_json_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    snapshot_md_path.write_text(render_snapshot_markdown(snapshot), encoding="utf-8")

    append_csv(output_dir / "experiment_metrics_index.csv", snapshot, SUMMARY_FIELDS)
    print(json.dumps({"snapshot_id": snapshot["snapshot_id"], "json_path": str(snapshot_json_path), "md_path": str(snapshot_md_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
