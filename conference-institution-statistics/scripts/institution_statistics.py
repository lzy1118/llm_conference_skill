from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import re

from conference_dataset_loader import filter_rows, load_normalized_rows, write_markdown_report, write_summary_csv


def normalize_institution_display_name(raw_name: str, canonical_name: str) -> str:
    preferred = (canonical_name or "").strip() or (raw_name or "").strip()
    if not preferred:
        return ""
    text = preferred.replace("&amp;", "&").strip()
    text = re.sub(r"^\*+\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def aggregate_institutions(rows: list[dict[str, str]]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    grouped: dict[str, dict[str, object]] = defaultdict(lambda: {
        "institution_id": "",
        "institution_name": "",
        "country": "",
        "paper_keys": set(),
        "author_rows": set(),
        "first_author_papers": set(),
        "conferences": set(),
        "years": set(),
    })
    by_conference: dict[tuple[str, str], set[str]] = defaultdict(set)
    by_year: dict[tuple[str, str], set[str]] = defaultdict(set)

    total_papers = {row["paper_key"] for row in rows}
    total_paper_count = max(len(total_papers), 1)

    for row in rows:
        key = (row.get("institution_id", "") or row["institution_key"]).strip()
        entry = grouped[key]
        entry["institution_id"] = entry["institution_id"] or row.get("institution_id", "")
        entry["institution_name"] = entry["institution_name"] or normalize_institution_display_name(
            row.get("inst", ""),
            row.get("canonical_institution_name", ""),
        )
        entry["country"] = entry["country"] or row["country"]
        entry["paper_keys"].add(row["paper_key"])
        entry["author_rows"].add((row["paper_key"], row["author_key"], row["author_order"], key))
        entry["conferences"].add(row["conference"])
        entry["years"].add(row["year"])
        if str(row["author_order"]) == "0":
            entry["first_author_papers"].add(row["paper_key"])
        by_conference[(key, row["conference"])].add(row["paper_key"])
        by_year[(key, row["year"])].add(row["paper_key"])

    summary = []
    for institution_key, entry in grouped.items():
        papers = len(entry["paper_keys"])
        summary.append({
            "institution_key": institution_key,
            "institution_id": entry["institution_id"],
            "institution_name": entry["institution_name"],
            "country": entry["country"],
            "papers": papers,
            "authors": len(entry["author_rows"]),
            "first_author_papers": len(entry["first_author_papers"]),
            "conferences": len(entry["conferences"]),
            "years_active": len(entry["years"]),
            "paper_share": round(papers / total_paper_count, 6),
        })

    conference_rows = [
        {
            "institution_key": institution_key,
            "conference": conference,
            "papers": len(papers),
        }
        for (institution_key, conference), papers in by_conference.items()
    ]
    year_rows = [
        {
            "institution_key": institution_key,
            "year": year,
            "papers": len(papers),
        }
        for (institution_key, year), papers in by_year.items()
    ]
    return (
        sorted(summary, key=lambda row: (-int(row["papers"]), -int(row["authors"]), str(row["institution_name"]))),
        sorted(conference_rows, key=lambda row: (row["conference"], -int(row["papers"]), row["institution_key"])),
        sorted(year_rows, key=lambda row: (row["year"], -int(row["papers"]), row["institution_key"])),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate institution statistics from normalized conference data.")
    parser.add_argument("--input", required=True, help="Path to normalized author_affiliation_facts.csv")
    parser.add_argument("--output-dir", required=True, help="Output analysis directory")
    parser.add_argument("--conference")
    parser.add_argument("--year")
    parser.add_argument("--country")
    args = parser.parse_args()

    rows = filter_rows(load_normalized_rows(Path(args.input)), conference=args.conference, year=args.year)
    if args.country:
        rows = [row for row in rows if row.get("country") == args.country]

    summary, by_conference, by_year = aggregate_institutions(rows)
    output_dir = Path(args.output_dir) / "institutions"
    write_summary_csv(output_dir / "institution_summary.csv", summary)
    write_summary_csv(output_dir / "institution_by_conference.csv", by_conference)
    write_summary_csv(output_dir / "institution_by_year.csv", by_year)
    write_markdown_report(
        output_dir / "institution_report.md",
        title="Institution Statistics Report",
        scope={
            "conference": args.conference or "all",
            "year": args.year or "all",
            "country": args.country or "all",
            "rows": len(rows),
        },
        highlights=summary[:10],
    )


if __name__ == "__main__":
    main()
