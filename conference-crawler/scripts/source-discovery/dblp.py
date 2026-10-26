"""DBLP proceedings URL discovery."""

from __future__ import annotations

import re
import time
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup


DBLP_HOSTS = ("dblp.org", "dblp.uni-trier.de", "dblp.dagstuhl.de")
DBLP_INDEX_URL = "https://{host}/db/conf/{dblp_key}/index.html"
SKIP_TERMS = (
    "companion",
    "demo",
    "doctoral",
    "poster",
    "satellite",
    "tutorial",
    "workshop",
)


def _looks_like_main_proceedings(text: str, href: str) -> bool:
    haystack = f"{text} {href}".lower()
    return not any(term in haystack for term in SKIP_TERMS)


def _looks_like_companion_slug(dblp_key: str, year: int, href: str) -> bool:
    return bool(re.search(rf"/{re.escape(dblp_key)}{year}c(?:-|\.html$)", href.lower()))


def _canonicalize_dblp_url(url: str) -> str:
    """Prefer the canonical DBLP host when a mirror served the index."""
    parsed = urlsplit(url)
    if parsed.netloc in DBLP_HOSTS:
        return urlunsplit((parsed.scheme or "https", "dblp.org", parsed.path, parsed.query, parsed.fragment))
    return url


def _make_record(conference: str, year: int, url: str, source: str = "dblp", backend: str = "dblp") -> dict[str, object]:
    return {
        "conference": conference,
        "year": year,
        "source": source,
        "backend": backend,
        "url": url,
        "status": "success",
    }


def discover_dblp_proceedings_urls(
    conference: str,
    dblp_key: str,
    year: int,
    backend: str = "dblp",
) -> list[dict[str, object]]:
    """Return DBLP proceedings records for one conference year."""
    last_error: Exception | None = None
    response = None
    index_url = ""
    for host in DBLP_HOSTS:
        index_url = DBLP_INDEX_URL.format(host=host, dblp_key=dblp_key)
        for attempt in range(1, 4):
            try:
                response = requests.get(index_url, timeout=20)
                response.raise_for_status()
                break
            except requests.RequestException as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(float(attempt))
        if response is not None:
            break
    if response is None:
        raise RuntimeError(f"Unable to fetch DBLP index for {dblp_key}") from last_error

    soup = BeautifulSoup(response.text, "html.parser")
    year_text = str(year)
    records: list[dict[str, object]] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a"):
        href = anchor.get("href") or ""
        text = anchor.get_text(" ", strip=True)
        absolute_url = _canonicalize_dblp_url(urljoin(index_url, href))
        combined = f"{text} {absolute_url}"
        if "/db/conf/" not in absolute_url:
            continue
        if year_text not in combined:
            continue
        if not absolute_url.endswith(".html"):
            continue
        if not _looks_like_main_proceedings(text, absolute_url):
            continue
        if _looks_like_companion_slug(dblp_key, year, absolute_url):
            continue
        if absolute_url in seen:
            continue
        seen.add(absolute_url)
        records.append(_make_record(conference, year, absolute_url, backend=backend))

    return records
