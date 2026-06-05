from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

try:
    from openpyxl import Workbook
except ImportError:  # pragma: no cover - optional dependency in local env
    Workbook = None


DEFAULT_EXTRACTION_DIR = Path("generated-data") / "extraction"
RULES_PATH = Path(__file__).resolve().parents[1] / "references" / "affiliation_noise_rules.csv"
EXPANDED_FIELDS = [
    "conference",
    "year",
    "paper_id",
    "title",
    "name",
    "article_tag",
    "author_order",
    "inst",
    "country",
    "classification_source",
    "classification_confidence",
    "classification_reason",
]
OUTPUT_FIELDS = ["name", "year", "article_tag", "author_order", "inst", "country"]
NOISE_FIELDS = EXPANDED_FIELDS + ["noise_reason"]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_workbook(path: Path, rows: list[dict[str, str]]) -> None:
    if Workbook is None:
        return
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "英文版"
    sheet.append(OUTPUT_FIELDS)
    for row in rows:
        sheet.append([row.get(field, "") for field in OUTPUT_FIELDS])
    workbook.save(path)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def load_rules(path: Path) -> tuple[dict[str, str], list[tuple[re.Pattern[str], str]]]:
    exact_rules: dict[str, str] = {}
    regex_rules: list[tuple[re.Pattern[str], str]] = []
    for row in read_csv(path):
        match_type = normalize_space(row.get("match_type", "")).casefold()
        value = normalize_space(row.get("value", ""))
        reason = normalize_space(row.get("reason", "")) or "noise_rule"
        if not match_type or not value:
            continue
        if match_type == "exact":
            exact_rules[value.casefold()] = reason
        elif match_type == "regex":
            regex_rules.append((re.compile(value, re.IGNORECASE), reason))
    return exact_rules, regex_rules


def classify_noise(inst: str, exact_rules: dict[str, str], regex_rules: list[tuple[re.Pattern[str], str]]) -> str:
    normalized = normalize_space(inst)
    if not normalized:
        return "noise_empty_affiliation"
    exact_reason = exact_rules.get(normalized.casefold())
    if exact_reason:
        return exact_reason
    for pattern, reason in regex_rules:
        if pattern.search(normalized):
            return reason
    return ""


def clean_conference(
    extraction_dir: Path,
    conference_key: str,
    exact_rules: dict[str, str],
    regex_rules: list[tuple[re.Pattern[str], str]],
) -> dict[str, object]:
    interim_dir = extraction_dir / "interim" / "by_conference" / conference_key
    output_dir = extraction_dir / "output" / "by_conference" / conference_key
    expanded_path = interim_dir / "author_affiliations_expanded.csv"
    noise_path = interim_dir / "noise_rows.csv"
    audit_path = output_dir / "author_affiliations_audit.csv"
    classified_path = output_dir / "author_affiliations.csv"
    workbook_path = output_dir / "author_affiliations.xlsx"
    validation_path = output_dir / "validation_report.json"

    rows = read_csv(expanded_path)
    cleaned_rows: list[dict[str, str]] = []
    noise_rows: list[dict[str, str]] = []

    for row in rows:
        reason = classify_noise(row.get("inst", ""), exact_rules, regex_rules)
        if reason:
            noise_rows.append({**row, "noise_reason": reason})
        else:
            cleaned_rows.append(row)

    classified_rows = [row for row in cleaned_rows if row.get("country") and row["country"] != "Unknown"]
    unresolved_after = len(cleaned_rows) - len(classified_rows)

    write_csv(expanded_path, EXPANDED_FIELDS, cleaned_rows)
    write_csv(noise_path, NOISE_FIELDS, noise_rows)
    write_csv(audit_path, EXPANDED_FIELDS, cleaned_rows)
    write_csv(classified_path, OUTPUT_FIELDS, classified_rows)
    write_workbook(workbook_path, classified_rows)

    report = json.loads(validation_path.read_text(encoding="utf-8"))
    report["expanded_author_rows"] = len(cleaned_rows)
    report["classified_author_rows"] = len(classified_rows)
    report["resolved_country_rows"] = len(classified_rows)
    report["unresolved_country_rows"] = unresolved_after
    report["noise_rows_removed"] = len(noise_rows)
    validation_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    return {
        "conference_key": conference_key,
        "input_rows": len(rows),
        "noise_rows_removed": len(noise_rows),
        "cleaned_rows": len(cleaned_rows),
        "classified_rows": len(classified_rows),
        "unresolved_rows": unresolved_after,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove extraction-layer affiliation noise rows.")
    parser.add_argument("--output-dir", default=str(DEFAULT_EXTRACTION_DIR), help="Extraction root directory")
    parser.add_argument("--conference", action="append", default=[], help="Optional conference_key to clean")
    args = parser.parse_args()

    extraction_dir = Path(args.output_dir)
    exact_rules, regex_rules = load_rules(RULES_PATH)
    interim_root = extraction_dir / "interim" / "by_conference"
    conference_keys = args.conference or sorted(path.name for path in interim_root.iterdir() if path.is_dir())

    summary: list[dict[str, object]] = []
    for conference_key in conference_keys:
        result = clean_conference(extraction_dir, conference_key, exact_rules, regex_rules)
        summary.append(result)
        if result["noise_rows_removed"]:
            print(
                f"{conference_key}: noise_rows_removed={result['noise_rows_removed']} "
                f"unresolved_rows={result['unresolved_rows']}"
            )

    payload = {
        "rules_path": str(RULES_PATH),
        "conference_count": len(summary),
        "noise_rows_removed": sum(int(row["noise_rows_removed"]) for row in summary),
        "unresolved_rows_after_cleaning": sum(int(row["unresolved_rows"]) for row in summary),
        "conference_summaries": summary,
    }
    report_path = extraction_dir / "noise_cleaning_report.json"
    report_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(
        "TOTAL "
        f"conference_count={payload['conference_count']} "
        f"noise_rows_removed={payload['noise_rows_removed']} "
        f"unresolved_rows_after_cleaning={payload['unresolved_rows_after_cleaning']}"
    )


if __name__ == "__main__":
    main()
