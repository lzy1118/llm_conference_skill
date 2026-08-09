#!/usr/bin/env python3
"""Export three-IACR-conference primary table to paper_metadata full_output layout."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_FIELDS = [
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


def clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def output_row(row: dict[str, str]) -> dict[str, str]:
    result = {field: clean(row.get(field, "")) for field in DEFAULT_FIELDS}
    # Match the four-security-conference paper_metadata schema while keeping
    # rows country-complete when the primary-institution stage has already
    # reviewed the country.
    if not result["country"]:
        result["country"] = clean(row.get("primary_country", ""))
    return result


def export(source: Path, output_root: Path) -> dict[str, Any]:
    with source.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [output_row(row) for row in reader]

    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in rows:
        conference = clean(row["conference"]).casefold()
        year = clean(row["year"])
        if not conference or not year:
            continue
        grouped.setdefault((conference, year), []).append(row)

    outputs = []
    for (conference, year), group_rows in sorted(grouped.items()):
        target_dir = output_root / conference / year / f"author_metadata_dataset_{year}"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / "paper_metadata.csv"
        with target.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=DEFAULT_FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(group_rows)
        outputs.append({
            "conference": conference,
            "year": year,
            "rows": len(group_rows),
            "output": str(target),
        })

    report = {
        "source": str(source),
        "output_root": str(output_root),
        "source_rows": len(rows),
        "written_rows": sum(item["rows"] for item in outputs),
        "files": len(outputs),
        "missing_country_rows": sum(not row["country"] for row in rows),
        "by_conference_year": outputs,
        "fieldnames": DEFAULT_FIELDS,
        "conference_counts": dict(Counter(row["conference"] for row in rows)),
    }
    report_path = output_root / "crypto_2020_2025_full_output_export_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report["report"] = str(report_path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("generated-data/full_output"))
    args = parser.parse_args()
    report = export(args.source, args.output_root)
    print(json.dumps({
        "source_rows": report["source_rows"],
        "written_rows": report["written_rows"],
        "files": report["files"],
        "missing_country_rows": report["missing_country_rows"],
        "report": report["report"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
