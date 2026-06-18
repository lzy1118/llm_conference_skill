from __future__ import annotations

import argparse
import csv
import html
import json
import mimetypes
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
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

from backend_common import conference_interim_dir, conference_output_dir, conference_pdf_dir, conference_raw_dir, summary_interim_dir, summary_output_dir, write_csv, write_workbook
from api_runtime import fetch_json_with_rate_limit, openalex_headers, semantic_scholar_headers
from classification_common import classify_with_patterns, load_override_rows, normalize_space


BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


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

US_EXACT_ALIASES = {
    "mit", "nist", "sri", "uc san diego", "uc berkeley", "uc irvine",
    "uc davis", "uc santa barbara", "uc santa cruz", "uc los angeles", "ucla",
    "ut austin", "uiuc", "umd", "nyu", "yale", "duke", "cmu", "usc",
    "gatech", "georgia tech",
}

US_KEYWORD_PATTERNS = [
    r"\bmassachusetts institute of technology\b", r"\bcarnegie mellon university\b",
    r"\bstanford university\b", r"\bprinceton university\b", r"\bcornell university\b",
    r"\bcornell tech\b", r"\bbrown university\b", r"\bduke university\b",
    r"\byale university\b", r"\byale\b", r"\bcolumbia university\b",
    r"\bnew york university\b", r"\bnyu\b", r"\bboston university\b",
    r"\bjohns hopkins university\b", r"\bjhu\b", r"\buniversity of california\b",
    r"\buniversity of washington\b", r"\buniversity of wisconsin\b", r"\buw-madison\b",
    r"\buniversity of maryland\b", r"\bumd\b", r"\buniversity of pennsylvania\b",
    r"\buniversity of michigan\b", r"\buniversity of texas\b", r"\but austin\b",
    r"\buniversity of illinois\b", r"\buiuc\b", r"\burbana-champaign\b",
    r"\bgeorgia tech\b", r"\bgeorgia institute of technology\b", r"\bcity college of new york\b",
    r"\bcuny\b", r"\bnorth carolina state university\b", r"\bnortheastern university\b",
    r"\bpurdue university\b", r"\brice university\b", r"\bstony brook university\b",
    r"\btexas a&m university\b", r"\bunc chapel hill\b", r"\buniversity of connecticut\b",
    r"\bwashington state university\b", r"\bgoogle\b", r"\bmeta\b", r"\bmicrosoft\b",
    r"\bibm research\b", r"\bintel\b", r"\bcloudflare\b", r"\bvisa research\b",
    r"\bamazon\b", r"\baws\b", r"\bapple\b", r"\bnational institute of standards and technology\b",
    r"\bsandia national lab\b", r"\bsandia national laboratories\b", r"\boak ridge national lab\b",
    r"\bargon national lab\b", r"\blawrence livermore\b", r"\blos alamos\b",
    r"\buniversity of north carolina\b", r"\buniversity of virginia\b", r"\buniversity of florida\b",
    r"\buniversity of colorado\b", r"\buniversity of arizona\b", r"\buniversity of southern california\b",
    r"\busc\b", r"\bucla\b", r"\bucsd\b", r"\bucsb\b", r"\bohio state university\b",
    r"\bpenn state\b", r"\bvirginia tech\b", r"\brutgers\b", r"\buc berkeley\b", r"\bucb\b",
    r"\buniversity of massachusetts\b", r"\bumass\b", r"\buniversity of minnesota\b",
    r"\buniversity of iowa\b", r"\buniversity of utah\b", r"\buniversity of oregon\b",
    r"\boregon state university\b", r"\buniversity of notre dame\b", r"\bnorthwestern university\b",
    r"\bemory university\b", r"\bgeorge mason university\b", r"\bgeorge washington university\b",
    r"\bamerican university\b", r"\bwayne state university\b", r"\bcase western\b",
    r"\buniversity of cincinnati\b", r"\buniversity of kansas\b", r"\buniversity of kentucky\b",
    r"\buniversity of tennessee\b", r"\buniversity of alabama\b", r"\buniversity of oklahoma\b",
    r"\buniversity of nebraska\b", r"\buniversity of south carolina\b", r"\buniversity of hawaii\b",
    r"\buniversity of delaware\b", r"\buniversity of maryland baltimore\b", r"\bstanford\b",
    r"\bmit\b", r"\bcaltech\b", r"\bharvard\b", r"\byale\b", r"\bprinceton\b",
    r"\bcolumbia\b", r"\bupenn\b", r"\bcornell\b", r"\bucsf\b", r"\buw\b", r"\bgmu\b",
    r"\bpurdue\b", r"\bnortheastern\b", r"\barizona state university\b", r"\basu\b",
    r"\buniversity of illinois chicago\b", r"\buic\b", r"\buniversity of texas at dallas\b",
    r"\butd\b", r"\buniversity of texas at san antonio\b", r"\butsa\b", r"\bsmu\b",
    r"\bsouthern methodist\b", r"\bdrexel university\b", r"\bstevens institute\b",
    r"\bworcester polytechnic\b", r"\bwpi\b", r"\brensselaer\b", r"\brpi\b", r"\buc davis\b",
    r"\buc irvine\b", r"\buc santa cruz\b", r"\bsuny\b", r"\bdisney research\b",
    r"\bqualcomm\b", r"\bnvidia\b", r"\bboeing\b", r"\bford\b", r"\bge research\b",
    r"\bsri international\b", r"\bbattelle\b", r"\bida\b", r"\bmitre\b", r"\brand\b",
    r"\bnasa\b", r"\bnoaa\b", r"\bnational security agency\b", r"\bnsa\b",
    r"\bdefense advanced research\b", r"\bdarpa\b", r"\barmy research lab\b",
    r"\bnaval research\b", r"\bair force research\b",
]

NON_US_KEYWORD_PATTERNS = [
    r"\beth zurich\b", r"\beth z.rich\b", r"\busi, lugano\b", r"\buniversity of luxembourg\b",
    r"\bruhr university bochum\b", r"\bkings? college london\b", r"\broyal holloway\b",
    r"\buniversity of auckland\b", r"\btechnical university of denmark\b", r"\bibm research europe\b",
    r"\buniversity of cambridge\b", r"\buniversity of oxford\b", r"\bimperial college\b",
    r"\bucl\b", r"\buniversity college london\b", r"\binria\b", r"\bcnrs\b",
    r"\buniversity of melbourne\b", r"\buniversity of sydney\b", r"\bnanyang technological\b",
    r"\bnational university of singapore\b", r"\btsinghua\b", r"\bpeking\b", r"\bfudan\b",
    r"\buniversity of tokyo\b", r"\bkyoto\b", r"\btechnische universit\b", r"\bludwig maximilian\b",
    r"\bmax planck\b", r"\buniversity of edinburgh\b", r"\buniversity of manchester\b",
    r"\buniversity of birmingham\b", r"\buniversity of bristol\b", r"\buniversity of glasgow\b",
    r"\bkarlsruhe institute\b", r"\buniversity of stuttgart\b", r"\bdarmstadt\b", r"\braadboud\b",
    r"\beindhoven\b", r"\bdelft\b", r"\buniversity of oslo\b", r"\bkth\b", r"\bchalmers\b",
    r"\buniversity of helsinki\b", r"\baalto\b", r"\buniversity of waterloo\b", r"\buniversity of toronto\b",
    r"\bmcgill\b", r"\buniversity of british columbia\b", r"\bepfl\b", r"\buniversity of bern\b",
    r"\buniversity of zurich\b", r"\buniversity of geneva\b", r"\buniversit.t basel\b", r"\bweizmann\b",
    r"\btechnion\b", r"\btel aviv\b", r"\bhebrew university\b", r"\bbar ilan\b",
    r"\bmonash\b", r"\buniversity of queensland\b", r"\buniversity of adelaide\b",
    r"\buniversity of new south wales\b", r"\bvrije universiteit\b", r"\buniversiteit leiden\b",
    r"\buniversiteit utrecht\b", r"\buniversiteit amsterdam\b", r"\buniversity of buenos aires\b",
    r"\buniversity of s£o paulo\b", r"\buniversity of cape town\b", r"\bnational chiao tung\b",
    r"\bnational tsing hua\b", r"\bnational taiwan\b", r"\buniversity of hong kong\b",
    r"\bhong kong university\b", r"\bchinese university of hong kong\b", r"\bcity university of hong kong\b",
    r"\buniversity of macau\b", r"\bseoul national\b", r"\bkaist\b", r"\bkorea university\b", r"\byonsei\b",
    r"\biisc\b", r"\biit bombay\b", r"\biit delhi\b", r"\biit madras\b", r"\bsoochow\b",
    r"\buniversity of science and technology of china\b", r"\buniversity of electronic science\b",
    r"\bxidian\b", r"\bbeihang\b", r"\bzhejiang\b", r"\bshanghai jiao\b", r"\bnanjing\b",
    r"\bwuhan\b", r"\bhuazhong\b", r"\bsun yat-sen\b", r"\bharbin institute\b", r"\btongji\b",
    r"\brenmin\b", r"\bbeijing institute\b", r"\bnational institute of informatics\b", r"\bsamsung\b",
    r"\bhuawei\b", r"\balibaba\b", r"\btencent\b", r"\bbaidu\b", r"\byandex\b",
    r"\bvodafone\b", r"\bdeutsche telekom\b", r"\bsony\b", r"\bntt\b", r"\bkddi\b",
    r"\bsoftbank\b", r"\brickitt\b", r"\bline corporation\b", r"\bnec corporation\b",
    r"\bfujitsu\b", r"\bhitachi\b", r"\bpanasonic\b", r"\bsharp\b", r"\btoshiba\b", r"\bcanon\b",
    r"\bolympus\b", r"\bkomatsu\b", r"\bdenso\b", r"\bmazda\b", r"\bhonda\b", r"\btoyota\b",
    r"\bnissan\b", r"\bsubaru\b", r"\bsuzuki\b", r"\bmitsubishi\b", r"\bsumitomo\b",
    r"\bmizuho\b", r"\bnomura\b", r"\bnintendo\b", r"\bcapcom\b", r"\bkonami\b", r"\bseg a\b",
    r"\bsquare enix\b", r"\bbandai\b", r"\bfrom software\b",
]

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

