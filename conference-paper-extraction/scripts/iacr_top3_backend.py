from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import csv

from backend_common import conference_interim_dir, conference_output_dir, conference_pdf_dir, conference_raw_dir, summary_interim_dir, summary_output_dir, write_csv, write_jsonl, write_workbook
from api_runtime import fetch_json_with_rate_limit
from classification_common import classify_with_patterns, load_override_rows, normalize_space
from iacr_resolution import run_resolution
from security_real_backend import fetch_openalex_affiliations, fetch_openalex_affiliations_by_doi

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
except Exception:
    webdriver = None
    By = None


@dataclass(frozen=True)
class ConferenceConfig:
    key: str
    conference: str
    year: int
    url: str


@dataclass(frozen=True)
class AffiliationClassification:
    country: str
    source: str
    confidence: float
    reason: str


ASIACRYPT_2020 = ConferenceConfig(
    key="asiacrypt_2020",
    conference="ASIACRYPT",
    year=2020,
    url="https://asiacrypt.iacr.org/2020/json/papers.json",
)
ASIACRYPT_2021 = ConferenceConfig(
    key="asiacrypt_2021",
    conference="ASIACRYPT",
    year=2021,
    url="https://asiacrypt.iacr.org/2021/json/papers.json",
)
ASIACRYPT_2022 = ConferenceConfig(
    key="asiacrypt_2022",
    conference="ASIACRYPT",
    year=2022,
    url="https://asiacrypt.iacr.org/2022/json/papers.json",
)
ASIACRYPT_2023 = ConferenceConfig(
    key="asiacrypt_2023",
    conference="ASIACRYPT",
    year=2023,
    url="https://asiacrypt.iacr.org/2023/json/papers.json",
)
ASIACRYPT_2024 = ConferenceConfig(
    key="asiacrypt_2024",
    conference="ASIACRYPT",
    year=2024,
    url="https://asiacrypt.iacr.org/2024/json/papers.json",
)
ASIACRYPT_2025 = ConferenceConfig(
    key="asiacrypt_2025",
    conference="ASIACRYPT",
    year=2025,
    url="https://asiacrypt.iacr.org/2025/json/papers.json",
)
CRYPTO_2020 = ConferenceConfig(
    key="crypto_2020",
    conference="CRYPTO",
    year=2020,
    url="https://crypto.iacr.org/2020/json/papers.json",
)
CRYPTO_2021 = ConferenceConfig(
    key="crypto_2021",
    conference="CRYPTO",
    year=2021,
    url="https://crypto.iacr.org/2021/json/papers.json",
)
CRYPTO_2022 = ConferenceConfig(
    key="crypto_2022",
    conference="CRYPTO",
    year=2022,
    url="https://crypto.iacr.org/2022/json/papers.json",
)
CRYPTO_2023 = ConferenceConfig(
    key="crypto_2023",
    conference="CRYPTO",
    year=2023,
    url="https://crypto.iacr.org/2023/json/papers.json",
)
CRYPTO_2024 = ConferenceConfig(
    key="crypto_2024",
    conference="CRYPTO",
    year=2024,
    url="https://crypto.iacr.org/2024/json/papers.json",
)
CRYPTO_2025 = ConferenceConfig(
    key="crypto_2025",
    conference="CRYPTO",
    year=2025,
    url="https://crypto.iacr.org/2025/json/papers.json",
)
EUROCRYPT_2020 = ConferenceConfig(
    key="eurocrypt_2020",
    conference="EUROCRYPT",
    year=2020,
    url="https://eurocrypt.iacr.org/2020/json/papers.json",
)
EUROCRYPT_2021 = ConferenceConfig(
    key="eurocrypt_2021",
    conference="EUROCRYPT",
    year=2021,
    url="https://eurocrypt.iacr.org/2021/json/papers.json",
)
EUROCRYPT_2022 = ConferenceConfig(
    key="eurocrypt_2022",
    conference="EUROCRYPT",
    year=2022,
    url="https://eurocrypt.iacr.org/2022/json/papers.json",
)
EUROCRYPT_2023 = ConferenceConfig(
    key="eurocrypt_2023",
    conference="EUROCRYPT",
    year=2023,
    url="https://eurocrypt.iacr.org/2023/json/papers.json",
)
EUROCRYPT_2024 = ConferenceConfig(
    key="eurocrypt_2024",
    conference="EUROCRYPT",
    year=2024,
    url="https://eurocrypt.iacr.org/2024/json/papers.json",
)
EUROCRYPT_2025 = ConferenceConfig(
    key="eurocrypt_2025",
    conference="EUROCRYPT",
    year=2025,
    url="https://eurocrypt.iacr.org/2025/json/papers.json",
)

CONFERENCE_CONFIGS = {
    config.key: config
    for config in [
        ASIACRYPT_2020,
        ASIACRYPT_2021,
        ASIACRYPT_2022,
        ASIACRYPT_2023,
        ASIACRYPT_2024,
        ASIACRYPT_2025,
        CRYPTO_2020,
        CRYPTO_2021,
        CRYPTO_2022,
        CRYPTO_2023,
        CRYPTO_2024,
        CRYPTO_2025,
        EUROCRYPT_2020,
        EUROCRYPT_2021,
        EUROCRYPT_2022,
        EUROCRYPT_2023,
        EUROCRYPT_2024,
        EUROCRYPT_2025,
    ]
}

US_EXACT_ALIASES = {
    "mit",
    "nist",
    "sri",
    "uc san diego",
    "uc berkeley",
    "uc irvine",
    "uc davis",
    "uc santa barbara",
    "uc santa cruz",
    "uc los angeles",
    "ucla",
    "ut austin",
    "uiuc",
    "umd",
    "nyu",
    "yale",
    "duke",
    "cmu",
}

US_KEYWORD_PATTERNS = [
    r"\bmassachusetts institute of technology\b",
    r"\bcarnegie mellon university\b",
    r"\bstanford university\b",
    r"\bprinceton university\b",
    r"\bcornell university\b",
    r"\bcornell tech\b",
    r"\bbrown university\b",
    r"\bduke university\b",
    r"\byale university\b",
    r"\byale\b",
    r"\bcolumbia university\b",
    r"\bnew york university\b",
    r"\bnyu\b",
    r"\bboston university\b",
    r"\bjohns hopkins university\b",
    r"\bjhu\b",
    r"\buniversity of california\b",
    r"\buniversity of washington\b",
    r"\buniversity of wisconsin\b",
    r"\buw-madison\b",
    r"\buniversity of maryland\b",
    r"\bumd\b",
    r"\buniversity of pennsylvania\b",
    r"\buniversity of michigan\b",
    r"\buniversity of texas\b",
    r"\but austin\b",
    r"\buniversity of illinois\b",
    r"\buiuc\b",
    r"\burbana-champaign\b",
    r"\bgeorgia tech\b",
    r"\bgeorgia institute of technology\b",
    r"\bcity college of new york\b",
    r"\bcuny\b",
    r"\bnorth carolina state university\b",
    r"\bnortheastern university\b",
    r"\bpurdue university\b",
    r"\brice university\b",
    r"\bstony brook university\b",
    r"\btexas a&m university\b",
    r"\bunc chapel hill\b",
    r"\buniversity of connecticut\b",
    r"\bwashington state university\b",
    r"\bgoogle\b",
    r"\bmeta\b",
    r"\bmicrosoft\b",
    r"\bibm research\b",
    r"\bintel\b",
    r"\bcloudflare\b",
    r"\bvisa research\b",
    r"\bfujitsu research of america\b",
    r"\baptos labs\b",
    r"\bbain capital crypto\b",
    r"\bcategory labs\b",
    r"\boffchain labs\b",
    r"\bproof trading\b",
    r"\bntt research\b",
    r"\bnational institute of standards and technology\b",
]

