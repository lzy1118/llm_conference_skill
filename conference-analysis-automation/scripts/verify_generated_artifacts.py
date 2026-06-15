from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERATED = ROOT / "generated-data"
REPORTS = GENERATED / "reports" / "experiment_metrics"
VERSIONED = GENERATED / "versioned_data"


@dataclass
class CheckResult:
    level: str
    name: str
    detail: str


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def add(results: list[CheckResult], level: str, name: str, detail: str) -> None:
    results.append(CheckResult(level=level, name=name, detail=detail))


def check_exists(results: list[CheckResult], path: Path) -> None:
    if path.exists() and path.is_file() and path.stat().st_size > 0:
        add(results, "PASS", "exists", str(path.relative_to(ROOT)))
    else:
        add(results, "FAIL", "exists", str(path.relative_to(ROOT)))


def latest_current_snapshot() -> tuple[dict[str, str], Path]:
    index_rows = [row for row in read_csv(REPORTS / "experiment_metrics_index.csv") if row.get("variant_id") == "current_logic_plus_skills"]
    index_rows.sort(key=lambda row: row.get("generated_at", ""))
    latest = index_rows[-1]
    snapshot_path = REPORTS / "snapshots" / f"{latest['snapshot_id']}.json"
    return latest, snapshot_path


def verify_core_files(results: list[CheckResult]) -> None:
    for path in [
        REPORTS / "fullbatch_version_comparison.md",
        REPORTS / "normalized_layer_comparison.md",
        REPORTS / "coverage_audit_evolution.md",
        GENERATED / "reports" / "data_generation_status_2026_06_06.md",
        REPORTS / "fullbatch_version_comparison_overall.csv",
        REPORTS / "fullbatch_version_comparison_by_conference.csv",
        REPORTS / "fullbatch_snapshot_evolution.csv",
        VERSIONED / "version_manifest.csv",
        VERSIONED / "current_results" / "INDEX.md",
        VERSIONED / "base_data" / "INDEX.md",
        VERSIONED / "historical_archive" / "INDEX.md",
        VERSIONED / "run_logs" / "INDEX.md",
    ]:
        check_exists(results, path)

    legacy_nested = GENERATED / "normalized" / "normalized"
    add(
        results,
        "PASS" if not legacy_nested.exists() else "FAIL",
        "normalized:no_nested_legacy_snapshot",
        f"exists={legacy_nested.exists()} path={legacy_nested.relative_to(ROOT)}",
    )


def verify_overall_metrics(results: list[CheckResult]) -> None:
    overall_rows = {row["metric"]: row for row in read_csv(REPORTS / "fullbatch_version_comparison_overall.csv")}
    latest_row, snapshot_path = latest_current_snapshot()
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    normalization = json.loads((GENERATED / "normalized" / "normalization_report.json").read_text(encoding="utf-8"))

    expected_pairs = [
        ("extracted_papers", str(snapshot["papers_count"])),
        ("normalized_papers", str(normalization["paper_count"])),
        ("normalized_author_affiliation_rows", str(normalization["normalized_rows"])),
        ("unique_institutions", str(normalization["institution_count"])),
        ("unknown_country_rows", str(normalization["rows_with_unknown_country"])),
        ("duplicate_row_keys_skipped", str(normalization["duplicate_row_keys_skipped"])),
    ]
    for metric, expected in expected_pairs:
        actual = overall_rows.get(metric, {}).get("current_value", "")
        level = "PASS" if actual == expected else "FAIL"
        add(results, level, f"overall:{metric}", f"expected={expected} actual={actual}")

    coverage_value = overall_rows.get("conference_year_coverage", {}).get("current_value", "")
    expected_coverage = f"{snapshot['conference_years']}/{snapshot['conference_years']}"
    add(
        results,
        "PASS" if coverage_value == expected_coverage else "FAIL",
        "overall:conference_year_coverage",
        f"expected={expected_coverage} actual={coverage_value}",
    )


