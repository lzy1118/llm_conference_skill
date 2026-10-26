#!/usr/bin/env python3
"""Query one author's papers, collaborators, and first-author papers."""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path


PAPER_FIELDS = [
    "paper_key", "conference", "year", "title", "author_order", "is_first_author",
]
COLLABORATOR_FIELDS = ["author_key", "author", "shared_papers"]


def normalized_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").casefold()
    return re.sub(r"\s+", " ", text).strip()


def compact_author_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", normalized_text(value))


def author_identity(row: dict[str, str]) -> str:
    return row.get("author_key", "").strip() or f"name:{normalized_text(row.get('name', ''))}"


def author_order_value(row: dict[str, str]) -> tuple[int, str]:
    value = row.get("author_order", "").strip()
    try:
        return int(value), value
    except ValueError:
        return 10**9, value


def filter_scope(
    rows: list[dict[str, str]], conference: str | None, year: str | None
) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if (conference is None or row.get("conference", "") == conference)
        and (year is None or row.get("year", "") == str(year))
    ]


def query_author(
    rows: list[dict[str, str]],
    *,
    author: str | None = None,
    author_key: str | None = None,
    conference: str | None = None,
    year: str | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    if bool(author) == bool(author_key):
        raise ValueError("Provide exactly one of author or author_key")

    scoped = filter_scope(rows, conference, year)
    if author_key:
        matched = [row for row in scoped if row.get("author_key", "").strip() == author_key]
        match_mode = "author_key"
    else:
        query_name = normalized_text(author or "")
        matched = [row for row in scoped if normalized_text(row.get("name", "")) == query_name]
        match_mode = "normalized_display_name"
        if not matched and query_name:
            compact_query = compact_author_name(query_name)
            matched = [
                row for row in scoped
                if compact_author_name(row.get("name", "")) == compact_query
            ]
            if matched:
                match_mode = "compact_author_name"

    matched_keys = sorted({author_identity(row) for row in matched})
    matched_paper_keys = {row.get("paper_key", "") for row in matched if row.get("paper_key", "")}
    matched_orders: dict[str, tuple[int, str]] = {}
    for row in matched:
        paper_key = row.get("paper_key", "")
        order = author_order_value(row)
        if paper_key and (paper_key not in matched_orders or order < matched_orders[paper_key]):
            matched_orders[paper_key] = order

    paper_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in scoped:
        if row.get("paper_key", "") in matched_paper_keys:
            paper_rows[row["paper_key"]].append(row)

    papers: list[dict[str, object]] = []
    collaborator_papers: dict[str, set[str]] = defaultdict(set)
    collaborator_names: dict[str, str] = {}
    for paper_key, rows_for_paper in paper_rows.items():
        sample = rows_for_paper[0]
        target_order_info = matched_orders.get(paper_key, (10**9, ""))
        target_order = target_order_info[1]
        papers.append({
            "paper_key": paper_key,
            "conference": sample.get("conference", ""),
            "year": sample.get("year", ""),
            "title": sample.get("title", ""),
            "author_order": target_order,
            "is_first_author": str(target_order_info[0] == 0).lower(),
        })
        for row in rows_for_paper:
            identity = author_identity(row)
            if identity in matched_keys:
                continue
            collaborator_names.setdefault(identity, row.get("name", "").strip())
            collaborator_papers[identity].add(paper_key)

    papers.sort(key=lambda row: (str(row["year"]), str(row["conference"]), str(row["title"]), str(row["paper_key"])))
    first_author_papers = [row.copy() for row in papers if row["is_first_author"] == "true"]
    collaborators = [
        {"author_key": key, "author": collaborator_names[key], "shared_papers": len(paper_keys)}
        for key, paper_keys in collaborator_papers.items()
    ]
    collaborators.sort(key=lambda row: (-int(row["shared_papers"]), str(row["author"]), str(row["author_key"])))

    summary: dict[str, object] = {
        "match_mode": match_mode,
        "query": author_key or author or "",
        "conference_filter": conference,
        "year_filter": year,
        "input_fact_rows": len(rows),
        "scoped_fact_rows": len(scoped),
        "matched_fact_rows": len(matched),
        "matched_author_keys": matched_keys,
        "identity_ambiguous": len(matched_keys) > 1,
        "paper_count": len(papers),
        "collaborator_count": len(collaborators),
        "first_author_paper_count": len(first_author_papers),
        "identity_policy": "Stable author_key when supplied; otherwise normalized full display name. No ORCID-level disambiguation.",
    }
    return papers, collaborators, first_author_papers, summary


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Path to author_affiliation_facts.csv")
    query = parser.add_mutually_exclusive_group(required=True)
    query.add_argument("--author", help="Exact full display name after whitespace and case normalization")
    query.add_argument("--author-key", help="Exact stable author key")
    parser.add_argument("--conference")
    parser.add_argument("--year")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    papers, collaborators, first_author_papers, summary = query_author(
        read_csv(Path(args.input)),
        author=args.author,
        author_key=args.author_key,
        conference=args.conference,
        year=args.year,
    )
    output_dir = Path(args.output_dir)
    write_csv(output_dir / "author_papers.csv", PAPER_FIELDS, papers)
    write_csv(output_dir / "author_collaborators.csv", COLLABORATOR_FIELDS, collaborators)
    write_csv(output_dir / "author_first_author_papers.csv", PAPER_FIELDS, first_author_papers)
    (output_dir / "author_query_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
