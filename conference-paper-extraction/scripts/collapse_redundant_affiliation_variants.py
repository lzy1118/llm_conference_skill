from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path


OUTPUT_FIELDS = ["name", "year", "article_tag", "author_order", "inst", "country"]
AUDIT_FIELDS = [
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

SAME_COUNTRY_AMBIGUOUS_REASONS = {
    "multi_affiliation_consensus",
    "shared_multi_affiliation_same_country",
}
INSTITUTION_KEYWORDS = re.compile(
    r"\b(university|institute|college|school|laboratory|laboratoire|lab|center|centre|academy|research|hospital|group|technology|technologies|corporation|corp|company|faculty)\b",
    re.IGNORECASE,
)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def split_candidate_parts(inst: str) -> list[str]:
    text = normalize_space(inst)
    if not text:
        return []
    if ";" in text:
        parts = [normalize_space(part) for part in text.split(";") if normalize_space(part)]
        if len(parts) > 1:
            return parts
    for sep in (" / ", " & "):
        if sep in text:
            parts = [normalize_space(part) for part in text.split(sep) if normalize_space(part)]
            if len(parts) > 1:
                return parts
    return [text]


def base_affiliation_label(inst: str) -> str:
    text = normalize_space(inst)
    text = re.sub(r"\([^)]*\)", "", text).strip(" ,;")
    if "," not in text:
        return text.casefold()
    head, tail = text.split(",", 1)
    if INSTITUTION_KEYWORDS.search(tail):
        return text.casefold()
    return normalize_space(head).casefold()


def choose_preferred_variant(parts: list[str]) -> str:
    return max(parts, key=lambda item: (len(normalize_space(item)), item))


def collapse_group(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], bool]:
    if not rows:
        return rows, False
    countries = {normalize_space(row.get("country", "")) for row in rows if normalize_space(row.get("country", ""))}
    reasons = {normalize_space(row.get("classification_reason", "")) for row in rows}
    if len(countries) != 1:
        return rows, False
    if not reasons or not reasons.issubset(SAME_COUNTRY_AMBIGUOUS_REASONS):
        return rows, False

    all_parts: list[str] = []
    for row in rows:
        all_parts.extend(split_candidate_parts(row.get("inst", "")))
    all_parts = list(dict.fromkeys(part for part in all_parts if part))
    if len(all_parts) <= 1:
        return rows, False

    base_labels = {base_affiliation_label(part) for part in all_parts if base_affiliation_label(part)}
    if len(base_labels) != 1:
        return rows, False

    preferred = choose_preferred_variant(all_parts)
    template = dict(rows[0])
    confidences = [float(normalize_space(row.get("classification_confidence", "0")) or "0") for row in rows]
    template["inst"] = preferred
    template["classification_source"] = "postprocess_same_institution_variant_collapse"
    template["classification_confidence"] = f"{max(confidences, default=0.95):.2f}"
    template["classification_reason"] = "same_institution_variant_collapsed"
    return [template], True


def grouped_key(row: dict[str, str]) -> tuple[str, str, str, str, str, str]:
    return (
        normalize_space(row.get("conference", "")),
        normalize_space(row.get("year", "")),
        normalize_space(row.get("paper_id", "")),
        normalize_space(row.get("title", "")),
        normalize_space(row.get("name", "")),
        normalize_space(row.get("author_order", "")),
    )


def count_country_resolution_rows(rows: list[dict[str, str]]) -> dict[str, int]:
    single_country_rows = sum(1 for row in rows if row.get("country") not in {"", "Unknown", "Multiple"})
    multiple_country_rows = sum(1 for row in rows if row.get("country") == "Multiple")
    unresolved_country_rows = sum(1 for row in rows if row.get("country") in {"", "Unknown"})
    return {
        "single_country_resolved_rows": single_country_rows,
        "multiple_country_rows": multiple_country_rows,
        "unresolved_country_rows": unresolved_country_rows,
    }


def process_conference(conference_dir: Path) -> dict[str, int]:
    audit_path = conference_dir / "author_affiliations_audit.csv"
    output_path = conference_dir / "author_affiliations.csv"
    validation_path = conference_dir / "validation_report.json"
    if not audit_path.exists() or not output_path.exists() or not validation_path.exists():
        return {"collapsed_groups": 0, "collapsed_rows": 0}

    rows = read_csv(audit_path)
    grouped: dict[tuple[str, str, str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    order: list[tuple[str, str, str, str, str, str]] = []
    for row in rows:
        key = grouped_key(row)
        if key not in grouped:
            order.append(key)
        grouped[key].append(row)

    updated_rows: list[dict[str, str]] = []
    collapsed_groups = 0
    collapsed_rows = 0
    for key in order:
        group_rows = grouped[key]
        replacement, changed = collapse_group(group_rows)
        if changed:
            collapsed_groups += 1
            collapsed_rows += len(group_rows) - len(replacement)
        updated_rows.extend(replacement)

    write_csv(audit_path, AUDIT_FIELDS, updated_rows)
    classified_rows = [row for row in updated_rows if row.get("country") and row["country"] != "Unknown"]
    write_csv(output_path, OUTPUT_FIELDS, classified_rows)

    report = json.loads(validation_path.read_text(encoding="utf-8"))
    country_counts = count_country_resolution_rows(updated_rows)
    report["expanded_author_rows"] = len(updated_rows)
    report["classified_author_rows"] = len(classified_rows)
    report["resolved_country_rows"] = len(classified_rows)
    report.update(country_counts)
    validation_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    return {"collapsed_groups": collapsed_groups, "collapsed_rows": collapsed_rows}


def main() -> None:
    parser = argparse.ArgumentParser(description="Collapse redundant same-institution affiliation variants in saved conference outputs.")
    parser.add_argument("--output-dir", default="generated-data/extraction/output/by_conference", help="by_conference output directory")
    parser.add_argument("--conference", action="append", default=[], help="Conference key to process. Repeatable.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    conference_dirs = []
    if args.conference:
        conference_dirs = [output_dir / key for key in args.conference]
    else:
        conference_dirs = sorted(path for path in output_dir.iterdir() if path.is_dir())

    total_groups = 0
    total_rows = 0
    for conference_dir in conference_dirs:
        result = process_conference(conference_dir)
        if result["collapsed_groups"]:
            print(f"{conference_dir.name}: collapsed_groups={result['collapsed_groups']} collapsed_rows={result['collapsed_rows']}")
        total_groups += result["collapsed_groups"]
        total_rows += result["collapsed_rows"]
    print(f"TOTAL collapsed_groups={total_groups} collapsed_rows={total_rows}")


if __name__ == "__main__":
    main()
