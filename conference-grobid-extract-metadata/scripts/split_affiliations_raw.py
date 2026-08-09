#!/usr/bin/env python3
"""
拆分作者机构 CSV，保留 raw 作者元数据字段：
- 按同一作者的多机构分隔符 ; / ； 拆成多行
- 每行的 affiliations 为拆分后的单条机构字符串
- 不解析 institution / city / province / country

默认：
  输入 data/asiacrypt_raw.csv
  输出 data/asiacrypt_raw_机构拆分_raw.csv
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from author_metadata.artifacts import trailing_country


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_INPUT = PROJECT_ROOT / "data" / "asiacrypt_raw.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "asiacrypt_raw_机构拆分_raw.csv"

OUTPUT_FIELDS = [
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
]


def clean_text(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def split_affiliations(value: str | None) -> list[str]:
    return [part for part in (clean_text(x) for x in re.split(r"[;；]", value or "")) if part]


def split_csv(input_path: Path, output_path: Path) -> int:
    output_rows = []
    next_rank = {}
    with input_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            affiliations = split_affiliations(row.get("affiliations")) or [""]
            author_key = (row.get("paper_id", ""), row.get("author_rank", ""), row.get("author", ""))
            start_rank = next_rank.get(author_key, 0)
            for offset, affiliation in enumerate(affiliations):
                output_rows.append(
                    {
                        "paper_id": row.get("paper_id", ""),
                        "year": row.get("year", ""),
                        "conference": row.get("conference", ""),
                        "title": row.get("title", ""),
                        "author": row.get("author", ""),
                        "author_rank": row.get("author_rank", ""),
                        "affiliation_rank": str(start_rank + offset),
                        "affiliations": affiliation,
                        "emails": row.get("emails", ""),
                        "first_author": row.get("first_author", ""),
                        "co_first_author": row.get("co_first_author", ""),
                        "corresponding": row.get("corresponding", ""),
                        "equal_contribution": row.get("equal_contribution", ""),
                        "country": trailing_country(affiliation),
                        "orcid": row.get("orcid", ""),
                    }
                )
            next_rank[author_key] = start_rank + len(affiliations)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(output_rows)
    return len(output_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Split author affiliations while preserving raw metadata fields.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Input CSV path.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output CSV path.")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    row_count = split_csv(input_path, output_path)
    print(f"wrote {row_count} rows to {output_path}")


if __name__ == "__main__":
    main()
