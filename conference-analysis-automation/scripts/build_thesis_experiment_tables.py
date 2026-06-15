from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_METRICS_DIR = ROOT / "generated-data" / "reports" / "experiment_metrics"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build thesis-ready experiment comparison tables")
    parser.add_argument("--metrics-dir", type=Path, default=DEFAULT_METRICS_DIR)
    parser.add_argument("--current-variant-id", default="current_logic_plus_skills")
    return parser.parse_args(argv)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def to_int(value: str) -> int:
    try:
        return int(float(value or 0))
    except ValueError:
        return 0


def to_float(value: str) -> float:
    try:
        return float(value or 0)
    except ValueError:
        return 0.0


def safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def latest_by_variant(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    latest: dict[str, dict[str, str]] = {}
    for row in sorted(rows, key=lambda item: item.get("generated_at", "")):
        latest[row.get("variant_id", "")] = row
    return latest


def aggregate_current_by_conference(current: dict[str, str]) -> list[dict[str, object]]:
    extraction_dir = Path(current["extraction_dir"])
    coverage_dir = Path(current["coverage_dir"])

    report_rows = []
    for path in sorted((extraction_dir / "output" / "by_conference").glob("*/validation_report.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        conference_key = path.parent.name
        if row.get("single_country_resolved_rows") is None or row.get("multiple_country_rows") is None:
            expanded_path = extraction_dir / "interim" / "by_conference" / conference_key / "author_affiliations_expanded.csv"
            if expanded_path.exists():
                expanded_rows = read_csv_rows(expanded_path)
                row["single_country_resolved_rows"] = sum(
                    1 for expanded in expanded_rows if expanded.get("country") not in {"", "Unknown", "Multiple"}
                )
                row["multiple_country_rows"] = sum(
                    1 for expanded in expanded_rows if expanded.get("country") == "Multiple"
                )
                row["unresolved_country_rows"] = sum(
                    1 for expanded in expanded_rows if expanded.get("country") in {"", "Unknown"}
                )
        report_rows.append(row)

    paper_rows = read_csv_rows(coverage_dir / "paper_completeness_audit.csv")

    paper_agg: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "audited_papers": 0,
            "papers_with_author_rows": 0,
            "papers_with_full_affiliation_coverage": 0,
            "papers_complete_unverified": 0,
        }
    )
    for row in paper_rows:
        conference = row.get("conference", "")
        paper_agg[conference]["audited_papers"] += 1
        if int(row.get("extracted_author_rows", 0) or 0) > 0:
            paper_agg[conference]["papers_with_author_rows"] += 1
        if row.get("coverage_status") == "complete_unverified":
            paper_agg[conference]["papers_with_full_affiliation_coverage"] += 1
        if row.get("completeness_status") == "complete_unverified":
            paper_agg[conference]["papers_complete_unverified"] += 1

    report_agg: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "conference_years": 0,
            "papers_count": 0,
            "expanded_author_rows": 0,
            "classified_author_rows": 0,
            "single_country_resolved_rows": 0,
            "multiple_country_rows": 0,
            "unresolved_country_rows": 0,
            "papers_without_affiliation_data": 0,
            "papers_with_partial_affiliation_coverage": 0,
        }
    )
    for row in report_rows:
        conference = str(row.get("conference", ""))
        agg = report_agg[conference]
        agg["conference_years"] += 1
        for key in [
            "papers_count",
            "expanded_author_rows",
            "classified_author_rows",
            "single_country_resolved_rows",
            "multiple_country_rows",
            "unresolved_country_rows",
            "papers_without_affiliation_data",
            "papers_with_partial_affiliation_coverage",
        ]:
            agg[key] += int(row.get(key, 0) or 0)

    combined = []
    for conference in sorted(report_agg):
        row = {"conference": conference, **report_agg[conference], **paper_agg.get(conference, {})}
        row["paper_full_affiliation_coverage_rate"] = safe_rate(
            row.get("papers_with_full_affiliation_coverage", 0),
            row.get("audited_papers", 0),
        )
        row["paper_complete_unverified_rate"] = safe_rate(
            row.get("papers_complete_unverified", 0),
            row.get("audited_papers", 0),
        )
        row["author_row_single_country_rate"] = safe_rate(
            row.get("single_country_resolved_rows", 0),
            row.get("expanded_author_rows", 0),
        )
        row["author_row_unknown_rate"] = safe_rate(
            row.get("unresolved_country_rows", 0),
            row.get("expanded_author_rows", 0),
        )
        combined.append(row)
    return combined


