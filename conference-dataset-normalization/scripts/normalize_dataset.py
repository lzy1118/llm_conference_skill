from __future__ import annotations

import argparse
import csv
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


DEFAULT_OUTPUT_ROOT = Path("generated-data")


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


def csv_row_get(row: dict[str, str], *keys: str) -> str:
    normalized = {
        normalize_whitespace(key).lstrip("\ufeff").strip('"'): value
        for key, value in row.items()
    }
    for key in keys:
        if key in normalized:
            return normalized[key]
    return ""


def load_reference_institutions() -> tuple[dict[str, str], dict[str, dict[str, str]], set[str]]:
    root = Path(__file__).resolve().parents[2]
    alias_path = root / "conference-dataset-normalization" / "references" / "institution_aliases.csv"
    registry_path = root / "conference-dataset-normalization" / "references" / "institution_registry.csv"
    alias_to_id: dict[str, str] = {}
    registry_by_id: dict[str, dict[str, str]] = {}
    reference_names: set[str] = set()

    if registry_path.exists():
        with registry_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                institution_id = normalize_whitespace(csv_row_get(row, "institution_id"))
                if not institution_id:
                    continue
                canonical_name = normalize_whitespace(csv_row_get(row, "canonical_name"))
                registry_by_id[institution_id] = {
                    "canonical_name": canonical_name,
                    "country": normalize_whitespace(csv_row_get(row, "country")),
                    "region": normalize_whitespace(csv_row_get(row, "region")),
                    "type": normalize_whitespace(csv_row_get(row, "type")),
                }
                if canonical_name:
                    reference_names.add(canonical_name.casefold())

    if alias_path.exists():
        with alias_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                alias = normalize_whitespace(csv_row_get(row, "alias"))
                institution_id = normalize_whitespace(csv_row_get(row, "institution_id"))
                if alias and institution_id:
                    alias_to_id[alias.casefold()] = institution_id
                    reference_names.add(alias.casefold())

    for institution_id, registry_row in registry_by_id.items():
        canonical_name = registry_row.get("canonical_name", "")
        if canonical_name:
            alias_to_id.setdefault(canonical_name.casefold(), institution_id)
    return alias_to_id, registry_by_id, reference_names


def recover_conference_and_title(article_tag: str) -> tuple[str, str]:
    normalized_tag = normalize_whitespace(article_tag)
    if not normalized_tag or "-" not in normalized_tag:
        return "", ""
    conference, title = normalized_tag.split("-", 1)
    return normalize_whitespace(conference), normalize_whitespace(title)


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
    alias_to_id, registry_by_id, reference_names = load_reference_institutions()

    for row in rows:
        article_tag = normalize_whitespace(row.get("article_tag", ""))
        recovered_conference, recovered_title = recover_conference_and_title(article_tag)
        conference = normalize_whitespace(row.get("conference", "")) or recovered_conference
        year = normalize_whitespace(row.get("year", ""))
        title = normalize_whitespace(row.get("title", "")) or recovered_title
        paper_id = normalize_whitespace(row.get("paper_id", ""))
        name = normalize_whitespace(row.get("name", ""))
        author_order_text = normalize_whitespace(row.get("author_order", ""))
        inst_value = normalize_whitespace(row.get("inst", ""))
        source_country = normalize_whitespace(row.get("country", ""))
        classification_source = normalize_whitespace(row.get("classification_source", ""))
        classification_confidence = normalize_whitespace(row.get("classification_confidence", ""))
        classification_reason = normalize_whitespace(row.get("classification_reason", ""))

        paper_key = normalize_paper_key(conference, year, title, paper_id)
        author_key = normalize_author_key(name)

        institutions = split_institutions(inst_value, known_names=reference_names) or [inst_value]
        split_combined_institutions = len(institutions) > 1

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
            institution_id = alias_to_id.get(institution.casefold(), "")
            registry_row = registry_by_id.get(institution_id, {})
            registry_country = normalize_whitespace(registry_row.get("country", ""))
            canonical_name = normalize_whitespace(registry_row.get("canonical_name", ""))
            country = ("" if split_combined_institutions else source_country) or registry_country or infer_country(institution)
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
                "institution_id": institution_id,
                "canonical_institution_name": canonical_name,
                "country": country,
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
        institution_ids = [str(row.get("institution_id", "")) for row in grouped_rows if str(row.get("institution_id", ""))]
        canonical_names = [str(row.get("canonical_institution_name", "")) for row in grouped_rows if str(row.get("canonical_institution_name", ""))]
        institution_id = choose_display_name(institution_ids)
        registry_row = registry_by_id.get(institution_id, {}) if institution_id else {}
        institution_dim.append(
            {
                "institution_key": institution_key,
                "inst_display": choose_display_name(display_names),
                "institution_id": institution_id,
                "canonical_name": choose_display_name(canonical_names) or str(registry_row.get("canonical_name", "")),
                "country": choose_display_name(sorted(countries)) or str(registry_row.get("country", "")),
                "region": str(registry_row.get("region", "")),
                "type": str(registry_row.get("type", "")),
                "source_count": len(grouped_rows),
                "needs_review": "Unknown" in countries,
            }
        )

    report = {
        "input_rows": len(rows),
        "normalized_rows": len(author_rows),
        "paper_count": len(paper_facts),
        "institution_count": len(institution_dim),
        "rows_with_reference_institution_id": sum(1 for row in author_rows if row.get("institution_id")),
        "duplicate_row_keys_skipped": duplicate_row_keys,
        "rows_missing_name": sum(1 for row in author_rows if not row["name"]),
        "rows_missing_inst": sum(1 for row in author_rows if not row["inst"]),
        "rows_with_unknown_country": sum(1 for row in author_rows if row["country"] == "Unknown"),
    }
    return author_rows, paper_facts, sorted(institution_dim, key=lambda row: str(row["inst_display"])), report


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize conference datasets for downstream analytics.")
    parser.add_argument("inputs", nargs="+", help="Input CSV files with author affiliation rows")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_ROOT), help="Output analysis root directory")
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
            "institution_id",
            "canonical_institution_name",
            "country",
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
        ["institution_key", "inst_display", "institution_id", "canonical_name", "country", "region", "type", "source_count", "needs_review"],
    )
    write_json(output_dir / "normalization_report.json", report)


if __name__ == "__main__":
    main()
