from __future__ import annotations

import csv
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as SeleniumChromeOptions
    from selenium.webdriver.chrome.service import Service as SeleniumChromeService
except Exception:
    webdriver = None
    SeleniumChromeOptions = None
    SeleniumChromeService = None

from api_runtime import fetch_json_with_rate_limit, openalex_headers, semantic_scholar_headers


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()



BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


MOJIBAKE_MARKERS = set("茅谩铆贸煤眉脴脙脡")
LATIN_EXTENDED_PATTERN = re.compile(r"[\u00c0-\u024f]")


def repair_gbk_mojibake(value: Any) -> str:
    text = str(value or "")
    if not any(marker in text for marker in MOJIBAKE_MARKERS):
        return text
    try:
        repaired = text.encode("gb18030").decode("utf-8")
    except UnicodeError:
        return text
    if any(marker in repaired for marker in MOJIBAKE_MARKERS):
        return text
    if re.search(r"[A-Za-z]", text) and LATIN_EXTENDED_PATTERN.search(repaired):
        return repaired
    return text


@dataclass(frozen=True)
class ConferenceConfig:
    key: str
    conference: str
    year: int
    dblp_key: str
    venue_tag: str


CONFERENCES = {
    "usenix_security_2020": ConferenceConfig("usenix_security_2020", "USENIX_SECURITY", 2020, "uss", "USENIX_SECURITY"),
    "usenix_security_2021": ConferenceConfig("usenix_security_2021", "USENIX_SECURITY", 2021, "uss", "USENIX_SECURITY"),
    "usenix_security_2022": ConferenceConfig("usenix_security_2022", "USENIX_SECURITY", 2022, "uss", "USENIX_SECURITY"),
    "usenix_security_2023": ConferenceConfig("usenix_security_2023", "USENIX_SECURITY", 2023, "uss", "USENIX_SECURITY"),
    "usenix_security_2024": ConferenceConfig("usenix_security_2024", "USENIX_SECURITY", 2024, "uss", "USENIX_SECURITY"),
    "usenix_security_2025": ConferenceConfig("usenix_security_2025", "USENIX_SECURITY", 2025, "uss", "USENIX_SECURITY"),
    "ndss_2020": ConferenceConfig("ndss_2020", "NDSS", 2020, "ndss", "NDSS"),
    "ndss_2021": ConferenceConfig("ndss_2021", "NDSS", 2021, "ndss", "NDSS"),
    "ndss_2022": ConferenceConfig("ndss_2022", "NDSS", 2022, "ndss", "NDSS"),
    "ndss_2023": ConferenceConfig("ndss_2023", "NDSS", 2023, "ndss", "NDSS"),
    "ndss_2024": ConferenceConfig("ndss_2024", "NDSS", 2024, "ndss", "NDSS"),
    "ndss_2025": ConferenceConfig("ndss_2025", "NDSS", 2025, "ndss", "NDSS"),
    "ieee_sp_2020": ConferenceConfig("ieee_sp_2020", "IEEE_S&P", 2020, "sp", "IEEE_S&P"),
    "ieee_sp_2021": ConferenceConfig("ieee_sp_2021", "IEEE_S&P", 2021, "sp", "IEEE_S&P"),
    "ieee_sp_2022": ConferenceConfig("ieee_sp_2022", "IEEE_S&P", 2022, "sp", "IEEE_S&P"),
    "ieee_sp_2023": ConferenceConfig("ieee_sp_2023", "IEEE_S&P", 2023, "sp", "IEEE_S&P"),
    "ieee_sp_2024": ConferenceConfig("ieee_sp_2024", "IEEE_S&P", 2024, "sp", "IEEE_S&P"),
    "ieee_sp_2025": ConferenceConfig("ieee_sp_2025", "IEEE_S&P", 2025, "sp", "IEEE_S&P"),
    "ieee_sp_2026": ConferenceConfig("ieee_sp_2026", "IEEE_S&P", 2026, "sp", "IEEE_S&P"),
    "ccs_2020": ConferenceConfig("ccs_2020", "CCS", 2020, "ccs", "CCS"),
    "ccs_2021": ConferenceConfig("ccs_2021", "CCS", 2021, "ccs", "CCS"),
    "ccs_2022": ConferenceConfig("ccs_2022", "CCS", 2022, "ccs", "CCS"),
    "ccs_2023": ConferenceConfig("ccs_2023", "CCS", 2023, "ccs", "CCS"),
    "ccs_2024": ConferenceConfig("ccs_2024", "CCS", 2024, "ccs", "CCS"),
    "ccs_2025": ConferenceConfig("ccs_2025", "CCS", 2025, "ccs", "CCS"),
    "ccs_2026": ConferenceConfig("ccs_2026", "CCS", 2026, "ccs", "CCS"),
    "ndss_2026": ConferenceConfig("ndss_2026", "NDSS", 2026, "ndss", "NDSS"),
    "usenix_security_2026": ConferenceConfig("usenix_security_2026", "USENIX_SECURITY", 2026, "uss", "USENIX_SECURITY"),
}


AUTHOR_NOTE_PATTERN = re.compile(
    r"\b(corresponding author|author to whom correspondence|equal contribution|shared first author|present address)\b",
    re.IGNORECASE,
)


SPECIAL_NAME_CHAR_MAP = str.maketrans(
    {
        "ı": "i",
        "İ": "I",
        "đ": "d",
        "Đ": "D",
        "ð": "d",
        "Ð": "D",
        "ł": "l",
        "Ł": "L",
        "ø": "o",
        "Ø": "O",
        "ß": "ss",
        "æ": "ae",
        "Æ": "Ae",
        "œ": "oe",
        "Œ": "Oe",
    }
)


AUTHOR_NAME_PLACEHOLDERS = {
    "available media",
}


def official_title_key(value: str) -> str:
    text = normalize_space(value)
    text = re.sub(r"^\(#\d+\)\s*", "", text)
    text = text.replace("^", "")
    text = text.replace("”", '"').replace("“", '"').replace("’", "'").replace("‘", "'")
    text = text.replace("–", "-").replace("—", "-")
    text = text.replace(":", " ").replace("-", " ").replace(".", " ")
    text = re.sub(r"[^0-9a-zA-Z]+", " ", text.casefold())
    return " ".join(text.split())


@lru_cache(maxsize=None)
def fetch_usenix_official_entries(year: int) -> list[dict[str, str]]:
    """抓取 USENIX 官方论文列表，并保留 accepted 页面的顺序。"""
    yy = str(year)[-2:]
    url = f"https://www.usenix.org/conference/usenixsecurity{yy}/technical-sessions"
    soup = BeautifulSoup(fetch_text(url, timeout=30), "html.parser")
    ordered_entries: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for article in soup.select("article.node.node-paper.view-mode-schedule"):
        anchor = article.select_one(f'h2 a[href*="/conference/usenixsecurity{yy}/presentation/"]')
        if anchor is None:
            continue
        if article.select_one(".usenix-schedule-media.pdf a") is None:
            continue
        href = normalize_space(anchor.get("href", ""))
        title = normalize_space(anchor.get_text(" ", strip=True))
        if not href or not title:
            continue
        full_url = href if href.startswith("http") else f"https://www.usenix.org{href}"
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)
        ordered_entries.append(
            {
                "title": title,
                "url": full_url,
                "official_affiliations": parse_usenix_affiliations_html(str(article)),
            }
        )

    # The technical-sessions DOM is the authoritative page list for the local
    # PDF corpus.  Do not apply review-cycle filters here: they intentionally
    # omit published/session papers that are present in the downloaded PDFs.
    return ordered_entries


def parse_author_names_from_official_affiliation_text(text: str) -> list[str]:
    authors: list[str] = []
    for match in re.finditer(r"([^,;()]+?)\s*\([^)]{2,}\)", text):
        for name in split_author_name_group(match.group(1)):
            if name and name not in authors:
                authors.append(name)
    return authors


def split_author_name_group(value: str) -> list[str]:
    text = clean_author_name(value)
    if not text:
        return []
    parts = [
        clean_author_name(part)
        for part in re.split(r"\s+\band\b\s+", text)
        if clean_author_name(part)
    ]
    if len(parts) > 1 and all(len(normalize_person_name(part)) >= 2 for part in parts):
        return parts
    return [text]


