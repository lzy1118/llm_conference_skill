from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import re

from conference_dataset_loader import filter_rows, load_normalized_rows, write_markdown_report, write_summary_csv


NON_COUNTING_INSTITUTION_SOURCES = {
    "secondary_unit_only",
    "unresolved_composite_fragment",
    "independent_researcher_default",
}


def normalize_institution_display_name(raw_name: str, canonical_name: str) -> str:
    preferred = (canonical_name or "").strip() or (raw_name or "").strip()
    if not preferred:
        return ""
    text = preferred.replace("&amp;", "&").strip()
    text = re.sub(r"^\*+\s*", "", text)
    text = re.sub(r"^[|;]+\s*|\s*[|;]+$", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_composite_name(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s*[|;]\s*", value or "") if part.strip()]


def split_composite_identity(value: str) -> list[str]:
    """Split aligned institution ids without treating a blank as an identity."""
    return [part.strip() for part in re.split(r"\s*[|;]\s*", value or "") if part.strip()]


def institution_name_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def is_first_author(row: dict[str, str]) -> bool:
    try:
        return int(row.get("author_order", "")) == 0
    except (TypeError, ValueError):
        return False


def normalized_author_order(value: str) -> str:
    value = (value or "").strip()
    try:
        return str(int(value))
    except ValueError:
        return value


def is_authoritative_institution_identity(value: str) -> bool:
    identity = (value or "").strip()
    return bool(
        re.fullmatch(r"https?://ror\.org/[0-9a-z]+", identity, flags=re.IGNORECASE)
        or re.fullmatch(r"INST\d+", identity, flags=re.IGNORECASE)
        or re.fullmatch(r"institution:[0-9a-f]{8,}", identity, flags=re.IGNORECASE)
    )


def expand_resolved_country_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Align known composite countries and preserve unresolved rows as Unknown."""
    country_candidates: dict[str, set[str]] = defaultdict(set)
    institution_country_candidates: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        countries = split_composite_name(row.get("country", ""))
        identities = split_composite_identity(row.get("institution_id", "") or row.get("institution_key", ""))
        if len(countries) == 1 and countries[0].casefold() not in {"", "unknown", "none", "n/a", "null"}:
            country_candidates[countries[0].casefold()].add(countries[0])
            if len(identities) == 1:
                institution_country_candidates[identities[0]].add(countries[0])
    country_registry = {
        key: next(iter(values))
        for key, values in country_candidates.items()
        if len(values) == 1
    }
    institution_country_registry = {
        identity: next(iter(values))
        for identity, values in institution_country_candidates.items()
        if len(values) == 1
    }

    expanded: list[dict[str, str]] = []
    for row in rows:
        countries = split_composite_name(row.get("country", ""))
        if len(countries) < 2:
            expanded.append(row)
            continue
        resolved_countries = [
            (index, country_registry.get(country.casefold()))
            for index, country in enumerate(countries)
        ]
        display = normalize_institution_display_name(
            row.get("inst", ""), row.get("canonical_institution_name", "")
        )
        institution_names = split_composite_name(display)
        institution_ids = split_composite_identity(row.get("institution_id", "") or row.get("institution_key", ""))
        aligned_institutions = len(institution_names) == len(countries) and len(institution_names) > 1
        if aligned_institutions:
            for index, country in resolved_countries:
                split_row = dict(row)
                split_row["country"] = country or "Unknown"
                split_row["inst"] = institution_names[index]
                split_row["canonical_institution_name"] = institution_names[index]
                if len(institution_ids) == len(countries):
                    split_row["institution_id"] = institution_ids[index]
                    split_row["institution_key"] = institution_ids[index]
                else:
                    split_row["institution_key"] = institution_names[index]
                split_row["country_source"] = (
                    "resolved_composite_component" if country else "unresolved_composite"
                )
                expanded.append(split_row)
            continue
        if len(institution_ids) == 1:
            canonical_country = institution_country_registry.get(institution_ids[0])
            split_row = dict(row)
            split_row["country"] = canonical_country or "Unknown"
            split_row["country_source"] = (
                "resolved_institution_country" if canonical_country else "unresolved_composite"
            )
            expanded.append(split_row)
            continue
        split_row = dict(row)
        split_row["country"] = "Unknown"
        split_row["country_source"] = "unresolved_composite"
        expanded.append(split_row)
    return expanded


def expand_resolved_composite_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Split participation rows and drop unresolved composite fragments.

    AffilGood often provides aligned ``name;name`` and ``ror;ror`` values.  Each
    aligned component must still have a known singleton identity or an
    authoritative ROR/local identity. When aligned ids are absent, fall back to
    the singleton registry built from the surrounding rows.
    """
    candidates: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in rows:
        display = normalize_institution_display_name(
            row.get("inst", ""), row.get("canonical_institution_name", "")
        )
        if len(split_composite_name(display)) != 1:
            continue
        identity = (row.get("institution_id", "") or row.get("institution_key", "")).strip()
        if not display or len(split_composite_identity(identity)) != 1:
            continue
        candidates[institution_name_key(display)][identity] = {
            "institution_key": row.get("institution_key", ""),
            "institution_id": row.get("institution_id", ""),
            "institution_name": display,
            "country": row.get("country", ""),
        }

    registry = {
        name_key: next(iter(identities.values()))
        for name_key, identities in candidates.items()
        if len(identities) == 1
    }
    expanded: list[dict[str, str]] = []
    for row in rows:
        display = normalize_institution_display_name(
            row.get("inst", ""), row.get("canonical_institution_name", "")
        )
        components = split_composite_name(display)
        if len(components) < 2:
            identity_values = split_composite_identity(
                row.get("institution_id", "") or row.get("institution_key", "")
            )
            if len(identity_values) > 1:
                component = registry.get(institution_name_key(display))
                if component is None:
                    continue
                split_row = dict(row)
                split_row["institution_key"] = component["institution_key"]
                split_row["institution_id"] = component["institution_id"]
                split_row["inst"] = component["institution_name"]
                split_row["canonical_institution_name"] = component["institution_name"]
                split_row["country"] = component["country"] or row.get("country", "")
                split_row["institution_source"] = "resolved_participation_component"
                expanded.append(split_row)
                continue
            expanded.append(row)
            continue
        identity_values = split_composite_identity(
            row.get("institution_id", "") or row.get("institution_key", "")
        )
        if len(identity_values) == len(components):
            resolved = []
            for component, identity in zip(components, identity_values):
                known = registry.get(institution_name_key(component))
                if known and identity in {known["institution_id"], known["institution_key"]}:
                    resolved.append(known)
                elif is_authoritative_institution_identity(identity):
                    resolved.append({
                        "institution_key": identity,
                        "institution_id": identity,
                        "institution_name": component,
                        "country": row.get("country", ""),
                    })
                else:
                    resolved.append(None)
        else:
            resolved = [registry.get(institution_name_key(component)) for component in components]
        if not any(component is not None for component in resolved):
            # A fully unresolved composite is only an affiliation fragment.
            continue
        if any(component is None for component in resolved):
            # Keep known institutions and discard only the unresolved fragments.
            resolved = [component for component in resolved if component is not None]
        if not resolved:
            expanded.append(row)
            continue
        for component in resolved:
            split_row = dict(row)
            split_row["institution_key"] = component["institution_key"]
            split_row["institution_id"] = component["institution_id"]
            split_row["inst"] = component["institution_name"]
            split_row["canonical_institution_name"] = component["institution_name"]
            split_row["country"] = component["country"] or row.get("country", "")
            split_row["institution_source"] = "resolved_participation_component"
            expanded.append(split_row)
    return expanded


def aggregate_institutions(rows: list[dict[str, str]]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    scope_papers = {row.get("paper_key", "").strip() for row in rows if row.get("paper_key", "").strip()}
    rows = expand_resolved_composite_rows(expand_resolved_country_rows(rows))
    grouped: dict[str, dict[str, object]] = defaultdict(lambda: {
        "institution_id": "",
        "institution_name": "",
        "countries": set(),
        "paper_keys": set(),
        "author_rows": set(),
        "first_author_papers": set(),
        "conferences": set(),
        "years": set(),
    })
    by_conference: dict[tuple[str, str], set[str]] = defaultdict(set)
    by_year: dict[tuple[str, str], set[str]] = defaultdict(set)

    total_paper_count = max(len(scope_papers), 1)

    for row in rows:
        if row.get("institution_source") in NON_COUNTING_INSTITUTION_SOURCES:
            continue
        key = (row.get("institution_id", "") or row.get("institution_key", "")).strip()
        paper_key = row.get("paper_key", "").strip()
        if not key or not paper_key:
            continue
        entry = grouped[key]
        entry["institution_id"] = entry["institution_id"] or row.get("institution_id", "")
        entry["institution_name"] = entry["institution_name"] or normalize_institution_display_name(
            row.get("inst", ""),
            row.get("canonical_institution_name", ""),
        )
        country = (row.get("country") or "").strip() or "Unknown"
        entry["countries"].add(country)
        entry["paper_keys"].add(paper_key)
        author_identity = (row.get("author_key", "") or row.get("name", "")).strip()
        if author_identity:
            entry["author_rows"].add(
                (paper_key, author_identity, normalized_author_order(row.get("author_order", "")), key)
            )
        entry["conferences"].add(row.get("conference", ""))
        entry["years"].add(row.get("year", ""))
        if author_identity and is_first_author(row):
            entry["first_author_papers"].add(paper_key)
        by_conference[(key, row.get("conference", ""))].add(paper_key)
        by_year[(key, row.get("year", ""))].add(paper_key)

    summary = []
    for institution_key, entry in grouped.items():
        papers = len(entry["paper_keys"])
        countries = sorted(entry["countries"], key=lambda value: (value.casefold(), value))
        summary.append({
            "institution_key": institution_key,
            "institution_id": entry["institution_id"],
            "institution_name": entry["institution_name"],
            "country": " | ".join(countries),
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
        rows = expand_resolved_country_rows(rows)
        country_key = args.country.strip().casefold()
        rows = [
            row for row in rows
            if ((row.get("country") or "").strip() or "Unknown").casefold() == country_key
        ]

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
            "composite_participation": "split only when every component has one known institution identity",
        },
        highlights=summary[:10],
    )


if __name__ == "__main__":
    main()
