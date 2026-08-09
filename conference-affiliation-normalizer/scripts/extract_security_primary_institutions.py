#!/usr/bin/env python3
"""Extract auditable primary institutions for the four security conferences."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from extract_crypto_primary_institutions import (
    OUTPUT_FIELDS,
    canonical_country,
    enrich_row,
    load_institution_table,
    load_reviewed_aliases,
    normalized_key,
    write_csv,
)


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_INPUT_DIR = (
    REPO_ROOT / "generated-data" / "security_2020_2025_institution_extraction_20260731"
    / "extraction_affilgood_postmatched"
)
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT / "generated-data" / "security_2020_2025_institution_extraction_20260731"
    / "primary_institution"
)
DEFAULT_TABLE = REPO_ROOT / "generated-data" / "institution_raw.csv"
DEFAULT_RULES = SCRIPT_DIR.parent / "references" / "personal-rules.json"
CONFERENCES = {"ccs", "ieee_sp", "ndss", "usenix_security"}


def conference_key(path: Path) -> str:
    name = path.name.casefold()
    for conference in sorted(CONFERENCES, key=len, reverse=True):
        if name.startswith(conference + "_"):
            return conference
    return ""


def enrich_security_row(
    row: dict[str, str],
    table: dict[str, Any],
    aliases: dict[str, list[dict[str, str]]],
    known_countries: set[str],
    known_cities: set[str],
    valid_local_ids: set[str] | None = None,
) -> dict[str, str]:
    enriched = enrich_row(row, table, aliases, known_countries, known_cities)
    institution = enriched.get("primary_institution", "").strip()
    ror_id = enriched.get("primary_ror_id", "").strip()
    country = enriched.get("primary_country", "").strip()
    if country and country != "none" and not enriched.get("affilgood_location_country", "").strip():
        enriched["affilgood_location_country"] = country
    if country and country != "none" and not enriched.get("country", "").strip():
        enriched["country"] = country
    if ror_id and not enriched.get("affilgood_ror_ids", "").strip():
        enriched["affilgood_ror_ids"] = ror_id
    if institution and institution != "Independent Researcher":
        if not enriched.get("affilgood_standard_institutions", "").strip():
            enriched["affilgood_standard_institutions"] = institution
        if not enriched.get("affilgood_institutions", "").strip():
            enriched["affilgood_institutions"] = institution
    primary_id = enriched.get("primary_institution_id", "").strip()
    has_reviewed_local_id = primary_id in (valid_local_ids or set())
    if institution == "Independent Researcher" and has_reviewed_local_id:
        reasons = [
            reason for reason in enriched.get("primary_review_reason", "").split(";")
            if reason and reason != "missing_country"
        ]
        enriched["primary_review_reason"] = ";".join(reasons)
        enriched["primary_match_status"] = "complete" if not reasons else "needs_supplement"
    if (
        institution
        and institution != "Independent Researcher"
        and not ror_id
        and not has_reviewed_local_id
    ):
        reasons = [
            reason for reason in enriched.get("primary_review_reason", "").split(";") if reason
        ]
        if "missing_ror" not in reasons:
            reasons.append("missing_ror")
        enriched["primary_review_reason"] = ";".join(reasons)
        enriched["primary_match_status"] = "needs_supplement"
    return enriched


def process_directory(
    input_dir: Path,
    output_dir: Path,
    institution_table: Path,
    personal_rules: Path,
) -> dict[str, Any]:
    table = load_institution_table(str(institution_table))
    aliases = load_reviewed_aliases(personal_rules)
    known_countries = {
        canonical_country(row.get("affilgood_location_country"))
        for row in table["rows"]
        if canonical_country(row.get("affilgood_location_country"))
    }
    known_cities = {
        normalized_key(row.get("affilgood_location_city"))
        for row in table["rows"]
        if normalized_key(row.get("affilgood_location_city"))
    }
    valid_local_ids = {
        str(row.get("conference_final_id") or row.get("conference_id") or "").strip()
        for row in table["rows"]
        if str(row.get("conference_final_id") or row.get("conference_id") or "").strip()
    }
    files = [path for path in sorted(input_dir.glob("*.csv")) if conference_key(path)]
    if not files:
        raise FileNotFoundError(f"no four-security-conference CSV files found in {input_dir}")

    combined: list[dict[str, str]] = []
    field_order: list[str] = []
    by_file: list[dict[str, Any]] = []
    for input_path in files:
        with input_path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            source_fields = list(reader.fieldnames or [])
            rows = [
                enrich_security_row(
                    row, table, aliases, known_countries, known_cities, valid_local_ids
                )
                for row in reader
            ]
        fields = source_fields + [field for field in OUTPUT_FIELDS if field not in source_fields]
        if not field_order:
            field_order = fields
        output_path = output_dir / f"{input_path.stem}_主体机构.csv"
        write_csv(output_path, rows, fields)
        combined.extend(rows)
        by_file.append({
            "conference": conference_key(input_path),
            "input": str(input_path.resolve()),
            "output": str(output_path.resolve()),
            "rows": len(rows),
            "complete": sum(row["primary_match_status"] == "complete" for row in rows),
            "needs_supplement": sum(
                row["primary_match_status"] != "complete" for row in rows
            ),
        })

    combined_path = output_dir / "四大安全会_2020-2025_主体机构.csv"
    review_path = output_dir / "四大安全会_2020-2025_主体机构_补充队列.csv"
    report_path = output_dir / "四大安全会_2020-2025_主体机构_报告.json"
    write_csv(combined_path, combined, field_order)
    review_rows = [row for row in combined if row["primary_match_status"] != "complete"]
    write_csv(review_path, review_rows, field_order)
    statuses = Counter(row["primary_match_status"] for row in combined)
    reasons = Counter(
        reason
        for row in review_rows
        for reason in row["primary_review_reason"].split(";")
        if reason
    )
    report = {
        "processing_order": [
            "country_backfill",
            "country_constrained_affilgood_ror",
            "institution_raw_postfill",
            "reviewed_supplement",
            "final_supplement_queue",
        ],
        "input_dir": str(input_dir.resolve()),
        "institution_table": str(institution_table.resolve()),
        "files": len(files),
        "rows": len(combined),
        "complete": statuses["complete"],
        "needs_supplement": statuses["needs_supplement"],
        "missing_country": reasons["missing_country"],
        "missing_institution_id": reasons["missing_institution_id"],
        "missing_ror": sum(
            bool(row["primary_institution"])
            and row["primary_institution"] != "Independent Researcher"
            and not bool(row["primary_ror_id"])
            and row["primary_institution_id"] not in valid_local_ids
            for row in combined
        ),
        "by_file": by_file,
        "combined_output": str(combined_path.resolve()),
        "supplement_queue": str(review_path.resolve()),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--institution-table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--personal-rules", type=Path, default=DEFAULT_RULES)
    args = parser.parse_args()
    report = process_directory(
        args.input_dir, args.output_dir, args.institution_table, args.personal_rules
    )
    print(json.dumps({key: report[key] for key in (
        "files", "rows", "complete", "needs_supplement", "missing_country",
        "missing_ror", "missing_institution_id", "combined_output", "supplement_queue",
    )}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
