#!/usr/bin/env python3
"""Query papers, authors, and institutions associated with a country or region."""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path


PAPER_FIELDS = ["paper_key", "conference", "year", "title", "all_authors"]
AUTHOR_FIELDS = [
    "paper_key", "conference", "year", "title", "author_key", "author",
    "author_order", "institutions", "country",
]
INSTITUTION_FIELDS = ["paper_key", "conference", "year", "title", "institution_key", "institution", "country"]


def normalized_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").casefold()
    return re.sub(r"\s+", " ", text).strip()


def split_composite_label(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s*[|;]\s*", value or "") if part.strip()]


def is_authoritative_institution_identity(value: str) -> bool:
    identity = (value or "").strip()
    return bool(
        re.fullmatch(r"https?://ror\.org/[0-9a-z]+", identity, flags=re.IGNORECASE)
        or re.fullmatch(r"INST\d+", identity, flags=re.IGNORECASE)
        or re.fullmatch(r"institution:[0-9a-f]{8,}", identity, flags=re.IGNORECASE)
    )


def expand_resolved_country_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Expand country components that occur as known singleton labels."""
    candidates: dict[str, set[str]] = defaultdict(set)
    institution_country_candidates: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        components = split_composite_label(row.get("country", ""))
        if len(components) == 1 and normalized_text(components[0]) not in {"", "unknown"}:
            candidates[normalized_text(components[0])].add(components[0])
            identities = split_composite_label(row.get("institution_id", "") or row.get("institution_key", ""))
            if len(identities) == 1:
                institution_country_candidates[identities[0]].add(components[0])
    registry = {key: next(iter(values)) for key, values in candidates.items() if len(values) == 1}
    institution_country_registry = {
        identity: next(iter(values))
        for identity, values in institution_country_candidates.items()
        if len(values) == 1
    }
    expanded: list[dict[str, str]] = []
    for row in rows:
        components = split_composite_label(row.get("country", ""))
        if len(components) < 2:
            expanded.append(row)
            continue
        resolved = [
            (index, registry.get(normalized_text(component)))
            for index, component in enumerate(components)
        ]
        resolved = [(index, component) for index, component in resolved if component]
        if not resolved:
            continue
        institution_names = split_composite_label(institution_display(row))
        institution_ids = split_composite_label(row.get("institution_id", "") or row.get("institution_key", ""))
        aligned_institutions = len(institution_names) == len(components) and len(institution_names) > 1
        if not aligned_institutions and len(institution_ids) == 1:
            canonical_country = institution_country_registry.get(institution_ids[0])
            if canonical_country:
                split_row = dict(row)
                split_row["country"] = canonical_country
                expanded.append(split_row)
            continue
        for index, country in resolved:
            split_row = dict(row)
            split_row["country"] = country
            if aligned_institutions:
                institution_name = institution_names[index]
                split_row["canonical_institution_name"] = institution_name
                split_row["inst"] = institution_name
                if len(institution_ids) == len(components):
                    split_row["institution_id"] = institution_ids[index]
                    split_row["institution_key"] = institution_ids[index]
                else:
                    split_row["institution_key"] = institution_name
            expanded.append(split_row)
    return expanded


def author_identity(row: dict[str, str]) -> str:
    return row.get("author_key", "").strip() or f"name:{normalized_text(row.get('name', ''))}"


def institution_identity(row: dict[str, str]) -> str:
    display = institution_display(row)
    return row.get("institution_key", "").strip() or f"institution:{normalized_text(display)}"


def institution_display(row: dict[str, str]) -> str:
    return row.get("canonical_institution_name", "").strip() or row.get("inst", "").strip()


def institution_components(
    row: dict[str, str], known_institutions: set[str] | None = None
) -> list[tuple[str, str]]:
    names = split_composite_label(institution_display(row))
    ids = split_composite_label(row.get("institution_id", "") or row.get("institution_key", ""))
    if len(names) > 1 and len(names) == len(ids):
        return list(dict.fromkeys(
            (identity, name)
            for identity, name in zip(ids, names)
            if identity and (is_authoritative_institution_identity(identity) or identity in (known_institutions or set()))
        ))
    if len(names) == 1:
        identity = ids[0] if len(ids) == 1 else institution_identity(row)
        return [(identity, names[0])]
    return []


def order_key(row: dict[str, str]) -> tuple[int, str, str]:
    value = row.get("author_order", "").strip()
    try:
        numeric = int(value)
    except ValueError:
        numeric = 10**9
    return numeric, value, row.get("name", "")


def filter_scope(
    rows: list[dict[str, str]], conference: str | None, year: str | None
) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if (conference is None or row.get("conference", "") == conference)
        and (year is None or row.get("year", "") == str(year))
    ]


def query_country(
    rows: list[dict[str, str]],
    *,
    country: str,
    conference: str | None = None,
    year: str | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    target = normalized_text(country)
    if not target:
        raise ValueError("country must not be empty")

    scoped = expand_resolved_country_rows(filter_scope(rows, conference, year))
    known_institutions = {
        identity
        for row in scoped
        if len(split_composite_label(institution_display(row))) == 1
        for identity in split_composite_label(row.get("institution_id", "") or row.get("institution_key", ""))
    }
    matched = [row for row in scoped if normalized_text(row.get("country", "")) == target]
    matched_paper_keys = {row.get("paper_key", "") for row in matched if row.get("paper_key", "")}
    paper_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in scoped:
        if row.get("paper_key", "") in matched_paper_keys:
            paper_rows[row["paper_key"]].append(row)

    papers: list[dict[str, object]] = []
    authors: list[dict[str, object]] = []
    institutions: list[dict[str, object]] = []
    for paper_key, rows_for_paper in paper_rows.items():
        sample = rows_for_paper[0]
        ordered_authors: dict[str, dict[str, str]] = {}
        for row in sorted(rows_for_paper, key=order_key):
            ordered_authors.setdefault(author_identity(row), row)
        papers.append({
            "paper_key": paper_key,
            "conference": sample.get("conference", ""),
            "year": sample.get("year", ""),
            "title": sample.get("title", ""),
            "all_authors": " | ".join(row.get("name", "").strip() for row in ordered_authors.values()),
        })

        selected_rows = [row for row in rows_for_paper if normalized_text(row.get("country", "")) == target]
        selected_authors: dict[str, dict[str, str]] = {}
        author_institutions: dict[str, dict[str, str]] = defaultdict(dict)
        selected_institutions: dict[str, dict[str, str]] = {}
        for row in sorted(selected_rows, key=order_key):
            author_key = author_identity(row)
            selected_authors.setdefault(author_key, row)
            for institution_key, institution_name in institution_components(row, known_institutions):
                if institution_key not in author_institutions[author_key] or row.get("canonical_institution_name", "").strip():
                    author_institutions[author_key][institution_key] = institution_name
                has_canonical_name = bool(row.get("canonical_institution_name", "").strip())
                if (
                    institution_key not in selected_institutions
                    or not selected_institutions[institution_key].get("_has_canonical_name")
                    and has_canonical_name
                ):
                    institution_row = dict(row)
                    institution_row["institution_key"] = institution_key
                    institution_row["institution_id"] = institution_key
                    institution_row["inst"] = institution_name
                    institution_row["canonical_institution_name"] = institution_name
                    institution_row["_has_canonical_name"] = has_canonical_name
                    selected_institutions[institution_key] = institution_row
        for identity, row in selected_authors.items():
            authors.append({
                "paper_key": paper_key,
                "conference": sample.get("conference", ""),
                "year": sample.get("year", ""),
                "title": sample.get("title", ""),
                "author_key": identity,
                "author": row.get("name", "").strip(),
                "author_order": row.get("author_order", "").strip(),
                "institutions": " | ".join(author_institutions[identity].values()),
                "country": row.get("country", "").strip(),
            })
        for identity, row in selected_institutions.items():
            institutions.append({
                "paper_key": paper_key,
                "conference": sample.get("conference", ""),
                "year": sample.get("year", ""),
                "title": sample.get("title", ""),
                "institution_key": identity,
                "institution": institution_display(row),
                "country": row.get("country", "").strip(),
            })

    paper_sort = lambda row: (str(row["year"]), str(row["conference"]), str(row["title"]), str(row["paper_key"]))
    papers.sort(key=paper_sort)
    authors.sort(key=lambda row: (*paper_sort(row), order_key({"author_order": str(row["author_order"]), "name": str(row["author"])})))
    institutions.sort(key=lambda row: (*paper_sort(row), str(row["institution"]), str(row["institution_key"])))
    summary: dict[str, object] = {
        "query": country,
        "conference_filter": conference,
        "year_filter": year,
        "input_fact_rows": len(rows),
        "scoped_fact_rows": len(scoped),
        "matched_fact_rows": len(matched),
        "paper_count": len(papers),
        "associated_author_count": len({str(row["author_key"]) for row in authors}),
        "associated_institution_count": len({str(row["institution_key"]) for row in institutions}),
        "attribution_policy": "Papers retain complete author context; only matched fact rows determine associated authors and institutions.",
    }
    return papers, authors, institutions, summary


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
    parser.add_argument("--country", required=True, help="Exact country or region after whitespace and case normalization")
    parser.add_argument("--conference")
    parser.add_argument("--year")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    papers, authors, institutions, summary = query_country(
        read_csv(Path(args.input)),
        country=args.country,
        conference=args.conference,
        year=args.year,
    )
    output_dir = Path(args.output_dir)
    write_csv(output_dir / "country_papers.csv", PAPER_FIELDS, papers)
    write_csv(output_dir / "country_authors.csv", AUTHOR_FIELDS, authors)
    write_csv(output_dir / "country_institutions.csv", INSTITUTION_FIELDS, institutions)
    (output_dir / "country_query_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
