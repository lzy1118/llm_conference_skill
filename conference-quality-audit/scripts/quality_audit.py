from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


ANALYSIS_EXPECTED_FILES = {
    "country": [Path("country/country_summary.csv"), Path("country/country_report.md")],
    "institutions": [Path("institutions/institution_summary.csv"), Path("institutions/institution_report.md")],
    "authors": [Path("authors/author_summary.csv"), Path("authors/author_report.md")],
    "trends": [Path("trends/trend_summary.csv"), Path("trends/trend_report.md")],
    "collaboration": [Path("collaboration/collaboration_edges.csv"), Path("collaboration/collaboration_report.md")],
}


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_confidence(value: str) -> float | None:
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def add_finding(findings: list[dict[str, object]], severity: str, code: str, message: str, count: int | None = None) -> None:
    finding: dict[str, object] = {"severity": severity, "code": code, "message": message}
    if count is not None:
        finding["count"] = count
    findings.append(finding)


def audit_normalized_rows(rows: list[dict[str, str]], findings: list[dict[str, object]]) -> dict[str, object]:
    required_fields = ("paper_key", "conference", "year", "name", "inst")
    missing_counts = {field: sum(1 for row in rows if not row.get(field, "")) for field in required_fields}
    unknown_country_rows = sum(1 for row in rows if row.get("country") == "Unknown")
    missing_author_key_rows = sum(1 for row in rows if not row.get("author_key", ""))

    low_confidence_rows = 0
    invalid_confidence_rows = 0
    institution_name_to_keys: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        institution_name = row.get("inst", "")
        institution_key = row.get("institution_key", "")
        if institution_name and institution_key:
            institution_name_to_keys[institution_name].add(institution_key)
        confidence = parse_confidence(row.get("classification_confidence", ""))
        raw_confidence = row.get("classification_confidence", "")
        if raw_confidence and confidence is None:
            invalid_confidence_rows += 1
        elif confidence is not None and confidence < 0.8:
            low_confidence_rows += 1

    duplicate_display_names = sum(1 for keys in institution_name_to_keys.values() if len(keys) > 1)

    for field, count in missing_counts.items():
        if count:
            add_finding(findings, "high", f"missing_{field}", f"Rows missing required field '{field}'", count)
    if unknown_country_rows:
        add_finding(findings, "medium", "unknown_country", "Rows have unresolved country value 'Unknown'", unknown_country_rows)
    if missing_author_key_rows:
        add_finding(findings, "medium", "missing_author_key", "Rows are missing author_key and may weaken author identity analysis", missing_author_key_rows)
    if low_confidence_rows:
        add_finding(findings, "medium", "low_classification_confidence", "Rows have classification_confidence below 0.8", low_confidence_rows)
    if invalid_confidence_rows:
        add_finding(findings, "medium", "invalid_classification_confidence", "Rows have non-numeric classification_confidence values", invalid_confidence_rows)
    if duplicate_display_names:
        add_finding(findings, "medium", "duplicate_institution_display_names", "Institution display names map to multiple normalized keys", duplicate_display_names)

    return {
        "row_count": len(rows),
        "missing_required_counts": missing_counts,
        "unknown_country_rows": unknown_country_rows,
        "missing_author_key_rows": missing_author_key_rows,
        "low_confidence_rows": low_confidence_rows,
        "invalid_confidence_rows": invalid_confidence_rows,
        "duplicate_institution_display_names": duplicate_display_names,
    }