NON_US_KEYWORD_PATTERNS = [
    r"\beth zurich\b",
    r"\beth zürich\b",
    r"\busi, lugano\b",
    r"\buniversity of luxembourg\b",
    r"\bruhr university bochum\b",
    r"\bkings? college london\b",
    r"\broyal holloway\b",
    r"\buniversity of auckland\b",
    r"\btechnical university of denmark\b",
    r"\bibm research europe\b",
    r"\borange\b",
]


def build_article_tag(config: ConferenceConfig, paper: dict[str, Any]) -> str:
    """为单条 IACR 论文记录构造稳定的会议范围标签。"""
    title = normalize_space(str(paper.get("title", "")))
    return f"{config.conference}-{title}"


AUTHOR_NOISE_PATTERN = re.compile(
    r"\b(corresponding author|author to whom correspondence|equal contribution|shared first author|present address)\b",
    re.IGNORECASE,
)
AUTHOR_INSTITUTION_PATTERN = re.compile(
    r"\b(university|institute|college|school|department|laborator(?:y|ies)|center|centre|faculty|academy|hospital|research|group|team|corporation|corp\.?|inc\.?|ltd\.?|gmbh|company)\b",
    re.IGNORECASE,
)


def split_top_level(value: str, separators: tuple[str, ...]) -> list[str]:
    text = str(value)
    parts: list[str] = []
    buffer: list[str] = []
    depth = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
        if depth == 0:
            matched = next((separator for separator in separators if text.startswith(separator, index)), "")
            if matched:
                part = normalize_space("".join(buffer))
                if part:
                    parts.append(part)
                buffer = []
                index += len(matched)
                continue
        buffer.append(char)
        index += 1
    tail = normalize_space("".join(buffer))
    if tail:
        parts.append(tail)
    return parts


def clean_author_candidate(value: str) -> str:
    text = normalize_space(str(value))
    text = re.sub(r"\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+\d{4}$", "", text)
    text = re.sub(r"\s*[\*\u2020\u2021\u00a7]+\s*$", "", text)
    text = re.sub(r"\s*\([^)]*\)$", lambda match: "" if AUTHOR_NOISE_PATTERN.search(match.group(0)) else match.group(0), text)
    return normalize_space(text.strip(" ,;"))


def looks_like_author_name(value: str) -> bool:
    text = clean_author_candidate(value)
    if not text or "@" in text or AUTHOR_NOISE_PATTERN.search(text):
        return False
    if any(char.isdigit() for char in text):
        return False
    if "(" in text or ")" in text:
        return False
    compact = re.sub(r"[,\-'. ]+", " ", text)
    parts = [part for part in compact.split() if part]
    if len(parts) < 2 or len(parts) > 6:
        return False
    if AUTHOR_INSTITUTION_PATTERN.search(text):
        return False
    if not any(part[0].isalpha() and part[0].isupper() for part in parts):
        return False
    return True


def looks_like_inline_author_affiliation_entry(value: str) -> bool:
    match = re.fullmatch(r"(.+?)\s*\((.+)\)", normalize_space(value))
    if not match:
        return False
    return looks_like_author_name(match.group(1))


def split_iacr_people_entries(value: str) -> list[str]:
    text = normalize_space(value)
    if not text:
        return []
    entries = split_top_level(text, (";",))
    if len(entries) > 1:
        return entries
    comma_entries = split_top_level(text, (",",))
    if len(comma_entries) > 1 and all(
        looks_like_author_name(entry) or looks_like_inline_author_affiliation_entry(entry)
        for entry in comma_entries
    ):
        return comma_entries
    and_entries = split_top_level(text, (" and ",))
    if len(and_entries) > 1 and all(looks_like_author_name(entry) for entry in and_entries):
        return and_entries
    return [text]


def parse_iacr_people_field(value: Any) -> list[str]:
    if isinstance(value, list):
        people: list[str] = []
        for item in value:
            people.extend(parse_iacr_people_field(item))
        return people
    if isinstance(value, str):
        people: list[str] = []
        for item in split_iacr_people_entries(value):
            cleaned = clean_author_candidate(item)
            if cleaned:
                people.append(cleaned)
        return people
    return []


def parse_iacr_affiliations_field(value: Any) -> list[str]:
    if isinstance(value, list):
        return [normalize_space(str(item)) for item in value if normalize_space(str(item))]
    if isinstance(value, str):
        return [normalize_space(item) for item in split_top_level(value, (";",)) if normalize_space(item)]
    return []


