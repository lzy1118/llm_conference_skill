#!/usr/bin/env python3
"""
合并某个会议多个年份的年度 paper_metadata.csv。

默认输入结构：
  data/{conference}_full_output/author_metadata_dataset_{year}/paper_metadata.csv

示例：
  python scripts/merge_yearly_metadata.py eurocrypt20-25
  python scripts/merge_yearly_metadata.py crypto23
  python scripts/merge_yearly_metadata.py --conference eurocrypt --years 2020-2025

默认输出：
  data/{conference}.csv
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"

OUTPUT_FIELDS = [
    "year",
    "conference",
    "title",
    "author",
    "author_rank",
    "affiliations",
    "emails",
    "first_author",
    "co_first_author",
    "corresponding",
    "equal_contribution",
]


def parse_years(value: str) -> list[int]:
    value = value.strip()
    if "-" in value:
        start, end = value.split("-", 1)
        return list(range(int(start), int(end) + 1))
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def normalize_year(value: str) -> int:
    year = int(value)
    if year < 100:
        return 2000 + year
    return year


def parse_source_spec(value: str) -> tuple[str, list[int]]:
    match = re.fullmatch(r"([A-Za-z_&-]+)(\d{2,4})(?:-(\d{2,4}))?", value.strip())
    if not match:
        raise ValueError(
            "source spec must look like eurocrypt20-25, crypto20-25, or crypto23"
        )

    conference = match.group(1).strip("_-")
    start = normalize_year(match.group(2))
    end = normalize_year(match.group(3)) if match.group(3) else start
    if end < start:
        raise ValueError(f"end year {end} is before start year {start}")
    return conference, list(range(start, end + 1))


def merge_yearly_metadata(
    data_dir: Path,
    conference: str,
    years: list[int],
    output_path: Path,
    input_root: Path | None = None,
) -> int:
    rows: list[dict[str, str]] = []
    root = input_root or (data_dir / f"{conference}_full_output")

    for year in years:
        src = root / f"author_metadata_dataset_{year}" / "paper_metadata.csv"
        if not src.exists():
            raise FileNotFoundError(f"missing yearly metadata: {src}")

        with src.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                normalized = {field: row.get(field, "") for field in OUTPUT_FIELDS}
                normalized["conference"] = normalized["conference"] or conference
                normalized["year"] = normalized["year"] or str(year)
                rows.append(normalized)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge yearly paper_metadata.csv files.")
    parser.add_argument(
        "source_spec",
        nargs="?",
        help="Compact source spec, e.g. eurocrypt20-25, crypto20-25, or crypto23.",
    )
    parser.add_argument("--conference", default="", help="Conference/source name, e.g. eurocrypt.")
    parser.add_argument("--years", default="", help="Year range/list, e.g. 2020-2025 or 2020,2021.")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="Data root directory.")
    parser.add_argument("--input-root", default="", help="Override input root directory.")
    parser.add_argument("--output", default="", help="Output CSV path. Default: data/{conference}.csv")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if args.source_spec:
        conference, years = parse_source_spec(args.source_spec)
    elif args.conference and args.years:
        conference = args.conference.strip()
        years = parse_years(args.years)
    else:
        parser.error("provide either source_spec or both --conference and --years")

    input_root = Path(args.input_root) if args.input_root else None
    output_path = Path(args.output) if args.output else data_dir / f"{conference}.csv"

    count = merge_yearly_metadata(data_dir, conference, years, output_path, input_root)
    print(f"wrote {count} rows to {output_path}")


if __name__ == "__main__":
    main()
