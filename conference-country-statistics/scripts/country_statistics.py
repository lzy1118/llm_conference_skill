from __future__ import annotations

import argparse
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from conference_dataset_loader import filter_rows, load_normalized_rows, write_markdown_report, write_summary_csv


def split_composite_label(value: str) -> list[str]:
    """Return non-empty components from an affiliation label."""
    return [part.strip() for part in re.split(r"\s*[|;]\s*", value or "") if part.strip()]


def label_key(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").casefold()
    return re.sub(r"\s+", " ", text).strip()


def is_authoritative_institution_identity(value: str) -> bool:
    identity = (value or "").strip()
    return bool(
        re.fullmatch(r"https?://ror\.org/[0-9a-z]+", identity, flags=re.IGNORECASE)
        or re.fullmatch(r"INST\d+", identity, flags=re.IGNORECASE)
        or re.fullmatch(r"institution:[0-9a-f]{8,}", identity, flags=re.IGNORECASE)
    )


def expand_resolved_country_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Expand countries with known components and discard unresolved fragments."""
    candidates: dict[str, set[str]] = defaultdict(set)
    institution_country_candidates: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        components = split_composite_label(row.get("country", ""))
        if len(components) == 1 and label_key(components[0]) not in {"", "unknown"}:
            candidates[label_key(components[0])].add(components[0])
            identities = split_composite_label(row.get("institution_id", "") or row.get("institution_key", ""))
            if len(identities) == 1:
                institution_country_candidates[identities[0]].add(components[0])
    registry = {
        key: next(iter(values))
        for key, values in candidates.items()
        if len(values) == 1
    }
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
            (index, registry.get(label_key(component)))
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
                split_row["country_source"] = "resolved_institution_country"
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
            split_row["country_source"] = "resolved_composite_component"
            expanded.append(split_row)
    return expanded


def institution_display(row: dict[str, str]) -> str:
    return (row.get("canonical_institution_name", "") or row.get("inst", "")).strip()


def resolved_institution_components(rows: list[dict[str, str]]) -> dict[str, list[tuple[str, str]]]:
    """Build a display-name registry for institution composite expansion."""
    candidates: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for row in rows:
        names = split_composite_label(institution_display(row))
        ids = split_composite_label(row.get("institution_id", "") or row.get("institution_key", ""))
        if len(names) != 1:
            continue
        identity = ids[0] if len(ids) == 1 else ""
        if names[0] and identity:
            candidates[label_key(names[0])].add((identity, names[0]))
    registry: dict[str, list[tuple[str, str]]] = {}
    for key, values in candidates.items():
        if len(values) == 1:
            registry[key] = list(values)
    return registry


def institution_components_for_row(
    row: dict[str, str], registry: dict[str, list[tuple[str, str]]]
) -> list[tuple[str, str]]:
    names = split_composite_label(institution_display(row))
    if not names:
        identity = (row.get("institution_id", "") or row.get("institution_key", "")).strip()
        return [(identity, "")] if identity else []
    ids = split_composite_label(row.get("institution_id", "") or row.get("institution_key", ""))
    if len(names) == len(ids) and len(names) > 1:
        resolved: list[tuple[str, str]] = []
        for identity, name in zip(ids, names):
            known = registry.get(label_key(name), [])
            if identity and (is_authoritative_institution_identity(identity) or any(identity == known_identity for known_identity, _ in known)):
                resolved.append((identity, name))
        return list(dict.fromkeys(resolved))
    if len(names) == 1:
        identity = ids[0] if len(ids) == 1 else ""
        return [(identity, names[0])] if identity else registry.get(label_key(names[0]), [])
    resolved: list[tuple[str, str]] = []
    for name in names:
        resolved.extend(registry.get(label_key(name), []))
    return list(dict.fromkeys(resolved))


def aggregate_country(rows: list[dict[str, str]]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    rows = [row for row in expand_resolved_country_rows(rows) if row.get("country", "").strip()]
    institution_registry = resolved_institution_components(rows)
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
        for institution_key, _ in institution_components_for_row(row, institution_registry):
            if institution_key:
                key["institution_keys"].add(institution_key)
        key["conferences"].add(row["conference"])
        key["years"].add(row["year"])

        conference_key = (country, row["conference"])
        by_conference[conference_key]["paper_keys"].add(row["paper_key"])
        by_conference[conference_key]["author_keys"].add((row["paper_key"], row["author_key"], row["author_order"], country))
        for institution_key, _ in institution_components_for_row(row, institution_registry):
            if institution_key:
                by_conference[conference_key]["institution_keys"].add(institution_key)

        year_key = (country, row["year"])
        by_year[year_key]["paper_keys"].add(row["paper_key"])
        by_year[year_key]["author_keys"].add((row["paper_key"], row["author_key"], row["author_order"], country))
        for institution_key, _ in institution_components_for_row(row, institution_registry):
            if institution_key:
                by_year[year_key]["institution_keys"].add(institution_key)

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
