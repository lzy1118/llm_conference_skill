from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path


EXPECTED_2020_2025_KEYS = [
    *(f"asiacrypt_{year}" for year in range(2020, 2026)),
    *(f"ccs_{year}" for year in range(2020, 2026)),
    *(f"crypto_{year}" for year in range(2020, 2026)),
    *(f"eurocrypt_{year}" for year in range(2020, 2026)),
    *(f"ieee_sp_{year}" for year in range(2020, 2026)),
    *(f"ndss_{year}" for year in range(2020, 2026)),
    *(f"usenix_security_{year}" for year in range(2020, 2026)),
]


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def replace_embedded_paths(value: object) -> object:
    if isinstance(value, str):
        return value.replace("generated-data/extraction_2020_2025_full", "generated-data/extraction")
    if isinstance(value, list):
        return [replace_embedded_paths(item) for item in value]
    if isinstance(value, dict):
        return {key: replace_embedded_paths(item) for key, item in value.items()}
    return value


def normalize_extraction_json_paths(extraction_dir: Path) -> None:
    for json_path in extraction_dir.rglob("*.json"):
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        normalized = replace_embedded_paths(payload)
        json_path.write_text(json.dumps(normalized, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def generate_extraction_index(extraction_dir: Path) -> None:
    by_conference_dir = extraction_dir / "output" / "by_conference"
    raw_root = extraction_dir / "raw" / "by_conference"
    interim_root = extraction_dir / "interim" / "by_conference"
    pdf_root = extraction_dir / "pdfs" / "by_conference"
    rows: list[dict[str, object]] = []

    for conference_dir in sorted(path for path in by_conference_dir.iterdir() if path.is_dir()):
        conference_key = conference_dir.name
        raw_dir = raw_root / conference_key
        interim_dir = interim_root / conference_key
        pdf_dir = pdf_root / conference_key
        rows.append(
            {
                "conference_key": conference_key,
                "raw_dir": str(raw_dir.resolve()) if raw_dir.exists() else "",
                "interim_dir": str(interim_dir.resolve()) if interim_dir.exists() else "",
                "output_dir": str(conference_dir.resolve()),
                "pdf_dir": str(pdf_dir.resolve()) if pdf_dir.exists() else "",
                "has_validation_report": (conference_dir / "validation_report.json").exists(),
                "has_author_affiliations": (conference_dir / "author_affiliations.csv").exists(),
                "has_author_affiliations_audit": (conference_dir / "author_affiliations_audit.csv").exists(),
                "has_xlsx": (conference_dir / "author_affiliations.xlsx").exists(),
            }
        )

    csv_path = extraction_dir / "artifact_index.csv"
    write_csv(
        csv_path,
        [
            "conference_key",
            "raw_dir",
            "interim_dir",
            "output_dir",
            "pdf_dir",
            "has_validation_report",
            "has_author_affiliations",
            "has_author_affiliations_audit",
            "has_xlsx",
        ],
        rows,
    )

    lines = [
        "# Extraction Artifact Index",
        "",
        "## Notes",
        "",
        "This index shows whether each `conference_key` has the expected extraction-layer artifacts.",
        "",
        f"- conference-year directories: {len(rows)}",
        f"- expected 2020-2025 conference-year directories: {len(EXPECTED_2020_2025_KEYS)}",
        f"- machine-readable version: `{csv_path.relative_to(extraction_dir.parent.parent)}`",
        "",
        "## Current Conference Index",
        "",
        "| conference_key | author_affiliations | audit | validation_report | pdf_dir |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        pdf_dir = row["pdf_dir"]
        pdf_cell = f"`{Path(str(pdf_dir)).relative_to(extraction_dir.parent.parent)}`" if pdf_dir else ""
        lines.append(
            f"| {row['conference_key']} | {str(row['has_author_affiliations']).lower()} | {str(row['has_author_affiliations_audit']).lower()} | {str(row['has_validation_report']).lower()} | {pdf_cell} |"
        )
    write_text(extraction_dir / "artifact_index.md", "\n".join(lines))


def list_relative_files(path: Path) -> list[Path]:
    return sorted(candidate for candidate in path.rglob("*") if candidate.is_file())


def key_files_for_directory(path: Path) -> str:
    files = list_relative_files(path)
    names = [file.name for file in files]
    preferred = []
    for suffix in ("summary.csv", "report.md", "report.json", "manifest.json", ".svg", ".csv", ".md", ".json"):
        for name in names:
            if suffix.startswith("."):
                if name.endswith(suffix) and name not in preferred:
                    preferred.append(name)
            elif name.endswith(suffix) and name not in preferred:
                preferred.append(name)
    if not preferred:
        preferred = names
    return " | ".join(preferred[:6])


def generate_analysis_index(analysis_dir: Path) -> None:
    entries = [
        ("README", analysis_dir / "README.md", "file"),
        ("audit", analysis_dir / "audit", "dir"),
        ("authors", analysis_dir / "authors", "dir"),
        ("automation_manifest", analysis_dir / "automation_manifest.json", "file"),
        ("automation_report", analysis_dir / "automation_report.md", "file"),
        ("collaboration", analysis_dir / "collaboration", "dir"),
        ("country", analysis_dir / "country", "dir"),
        ("institutions", analysis_dir / "institutions", "dir"),
        ("reports", analysis_dir / "reports", "dir"),
        ("trends", analysis_dir / "trends", "dir"),
        ("visualizations", analysis_dir / "visualizations", "dir"),
    ]
    rows: list[dict[str, object]] = []
    repo_root = analysis_dir.parent.parent

    for section, path, kind in entries:
        if not path.exists():
            file_count = 0
            key_files = ""
        elif kind == "file":
            file_count = 1
            key_files = path.name
        else:
            file_count = len(list_relative_files(path))
            key_files = key_files_for_directory(path)
        rows.append(
            {
                "section": section,
                "path": str(path.relative_to(repo_root)),
                "type": kind,
                "file_count": file_count,
                "key_files": key_files,
            }
        )

    csv_path = analysis_dir / "artifact_index.csv"
    write_csv(csv_path, ["section", "path", "type", "file_count", "key_files"], rows)

    lines = [
        "# Analysis Artifact Index",
        "",
        "| section | path | type | file_count | key_files |",
        "|---|---|---|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['section']} | `{row['path']}` | {row['type']} | {row['file_count']} | {row['key_files']} |"
        )
    write_text(analysis_dir / "artifact_index.md", "\n".join(lines))


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def unresolved_titles(queue_path: Path) -> list[str]:
    if not queue_path.exists():
        return []
    with queue_path.open(encoding="utf-8", newline="") as handle:
        return [row.get("title", "").strip() for row in csv.DictReader(handle) if row.get("title")]


def load_conference_reports(extraction_dir: Path) -> list[dict[str, object]]:
    reports: list[dict[str, object]] = []
    by_conference_dir = extraction_dir / "output" / "by_conference"
    for report_path in sorted(by_conference_dir.glob("*/validation_report.json")):
        report = load_json(report_path)
        report["conference_key"] = report_path.parent.name
        reports.append(report)
    return reports


def sum_int(rows: list[dict[str, object]], key: str) -> int:
    total = 0
    for row in rows:
        try:
            total += int(row.get(key, 0) or 0)
        except (TypeError, ValueError):
            continue
    return total


def generate_validation_status_report(extraction_dir: Path, report_path: Path) -> None:
    reports = load_conference_reports(extraction_dir)
    crypto_reports = [
        row
        for row in reports
        if str(row.get("conference", "")) in {"ASIACRYPT", "CRYPTO", "EUROCRYPT"}
    ]
    security_reports = [
        row
        for row in reports
        if str(row.get("conference", "")) in {"USENIX_SECURITY", "NDSS", "IEEE_S&P", "CCS"}
    ]

    total_papers = sum_int(reports, "papers_count")
    total_expanded_rows = sum_int(reports, "expanded_author_rows")
    total_classified_rows = sum_int(reports, "classified_author_rows")
    total_unresolved_countries = sum_int(reports, "unresolved_country_rows")
    total_missing_affiliations = sum_int(reports, "papers_without_affiliation_data")
    total_mismatch_issues = sum_int(reports, "affiliation_mismatch_issues")
    expected_keys = set(EXPECTED_2020_2025_KEYS)
    actual_keys = {path.name for path in (extraction_dir / "output" / "by_conference").iterdir() if path.is_dir()}
    missing_keys = sorted(expected_keys - actual_keys)
    extra_keys = sorted(actual_keys - expected_keys)

    remaining_gap_paths = {
        "USENIX 2024": extraction_dir / "interim" / "by_conference" / "usenix_security_2024" / "affiliation_resolution_queue.csv",
        "USENIX 2025": extraction_dir / "interim" / "by_conference" / "usenix_security_2025" / "affiliation_resolution_queue.csv",
        "CCS 2025": extraction_dir / "interim" / "by_conference" / "ccs_2025" / "affiliation_resolution_queue.csv",
    }

    lines = [
        "# 2020-2025 Extraction Validation Status",
        "",
        f"Updated: {datetime.now().strftime('%Y-%m-%d')}",
        "",
        "## Scope",
        "",
        "- Conferences: ASIACRYPT / CRYPTO / EUROCRYPT / USENIX Security / NDSS / IEEE S&P / ACM CCS",
        "- Years: 2020-2025",
        f"- Canonical extraction directory: `{extraction_dir.relative_to(extraction_dir.parent.parent)}`",
        "- Validation sources: all `generated-data/extraction/output/by_conference/*/validation_report.json` files",
        "",
        "## Coverage",
        "",
        f"- expected conference-year directories: {len(expected_keys)}",
        f"- present conference-year directories: {len(actual_keys)}",
        f"- missing conference-year directories: {len(missing_keys)}",
        f"- unexpected conference-year directories: {len(extra_keys)}",
        "",
        "## Totals",
        "",
        f"- papers: {total_papers}",
        f"- expanded author-affiliation rows: {total_expanded_rows}",
        f"- classified author-affiliation-country rows: {total_classified_rows}",
        f"- unresolved country rows before normalization: {total_unresolved_countries}",
        f"- papers still missing affiliation data: {total_missing_affiliations}",
        f"- affiliation mismatch issues: {total_mismatch_issues}",
        "",
        "## Group Summaries",
        "",
        f"- top3_crypto conference-years: {len(crypto_reports)}",
        f"- top3_crypto papers: {sum_int(crypto_reports, 'papers_count')}",
        f"- top3_crypto classified rows: {sum_int(crypto_reports, 'classified_author_rows')}",
        f"- top3_crypto unresolved country rows: {sum_int(crypto_reports, 'unresolved_country_rows')}",
        f"- top3_crypto mismatch issues: {sum_int(crypto_reports, 'affiliation_mismatch_issues')}",
        f"- top4_security conference-years: {len(security_reports)}",
        f"- top4_security papers: {sum_int(security_reports, 'papers_count')}",
        f"- top4_security papers without affiliation data: {sum_int(security_reports, 'papers_without_affiliation_data')}",
        f"- top4_security classified rows: {sum_int(security_reports, 'classified_author_rows')}",
        f"- top4_security unresolved country rows: {sum_int(security_reports, 'unresolved_country_rows')}",
        "",
        "## Remaining Explicit Affiliation Gaps",
        "",
    ]

    for label, queue_path in remaining_gap_paths.items():
        titles = unresolved_titles(queue_path)
        lines.append(f"- {label}: {len(titles)} paper(s)")
        for title in titles[:5]:
            lines.append(f"  - {title}")

    if crypto_reports:
        worst_crypto = sorted(
            crypto_reports,
            key=lambda row: int(row.get("unresolved_country_rows", 0)),
            reverse=True,
        )[:3]
        lines.extend(["", "## Highest Crypto Unresolved-Country Counts", ""])
        for row in worst_crypto:
            lines.append(
                f"- {row.get('conference')} {row.get('year')}: unresolved_country_rows={row.get('unresolved_country_rows', 0)}, mismatch_issues={row.get('affiliation_mismatch_issues', 0)}"
            )

    if security_reports:
        worst_security = sorted(
            security_reports,
            key=lambda row: int(row.get("papers_without_affiliation_data", 0)),
            reverse=True,
        )[:5]
        lines.extend(["", "## Highest Security Missing-Affiliation Counts", ""])
        for row in worst_security:
            lines.append(
                f"- {row.get('conference')} {row.get('year')}: papers_without_affiliation_data={row.get('papers_without_affiliation_data', 0)}, unresolved_country_rows={row.get('unresolved_country_rows', 0)}"
            )

    lines.extend(
        [
            "",
            "## Conclusion",
            "",
            "- The canonical 2020-2025 extraction batch is now aligned under `generated-data/extraction/`.",
            "- The normalized and analysis layers should be interpreted against this canonical batch, not against ad hoc partial extraction snapshots.",
        ]
    )
    write_text(report_path, "\n".join(lines))


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    extraction_dir = repo_root / "generated-data" / "extraction"
    analysis_dir = repo_root / "generated-data" / "analysis"
    report_path = repo_root / "generated-data" / "reports" / "extraction_2020_2025_validation_status_2026_06_03.md"
    normalize_extraction_json_paths(extraction_dir)
    generate_extraction_index(extraction_dir)
    generate_analysis_index(analysis_dir)
    generate_validation_status_report(extraction_dir, report_path)


if __name__ == "__main__":
    main()
