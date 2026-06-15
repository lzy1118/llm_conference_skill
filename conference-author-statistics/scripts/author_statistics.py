from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import re

from conference_dataset_loader import filter_rows, load_normalized_rows, write_markdown_report, write_summary_csv


def normalize_author_display_name(name: str) -> str:
    text = name.strip()
    if not text:
        return ""
    return re.sub(r"\s0+\d+$", "", text).strip()


def simplified_author_name(value: str) -> str:
    text = re.sub(r"[^a-z0-9 ]+", " ", value.casefold())
    parts = [part for part in text.split() if part]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0][0]} {' '.join(parts[1:])}"


def has_initial_fullname_pair(names: set[str]) -> bool:
    parsed = []
    for name in names:
        parts = [part for part in re.sub(r"[^A-Za-z0-9 ]+", " ", name).split() if part]
        if len(parts) >= 2:
            parsed.append(parts)
    for left in parsed:
        for right in parsed:
            if left == right:
                continue
            if left[-1].casefold() != right[-1].casefold():
                continue
            if len(left[0]) == 1 and right[0].casefold().startswith(left[0].casefold()):
                return True
    return False


def build_identity_review(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    by_display: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    by_simplified: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    for row in rows:
        author_name = normalize_author_display_name(row.get("name", "").strip())
        author_key = row.get("author_key", "").strip() or author_name
        display_key = author_name.casefold()
        simplified_key = simplified_author_name(author_name)
        for bucket_key, bucket in ((display_key, by_display), (simplified_key, by_simplified)):
            if not bucket_key:
                continue
            entry = bucket[bucket_key]
            entry["author_keys"].add(author_key)
            entry["author_names"].add(author_name)
            entry["papers"].add(row.get("paper_key", ""))
            entry["conferences"].add(row.get("conference", ""))
            entry["years"].add(row.get("year", ""))
            if row.get("country"):
                entry["countries"].add(row.get("country", ""))
            if row.get("canonical_institution_name") or row.get("inst"):
                entry["institutions"].add(row.get("canonical_institution_name", "") or row.get("inst", ""))

    review_rows: list[dict[str, object]] = []
    for display_key, entry in by_display.items():
        if len(entry["author_keys"]) <= 1:
            continue
        review_rows.append(
            {
                "identity_cluster_key": display_key,
                "issue_type": "same_display_name_multiple_author_keys",
                "author_names": " | ".join(sorted(entry["author_names"])),
                "author_keys": " | ".join(sorted(entry["author_keys"])),
                "papers": len(entry["papers"]),
                "conferences": " | ".join(sorted(entry["conferences"])),
                "years": " | ".join(sorted(entry["years"])),
                "countries": " | ".join(sorted(entry["countries"])),
                "institutions": " | ".join(sorted(entry["institutions"])[:12]),
                "needs_review": "true",
            }
        )

    for simplified_key, entry in by_simplified.items():
        if len(entry["author_names"]) <= 1:
            continue
        if not has_initial_fullname_pair(entry["author_names"]):
            continue
        review_rows.append(
            {
                "identity_cluster_key": simplified_key,
                "issue_type": "same_initial_last_name_multiple_display_names",
                "author_names": " | ".join(sorted(entry["author_names"])),
                "author_keys": " | ".join(sorted(entry["author_keys"])),
                "papers": len(entry["papers"]),
                "conferences": " | ".join(sorted(entry["conferences"])),
                "years": " | ".join(sorted(entry["years"])),
                "countries": " | ".join(sorted(entry["countries"])),
                "institutions": " | ".join(sorted(entry["institutions"])[:12]),
                "needs_review": "true",
            }
        )
    return sorted(review_rows, key=lambda row: (-int(row["papers"]), str(row["identity_cluster_key"])))


def aggregate_authors(rows: list[dict[str, str]]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
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
        grouped[key]["author_name"] = grouped[key]["author_name"] or normalize_author_display_name(row["name"])
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
                    "author_name": normalize_author_display_name(row["name"]),
                    "paper_key": row["paper_key"],
                    "conference": row["conference"],
                    "year": row["year"],
                    "title": row["title"],
                })

    coauthor_edges: dict[tuple[str, str], dict[str, object]] = {}
    for paper_key, paper_rows in papers_to_authors.items():
        distinct = {}
        for row in paper_rows:
            distinct[row["author_key"] or row["name"]] = normalize_author_display_name(row["name"])
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
            "author_name": normalize_author_display_name(str(entry["author_name"])),
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
        build_identity_review(rows),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate author statistics from normalized conference data.")
    parser.add_argument("--input", required=True, help="Path to normalized author_affiliation_facts.csv")
    parser.add_argument("--output-dir", required=True, help="Output analysis directory")
    parser.add_argument("--conference")
    parser.add_argument("--year")
    args = parser.parse_args()

    rows = filter_rows(load_normalized_rows(Path(args.input)), conference=args.conference, year=args.year)
    summary, by_year, first_author_rows, coauthor_edges, identity_review = aggregate_authors(rows)
    output_dir = Path(args.output_dir) / "authors"
    write_summary_csv(output_dir / "author_summary.csv", summary)
    write_summary_csv(output_dir / "author_by_year.csv", by_year)
    write_summary_csv(output_dir / "first_author_summary.csv", first_author_rows)
    write_summary_csv(output_dir / "coauthor_edges.csv", coauthor_edges)
    write_summary_csv(output_dir / "author_identity_review.csv", identity_review)
    write_markdown_report(
        output_dir / "author_report.md",
        title="Author Statistics Report",
        scope={"conference": args.conference or "all", "year": args.year or "all", "rows": len(rows)},
        highlights=summary[:10],
    )


if __name__ == "__main__":
    main()