CCS_POSTER_PATTERN = re.compile(r"(^poster\b[\s:\-]?|\(poster\)\.?$)", re.IGNORECASE)
CCS_WORKSHOP_PATTERN = re.compile(
    r"\b("
    r"workshop|"
    r"wpes\s*'?\d{2}|"
    r"aisec\s*'?\d{2}|"
    r"ccsw\s*'?\d{2}|"
    r"mtd\s*'?\d{2}|"
    r"ashes\s*\d{4}|"
    r"cpsi?otsec\s*'?\d{2}|"
    r"consensusday\s*'?\d{2}|"
    r"plas\b|"
    r"defi\s*'?\d{2}|"
    r"healthsec\s*'?\d{2}|"
    r"aacd\s*'?\d{2}|"
    r"lamps\s*'?\d{2}|"
    r"ricss\s*'?\d{2}|"
    r"feast\s*'?\d{2}|"
    r"watch\s*'?\d{2}|"
    r"sats\s*'?\d{2}|"
    r"wahc\s*'?\d{2}|"
    r"scored\s*'?\d{2}|"
    r"haips\s*'?\d{2}|"
    r"sure\s*'?\d{2}|"
    r"artman\s*'?\d{2}|"
    r"checkmate\s*'?\d{2}|"
    r"free5gc\s*'?\d{2}"
    r")\b",
    re.IGNORECASE,
)
CCS_DEMO_PATTERN = re.compile(r"^demo\s*[:\-]", re.IGNORECASE)
CCS_TUTORIAL_PATTERN = re.compile(r"^tutorial\b", re.IGNORECASE)
CCS_DOCTORAL_PATTERN = re.compile(r"doctoral symposium", re.IGNORECASE)
CCS_COMPETITION_PATTERN = re.compile(r"course competition", re.IGNORECASE)
CCS_DISSERTATION_PATTERN = re.compile(r"dissertation research description", re.IGNORECASE)
CCS_PROGRAM_PATTERN = re.compile(r"young scholars development program", re.IGNORECASE)
CCS_NON_MAIN_TITLES_BY_YEAR: dict[int, set[str]] = {
    2020: {
        "Machine Learning and Security: The Good, The Bad, and The Ugly.",
    },
    2021: {
        "Pseudo-Randomness and the Crystal Ball.",
        "Towards Building a Responsible Data Economy.",
        "Are we done yet? Our Journey to Fight against Memory-safety Bugs.",
    },
    2022: {
        "Designing Hardware for Cryptography and Cryptography for Hardware.",
        "We Are the Experts, and We Are the Problem: The Security Advice Fiasco.",
        "Sustainability is a Security Problem.",
    },
    2024: {
        "Cryptography and Computer Security: A View From the Year 2100.",
        "Staving off the IoT Armageddon.",
        "Verifiable Security Policies for Distributed Systems.",
    },
    2025: {
        "Autonomous Vulnerability Analysis, Triaging, and Repair: A Historical Perspective.",
        "Mechanizing Privacy by Design.",
    },
}

NDSS_NON_MAIN_TITLES_BY_YEAR: dict[int, set[str]] = {
    2020: {
        'Overcoming the "Evil Twins" Attack: Lessons Learned from the Industrial Battlefield.',
    },
}

IEEE_SP_TITLE_OVERRIDES_BY_DOI: dict[str, str] = {
    "10.1109/SP40001.2021.00111": "A2L: Anonymous Atomic Locks for Scalability in Payment Channel Hubs",
    "10.1109/SP40001.2021.00100": "Doing good by fighting fraud: Ethical anti-fraudsystems for mobile payments",
    "10.1109/SP40001.2021.00088": "Merkle^2: A Low-Latency Transparency Log System",
    "10.1109/SP40001.2021.00067": "Proactive Threshold Wallets with Offline Devices",
    "10.1109/SP40001.2021.00031": "Electromagnetic Covert Channels Can Be Super Resilient",
    "10.1109/SP40001.2021.9796062": "Journey to the Center of the Cookie Ecosystem: Unraveling Actors' Roles and Relationships",
    "10.1109/SP46214.2022.9833665": "Analyzing Ground-Truth Data of Mobile Gambling Scam",
    "10.1109/SP46214.2022.9833639": "Attacks on Wireless Coexistence",
    "10.1109/SP46214.2022.9833647": "Back to the Drawing Board: A Critical Evaluation of Poisoning Attacks on Federated Learning",
    "10.1109/SP46214.2022.9833772": "Blacksmith: Compromising Target Row Refresh by Rowhammering in the Frequency Domain",
    "10.1109/SP46214.2022.9833655": "MatRiCT+: More Efficient Post-Quantum Private Blockchain Payments",
    "10.1109/SP46214.2022.9833564": "PCR-Auth: Solving Authentication Puzzle Challenges with Encoded Palm Contact Responses",
    "10.1109/SP46214.2022.9833702": "Private Nearest Neighbor Search with Sublinear Communication and Malicious Security",
    "10.1109/SP46214.2022.9833663": "SoK: The Dual Nature of Technology in Sexual Assault",
}

IEEE_SP_REASSIGNED_CONFERENCE_KEYS_BY_DOI: dict[str, str] = {
    "10.1109/SP40001.2021.9796062": "ieee_sp_2021",
}

IEEE_SP_REASSIGNED_PAPER_SUPPLEMENTS: dict[str, dict[str, Any]] = {
    "10.1109/SP40001.2021.9796062": {
        "paperId": "conf/sp/Sanchez-RolaDBV21",
        "title": "Journey to the Center of the Cookie Ecosystem: Unraveling Actors' Roles and Relationships",
        "authors": [
            "Iskander Sánchez-Rola",
            "Matteo Dell'Amico",
            "Davide Balzarotti",
            "Pierre-Antoine Vervier",
            "Leyla Bilge",
        ],
        "url": "https://doi.org/10.1109/SP40001.2021.9796062",
        "pages": "",
    },
}


def build_article_tag(config: ConferenceConfig, title: str) -> str:
    """构造带会议范围的稳定标签，用于论文匹配和导出。"""
    return f"{config.venue_tag}-{normalize_space(title)}"


