"""Unified conference proceedings source discovery."""

from __future__ import annotations

import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from dblp import discover_dblp_proceedings_urls
from neurips import discover_neurips_proceedings_urls
from pmlr import discover_icml_proceedings_urls
from registry import CONFERENCE_REGISTRY


SOURCE_MANIFEST_FIELDS = [
    "conference",
    "year",
    "source",
    "backend",
    "url",
    "paper_count",
    "status",
    "discovered_time",
    "validation_status",
]


def _normalization_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def normalize_conference_name(name: str) -> str:
    """Normalize a conference name or alias to the registry key."""
    normalized = _normalization_key(name)
    for conference, config in CONFERENCE_REGISTRY.items():
        names = [conference, *config.get("aliases", [])]
        if normalized in {_normalization_key(item) for item in names}:
            return conference
    raise ValueError(f"Unknown conference: {name}")


def discover_proceedings_urls(conference: str, years: Iterable[int | str]) -> list[dict[str, object]]:
    """Discover proceedings source records for a conference and one or more years."""
    conference_key = normalize_conference_name(conference)
    config = CONFERENCE_REGISTRY[conference_key]
    discovery = config["discovery"]
    backend = config["backend"]
    records: list[dict[str, object]] = []
    discovered_time = datetime.now(timezone.utc).isoformat()

    for raw_year in years:
        year = int(raw_year)
        if discovery == "dblp":
            records_for_year = discover_dblp_proceedings_urls(
                conference_key,
                str(config["dblp_key"]),
                year,
                backend=str(backend),
            )
        elif discovery == "neurips":
            records_for_year = discover_neurips_proceedings_urls(conference_key, year)
        elif discovery == "pmlr":
            records_for_year = discover_icml_proceedings_urls(conference_key, year)
        else:
            raise ValueError(f"Unsupported discovery backend: {discovery}")

        for record in records_for_year:
            records.append(
                {
                    "conference": str(record.get("conference", conference_key)),
                    "year": int(record.get("year", year)),
                    "source": str(record.get("source", discovery)),
                    "backend": str(record.get("backend", backend)),
                    "url": str(record.get("url", "")),
                    "paper_count": "",
                    "status": str(record.get("status", "success")),
                    "discovered_time": discovered_time,
                    "validation_status": "discovered",
                }
            )

    return records


def save_source_manifest(records: list[dict[str, object]], manifest_path: Path) -> None:
    """Append discovered source records to a CSV manifest and deduplicate."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    merged_rows: dict[tuple[str, str, str, str], dict[str, object]] = {}

    if manifest_path.exists():
        with open(manifest_path, encoding="utf-8-sig", newline="") as file_obj:
            for row in csv.DictReader(file_obj):
                key = (
                    str(row.get("conference", "")),
                    str(row.get("year", "")),
                    str(row.get("source", "")),
                    str(row.get("url", "")),
                )
                merged_rows[key] = row

    for record in records:
        key = (
            str(record.get("conference", "")),
            str(record.get("year", "")),
            str(record.get("source", "")),
            str(record.get("url", "")),
        )
        new_row = {field: record.get(field, "") for field in SOURCE_MANIFEST_FIELDS}
        previous_row = merged_rows.get(key)
        if previous_row:
            if not new_row.get("paper_count") and previous_row.get("paper_count"):
                new_row["paper_count"] = previous_row.get("paper_count", "")
            if (
                new_row.get("validation_status") == "discovered"
                and previous_row.get("validation_status") == "validated"
            ):
                new_row["validation_status"] = "validated"
        merged_rows[key] = new_row

    rows = sorted(
        merged_rows.values(),
        key=lambda row: (
            str(row.get("conference", "")),
            str(row.get("year", "")),
            str(row.get("source", "")),
            str(row.get("url", "")),
        ),
    )

    with open(manifest_path, "w", newline="", encoding="utf-8") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=SOURCE_MANIFEST_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in SOURCE_MANIFEST_FIELDS})


def update_source_manifest_counts(manifest_path: Path, counts_by_url: dict[str, int]) -> None:
    """Update manifest paper counts after crawler validation."""
    if not manifest_path.exists():
        return
    with open(manifest_path, encoding="utf-8", newline="") as file_obj:
        rows = list(csv.DictReader(file_obj))
    for row in rows:
        url = row.get("url", "")
        if url not in counts_by_url:
            continue
        count = counts_by_url[url]
        if count <= 0 and row.get("paper_count"):
            continue
        row["paper_count"] = str(count)
        row["validation_status"] = "validated"
    save_source_manifest(rows, manifest_path)


def _parse_years(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def main() -> None:
    conference = sys.argv[1] if len(sys.argv) > 1 else "crypto"
    years = _parse_years(sys.argv[2]) if len(sys.argv) > 2 else [2024]
    result = discover_proceedings_urls(conference, years)
    for item in result:
        print(f"{item['conference']} {item['year']} {item['source'].upper()} {item['url']}")


if __name__ == "__main__":
    main()
