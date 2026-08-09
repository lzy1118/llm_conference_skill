from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from collections import defaultdict
from pathlib import Path


ENTITY_CHOICES = ("country", "institution", "author")
NON_COUNTING_INSTITUTION_SOURCES = {
    "secondary_unit_only",
    "unresolved_composite_fragment",
    "independent_researcher_default",
}


def split_composite_label(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s*[|;]\s*", value or "") if part.strip()]


def institution_display(row: dict[str, str]) -> str:
    return (row.get("canonical_institution_name", "") or row.get("inst", "")).strip()


def normalize_label(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value or "").casefold()).strip()


def authoritative_institution_id(value: str) -> bool:
    return bool(
        re.fullmatch(r"https?://ror\.org/[0-9a-z]+", value or "", flags=re.IGNORECASE)
        or re.fullmatch(r"INST\d+", value or "", flags=re.IGNORECASE)
        or re.fullmatch(r"institution:[0-9a-f]{8,}", value or "", flags=re.IGNORECASE)
    )


def expand_country_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    known: dict[str, str] = {}
    institution_country: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        countries = split_composite_label(row.get("country", ""))
        identities = split_composite_label(row.get("institution_id", "") or row.get("institution_key", ""))
        if len(countries) == 1 and normalize_label(countries[0]) not in {"", "unknown"}:
            known.setdefault(normalize_label(countries[0]), countries[0])
            if len(identities) == 1:
                institution_country.setdefault(identities[0], set()).add(countries[0])
    canonical_institution_country = {
        identity: next(iter(values)) for identity, values in institution_country.items() if len(values) == 1
    }
    expanded: list[dict[str, str]] = []
    for row in rows:
        countries = split_composite_label(row.get("country", ""))
        if len(countries) < 2:
            expanded.append(row)
            continue
        resolved = [(index, known.get(normalize_label(country))) for index, country in enumerate(countries)]
        resolved = [(index, country) for index, country in resolved if country]
        names = split_composite_label(institution_display(row))
        identities = split_composite_label(row.get("institution_id", "") or row.get("institution_key", ""))
        if len(names) == len(countries) and len(names) > 1:
            for index, country in resolved:
                split_row = dict(row, country=country)
                if len(identities) == len(countries):
                    split_row["institution_key"] = identities[index]
                    split_row["institution_id"] = identities[index]
                    split_row["inst"] = names[index]
                    split_row["canonical_institution_name"] = names[index]
                expanded.append(split_row)
        elif len(identities) == 1 and identities[0] in canonical_institution_country:
            expanded.append(dict(row, country=canonical_institution_country[identities[0]]))
    return expanded


def expand_institution_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    registry: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        names = split_composite_label(institution_display(row))
        identities = split_composite_label(row.get("institution_id", "") or row.get("institution_key", ""))
        if len(names) == len(identities) == 1:
            registry[normalize_label(names[0])].add(identities[0])
    expanded: list[dict[str, str]] = []
    for row in rows:
        if row.get("institution_source") in NON_COUNTING_INSTITUTION_SOURCES:
            continue
        names = split_composite_label(institution_display(row))
        identities = split_composite_label(row.get("institution_id", "") or row.get("institution_key", ""))
        if len(names) < 2:
            if not names and not identities:
                continue
            if len(identities) > 1:
                known = registry.get(normalize_label(names[0]), set()) if names else set()
                if len(known) != 1:
                    continue
                identity = next(iter(known))
                expanded.append(dict(row, institution_key=identity, institution_id=identity, inst=names[0], canonical_institution_name=names[0]))
            else:
                expanded.append(row)
            continue
        for name, identity in zip(names, identities) if len(names) == len(identities) else []:
            known = registry.get(normalize_label(name), set())
            if identity not in known and not authoritative_institution_id(identity):
                continue
            expanded.append(dict(row, institution_key=identity, institution_id=identity, inst=name, canonical_institution_name=name))
    return expanded


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def entity_fields(entity: str) -> tuple[str, str]:
    if entity == "country":
        return "country", "country"
    if entity == "institution":
        return "institution_key", "inst"
    return "author_key", "name"


def filter_rows(rows: list[dict[str, str]], conference: str | None, year: str | None) -> list[dict[str, str]]:
    filtered = rows
    if conference:
        filtered = [row for row in filtered if row.get("conference") == conference]
    if year:
        filtered = [row for row in filtered if row.get("year") == str(year)]
    return filtered


