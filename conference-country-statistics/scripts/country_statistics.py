from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from conference_dataset_loader import filter_rows, load_normalized_rows, write_markdown_report, write_summary_csv


def aggregate_country(rows: list[dict[str, str]]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    by_country: dict[str, dict[str, object]] = defaultdict(lambda: {
        "paper_keys": set(),
        "author_keys": set(),
        "institution_keys": set(),
        "conferences": set(),
        "years": set(),
    })
    by_conference: dict[tuple[str, str], dict[str, object]] = defaultdict(lambda: {"paper_keys": set(), "author_keys": set(), "institution_keys": set()})
    by_year: dict[tuple[str, str], dict[str, object]] = defaultdict(lambda: {"paper_keys": set(), "author_keys": set(), "institution_keys": set()})

    total_papers = {row["paper_key"] for row in rows}
    total_authors = {(row["paper_key"], row["author_key"], row["author_order"], row["country"]) for row in rows}

    for row in rows:
        country = row["country"] or "Unknown"
        key = by_country[country]
        key["paper_keys"].add(row["paper_key"])
        key["author_keys"].add((row["paper_key"], row["author_key"], row["author_order"], country))
        key["institution_keys"].add(row["institution_key"])
        key["conferences"].add(row["conference"])
        key["years"].add(row["year"])

        conference_key = (country, row["conference"])
        by_conference[conference_key]["paper_keys"].add(row["paper_key"])
        by_conference[conference_key]["author_keys"].add((row["paper_key"], row["author_key"], row["author_order"], country))
        by_conference[conference_key]["institution_keys"].add(row["institution_key"])

        year_key = (country, row["year"])
        by_year[year_key]["paper_keys"].add(row["paper_key"])
        by_year[year_key]["author_keys"].add((row["paper_key"], row["author_key"], row["author_order"], country))
        by_year[year_key]["institution_keys"].add(row["institution_key"])

    total_paper_count = max(len(total_papers), 1)
    total_author_count = max(len(total_authors), 1)

    summary = []
    for country, stats in by_country.items():
        papers = len(stats["paper_keys"])
        authors = len(stats["author_keys"])
        summary.append({
            "country": country,
            "papers": papers,
            "authors": authors,
            "institutions": len(stats["institution_keys"]),
            "paper_share": round(papers / total_paper_count, 6),
            "author_share": round(authors / total_author_count, 6),
            "avg_authors_per_paper": round(authors / papers, 6) if papers else 0.0,
            "conference_count": len(stats["conferences"]),
            "year_min": min(stats["years"]) if stats["years"] else "",
            "year_max": max(stats["years"]) if stats["years"] else "",
        })

    by_conference_rows = []
    for (country, conference), stats in by_conference.items():
        by_conference_rows.append({
            "country": country,
            "conference": conference,
            "papers": len(stats["paper_keys"]),
            "authors": len(stats["author_keys"]),
            "institutions": len(stats["institution_keys"]),
        })

    by_year_rows = []
    for (country, year), stats in by_year.items():
        by_year_rows.append({
            "country": country,
            "year": year,
            "papers": len(stats["paper_keys"]),
            "authors": len(stats["author_keys"]),
            "institutions": len(stats["institution_keys"]),
        })

    return (
        sorted(summary, key=lambda row: (-int(row["papers"]), -int(row["authors"]), str(row["country"]))),
        sorted(by_conference_rows, key=lambda row: (row["conference"], -int(row["papers"]), row["country"])),
        sorted(by_year_rows, key=lambda row: (row["year"], -int(row["papers"]), row["country"])),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate country statistics from normalized conference data.")
    parser.add_argument("--input", required=True, help="Path to normalized author_affiliation_facts.csv")
    parser.add_argument("--output-dir", required=True, help="Output analysis directory")
    parser.add_argument("--conference")
    parser.add_argument("--year")
    args = parser.parse_args()

    rows = filter_rows(load_normalized_rows(Path(args.input)), conference=args.conference, year=args.year)
    summary, by_conference, by_year = aggregate_country(rows)

    output_dir = Path(args.output_dir) / "country"
    write_summary_csv(output_dir / "country_summary.csv", summary)
    write_summary_csv(output_dir / "country_by_conference.csv", by_conference)
    write_summary_csv(output_dir / "country_by_year.csv", by_year)
    write_markdown_report(
        output_dir / "country_report.md",
        title="Country Statistics Report",
        scope={"conference": args.conference or "all", "year": args.year or "all", "rows": len(rows)},
        highlights=summary[:10],
    )


if __name__ == "__main__":
    main()
