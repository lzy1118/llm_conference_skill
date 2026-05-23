from __future__ import annotations

# Legacy compatibility script.
#
# This file preserves the historical US-named merge entrypoint for enriched
# compatibility outputs. Prefer `merge_resolved_rows.py` as the neutral wrapper
# when documenting or invoking this flow going forward.

import argparse
import csv
from pathlib import Path

from openpyxl import Workbook


MAIN_FIELDS = ["name", "year", "article_tag", "author_order", "inst"]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def row_key(row: dict[str, str]) -> tuple[str, str, str, str, str]:
    return tuple(row.get(field, "") for field in MAIN_FIELDS)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MAIN_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_xlsx(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "英文版"
    sheet.append(MAIN_FIELDS)
    for row in rows:
        sheet.append([row.get(field, "") for field in MAIN_FIELDS])
    workbook.save(path)


def merge_rows(base_rows: list[dict[str, str]], candidate_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    merged = []
    seen = set()
    for row in [*base_rows, *candidate_rows]:
        key = row_key(row)
        if key in seen:
            continue
        seen.add(key)
        merged.append({field: row.get(field, "") for field in MAIN_FIELDS})
    return merged


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=Path("data/output/2025-2026三大密码会_美国机构.csv"))
    parser.add_argument("--candidates", type=Path, default=Path("data/resolution/merge_candidates_us_rows.csv"))
    parser.add_argument("--output-csv", type=Path, default=Path("data/output/2025-2026三大密码会_美国机构_enriched.csv"))
    parser.add_argument("--output-xlsx", type=Path, default=Path("data/output/2025-2026三大密码会_美国机构_enriched.xlsx"))
    args = parser.parse_args()

    rows = merge_rows(read_csv(args.base), read_csv(args.candidates))
    write_csv(args.output_csv, rows)
    write_xlsx(args.output_xlsx, rows)
    print(f"merged_rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
