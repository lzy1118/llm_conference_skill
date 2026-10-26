#!/usr/bin/env python3
"""Generate a compact conference author-primary-institution display table."""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


DISPLAY_FIELDS = (
    "paper_id",
    "year",
    "conference",
    "title",
    "author",
    "author_rank",
    "affiliation_rank",
    "affiliations",
    "emails",
    "first_author",
    "co_first_author",
    "corresponding",
    "equal_contribution",
    "country",
    "orcid",
)

def clean_token(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._&+-]+", "_", (value or "").strip())
    return value.strip("_")


def output_name(conference: str, year: str | None) -> str:
    prefix = clean_token(conference)
    if not prefix:
        raise ValueError("conference is required for deterministic output naming")
    return f"{prefix}_{clean_token(year)}_final.csv" if year else f"{prefix}_final.csv"


def first_nonempty(row: dict[str, str], *fields: str) -> str:
    for field in fields:
        value = (row.get(field) or "").strip()
        if value:
            return value
    return ""


def generate(input_path: Path, output_path: Path, conference: str, year: str | None) -> tuple[int, int]:
    selected: list[dict[str, str]] = []
    skipped = 0
    with input_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"input has no CSV header: {input_path}")
        if "affilgood_location_country" not in reader.fieldnames:
            raise ValueError("input must contain affilgood_location_country")
        for row in reader:
            if conference and (row.get("conference") or "").casefold() != conference.casefold():
                skipped += 1
                continue
            if year and (row.get("year") or "").strip() != str(year):
                skipped += 1
                continue
            selected.append(
                {
                    "paper_id": row.get("paper_id", ""),
                    "year": row.get("year", ""),
                    "conference": row.get("conference", ""),
                    "title": row.get("title", ""),
                    "author": row.get("author", ""),
                    "author_rank": row.get("author_rank", ""),
                    "affiliation_rank": row.get("affiliation_rank", ""),
                    "affiliations": first_nonempty(
                        row,
                        "primary_institution",
                        "affilgood_standard_institutions",
                        "affilgood_institutions",
                        "affiliations",
                        "affiliation_raw",
                        "affiliation",
                    ),
                    "emails": row.get("emails", ""),
                    "first_author": row.get("first_author", ""),
                    "co_first_author": row.get("co_first_author", ""),
                    "corresponding": row.get("corresponding", ""),
                    "equal_contribution": row.get("equal_contribution", ""),
                    "country": (row.get("affilgood_location_country") or "").strip(),
                    "orcid": row.get("orcid", ""),
                }
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DISPLAY_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(selected)
    return len(selected), skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("generated-data/extraction_final"))
    parser.add_argument("--conference", required=True)
    parser.add_argument("--year")
    parser.add_argument("--output", type=Path, help="Override the generated output path.")
    args = parser.parse_args()
    conference_dir = clean_token(args.conference).casefold()
    year_dir = clean_token(args.year) if args.year else "all_years"
    output = args.output or args.output_dir / conference_dir / year_dir / output_name(args.conference, args.year)
    written, skipped = generate(args.input, output, args.conference, args.year)
    print(f"wrote {written} rows to {output}; skipped {skipped} rows outside scope")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
