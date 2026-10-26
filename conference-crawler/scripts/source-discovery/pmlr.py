"""PMLR proceedings source discovery."""

from __future__ import annotations

from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


PMLR_INDEX_URL = "https://proceedings.mlr.press/"


def discover_icml_proceedings_urls(conference: str, year: int) -> list[dict[str, object]]:
    """Find ICML proceedings records from the PMLR proceedings index."""
    response = requests.get(PMLR_INDEX_URL, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    year_text = str(year)

    for anchor in soup.find_all("a"):
        href = anchor.get("href") or ""
        parent = anchor.find_parent("li")
        text = parent.get_text(" ", strip=True) if parent else anchor.get_text(" ", strip=True)
        haystack = f"{text} {href}".lower()
        if year_text not in haystack:
            continue
        if (
            f"proceedings of icml {year}" not in haystack
            and f"icml {year} proceedings" not in haystack
            and f"proceedings of the international conference on machine learning {year}" not in haystack
        ):
            continue
        url = urljoin(PMLR_INDEX_URL, href)
        if url in seen:
            continue
        seen.add(url)
        records.append(
            {
                "conference": conference,
                "year": year,
                "source": "pmlr",
                "backend": "pmlr",
                "url": url,
                "status": "success",
            }
        )

    return records
