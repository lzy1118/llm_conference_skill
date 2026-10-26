"""NeurIPS proceedings source discovery."""

from __future__ import annotations

import requests


def discover_neurips_proceedings_urls(conference: str, year: int) -> list[dict[str, object]]:
    """Return canonical NeurIPS proceedings records for a year if reachable."""
    url = f"https://papers.nips.cc/paper_files/paper/{year}"
    response = requests.get(url, timeout=30)
    if response.status_code == 404:
        return []
    response.raise_for_status()
    return [
        {
            "conference": conference,
            "year": year,
            "source": "neurips",
            "backend": "neurips",
            "url": url,
            "status": "success",
        }
    ]