def aggregate_trends(rows: list[dict[str, str]], entity: str) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if entity == "country":
        rows = expand_country_rows(rows)
    elif entity == "institution":
        rows = expand_institution_rows(rows)
    entity_key_field, entity_name_field = entity_fields(entity)
    per_entity_year: dict[tuple[str, str], set[str]] = defaultdict(set)
    entity_names: dict[str, str] = {}

    for row in rows:
        if entity == "institution":
            if row.get("institution_source") in NON_COUNTING_INSTITUTION_SOURCES:
                continue
            entity_key = (
                row.get("institution_id", "")
                or row.get(entity_key_field, "")
                or row.get(entity_name_field, "")
            )
            if not entity_key.strip():
                continue
            entity_name = row.get("canonical_institution_name", "") or row.get(entity_name_field, "") or entity_key
        elif entity == "country":
            if not row.get("country", "").strip():
                continue
            entity_key = row.get(entity_key_field, "") or row.get(entity_name_field, "") or "Unknown"
            entity_name = row.get(entity_name_field, "") or entity_key
        else:
            entity_key = row.get(entity_key_field, "") or row.get(entity_name_field, "") or "Unknown"
            entity_name = row.get(entity_name_field, "") or entity_key
        year = row.get("year", "")
        if not year:
            continue
        entity_names[entity_key] = entity_names.get(entity_key, entity_name) or entity_name
        per_entity_year[(entity_key, year)].add(row.get("paper_key", ""))

    entity_year_rows_by_key: dict[str, list[dict[str, object]]] = defaultdict(list)
    for (entity_key, year), paper_keys in per_entity_year.items():
        entity_year_rows_by_key[entity_key].append(
            {
                "entity_type": entity,
                "entity_key": entity_key,
                "entity_name": entity_names.get(entity_key, entity_key),
                "year": year,
                "papers": len({key for key in paper_keys if key}),
            }
        )

    trend_by_year: list[dict[str, object]] = []
    trend_summary: list[dict[str, object]] = []
    for entity_key, entity_rows in entity_year_rows_by_key.items():
        entity_rows.sort(key=lambda row: str(row["year"]))
        previous_papers = None
        for row in entity_rows:
            papers = int(row["papers"])
            delta = papers - previous_papers if previous_papers is not None else ""
            ratio = round(delta / previous_papers, 6) if previous_papers not in (None, 0) else ""
            trend_by_year.append(
                {
                    **row,
                    "previous_year_papers": previous_papers if previous_papers is not None else "",
                    "delta_papers": delta,
                    "delta_ratio": ratio,
                }
            )
            previous_papers = papers

        papers_first = int(entity_rows[0]["papers"])
        papers_last = int(entity_rows[-1]["papers"])
        peak_row = max(entity_rows, key=lambda row: (int(row["papers"]), str(row["year"])))
        trend_summary.append(
            {
                "entity_type": entity,
                "entity_key": entity_key,
                "entity_name": entity_rows[0]["entity_name"],
                "year_first": entity_rows[0]["year"],
                "year_last": entity_rows[-1]["year"],
                "years_active": len(entity_rows),
                "papers_first": papers_first,
                "papers_last": papers_last,
                "papers_peak": int(peak_row["papers"]),
                "peak_year": peak_row["year"],
                "net_change": papers_last - papers_first,
            }
        )

    return (
        sorted(trend_summary, key=lambda row: (-int(row["papers_peak"]), -int(row["net_change"]), str(row["entity_name"]))),
        sorted(trend_by_year, key=lambda row: (str(row["year"]), -int(row["papers"]), str(row["entity_name"]))),
    )


def write_report(path: Path, entity: str, conference: str | None, year: str | None, summary: list[dict[str, object]]) -> None:
    lines = [
        "# Conference Trend Analysis Report",
        "",
        "## Scope",
        "",
        f"- entity: {entity}",
        f"- conference: {conference or 'all'}",
        f"- year: {year or 'all'}",
        "",
        "## Highlights",
        "",
    ]
    if not summary:
        lines.append("No rows matched the selected filters.")
    else:
        for row in summary[:10]:
            lines.append(f"- {row['entity_name']}: peak={row['papers_peak']} peak_year={row['peak_year']} net_change={row['net_change']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate temporal trend summaries from normalized conference data.")
    parser.add_argument("--input", required=True, help="Path to normalized author_affiliation_facts.csv")
    parser.add_argument("--output-dir", required=True, help="Output analysis directory root")
    parser.add_argument("--entity", required=True, choices=ENTITY_CHOICES, help="Entity dimension for trend analysis")
    parser.add_argument("--conference")
    parser.add_argument("--year")
    args = parser.parse_args()

    rows = filter_rows(read_rows(Path(args.input)), args.conference, args.year)
    summary, by_year = aggregate_trends(rows, args.entity)
    output_dir = Path(args.output_dir) / "trends"
    write_rows(output_dir / "trend_summary.csv", summary)
    write_rows(output_dir / "trend_by_entity_year.csv", by_year)
    write_report(output_dir / "trend_report.md", args.entity, args.conference, args.year, summary)


if __name__ == "__main__":
    main()