def parse_author_affiliations_from_parenthesized_text(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    normalized = normalize_space(text)
    segments: list[str] = []
    current: list[str] = []
    depth = 0
    for char in normalized:
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
        if char in {";", ","} and depth == 0:
            segment = normalize_space("".join(current))
            if segment:
                segments.append(segment)
            current = []
            continue
        current.append(char)
    final_segment = normalize_space("".join(current))
    if final_segment:
        segments.append(final_segment)

    for segment in segments:
        segment = normalize_space(segment)
        if not segment:
            continue
        # Official accepted-paper pages sometimes include nickname parentheses in
        # author names, e.g. "Danfeng (Daphne) Yao (Virginia Tech)".
        # Treat only the final parenthesized group as the affiliation.
        if not segment.endswith(")"):
            continue
        depth = 0
        open_index = -1
        for index in range(len(segment) - 1, -1, -1):
            char = segment[index]
            if char == ")":
                depth += 1
            elif char == "(":
                depth -= 1
                if depth == 0:
                    open_index = index
                    break
        if open_index <= 0:
            continue
        names = split_author_name_group(segment[:open_index])
        inst = normalize_space(segment[open_index + 1 : -1])
        if not names or len(inst) <= 2 or inst.startswith("http"):
            continue
        rows.extend({"name": name, "affiliations": [inst]} for name in names)
    return rows


CCS_OFFICIAL_AFFILIATION_HINTS = re.compile(
    r"\b(?:university|institute|institution|college|school|laborator(?:y|ies)|labs?|"
    r"research|center|centre|academy|corporation|corp\.?|company|inc\.?|ltd\.?|"
    r"gmbh|llc|aist|nec|ibm|google|microsoft|vmware|cispa)\b",
    re.IGNORECASE,
)


def _looks_like_ccs_official_affiliation(value: str) -> bool:
    text = normalize_space(value)
    if not text:
        return False
    if CCS_OFFICIAL_AFFILIATION_HINTS.search(text):
        return True
    if "," in text or any(char.isdigit() for char in text):
        return True
    compact = re.sub(r"[^A-Za-z]", "", text)
    return 2 <= len(compact) <= 12 and compact.isupper()


def _looks_like_ccs_official_author(value: str) -> bool:
    name = clean_author_name(value)
    if not name or CCS_OFFICIAL_AFFILIATION_HINTS.search(name):
        return False
    tokens = re.findall(r"[A-Za-zÀ-\u024f][A-Za-zÀ-\u024f.'`’\-]*", name)
    if not 2 <= len(tokens) <= 7:
        return False
    capitalized = sum(token[0].isupper() for token in tokens if token)
    return capitalized >= 2


def repair_ccs_missing_author_separators(text: str) -> tuple[str, int]:
    """Recover omitted semicolons between ``Author (Affiliation)`` pairs.

    CCS accepted-paper pages occasionally contain a sequence such as
    ``Wataru Nakamura (Hitachi, Ltd.) Kazuma Ohara (AIST)``.  The recovery is
    deliberately narrow: the closed group must look like an institution and
    the bridge before the next opening parenthesis must look like a full
    person name.  This avoids splitting nickname forms such as
    ``Minhui (Jason) Xue (The University of Adelaide)``.
    """
    normalized = normalize_space(text.replace("\xa0", " "))
    if not normalized:
        return "", 0

    insertions: list[int] = []
    stack: list[int] = []
    top_level_groups: list[tuple[int, int]] = []
    for index, char in enumerate(normalized):
        if char == "(":
            stack.append(index)
        elif char == ")" and stack:
            open_index = stack.pop()
            if not stack:
                top_level_groups.append((open_index, index))

    for open_index, close_index in top_level_groups:
        next_start = close_index + 1
        while next_start < len(normalized) and normalized[next_start].isspace():
            next_start += 1
        if next_start >= len(normalized) or normalized[next_start] in ";,":
            continue
        next_open = normalized.find("(", next_start)
        if next_open < 0:
            continue
        affiliation = normalized[open_index + 1 : close_index]
        possible_author = normalized[next_start:next_open]
        if _looks_like_ccs_official_affiliation(affiliation) and _looks_like_ccs_official_author(possible_author):
            insertions.append(next_start)

    repaired = normalized
    for index in reversed(insertions):
        repaired = f"{repaired[:index]}; {repaired[index:]}"
    return repaired, len(insertions)


def parse_ccs_row_author_text(text: str) -> tuple[list[str], list[dict[str, Any]]]:
    normalized, _repair_count = repair_ccs_missing_author_separators(text)
    if not normalized:
        return [], []
    affiliations = parse_author_affiliations_from_parenthesized_text(normalized)
    return ([row["name"] for row in affiliations], affiliations)


def parse_ccs_author_table_cell(cell: Any) -> tuple[list[str], list[dict[str, Any]]]:
    segments = [
        normalize_space(part)
        for part in cell.stripped_strings
        if normalize_space(part)
    ]
    if len(segments) <= 1:
        return parse_ccs_row_author_text(cell.get_text(" ", strip=True))
    rows: list[dict[str, Any]] = []
    for segment in segments:
        rows.extend(parse_author_affiliations_from_parenthesized_text(segment))
    return ([row["name"] for row in rows], rows)


def parse_ieee_official_author_affiliations(item: Any) -> list[dict[str, Any]]:
    collapse = item.select_one("div.collapse.authorlist")
    if collapse is None:
        item_text = normalize_space(item.get_text(" ", strip=True))
        title_el = item.find("b")
        if title_el is not None:
            title = normalize_space(title_el.get_text(" ", strip=True))
            if title and item_text.startswith(title):
                item_text = normalize_space(item_text[len(title):].strip(" -"))
        return parse_author_affiliations_from_parenthesized_text(item_text)
    author_segments: list[str] = []
    aff_segments: list[str] = []
    phase = "authors"
    for child in collapse.children:
        name = getattr(child, "name", None)
        if name == "br":
            phase = "affiliations"
            continue
        if name == "sup":
            token = f"[{normalize_space(child.get_text(' ', strip=True)).replace(' ', '')}]"
        else:
            token = str(child)
        if phase == "authors":
            author_segments.append(token)
        else:
            aff_segments.append(token)
    author_text = normalize_space(BeautifulSoup("".join(author_segments), "html.parser").get_text(" ", strip=True))
    aff_text = normalize_space(BeautifulSoup("".join(aff_segments), "html.parser").get_text(" ", strip=True))
    if not author_text or not aff_text:
        return []

    affiliation_map: dict[str, str] = {}
    for nums, inst in re.findall(r"\[(\d+(?:,\d+)*)\]\s*:\s*(.*?)(?=(?:\s*\[\d+(?:,\d+)*\]\s*:)|$)", aff_text):
        institution = normalize_space(inst.strip(" ,;"))
        if not institution:
            continue
        for num in nums.split(","):
            affiliation_map[normalize_space(num)] = institution

    if not affiliation_map:
        shared_affiliation = normalize_space(aff_text.strip(" ,;"))
        if shared_affiliation:
            rows: list[dict[str, Any]] = []
            for part in author_text.split(","):
                for name in split_author_name_group(part):
                    rows.append({"name": name, "affiliations": [shared_affiliation]})
            return rows

    rows: list[dict[str, Any]] = []
    for name_text, nums in re.findall(r"(.*?)\[(\d+(?:,\d+)*)\](?=\s*(?:,|$))", author_text):
        name = clean_author_name(name_text.strip(" ,;"))
        if not name:
            continue
        affiliations: list[str] = []
        for num in nums.split(","):
            institution = affiliation_map.get(normalize_space(num), "")
            if institution and institution not in affiliations:
                affiliations.append(institution)
        rows.append({"name": name, "affiliations": affiliations})
    return rows


def parse_ieee_official_authors(item: Any) -> list[str]:
    """Read the author line even when the official DOM omits affiliations."""
    collapse = item.select_one("div.collapse.authorlist")
    if collapse is None:
        return []
    author_segments: list[str] = []
    for child in collapse.children:
        if getattr(child, "name", None) == "br":
            break
        if getattr(child, "name", None) == "sup":
            continue
        author_segments.append(str(child))
    author_text = normalize_space(
        BeautifulSoup("".join(author_segments), "html.parser").get_text(" ", strip=True)
    )
    authors: list[str] = []
    for part in re.split(r",|\s+\band\b\s+", author_text, flags=re.IGNORECASE):
        name = clean_author_name(part)
        if len(normalize_person_name(name)) >= 2:
            authors.append(name)
    return authors


def clean_author_name(value: str) -> str:
    text = normalize_space(html.unescape(repair_gbk_mojibake(value)))
    text = re.sub(r"\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+\d{4}$", "", text)
    text = re.sub(r"\s*[\*\u2020\u2021\u00a7]+\s*$", "", text)
    text = re.sub(r"\s*\([^)]*\)$", lambda match: "" if AUTHOR_NOTE_PATTERN.search(match.group(0)) else match.group(0), text)
    text = normalize_space(text.strip(" ,;"))
    if text.casefold() in AUTHOR_NAME_PLACEHOLDERS:
        return ""
    return text


def fetch_acm_text_via_playwright(paper_url: str) -> str:
    if sync_playwright is None:
        return ""
    try:
        with sync_playwright() as p:
            launch_kwargs: dict[str, Any] = {"headless": True}
            chrome_path = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
            if chrome_path.exists():
                launch_kwargs["executable_path"] = str(chrome_path)
            browser = p.chromium.launch(**launch_kwargs)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720},
            )
            page = context.new_page()
            try:
                page.goto(paper_url, timeout=20000, wait_until="domcontentloaded")
                html = page.content()
            except Exception:
                html = ""
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
            return html
    except Exception:
        return ""


