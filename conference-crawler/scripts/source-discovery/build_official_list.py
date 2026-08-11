#!/usr/bin/env python3

"""Build an official accepted-paper list from source discovery metadata.


The generated CSV is intentionally compatible with the existing
``download/official_accepted_papers.csv`` schema:

    conference,year,title,doi

This script does not download PDFs. It discovers proceedings URLs, asks the
existing DBLP metadata crawler for paper records, and writes title/DOI rows.
"""

from __future__ import annotations

import argparse


import csv


import sys


from pathlib import Path


from typing import Iterable

from discover import discover_proceedings_urls, save_source_manifest, update_source_manifest_counts

SPIDER_DIR = Path(__file__).resolve().parents[1] / "spider-pdf"


if str(SPIDER_DIR) not in sys.path:

    sys.path.insert(0, str(SPIDER_DIR))

from core import DBLPPDFCrawler  # noqa: E402

OFFICIAL_LIST_FIELDS = ["conference", "year", "title", "doi"]

def _parse_years(value: str) -> list[int]:

    years = [int(item.strip()) for item in value.split(",") if item.strip()]

    if not years:

        raise argparse.ArgumentTypeError("at least one year is required")

    return years

def build_official_rows(conference: str, years: Iterable[int], manifest_path: Path | None = None) -> list[dict[str, str]]:

    records = discover_proceedings_urls(conference, years)

    if manifest_path is not None:

        save_source_manifest(records, manifest_path)

    crawler = DBLPPDFCrawler(sleep_seconds=0.0)

    rows: list[dict[str, str]] = []

    counts_by_url: dict[str, int] = {}

    for index, record in enumerate(records, start=1):

        url = str(record["url"])

        print(f"[SOURCE_DISCOVERY] official-list TOC {index}/{len(records)} url={url}")

        papers = crawler.fetch_papers(url)

        counts_by_url[url] = len(papers)

        for paper in papers:

            rows.append(

                {

                    "conference": str(record["conference"]),

                    "year": str(record["year"]),

                    "title": paper.title,

                    "doi": paper.doi,

                }

            )

    if manifest_path is not None:

        update_source_manifest_counts(manifest_path, counts_by_url)

    return rows

def write_official_list(rows: list[dict[str, str]], output_path: Path) -> None:

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8-sig", newline="") as file_obj:

        writer = csv.DictWriter(file_obj, fieldnames=OFFICIAL_LIST_FIELDS)

        writer.writeheader()

        for row in rows:

            writer.writerow({field: row.get(field, "") for field in OFFICIAL_LIST_FIELDS})

def main() -> None:

    parser = argparse.ArgumentParser(description="Build official_accepted_papers.csv from source discovery metadata.")

    parser.add_argument("conference", help="Conference key or alias, e.g. crypto")

    parser.add_argument("--years", required=True, type=_parse_years, help="Comma-separated years, e.g. 2024 or 2023,2024")

    parser.add_argument(

        "--output",

        default=str(Path(__file__).resolve().parents[1] / "download" / "official_accepted_papers.csv"),

        help="Output CSV path; defaults to scripts/download/official_accepted_papers.csv",

    )

    parser.add_argument(

        "--manifest",

        default=str(Path(__file__).resolve().parents[1] / "download" / "metadata" / "source_manifest.csv"),

        help="Source manifest CSV path; use an empty string to skip manifest output",

    )

    args = parser.parse_args()

    output_path = Path(args.output).expanduser().resolve()

    manifest_path = Path(args.manifest).expanduser().resolve() if args.manifest else None

    rows = build_official_rows(args.conference, args.years, manifest_path)

    write_official_list(rows, output_path)

    print(f"[CRAWLER] official papers: {len(rows)}")

    print(f"[CRAWLER] official list: {output_path}")

if __name__ == "__main__":

    main()
