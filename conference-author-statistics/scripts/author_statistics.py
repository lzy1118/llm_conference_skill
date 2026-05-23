from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from conference_dataset_loader import filter_rows, load_normalized_rows, write_markdown_report, write_summary_csv


def aggregate_authors(rows: list[dict[str, str]]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    grouped: dict[str, dict[str, object]] = defaultdict(lambda: {
        "author_name": "",
        "paper_keys": set(),
        "conferences": set(),
        "years": set(),
        "first_author_papers": set(),
        "coauthors": set(),
    })
    by_year: dict[tuple[str, str], set[str]] = defaultdict(set)
    first_author_rows: list[dict[str, object]] = []
    papers_to_authors: dict[str, list[dict[str, str]]] = defaultdict(list)

    for row in rows:
        key = row["author_key"] or row["name"]
        grouped[key]["author_name"] = grouped[key]["author_name"] or row["name"]
        grouped[key]["paper_keys"].add(row["paper_key"])
        grouped[key]["conferences"].add(row["conference"])
        grouped[key]["years"].add(row["year"])
        if str(row["author_order"]) == "0":
            grouped[key]["first_author_papers"].add(row["paper_key"])
        by_year[(key, row["year"])].add(row["paper_key"])
        papers_to_authors[row["paper_key"]].append(row)

    for paper_rows in papers_to_authors.values():
        unique_authors = {}
        for row in paper_rows:
            key = row["author_key"] or row["name"]
            unique_authors[key] = row["name"]
        author_keys = sorted(unique_authors)
        for author_key in author_keys:
            grouped[author_key]["coauthors"].update(other for other in author_keys if other != author_key)
        for row in paper_rows:
            if str(row["author_order"]) == "0":
                first_author_rows.append({
                    "author_key": row["author_key"] or row["name"],
                    "author_name": row["name"],
                    "paper_key": row["paper_key"],
                    "conference": row["conference"],
                    "year": row["year"],
                    "title": row["title"],
                })

    coauthor_edges: dict[tuple[str, str], dict[str, object]] = {}
    for paper_key, paper_rows in papers_to_authors.items():
        distinct = {}
        for row in paper_rows:
            distinct[row["author_key"] or row["name"]] = row["name"]
        keys = sorted(distinct)
        for index, left in enumerate(keys):
            for right in keys[index + 1:]:
                edge_key = (left, right)
                edge = coauthor_edges.setdefault(edge_key, {
                    "author_key_1": left,
                    "author_name_1": distinct[left],
                    "author_key_2": right,
                    "author_name_2": distinct[right],
                    "shared_papers": 0,
                })
                edge["shared_papers"] += 1

    summary = []
    for author_key, entry in grouped.items():
        summary.append({
            "author_key": author_key,
            "author_name": entry["author_name"],
            "papers": len(entry["paper_keys"]),
            "conferences": len(entry["conferences"]),
            "years_active": len(entry["years"]),
            "first_author_papers": len(entry["first_author_papers"]),
            "coauthor_count": len(entry["coauthors"]),
            "year_first": min(entry["years"]) if entry["years"] else "",
            "year_last": max(entry["years"]) if entry["years"] else "",
        })

    author_by_year = [
        {
            "author_key": author_key,
            "year": year,
            "papers": len(papers),
        }
        for (author_key, year), papers in by_year.items()
    ]
    return (
        sorted(summary, key=lambda row: (-int(row["papers"]), -int(row["first_author_papers"]), str(row["author_name"]))),
        sorted(author_by_year, key=lambda row: (row["year"], -int(row["papers"]), row["author_key"])),
        sorted(first_author_rows, key=lambda row: (row["year"], row["conference"], row["author_name"])),
        sorted(coauthor_edges.values(), key=lambda row: (-int(row["shared_papers"]), row["author_name_1"], row["author_name_2"])),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate author statistics from normalized conference data.")
    parser.add_argument("--input", required=True, help="Path to normalized author_affiliation_facts.csv")
    parser.add_argument("--output-dir", required=True, help="Output analysis directory")
    parser.add_argument("--conference")
    parser.add_argument("--year")
    args = parser.parse_args()

    rows = filter_rows(load_normalized_rows(Path(args.input)), conference=args.conference, year=args.year)
    summary, by_year, first_author_rows, coauthor_edges = aggregate_authors(rows)
    output_dir = Path(args.output_dir) / "authors"
    write_summary_csv(output_dir / "author_summary.csv", summary)
    write_summary_csv(output_dir / "author_by_year.csv", by_year)
    write_summary_csv(output_dir / "first_author_summary.csv", first_author_rows)
    write_summary_csv(output_dir / "coauthor_edges.csv", coauthor_edges)
    write_markdown_report(
        output_dir / "author_report.md",
        title="Author Statistics Report",
        scope={"conference": args.conference or "all", "year": args.year or "all", "rows": len(rows)},
        highlights=summary[:10],
    )


if __name__ == "__main__":
    main()