def find_local_chrome_binary() -> str:
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return ""


def find_local_chromedriver() -> str:
    import os

    candidates = [
        os.environ.get("ACM_CHROMEDRIVER_PATH", "").strip(),
        "/tmp/chromedriver149/chromedriver-mac-arm64/chromedriver",
        "/usr/local/bin/chromedriver",
        "/opt/homebrew/bin/chromedriver",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return ""


def fetch_acm_text_via_selenium(paper_url: str) -> str:
    """通过本地 Selenium 驱动的 Chrome 兜底抓取 ACM DOI 页 HTML。"""
    if webdriver is None or SeleniumChromeOptions is None or SeleniumChromeService is None:
        return ""
    chromedriver_path = find_local_chromedriver()
    chrome_binary = find_local_chrome_binary()
    if not chromedriver_path or not chrome_binary:
        return ""
    options = SeleniumChromeOptions()
    options.binary_location = chrome_binary
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,720")
    options.add_argument("--no-proxy-server")
    options.add_argument("--proxy-server=direct://")
    options.add_argument("--proxy-bypass-list=*")
    driver = None
    try:
        driver = webdriver.Chrome(
            service=SeleniumChromeService(chromedriver_path),
            options=options,
        )
        driver.set_page_load_timeout(30)
        driver.get(paper_url)
        return driver.page_source
    except Exception:
        return ""
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def fetch_acm_affiliations(
    paper_url: str,
    title: str = "",
) -> list[dict[str, Any]]:
    """结合 HTML 解析与浏览器兜底方式解析 ACM 的作者机构行。"""
    html = ""
    if not html:
        try:
            html = fetch_acm_text_via_playwright(paper_url)
        except Exception:
            html = ""
    if not html:
        try:
            html = fetch_acm_text_via_selenium(paper_url)
        except Exception:
            html = ""
    if not html:
        try:
            html = fetch_text(paper_url, timeout=20)
        except Exception:
            return []
    rows = parse_acm_affiliations_html(html)
    return rows if has_resolved_affiliations(rows) else []


def author_matches_with_aliases(
    author: str,
    candidate_name: str,
    author_name_aliases: dict[str, set[str]] | None = None,
) -> bool:
    if names_match(author, candidate_name):
        return True
    if not author_name_aliases:
        return False
    for canonical_name, aliases in author_name_aliases.items():
        variants = aliases | {canonical_name}
        if any(names_match(author, variant) for variant in variants) and any(
            names_match(candidate_name, variant) for variant in variants
        ):
            return True
    return False


def parse_usenix_affiliations_html(html_text: str) -> list[dict[str, Any]]:
    def split_author_group(names_text: str) -> list[str]:
        normalized_names = html.unescape(names_text)
        normalized_names = re.sub(r"\s+", " ", normalized_names).strip(" ,;")
        normalized_names = re.sub(r",\s+and\s+", ", ", normalized_names)
        normalized_names = re.sub(r"\s+and\s+", ", ", normalized_names)
        return [name for name in (clean_author_name(part) for part in normalized_names.split(",")) if name]

    authors = re.findall(r'<meta\s+name="citation_author"\s+content="([^"]+)"', html_text)
    institutions = re.findall(r'<meta\s+name="citation_author_institution"\s+content="([^"]+)"', html_text)
    meta_rows = []
    for index, author in enumerate(authors):
        inst = institutions[index] if index < len(institutions) else ""
        clean_author = clean_author_name(author)
        clean_inst = normalize_space(html.unescape(inst).rstrip(";"))
        meta_rows.append({"name": clean_author, "affiliations": [clean_inst] if clean_inst else []})

    author_block_rows = []
    author_block_match = re.search(
        r'<div class="field field-name-field-paper-people-text.*?<p>(.*?)</p>',
        html_text,
        re.DOTALL,
    )
    if author_block_match:
        author_block = author_block_match.group(1)
        for names_text, institution_text in re.findall(r'([^<]+?),\s*<em>(.*?)</em>', author_block, re.DOTALL):
            institution = normalize_space(html.unescape(re.sub(r"<[^>]+>", " ", institution_text)).rstrip(";"))
            for name in split_author_group(names_text):
                author_block_rows.append({"name": name, "affiliations": [institution] if institution else []})

    if not meta_rows:
        return author_block_rows
    if not author_block_rows:
        return meta_rows

    merged = {row["name"]: {"name": row["name"], "affiliations": list(row.get("affiliations", []))} for row in meta_rows if row.get("name")}
    for row in author_block_rows:
        name = row.get("name", "")
        if not name:
            continue
        if name not in merged:
            merged[name] = {"name": name, "affiliations": list(row.get("affiliations", []))}
            continue
        if not merged[name].get("affiliations") and row.get("affiliations"):
            merged[name]["affiliations"] = list(row["affiliations"])
    return list(merged.values())


def parse_ndss_affiliations_html(html: str) -> list[dict[str, Any]]:
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)

    paper_data_match = re.search(r'<div class="paper-data">(.*?)</div>\s*<div class="paper-buttons">', text, re.DOTALL | re.IGNORECASE)
    if paper_data_match:
        paper_data = paper_data_match.group(1)
        paragraphs = re.findall(r"<p>(.*?)</p>", paper_data, re.DOTALL | re.IGNORECASE)
        for paragraph in paragraphs:
            clean = normalize_space(re.sub(r"<[^>]+>", " ", paragraph))
            if "(" not in clean or ")" not in clean:
                continue
            result = []
            for match in re.finditer(r"([^,]+?)\s*\(([^)]+)\)", clean):
                name = clean_author_name(match.group(1))
                inst = normalize_space(match.group(2))
                if len(name.split()) < 2 or len(inst) <= 3 or inst.startswith("http") or inst[0].isdigit():
                    continue
                result.append({"name": name, "affiliations": [inst]})
            if result:
                return result

    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.DOTALL | re.IGNORECASE)
    if not h1_match:
        return []
    after_h1 = text[h1_match.end():h1_match.end() + 3000]
    after_h1_clean = re.sub(r"<[^>]+>", " ", after_h1)
    after_h1_clean = re.sub(r"\s+", " ", after_h1_clean).strip()
    result = []
    pattern = r"([A-Z][a-zA-ZÀ-ÿ\-']+(?:\s+(?:van|de|di|da|von|le|la|el)\s+)?(?:\s+[A-Z][a-zA-ZÀ-ÿ\-']+(?:\s+\d{4})?)+)\s*\(([^)]+)\)"
    for match in re.finditer(pattern, after_h1_clean):
        name = clean_author_name(match.group(1))
        inst = match.group(2).strip()
        if len(inst) > 3 and not inst.startswith("http") and not inst[0].isdigit():
            result.append({"name": name, "affiliations": [inst]})
    return result


