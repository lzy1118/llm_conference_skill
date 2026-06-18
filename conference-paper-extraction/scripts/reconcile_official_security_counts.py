from __future__ import annotations

import json
import re
import subprocess
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
import requests

from bs4 import BeautifulSoup


ROOT = Path("/Users/liziyu/llm_conference_skill")
RAW_DIR = ROOT / "generated-data" / "extraction" / "raw" / "by_conference"
OUTPUT_DIR = ROOT / "generated-data" / "extraction" / "output" / "official_reconciliation"
OUTPUT_JSON = OUTPUT_DIR / "security_official_reconciliation.json"

YEARS = range(2020, 2026)


@dataclass
class OfficialEntry:
    title: str
    url: str = ""
    doi: str = ""


def fetch_text(url: str) -> str:
    result = subprocess.run(
        [
            "curl",
            "-L",
            "--silent",
            "--show-error",
            "--max-time",
            "60",
            "-A",
            "Mozilla/5.0",
            url,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def soup_from(url: str) -> BeautifulSoup:
    return BeautifulSoup(fetch_text(url), "html.parser")


def normalize_title(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text.strip())
    text = re.sub(r"[^0-9a-zA-Z]+", " ", text.lower())
    return " ".join(text.split())


def load_local_papers(conference_key: str) -> list[dict[str, Any]]:
    path = RAW_DIR / conference_key / "papers.json"
    return json.loads(path.read_text())


def extract_doi(url: str) -> str:
    match = re.search(r"10\.\d{4,9}/[^\s/]+(?:/[^\s]+)?", url or "")
    return match.group(0) if match else ""


def ccs_official_entries(year: int) -> list[OfficialEntry]:
    if year == 2020:
        soup = soup_from("https://www.sigsac.org/ccs/CCS2020/accepted-papers.html")
        return [OfficialEntry(title=b.get_text(" ", strip=True)) for b in soup.select("div.row.papers-item b")]
    if year == 2021:
        soup = soup_from("https://www.sigsac.org/ccs/CCS2021/accepted-papers.html")
        return [OfficialEntry(title=b.get_text(" ", strip=True)) for b in soup.select("div.row.papers-item b")]
    if year == 2022:
        soup = soup_from("https://www.sigsac.org/ccs/CCS2022/program/accepted-papers.html")
        return [OfficialEntry(title=td.get_text(" ", strip=True)) for td in soup.select("table tr td:first-child")]
    if year == 2023:
        xml_text = fetch_text("https://www.sigsac.org/ccs/CCS2023/assets/data/accepted_papers.xml")
        root = ET.fromstring(xml_text)
        return [OfficialEntry(title=paper.findtext("title", "").strip()) for paper in root.findall(".//paper") if paper.findtext("title", "").strip()]
    if year == 2024:
        soup = soup_from("https://www.sigsac.org/ccs/CCS2024/program/accepted-papers.html")
        entries: list[OfficialEntry] = []
        for row in soup.select("table tr"):
            first = row.find("td")
            if not first:
                continue
            title = first.get_text(" ", strip=True)
            if title and title.lower() != "title":
                entries.append(OfficialEntry(title=title))
        return entries
    if year == 2025:
        data = json.loads(fetch_text("https://www.sigsac.org/ccs/CCS2025/assets/accepted-papers.json"))
        entries: list[OfficialEntry] = []
        for cycle_key in ("firstCycle", "secondCycle"):
            for item in data.get(cycle_key, []):
                entries.append(
                    OfficialEntry(
                        title=item.get("title", "").strip(),
                        url=item.get("url", "").strip(),
                        doi=extract_doi(item.get("url", "")),
                    )
                )
        return entries
    raise ValueError(f"Unsupported CCS year: {year}")


def ndss_official_entries(year: int) -> list[OfficialEntry]:
    soup = soup_from(f"https://www.ndss-symposium.org/ndss{year}/accepted-papers/")
    return [OfficialEntry(title=h2.get_text(" ", strip=True)) for h2 in soup.select("h2") if h2.get_text(" ", strip=True) != f"NDSS Symposium {year} Accepted Papers"]


def ieee_sp_official_entries(year: int) -> list[OfficialEntry]:
    if year <= 2023:
        url = f"https://www.ieee-security.org/TC/SP{year}/program-papers.html"
    else:
        url = f"https://sp{year}.ieee-security.org/accepted-papers.html"
    soup = soup_from(url)
    return [OfficialEntry(title=b.get_text(" ", strip=True)) for b in soup.select("div.list-group-item b")]


def usenix_official_entries(year: int) -> list[OfficialEntry]:
    yy = str(year)[-2:]
    response = requests.get(
        f"https://www.usenix.org/conference/usenixsecurity{yy}/technical-sessions",
        headers={"User-Agent": "Mozilla/5.0", "Connection": "close"},
        timeout=(20, 20),
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    ordered_entries: list[OfficialEntry] = []
    seen_urls: set[str] = set()
    for article in soup.select("article.node.node-paper.view-mode-schedule"):
        anchor = article.select_one(f'a[href*="/conference/usenixsecurity{yy}/presentation/"]')
        if anchor is None:
            continue
        if article.select_one(".usenix-schedule-media.pdf a") is None:
            continue
        href = anchor.get("href", "").strip()
        title = anchor.get_text(" ", strip=True)
        if not href or not title:
            continue
        full_url = href if href.startswith("http") else f"https://www.usenix.org{href}"
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)
        ordered_entries.append(OfficialEntry(title=title, url=full_url))

    if year != 2025:
        return ordered_entries

    cycle1_response = requests.get(
        "https://www.usenix.org/conference/usenixsecurity25/cycle1-accepted-papers",
        headers={"User-Agent": "Mozilla/5.0", "Connection": "close"},
        timeout=(20, 20),
    )
    cycle1_response.raise_for_status()
    cycle1_soup = BeautifulSoup(cycle1_response.text, "html.parser")
    cycle1_titles: list[str] = []
    seen_titles: set[str] = set()
    for anchor in cycle1_soup.select('a[href*="/conference/usenixsecurity25/presentation/"]'):
        title = anchor.get_text(" ", strip=True)
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        cycle1_titles.append(title)
    if len(cycle1_titles) < 214:
        return ordered_entries

    cycle1_new_keys = {normalize_title(title) for title in cycle1_titles[:214]}
    cycle1_all_keys = {normalize_title(title) for title in cycle1_titles}
    tech_only_keys = {normalize_title(entry.title) for entry in ordered_entries if normalize_title(entry.title) not in cycle1_all_keys}
    if len(tech_only_keys) != 193:
        return ordered_entries
    retained = cycle1_new_keys | tech_only_keys
    filtered = [entry for entry in ordered_entries if normalize_title(entry.title) in retained]
    return filtered if len(filtered) == 407 else ordered_entries


def official_entries(venue: str, year: int) -> list[OfficialEntry]:
    if venue == "ccs":
        return ccs_official_entries(year)
    if venue == "ndss":
        return ndss_official_entries(year)
    if venue == "ieee_sp":
        return ieee_sp_official_entries(year)
    if venue == "usenix_security":
        return usenix_official_entries(year)
    raise ValueError(f"Unsupported venue: {venue}")


def local_key(venue: str, year: int, paper: dict[str, Any]) -> str:
    url = (paper.get("url") or "").strip()
    if venue == "usenix_security" and url:
        return url
    if venue == "ccs" and year == 2025:
        doi = extract_doi(url)
        if doi:
            return doi
    return normalize_title(paper.get("title", ""))


def official_key(venue: str, year: int, entry: OfficialEntry) -> str:
    if venue == "usenix_security" and entry.url:
        return entry.url
    if venue == "ccs" and year == 2025 and entry.doi:
        return entry.doi
    return normalize_title(entry.title)


def infer_reason(venue: str, direction: str, item: dict[str, Any]) -> str:
    title = item.get("title", "")
    normalized = normalize_title(title)
    pages = item.get("pages", "")
    if venue == "ccs" and direction == "local_only":
        if pages:
            span = re.match(r"(\d+)\s*-\s*(\d+)", pages)
            if span:
                length = int(span.group(2)) - int(span.group(1)) + 1
                if length <= 4:
                    return "short proceedings item likely not counted on official accepted-papers page"
        if re.search(r"\b(poster|demo|tutorial|doctoral|symposium|competition|checkmate|free5gc)\b", normalized):
            return "non-main-track CCS item retained locally"
        return "title present locally but not on official accepted list"
    if venue == "ccs" and direction == "official_only":
        return "official CCS entry missing locally; likely DBLP/proceedings ingestion gap or blank title metadata"
    if venue == "usenix_security" and direction == "official_only":
        return "official USENIX presentation page missing locally; likely DBLP/source coverage gap"
    if venue == "usenix_security" and direction == "local_only":
        return "local entry not found in official USENIX technical-sessions presentation list"
    if venue == "ieee_sp" and direction == "official_only":
        return "official IEEE S&P accepted-paper entry missing locally"
    if venue == "ieee_sp" and direction == "local_only":
        return "local IEEE S&P entry not found on official accepted-paper page"
    if venue == "ndss" and direction == "official_only":
        return "official NDSS accepted-paper entry missing locally"
    if venue == "ndss" and direction == "local_only":
        return "local NDSS entry not found on official accepted-paper page"
    return "unclassified mismatch"


def find_close_variants(local_only: dict[str, dict[str, Any]], official_only: dict[str, OfficialEntry]) -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []
    used_local: set[str] = set()
    used_official: set[str] = set()
    for off_key, off_entry in official_only.items():
        best_key = ""
        best_ratio = 0.0
        for loc_key, loc_item in local_only.items():
            if loc_key in used_local:
                continue
            ratio = SequenceMatcher(None, normalize_title(off_entry.title), normalize_title(loc_item.get("title", ""))).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_key = loc_key
        if best_key and best_ratio >= 0.92:
            used_local.add(best_key)
            used_official.add(off_key)
            variants.append(
                {
                    "official_title": off_entry.title,
                    "local_title": local_only[best_key].get("title", ""),
                    "similarity": round(best_ratio, 4),
                }
            )
    return variants


def compare_venue_year(venue: str, year: int) -> dict[str, Any]:
    conference_key = f"{venue}_{year}"
    local_papers = load_local_papers(conference_key)
    official = official_entries(venue, year)

    local_map = {local_key(venue, year, paper): paper for paper in local_papers if local_key(venue, year, paper)}
    official_map = {official_key(venue, year, entry): entry for entry in official if official_key(venue, year, entry)}

    local_only_keys = sorted(set(local_map) - set(official_map))
    official_only_keys = sorted(set(official_map) - set(local_map))

    local_only = {key: local_map[key] for key in local_only_keys}
    official_only = {key: official_map[key] for key in official_only_keys}
    close_variants = find_close_variants(local_only, official_only)

    return {
        "conference_key": conference_key,
        "official_count": len(official_map),
        "local_count": len(local_map),
        "count_diff_local_minus_official": len(local_map) - len(official_map),
        "local_only_count": len(local_only),
        "official_only_count": len(official_only),
        "probable_title_variants": close_variants,
        "official_source": source_description(venue, year),
        "local_only_examples": [
            {
                "paperId": paper.get("paperId", ""),
                "title": paper.get("title", ""),
                "url": paper.get("url", ""),
                "pages": paper.get("pages", ""),
                "reason": infer_reason(venue, "local_only", paper),
            }
            for paper in list(local_only.values())[:25]
        ],
        "official_only_examples": [
            {
                "title": entry.title,
                "url": entry.url,
                "doi": entry.doi,
                "reason": infer_reason(venue, "official_only", {"title": entry.title, "url": entry.url, "doi": entry.doi}),
            }
            for entry in list(official_only.values())[:25]
        ],
    }


def source_description(venue: str, year: int) -> str:
    if venue == "ccs":
        if year == 2023:
            return "ACM CCS 2023 official accepted_papers.xml"
        if year == 2025:
            return "ACM CCS 2025 official accepted-papers.json"
        return f"ACM CCS {year} official accepted-papers webpage"
    if venue == "ndss":
        return f"NDSS {year} official accepted-papers webpage"
    if venue == "ieee_sp":
        return f"IEEE S&P {year} official accepted-papers/program-papers webpage"
    if venue == "usenix_security":
        return f"USENIX Security {year} official technical-sessions presentation links"
    raise ValueError(venue)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for venue in ("ccs", "ieee_sp", "ndss", "usenix_security"):
        for year in YEARS:
            conference_key = f"{venue}_{year}"
            print(f"processing {conference_key}", flush=True)
            try:
                results.append(compare_venue_year(venue, year))
            except Exception as exc:
                results.append(
                    {
                        "conference_key": conference_key,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            OUTPUT_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    OUTPUT_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(str(OUTPUT_JSON))


if __name__ == "__main__":
    main()
