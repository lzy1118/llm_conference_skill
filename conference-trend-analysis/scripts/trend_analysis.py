from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


ENTITY_CHOICES = ("country", "institution", "author")


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
    entity_key_field, entity_name_field = entity_fields(entity)
    per_entity_year: dict[tuple[str, str], set[str]] = defaultdict(set)
    entity_names: dict[str, str] = {}

    for row in rows:
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
