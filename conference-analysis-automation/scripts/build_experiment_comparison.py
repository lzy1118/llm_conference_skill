from __future__ import annotations

import argparse
import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_DIR = ROOT / "generated-data" / "reports" / "experiment_metrics"

INDEX_FIELDS = [
    "snapshot_id",
    "variant_id",
    "variant_label",
    "phase",
    "generated_at",
    "papers_count",
    "audited_papers",
    "papers_with_author_rows",
    "papers_with_full_affiliation_coverage",
    "papers_complete_unverified",
    "papers_without_affiliation_data",
    "papers_with_partial_affiliation_coverage",
    "expanded_author_rows",
    "classified_author_rows",
    "single_country_resolved_rows",
    "multiple_country_rows",
    "unresolved_country_rows",
    "paper_any_author_row_rate",
    "paper_full_affiliation_coverage_rate",
    "paper_complete_unverified_rate",
    "author_row_known_or_multiple_rate",
    "author_row_single_country_rate",
    "author_row_unknown_rate",
]

DELTA_FIELDS = [
    "papers_with_full_affiliation_coverage",
    "papers_complete_unverified",
    "papers_without_affiliation_data",
    "papers_with_partial_affiliation_coverage",
    "single_country_resolved_rows",
    "unresolved_country_rows",
    "paper_full_affiliation_coverage_rate",
    "paper_complete_unverified_rate",
    "author_row_single_country_rate",
    "author_row_unknown_rate",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a comparison table for experiment metric snapshots")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--variant-id", action="append", default=[], help="Limit to specific variant ids")
    parser.add_argument("--baseline-variant-id", default="", help="Variant id to use as delta baseline")
    return parser.parse_args(argv)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def latest_by_variant(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    latest: dict[str, dict[str, str]] = {}
    for row in sorted(rows, key=lambda item: item.get("generated_at", "")):
        latest[row.get("variant_id", "")] = row
    return list(latest.values())


def to_float(row: dict[str, str], key: str) -> float:
    try:
        return float(row.get(key, "") or 0)
    except ValueError:
        return 0.0


def render_markdown(rows: list[dict[str, str]], baseline_row: dict[str, str] | None) -> str:
    lines = [
        "# Experiment Comparison",
        "",
        "## Snapshot Table",
        "",
        "| variant_id | label | phase | papers | full_aff_cov_rate | complete_rate | single_country_rate | unknown_rate | generated_at |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            f"{row.get('variant_id', '')} | "
            f"{row.get('variant_label', '')} | "
            f"{row.get('phase', '')} | "
            f"{row.get('papers_count', '')} | "
            f"{to_float(row, 'paper_full_affiliation_coverage_rate'):.2%} | "
            f"{to_float(row, 'paper_complete_unverified_rate'):.2%} | "
            f"{to_float(row, 'author_row_single_country_rate'):.2%} | "
            f"{to_float(row, 'author_row_unknown_rate'):.2%} | "
            f"{row.get('generated_at', '')} |"
        )

    if baseline_row is not None:
        lines.extend(
            [
                "",
                f"## Delta vs `{baseline_row.get('variant_id', '')}`",
                "",
                "| variant_id | metric | delta |",
                "| --- | --- | ---: |",
            ]
        )
        for row in rows:
            if row.get("variant_id") == baseline_row.get("variant_id"):
                continue
            for field in DELTA_FIELDS:
                delta = to_float(row, field) - to_float(baseline_row, field)
                lines.append(f"| {row.get('variant_id', '')} | {field} | {delta:.6f} |")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    index_path = args.input_dir / "experiment_metrics_index.csv"
    rows = latest_by_variant(read_csv_rows(index_path))
    if args.variant_id:
        selected = set(args.variant_id)
        rows = [row for row in rows if row.get("variant_id", "") in selected]
    rows = sorted(rows, key=lambda row: (row.get("phase", ""), row.get("generated_at", ""), row.get("variant_id", "")))

    baseline_row = None
    if args.baseline_variant_id:
        baseline_row = next((row for row in rows if row.get("variant_id") == args.baseline_variant_id), None)
    elif rows:
        baseline_row = rows[0]

    comparison_md = render_markdown(rows, baseline_row)
    md_path = args.input_dir / "experiment_comparison.md"
    csv_path = args.input_dir / "experiment_comparison.csv"
    md_path.write_text(comparison_md, encoding="utf-8")

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=INDEX_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(str(md_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
