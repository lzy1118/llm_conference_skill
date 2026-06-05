from __future__ import annotations

import csv
import json
from pathlib import Path

from security_real_backend import classify_affiliation, load_institution_overrides

try:
    from openpyxl import Workbook
except ImportError:  # pragma: no cover - optional dependency in local env
    Workbook = None


ROOT = Path(__file__).resolve().parents[2]
EXTRACTION_DIR = ROOT / "generated-data" / "extraction"
INTERIM_DIR = EXTRACTION_DIR / "interim" / "by_conference"
OUTPUT_DIR = EXTRACTION_DIR / "output" / "by_conference"
OVERRIDES_PATH = EXTRACTION_DIR / "reference" / "institution_country_overrides.csv"

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


def reclassify_conference(conference_key: str, overrides: dict[str, object]) -> tuple[int, int, int, int]:
    expanded_path = INTERIM_DIR / conference_key / "author_affiliations_expanded.csv"
    output_dir = OUTPUT_DIR / conference_key
    audit_path = output_dir / "author_affiliations_audit.csv"
    classified_path = output_dir / "author_affiliations.csv"
    workbook_path = output_dir / "author_affiliations.xlsx"
    validation_path = output_dir / "validation_report.json"

    rows = read_csv(expanded_path)
    resolved_before = sum(1 for row in rows if row.get("country") and row["country"] != "Unknown")
    updated_rows: list[dict[str, str]] = []
    resolved_now = 0

    for row in rows:
        if row.get("country") in {"", "Unknown"}:
            classification = classify_affiliation(row.get("inst", ""), overrides)
            if classification.country and classification.country != "Unknown":
                row = {
                    **row,
                    "country": classification.country,
                    "classification_source": classification.source,
                    "classification_confidence": str(classification.confidence),
                    "classification_reason": classification.reason,
                }
                resolved_now += 1
        updated_rows.append(row)

    classified_rows = [row for row in updated_rows if row.get("country") and row["country"] != "Unknown"]
    unresolved_after = len(updated_rows) - len(classified_rows)

    write_csv(expanded_path, EXPANDED_FIELDS, updated_rows)
    write_csv(audit_path, EXPANDED_FIELDS, updated_rows)
    write_csv(classified_path, OUTPUT_FIELDS, classified_rows)
    write_workbook(workbook_path, classified_rows)

    report = json.loads(validation_path.read_text(encoding="utf-8"))
    report["expanded_author_rows"] = len(updated_rows)
    report["classified_author_rows"] = len(classified_rows)
    report["resolved_country_rows"] = len(classified_rows)
    report["unresolved_country_rows"] = unresolved_after
    validation_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    return len(updated_rows), resolved_before, len(classified_rows), resolved_now


def main() -> None:
    overrides = load_institution_overrides(OVERRIDES_PATH)
    totals = {
        "rows": 0,
        "resolved_before": 0,
        "resolved_after": 0,
        "resolved_now": 0,
    }
    for conference_dir in sorted(path for path in INTERIM_DIR.iterdir() if path.is_dir()):
        conference_key = conference_dir.name
        rows, resolved_before, resolved_after, resolved_now = reclassify_conference(conference_key, overrides)
        totals["rows"] += rows
        totals["resolved_before"] += resolved_before
        totals["resolved_after"] += resolved_after
        totals["resolved_now"] += resolved_now
        if resolved_now:
            print(f"{conference_key}: resolved_now={resolved_now} unresolved_after={rows - resolved_after}")

    unresolved_before = totals["rows"] - totals["resolved_before"]
    unresolved_after = totals["rows"] - totals["resolved_after"]
    print(
        "TOTAL "
        f"rows={totals['rows']} unresolved_before={unresolved_before} "
        f"resolved_now={totals['resolved_now']} unresolved_after={unresolved_after}"
    )


if __name__ == "__main__":
    main()
