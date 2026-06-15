from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERATED = ROOT / "generated-data"
REPORTS_DIR = GENERATED / "reports" / "experiment_metrics"

HISTORICAL_SUMMARY = GENERATED / "versioned_data" / "historical_archive" / "reports" / "thesis_analysis" / "thesis_metrics" / "thesis_metrics_summary.json"
HISTORICAL_CONFERENCE = GENERATED / "versioned_data" / "historical_archive" / "reports" / "thesis_analysis" / "thesis_metrics" / "conference_comparison.csv"
CURRENT_FACTS = GENERATED / "normalized" / "author_affiliation_facts.csv"
CURRENT_PAPERS = GENERATED / "normalized" / "paper_facts.csv"
CURRENT_NORMALIZATION_REPORT = GENERATED / "normalized" / "normalization_report.json"
INDEX_PATH = GENERATED / "reports" / "experiment_metrics" / "experiment_metrics_index.csv"


CONFERENCE_DISPLAY_TO_KEY = {
    "Asiacrypt": "ASIACRYPT",
    "Crypto": "CRYPTO",
    "Eurocrypt": "EUROCRYPT",
    "USENIX Security": "USENIX_SECURITY",
    "NDSS": "NDSS",
    "IEEE S&P": "IEEE_S&P",
    "ACM CCS": "CCS",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def fmt_pct(value: float) -> str:
    return f"{value:.2%}"


def fmt_delta(value: float | int) -> str:
    if isinstance(value, int):
        return f"{value:+d}"
    return f"{value:+.4f}"


def load_snapshot_rows() -> list[dict[str, str]]:
    rows = [row for row in read_csv(INDEX_PATH) if row.get("variant_id") == "current_logic_plus_skills"]
    rows.sort(key=lambda row: row.get("generated_at", ""))
    return rows


def load_current_snapshot() -> dict[str, object]:
    rows = load_snapshot_rows()
    if not rows:
        raise FileNotFoundError(f"No current_logic_plus_skills rows found in {INDEX_PATH}")
    snapshot_id = rows[-1]["snapshot_id"]
    snapshot_path = REPORTS_DIR / "snapshots" / f"{snapshot_id}.json"
    return json.loads(snapshot_path.read_text(encoding="utf-8"))


def build_current_normalized_metrics(current_snapshot: dict[str, object]) -> tuple[dict[str, int], dict[str, dict[str, float | int]]]:
    facts = read_csv(CURRENT_FACTS)
    papers = read_csv(CURRENT_PAPERS)
    normalization = json.loads(CURRENT_NORMALIZATION_REPORT.read_text(encoding="utf-8"))
    conference_year_pairs = {
        (str(row.get("conference", "")).strip(), str(row.get("year", "")).strip())
        for row in papers
        if str(row.get("conference", "")).strip() and str(row.get("year", "")).strip()
    }
    conference_count = len({conference for conference, _ in conference_year_pairs})

    unique_authors = {row["author_key"] for row in facts if row.get("author_key")}
    unique_institutions = {row["institution_key"] for row in facts if row.get("institution_key")}
    unknown_rows = sum(1 for row in facts if (row.get("country") or "") in {"", "Unknown"})

    overall = {
        "conference_year_coverage_num": len(conference_year_pairs),
        "conference_year_coverage_den": int(current_snapshot.get("conference_years", 0) or 0),
        "extracted_papers": int(current_snapshot.get("papers_count", 0) or 0),
        "normalized_papers": len(papers),
        "normalized_author_affiliation_rows": len(facts),
        "unique_authors": len(unique_authors),
        "unique_institutions": len(unique_institutions),
        "unknown_country_rows": unknown_rows,
        "duplicate_row_keys_skipped": int(normalization.get("duplicate_row_keys_skipped", 0) or 0),
    }

    by_conf: dict[str, dict[str, float | int | set[str]]] = defaultdict(
        lambda: {
            "papers": 0,
            "author_affiliation_rows": 0,
            "authors": set(),
            "institutions": set(),
            "unknown_country_rows": 0,
            "years": set(),
        }
    )
    for row in papers:
        entry = by_conf[row["conference"]]
        entry["papers"] += 1
        if row.get("year"):
            entry["years"].add(int(row["year"]))
    for row in facts:
        entry = by_conf[row["conference"]]
        entry["author_affiliation_rows"] += 1
        if row.get("author_key"):
            entry["authors"].add(row["author_key"])
        if row.get("institution_key"):
            entry["institutions"].add(row["institution_key"])
        if (row.get("country") or "") in {"", "Unknown"}:
            entry["unknown_country_rows"] += 1

    current_conference: dict[str, dict[str, float | int]] = {}
    for conf, row in by_conf.items():
        author_rows = int(row["author_affiliation_rows"])
        unknown = int(row["unknown_country_rows"])
        years = sorted(int(year) for year in row["years"])
        current_conference[conf] = {
            "papers": int(row["papers"]),
            "author_affiliation_rows": author_rows,
            "authors": len(row["authors"]),
            "institutions": len(row["institutions"]),
            "unknown_country_rows": unknown,
            "unknown_rate": unknown / author_rows if author_rows else 0.0,
            "year_min": years[0] if years else 0,
            "year_max": years[-1] if years else 0,
        }
    return overall, current_conference


def load_historical_metrics() -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    summary = json.loads(HISTORICAL_SUMMARY.read_text(encoding="utf-8"))["pipeline_summary"]
    conference_rows = read_csv(HISTORICAL_CONFERENCE)
    by_conf = {
        CONFERENCE_DISPLAY_TO_KEY[row["conference"]]: row
        for row in conference_rows
        if row["conference"] in CONFERENCE_DISPLAY_TO_KEY
    }
    return summary, by_conf


def build_overall_rows(historical: dict[str, str], current: dict[str, int]) -> list[dict[str, object]]:
    hist_coverage = historical.get("conference_year_coverage", "0/0")
    hist_cov_num, hist_cov_den = [int(part) for part in hist_coverage.split("/", 1)]
    rows = [
        {
            "metric": "conference_year_coverage",
            "historical_value": hist_coverage,
            "current_value": f"{current['conference_year_coverage_num']}/{current['conference_year_coverage_den']}",
            "delta": f"{current['conference_year_coverage_num'] - hist_cov_num:+d}/{current['conference_year_coverage_den'] - hist_cov_den:+d}",
            "note": "seven-conference 2020-2025 scope",
        },
    ]
    metric_keys = [
        "extracted_papers",
        "normalized_papers",
        "normalized_author_affiliation_rows",
        "unique_authors",
        "unique_institutions",
        "unknown_country_rows",
        "duplicate_row_keys_skipped",
    ]
    for key in metric_keys:
        hist_value = int(historical.get(key, "0") or 0)
        cur_value = int(current.get(key, 0) or 0)
        rows.append(
            {
                "metric": key,
                "historical_value": hist_value,
                "current_value": cur_value,
                "delta": cur_value - hist_value,
                "note": "",
            }
        )
    return rows


def build_conference_rows(
    historical: dict[str, dict[str, str]], current: dict[str, dict[str, float | int]]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for conf in ["ASIACRYPT", "CRYPTO", "EUROCRYPT", "USENIX_SECURITY", "NDSS", "IEEE_S&P", "CCS"]:
        hist = historical[conf]
        cur = current[conf]
        rows.append(
            {
                "conference": conf,
                "historical_papers": int(hist["papers"]),
                "current_papers": int(cur["papers"]),
                "delta_papers": int(cur["papers"]) - int(hist["papers"]),
                "historical_author_affiliation_rows": int(hist["author_affiliation_rows"]),
                "current_author_affiliation_rows": int(cur["author_affiliation_rows"]),
                "delta_author_affiliation_rows": int(cur["author_affiliation_rows"]) - int(hist["author_affiliation_rows"]),
                "historical_authors": int(hist["authors"]),
                "current_authors": int(cur["authors"]),
                "delta_authors": int(cur["authors"]) - int(hist["authors"]),
                "historical_institutions": int(hist["institutions"]),
                "current_institutions": int(cur["institutions"]),
                "delta_institutions": int(cur["institutions"]) - int(hist["institutions"]),
                "historical_unknown_country_rows": int(hist["unknown_country_rows"]),
                "current_unknown_country_rows": int(cur["unknown_country_rows"]),
                "delta_unknown_country_rows": int(cur["unknown_country_rows"]) - int(hist["unknown_country_rows"]),
                "historical_unknown_rate": float(hist["unknown_rate"]),
                "current_unknown_rate": float(cur["unknown_rate"]),
                "delta_unknown_rate": float(cur["unknown_rate"]) - float(hist["unknown_rate"]),
            }
        )
    return rows


def build_snapshot_rows_table(snapshot_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    fields = [
        "snapshot_id",
        "generated_at",
        "papers_count",
        "audited_papers",
        "papers_with_author_rows",
        "papers_with_full_affiliation_coverage",
        "papers_complete_unverified",
        "paper_any_author_row_rate",
        "paper_full_affiliation_coverage_rate",
        "paper_complete_unverified_rate",
    ]
    return [{field: row.get(field, "") for field in fields} for row in snapshot_rows]


def render_fullbatch_markdown(
    overall_rows: list[dict[str, object]],
    conference_rows: list[dict[str, object]],
    snapshot_rows: list[dict[str, object]],
) -> str:
    lines = [
        "# Full-Batch Version Comparison",
        "",
        "## Table 1. Historical Full-Batch Output vs Current Normalized Output",
        "",
        "| metric | historical | current | delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in overall_rows:
        lines.append(
            f"| {row['metric']} | {row['historical_value']} | {row['current_value']} | {row['delta']} |"
        )

    lines.extend(
        [
            "",
            "## Table 2. Seven-Conference Historical vs Current Normalized Comparison",
            "",
            "| conference | papers | rows | authors | institutions | unknown_rows | unknown_rate |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in conference_rows:
        lines.append(
            "| "
            f"{row['conference']} | "
            f"{row['historical_papers']} -> {row['current_papers']} ({fmt_delta(int(row['delta_papers']))}) | "
            f"{row['historical_author_affiliation_rows']} -> {row['current_author_affiliation_rows']} ({fmt_delta(int(row['delta_author_affiliation_rows']))}) | "
            f"{row['historical_authors']} -> {row['current_authors']} ({fmt_delta(int(row['delta_authors']))}) | "
            f"{row['historical_institutions']} -> {row['current_institutions']} ({fmt_delta(int(row['delta_institutions']))}) | "
            f"{row['historical_unknown_country_rows']} -> {row['current_unknown_country_rows']} ({fmt_delta(int(row['delta_unknown_country_rows']))}) | "
            f"{fmt_pct(float(row['historical_unknown_rate']))} -> {fmt_pct(float(row['current_unknown_rate']))} ({fmt_delta(float(row['delta_unknown_rate']))}) |"
        )

    lines.extend(
        [
            "",
            "## Table 3. Snapshot Evolution for Paper-Level Coverage Metrics",
            "",
            "| snapshot_id | papers | author_rows | full_aff_cov | complete_unverified | any_author_row_rate | full_aff_cov_rate | complete_rate |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in snapshot_rows:
        lines.append(
            "| "
            f"{row['snapshot_id']} | "
            f"{row['papers_count']} | "
            f"{row['papers_with_author_rows']} | "
            f"{row['papers_with_full_affiliation_coverage']} | "
            f"{row['papers_complete_unverified']} | "
            f"{fmt_pct(float(row['paper_any_author_row_rate'] or 0))} | "
            f"{fmt_pct(float(row['paper_full_affiliation_coverage_rate'] or 0))} | "
            f"{fmt_pct(float(row['paper_complete_unverified_rate'] or 0))} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Historical full-batch normalized outputs and current normalized outputs are effectively stable at the global and conference level.",
            "- The meaningful recent change appears in paper-level coverage metrics, where the latest snapshot improves over earlier snapshots after the coverage-layer paper-id alignment fix.",
            "- This means the strongest main-text comparison is: normalized analysis layer remained stable, while coverage auditing became more accurate and complete.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_normalized_layer_markdown(
    overall_rows: list[dict[str, object]],
    conference_rows: list[dict[str, object]],
) -> str:
    lines = [
        "# Normalized Layer Comparison",
        "",
        "## Table 1. Historical vs Current Normalized Layer",
        "",
        "| metric | historical | current | delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in overall_rows:
        lines.append(
            f"| {row['metric']} | {row['historical_value']} | {row['current_value']} | {row['delta']} |"
        )

    lines.extend(
        [
            "",
            "## Table 2. Seven-Conference Normalized Layer Comparison",
            "",
            "| conference | papers | rows | authors | institutions | unknown_rows | unknown_rate |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in conference_rows:
        lines.append(
            "| "
            f"{row['conference']} | "
            f"{row['historical_papers']} -> {row['current_papers']} ({fmt_delta(int(row['delta_papers']))}) | "
            f"{row['historical_author_affiliation_rows']} -> {row['current_author_affiliation_rows']} ({fmt_delta(int(row['delta_author_affiliation_rows']))}) | "
            f"{row['historical_authors']} -> {row['current_authors']} ({fmt_delta(int(row['delta_authors']))}) | "
            f"{row['historical_institutions']} -> {row['current_institutions']} ({fmt_delta(int(row['delta_institutions']))}) | "
            f"{row['historical_unknown_country_rows']} -> {row['current_unknown_country_rows']} ({fmt_delta(int(row['delta_unknown_country_rows']))}) | "
            f"{fmt_pct(float(row['historical_unknown_rate']))} -> {fmt_pct(float(row['current_unknown_rate']))} ({fmt_delta(float(row['delta_unknown_rate']))}) |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- The normalized analysis layer is stable between the historical full-batch output and the current output.",
            "- This supports treating the normalized layer as the consistent backbone for downstream analysis.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_coverage_evolution_markdown(snapshot_rows: list[dict[str, object]]) -> str:
    lines = [
        "# Coverage Audit Evolution",
        "",
        "## Table 1. Snapshot Evolution for Paper-Level Coverage Metrics",
        "",
        "| snapshot_id | papers | author_rows | full_aff_cov | complete_unverified | any_author_row_rate | full_aff_cov_rate | complete_rate |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in snapshot_rows:
        lines.append(
            "| "
            f"{row['snapshot_id']} | "
            f"{row['papers_count']} | "
            f"{row['papers_with_author_rows']} | "
            f"{row['papers_with_full_affiliation_coverage']} | "
            f"{row['papers_complete_unverified']} | "
            f"{fmt_pct(float(row['paper_any_author_row_rate'] or 0))} | "
            f"{fmt_pct(float(row['paper_full_affiliation_coverage_rate'] or 0))} | "
            f"{fmt_pct(float(row['paper_complete_unverified_rate'] or 0))} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- The recent measurable improvement comes from the paper-level coverage audit layer.",
            "- The latest snapshot improves paper-to-author-row linkage and therefore raises full affiliation coverage and complete_unverified counts.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    historical_overall, historical_conference = load_historical_metrics()
    snapshot_rows = load_snapshot_rows()
    current_snapshot = load_current_snapshot()
    current_overall, current_conference = build_current_normalized_metrics(current_snapshot)

    overall_rows = build_overall_rows(historical_overall, current_overall)
    conference_rows = build_conference_rows(historical_conference, current_conference)
    snapshot_table_rows = build_snapshot_rows_table(snapshot_rows)

    write_csv(
        REPORTS_DIR / "fullbatch_version_comparison_overall.csv",
        overall_rows,
        ["metric", "historical_value", "current_value", "delta", "note"],
    )
    write_csv(
        REPORTS_DIR / "fullbatch_version_comparison_by_conference.csv",
        conference_rows,
        [
            "conference",
            "historical_papers",
            "current_papers",
            "delta_papers",
            "historical_author_affiliation_rows",
            "current_author_affiliation_rows",
            "delta_author_affiliation_rows",
            "historical_authors",
            "current_authors",
            "delta_authors",
            "historical_institutions",
            "current_institutions",
            "delta_institutions",
            "historical_unknown_country_rows",
            "current_unknown_country_rows",
            "delta_unknown_country_rows",
            "historical_unknown_rate",
            "current_unknown_rate",
            "delta_unknown_rate",
        ],
    )
    write_csv(
        REPORTS_DIR / "fullbatch_snapshot_evolution.csv",
        snapshot_table_rows,
        [
            "snapshot_id",
            "generated_at",
            "papers_count",
            "audited_papers",
            "papers_with_author_rows",
            "papers_with_full_affiliation_coverage",
            "papers_complete_unverified",
            "paper_any_author_row_rate",
            "paper_full_affiliation_coverage_rate",
            "paper_complete_unverified_rate",
        ],
    )
    md = render_fullbatch_markdown(overall_rows, conference_rows, snapshot_table_rows)
    md_path = REPORTS_DIR / "fullbatch_version_comparison.md"
    md_path.write_text(md, encoding="utf-8")
    (REPORTS_DIR / "normalized_layer_comparison.md").write_text(
        render_normalized_layer_markdown(overall_rows, conference_rows),
        encoding="utf-8",
    )
    (REPORTS_DIR / "coverage_audit_evolution.md").write_text(
        render_coverage_evolution_markdown(snapshot_table_rows),
        encoding="utf-8",
    )
    print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