@dataclass(frozen=True)
class AffiliationClassification:
    country: str
    source: str
    confidence: float
    reason: str


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

    if year != 2025:
        return ordered_entries

    # USENIX Security '25 program chairs report 214 new Cycle 1 accepts and 193 new Cycle 2
    # accepts, plus 32 carry-overs from the 2024 review process. The public Cycle 1 page
    # contains 245 titles while the technical-sessions page contains 438 PDF-backed papers.
    # Empirically, the technical-sessions entries not present on the Cycle 1 page are exactly
    # 193, matching the Cycle 2 accepted-paper count. We therefore treat the first 214 titles
    # listed on the Cycle 1 page as the review-cycle-new Cycle 1 set and exclude the remaining
    # tail entries from the 2025 review-cycle paper list.
    try:
        cycle1_html = fetch_text("https://www.usenix.org/conference/usenixsecurity25/cycle1-accepted-papers", timeout=30)
    except Exception:
        return ordered_entries
    cycle1_soup = BeautifulSoup(cycle1_html, "html.parser")
    cycle1_titles: list[str] = []
    seen_cycle1: set[str] = set()
    for anchor in cycle1_soup.select('a[href*="/conference/usenixsecurity25/presentation/"]'):
        title = normalize_space(anchor.get_text(" ", strip=True))
        if not title or title in seen_cycle1:
            continue
        seen_cycle1.add(title)
        cycle1_titles.append(title)

    if len(cycle1_titles) < 214:
        return ordered_entries

    cycle1_new_keys = {official_title_key(title) for title in cycle1_titles[:214]}
    cycle1_all_keys = {official_title_key(title) for title in cycle1_titles}
    tech_only_keys = {
        official_title_key(entry["title"])
        for entry in ordered_entries
        if official_title_key(entry["title"]) not in cycle1_all_keys
    }
    if len(tech_only_keys) != 193:
        return ordered_entries

    retained_keys = cycle1_new_keys | tech_only_keys
    filtered_entries = [entry for entry in ordered_entries if official_title_key(entry["title"]) in retained_keys]
    return filtered_entries if len(filtered_entries) == 407 else ordered_entries


def parse_author_names_from_official_affiliation_text(text: str) -> list[str]:
    authors: list[str] = []
    for match in re.finditer(r"([^,;()]+?)\s*\([^)]{2,}\)", text):
        name = clean_author_name(match.group(1))
        if name and name not in authors:
            authors.append(name)
    return authors


