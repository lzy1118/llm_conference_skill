from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from analytics_common import (
    choose_display_name,
    ensure_directory,
    infer_country,
    normalize_author_key,
    normalize_institution_key,
    normalize_paper_key,
    normalize_whitespace,
    read_csv_rows,
    split_institutions,
    stable_key,
    write_csv_rows,
    write_json,
)


CANONICAL_FIELDS = {
    "author": "name",
    "author_name": "name",
    "institution": "inst",
    "affiliation": "inst",
    "venue": "conference",
    "conf": "conference",
    "paper_title": "title",
    "position": "author_order",
}


def remap_row(row: dict[str, str]) -> dict[str, str]:
    remapped: dict[str, str] = {}
    for key, value in row.items():
        normalized_key = CANONICAL_FIELDS.get(key.strip().lower(), key.strip().lower())
        remapped[normalized_key] = value
    return remapped


def collect_input_rows(inputs: list[Path]) -> tuple[list[dict[str, str]], list[str]]:
    rows: list[dict[str, str]] = []
    input_files: list[str] = []
    for path in inputs:
        input_files.append(str(path))
        rows.extend(remap_row(row) for row in read_csv_rows(path))
    return rows, input_files


def build_normalized_tables(rows: list[dict[str, str]]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    author_rows: list[dict[str, object]] = []
    paper_index: dict[str, dict[str, object]] = {}
    institution_rows: dict[str, list[dict[str, object]]] = defaultdict(list)
    duplicate_row_keys = 0
    seen_row_keys: set[str] = set()

    for row in rows:
        conference = normalize_whitespace(row.get("conference", ""))
        year = normalize_whitespace(row.get("year", ""))
        title = normalize_whitespace(row.get("title", ""))
        paper_id = normalize_whitespace(row.get("paper_id", ""))
        article_tag = normalize_whitespace(row.get("article_tag", ""))
        name = normalize_whitespace(row.get("name", ""))
        author_order_text = normalize_whitespace(row.get("author_order", ""))
        inst_value = normalize_whitespace(row.get("inst", ""))
        source_country = normalize_whitespace(row.get("country", ""))
        classification_source = normalize_whitespace(row.get("classification_source", ""))
        classification_confidence = normalize_whitespace(row.get("classification_confidence", ""))
        classification_reason = normalize_whitespace(row.get("classification_reason", ""))
        is_us = normalize_whitespace(row.get("is_us_institution", ""))

        paper_key = normalize_paper_key(conference, year, title, paper_id)
        author_key = normalize_author_key(name)

        # Extraction backends may already emit one expanded row per author-affiliation with
        # a resolved country. Preserve that contract instead of splitting and re-inferring.
        if source_country:
            institutions = [inst_value]
        else:
            institutions = split_institutions(inst_value) or [inst_value]

        paper_entry = paper_index.setdefault(
            paper_key,
            {
                "paper_key": paper_key,
                "conference": conference,
                "year": year,
                "title": title,
                "article_tag": article_tag,
                "paper_id": paper_id,
                "author_count": 0,
            },
        )
        paper_entry["author_count"] = max(int(paper_entry["author_count"]), int(author_order_text or "0") + 1)

        for institution in institutions:
            institution_key = normalize_institution_key(institution)
            country = source_country or infer_country(institution, is_us)
            row_key = stable_key(paper_key, author_order_text, institution_key)
            if row_key in seen_row_keys:
                duplicate_row_keys += 1
                continue
            seen_row_keys.add(row_key)

            normalized_row = {
                "row_key": row_key,
                "paper_key": paper_key,
                "conference": conference,
                "year": year,
                "title": title,
                "article_tag": article_tag,
                "paper_id": paper_id,
                "name": name,
                "author_key": author_key,
                "author_order": int(author_order_text or "0"),
                "inst": institution,
                "institution_key": institution_key,
                "country": country,
                "is_us_institution": is_us.lower() == "true",
                "classification_source": classification_source,
                "classification_confidence": classification_confidence,
                "classification_reason": classification_reason,
            }
            author_rows.append(normalized_row)
            institution_rows[institution_key].append(normalized_row)

    paper_facts = sorted(paper_index.values(), key=lambda row: (row["conference"], row["year"], row["title"]))
    institution_dim: list[dict[str, object]] = []
    for institution_key, grouped_rows in institution_rows.items():
        countries = {str(row["country"]) for row in grouped_rows if str(row["country"])}
        display_names = [str(row["inst"]) for row in grouped_rows]
        institution_dim.append(
            {
                "institution_key": institution_key,
                "inst_display": choose_display_name(display_names),
                "country": choose_display_name(sorted(countries)),
                "is_us_institution": any(bool(row["is_us_institution"]) for row in grouped_rows),
                "source_count": len(grouped_rows),
                "needs_review": "Unknown" in countries,
            }
        )

    report = {
        "input_rows": len(rows),
        "normalized_rows": len(author_rows),
        "paper_count": len(paper_facts),
        "institution_count": len(institution_dim),
        "duplicate_row_keys_skipped": duplicate_row_keys,
        "rows_missing_name": sum(1 for row in author_rows if not row["name"]),
        "rows_missing_inst": sum(1 for row in author_rows if not row["inst"]),
        "rows_with_unknown_country": sum(1 for row in author_rows if row["country"] == "Unknown"),
    }
    return author_rows, paper_facts, sorted(institution_dim, key=lambda row: str(row["inst_display"])), report


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize conference datasets for downstream analytics.")
    parser.add_argument("inputs", nargs="+", help="Input CSV files with author affiliation rows")
    parser.add_argument("--output-dir", required=True, help="Output analysis root directory")
    args = parser.parse_args()

    input_paths = [Path(value) for value in args.inputs]
    output_dir = Path(args.output_dir) / "normalized"
    ensure_directory(output_dir)

    rows, input_files = collect_input_rows(input_paths)
    author_rows, paper_facts, institution_dim, report = build_normalized_tables(rows)
    report["input_files"] = input_files

    write_csv_rows(
        output_dir / "author_affiliation_facts.csv",
        author_rows,
        [
            "row_key",
            "paper_key",
            "conference",
            "year",
            "title",
            "article_tag",
            "paper_id",
            "name",
            "author_key",
            "author_order",
            "inst",
            "institution_key",
            "country",
            "is_us_institution",
            "classification_source",
            "classification_confidence",
            "classification_reason",
        ],
    )
    write_csv_rows(
        output_dir / "paper_facts.csv",
        paper_facts,
        ["paper_key", "conference", "year", "title", "article_tag", "paper_id", "author_count"],
    )
    write_csv_rows(
        output_dir / "institution_dim.csv",
        institution_dim,
        ["institution_key", "inst_display", "country", "is_us_institution", "source_count", "needs_review"],
    )
    write_json(output_dir / "normalization_report.json", report)


if __name__ == "__main__":
    main()