def audit_institution_dim(rows: list[dict[str, str]], findings: list[dict[str, object]]) -> dict[str, object]:
    needs_review_rows = sum(1 for row in rows if str(row.get("needs_review", "")).lower() == "true")
    unknown_country_rows = sum(1 for row in rows if row.get("country") == "Unknown")
    display_counts = Counter(row.get("inst_display", "") for row in rows if row.get("inst_display", ""))
    duplicate_display_rows = sum(1 for count in display_counts.values() if count > 1)

    if needs_review_rows:
        add_finding(findings, "medium", "institution_needs_review", "Institution dimension contains rows marked needs_review", needs_review_rows)
    if unknown_country_rows:
        add_finding(findings, "medium", "institution_unknown_country", "Institution dimension contains Unknown country rows", unknown_country_rows)
    if duplicate_display_rows:
        add_finding(findings, "low", "duplicate_institution_dim_display", "Institution dimension contains duplicate display names", duplicate_display_rows)

    return {
        "row_count": len(rows),
        "needs_review_rows": needs_review_rows,
        "unknown_country_rows": unknown_country_rows,
        "duplicate_display_rows": duplicate_display_rows,
    }


def audit_analysis_dir(analysis_dir: Path, findings: list[dict[str, object]]) -> dict[str, object]:
    checks: dict[str, object] = {"analysis_dir": str(analysis_dir), "sections": {}}
    for section, relative_paths in ANALYSIS_EXPECTED_FILES.items():
        section_info = {"missing_files": [], "empty_files": []}
        for relative_path in relative_paths:
            path = analysis_dir / relative_path
            if not path.exists():
                section_info["missing_files"].append(str(relative_path))
                severity = "high" if path.suffix == ".csv" else "medium"
                add_finding(findings, severity, "missing_analysis_file", f"Missing analysis file: {relative_path}")
                continue
            if path.suffix == ".csv":
                rows = read_csv_rows(path)
                if not rows:
                    section_info["empty_files"].append(str(relative_path))
                    add_finding(findings, "low", "empty_analysis_file", f"Analysis CSV is empty: {relative_path}")
        checks["sections"][section] = section_info
    return checks


def write_outputs(output_dir: Path, payload: dict[str, object]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "quality_audit.json").write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    lines = ["# Conference Quality Audit", "", "## Severity Counts", ""]
    severity_counts = payload["severity_counts"]
    for severity in ("high", "medium", "low"):
        lines.append(f"- {severity}: {severity_counts.get(severity, 0)}")
    lines.extend(["", "## Findings", ""])
    findings = payload["findings"]
    if not findings:
        lines.append("- No findings.")
    else:
        for finding in findings:
            suffix = f" count={finding['count']}" if "count" in finding else ""
            lines.append(f"- [{finding['severity']}] {finding['code']}: {finding['message']}{suffix}")
    (output_dir / "quality_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit normalized conference data and analysis outputs.")
    parser.add_argument("--normalized-input", help="Path to normalized author_affiliation_facts.csv")
    parser.add_argument("--institution-dim", help="Optional path to institution_dim.csv")
    parser.add_argument("--analysis-dir", help="Optional path to an analysis output directory")
    parser.add_argument("--output-dir", required=True, help="Output directory for audit results")
    args = parser.parse_args()

    if not args.normalized_input and not args.analysis_dir:
        raise SystemExit("Provide at least --normalized-input or --analysis-dir")

    findings: list[dict[str, object]] = []
    payload: dict[str, object] = {
        "normalized_checks": None,
        "institution_dim_checks": None,
        "analysis_checks": None,
        "findings": findings,
    }

    if args.normalized_input:
        normalized_rows = read_csv_rows(Path(args.normalized_input).resolve())
        payload["normalized_checks"] = audit_normalized_rows(normalized_rows, findings)
    if args.institution_dim:
        institution_rows = read_csv_rows(Path(args.institution_dim).resolve())
        payload["institution_dim_checks"] = audit_institution_dim(institution_rows, findings)
    if args.analysis_dir:
        payload["analysis_checks"] = audit_analysis_dir(Path(args.analysis_dir).resolve(), findings)

    severity_counts = Counter(str(finding["severity"]) for finding in findings)
    payload["severity_counts"] = dict(severity_counts)
    write_outputs(Path(args.output_dir).resolve(), payload)


if __name__ == "__main__":
    main()
