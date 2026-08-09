#!/usr/bin/env python3
"""Append institution aliases as separate institution_raw rows with an existing local ID."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from institution_reference import normalized_key


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_INPUT = (
    REPO_ROOT / "generated-data" / "security_2020_2025_institution_extraction_20260731"
    / "primary_institution" / "四大安全会_2020-2025_主体机构.csv"
)
DEFAULT_TABLE = REPO_ROOT / "generated-data" / "institution_raw.csv"
DEFAULT_REPORT = (
    REPO_ROOT / "generated-data" / "security_2020_2025_institution_extraction_20260731"
    / "primary_institution" / "机构别名同编号补充报告.json"
)


def clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def local_id(row: dict[str, str]) -> str:
    return clean(row.get("conference_final_id") or row.get("conference_id"))


def country_key(value: Any) -> str:
    return normalized_key(clean(value))


def ror_key(value: Any) -> str:
    return ";".join(part.strip().casefold() for part in str(value or "").split(";") if part.strip())


def load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def build_alias_rows(
    source_rows: list[dict[str, str]], table_rows: list[dict[str, str]]
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, int]]:
    by_id: dict[str, list[dict[str, str]]] = defaultdict(list)
    existing_alias_ids: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in table_rows:
        identifier = local_id(row)
        if not identifier:
            continue
        by_id[identifier].append(row)
        country = country_key(row.get("affilgood_location_country"))
        for field in ("affilgood_institutions", "affilgood_standard_institutions"):
            name = normalized_key(row.get(field, ""))
            if name:
                existing_alias_ids[(name, country)].add(identifier)

    additions: dict[tuple[str, str, str], dict[str, str]] = {}
    reviews: list[dict[str, str]] = []
    counts: Counter[str] = Counter()
    for source in source_rows:
        country = clean(source.get("primary_country") or source.get("affilgood_location_country"))
        country_norm = country_key(country)
        primary_id = clean(source.get("institution_reference_id"))
        primary_name = clean(source.get("primary_institution"))
        candidate_ids: set[str] = {primary_id} if primary_id in by_id else set()
        reference_status = clean(source.get("institution_reference_status")).casefold()
        aliases = []
        for field in ("affilgood_institutions", "affiliation_institution_candidate"):
            alias = clean(source.get(field))
            if alias and normalized_key(alias) != normalized_key(primary_name):
                aliases.append(alias)
        for alias in dict.fromkeys(aliases):
            alias_norm = normalized_key(alias)
            if len(alias_norm) < 3:
                reviews.append({
                    "alias": alias,
                    "country": country,
                    "candidate_ids": ";".join(sorted(candidate_ids)),
                    "existing_ids": "",
                    "review_reason": "implausibly_short_alias",
                })
                counts["review_implausibly_short_alias"] += 1
                continue
            if "conflict" in reference_status or "ambiguous" in reference_status:
                reviews.append({
                    "alias": alias,
                    "country": country,
                    "candidate_ids": ";".join(sorted(candidate_ids)),
                    "existing_ids": "",
                    "review_reason": "source_reference_not_stable",
                })
                counts["review_source_reference_not_stable"] += 1
                continue
            existing_ids = existing_alias_ids.get((alias_norm, country_norm), set())
            if existing_ids:
                if len(existing_ids) == 1 and existing_ids == candidate_ids:
                    counts["already_present_same_id"] += 1
                elif candidate_ids and existing_ids == candidate_ids:
                    counts["already_present_same_id"] += 1
                else:
                    reviews.append({
                        "alias": alias,
                        "country": country,
                        "candidate_ids": ";".join(sorted(candidate_ids)),
                        "existing_ids": ";".join(sorted(existing_ids)),
                        "review_reason": "alias_already_assigned_to_other_id",
                    })
                    counts["review_alias_id_conflict"] += 1
                continue
            if len(candidate_ids) != 1:
                reviews.append({
                    "alias": alias,
                    "country": country,
                    "candidate_ids": ";".join(sorted(candidate_ids)),
                    "existing_ids": "",
                    "review_reason": "no_unique_existing_institution_id",
                })
                counts["review_no_unique_id"] += 1
                continue
            identifier = next(iter(candidate_ids))
            base = by_id[identifier][0]
            base_country = country_key(base.get("affilgood_location_country"))
            if country_norm and base_country and country_norm != base_country:
                reviews.append({
                    "alias": alias,
                    "country": country,
                    "candidate_ids": identifier,
                    "existing_ids": "",
                    "review_reason": "country_conflicts_with_existing_id",
                })
                counts["review_country_conflict"] += 1
                continue
            base_standard = clean(
                base.get("affilgood_standard_institutions")
                or base.get("affilgood_institutions")
            )
            if (";" in alias) != (";" in base_standard):
                reviews.append({
                    "alias": alias,
                    "country": country,
                    "candidate_ids": identifier,
                    "existing_ids": "",
                    "review_reason": "composite_structure_mismatch",
                })
                counts["review_composite_structure_mismatch"] += 1
                continue
            key = (identifier, alias_norm, country_norm)
            additions.setdefault(key, {
                "affilgood_ror_ids": clean(base.get("affilgood_ror_ids") or source.get("primary_ror_id")),
                "conference_id": identifier,
                "affilgood_institutions": alias,
                "affilgood_location_country": clean(base.get("affilgood_location_country") or country),
                "affilgood_location_city": clean(base.get("affilgood_location_city") or source.get("primary_city")),
                "conference_final_id": identifier,
                "affilgood_standard_institutions": base_standard or primary_name,
                "affilgood_standardization_source": "alias_same_institution_id",
                "notes": "Alias appended as a separate row; original institution row preserved; local ID reused.",
            })
    counts["new_alias_rows"] = len(additions)
    return list(additions.values()), reviews, dict(counts)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def supplement(
    input_path: Path, table_path: Path, report_path: Path, *, dry_run: bool = False
) -> dict[str, Any]:
    source_fields, source_rows = load_csv(input_path)
    table_fields, table_rows = load_csv(table_path)
    additions, reviews, counts = build_alias_rows(source_rows, table_rows)
    fields = list(table_fields)
    for field in (
        "affilgood_ror_ids", "conference_id", "affilgood_institutions",
        "affilgood_location_country", "affilgood_location_city", "conference_final_id",
        "affilgood_standard_institutions", "affilgood_standardization_source", "notes",
    ):
        if field not in fields:
            fields.append(field)
    if additions and not dry_run:
        write_csv(table_path, fields, table_rows + additions)
    additions_path = report_path.with_name(report_path.stem + "_新增别名.csv")
    review_path = report_path.with_name(report_path.stem + "_需复核.csv")
    write_csv(additions_path, fields, additions)
    review_fields = ["alias", "country", "candidate_ids", "existing_ids", "review_reason"]
    write_csv(review_path, review_fields, reviews)
    report = {
        "input": str(input_path.resolve()),
        "institution_table": str(table_path.resolve()),
        "source_rows": len(source_rows),
        "table_rows_before": len(table_rows),
        "table_rows_after": len(table_rows) + (0 if dry_run else len(additions)),
        "dry_run": dry_run,
        **counts,
        "review_rows": len(reviews),
        "additions_output": str(additions_path.resolve()),
        "review_output": str(review_path.resolve()),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--institution-table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    report = supplement(args.input, args.institution_table, args.report, dry_run=args.dry_run)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