def verify_snapshot_evolution(results: list[CheckResult]) -> None:
    rows = read_csv(REPORTS / "fullbatch_snapshot_evolution.csv")
    if not rows:
        add(results, "FAIL", "snapshot_evolution", "no rows")
        return
    latest_index_row, _ = latest_current_snapshot()
    latest_snapshot_id = latest_index_row["snapshot_id"]
    ids = [row["snapshot_id"] for row in rows]
    add(results, "PASS" if latest_snapshot_id == ids[-1] else "FAIL", "snapshot_evolution:latest_id", f"expected={latest_snapshot_id} actual={ids[-1]}")

    latest = rows[-1]
    expected = {
        "papers_count": "7426",
        "audited_papers": "7426",
        "papers_with_author_rows": "7183",
        "papers_with_full_affiliation_coverage": "6023",
        "papers_complete_unverified": "6023",
    }
    for key, expected_value in expected.items():
        actual = latest.get(key, "")
        add(results, "PASS" if actual == expected_value else "FAIL", f"snapshot_evolution:{key}", f"expected={expected_value} actual={actual}")


def verify_versioned_manifest(results: list[CheckResult]) -> None:
    manifest_rows = read_csv(VERSIONED / "version_manifest.csv")
    if not manifest_rows:
        add(results, "FAIL", "version_manifest", "empty manifest")
        return

    missing_targets = [row["copied_to"] for row in manifest_rows if not Path(row["copied_to"]).exists()]
    add(results, "PASS" if not missing_targets else "FAIL", "version_manifest:targets", f"missing={len(missing_targets)}")

    bucket_counts = Counter(row["bucket"] for row in manifest_rows)
    add(results, "PASS", "version_manifest:buckets", str(dict(bucket_counts)))

    duplicated_sources = sum(1 for _, count in Counter(row["source"] for row in manifest_rows).items() if count > 1)
    add(results, "PASS" if duplicated_sources == 0 else "WARN", "version_manifest:duplicate_sources", f"duplicate_sources={duplicated_sources}")


def verify_versioned_current_matches_source(results: list[CheckResult]) -> None:
    pairs = [
        (
            GENERATED / "reports" / "experiment_metrics" / "normalized_layer_comparison.md",
            VERSIONED / "current_results" / "reports" / "experiment_metrics" / "normalized_layer_comparison.md",
        ),
        (
            GENERATED / "reports" / "experiment_metrics" / "coverage_audit_evolution.md",
            VERSIONED / "current_results" / "reports" / "experiment_metrics" / "coverage_audit_evolution.md",
        ),
        (
            GENERATED / "reports" / "experiment_metrics" / "fullbatch_version_comparison.md",
            VERSIONED / "current_results" / "reports" / "experiment_metrics" / "fullbatch_version_comparison.md",
        ),
        (
            GENERATED / "coverage" / "paper_completeness_audit.csv",
            VERSIONED / "base_data" / "coverage" / "paper_completeness_audit.csv",
        ),
    ]
    for source, copied in pairs:
        same = source.exists() and copied.exists() and source.read_bytes() == copied.read_bytes()
        add(results, "PASS" if same else "FAIL", "versioned_match", f"{source.relative_to(ROOT)} == {copied.relative_to(ROOT)}")


def main() -> int:
    results: list[CheckResult] = []
    verify_core_files(results)
    verify_overall_metrics(results)
    verify_snapshot_evolution(results)
    verify_versioned_manifest(results)
    verify_versioned_current_matches_source(results)

    for result in results:
        print(f"[{result.level}] {result.name}: {result.detail}")

    fail_count = sum(1 for result in results if result.level == "FAIL")
    warn_count = sum(1 for result in results if result.level == "WARN")
    pass_count = sum(1 for result in results if result.level == "PASS")
    print(f"\nSummary: PASS={pass_count} WARN={warn_count} FAIL={fail_count}")
    return 1 if fail_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
