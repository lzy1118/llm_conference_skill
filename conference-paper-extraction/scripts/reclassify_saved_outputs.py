from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from iacr_top3_backend import classify_affiliation as classify_iacr_affiliation
from iacr_top3_backend import load_institution_overrides as load_iacr_institution_overrides
from security_real_backend import classify_affiliation as classify_security_affiliation
from security_real_backend import load_institution_overrides as load_security_institution_overrides

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

GENERIC_FRAGMENT_PATTERNS = [
    r"\bcenter\b",
    r"\bcentre\b",
    r"\bdepartment\b",
    r"\bd[ée]partement\b",
    r"\bdivision\b",
    r"\binstitute\b",
    r"\blaboratory\b",
    r"\blaboratoire\b",
    r"\bschool\b",
    r"\bfaculty\b",
    r"\bamt\b",
    r"\bministry\b",
]


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


def is_context_propagation_candidate(inst: str) -> bool:
    text = normalize_space(inst)
    if not text:
        return False
    if any(marker in text for marker in [",", ";", "(", ")"]):
        return False
    lower = text.casefold()
    if re.search(r"\b(university|college)\b", lower):
        return False
    return any(re.search(pattern, lower) for pattern in GENERIC_FRAGMENT_PATTERNS)


def propagate_unique_country_within_author_paper(rows: list[dict[str, str]]) -> int:
    grouped: dict[tuple[str, str, str, str, str, str], list[dict[str, str]]] = {}
    for row in rows:
        key = (
            row.get("conference", ""),
            row.get("year", ""),
            row.get("paper_id", ""),
            row.get("title", ""),
            row.get("name", ""),
            row.get("author_order", ""),
        )
        grouped.setdefault(key, []).append(row)

    resolved_now = 0
    for group_rows in grouped.values():
        known_countries = {
            row.get("country", "")
            for row in group_rows
            if row.get("country") and row.get("country") != "Unknown"
        }
        if len(known_countries) != 1:
            continue
        inherited_country = next(iter(known_countries))
        for row in group_rows:
            if row.get("country") not in {"", "Unknown"}:
                continue
            if not is_context_propagation_candidate(row.get("inst", "")):
                continue
            row["country"] = inherited_country
            row["classification_source"] = "paper_author_country_propagation"
            row["classification_confidence"] = "0.85"
            row["classification_reason"] = "same_author_same_paper_unique_country_context"
            resolved_now += 1
    return resolved_now


def is_iacr_conference(conference_key: str) -> bool:
    return conference_key.startswith(("asiacrypt_", "crypto_", "eurocrypt_"))


def count_country_resolution_rows(rows: list[dict[str, str]]) -> dict[str, int]:
    single_country_rows = sum(1 for row in rows if row.get("country") not in {"", "Unknown", "Multiple"})
    multiple_country_rows = sum(1 for row in rows if row.get("country") == "Multiple")
    unresolved_country_rows = sum(1 for row in rows if row.get("country") in {"", "Unknown"})
    return {
        "single_country_resolved_rows": single_country_rows,
        "multiple_country_rows": multiple_country_rows,
        "unresolved_country_rows": unresolved_country_rows,
    }


def reclassify_conference(
    conference_key: str,
    overrides: dict[str, object],
    classify_affiliation_fn,
) -> tuple[int, int, int, int]:
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
            classification = classify_affiliation_fn(row.get("inst", ""), overrides)
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

    if not is_iacr_conference(conference_key):
        resolved_now += propagate_unique_country_within_author_paper(updated_rows)

    classified_rows = [row for row in updated_rows if row.get("country") and row["country"] != "Unknown"]
    country_counts = count_country_resolution_rows(updated_rows)
    unresolved_after = country_counts["unresolved_country_rows"]

    write_csv(expanded_path, EXPANDED_FIELDS, updated_rows)
    write_csv(audit_path, EXPANDED_FIELDS, updated_rows)
    write_csv(classified_path, OUTPUT_FIELDS, classified_rows)
    write_workbook(workbook_path, classified_rows)

    report = json.loads(validation_path.read_text(encoding="utf-8"))
    report["expanded_author_rows"] = len(updated_rows)
    report["classified_author_rows"] = len(classified_rows)
    report["resolved_country_rows"] = len(classified_rows)
    report.update(country_counts)
    validation_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    return len(updated_rows), resolved_before, len(classified_rows), resolved_now


def main() -> None:
    totals = {
        "rows": 0,
        "resolved_before": 0,
        "resolved_after": 0,
        "resolved_now": 0,
    }
    for conference_dir in sorted(path for path in INTERIM_DIR.iterdir() if path.is_dir()):
        conference_key = conference_dir.name
        if is_iacr_conference(conference_key):
            overrides = load_iacr_institution_overrides(OVERRIDES_PATH)
            classify_fn = classify_iacr_affiliation
        else:
            overrides = load_security_institution_overrides(OVERRIDES_PATH)
            classify_fn = classify_security_affiliation
        rows, resolved_before, resolved_after, resolved_now = reclassify_conference(conference_key, overrides, classify_fn)
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