def build_markdown(
    current: dict[str, str],
    historical: list[dict[str, str]],
    current_by_conference: list[dict[str, object]],
) -> str:
    lines = [
        "# Thesis Experiment Tables",
        "",
        "## Table 1. Current Full-Batch Snapshot",
        "",
        "| variant | conference_years | papers | full_affiliation_coverage | complete_unverified | single_country_rows | unresolved_rows |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        (
            "| "
            f"{current.get('variant_label', '')} | "
            f"{current.get('conference_years', '')} | "
            f"{current.get('papers_count', '')} | "
            f"{to_int(current.get('papers_with_full_affiliation_coverage', '0'))} ({to_float(current.get('paper_full_affiliation_coverage_rate', '0')):.2%}) | "
            f"{to_int(current.get('papers_complete_unverified', '0'))} ({to_float(current.get('paper_complete_unverified_rate', '0')):.2%}) | "
            f"{current.get('single_country_resolved_rows', '')} ({to_float(current.get('author_row_single_country_rate', '0')):.2%}) | "
            f"{current.get('unresolved_country_rows', '')} ({to_float(current.get('author_row_unknown_rate', '0')):.2%}) |"
        ),
        "",
        "## Table 1B. Current Seven-Conference Breakdown",
        "",
        "| conference | years | papers | full_aff_cov | complete_unverified | single_country_rate | unresolved_rows | no_affiliation | partial_aff_cov |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for row in current_by_conference:
        lines.append(
            "| "
            f"{row.get('conference', '')} | "
            f"{row.get('conference_years', 0)} | "
            f"{row.get('papers_count', 0)} | "
            f"{row.get('papers_with_full_affiliation_coverage', 0)} ({row.get('paper_full_affiliation_coverage_rate', 0.0):.2%}) | "
            f"{row.get('papers_complete_unverified', 0)} ({row.get('paper_complete_unverified_rate', 0.0):.2%}) | "
            f"{row.get('single_country_resolved_rows', 0)} / {row.get('expanded_author_rows', 0)} ({row.get('author_row_single_country_rate', 0.0):.2%}) | "
            f"{row.get('unresolved_country_rows', 0)} ({row.get('author_row_unknown_rate', 0.0):.2%}) | "
            f"{row.get('papers_without_affiliation_data', 0)} | "
            f"{row.get('papers_with_partial_affiliation_coverage', 0)} |"
        )

    lines.extend(
        [
            "",
            "## Table 2. Documented Historical Method Comparisons",
            "",
            "| scope | variant | conference_key | papers | expanded_rows | classified_rows | unresolved_rows | unresolved_rate | source |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )

    for row in historical:
        unresolved_rate = row.get("unresolved_rate", "")
        unresolved_rate_cell = f"{to_float(unresolved_rate):.2%}" if unresolved_rate else ""
        lines.append(
            "| "
            f"{row.get('scope', '')} | "
            f"{row.get('variant_label', '')} | "
            f"{row.get('conference_key', '')} | "
            f"{row.get('papers_count', '')} | "
            f"{row.get('expanded_author_rows', '')} | "
            f"{row.get('classified_author_rows', '')} | "
            f"{row.get('unresolved_country_rows', '')} | "
            f"{unresolved_rate_cell} | "
            f"{Path(row.get('source_file', '')).name} |"
        )

    usenix_rows = [row for row in historical if row.get("variant_id", "").startswith("usenix2020_")]
    top3_rows = [row for row in historical if row.get("variant_id", "").startswith("top3_crypto_")]
    ccs_rows = [row for row in historical if row.get("variant_id") == "ccs_openalex_doi_ablation"]

    lines.extend(
        [
            "",
            "## Table 3. USENIX 2020 Method A/B/C Comparison",
            "",
            "| method | classified_rows | unresolved_rows | unresolved_rate |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for row in usenix_rows:
        lines.append(
            "| "
            f"{row.get('variant_label', '')} | "
            f"{row.get('classified_author_rows', '')} | "
            f"{row.get('unresolved_country_rows', '')} | "
            f"{to_float(row.get('unresolved_rate', '0')):.2%} |"
        )

    lines.extend(
        [
            "",
            "## Table 4. Top3 Crypto Parser Compatibility Comparison",
            "",
            "| stage | papers | expanded_rows | classified_rows | unresolved_rows | mismatch_issues |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in top3_rows:
        lines.append(
            "| "
            f"{row.get('variant_label', '')} | "
            f"{row.get('papers_count', '')} | "
            f"{row.get('expanded_author_rows', '')} | "
            f"{row.get('classified_author_rows', '')} | "
            f"{row.get('unresolved_country_rows', '')} | "
            f"{row.get('affiliation_mismatch_issues', '')} |"
        )

    lines.extend(
        [
            "",
            "## Table 5. CCS OpenAlex DOI Ablation",
            "",
            "| conference_key | papers | papers_with_author_rows | papers_without_affiliation_data | note |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
    )
    for row in ccs_rows:
        lines.append(
            "| "
            f"{row.get('conference_key', '')} | "
            f"{row.get('papers_count', '')} | "
            f"{row.get('papers_with_author_rows', '')} | "
            f"{row.get('papers_without_affiliation_data', '')} | "
            f"{row.get('notes', '')} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation Notes",
            "",
            "- Table 1 is the current full-batch snapshot and is the best candidate for main-text aggregate reporting.",
            "- Table 1B expands the current snapshot into seven conference-level results, which is the right level when discussing venue differences.",
            "- Tables 2-5 are documented historical or local ablation observations recovered from `duringtest/` notes.",
            "- Historical tables should be described as documented comparisons unless the original full artifact directories are recovered and recaptured as formal snapshots.",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    metrics_dir = args.metrics_dir
    latest = latest_by_variant(read_csv_rows(metrics_dir / "experiment_metrics_index.csv"))
    current = latest[args.current_variant_id]
    historical = read_csv_rows(metrics_dir / "documented_historical_observations.csv")
    current_by_conference = aggregate_current_by_conference(current)

    md_path = metrics_dir / "thesis_experiment_tables.md"
    md_path.write_text(build_markdown(current, historical, current_by_conference), encoding="utf-8")
    print(str(md_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