def parse_author_affiliations_from_parenthesized_text(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for match in re.finditer(r"([^,;()]+?)\s*\(([^)]+)\)", text):
        name = clean_author_name(match.group(1))
        inst = normalize_space(match.group(2))
        if not name or len(inst) <= 2 or inst.startswith("http"):
            continue
        rows.append({"name": name, "affiliations": [inst]})
    return rows


def parse_ccs_row_author_text(text: str) -> tuple[list[str], list[dict[str, Any]]]:
    normalized = normalize_space(text.replace("\xa0", " "))
    if not normalized:
        return [], []
    return (
        parse_author_names_from_official_affiliation_text(normalized),
        parse_author_affiliations_from_parenthesized_text(normalized),
    )


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


def clean_author_name(value: str) -> str:
    text = normalize_space(html.unescape(str(value)))
    text = re.sub(r"\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+\d{4}$", "", text)
    text = re.sub(r"\s*[\*\u2020\u2021\u00a7]+\s*$", "", text)
    text = re.sub(r"\s*\([^)]*\)$", lambda match: "" if AUTHOR_NOTE_PATTERN.search(match.group(0)) else match.group(0), text)
    text = normalize_space(text.strip(" ,;"))
    if text.casefold() in AUTHOR_NAME_PLACEHOLDERS:
        return ""
    return text


def classify_affiliation(
    affiliation: str,
    overrides: dict[str, AffiliationClassification] | None = None,
) -> AffiliationClassification:
    normalized = normalize_space(affiliation)
    if overrides and normalized.casefold() in overrides:
        return overrides[normalized.casefold()]
    parts = split_affiliation_parts(affiliation)
    if len(parts) > 1:
        results = [classify_single_affiliation(part, overrides) for part in parts]
        countries = {result.country for result in results if result.country != "Unknown"}
        if countries == {"China", "Hong Kong"}:
            lower = normalized.casefold()
            if "shenzhen" in lower:
                return AffiliationClassification("China", "rule", 0.95, "hong_kong_shenzhen_consensus")
            if "hong kong" in lower:
                return AffiliationClassification("Hong Kong", "rule", 0.95, "hong_kong_consensus")
        if len(countries) > 1:
            return AffiliationClassification(
                "Multiple",
                "rule",
                min((result.confidence for result in results if result.country != "Unknown"), default=0.7),
                "multiple_countries",
            )
        if len(countries) == 1:
            country = next(iter(countries))
            return AffiliationClassification(
                country,
                "rule",
                min((result.confidence for result in results if result.country != "Unknown"), default=0.7),
                "multi_affiliation_consensus",
            )
        return results[-1]
    return classify_single_affiliation(affiliation, overrides)

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


def split_affiliation_parts(affiliation: str) -> list[str]:
    normalized = normalize_space(affiliation)
    if ", and " in normalized:
        parts = [part.strip(" ,") for part in re.split(r",\s+and\s+", normalized) if part.strip(" ,")]
        if len(parts) > 1:
            return parts
    if ";" in normalized:
        return [part.strip() for part in normalized.split(";") if part.strip()]
    if "/" in normalized:
        return [part.strip() for part in normalized.split("/") if part.strip()]
    if " & " in normalized:
        parts = [part.strip() for part in normalized.split(" & ") if part.strip()]
        if len(parts) > 1:
            classified_countries = {
                classify_single_affiliation(part, overrides=None).country
                for part in parts
                if classify_single_affiliation(part, overrides=None).country != "Unknown"
            }
            if len(classified_countries) > 1:
                return parts
            if re.search(r"\b(University|Institute|Labs|Lab|Research|College|Technologies|Technology|Center|Centre|Group|School)\b.*&.*\b(University|Institute|Labs|Lab|Research|College|Technologies|Technology|Center|Centre|Group|School)\b", normalized):
                return parts
    if " and " in normalized:
        if re.search(
            r"\b(Science and Technology|Posts and Telecommunications|Economics and Technology|Research and Technology|Information and Communications Technology|Polytechnic Institute and State University|Parallel Computer Engineering and Technology|Mathematical Engineering and Advanced Computing)\b",
            normalized,
            re.IGNORECASE,
        ):
            return [normalized]
        parts = [part.strip() for part in normalized.split(" and ") if part.strip()]
        if len(parts) > 1:
            classified_countries = {
                classify_single_affiliation(part, overrides=None).country
                for part in parts
                if classify_single_affiliation(part, overrides=None).country != "Unknown"
            }
            if len(classified_countries) > 1:
                return parts
            if re.search(r"\b(University|Universität|Universitat|Institute|Labs|Lab|Research|College|Technologies|Technology|Center|Centre|Group|School)\b.*\band\b.*\b(University|Universität|Universitat|Institute|Labs|Lab|Research|College|Technologies|Technology|Center|Centre|Group|School)\b", normalized):
                return parts
    return [normalized]


def classify_single_affiliation(
    affiliation: str,
    overrides: dict[str, AffiliationClassification] | None = None,
) -> AffiliationClassification:
    return classify_with_patterns(
        affiliation,
        overrides=overrides,
        exact_aliases=US_EXACT_ALIASES,
        non_us_patterns=NON_US_KEYWORD_PATTERNS,
        us_patterns=US_KEYWORD_PATTERNS,
        classification_factory=AffiliationClassification,
    )


def load_institution_overrides(path: Path) -> dict[str, AffiliationClassification]:
    return load_override_rows(path, AffiliationClassification)


def load_author_name_aliases(path: Path) -> dict[str, set[str]]:
    if not path.exists():
        return {}
    aliases: dict[str, set[str]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            canonical = normalize_space(row.get("canonical_name", ""))
            alias = normalize_space(row.get("alias", ""))
            if not canonical or not alias:
                continue
            aliases.setdefault(canonical, set()).add(alias)
    return aliases


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


def load_author_affiliation_overrides(path: Path) -> dict[tuple[str, str, str, str, str], list[dict[str, str]]]:
    if not path.exists():
        return {}
    overrides: dict[tuple[str, str, str, str, str], list[dict[str, str]]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            conference = normalize_space(row.get("conference", ""))
            year = normalize_space(row.get("year", ""))
            article_tag = normalize_space(row.get("article_tag", ""))
            author_order = normalize_space(row.get("author_order", ""))
            author_name = normalize_space(row.get("name", ""))
            raw_inst = row.get("inst", "") or ""
            inst = normalize_space(raw_inst)
            country = normalize_space(row.get("country", ""))
            if not conference or not year or not article_tag or not author_order or not author_name or not inst:
                continue
            key = (conference, year, article_tag, author_order, author_name)
            overrides.setdefault(key, [])
            value = {"inst": raw_inst.strip("\n\r"), "country": country}
            if value not in overrides[key]:
                overrides[key].append(value)
    return overrides


def apply_author_affiliation_overrides(
    config: ConferenceConfig,
    papers: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    issues: list[dict[str, str]],
    overrides: dict[tuple[str, str, str, str, str], list[dict[str, str]]],
    institution_overrides: dict[str, AffiliationClassification] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    if not overrides:
        return rows, issues

    paper_key_to_override_rows: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    paper_id_by_key: dict[tuple[str, str, str], str] = {}
    title_by_key: dict[tuple[str, str, str], str] = {}

    for paper in papers:
        title = normalize_space(str(paper.get("title", "")))
        authors = [normalize_space(str(author)) for author in paper.get("authors", [])]
        article_tag = build_article_tag(config, title)
        paper_key = (
            normalize_space(config.conference),
            normalize_space(str(config.year)),
            normalize_space(article_tag),
        )
        override_rows: list[dict[str, Any]] = []
        complete = True
        for order, author in enumerate(authors):
            key = (
                paper_key[0],
                paper_key[1],
                paper_key[2],
                str(order),
                author,
            )
            override_insts = overrides.get(key, [])
            if not override_insts:
                complete = False
                break
            for override in override_insts:
                inst = override["inst"]
                forced_country = normalize_space(override.get("country", ""))
                if forced_country:
                    classification = AffiliationClassification(
                        country=forced_country,
                        source="override",
                        confidence=1.0,
                        reason="author_affiliation_override_country",
                    )
                else:
                    classification = classify_affiliation(inst, institution_overrides)
                override_rows.append(
                    {
                        "conference": config.conference,
                        "year": config.year,
                        "paper_id": paper.get("paperId", ""),
                        "title": title,
                        "name": author,
                        "article_tag": article_tag,
                        "author_order": order,
                        "inst": inst,
                        "country": classification.country,
                        "classification_source": "author_affiliation_override",
                        "classification_confidence": 1.0,
                        "classification_reason": "author_affiliation_override",
                    }
                )
        if complete and override_rows:
            paper_key_to_override_rows[paper_key] = override_rows
            paper_id_by_key[paper_key] = str(paper.get("paperId", ""))
            title_by_key[paper_key] = title

    if not paper_key_to_override_rows:
        return rows, issues

    overridden_paper_ids = set(paper_id_by_key.values())
    updated_rows = [row for row in rows if str(row.get("paper_id", "")) not in overridden_paper_ids]
    updated_issues = [issue for issue in issues if str(issue.get("paper_id", "")) not in overridden_paper_ids]
    for paper_key in sorted(paper_key_to_override_rows):
        updated_rows.extend(paper_key_to_override_rows[paper_key])
    return updated_rows, updated_issues


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
        clean = normalize_space(re.sub(r"<[^>]+>", " ", html.unescape(value)))
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


def safe_pdf_stem(paper: dict[str, Any]) -> str:
    paper_id = normalize_space(str(paper.get("paperId", ""))).replace("/", "_")
    if paper_id:
        return paper_id
    title = slug_text(str(paper.get("title", "")))
    return title or "paper"


def extract_pdf_links_from_html(base_url: str, html_text: str) -> list[str]:
    links: list[str] = []
    for href in re.findall(r'href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\']', html_text, re.IGNORECASE):
        absolute = urllib.parse.urljoin(base_url, html.unescape(href))
        if absolute not in links:
            links.append(absolute)
    return links


def extract_public_pdf_candidates(base_url: str, html_text: str) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []

    def add(url: str, strategy: str) -> None:
        absolute = urllib.parse.urljoin(base_url, html.unescape(url.strip()))
        if absolute and all(existing[0] != absolute for existing in candidates):
            candidates.append((absolute, strategy))

    for pattern in [
        r'<meta[^>]+name="citation_pdf_url"[^>]+content="([^"]+)"',
        r'<meta[^>]+property="citation_pdf_url"[^>]+content="([^"]+)"',
        r'<meta[^>]+name="wkhealth_pdf_url"[^>]+content="([^"]+)"',
    ]:
        for match in re.findall(pattern, html_text, re.IGNORECASE):
            add(match, "meta_pdf_url")

    for href in re.findall(r'href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\']', html_text, re.IGNORECASE):
        add(href, "href_pdf")

    for pattern in [
        r'pdfUrl["\']?\s*[:=]\s*["\']([^"\']+)',
        r'epdf["\']?\s*[:=]\s*["\']([^"\']+)',
        r'data-pdf-url=["\']([^"\']+)["\']',
    ]:
        for match in re.findall(pattern, html_text, re.IGNORECASE):
            add(match, "script_pdf_hint")
    return candidates


def resolve_pdf_url(config: ConferenceConfig, paper: dict[str, Any]) -> tuple[str, str]:
    url = normalize_space(str(paper.get("url", "")))
    if not url:
        return "", ""
    if url.lower().endswith(".pdf"):
        return url, "raw_pdf_url"
    try:
        page_html = fetch_text(url, timeout=20)
    except Exception:
        return "", ""
    candidates = extract_public_pdf_candidates(url, page_html)
    if not candidates:
        return "", ""
    if config.conference == "USENIX_SECURITY":
        for link, strategy in candidates:
            if "files/conference" in link or "/presentation/" in link or "usenixsecurity" in link:
                return link, strategy
    return candidates[0]


def download_pdf(url: str, output_path: Path, referer: str = "", timeout: int = 60) -> tuple[bool, str, int]:
    headers = dict(BROWSER_HEADERS)
    headers["Accept"] = "application/pdf,*/*;q=0.8"
    if referer:
        headers["Referer"] = referer
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        content = response.read()
        final_url = response.geturl()
    is_pdf = "pdf" in content_type.casefold() or final_url.lower().endswith(".pdf")
    if not is_pdf:
        return False, content_type, len(content)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(content)
    return True, content_type, len(content)


def download_pdfs_for_conference(
    config: ConferenceConfig,
    papers: list[dict[str, Any]],
    output_dir: Path,
    pdf_limit: int = 0,
) -> dict[str, Any]:
    pdf_dir = conference_pdf_dir(output_dir, config.key)
    report_rows: list[dict[str, Any]] = []
    downloaded = 0
    papers_seen = 0
    for index, paper in enumerate(papers):
        if pdf_limit > 0 and papers_seen >= pdf_limit:
            break
        papers_seen += 1
        paper_id = normalize_space(str(paper.get("paperId", "")))
        title = normalize_space(str(paper.get("title", "")))
        source_url = normalize_space(str(paper.get("url", "")))
        pdf_url, resolution_strategy = resolve_pdf_url(config, paper)
        row = {
            "conference": config.conference,
            "year": config.year,
            "paper_id": paper_id,
            "title": title,
            "source_url": source_url,
            "pdf_url": pdf_url,
            "resolution_strategy": resolution_strategy,
            "status": "pending",
            "content_type": "",
            "bytes": 0,
            "path": "",
            "error": "",
        }
        if not pdf_url:
            row["status"] = "no_pdf_url"
            report_rows.append(row)
            continue
        output_path = pdf_dir / f"{safe_pdf_stem(paper)}.pdf"
        try:
            ok, content_type, byte_count = download_pdf(pdf_url, output_path, referer=source_url)
            row["content_type"] = content_type
            row["bytes"] = byte_count
            if ok:
                row["status"] = "downloaded"
                row["path"] = str(output_path)
                downloaded += 1
            else:
                row["status"] = "non_pdf_response"
        except Exception as exc:
            row["status"] = "download_error"
            row["error"] = str(exc)
        report_rows.append(row)
    report_path = output_dir / "interim" / f"{config.key}_pdf_download_report.csv"
    write_csv(
        report_path,
        report_rows,
        ["conference", "year", "paper_id", "title", "source_url", "pdf_url", "resolution_strategy", "status", "content_type", "bytes", "path", "error"],
    )
    summary = {
        "conference": config.conference,
        "year": config.year,
        "papers_seen": papers_seen,
        "downloaded_pdfs": downloaded,
        "report_path": str(report_path),
        "pdf_dir": str(pdf_dir),
    }
    (output_dir / "interim" / f"{config.key}_pdf_download_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def is_ccs_main_conference_paper(config: ConferenceConfig, title: str) -> bool:
    return is_ccs_main_conference_paper_with_pages(config, title, "")


def page_span_from_string(pages: str) -> int | None:
    normalized_pages = normalize_space(pages)
    if not normalized_pages:
        return None
    if "-" in normalized_pages:
        start, end = normalized_pages.split("-", 1)
        try:
            return int(end) - int(start) + 1
        except Exception:
            return None
    try:
        int(normalized_pages)
    except Exception:
        return None
    return 1


def is_ccs_main_conference_paper_with_pages(
    config: ConferenceConfig,
    title: str,
    pages: str,
) -> bool:
    normalized_title = normalize_space(title)
    if not normalized_title:
        return False
    if CCS_POSTER_PATTERN.search(normalized_title):
        return False
    if CCS_WORKSHOP_PATTERN.search(normalized_title):
        return False
    if CCS_DEMO_PATTERN.search(normalized_title):
        return False
    if CCS_TUTORIAL_PATTERN.search(normalized_title):
        return False
    if CCS_DOCTORAL_PATTERN.search(normalized_title):
        return False
    if CCS_COMPETITION_PATTERN.search(normalized_title):
        return False
    if CCS_DISSERTATION_PATTERN.search(normalized_title):
        return False
    if CCS_PROGRAM_PATTERN.search(normalized_title):
        return False
    if normalized_title in CCS_NON_MAIN_TITLES_BY_YEAR.get(config.year, set()):
        return False
    span = page_span_from_string(pages)
    if span is not None and span <= 4:
        return False
    return True


def fetch_ccs_2020_2021_official_entries(year: int) -> list[dict[str, Any]]:
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
                }
            )
    return entries


def fetch_ccs_2022_2024_table_official_entries(year: int) -> list[dict[str, Any]]:
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
        author_text = normalize_space(cells[1].get_text(" ", strip=True))
        authors, official_affiliations = parse_ccs_row_author_text(author_text)
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


def fetch_ccs_2023_official_entries() -> list[dict[str, Any]]:
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


def fetch_ccs_2025_official_entries() -> list[dict[str, Any]]:
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
    if year in (2020, 2021):
        return fetch_ccs_2020_2021_official_entries(year)
    if year in (2022, 2024):
        return fetch_ccs_2022_2024_table_official_entries(year)
    if year == 2023:
        return fetch_ccs_2023_official_entries()
    if year == 2025:
        return fetch_ccs_2025_official_entries()
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
        url = f"https://www.ieee-security.org/TC/SP{year}/program-papers.html"
    else:
        url = f"https://sp{year}.ieee-security.org/accepted-papers.html"
    try:
        soup = BeautifulSoup(fetch_text(url, timeout=30), "html.parser")
    except Exception:
        return []
    entries: list[dict[str, Any]] = []
    for item in soup.select("div.list-group-item"):
        title_el = item.find("b")
        if not title_el:
            continue
        title = normalize_space(title_el.get_text(" ", strip=True))
        block_text = normalize_space(item.get_text(" ", strip=True))
        author_text = block_text.replace(title, "", 1).strip(" -")
        authors = parse_author_names_from_official_affiliation_text(author_text)
        official_affiliations = parse_ieee_official_author_affiliations(item)
        if title:
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


def dedupe_papers_by_identity(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for paper in papers:
        doi = extract_doi_from_url(normalize_space(str(paper.get("url", ""))))
        key = doi or official_title_key(str(paper.get("title", "")))
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(paper)
    return deduped


def apply_ieee_sp_title_and_year_overrides(config: ConferenceConfig, papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    adjusted: list[dict[str, Any]] = []
    for paper in papers:
        doi = extract_doi_from_url(normalize_space(str(paper.get("url", ""))))
        if doi:
            target_key = IEEE_SP_REASSIGNED_CONFERENCE_KEYS_BY_DOI.get(doi, config.key)
            if target_key != config.key:
                continue
            override_title = IEEE_SP_TITLE_OVERRIDES_BY_DOI.get(doi)
            if override_title:
                paper = dict(paper)
                paper["title"] = override_title
        adjusted.append(paper)
    if config.key == "ieee_sp_2021":
        existing_dois = {extract_doi_from_url(normalize_space(str(p.get("url", "")))) for p in adjusted}
        for doi, target_key in IEEE_SP_REASSIGNED_CONFERENCE_KEYS_BY_DOI.items():
            if target_key != config.key or doi in existing_dois:
                continue
            supplement = IEEE_SP_REASSIGNED_PAPER_SUPPLEMENTS.get(doi)
            if supplement:
                adjusted.append(dict(supplement))
            else:
                adjusted.append(
                    {
                        "paperId": f"official/{config.key}/{doi}",
                        "title": IEEE_SP_TITLE_OVERRIDES_BY_DOI.get(doi, ""),
                        "authors": [],
                        "url": f"https://doi.org/{doi}",
                        "pages": "",
                    }
                )
    return adjusted


def merge_official_paper_supplements(config: ConferenceConfig, papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    updated = [dict(paper) for paper in papers]

    if config.conference == "USENIX_SECURITY":
        try:
            official_entries = fetch_usenix_official_entries(config.year)
        except Exception:
            official_entries = []
        if official_entries:
            official_by_url = {
                normalize_space(str(entry.get("url", ""))): entry
                for entry in official_entries
                if normalize_space(str(entry.get("url", "")))
            }
            official_by_title = {
                official_title_key(str(entry.get("title", ""))): entry
                for entry in official_entries
                if official_title_key(str(entry.get("title", "")))
            }
            filtered: list[dict[str, Any]] = []
            for paper in updated:
                url_key = normalize_space(str(paper.get("url", "")))
                title_key = official_title_key(str(paper.get("title", "")))
                official_entry = official_by_url.get(url_key) or official_by_title.get(title_key)
                if not official_entry:
                    continue
                if official_entry.get("title"):
                    paper["title"] = official_entry["title"]
                if official_entry.get("url"):
                    paper["url"] = official_entry["url"]
                filtered.append(paper)
            updated = filtered

    if config.conference == "IEEE_S&P":
        updated = apply_ieee_sp_title_and_year_overrides(config, updated)

    if config.conference == "NDSS":
        excluded_titles = NDSS_NON_MAIN_TITLES_BY_YEAR.get(config.year, set())
        if excluded_titles:
            updated = [paper for paper in updated if normalize_space(str(paper.get("title", ""))) not in excluded_titles]
        official_entries = fetch_ndss_official_entries(config.year)
        existing_urls = {normalize_space(str(paper.get("url", ""))) for paper in updated}
        for entry in official_entries:
            if normalize_space(entry["url"]) not in existing_urls:
                entry = dict(entry)
                entry["paperId"] = f"official/{config.key}/{slug_text(entry['title'])}"
                updated.append(entry)

    if config.conference == "CCS":
        official_entries = fetch_ccs_official_entries(config.year)
        official_by_doi = {
            normalize_space(str(entry.get("doi", ""))): entry
            for entry in official_entries
            if normalize_space(str(entry.get("doi", "")))
        }
        official_by_title = {
            official_title_key(str(entry.get("title", ""))): entry
            for entry in official_entries
            if official_title_key(str(entry.get("title", "")))
        }
        for paper in updated:
            doi = extract_doi_from_url(normalize_space(str(paper.get("url", ""))))
            title_key = official_title_key(str(paper.get("title", "")))
            official_entry = official_by_doi.get(doi) or official_by_title.get(title_key)
            if not official_entry:
                continue
            if official_entry.get("title"):
                paper["title"] = official_entry["title"]
            if official_entry.get("authors"):
                paper["authors"] = official_entry["authors"]
        if config.key == "ccs_2025":
            filtered: list[dict[str, Any]] = []
            seen_title_keys: set[str] = set()
            seen_dois: set[str] = set()
            for paper in updated:
                doi = extract_doi_from_url(normalize_space(str(paper.get("url", ""))))
                title_key = official_title_key(str(paper.get("title", "")))
                official_entry = official_by_doi.get(doi) or official_by_title.get(title_key)
                if not official_entry:
                    continue
                seen_title_keys.add(title_key)
                if doi:
                    seen_dois.add(doi)
                filtered.append(paper)
            updated = filtered
            for title_key, entry in official_by_title.items():
                entry_doi = normalize_space(str(entry.get("doi", "")))
                if title_key in seen_title_keys or (entry_doi and entry_doi in seen_dois):
                    continue
                extra_entry = dict(entry)
                extra_entry["paperId"] = f"official/{config.key}/{slug_text(entry['title'])}"
                updated.append(extra_entry)

    return dedupe_papers_by_identity(updated)


def fetch_dblp_papers(config: ConferenceConfig) -> list[dict[str, Any]]:
    url = f"https://dblp.org/db/conf/{config.dblp_key}/{config.dblp_key}{config.year}.xml"
    request = urllib.request.Request(url, headers={"User-Agent": BROWSER_HEADERS["User-Agent"]})
    xml_data = ""
    last_error: Exception | None = None
    for timeout in (20, 30, 45):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                xml_data = response.read().decode("utf-8", errors="replace")
            break
        except Exception as exc:
            last_error = exc
    if not xml_data:
        print(f"DBLP fetch failed for {config.key}: {last_error}", file=sys.stderr)
        if config.conference == "CCS":
            return dedupe_papers_by_identity(fetch_ccs_official_entries(config.year))
        if config.conference == "NDSS":
            return dedupe_papers_by_identity(fetch_ndss_official_entries(config.year))
        if config.conference == "IEEE_S&P":
            return dedupe_papers_by_identity(fetch_ieee_sp_official_entries(config.year))
        return []

    root = ET.fromstring(xml_data)
    ccs_2025_official_by_doi = {}
    if config.key == "ccs_2025":
        ccs_2025_official_by_doi = {
            entry["doi"]: entry
            for entry in fetch_ccs_2025_official_entries()
            if entry.get("doi")
        }
    papers = []
    for article in root.findall(".//inproceedings") + root.findall(".//article"):
        title_el = article.find("title")
        title = normalize_space(title_el.text) if title_el is not None and title_el.text else ""
        ee = article.find("ee")
        url = ee.text.strip() if ee is not None and ee.text else ""
        doi = extract_doi_from_url(url)
        if not title:
            official_entry = ccs_2025_official_by_doi.get(doi, {})
            title = normalize_space(str(official_entry.get("title", "")))
            if not title:
                continue
        pages = normalize_space(article.findtext("pages", ""))
        if config.conference == "CCS" and not is_ccs_main_conference_paper_with_pages(config, title, pages):
            continue
        authors = []
        for author in article.findall(".//author"):
            if author.text:
                cleaned = clean_author_name(author.text)
                if cleaned:
                    authors.append(cleaned)
        if not authors and doi in ccs_2025_official_by_doi:
            authors = list(ccs_2025_official_by_doi[doi].get("authors", []))
        paper_id = article.get("key", "")
        papers.append({
            "paperId": paper_id,
            "title": title,
            "authors": authors,
            "url": url,
            "pages": pages,
        })
    return merge_official_paper_supplements(config, papers)


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


def unpaywall_email() -> str:
    for env_name in ("UNPAYWALL_EMAIL", "OPENALEX_MAILTO"):
        value = os.environ.get(env_name, "").strip()
        if value:
            return value
    return "test@example.com"


def fetch_unpaywall_by_doi(doi: str) -> dict[str, Any]:
    normalized_doi = normalize_space(doi)
    if not normalized_doi:
        return {}
    email = urllib.parse.quote(unpaywall_email(), safe="@")
    encoded_doi = urllib.parse.quote(normalized_doi, safe="")
    url = f"https://api.unpaywall.org/v2/{encoded_doi}?email={email}"
    try:
        payload = fetch_json_with_rate_limit(
            "unpaywall",
            url,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,*/*;q=0.8"},
            timeout=8,
            max_retries=1,
        )
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def fetch_semantic_scholar_paper(title: str, doi: str = "") -> dict[str, Any]:
    normalized_doi = normalize_space(doi)
    try:
        if normalized_doi:
            encoded_doi = urllib.parse.quote(normalized_doi, safe="")
            url = (
                f"https://api.semanticscholar.org/graph/v1/paper/DOI:{encoded_doi}"
                "?fields=title,externalIds,authors,year,venue,openAccessPdf"
            )
            payload = fetch_json_with_rate_limit(
                "semantic_scholar",
                url,
                headers=semantic_scholar_headers(),
                timeout=8,
                max_retries=1,
            )
            if isinstance(payload, dict) and payload:
                return payload
    except Exception:
        pass

    query = urllib.parse.quote_plus(title[:100])
    url = (
        "https://api.semanticscholar.org/graph/v1/paper/search"
        f"?query={query}&limit=1&fields=title,externalIds,authors,year,venue,openAccessPdf"
    )
    try:
        payload = fetch_json_with_rate_limit(
            "semantic_scholar",
            url,
            headers=semantic_scholar_headers(),
            timeout=8,
            max_retries=1,
        )
    except Exception:
        return {}
    data = payload.get("data", []) if isinstance(payload, dict) else []
    if not data:
        return {}
    first = data[0]
    if normalized_title_key(str(first.get("title", ""))) != normalized_title_key(title):
        return {}
    return first if isinstance(first, dict) else {}


def normalized_title_key(title: str) -> str:
    title = re.sub(r"<[^>]+>", " ", title)
    return normalize_space(title).casefold().rstrip(".")


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


def manifest_csv_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "conference": row.get("conference", ""),
        "year": row.get("year", ""),
        "paper_id": row.get("paper_id", ""),
        "title": row.get("title", ""),
        "doi": row.get("doi", ""),
        "url": row.get("url", ""),
        "status": row.get("status", ""),
        "source": row.get("source", ""),
        "pdf_url": row.get("pdf_url", ""),
        "pdf_path": row.get("pdf_path", ""),
    }


def resolve_pdf_manifest_fields(
    config: ConferenceConfig,
    paper: dict[str, Any],
) -> dict[str, Any]:
    pdf_url, resolution_strategy = resolve_pdf_url(config, paper)
    if pdf_url:
        return {
            "status": "open_pdf_found",
            "source": resolution_strategy or "landing_page",
            "pdf_url": pdf_url,
            "pdf_path": "",
        }
    return {
        "status": "no_open_pdf",
        "source": "",
        "pdf_url": "",
        "pdf_path": "",
    }


def build_manifest_row(
    config: ConferenceConfig,
    paper: dict[str, Any],
) -> dict[str, Any]:
    url = normalize_space(str(paper.get("url", "")))
    return {
        "conference": config.conference,
        "year": config.year,
        "paper_id": paper.get("paperId", ""),
        "title": normalize_space(str(paper.get("title", ""))),
        "doi": extract_doi_from_url(url),
        "url": url,
        "status": "",
        "source": "",
        "pdf_url": "",
        "pdf_path": "",
        "openalex": None,
        "unpaywall": None,
        "semantic_scholar": None,
    }


def enrich_manifest_row(
    config: ConferenceConfig,
    paper: dict[str, Any],
) -> dict[str, Any]:
    row = build_manifest_row(config, paper)
    row.update(resolve_pdf_manifest_fields(config, paper))
    doi = normalize_space(str(row.get("doi", "")))
    if doi:
        openalex_work = fetch_openalex_work_by_doi(doi)
        if openalex_work:
            row["openalex"] = openalex_work
            if row["status"] == "no_open_pdf":
                primary_location = openalex_work.get("primary_location") or {}
                pdf_url = normalize_space(str(primary_location.get("pdf_url", "")))
                if pdf_url:
                    row["status"] = "open_pdf_found"
                    row["source"] = "openalex"
                    row["pdf_url"] = pdf_url
        unpaywall = fetch_unpaywall_by_doi(doi)
        if unpaywall:
            row["unpaywall"] = unpaywall
            best_oa_location = unpaywall.get("best_oa_location") or {}
            pdf_url = normalize_space(str(best_oa_location.get("url_for_pdf", "")))
            if pdf_url and row["status"] == "no_open_pdf":
                row["status"] = "open_pdf_found"
                row["source"] = "unpaywall"
                row["pdf_url"] = pdf_url
    semantic_scholar = fetch_semantic_scholar_paper(row["title"], doi)
    if semantic_scholar:
        row["semantic_scholar"] = semantic_scholar
        if row["status"] == "no_open_pdf":
            open_access_pdf = semantic_scholar.get("openAccessPdf") or {}
            pdf_url = normalize_space(str(open_access_pdf.get("url", "")))
            if pdf_url:
                row["status"] = "open_pdf_found"
                row["source"] = "semantic_scholar"
                row["pdf_url"] = pdf_url
    return row


def build_conference_manifest_rows(
    config: ConferenceConfig,
    papers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """为每篇论文组装包含 PDF、元数据和机构状态的清单行。"""
    return [enrich_manifest_row(config, paper) for paper in papers]


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
    if cache_file.exists():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        if has_resolved_affiliations(cached) and cache_has_full_author_coverage(cached, authors, author_name_aliases):
            return cached
    official_cached = load_official_affiliations_for_paper(config, paper)
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


def expand_author_rows(
    config: ConferenceConfig,
    papers: list[dict[str, Any]],
    overrides: dict[str, AffiliationClassification] | None = None,
    cache_dir: Path | None = None,
    fetch_from_network: bool = False,
    author_name_aliases: dict[str, set[str]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    for paper in papers:
        title = normalize_space(paper.get("title", ""))
        authors = [normalize_space(author) for author in paper.get("authors", [])]
        paper_id = paper.get("paperId", "")
        article_tag = build_article_tag(config, title)
        author_affiliations = resolve_affiliations_for_paper(
            config,
            paper,
            cache_dir,
            fetch_from_network,
            author_name_aliases,
        ) if cache_dir else []

        if author_affiliations:
            aff_map, aff_name_pairs = build_affiliation_map(author_affiliations)
            matched_affiliations = match_author_affiliations(authors, aff_map, aff_name_pairs, author_name_aliases)
            original_match_flags = [bool(affs) for affs in matched_affiliations]
            fallback_match_flags = [False] * len(authors)
            shared_fill_flags = [False] * len(authors)

            if fetch_from_network and any(not affs for affs in matched_affiliations):
                openalex_affiliations = resolve_openalex_fallback(
                    paper.get("url", ""),
                    title,
                    authors,
                    config.year,
                )
                if openalex_affiliations:
                    fallback_map, fallback_name_pairs = build_affiliation_map(openalex_affiliations)
                    fallback_matches = match_author_affiliations(authors, fallback_map, fallback_name_pairs, author_name_aliases)
                    fallback_match_flags = [bool(affs) for affs in fallback_matches]
                    matched_affiliations = [
                        primary if primary else fallback
                        for primary, fallback in zip(matched_affiliations, fallback_matches)
                    ]

            if any(not affs for affs in matched_affiliations):
                before_shared_fill = [bool(affs) for affs in matched_affiliations]
                matched_affiliations = fill_shared_affiliation_gaps(matched_affiliations)
                shared_fill_flags = [
                    (not before) and bool(after)
                    for before, after in zip(before_shared_fill, matched_affiliations)
                ]

            matched_count = sum(1 for affs in matched_affiliations if affs)
            if matched_count > 0:
                unmatched_authors: list[str] = []
                for order, (author, affs) in enumerate(zip(authors, matched_affiliations)):
                    if not affs:
                        unmatched_authors.append(author)
                        rows.append({
                            "conference": config.conference,
                            "year": config.year,
                            "paper_id": paper_id,
                            "title": title,
                            "name": author,
                            "article_tag": article_tag,
                            "author_order": order,
                            "inst": "",
                            "country": "Unknown",
                            "classification_source": "author_affiliation_unmatched",
                            "classification_confidence": 0.0,
                            "classification_reason": "author_not_matched_in_source_affiliations",
                        })
                        continue
                    inst = "; ".join(affs)
                    classification = classify_affiliation(inst, overrides)
                    classification_source = classification.source
                    classification_confidence = classification.confidence
                    classification_reason = classification.reason
                    if shared_fill_flags[order]:
                        classification_source = "paper_shared_affiliation_backfill"
                        classification_confidence = min(classification.confidence, 0.7)
                        classification_reason = "paper_level_single_affiliation_consensus"
                    elif (not original_match_flags[order]) and fallback_match_flags[order]:
                        classification_source = "openalex_partial_gap_fill"
                        classification_confidence = min(classification.confidence, 0.8)
                        classification_reason = "openalex_partial_author_gap_fill"
                    rows.append({
                        "conference": config.conference,
                        "year": config.year,
                        "paper_id": paper_id,
                        "title": title,
                        "name": author,
                        "article_tag": article_tag,
                        "author_order": order,
                        "inst": inst,
                        "country": classification.country,
                        "classification_source": classification_source,
                        "classification_confidence": classification_confidence,
                        "classification_reason": classification_reason,
                    })
                if unmatched_authors:
                    issues.append({
                        "conference": config.conference,
                        "year": str(config.year),
                        "paper_id": paper_id,
                        "title": title,
                        "issue": "partial_author_affiliation_coverage",
                        "authors_count": str(len(authors)),
                        "affiliations_count": str(len(author_affiliations)),
                        "authors": " | ".join(unmatched_authors),
                        "affiliations": " | ".join(
                            f"{item.get('name', '').strip()}: {'; '.join(item.get('affiliations', []))}".strip(": ")
                            for item in author_affiliations
                        ),
                    })
                continue

            issues.append({
                "conference": config.conference,
                "year": str(config.year),
                "paper_id": paper_id,
                "title": title,
                "issue": "author_affiliation_match_failed",
                "authors_count": str(len(authors)),
                "affiliations_count": str(len(author_affiliations)),
                "authors": " | ".join(authors),
                "affiliations": " | ".join(
                    f"{item.get('name', '').strip()}: {'; '.join(item.get('affiliations', []))}".strip(": ")
                    for item in author_affiliations
                ),
            })
            continue

        issues.append({
            "conference": config.conference,
            "year": str(config.year),
            "paper_id": paper_id,
            "title": title,
            "issue": "no_affiliation_data",
            "authors_count": str(len(authors)),
            "affiliations_count": "0",
            "authors": " | ".join(authors),
            "affiliations": "",
        })
    return rows, issues


def filter_classified_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("country") and row["country"] != "Unknown"]


def count_country_resolution_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    single_country_rows = sum(1 for row in rows if row.get("country") not in {"", "Unknown", "Multiple"})
    multiple_country_rows = sum(1 for row in rows if row.get("country") == "Multiple")
    unresolved_country_rows = sum(1 for row in rows if row.get("country") in {"", "Unknown"})
    return {
        "single_country_resolved_rows": single_country_rows,
        "multiple_country_rows": multiple_country_rows,
        "unresolved_country_rows": unresolved_country_rows,
    }


def normalize_papers(config: ConferenceConfig, papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{
        "conference": config.conference,
        "year": config.year,
        "paper_id": paper.get("paperId", ""),
        "title": normalize_space(paper.get("title", "")),
        "article_tag": build_article_tag(config, paper.get("title", "")),
        "authors_count": len(paper.get("authors", [])),
        "url": paper.get("url", ""),
    } for paper in papers]


def build_affiliation_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["inst"], row["classification_reason"])
        candidates.setdefault(key, {
            "inst": row["inst"],
            "country": row["country"],
            "classification_source": row["classification_source"],
            "classification_confidence": row["classification_confidence"],
            "classification_reason": row["classification_reason"],
            "example_conference": row["conference"],
            "example_paper_id": row["paper_id"],
            "example_title": row["title"],
        })
    return sorted(candidates.values(), key=lambda item: (item["inst"], item["classification_reason"]))


def run_single_conference(
    config: ConferenceConfig,
    raw_json_path: Path,
    output_dir: Path,
    papers: list[dict[str, Any]] | None = None,
    fetch_affiliations: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    """执行单个安全会议年份的完整抽取流程。"""
    if papers is None:
        papers = json.loads(raw_json_path.read_text(encoding="utf-8"))
    overrides = load_institution_overrides(output_dir / "reference" / "institution_country_overrides.csv")
    author_name_aliases = load_author_name_aliases(
        output_dir / "reference" / "author_name_aliases.csv"
    )
    author_affiliation_overrides = load_author_affiliation_overrides(
        output_dir / "reference" / "author_affiliation_overrides.csv"
    )
    cache_dir = output_dir / "resolution" / "affiliation_cache"
    conference_output = conference_output_dir(output_dir, config.key)
    conference_interim = conference_interim_dir(output_dir, config.key)
    paper_rows = normalize_papers(config, papers)
    manifest_rows = build_conference_manifest_rows(config, papers)
    rows, issues = expand_author_rows(
        config,
        papers,
        overrides,
        cache_dir,
        fetch_affiliations,
        author_name_aliases,
    )
    rows, issues = apply_author_affiliation_overrides(
        config,
        papers,
        rows,
        issues,
        author_affiliation_overrides,
        overrides,
    )
    classified_rows = filter_classified_rows(rows)
    classified_rows_final = classified_rows
    country_counts = count_country_resolution_rows(rows)
    papers_with_author_rows = len({row["paper_id"] for row in rows if row.get("paper_id")})
    papers_without_affiliation_data = sum(1 for issue in issues if issue.get("issue") == "no_affiliation_data")
    partial_affiliation_coverage = sum(1 for issue in issues if issue.get("issue") == "partial_author_affiliation_coverage")
    author_affiliation_match_failed = sum(1 for issue in issues if issue.get("issue") == "author_affiliation_match_failed")

    write_csv(conference_interim / "author_affiliations_expanded.csv", rows,
              ["conference", "year", "paper_id", "title", "name", "article_tag",
               "author_order", "inst", "country", "classification_source",
               "classification_confidence", "classification_reason"])
    write_csv(conference_interim / "affiliation_resolution_queue.csv", issues,
              ["conference", "year", "paper_id", "title", "issue",
               "authors_count", "affiliations_count", "authors", "affiliations"])
    write_csv(conference_output / "author_affiliations.csv", classified_rows,
              ["name", "year", "article_tag", "author_order", "inst", "country"])
    write_csv(conference_output / "author_affiliations_audit.csv", classified_rows_final,
              ["conference", "year", "paper_id", "title", "name", "article_tag",
               "author_order", "inst", "country", "classification_source",
               "classification_confidence", "classification_reason"])
    write_workbook(conference_output / "author_affiliations.xlsx", classified_rows_final, ["name", "year", "article_tag", "author_order", "inst", "country"])
    write_csv(conference_interim / "institution_classification_candidates.csv", build_affiliation_candidates(rows),
              ["inst", "country", "classification_source", "classification_confidence",
               "classification_reason", "example_conference", "example_paper_id", "example_title"])
    write_csv(
        conference_interim / "open_pdf_manifest.csv",
        [manifest_csv_row(row) for row in manifest_rows],
        ["conference", "year", "paper_id", "title", "doi", "url", "status", "source", "pdf_url", "pdf_path"],
    )
    (conference_interim / "open_pdf_manifest.json").write_text(
        json.dumps(manifest_rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report = {
        "conference": config.conference,
        "year": config.year,
        "raw_json": str(raw_json_path),
        "papers_count": len(papers),
        "papers_with_author_rows": papers_with_author_rows,
        "papers_without_affiliation_data": papers_without_affiliation_data,
        "papers_with_partial_affiliation_coverage": partial_affiliation_coverage,
        "papers_with_author_affiliation_match_failed": author_affiliation_match_failed,
        "expanded_author_rows": len(rows),
        "classified_author_rows": len(classified_rows),
        "resolved_country_rows": len(classified_rows),
        **country_counts,
        "no_affiliation_issues": len(issues),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (conference_output / "validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return report, paper_rows, rows, issues, manifest_rows


def run_all_pipelines(
    output_dir: Path,
    conference_keys: list[str] | None = None,
    fetch_affiliations: bool = False,
    download_pdfs: bool = False,
    pdf_limit: int = 0,
    start: int = 0,
    limit: int = 0,
) -> dict[str, Any]:
    """对选定安全会议批量执行抽取，并汇总结果。"""
    selected_keys = conference_keys or list(CONFERENCES.keys())
    summary_output = summary_output_dir(output_dir, "top4_security")
    summary_interim = summary_interim_dir(output_dir, "top4_security")
    reports = []
    all_papers = []
    all_rows = []
    all_issues = []
    all_manifest_rows = []
    pdf_reports = []

    for key in selected_keys:
        config = CONFERENCES[key]
        raw_json_path = conference_raw_dir(output_dir, config.key) / "papers.json"
        if not raw_json_path.exists():
            print(f"Skipping {config.key}: no raw JSON at {raw_json_path}", file=sys.stderr)
            continue
        papers = json.loads(raw_json_path.read_text(encoding="utf-8"))
        if start > 0 or limit > 0:
            stop = start + limit if limit > 0 else None
            papers = papers[start:stop]
        if download_pdfs:
            pdf_reports.append(download_pdfs_for_conference(config, papers, output_dir, pdf_limit=pdf_limit))
        report, paper_rows, rows, issues, manifest_rows = run_single_conference(
            config,
            raw_json_path,
            output_dir,
            papers=papers,
            fetch_affiliations=fetch_affiliations,
        )
        reports.append(report)
        all_papers.extend(paper_rows)
        all_rows.extend(rows)
        all_issues.extend(issues)
        all_manifest_rows.extend(manifest_rows)

    all_classified_rows = filter_classified_rows(all_rows)
    all_classified_rows_final = all_classified_rows
    country_counts = count_country_resolution_rows(all_rows)
    candidates = build_affiliation_candidates(all_rows)

    write_csv(summary_interim / "papers_normalized.csv", all_papers,
              ["conference", "year", "paper_id", "title", "article_tag", "authors_count", "url"])
    write_csv(summary_interim / "author_affiliations_expanded.csv", all_rows,
              ["conference", "year", "paper_id", "title", "name", "article_tag",
               "author_order", "inst", "country", "classification_source",
               "classification_confidence", "classification_reason"])
    write_csv(summary_interim / "institution_classification_candidates.csv", candidates,
              ["inst", "country", "classification_source", "classification_confidence",
               "classification_reason", "example_conference", "example_paper_id", "example_title"])
    write_csv(summary_interim / "affiliation_resolution_queue.csv", all_issues,
              ["conference", "year", "paper_id", "title", "issue",
               "authors_count", "affiliations_count", "authors", "affiliations"])
    manifests_dir = output_dir / "manifests"
    write_csv(
        manifests_dir / "open_pdf_manifest.csv",
        [manifest_csv_row(row) for row in all_manifest_rows],
        ["conference", "year", "paper_id", "title", "doi", "url", "status", "source", "pdf_url", "pdf_path"],
    )
    (manifests_dir / "open_pdf_manifest.json").write_text(
        json.dumps(all_manifest_rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_csv(summary_output / "四大安全顶会_作者机构国家.csv", all_classified_rows,
              ["name", "year", "article_tag", "author_order", "inst", "country"])
    write_csv(summary_output / "四大安全顶会_作者机构国家_audit.csv", all_classified_rows_final,
              ["conference", "year", "paper_id", "title", "name", "article_tag",
               "author_order", "inst", "country", "classification_source",
               "classification_confidence", "classification_reason"])
    write_workbook(summary_output / "四大安全顶会_作者机构国家.xlsx", all_classified_rows_final, ["name", "year", "article_tag", "author_order", "inst", "country"])
    combined = {
        "reports": reports,
        "papers_count": sum(report["papers_count"] for report in reports),
        "papers_with_author_rows": len({row["paper_id"] for row in all_rows if row.get("paper_id")}),
        "papers_without_affiliation_data": sum(1 for issue in all_issues if issue.get("issue") == "no_affiliation_data"),
        "papers_with_partial_affiliation_coverage": sum(1 for issue in all_issues if issue.get("issue") == "partial_author_affiliation_coverage"),
        "papers_with_author_affiliation_match_failed": sum(1 for issue in all_issues if issue.get("issue") == "author_affiliation_match_failed"),
        "expanded_author_rows": len(all_rows),
        "classified_author_rows": len(all_classified_rows),
        "resolved_country_rows": len(all_classified_rows),
        **country_counts,
        "no_affiliation_issues": len(all_issues),
        "pdf_download_reports": pdf_reports,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (summary_output / "validation_report.json").write_text(
        json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return combined


def fetch_dblp_and_save(config: ConferenceConfig, output_dir: Path) -> None:
    papers = fetch_dblp_papers(config)
    output_path = conference_raw_dir(output_dir, config.key) / "papers.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not papers and output_path.exists():
        try:
            existing = json.loads(output_path.read_text(encoding="utf-8"))
        except Exception:
            existing = []
        if existing:
            print(f"Keeping existing papers for {config.key}: fetch returned 0 but {len(existing)} cached rows exist", file=sys.stderr)
            return
    output_path.write_text(json.dumps(papers, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Fetched {len(papers)} papers for {config.key}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """解析命令行参数并启动安全会议抽取后端。"""
    parser = argparse.ArgumentParser(description="Security conference affiliation and country extraction pipeline")
    parser.add_argument("--conference", nargs="*", default=["all"], help="Conference keys or 'all'")
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    parser.add_argument("--fetch", action="store_true", help="Fetch papers from DBLP")
    parser.add_argument("--fetch-affiliations", action="store_true", help="Fetch affiliations from conference websites")
    parser.add_argument("--download-pdfs", action="store_true", help="Download PDFs when paper pages expose PDF links")
    parser.add_argument("--pdf-limit", type=int, default=0, help="Limit PDF downloads per conference; 0 means no limit")
    parser.add_argument("--start", type=int, default=0, help="Start index for per-conference batching")
    parser.add_argument("--limit", type=int, default=0, help="Limit papers per conference for batching; 0 means no limit")
    parser.add_argument("--list-conferences", action="store_true")
    args = parser.parse_args(argv)

    if args.list_conferences:
        for key, config in CONFERENCES.items():
            print(f"  {key}: {config.conference} {config.year}")
        return 0

    if "all" in args.conference:
        keys = list(CONFERENCES.keys())
    else:
        keys = args.conference

    if args.fetch:
        for key in keys:
            config = CONFERENCES[key]
            fetch_dblp_and_save(config, args.output_dir)

    report = run_all_pipelines(
        args.output_dir,
        keys,
        args.fetch_affiliations,
        args.download_pdfs,
        args.pdf_limit,
        args.start,
        args.limit,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