def parse_ieee_affiliations_html(html: str) -> list[dict[str, Any]]:
    match = re.search(r'xplGlobal\.document\.metadata\s*=\s*(\{.*?\});', html, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    result = []
    for author in data.get("authors", []):
        name = clean_author_name(author.get("name", ""))
        affiliations = author.get("affiliation", [])
        if name:
            result.append({"name": name, "affiliations": affiliations})
    return result


def extract_meta_contents(html_text: str, meta_name: str) -> list[str]:
    pattern = rf'<meta[^>]+name=["\']{re.escape(meta_name)}["\'][^>]+content=["\']([^"\']*)["\']'
    return [normalize_space(html.unescape(value)) for value in re.findall(pattern, html_text, re.IGNORECASE)]


def normalize_affiliation_values(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = normalize_space(re.sub(r"<[^>]+>", " ", html.unescape(repair_gbk_mojibake(value))))
        if not clean:
            continue
        key = clean.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(clean)
    return normalized


def affiliation_names_from_value(value: Any) -> list[str]:
    if isinstance(value, list):
        names: list[str] = []
        for item in value:
            names.extend(affiliation_names_from_value(item))
        return normalize_affiliation_values(names)
    if isinstance(value, dict):
        candidates = [
            value.get("name", ""),
            value.get("alternateName", ""),
            value.get("legalName", ""),
        ]
        return normalize_affiliation_values([str(candidate) for candidate in candidates if normalize_space(str(candidate))])
    text = normalize_space(str(value))
    return normalize_affiliation_values([text]) if text else []


def parse_acm_json_ld_authors(html_text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for block in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>\s*(.*?)\s*</script>',
        html_text,
        re.IGNORECASE | re.DOTALL,
    ):
        try:
            payload = json.loads(html.unescape(block))
        except Exception:
            continue

        def visit(node: Any) -> None:
            if isinstance(node, list):
                for item in node:
                    visit(item)
                return
            if not isinstance(node, dict):
                return
            author_value = node.get("author")
            if isinstance(author_value, list):
                for author in author_value:
                    if not isinstance(author, dict):
                        continue
                    name = clean_author_name(author.get("name", ""))
                    if not name:
                        continue
                    affiliations = affiliation_names_from_value(author.get("affiliation", []))
                    rows.append({"name": name, "affiliations": affiliations})
            for nested in node.values():
                if isinstance(nested, (dict, list)):
                    visit(nested)

        visit(payload)
    return rows


def parse_acm_microdata_authors(html_text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    pattern = re.compile(
        r'<div[^>]+class="dropBlock__body"[^>]*>.*?<div[^>]+property="name"[^>]*>.*?'
        r'<span[^>]+property="givenName"[^>]*>(.*?)</span>\s*'
        r'<span[^>]+property="familyName"[^>]*>(.*?)</span>.*?'
        r'<div[^>]+class="affiliations"[^>]*>(.*?)</div>',
        re.IGNORECASE | re.DOTALL,
    )
    for given_name, family_name, affiliation_block in pattern.findall(html_text):
        name = clean_author_name(
            f"{normalize_space(html.unescape(re.sub(r'<[^>]+>', ' ', given_name)))} "
            f"{normalize_space(html.unescape(re.sub(r'<[^>]+>', ' ', family_name)))}"
        )
        if not name:
            continue
        affiliations = normalize_affiliation_values(
            re.findall(
                r'<span[^>]+property="name"[^>]*>(.*?)</span>',
                affiliation_block,
                re.IGNORECASE | re.DOTALL,
            )
        )
        key = name.casefold()
        if key in seen_names:
            continue
        seen_names.add(key)
        rows.append({"name": name, "affiliations": affiliations})
    return rows


def parse_acm_contributor_holders(html_text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    holder_pattern = re.compile(
        r"<div[^>]+data-doi=[\"']10\.1145/contrib-[^\"']+[\"'][^>]*>.*?(?=<div[^>]+data-doi=[\"']10\.1145/contrib-|<div class=\"core-self-citation\"|$)",
        re.IGNORECASE | re.DOTALL,
    )
    for block in holder_pattern.findall(html_text):
        given_name = ""
        family_name = ""
        given_match = re.search(r"<span[^>]+property=[\"']givenName[\"'][^>]*>(.*?)</span>", block, re.IGNORECASE | re.DOTALL)
        family_match = re.search(r"<span[^>]+property=[\"']familyName[\"'][^>]*>(.*?)</span>", block, re.IGNORECASE | re.DOTALL)
        if given_match:
            given_name = normalize_space(html.unescape(re.sub(r"<[^>]+>", " ", given_match.group(1))))
        if family_match:
            family_name = normalize_space(html.unescape(re.sub(r"<[^>]+>", " ", family_match.group(1))))
        name = clean_author_name(f"{given_name} {family_name}")
        if not name:
            name_match = re.search(r"<a[^>]+title=[\"']([^\"']+)[\"'][^>]*role=[\"']button[\"']", block, re.IGNORECASE)
            if name_match:
                name = clean_author_name(name_match.group(1))
        if not name:
            name_match = re.search(r"<div[^>]+property=[\"']name[\"'][^>]*>(.*?)</div>", block, re.IGNORECASE | re.DOTALL)
            if name_match:
                name = clean_author_name(re.sub(r"<[^>]+>", " ", name_match.group(1)))
        if not name:
            continue
        affiliations = normalize_affiliation_values(
            re.findall(
                r"<(?:div|span)[^>]+property=[\"']affiliation[\"'][^>]*>.*?<span[^>]+property=[\"']name[\"'][^>]*>(.*?)</span>",
                block,
                re.IGNORECASE | re.DOTALL,
            )
        )
        if not affiliations:
            affiliations = normalize_affiliation_values(
                re.findall(
                    r"<div[^>]+class=[\"'][^\"']*affiliations[^\"']*[\"'][^>]*>(.*?)</div>",
                    block,
                    re.IGNORECASE | re.DOTALL,
                )
            )
        key = name.casefold()
        if key in seen_names:
            continue
        seen_names.add(key)
        rows.append({"name": name, "affiliations": affiliations})
    return rows


def parse_acm_affiliations_html(html_text: str) -> list[dict[str, Any]]:
    """从元数据、JSON-LD 和可见页面块中解析 ACM 作者机构结构。"""
    meta_authors = extract_meta_contents(html_text, "citation_author")
    meta_institutions = extract_meta_contents(html_text, "citation_author_institution")
    if meta_authors:
        rows: list[dict[str, Any]] = []
        for index, author in enumerate(meta_authors):
            affiliations = []
            if index < len(meta_institutions):
                affiliations = normalize_affiliation_values([meta_institutions[index]])
            rows.append({"name": clean_author_name(author), "affiliations": affiliations})
        if any(row.get("affiliations") for row in rows):
            return rows

    json_ld_rows = parse_acm_json_ld_authors(html_text)
    if any(row.get("affiliations") for row in json_ld_rows):
        return json_ld_rows

    microdata_rows = parse_acm_microdata_authors(html_text)
    if any(row.get("affiliations") for row in microdata_rows):
        return microdata_rows

    contributor_rows = parse_acm_contributor_holders(html_text)
    if any(row.get("affiliations") for row in contributor_rows):
        return contributor_rows

    author_blocks = re.findall(
        r'(<[^>]+class=["\'][^"\']*author[^"\']*["\'][^>]*>.*?</(?:article|div|li|section)>)',
        html_text,
        re.IGNORECASE | re.DOTALL,
    )
    parsed_rows: list[dict[str, Any]] = []
    for block in author_blocks:
        block_text = normalize_space(html.unescape(re.sub(r"<[^>]+>", " ", block)))
        if not block_text:
            continue
        name_match = re.search(r"\b([A-Z][A-Za-zÀ-ÿ'`\-]+(?:\s+[A-Z][A-Za-zÀ-ÿ'`\-]+){1,5})\b", block_text)
        if not name_match:
            continue
        name = clean_author_name(name_match.group(1))
        if not name:
            continue
        affiliations = normalize_affiliation_values(
            re.findall(
                r'(?:affiliation|institution)[^<>:]{0,40}[:\s]\s*([^<>{}]{4,200})',
                block_text,
                re.IGNORECASE,
            )
        )
        if affiliations:
            parsed_rows.append({"name": name, "affiliations": affiliations})
    if any(row.get("affiliations") for row in parsed_rows):
        return parsed_rows
    return []


def fetch_text(url: str, timeout: int = 20) -> str:
    request = urllib.request.Request(url, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def slug_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalize_space(value).casefold()).strip("-")


CCS_SOURCE_FORMAT_BY_YEAR = {
    2020: "html_card",
    2021: "html_card",
    2022: "html_table",
    2023: "xml_profiles",
    2024: "html_table",
    2025: "json_cycles",
}


def fetch_ccs_html_card_official_entries(year: int) -> list[dict[str, Any]]:
    try:
        soup = BeautifulSoup(fetch_text(f"https://www.sigsac.org/ccs/CCS{year}/accepted-papers.html", timeout=30), "html.parser")
    except Exception:
        return []
    entries: list[dict[str, Any]] = []
    for row in soup.select("div.row.papers-item"):
        title_el = row.select_one("b")
        author_el = row.select_one("p")
        title = normalize_space(title_el.get_text(" ", strip=True)) if title_el else ""
        author_text = normalize_space(author_el.get_text(" ", strip=True)) if author_el else ""
        _repaired_author_text, separator_repairs = repair_ccs_missing_author_separators(author_text)
        authors, official_affiliations = parse_ccs_row_author_text(author_text)
        if title:
            entries.append(
                {
                    "paperId": f"official/ccs_{year}/{slug_text(title)}",
                    "title": title,
                    "authors": authors,
                    "official_affiliations": official_affiliations,
                    "url": "",
                    "pages": "",
                    "source_repairs": (
                        [{"code": "missing_author_separator_recovered", "count": separator_repairs}]
                        if separator_repairs
                        else []
                    ),
                }
            )
    return entries


def fetch_ccs_html_table_official_entries(year: int) -> list[dict[str, Any]]:
    try:
        soup = BeautifulSoup(fetch_text(f"https://www.sigsac.org/ccs/CCS{year}/program/accepted-papers.html", timeout=30), "html.parser")
    except Exception:
        return []
    entries: list[dict[str, Any]] = []
    for row in soup.select("table tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        title = normalize_space(cells[0].get_text(" ", strip=True))
        if not title or title.casefold() == "title":
            continue
        authors, official_affiliations = parse_ccs_author_table_cell(cells[1])
        entries.append(
            {
                "paperId": f"official/ccs_{year}/{slug_text(title)}",
                "title": title,
                "authors": authors,
                "official_affiliations": official_affiliations,
                "url": "",
                "pages": "",
            }
        )
    return entries


def fetch_ccs_xml_profile_official_entries() -> list[dict[str, Any]]:
    try:
        papers_root = ET.fromstring(fetch_text("https://www.sigsac.org/ccs/CCS2023/assets/data/accepted_papers.xml", timeout=30))
        authors_root = ET.fromstring(fetch_text("https://www.sigsac.org/ccs/CCS2023/assets/data/author_profiles.xml", timeout=30))
        institutes_root = ET.fromstring(fetch_text("https://www.sigsac.org/ccs/CCS2023/assets/data/institute_profiles.xml", timeout=30))
    except Exception:
        return []

    institute_map: dict[str, str] = {}
    for institute in institutes_root.findall(".//institute"):
        institute_id = normalize_space(institute.findtext("id", ""))
        institute_name = normalize_space(institute.findtext("name", ""))
        if institute_id and institute_name:
            institute_map[institute_id] = institute_name

    author_map: dict[str, dict[str, Any]] = {}
    for author in authors_root.findall(".//author"):
        author_id = normalize_space(author.findtext("id", ""))
        author_name = clean_author_name(author.findtext("name", ""))
        institute_ids = [
            normalize_space(part)
            for part in normalize_space(author.findtext("institutes", "")).split(",")
            if normalize_space(part)
        ]
        affiliations = normalize_affiliation_values(
            [institute_map[institute_id] for institute_id in institute_ids if institute_id in institute_map]
        )
        if author_id and author_name:
            author_map[author_id] = {
                "name": author_name,
                "affiliations": affiliations,
            }

    entries: list[dict[str, Any]] = []
    for paper in papers_root.findall(".//paper"):
        title = normalize_space(paper.findtext("title", ""))
        if not title:
            continue
        author_ids = [
            normalize_space(part)
            for part in normalize_space(paper.findtext("authors", "")).split(",")
            if normalize_space(part)
        ]
        authors: list[str] = []
        official_affiliations: list[dict[str, Any]] = []
        for author_id in author_ids:
            author = author_map.get(author_id)
            if not author:
                continue
            authors.append(author["name"])
            official_affiliations.append(
                {
                    "name": author["name"],
                    "affiliations": list(author["affiliations"]),
                }
            )
        entries.append(
            {
                "paperId": f"official/ccs_2023/{slug_text(title)}",
                "title": title,
                "authors": authors,
                "official_affiliations": official_affiliations,
                "url": "",
                "pages": "",
            }
        )
    return entries


def fetch_ccs_json_cycle_official_entries() -> list[dict[str, Any]]:
    try:
        payload = json.loads(fetch_text("https://www.sigsac.org/ccs/CCS2025/assets/accepted-papers.json", timeout=30))
    except Exception:
        return []
    entries: list[dict[str, Any]] = []
    for cycle_name in ("firstCycle", "secondCycle"):
        for item in payload.get(cycle_name, []):
            title = normalize_space(item.get("title", ""))
            title = re.sub(r"^\(#\d+\)\s*", "", title)
            url = normalize_space(item.get("url", ""))
            doi = extract_doi_from_url(url)
            authors = [
                clean_author_name(author.get("name", ""))
                for author in item.get("authors", [])
                if clean_author_name(author.get("name", ""))
            ]
            official_affiliations = [
                {
                    "name": clean_author_name(author.get("name", "")),
                    "affiliations": normalize_affiliation_values([str(author.get("affiliation", ""))]),
                }
                for author in item.get("authors", [])
                if clean_author_name(author.get("name", ""))
            ]
            if title and doi:
                entries.append(
                    {
                        "paperId": "",
                        "title": title,
                        "authors": authors,
                        "official_affiliations": official_affiliations,
                        "url": url,
                        "pages": "",
                        "doi": doi,
                    }
                )
    return entries


def fetch_ccs_official_entries(year: int) -> list[dict[str, Any]]:
    source_format = CCS_SOURCE_FORMAT_BY_YEAR.get(year)
    if source_format == "html_card":
        return fetch_ccs_html_card_official_entries(year)
    if source_format == "html_table":
        return fetch_ccs_html_table_official_entries(year)
    if source_format == "xml_profiles":
        return fetch_ccs_xml_profile_official_entries()
    if source_format == "json_cycles":
        return fetch_ccs_json_cycle_official_entries()
    return []


def fetch_ndss_official_entries(year: int) -> list[dict[str, Any]]:
    try:
        soup = BeautifulSoup(fetch_text(f"https://www.ndss-symposium.org/ndss{year}/accepted-papers/", timeout=30), "html.parser")
    except Exception:
        return []
    entries: list[dict[str, Any]] = []
    for item in soup.select("div.pt-cv-content-item"):
        title_anchor = item.select_one("h2.pt-cv-title a[href]")
        if not title_anchor:
            continue
        title = normalize_space(title_anchor.get_text(" ", strip=True))
        url = normalize_space(title_anchor.get("href", ""))
        author_text = normalize_space(item.select_one(".pt-cv-ctf-value").get_text(" ", strip=True)) if item.select_one(".pt-cv-ctf-value") else ""
        authors = parse_author_names_from_official_affiliation_text(author_text)
        official_affiliations = parse_author_affiliations_from_parenthesized_text(author_text)
        if title and url:
            entries.append(
                {
                    "paperId": "",
                    "title": title,
                    "authors": authors,
                    "official_affiliations": official_affiliations,
                    "url": url,
                    "pages": "",
                }
            )
    return entries


def fetch_ieee_sp_official_entries(year: int) -> list[dict[str, Any]]:
    if year <= 2023:
        urls = [
            f"https://www.ieee-security.org/TC/SP{year}/program-papers.html",
            f"https://www.ieee-security.org/TC/SP{year}/program.html",
        ]
    else:
        urls = [f"https://sp{year}.ieee-security.org/accepted-papers.html"]
    entries: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for url in urls:
        try:
            soup = BeautifulSoup(fetch_text(url, timeout=30), "html.parser")
        except Exception:
            continue
        for item in soup.select("div.list-group-item"):
            title_el = item.find("b")
            if not title_el:
                continue
            title = normalize_space(title_el.get_text(" ", strip=True))
            title_key = official_title_key(title)
            if not title or title_key in seen_titles:
                continue
            block_text = normalize_space(item.get_text(" ", strip=True))
            author_text = block_text.replace(title, "", 1).strip(" -")
            authors = parse_author_names_from_official_affiliation_text(author_text)
            official_affiliations = parse_ieee_official_author_affiliations(item)
            if not authors and official_affiliations:
                authors = [
                    clean_author_name(str(row.get("name", "")))
                    for row in official_affiliations
                    if clean_author_name(str(row.get("name", "")))
                ]
            if not authors:
                authors = parse_ieee_official_authors(item)
            # The full program page also contains schedule placeholders and
            # committee meetings inside the same list-group markup as papers.
            if not authors:
                continue
            seen_titles.add(title_key)
            entries.append(
                {
                    "paperId": f"official/ieee_sp_{year}/{slug_text(title)}",
                    "title": title,
                    "authors": authors,
                    "official_affiliations": official_affiliations,
                    "url": "",
                    "pages": "",
                }
            )
    return entries


def fetch_usenix_affiliations(paper_url: str) -> list[dict[str, Any]]:
    try:
        html = fetch_text(paper_url, timeout=15)
    except Exception:
        return []
    return parse_usenix_affiliations_html(html)


def fetch_ndss_affiliations(paper_url: str) -> list[dict[str, Any]]:
    try:
        html = fetch_text(paper_url, timeout=15)
    except Exception:
        return []
    return parse_ndss_affiliations_html(html)


def fetch_ieee_affiliations(paper_url: str) -> list[dict[str, Any]]:
    try:
        html = fetch_text(paper_url, timeout=15)
    except Exception:
        return []
    return parse_ieee_affiliations_html(html)


def fetch_semantic_scholar_affiliations(title: str, authors: list[str]) -> list[dict[str, Any]]:
    """查询 Semantic Scholar，并将返回作者信息映射回目标作者列表。"""
    query = urllib.parse.quote_plus(title[:100])
    url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={query}&limit=1&fields=title,authors"
    try:
        data = fetch_json_with_rate_limit(
            "semantic_scholar",
            url,
            headers=semantic_scholar_headers(),
            timeout=20,
        )
    except Exception:
        return []
    papers = data.get("data", [])
    if not papers:
        return []
    result = []
    for author in papers[0].get("authors", []):
        name = author.get("name", "")
        affiliations = [author.get("affiliations", [""])[0]] if author.get("affiliations") else []
        if name:
            result.append({"name": name, "affiliations": affiliations})
    return result


def fetch_openalex_work_by_doi(doi: str) -> dict[str, Any]:
    normalized_doi = normalize_space(doi)
    if not normalized_doi:
        return {}
    url = f"https://api.openalex.org/works/doi:{urllib.parse.quote(normalized_doi, safe='')}"
    try:
        payload = fetch_json_with_rate_limit(
            "openalex",
            url,
            headers=openalex_headers(),
            timeout=8,
            max_retries=1,
        )
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def normalized_title_key(title: str) -> str:
    title = re.sub(r"<[^>]+>", " ", title)
    return re.sub(r"\s+", "", normalize_space(title).casefold().rstrip("."))


def normalize_person_name(value: str) -> list[str]:
    text = clean_author_name(value)
    text = text.translate(SPECIAL_NAME_CHAR_MAP)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"<[^>]+>", " ", text)
    text = normalize_space(text)
    if "," in text:
        parts = [part.strip() for part in text.split(",") if part.strip()]
        if len(parts) >= 2:
            text = f"{' '.join(parts[1:])} {parts[0]}"
    text = re.sub(r"[^A-Za-z0-9 ]+", " ", text)
    return [part.casefold() for part in text.split() if part]


def normalize_person_name_loose(value: str) -> list[str]:
    parts = normalize_person_name(value)
    loose_parts: list[str] = []
    for part in parts:
        loose = part
        for src, dst in (("ae", "a"), ("oe", "o"), ("ue", "u")):
            loose = loose.replace(src, dst)
        loose_parts.append(loose)
    return loose_parts


def bounded_edit_distance(left: str, right: str, limit: int) -> int:
    if left == right:
        return 0
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        row_min = current[0]
        for j, right_char in enumerate(right, start=1):
            cost = 0 if left_char == right_char else 1
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + cost,
                )
            )
            row_min = min(row_min, current[-1])
        if row_min > limit:
            return limit + 1
        previous = current
    return previous[-1]


def loose_name_variant_match(left_parts: list[str], right_parts: list[str]) -> bool:
    if not left_parts or not right_parts or len(left_parts) != len(right_parts):
        return False
    if left_parts == right_parts:
        return True
    if len(left_parts) >= 2:
        if left_parts[:-1] == right_parts[:-1]:
            left_last = left_parts[-1]
            right_last = right_parts[-1]
            if left_last and right_last and left_last[0] == right_last[0]:
                if bounded_edit_distance(left_last, right_last, 2) <= 2:
                    return True
    if len(left_parts) == 2:
        if left_parts[0] == right_parts[0]:
            if bounded_edit_distance(left_parts[1], right_parts[1], 2) <= 2:
                return True
    return False


def names_match(left: str, right: str) -> bool:
    left_parts = normalize_person_name(left)
    right_parts = normalize_person_name(right)
    if not left_parts or not right_parts:
        return False
    if left_parts == right_parts:
        return True
    if left_parts[0] == right_parts[0]:
        left_tail = "".join(left_parts[1:])
        right_tail = "".join(right_parts[1:])
        if left_tail and left_tail == right_tail:
            return True
    if len(left_parts) >= 2 and len(right_parts) >= 2:
        # Handle surname-first renderings such as "Wang Tao" or "Zhu Wei-dong".
        if left_parts[-1] == right_parts[0]:
            if "".join(left_parts[:-1]) == "".join(right_parts[1:]):
                return True
        if right_parts[-1] == left_parts[0]:
            if "".join(right_parts[:-1]) == "".join(left_parts[1:]):
                return True
    left_loose_parts = normalize_person_name_loose(left)
    right_loose_parts = normalize_person_name_loose(right)
    if loose_name_variant_match(left_parts, right_parts):
        return True
    if loose_name_variant_match(left_loose_parts, right_loose_parts):
        return True
    if left_parts[-1] != right_parts[-1]:
        return False
    if left_parts[0][0] != right_parts[0][0]:
        return False
    return True


def map_author_name(input_authors: list[str], candidate_name: str) -> str:
    for name in input_authors:
        if names_match(name, candidate_name):
            return name
    return ""


def normalized_person_key(value: str) -> str:
    return " ".join(normalize_person_name(value))


AFFILIATION_FRAGMENT_MERGE_RULES: list[tuple[str, str, str]] = [
    ("Department of Computer Science", "Engineering", "Department of Computer Science and Engineering"),
    ("Dept. of Computer Science", "Engineering", "Dept. of Computer Science and Engineering"),
    ("Mathematics", "Computer Science", "Mathematics and Computer Science"),
    ("Department of Applied Mathematics", "Computer Science", "Department of Applied Mathematics and Computer Science"),
    ("Electrical", "Computer Engineering", "Electrical and Computer Engineering"),
    (
        "School of Electrical Engineering",
        "Computer Science",
        "School of Electrical Engineering and Computer Science",
    ),
    ("School of Computing", "Information Technology", "School of Computing and Information Technology"),
    ("College of Computer", "Cyber Security", "College of Computer and Cyber Security"),
    ("College of Computer Science", "Engineering", "College of Computer Science and Engineering"),
    (
        "Paul G. Allen School of Computer Science",
        "Engineering",
        "Paul G. Allen School of Computer Science and Engineering",
    ),
    ("Institute of Information", "Engineering", "Institute of Information Engineering"),
    (
        "Key Laboratory of Trustworthy Distributed Computing",
        "Service",
        "Key Laboratory of Trustworthy Distributed Computing and Service",
    ),
    (
        "Laboratory for Advanced Computing",
        "Intelligence Engineering",
        "Laboratory for Advanced Computing and Intelligence Engineering",
    ),
]


DROP_IF_SUBSTRING_FRAGMENT_LABELS = {
    "Software",
}


DROP_EXACT_AFFILIATION_NOISE_LABELS = {
    # Commonly mis-extracted from "Menlo Park, CA, USA" location strings.
    "Menlo School",
}


IDENTIFIER_NOISE_PATTERN = re.compile(r"^\d{4}[-−]\d{4}[-−]\d{4}[-−][\dXx]{4}$")


def merge_affiliation_fragments(first: str, second: str) -> str | None:
    normalized_first = normalize_space(first)
    normalized_second = normalize_space(second)
    for prefix, continuation, merged_prefix in AFFILIATION_FRAGMENT_MERGE_RULES:
        if normalized_first != prefix:
            continue
        if not normalized_second.startswith(continuation):
            continue
        suffix = normalized_second[len(continuation):].lstrip(" ,")
        if not suffix:
            return merged_prefix
        if suffix.startswith("of "):
            return f"{merged_prefix} {suffix}"
        return f"{merged_prefix}, {suffix}"
    return None


def sanitize_affiliation_list(author: str, affiliations: list[str]) -> list[str]:
    cleaned = [normalize_space(value) for value in affiliations if normalize_space(value)]
    if not cleaned:
        return []
    merged: list[str] = []
    index = 0
    author_tokens = normalize_space(author).casefold().split()
    while index < len(cleaned):
        current = cleaned[index]
        if index + 1 < len(cleaned):
            merged_value = merge_affiliation_fragments(current, cleaned[index + 1])
            if merged_value is not None:
                merged.append(merged_value)
                index += 2
                continue
        current_tokens = current.casefold().split()
        if len(current_tokens) == 1 and len(author_tokens) >= 3 and current_tokens[0] in author_tokens:
            index += 1
            continue
        compact = current.replace("-", "").replace("−", "")
        if IDENTIFIER_NOISE_PATTERN.fullmatch(current) or (compact.isdigit() and len(compact) >= 12):
            index += 1
            continue
        if current in DROP_IF_SUBSTRING_FRAGMENT_LABELS and any(
            current.casefold() in sibling.casefold() and len(sibling) > len(current)
            for sibling in cleaned
            if sibling != current
        ):
            index += 1
            continue
        if current in DROP_EXACT_AFFILIATION_NOISE_LABELS:
            index += 1
            continue
        merged.append(current)
        index += 1

    deduped: list[str] = []
    seen: set[str] = set()
    for value in merged:
        marker = value.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(value)
    return deduped


def build_affiliation_map(author_affiliations: list[dict[str, Any]]) -> tuple[dict[str, list[str]], list[tuple[str, list[str]]]]:
    aff_map: dict[str, list[str]] = {}
    aff_name_pairs: list[tuple[str, list[str]]] = []
    for item in author_affiliations:
        source_name = normalize_space(str(item.get("name", "")))
        affiliations = sanitize_affiliation_list(source_name, list(item.get("affiliations", [])))
        if not source_name:
            continue
        aff_name_pairs.append((source_name, affiliations))
        aff_map[normalized_person_key(source_name)] = affiliations
    return aff_map, aff_name_pairs


def match_author_affiliations(
    authors: list[str],
    aff_map: dict[str, list[str]],
    aff_name_pairs: list[tuple[str, list[str]]],
    author_name_aliases: dict[str, set[str]] | None = None,
) -> list[list[str]]:
    matched_affiliations: list[list[str]] = []
    for author in authors:
        key = normalized_person_key(author)
        if key in aff_map:
            matched_affiliations.append(aff_map[key])
            continue
        matched = False
        for aff_name, affs in aff_name_pairs:
            aff_key = normalized_person_key(aff_name)
            if not aff_key:
                continue
            if author_matches_with_aliases(author, aff_name, author_name_aliases):
                matched_affiliations.append(affs)
                matched = True
                break
            if aff_key in key or key in aff_key:
                matched_affiliations.append(affs)
                matched = True
                break
            key_parts = key.split()
            aff_parts = aff_key.split()
            if (
                len(key_parts) >= 2
                and len(aff_parts) >= 2
                and key_parts[-1] == aff_parts[-1]
                and key_parts[0][0] == aff_parts[0][0]
            ):
                matched_affiliations.append(affs)
                matched = True
                break
        if not matched:
            matched_affiliations.append([])
    return matched_affiliations


def fill_shared_affiliation_gaps(matched_affiliations: list[list[str]]) -> list[list[str]]:
    known_affiliations = [
        "; ".join(affs)
        for affs in matched_affiliations
        if affs and "; ".join(affs).strip()
    ]
    unique_known_affiliations = sorted(set(known_affiliations))
    if len(unique_known_affiliations) != 1:
        return matched_affiliations
    shared_affiliations = next((affs for affs in matched_affiliations if affs), [])
    if not shared_affiliations:
        return matched_affiliations
    return [affs if affs else list(shared_affiliations) for affs in matched_affiliations]


def extract_doi_from_url(url: str) -> str:
    value = normalize_space(url)
    if not value:
        return ""
    value = value.rstrip("/")
    for marker in ("doi.org/", "dl.acm.org/doi/"):
        if marker in value:
            doi = value.split(marker, 1)[1].strip()
            return doi
    doi_match = re.search(r"\b10\.\d{4,9}/\S+\b", value)
    return doi_match.group(0).rstrip(").,;") if doi_match else ""


def map_openalex_authorships(authorships: list[dict[str, Any]], authors: list[str]) -> list[dict[str, Any]]:
    mapped_rows: list[dict[str, Any]] = []
    matched = 0
    for authorship in authorships:
        author_info = authorship.get("author", {})
        candidate_names = [
            normalize_space(str(author_info.get("display_name", ""))),
            normalize_space(str(authorship.get("raw_author_name", ""))),
        ]
        mapped_name = ""
        for candidate_name in candidate_names:
            if not candidate_name:
                continue
            mapped_name = map_author_name(authors, candidate_name)
            if mapped_name:
                break
        if not mapped_name:
            continue

        affiliations: list[str] = []
        for institution in authorship.get("institutions", []):
            inst_name = normalize_space(str(institution.get("display_name", "")))
            if inst_name and inst_name not in affiliations:
                affiliations.append(inst_name)
        for raw_aff in authorship.get("raw_affiliation_strings", []):
            raw_name = normalize_space(str(raw_aff))
            if raw_name and raw_name not in affiliations:
                affiliations.append(raw_name)
        mapped_rows.append({"name": mapped_name, "affiliations": affiliations})
        if affiliations:
            matched += 1
    if matched > 0:
        return mapped_rows
    return []


def has_resolved_affiliations(rows: list[dict[str, Any]]) -> bool:
    for row in rows:
        affiliations = row.get("affiliations", [])
        if any(normalize_space(str(value)) for value in affiliations):
            return True
    return False


def cache_has_full_author_coverage(
    rows: list[dict[str, Any]],
    authors: list[str],
    author_name_aliases: dict[str, set[str]] | None = None,
) -> bool:
    if not rows:
        return False
    aff_map, aff_name_pairs = build_affiliation_map(rows)
    matched_affiliations = match_author_affiliations(authors, aff_map, aff_name_pairs, author_name_aliases)
    return bool(authors) and all(bool(affs) for affs in matched_affiliations)


def count_covered_authors(
    rows: list[dict[str, Any]],
    authors: list[str],
    author_name_aliases: dict[str, set[str]] | None = None,
) -> int:
    if not rows or not authors:
        return 0
    aff_map, aff_name_pairs = build_affiliation_map(rows)
    matched_affiliations = match_author_affiliations(authors, aff_map, aff_name_pairs, author_name_aliases)
    return sum(1 for affs in matched_affiliations if affs)


def choose_best_affiliation_rows(
    authors: list[str],
    author_name_aliases: dict[str, set[str]] | None,
    *candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    best_rows: list[dict[str, Any]] = []
    best_score = (-1, -1)
    for rows in candidates:
        if not has_resolved_affiliations(rows):
            continue
        score = (count_covered_authors(rows, authors, author_name_aliases), len(rows))
        if score > best_score:
            best_rows = rows
            best_score = score
    return best_rows


def candidate_legacy_affiliation_cache_dirs() -> list[Path]:
    dirs: list[Path] = []
    env_dir = os.environ.get("LEGACY_AFFILIATION_CACHE_DIR", "").strip()
    if env_dir:
        dirs.append(Path(env_dir))
    dirs.append(Path("/Users/liziyu/llm_conference_us/Security-data/data/resolution/affiliation_cache_2020-2026"))
    deduped: list[Path] = []
    seen: set[str] = set()
    for directory in dirs:
        key = str(directory)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(directory)
    return deduped


def candidate_legacy_open_pdf_manifest_paths(config: ConferenceConfig) -> list[Path]:
    paths: list[Path] = []
    env_path = os.environ.get("LEGACY_OPEN_PDF_MANIFEST_PATH", "").strip()
    if env_path:
        paths.append(Path(env_path))
    if config.conference == "CCS":
        paths.append(
            Path(
                "/Users/liziyu/graduation/会议主题及自动化采集的文件（原名during)/ccstry/data/ccs/ccs2020_2025_open_pdf_manifest.json"
            )
        )
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


@lru_cache(maxsize=8)
def load_legacy_open_pdf_manifest_index(path_str: str) -> dict[str, dict[str, Any]]:
    path = Path(path_str)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, list):
        return {}

    index: dict[str, dict[str, Any]] = {}
    for row in payload:
        if not isinstance(row, dict):
            continue
        doi = normalize_space(str(row.get("doi", ""))).casefold()
        if not doi or doi in index:
            continue
        index[doi] = row
    return index


def load_legacy_affiliations_for_paper(
    config: ConferenceConfig,
    paper: dict[str, Any],
) -> list[dict[str, Any]]:
    url = normalize_space(str(paper.get("url", "")))
    doi = extract_doi_from_url(url)
    paper_id = normalize_space(str(paper.get("paperId", ""))).replace("/", "_")
    candidate_keys: list[str] = []
    if doi:
        candidate_keys.append(f"{config.key}_{doi.replace('/', '_')}_affiliations.json")
    if paper_id:
        candidate_keys.extend(
            [
                f"{paper_id}_affiliations.json",
                f"{config.key}_{paper_id}_affiliations.json",
            ]
        )
        if config.conference == "USENIX_SECURITY":
            candidate_keys.extend(
                [
                    f"usenix_{config.year}_{paper_id}_affiliations.json",
                    f"usenix_security_{config.year}_{paper_id}_affiliations.json",
                ]
            )
    if not candidate_keys:
        return []
    deduped_keys = list(dict.fromkeys(candidate_keys))
    for directory in candidate_legacy_affiliation_cache_dirs():
        for cache_key in deduped_keys:
            path = directory / cache_key
            if not path.exists():
                continue
            try:
                rows = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if has_resolved_affiliations(rows):
                return rows
    return []


@lru_cache(maxsize=32)
def load_official_affiliation_entries(config_key: str) -> list[dict[str, Any]]:
    config = CONFERENCES[config_key]
    if config.conference == "USENIX_SECURITY":
        return fetch_usenix_official_entries(config.year)
    if config.conference == "NDSS":
        return fetch_ndss_official_entries(config.year)
    if config.conference == "IEEE_S&P":
        return fetch_ieee_sp_official_entries(config.year)
    if config.conference == "CCS":
        return fetch_ccs_official_entries(config.year)
    return []


def load_official_affiliations_for_paper(
    config: ConferenceConfig,
    paper: dict[str, Any],
) -> list[dict[str, Any]]:
    try:
        entries = load_official_affiliation_entries(config.key)
    except Exception:
        return []
    if not entries:
        return []
    title_key = official_title_key(str(paper.get("title", "")))
    url_key = normalize_space(str(paper.get("url", "")))
    doi_key = extract_doi_from_url(url_key)
    for entry in entries:
        entry_title_key = official_title_key(str(entry.get("title", "")))
        entry_url_key = normalize_space(str(entry.get("url", "")))
        entry_doi_key = normalize_space(str(entry.get("doi", "")))
        if url_key and entry_url_key and url_key == entry_url_key:
            return list(entry.get("official_affiliations", []))
        if doi_key and entry_doi_key and doi_key == entry_doi_key:
            return list(entry.get("official_affiliations", []))
        if title_key and entry_title_key and title_key == entry_title_key:
            return list(entry.get("official_affiliations", []))
    return []


def load_legacy_openalex_affiliations_for_paper(
    config: ConferenceConfig,
    paper: dict[str, Any],
) -> list[dict[str, Any]]:
    doi = extract_doi_from_url(normalize_space(str(paper.get("url", ""))))
    authors = paper.get("authors", [])
    if not doi or not authors:
        return []

    for manifest_path in candidate_legacy_open_pdf_manifest_paths(config):
        index = load_legacy_open_pdf_manifest_index(str(manifest_path))
        if not index:
            continue
        row = index.get(doi.casefold())
        if not row:
            continue
        openalex = row.get("openalex")
        if not isinstance(openalex, dict):
            continue
        mapped_rows = map_openalex_authorships(openalex.get("authorships", []), authors)
        if has_resolved_affiliations(mapped_rows):
            return mapped_rows
    return []


def fetch_openalex_affiliations_by_doi(doi: str, authors: list[str], year: int | None = None) -> list[dict[str, Any]]:
    """优先按 DOI 从 OpenAlex 获取作者机构信息。"""
    normalized_doi = normalize_space(doi)
    if not normalized_doi:
        return []
    url = f"https://api.openalex.org/works/doi:{urllib.parse.quote(normalized_doi, safe='')}"
    try:
        payload = fetch_json_with_rate_limit(
            "openalex",
            url,
            headers=openalex_headers(),
            timeout=20,
        )
    except Exception:
        return []

    publication_year = payload.get("publication_year")
    if year is not None and publication_year is not None and int(publication_year) != int(year):
        return []
    return map_openalex_authorships(payload.get("authorships", []), authors)


def fetch_openalex_affiliations(title: str, authors: list[str], year: int | None = None) -> list[dict[str, Any]]:
    """在通用兜底场景下通过标题检索 OpenAlex 获取作者机构信息。"""
    query = urllib.parse.quote(title)
    url = f"https://api.openalex.org/works?search={query}&per-page=5"
    try:
        payload = fetch_json_with_rate_limit(
            "openalex",
            url,
            headers=openalex_headers(),
            timeout=20,
        )
    except Exception:
        return []

    for result in payload.get("results", []):
        display_name = normalize_space(str(result.get("display_name", "")))
        publication_year = result.get("publication_year")
        if normalized_title_key(display_name) != normalized_title_key(title):
            continue
        if year is not None and publication_year is not None and int(publication_year) != int(year):
            continue
        mapped_rows = map_openalex_authorships(result.get("authorships", []), authors)
        if mapped_rows:
            return mapped_rows
    return []


def resolve_openalex_fallback(url: str, title: str, authors: list[str], year: int | None = None) -> list[dict[str, Any]]:
    doi = extract_doi_from_url(url)
    if doi:
        affiliations = fetch_openalex_affiliations_by_doi(doi, authors, year)
        if has_resolved_affiliations(affiliations):
            return affiliations
    affiliations = fetch_openalex_affiliations(title, authors, year)
    if has_resolved_affiliations(affiliations):
        return affiliations
    return []


def resolve_affiliations_for_paper(
    config: ConferenceConfig,
    paper: dict[str, Any],
    cache_dir: Path,
    fetch_from_network: bool = False,
    author_name_aliases: dict[str, set[str]] | None = None,
) -> list[dict[str, Any]]:
    """对单篇论文执行会议定制的兜底链路，并尽量复用缓存。"""
    import time

    cache_file = cache_dir / f"{paper['paperId'].replace('/', '_')}_affiliations.json"
    authors = paper.get("authors", [])
    url = paper.get("url", "")
    title = paper.get("title", "")
    cached: list[dict[str, Any]] = []
    official_cached = load_official_affiliations_for_paper(config, paper) if fetch_from_network else []
    if config.conference == "CCS" and cache_has_full_author_coverage(official_cached, authors, author_name_aliases):
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(official_cached, ensure_ascii=False, indent=2), encoding="utf-8")
        return official_cached
    if cache_file.exists():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        if has_resolved_affiliations(cached) and cache_has_full_author_coverage(cached, authors, author_name_aliases):
            return cached
    legacy_cached = load_legacy_affiliations_for_paper(config, paper)
    legacy_openalex = load_legacy_openalex_affiliations_for_paper(config, paper)
    best_local_rows = choose_best_affiliation_rows(
        authors,
        author_name_aliases,
        official_cached,
        cached,
        legacy_cached,
        legacy_openalex,
    )
    if best_local_rows:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(best_local_rows, ensure_ascii=False, indent=2), encoding="utf-8")
        if cache_has_full_author_coverage(best_local_rows, authors, author_name_aliases) or not fetch_from_network:
            return best_local_rows
    if not fetch_from_network:
        return []

    affiliations = []
    time.sleep(0.3)
    if config.conference == "USENIX_SECURITY" and url:
        affiliations = fetch_usenix_affiliations(url)
        if not has_resolved_affiliations(affiliations):
            affiliations = resolve_openalex_fallback(url, title, authors, config.year)
    elif config.conference == "NDSS" and url:
        affiliations = fetch_ndss_affiliations(url)
        if not has_resolved_affiliations(affiliations):
            affiliations = resolve_openalex_fallback(url, title, authors, config.year)
    elif config.conference == "IEEE_S&P" and url and "doi.org" in url:
        affiliations = fetch_ieee_affiliations(url)
        if not has_resolved_affiliations(affiliations):
            affiliations = resolve_openalex_fallback(url, title, authors, config.year)
    elif config.conference == "CCS" and url:
        affiliations = fetch_acm_affiliations(url, title=title)
        doi = extract_doi_from_url(url)
        if not has_resolved_affiliations(affiliations) and doi:
            affiliations = fetch_openalex_affiliations_by_doi(doi, authors, config.year)
        if not has_resolved_affiliations(affiliations):
            affiliations = fetch_openalex_affiliations(title, authors, config.year)
        if not has_resolved_affiliations(affiliations):
            affiliations = fetch_semantic_scholar_affiliations(title, authors)

    affiliations = choose_best_affiliation_rows(authors, author_name_aliases, best_local_rows, affiliations)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(affiliations, ensure_ascii=False, indent=2), encoding="utf-8")
    return affiliations