def dedupe_preserving_order_casefold(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_space(value)
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped


def extract_iacr_authors(paper: dict[str, Any]) -> list[str]:
    """从异构的 IACR JSON 字段中提取规范化作者名。"""
    authors = parse_iacr_people_field(paper.get("authors", []))
    if authors:
        return authors
    return parse_iacr_people_field(paper.get("author", []))


def extract_iacr_affiliations(paper: dict[str, Any]) -> list[str]:
    """从异构的 IACR JSON 字段中提取机构字符串。"""
    affiliations = parse_iacr_affiliations_field(paper.get("affiliations", []))
    if affiliations:
        return dedupe_preserving_order_casefold(affiliations)
    return dedupe_preserving_order_casefold(parse_iacr_affiliations_field(paper.get("institution", [])))


def parse_inline_author_affiliation_pairs(value: Any) -> tuple[list[str], list[str]]:
    entries = parse_iacr_people_field(value) if isinstance(value, list) else split_iacr_people_entries(str(value))
    authors: list[str] = []
    affiliations: list[str] = []
    for entry in entries:
        match = re.fullmatch(r"(.+?)\s*\((.+)\)", entry)
        if not match:
            return [], []
        author = clean_author_candidate(match.group(1))
        affiliation = normalize_space(match.group(2))
        if not author or not affiliation or not looks_like_author_name(author):
            return [], []
        authors.append(author)
        affiliations.append(affiliation)
    return authors, affiliations


def extract_iacr_paper_id(paper: dict[str, Any], fallback_index: int) -> str:
    paper_id = normalize_space(str(paper.get("paperId", "")))
    if paper_id:
        return paper_id
    legacy_id = normalize_space(str(paper.get("id", "")))
    if legacy_id:
        return legacy_id
    return f"legacy_{fallback_index}"


def extract_iacr_author_affiliation_lists(paper: dict[str, Any]) -> tuple[list[str], list[str]]:
    """使用当前最可靠的 IACR 字段返回对齐后的作者与机构列表。"""
    authors = extract_iacr_authors(paper)
    affiliations = extract_iacr_affiliations(paper)
    inline_authors, inline_affiliations = parse_inline_author_affiliation_pairs(paper.get("author", []))
    if authors and affiliations and len(authors) == len(affiliations):
        return authors, affiliations
    if inline_authors and inline_affiliations:
        return inline_authors, inline_affiliations
    return authors, affiliations


def classify_affiliation(
    affiliation: str,
    overrides: dict[str, AffiliationClassification] | None = None,
) -> AffiliationClassification:
    parts = split_affiliation_parts(affiliation, overrides)
    if len(parts) > 1:
        results = [classify_affiliation(part, overrides) for part in parts]
        countries = {result.country for result in results if result.country != "Unknown"}
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
    return classify_with_patterns(
        affiliation,
        overrides=overrides,
        exact_aliases=US_EXACT_ALIASES,
        non_us_patterns=NON_US_KEYWORD_PATTERNS,
        us_patterns=US_KEYWORD_PATTERNS,
        classification_factory=AffiliationClassification,
    )


ADDRESS_ONLY_FRAGMENT_PATTERN = re.compile(
    r"^(?:[A-Z][a-z]+(?:[- ][A-Z][a-z]+)*|the [A-Z][a-z]+|[A-Z][a-z]+(?:, [A-Z][a-z]+)*)$"
)
INSTITUTION_HINT_PATTERN = re.compile(
    r"\b(university|institute|college|school|laborator(?:y|ies)|center|centre|academy|department|faculty|research|group|lab|company|inc\.?|ltd\.?|gmbh|corp\.?)\b",
    re.IGNORECASE,
)


def should_keep_semicolon_affiliation_together(normalized: str) -> bool:
    parts = [part.strip() for part in normalized.split(";") if part.strip()]
    if len(parts) < 3:
        return False
    last_country = classify_affiliation(parts[-1]).country
    if last_country == "Unknown":
        return False
    middle_address_only = all(
        not INSTITUTION_HINT_PATTERN.search(part) and ADDRESS_ONLY_FRAGMENT_PATTERN.fullmatch(part)
        for part in parts[1:-1]
    )
    first_is_compact_label = len(parts[0].split()) <= 6
    return middle_address_only and first_is_compact_label


def split_affiliation_parts(
    affiliation: str,
    overrides: dict[str, AffiliationClassification] | None = None,
) -> list[str]:
    normalized = normalize_space(affiliation)
    if re.search(r"\bendress\s*&\s*hauser\b", normalized, re.IGNORECASE):
        return [normalized]
    if ", and " in normalized:
        parts = [part.strip(" ,") for part in re.split(r",\s+and\s+", normalized) if part.strip(" ,")]
        if len(parts) > 1:
            return parts
    if ", " in normalized and overrides:
        parts = [part.strip(" ,") for part in normalized.split(",") if part.strip(" ,")]
        if len(parts) > 1 and all(part.casefold() in overrides for part in parts):
            return parts
    if ";" in normalized:
        if should_keep_semicolon_affiliation_together(normalized):
            return [normalized]
        return [part.strip() for part in normalized.split(";") if part.strip()]
    if "/" in normalized:
        return [part.strip() for part in normalized.split("/") if part.strip()]
    if " & " in normalized:
        parts = [part.strip() for part in normalized.split(" & ") if part.strip()]
        if len(parts) > 1:
            return parts
    if " and " in normalized:
        if re.search(
            r"\b(Science and Technology|Posts and Telecommunications|Economics and Technology|Research and Technology|Information and Communications Technology|Polytechnic Institute and State University|Academy of Mathematics and System Science|Academy of Mathematics and Systems Science|Beijing Institute of Mathematical Sciences and Application|Beijing Institute of Mathematical Sciences and Applications|Computer Science and Artificial Intelligence|Security and Privacy|Technology and Economics|Agriculture and Technology|Computer Science and Control|Network Sciences and Cyberspace|Physical and Mathematical Sciences|National and Kapodistrian University)\b",
            normalized,
            re.IGNORECASE,
        ):
            return [normalized]
        parts = [part.strip() for part in normalized.split(" and ") if part.strip()]
        if len(parts) > 1:
            return parts
    return [normalized]


def classify_affiliation_parts(
    affiliation: str,
    overrides: dict[str, AffiliationClassification] | None = None,
) -> list[tuple[str, AffiliationClassification]]:
    """对拆分后的各机构片段分别分类，并在有用时保留多片段证据。"""
    normalized = normalize_space(affiliation)
    if overrides and normalized.casefold() in overrides:
        return [(normalized, overrides[normalized.casefold()])]
    parts = split_affiliation_parts(affiliation, overrides)
    results: list[tuple[str, AffiliationClassification]] = []
    seen: set[tuple[str, str]] = set()
    has_resolved_part = False
    for part in parts:
        classification = classify_affiliation(part, overrides)
        key = (part, classification.country)
        if key in seen:
            continue
        seen.add(key)
        results.append((part, classification))
        if classification.country and classification.country != "Unknown":
            has_resolved_part = True
        if part == "NTT Research":
            us_key = (part, "United States")
            if us_key not in seen:
                seen.add(us_key)
                results.append(
                    (
                        part,
                        AffiliationClassification(
                            country="United States",
                            source="rule",
                            confidence=0.95,
                            reason="reference_dual_participation_us",
                        ),
                    )
                )
                has_resolved_part = True
        if part == "NIST Associate":
            us_key = (part, "United States")
            if us_key not in seen:
                seen.add(us_key)
                results.append(
                    (
                        part,
                        AffiliationClassification(
                            country="United States",
                            source="rule",
                            confidence=0.95,
                            reason="reference_dual_participation_us",
                        ),
                    )
                )
                has_resolved_part = True
    if len(parts) > 1 and not has_resolved_part:
        fallback_classification = classify_affiliation(normalized, overrides)
        fallback_key = (normalized, fallback_classification.country)
        if fallback_key not in seen:
            results = [(normalized, fallback_classification)]
    return results


def dedupe_affiliation_classifications(
    classifications: list[tuple[str, AffiliationClassification]],
) -> list[tuple[str, AffiliationClassification]]:
    unique_affiliations: list[tuple[str, AffiliationClassification]] = []
    seen_affiliations: set[tuple[str, str]] = set()
    for affiliation, classification in classifications:
        key = (affiliation, classification.country)
        if key in seen_affiliations:
            continue
        seen_affiliations.add(key)
        unique_affiliations.append((affiliation, classification))
    return unique_affiliations


def build_openalex_mismatch_rows(
    config: ConferenceConfig,
    paper_id: str,
    title: str,
    article_tag: str,
    authors: list[str],
    overrides: dict[str, AffiliationClassification] | None = None,
) -> list[dict[str, Any]]:
    author_affiliations = fetch_openalex_affiliations(title, authors, config.year)
    if len(author_affiliations) != len(authors):
        return []

    aff_map = {
        normalize_space(item["name"]).casefold(): [normalize_space(str(value)) for value in item.get("affiliations", []) if normalize_space(str(value))]
        for item in author_affiliations
    }
    rows: list[dict[str, Any]] = []
    for order, author in enumerate(authors):
        affiliations = aff_map.get(normalize_space(author).casefold(), [])
        if not affiliations:
            return []
        joined_affiliation = "; ".join(dict.fromkeys(affiliations))
        if not joined_affiliation:
            return []
        for resolved_affiliation, classification in classify_affiliation_parts(joined_affiliation, overrides):
            rows.append(
                {
                    "conference": config.conference,
                    "year": config.year,
                    "paper_id": paper_id,
                    "title": title,
                    "name": author,
                    "article_tag": article_tag,
                    "author_order": order,
                    "inst": resolved_affiliation,
                    "country": classification.country,
                    "classification_source": "openalex_mismatch_resolution",
                    "classification_confidence": classification.confidence,
                    "classification_reason": classification.reason,
                }
            )
    return rows


def normalize_person_name_for_match(value: str) -> list[str]:
    text = normalize_space(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^A-Za-z0-9 ]+", " ", text)
    return [part.casefold() for part in text.split() if part]


def names_match_for_crossref(left: str, right: str) -> bool:
    left_parts = normalize_person_name_for_match(left)
    right_parts = normalize_person_name_for_match(right)
    if not left_parts or not right_parts:
        return False
    return left_parts[-1] == right_parts[-1] and left_parts[0][0] == right_parts[0][0]


def fetch_crossref_doi_for_title(title: str, authors: list[str]) -> str:
    url = f"https://api.crossref.org/works?rows=5&query.title={urllib.parse.quote(title)}"
    try:
        payload = fetch_json_with_rate_limit(
            "crossref",
            url,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,*/*;q=0.8"},
            timeout=30,
        )
    except Exception:
        return ""

    best_doi = ""
    best_overlap = 0
    for item in payload.get("message", {}).get("items", []):
        candidate_title = normalize_space(str((item.get("title") or [""])[0]))
        doi = normalize_space(str(item.get("DOI", "")))
        if not candidate_title or not doi:
            continue
        overlap = 0
        for author in item.get("author", []):
            candidate_name = normalize_space(" ".join([author.get("given", ""), author.get("family", "")]).strip())
            if candidate_name and any(names_match_for_crossref(candidate_name, name) for name in authors):
                overlap += 1
        if overlap > best_overlap:
            best_overlap = overlap
            best_doi = doi
    threshold = max(1, len(authors) - 1)
    return best_doi if best_overlap >= threshold else ""


def build_crossref_openalex_mismatch_rows(
    config: ConferenceConfig,
    paper_id: str,
    title: str,
    article_tag: str,
    authors: list[str],
    overrides: dict[str, AffiliationClassification] | None = None,
) -> list[dict[str, Any]]:
    doi = fetch_crossref_doi_for_title(title, authors)
    if not doi:
        return []
    author_affiliations = fetch_openalex_affiliations_by_doi(doi, authors, config.year)
    if len(author_affiliations) != len(authors):
        return []

    aff_map = {
        normalize_space(item["name"]).casefold(): [normalize_space(str(value)) for value in item.get("affiliations", []) if normalize_space(str(value))]
        for item in author_affiliations
    }
    rows: list[dict[str, Any]] = []
    for order, author in enumerate(authors):
        affiliations = aff_map.get(normalize_space(author).casefold(), [])
        if not affiliations:
            return []
        joined_affiliation = "; ".join(dict.fromkeys(affiliations))
        if not joined_affiliation:
            return []
        for resolved_affiliation, classification in classify_affiliation_parts(joined_affiliation, overrides):
            rows.append(
                {
                    "conference": config.conference,
                    "year": config.year,
                    "paper_id": paper_id,
                    "title": title,
                    "name": author,
                    "article_tag": article_tag,
                    "author_order": order,
                    "inst": resolved_affiliation,
                    "country": classification.country,
                    "classification_source": "crossref_openalex_mismatch_resolution",
                    "classification_confidence": classification.confidence,
                    "classification_reason": classification.reason,
                }
            )
    return rows


def expand_author_rows(
    config: ConferenceConfig,
    papers: list[dict[str, Any]],
    overrides: dict[str, AffiliationClassification] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """将论文级作者机构证据展开为行级审计记录。"""
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []

    for index, paper in enumerate(papers):
        authors, affiliations = extract_iacr_author_affiliation_lists(paper)
        paper_id = extract_iacr_paper_id(paper, index)
        title = normalize_space(str(paper.get("title", "")))
        article_tag = build_article_tag(config, paper)

        if len(authors) != len(affiliations):
            # Conservative fallback for IACR mismatch rows:
            # only keep cases that are still author-level plausible.
            # - single author + multiple affiliations: preserve all affiliations
            # - multiple authors + single affiliation: assign shared affiliation to all authors
            # - multiple authors + fewer shared affiliations: assign the resolved shared
            #   bundle to every author when the page clearly only exposes paper-level
            #   affiliations
            fallback_classifications = [
                (affiliation, classify_affiliation_parts(affiliation, overrides))
                for affiliation in affiliations
                if affiliation
            ]
            resolved_affiliations = [
                (resolved_affiliation, classification)
                for _affiliation, parts in fallback_classifications
                for resolved_affiliation, classification in parts
                if classification.country and classification.country != "Unknown"
            ]
            fallback_affiliations = dedupe_affiliation_classifications(
                [
                    (resolved_affiliation, classification)
                    for _affiliation, parts in fallback_classifications
                    for resolved_affiliation, classification in parts
                ]
            )
            fallback_mode = ""
            if len(authors) == 1:
                fallback_mode = "single_author_multi_affiliation"
            elif len(affiliations) == 1:
                fallback_mode = "shared_single_affiliation"
            handled_conservatively = False

            if resolved_affiliations and fallback_mode:
                classification_source = f"mismatch_fallback_{fallback_mode}"
                if fallback_mode == "single_author_multi_affiliation":
                    for affiliation, classification in resolved_affiliations:
                        rows.append(
                            {
                                "conference": config.conference,
                                "year": config.year,
                                "paper_id": paper_id,
                                "title": title,
                                "name": authors[0],
                                "article_tag": article_tag,
                                "author_order": 0,
                                "inst": affiliation,
                                "country": classification.country,
                                "classification_source": classification_source,
                                "classification_confidence": classification.confidence,
                                "classification_reason": classification.reason,
                            }
                        )
                    handled_conservatively = True
                else:
                    shared_countries = {
                        classification.country
                        for _affiliation, classification in fallback_affiliations
                        if classification.country and classification.country != "Unknown"
                    }
                    shared_country = (
                        next(iter(shared_countries))
                        if len(shared_countries) == 1
                        else "Multiple"
                        if len(shared_countries) > 1
                        else "Unknown"
                    )
                    joined_shared_affiliation = "; ".join(
                        dict.fromkeys(affiliation for affiliation, _classification in fallback_affiliations)
                    )
                    min_confidence = min(
                        (
                            classification.confidence
                            for _affiliation, classification in fallback_affiliations
                        ),
                        default=0.0,
                    )
                    classification_reason = (
                        "shared_single_affiliation_same_country"
                        if len(shared_countries) == 1
                        else "shared_single_affiliation_mixed_country"
                        if len(shared_countries) > 1
                        else "shared_single_affiliation_unresolved_country"
                    )
                    for order, author in enumerate(authors):
                        rows.append(
                            {
                                "conference": config.conference,
                                "year": config.year,
                                "paper_id": paper_id,
                                "title": title,
                                "name": author,
                                "article_tag": article_tag,
                                "author_order": order,
                                "inst": joined_shared_affiliation,
                                "country": shared_country,
                                "classification_source": classification_source,
                                "classification_confidence": min_confidence,
                                "classification_reason": classification_reason,
                            }
                        )
                    handled_conservatively = True
            if not handled_conservatively and len(authors) > len(affiliations) >= 1 and fallback_affiliations:
                resolved_countries = {
                    classification.country
                    for _affiliation, classification in fallback_affiliations
                    if classification.country and classification.country != "Unknown"
                }
                shared_country = (
                    next(iter(resolved_countries))
                    if len(resolved_countries) == 1
                    else "Multiple"
                    if len(resolved_countries) > 1
                    else "Unknown"
                )
                joined_affiliation = "; ".join(
                    dict.fromkeys(affiliation for affiliation, _classification in fallback_affiliations)
                )
                min_confidence = min(
                    (
                        classification.confidence
                        for _affiliation, classification in fallback_affiliations
                    ),
                    default=0.0,
                )
                for order, author in enumerate(authors):
                    rows.append(
                        {
                            "conference": config.conference,
                            "year": config.year,
                            "paper_id": paper_id,
                            "title": title,
                            "name": author,
                            "article_tag": article_tag,
                            "author_order": order,
                            "inst": joined_affiliation,
                            "country": shared_country,
                            "classification_source": (
                                "mismatch_fallback_shared_multi_affiliation_bundle"
                                if resolved_countries
                                else "mismatch_fallback_shared_multi_affiliation_bundle_unresolved"
                            ),
                            "classification_confidence": min_confidence,
                            "classification_reason": (
                                "shared_multi_affiliation_same_country"
                                if len(resolved_countries) == 1
                                else "shared_multi_affiliation_mixed_country"
                                if len(resolved_countries) > 1
                                else "shared_multi_affiliation_unresolved_country"
                            ),
                        }
                    )
                handled_conservatively = True
            if handled_conservatively:
                continue

            openalex_rows = build_openalex_mismatch_rows(
                config,
                paper_id,
                title,
                article_tag,
                authors,
                overrides,
            )
            if openalex_rows:
                rows.extend(openalex_rows)
                continue
            crossref_openalex_rows = build_crossref_openalex_mismatch_rows(
                config,
                paper_id,
                title,
                article_tag,
                authors,
                overrides,
            )
            if crossref_openalex_rows:
                rows.extend(crossref_openalex_rows)
                continue
            if not handled_conservatively:
                issues.append(
                    {
                        "conference": config.conference,
                        "year": str(config.year),
                        "paper_id": paper_id,
                        "title": title,
                        "issue": "author_affiliation_count_mismatch",
                        "authors_count": str(len(authors)),
                        "affiliations_count": str(len(affiliations)),
                        "authors": " | ".join(authors),
                        "affiliations": " | ".join(affiliations),
                    }
                )
            continue

        for order, (author, affiliation) in enumerate(zip(authors, affiliations)):
            for resolved_affiliation, classification in classify_affiliation_parts(affiliation, overrides):
                rows.append(
                    {
                        "conference": config.conference,
                        "year": config.year,
                        "paper_id": paper_id,
                        "title": title,
                        "name": author,
                        "article_tag": article_tag,
                        "author_order": order,
                        "inst": resolved_affiliation,
                        "country": classification.country,
                        "classification_source": classification.source,
                        "classification_confidence": classification.confidence,
                        "classification_reason": classification.reason,
                    }
                )

    return rows, issues


def filter_classified_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    included_unknown_institutions = {
        "independent researcher",
    }
    return [
        row
        for row in rows
        if (
            row.get("country")
            and row["country"] != "Unknown"
        )
        or normalize_space(str(row.get("inst", ""))).casefold() in included_unknown_institutions
    ]


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
    """将原始 IACR JSON 论文转换为下游共用的论文结构。"""
    return [
        {
            "conference": config.conference,
            "year": config.year,
            "paper_id": extract_iacr_paper_id(paper, index),
            "title": normalize_space(str(paper.get("title", ""))),
            "article_tag": build_article_tag(config, paper),
            "authors_count": len(extract_iacr_author_affiliation_lists(paper)[0]),
            "affiliations_count": len(extract_iacr_author_affiliation_lists(paper)[1]),
        }
        for index, paper in enumerate(papers)
    ]


def build_affiliation_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从展开后的记录中筛出仍需消歧支持的机构候选。"""
    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["inst"], row["classification_reason"])
        candidates.setdefault(
            key,
            {
                "inst": row["inst"],
                "country": row["country"],
                "classification_source": row["classification_source"],
                "classification_confidence": row["classification_confidence"],
                "classification_reason": row["classification_reason"],
                "example_conference": row["conference"],
                "example_paper_id": row["paper_id"],
                "example_title": row["title"],
            },
        )
    return sorted(candidates.values(), key=lambda item: (item["inst"], item["classification_reason"]))


def load_institution_overrides(path: Path) -> dict[str, AffiliationClassification]:
    return load_override_rows(path, AffiliationClassification)


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
    rows: list[dict[str, Any]],
    overrides: dict[tuple[str, str, str, str, str], list[dict[str, str]]],
    institution_overrides: dict[str, AffiliationClassification] | None,
) -> list[dict[str, Any]]:
    if not overrides:
        return rows
    overridden_papers = {
        (conference, year, article_tag)
        for conference, year, article_tag, _author_order, _author_name in overrides
    }
    overridden_author_slots = {
        (conference, year, article_tag, author_order)
        for conference, year, article_tag, author_order, _author_name in overrides
    }
    updated: list[dict[str, Any]] = []
    replaced_keys: set[tuple[str, str, str, str, str]] = set()
    for row in rows:
        key = (
            normalize_space(str(row.get("conference", ""))),
            normalize_space(str(row.get("year", ""))),
            normalize_space(str(row.get("article_tag", ""))),
            normalize_space(str(row.get("author_order", ""))),
            normalize_space(str(row.get("name", ""))),
        )
        paper_key = key[:3]
        override_insts = overrides.get(key)
        if not override_insts:
            if key[:4] in overridden_author_slots:
                continue
            updated.append(row)
            continue
        if key in replaced_keys:
            continue
        replaced_keys.add(key)
        for override in override_insts:
            inst = override["inst"]
            forced_country = override.get("country", "")
            if forced_country:
                classification = AffiliationClassification(
                    country=forced_country,
                    source="override",
                    confidence=1.0,
                    reason="author_affiliation_override_country",
                )
            else:
                classification = classify_affiliation(inst, institution_overrides)
            updated.append(
                {
                    **row,
                    "inst": inst,
                    "country": classification.country,
                    "classification_source": "author_affiliation_override",
                    "classification_confidence": 1.0,
                    "classification_reason": "author_affiliation_override",
                }
            )
    return updated


def build_llm_resolution_rows(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for candidate in candidates:
        if candidate["classification_source"] != "unresolved":
            continue
        rows.append(
            {
                "inst": candidate["inst"],
                "country": candidate.get("country", "Unknown"),
                "normalized_institution": candidate["inst"],
                "reason": "Conservative unresolved classification. Requires manual review before inclusion.",
                "confidence": 0.0,
                "needs_manual_review": True,
                "example_conference": candidate["example_conference"],
                "example_paper_id": candidate["example_paper_id"],
                "example_title": candidate["example_title"],
            }
        )
    return rows


def load_papers(raw_json_path: Path) -> list[dict[str, Any]]:
    data = json.loads(raw_json_path.read_text(encoding="utf-8"))
    papers = data.get("acceptedPapers")
    if not isinstance(papers, list):
        raise ValueError(f"{raw_json_path} does not contain acceptedPapers[]")
    return papers


def fetch_json(url: str, output_path: Path) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
            "Referer": url.rsplit("/", 2)[0] + "/acceptedpapers.php",
        },
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                content = response.read()
                status = getattr(response, "status", 200)
            break
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt == 2:
                raise
            time.sleep(2.0 * (attempt + 1))
    else:
        raise RuntimeError(f"Failed to fetch {url}: {last_error}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(content)
    return {
        "url": url,
        "status": status,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "path": str(output_path),
    }


def slug_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalize_space(value).casefold()).strip("-")


def safe_pdf_stem(paper: dict[str, Any]) -> str:
    paper_id = normalize_space(str(paper.get("paperId", ""))).replace("/", "_")
    if paper_id:
        return paper_id
    title = slug_text(str(paper.get("title", "")))
    return title or "paper"


def extract_pdf_url_from_paper(paper: dict[str, Any]) -> str:
    candidates = [
        paper.get("pdf"),
        paper.get("pdf_url"),
        paper.get("pdfUrl"),
        paper.get("url"),
        paper.get("ee"),
    ]
    for candidate in candidates:
        value = normalize_space(str(candidate or ""))
        if value.lower().endswith(".pdf"):
            return value
    return ""


def normalized_title_key(title: str) -> str:
    return normalize_space(title).casefold().rstrip(".")


def fetch_dblp_search_hits(title: str) -> list[dict[str, Any]]:
    query = urllib.parse.quote(title)
    url = f"https://dblp.org/search/publ/api?q={query}&format=json&h=5"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,*/*;q=0.8"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    hits = payload.get("result", {}).get("hits", {}).get("hit", [])
    if isinstance(hits, dict):
        return [hits]
    return hits if isinstance(hits, list) else []


def candidate_pdf_url_from_dblp_hit(
    hit: dict[str, Any],
    title: str,
    year: int,
) -> tuple[str, str, str]:
    info = hit.get("info", {})
    hit_title = normalize_space(str(info.get("title", "")))
    if normalized_title_key(hit_title) != normalized_title_key(title):
        return "", "", ""
    hit_year = normalize_space(str(info.get("year", "")))
    if hit_year and hit_year != str(year):
        return "", "", ""
    ee = normalize_space(str(info.get("ee", "")))
    if not ee:
        return "", "", ""
    if "eprint.iacr.org" in ee:
        return "", "", ""
    if ee.lower().endswith(".pdf"):
        return ee, ee, "dblp_direct_pdf"
    return "", "", ""


def fetch_arxiv_search_hits(title: str) -> list[dict[str, str]]:
    query = urllib.parse.quote(title)
    url = f"http://export.arxiv.org/api/query?search_query=all:%22{query}%22&start=0&max_results=5"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/atom+xml,*/*;q=0.8"})
    with urllib.request.urlopen(request, timeout=45) as response:
        payload = response.read().decode("utf-8", errors="replace")
    root = ET.fromstring(payload)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    hits: list[dict[str, str]] = []
    for entry in root.findall("atom:entry", ns):
        entry_title = normalize_space(entry.findtext("atom:title", default="", namespaces=ns))
        entry_id = normalize_space(entry.findtext("atom:id", default="", namespaces=ns))
        pdf_url = ""
        for link in entry.findall("atom:link", ns):
            title_attr = normalize_space(str(link.attrib.get("title", "")))
            href = normalize_space(str(link.attrib.get("href", "")))
            if title_attr.casefold() == "pdf" and href:
                pdf_url = href if href.lower().endswith(".pdf") else f"{href}.pdf"
                break
        if entry_title:
            hits.append({"title": entry_title, "id": entry_id, "pdf_url": pdf_url})
    return hits


def candidate_pdf_url_from_arxiv_hit(hit: dict[str, str], title: str) -> tuple[str, str, str]:
    hit_title = normalize_space(hit.get("title", ""))
    if normalized_title_key(hit_title) != normalized_title_key(title):
        return "", "", ""
    pdf_url = normalize_space(hit.get("pdf_url", ""))
    source_url = normalize_space(hit.get("id", ""))
    if pdf_url:
        return pdf_url, source_url or pdf_url, "arxiv_exact"
    return "", "", ""


def fetch_openreview_search_hits(title: str) -> list[dict[str, str]]:
    query = urllib.parse.quote(title)
    url = f"https://api2.openreview.net/notes/search?query={query}&limit=5"
    payload = fetch_json_with_rate_limit(
        "openreview",
        url,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,*/*;q=0.8"},
        timeout=45,
    )
    notes = payload.get("notes", [])
    hits: list[dict[str, str]] = []
    for note in notes if isinstance(notes, list) else []:
        content = note.get("content", {}) if isinstance(note, dict) else {}
        title_value = content.get("title", "")
        if isinstance(title_value, dict):
            title_value = title_value.get("value", "")
        note_id = normalize_space(str(note.get("id", "")))
        hits.append({"title": normalize_space(str(title_value)), "id": note_id})
    return hits


def candidate_pdf_url_from_openreview_hit(hit: dict[str, str], title: str) -> tuple[str, str, str]:
    hit_title = normalize_space(hit.get("title", ""))
    if normalized_title_key(hit_title) != normalized_title_key(title):
        return "", "", ""
    note_id = normalize_space(hit.get("id", ""))
    if note_id:
        return f"https://openreview.net/pdf?id={note_id}", f"https://openreview.net/forum?id={note_id}", "openreview_exact"
    return "", "", ""


def candidate_pdf_url_from_public_url(url: str) -> tuple[str, str]:
    clean = normalize_space(url)
    lower = clean.casefold()
    if not clean:
        return "", ""
    if lower.endswith(".pdf"):
        return clean, "webdriver_direct_pdf"
    if "arxiv.org/abs/" in lower:
        return clean.replace("/abs/", "/pdf/") + ".pdf", "webdriver_arxiv_search"
    if "openreview.net/forum?id=" in lower:
        note_id = clean.split("id=", 1)[1]
        return f"https://openreview.net/pdf?id={note_id}", "webdriver_openreview_search"
    return "", ""


def search_public_pdf_candidates_with_webdriver(driver: Any, title: str) -> list[tuple[str, str, str]]:
    if driver is None or By is None:
        return []
    query = urllib.parse.quote(f'"{title}" site:arxiv.org OR site:openreview.net OR filetype:pdf -site:eprint.iacr.org -site:link.springer.com')
    search_url = f"https://duckduckgo.com/?q={query}"
    driver.get(search_url)
    candidates: list[tuple[str, str, str]] = []
    for element in driver.find_elements(By.CSS_SELECTOR, "a[href]"):
        href = normalize_space(str(element.get_attribute("href") or ""))
        if not href:
            continue
        if "eprint.iacr.org" in href or "link.springer.com" in href:
            continue
        if not any(host in href for host in ["arxiv.org", "openreview.net", ".pdf"]):
            continue
        pdf_url, strategy = candidate_pdf_url_from_public_url(href)
        if pdf_url and all(existing[0] != pdf_url for existing in candidates):
            candidates.append((pdf_url, href, strategy))
    return candidates


def create_safari_webdriver() -> Any | None:
    if webdriver is None:
        return None
    try:
        return webdriver.Safari()
    except Exception:
        return None


def resolve_iacr_pdf_candidate(
    config: ConferenceConfig,
    paper: dict[str, Any],
    cache_dir: Path,
    driver: Any | None = None,
) -> tuple[str, str, str]:
    """从多个公开来源中为单篇论文定位可用的 PDF 候选。"""
    direct_pdf = extract_pdf_url_from_paper(paper)
    if direct_pdf:
        return direct_pdf, direct_pdf, "raw_pdf_url"

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_key = safe_pdf_stem(paper)
    cache_path = cache_dir / f"{cache_key}_dblp_search.json"
    if cache_path.exists():
        hits = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        try:
            hits = fetch_dblp_search_hits(normalize_space(str(paper.get("title", ""))))
        except Exception:
            hits = []
        cache_path.write_text(json.dumps(hits, ensure_ascii=False, indent=2), encoding="utf-8")

    title = normalize_space(str(paper.get("title", "")))
    for hit in hits:
        pdf_url, source_url, strategy = candidate_pdf_url_from_dblp_hit(hit, title, config.year)
        if pdf_url:
            return pdf_url, source_url, strategy

    arxiv_cache_path = cache_dir / f"{cache_key}_arxiv_search.json"
    if arxiv_cache_path.exists():
        arxiv_hits = json.loads(arxiv_cache_path.read_text(encoding="utf-8"))
    else:
        try:
            arxiv_hits = fetch_arxiv_search_hits(title)
        except Exception:
            arxiv_hits = []
        arxiv_cache_path.write_text(json.dumps(arxiv_hits, ensure_ascii=False, indent=2), encoding="utf-8")
    for hit in arxiv_hits:
        pdf_url, source_url, strategy = candidate_pdf_url_from_arxiv_hit(hit, title)
        if pdf_url:
            return pdf_url, source_url, strategy

    openreview_cache_path = cache_dir / f"{cache_key}_openreview_search.json"
    if openreview_cache_path.exists():
        openreview_hits = json.loads(openreview_cache_path.read_text(encoding="utf-8"))
    else:
        try:
            openreview_hits = fetch_openreview_search_hits(title)
        except Exception:
            openreview_hits = []
        openreview_cache_path.write_text(json.dumps(openreview_hits, ensure_ascii=False, indent=2), encoding="utf-8")
    for hit in openreview_hits:
        pdf_url, source_url, strategy = candidate_pdf_url_from_openreview_hit(hit, title)
        if pdf_url:
            return pdf_url, source_url, strategy

    if driver is not None:
        webdriver_cache_path = cache_dir / f"{cache_key}_webdriver_search.json"
        if webdriver_cache_path.exists():
            webdriver_hits = json.loads(webdriver_cache_path.read_text(encoding="utf-8"))
        else:
            try:
                webdriver_hits = [
                    {"pdf_url": pdf_url, "source_url": source_url, "strategy": strategy}
                    for pdf_url, source_url, strategy in search_public_pdf_candidates_with_webdriver(driver, title)
                ]
            except Exception:
                webdriver_hits = []
            webdriver_cache_path.write_text(json.dumps(webdriver_hits, ensure_ascii=False, indent=2), encoding="utf-8")
        for hit in webdriver_hits:
            pdf_url = normalize_space(str(hit.get("pdf_url", "")))
            source_url = normalize_space(str(hit.get("source_url", "")))
            strategy = normalize_space(str(hit.get("strategy", "webdriver_search")))
            if pdf_url:
                return pdf_url, source_url, strategy
    return "", "", ""


def download_pdf(url: str, output_path: Path, referer: str = "") -> tuple[bool, str, int]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/pdf,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if referer:
        headers["Referer"] = referer
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
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
    webdriver_search: bool = False,
) -> dict[str, Any]:
    """下载会议论文 PDF，并记录成功与未解决情况。"""
    pdf_dir = conference_pdf_dir(output_dir, config.key)
    cache_dir = output_dir / "resolution" / config.key / "dblp_pdf_search_cache"
    report_rows: list[dict[str, Any]] = []
    downloaded = 0
    papers_seen = 0
    driver = create_safari_webdriver() if webdriver_search else None
    for paper in papers:
        if pdf_limit > 0 and papers_seen >= pdf_limit:
            break
        papers_seen += 1
        paper_id = normalize_space(str(paper.get("paperId", "")))
        title = normalize_space(str(paper.get("title", "")))
        pdf_url, source_url, strategy = resolve_iacr_pdf_candidate(config, paper, cache_dir, driver=driver)
        row = {
            "conference": config.conference,
            "year": config.year,
            "paper_id": paper_id,
            "title": title,
            "source_url": source_url,
            "pdf_url": pdf_url,
            "resolution_strategy": strategy,
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
    if driver is not None:
        try:
            driver.quit()
        except Exception:
            pass
    return summary


def run_single_conference(
    config: ConferenceConfig,
    raw_json_path: Path,
    output_dir: Path,
    resolve_mismatches: bool = False,
    query_dblp_for_resolution: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    """执行单个 IACR 会议年份的完整抽取流程。"""
    papers = load_papers(raw_json_path)
    overrides = load_institution_overrides(output_dir / "reference" / "institution_country_overrides.csv")
    author_affiliation_overrides = load_author_affiliation_overrides(
        output_dir / "reference" / "author_affiliation_overrides.csv"
    )
    conference_output = conference_output_dir(output_dir, config.key)
    conference_interim = conference_interim_dir(output_dir, config.key)
    paper_rows = normalize_papers(config, papers)
    rows, issues = expand_author_rows(config, papers, overrides)
    rows = apply_author_affiliation_overrides(rows, author_affiliation_overrides, overrides)
    classified_rows = filter_classified_rows(rows)
    classified_rows_final = rows
    country_counts = count_country_resolution_rows(rows)

    write_csv(
        conference_interim / "author_affiliations_expanded.csv",
        rows,
        [
            "conference",
            "year",
            "paper_id",
            "title",
            "name",
            "article_tag",
            "author_order",
            "inst",
            "country",
            "classification_source",
            "classification_confidence",
            "classification_reason",
        ],
    )
    write_csv(
        conference_interim / "affiliation_resolution_queue.csv",
        issues,
        [
            "conference",
            "year",
            "paper_id",
            "title",
            "issue",
            "authors_count",
            "affiliations_count",
            "authors",
            "affiliations",
        ],
    )
    write_csv(
        conference_output / "author_affiliations.csv",
        classified_rows,
        ["name", "year", "article_tag", "author_order", "inst", "country"],
    )
    write_csv(
        conference_output / "author_affiliations_audit.csv",
        classified_rows_final,
        [
            "conference",
            "year",
            "paper_id",
            "title",
            "name",
            "article_tag",
            "author_order",
            "inst",
            "country",
            "classification_source",
            "classification_confidence",
            "classification_reason",
        ],
    )
    write_workbook(conference_output / "author_affiliations.xlsx", classified_rows_final, ["name", "year", "article_tag", "author_order", "inst", "country"])
    write_csv(
        conference_interim / "institution_classification_candidates.csv",
        build_affiliation_candidates(rows),
        [
            "inst",
            "country",
            "classification_source",
            "classification_confidence",
            "classification_reason",
            "example_conference",
            "example_paper_id",
            "example_title",
        ],
    )
    report = {
        "conference": config.conference,
        "year": config.year,
        "raw_json": str(raw_json_path),
        "papers_count": len(papers),
        "expanded_author_rows": len(rows),
        "classified_author_rows": len(classified_rows),
        "resolved_country_rows": len(classified_rows),
        **country_counts,
        "affiliation_mismatch_issues": len(issues),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if resolve_mismatches and issues:
        resolution_dir = output_dir / "resolution" / config.key
        resolution_queue = conference_interim / "affiliation_resolution_queue.csv"
        resolution_report = run_resolution(
            resolution_queue,
            resolution_dir,
            query_dblp=query_dblp_for_resolution,
        )
        report["resolution_report_path"] = str(resolution_dir / "resolution_report.json")
        report["resolution_tasks"] = resolution_report["tasks"]
    report_path = conference_output / "validation_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report, paper_rows, rows, issues


def run_all_pipelines(
    output_dir: Path,
    conference_keys: list[str] | None = None,
    resolve_mismatches: bool = False,
    query_dblp_for_resolution: bool = False,
    download_pdfs: bool = False,
    pdf_limit: int = 0,
    webdriver_search: bool = False,
) -> dict[str, Any]:
    """对请求的 IACR 会议集合批量执行抽取。"""
    selected_keys = conference_keys or list(CONFERENCE_CONFIGS.keys())
    summary_output = summary_output_dir(output_dir, "top3_crypto")
    summary_interim = summary_interim_dir(output_dir, "top3_crypto")
    reports: list[dict[str, Any]] = []
    all_papers: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    all_issues: list[dict[str, str]] = []
    pdf_reports: list[dict[str, Any]] = []

    for key in selected_keys:
        config = CONFERENCE_CONFIGS[key]
        raw_json_path = conference_raw_dir(output_dir, config.key) / "papers.json"
        papers = load_papers(raw_json_path)
        if download_pdfs:
            pdf_reports.append(download_pdfs_for_conference(config, papers, output_dir, pdf_limit=pdf_limit, webdriver_search=webdriver_search))
        report, paper_rows, rows, issues = run_single_conference(
            config,
            raw_json_path,
            output_dir,
            resolve_mismatches=resolve_mismatches,
            query_dblp_for_resolution=query_dblp_for_resolution,
        )
        reports.append(report)
        all_papers.extend(paper_rows)
        all_rows.extend(rows)
        all_issues.extend(issues)

    all_classified_rows = filter_classified_rows(all_rows)
    all_classified_rows_final = all_rows
    country_counts = count_country_resolution_rows(all_rows)
    candidates = build_affiliation_candidates(all_rows)
    llm_rows = build_llm_resolution_rows(candidates)

    write_csv(
        summary_interim / "papers_normalized.csv",
        all_papers,
        [
            "conference",
            "year",
            "paper_id",
            "title",
            "article_tag",
            "authors_count",
            "affiliations_count",
        ],
    )
    write_csv(
        summary_interim / "author_affiliations_expanded.csv",
        all_rows,
        [
            "conference",
            "year",
            "paper_id",
            "title",
            "name",
            "article_tag",
            "author_order",
            "inst",
            "country",
            "classification_source",
            "classification_confidence",
            "classification_reason",
        ],
    )
    write_csv(
        summary_interim / "institution_classification_candidates.csv",
        candidates,
        [
            "inst",
            "country",
            "classification_source",
            "classification_confidence",
            "classification_reason",
            "example_conference",
            "example_paper_id",
            "example_title",
        ],
    )
    write_csv(
        summary_interim / "affiliation_resolution_queue.csv",
        all_issues,
        [
            "conference",
            "year",
            "paper_id",
            "title",
            "issue",
            "authors_count",
            "affiliations_count",
            "authors",
            "affiliations",
        ],
    )
    write_jsonl(summary_interim / "llm_resolution_input.jsonl", llm_rows)
    write_jsonl(summary_interim / "llm_resolution_output.jsonl", llm_rows)

    write_csv(
        summary_output / "2020-2025三大密码会_作者机构国家.csv",
        all_classified_rows,
        ["name", "year", "article_tag", "author_order", "inst", "country"],
    )
    write_csv(
        summary_output / "2020-2025三大密码会_作者机构国家_audit.csv",
        all_classified_rows_final,
        [
            "conference",
            "year",
            "paper_id",
            "title",
            "name",
            "article_tag",
            "author_order",
            "inst",
            "country",
            "classification_source",
            "classification_confidence",
            "classification_reason",
        ],
    )
    write_workbook(summary_output / "2020-2025三大密码会_作者机构国家.xlsx", all_classified_rows_final, ["name", "year", "article_tag", "author_order", "inst", "country"])

    combined_report = {
        "reports": reports,
        "papers_count": sum(report["papers_count"] for report in reports),
        "expanded_author_rows": len(all_rows),
        "classified_author_rows": len(all_classified_rows),
        "resolved_country_rows": len(all_classified_rows),
        **country_counts,
        "affiliation_mismatch_issues": len(all_issues),
        "unresolved_affiliation_candidates": len(llm_rows),
        "pdf_download_reports": pdf_reports,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "notes": [
            "Main output contains only conservatively country-resolved author rows.",
            "Audit output preserves mismatch fallback rows even when the country remains Unknown.",
            "LLM resolution output is conservative: unresolved institutions remain marked for manual review.",
        ],
    }
    report_path = summary_output / "validation_report.json"
    report_path.write_text(json.dumps(combined_report, ensure_ascii=False, indent=2), encoding="utf-8")
    return combined_report


def main(argv: list[str] | None = None) -> int:
    """解析命令行参数并启动 IACR 三大会抽取后端。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--conference", nargs="*", default=["all"], help="Conference keys or 'all'")
    parser.add_argument("--raw-json", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--list-conferences", action="store_true")
    parser.add_argument("--resolve-mismatches", action="store_true")
    parser.add_argument("--query-dblp-for-resolution", action="store_true")
    parser.add_argument("--download-pdfs", action="store_true")
    parser.add_argument("--pdf-limit", type=int, default=0)
    parser.add_argument("--webdriver-search", action="store_true")
    args = parser.parse_args(argv)

    if args.list_conferences:
        for key, config in CONFERENCE_CONFIGS.items():
            print(f"  {key}: {config.conference} {config.year}")
        return 0

    if "all" in args.conference:
        keys = list(CONFERENCE_CONFIGS.keys())
    else:
        keys = args.conference

    if args.fetch:
        for key in keys:
            config = CONFERENCE_CONFIGS[key]
            raw_json_path = conference_raw_dir(args.output_dir, config.key) / "papers.json"
            try:
                metadata = fetch_json(config.url, raw_json_path)
                metadata_path = conference_raw_dir(args.output_dir, config.key) / "fetch_metadata.json"
                metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            except urllib.error.HTTPError as exc:
                print(
                    f"Fetch for {config.key} failed with HTTP {exc.code}. Provide saved raw snapshots before running.",
                    file=sys.stderr,
                )
                return 2

    if len(keys) == 1 and args.raw_json:
        config = CONFERENCE_CONFIGS[keys[0]]
        report, _paper_rows, _rows, _issues = run_single_conference(
            config,
            args.raw_json,
            args.output_dir,
            resolve_mismatches=args.resolve_mismatches,
            query_dblp_for_resolution=args.query_dblp_for_resolution,
        )
    else:
        report = run_all_pipelines(
            args.output_dir,
            keys,
            resolve_mismatches=args.resolve_mismatches,
            query_dblp_for_resolution=args.query_dblp_for_resolution,
            download_pdfs=args.download_pdfs,
            pdf_limit=args.pdf_limit,
            webdriver_search=args.webdriver_search,
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
