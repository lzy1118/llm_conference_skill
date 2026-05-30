from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import csv

from backend_common import write_csv, write_jsonl, write_workbook
from classification_common import classify_with_patterns, load_override_rows, normalize_space
from iacr_resolution import run_resolution


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
    title = normalize_space(str(paper.get("title", "")))
    return f"{config.conference}-{title}"


def parse_iacr_people_field(value: Any) -> list[str]:
    if isinstance(value, list):
        return [normalize_space(str(item)) for item in value if normalize_space(str(item))]
    if isinstance(value, str):
        return [normalize_space(item) for item in value.split(";") if normalize_space(item)]
    return []


def parse_iacr_affiliations_field(value: Any) -> list[str]:
    if isinstance(value, list):
        return [normalize_space(str(item)) for item in value if normalize_space(str(item))]
    if isinstance(value, str):
        return [normalize_space(item) for item in value.split(";") if normalize_space(item)]
    return []


def extract_iacr_authors(paper: dict[str, Any]) -> list[str]:
    authors = parse_iacr_people_field(paper.get("authors", []))
    if authors:
        return authors
    return parse_iacr_people_field(paper.get("author", []))


def extract_iacr_affiliations(paper: dict[str, Any]) -> list[str]:
    affiliations = parse_iacr_affiliations_field(paper.get("affiliations", []))
    if affiliations:
        return affiliations
    return parse_iacr_affiliations_field(paper.get("institution", []))


def parse_inline_author_affiliation_pairs(value: Any) -> tuple[list[str], list[str]]:
    entries = parse_iacr_people_field(value)
    authors: list[str] = []
    affiliations: list[str] = []
    for entry in entries:
        match = re.fullmatch(r"(.+?)\s*\((.+)\)", entry)
        if not match:
            return [], []
        author = normalize_space(match.group(1))
        affiliation = normalize_space(match.group(2))
        if not author or not affiliation:
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
    authors = extract_iacr_authors(paper)
    affiliations = extract_iacr_affiliations(paper)
    if authors and affiliations:
        return authors, affiliations
    inline_authors, inline_affiliations = parse_inline_author_affiliation_pairs(paper.get("author", []))
    if inline_authors and inline_affiliations:
        return inline_authors, inline_affiliations
    return authors, affiliations


def classify_affiliation(
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


def split_affiliation_parts(affiliation: str) -> list[str]:
    normalized = normalize_space(affiliation)
    if ";" in normalized:
        return [part.strip() for part in normalized.split(";") if part.strip()]
    if "/" in normalized:
        return [part.strip() for part in normalized.split("/") if part.strip()]
    if " & " in normalized:
        parts = [part.strip() for part in normalized.split(" & ") if part.strip()]
        if len(parts) > 1:
            return parts
    if " and " in normalized:
        if re.search(
            r"\b(Science and Technology|Posts and Telecommunications|Economics and Technology|Research and Technology|Information and Communications Technology|Polytechnic Institute and State University|Academy of Mathematics and System Science|Academy of Mathematics and Systems Science|Beijing Institute of Mathematical Sciences and Application|Beijing Institute of Mathematical Sciences and Applications|Computer Science and Artificial Intelligence)\b",
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
    parts = split_affiliation_parts(affiliation)
    results: list[tuple[str, AffiliationClassification]] = []
    seen: set[tuple[str, str]] = set()
    for part in parts:
        classification = classify_affiliation(part, overrides)
        key = (part, classification.country)
        if key in seen:
            continue
        seen.add(key)
        results.append((part, classification))
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
        if part == "College of Computer Science and Artificial Intelligence, Fudan University, Shanghai, China":
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
    return results


def expand_author_rows(
    config: ConferenceConfig,
    papers: list[dict[str, Any]],
    overrides: dict[str, AffiliationClassification] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []

    for index, paper in enumerate(papers):
        authors, affiliations = extract_iacr_author_affiliation_lists(paper)
        paper_id = extract_iacr_paper_id(paper, index)
        title = normalize_space(str(paper.get("title", "")))
        article_tag = build_article_tag(config, paper)

        if len(authors) != len(affiliations):
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
            # Conservative fallback for IACR mismatch rows:
            # keep any affiliation strings whose country can be resolved so paper-level
            # country participation is not dropped entirely. We duplicate the resolved
            # affiliation set across authors because author-level alignment is unavailable.
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
            if resolved_affiliations:
                classification_source = "mismatch_fallback_multi_country"
                known_countries = {classification.country for _, classification in resolved_affiliations}
                if len(known_countries) == 1:
                    classification_source = "mismatch_fallback_same_country"
                for order, author in enumerate(authors):
                    for affiliation, classification in resolved_affiliations:
                        rows.append(
                            {
                                "conference": config.conference,
                                "year": config.year,
                                "paper_id": paper_id,
                                "title": title,
                                "name": author,
                                "article_tag": article_tag,
                                "author_order": order,
                                "inst": affiliation,
                                "country": classification.country,
                                "classification_source": classification_source,
                                "classification_confidence": classification.confidence,
                                "classification_reason": classification.reason,
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
    return [row for row in rows if row.get("country") and row["country"] != "Unknown"]


def normalize_papers(config: ConferenceConfig, papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
    with urllib.request.urlopen(request, timeout=45) as response:
        content = response.read()
        status = getattr(response, "status", 200)

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


def download_pdf(url: str, output_path: Path) -> tuple[bool, str, int]:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/pdf,*/*;q=0.8"})
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
) -> dict[str, Any]:
    pdf_dir = output_dir / "pdfs" / config.key
    report_rows: list[dict[str, Any]] = []
    downloaded = 0
    papers_seen = 0
    for paper in papers:
        if pdf_limit > 0 and downloaded >= pdf_limit:
            break
        papers_seen += 1
        paper_id = normalize_space(str(paper.get("paperId", "")))
        title = normalize_space(str(paper.get("title", "")))
        pdf_url = extract_pdf_url_from_paper(paper)
        row = {
            "conference": config.conference,
            "year": config.year,
            "paper_id": paper_id,
            "title": title,
            "pdf_url": pdf_url,
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
            ok, content_type, byte_count = download_pdf(pdf_url, output_path)
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
        ["conference", "year", "paper_id", "title", "pdf_url", "status", "content_type", "bytes", "path", "error"],
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


def run_single_conference(
    config: ConferenceConfig,
    raw_json_path: Path,
    output_dir: Path,
    resolve_mismatches: bool = False,
    query_dblp_for_resolution: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    papers = load_papers(raw_json_path)
    overrides = load_institution_overrides(output_dir / "reference" / "institution_country_overrides.csv")
    author_affiliation_overrides = load_author_affiliation_overrides(
        output_dir / "reference" / "author_affiliation_overrides.csv"
    )
    paper_rows = normalize_papers(config, papers)
    rows, issues = expand_author_rows(config, papers, overrides)
    rows = apply_author_affiliation_overrides(rows, author_affiliation_overrides, overrides)
    classified_rows = filter_classified_rows(rows)
    classified_rows_final = classified_rows

    write_csv(
        output_dir / "interim" / f"{config.key}_author_affiliations_expanded.csv",
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
        output_dir / "interim" / f"{config.key}_affiliation_resolution_queue.csv",
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
        output_dir / "output" / f"{config.key}_author_affiliations.csv",
        classified_rows,
        ["name", "year", "article_tag", "author_order", "inst", "country"],
    )
    write_csv(
        output_dir / "output" / f"{config.key}_author_affiliations_audit.csv",
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
    write_workbook(output_dir / "output" / f"{config.key}_author_affiliations.xlsx", classified_rows_final, ["name", "year", "article_tag", "author_order", "inst", "country"])
    write_csv(
        output_dir / "interim" / f"{config.key}_institution_classification_candidates.csv",
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
        "unresolved_country_rows": len(rows) - len(classified_rows),
        "affiliation_mismatch_issues": len(issues),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if resolve_mismatches and issues:
        resolution_dir = output_dir / "resolution" / config.key
        resolution_queue = output_dir / "interim" / f"{config.key}_affiliation_resolution_queue.csv"
        resolution_report = run_resolution(
            resolution_queue,
            resolution_dir,
            query_dblp=query_dblp_for_resolution,
        )
        report["resolution_report_path"] = str(resolution_dir / "resolution_report.json")
        report["resolution_tasks"] = resolution_report["tasks"]
    report_path = output_dir / "output" / f"{config.key}_validation_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report, paper_rows, rows, issues


def run_all_pipelines(
    output_dir: Path,
    conference_keys: list[str] | None = None,
    resolve_mismatches: bool = False,
    query_dblp_for_resolution: bool = False,
    download_pdfs: bool = False,
    pdf_limit: int = 0,
) -> dict[str, Any]:
    selected_keys = conference_keys or list(CONFERENCE_CONFIGS.keys())
    reports: list[dict[str, Any]] = []
    all_papers: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    all_issues: list[dict[str, str]] = []
    pdf_reports: list[dict[str, Any]] = []

    for key in selected_keys:
        config = CONFERENCE_CONFIGS[key]
        raw_json_path = output_dir / "raw" / f"{config.key}_papers.json"
        papers = load_papers(raw_json_path)
        if download_pdfs:
            pdf_reports.append(download_pdfs_for_conference(config, papers, output_dir, pdf_limit=pdf_limit))
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
    all_classified_rows_final = all_classified_rows
    candidates = build_affiliation_candidates(all_rows)
    llm_rows = build_llm_resolution_rows(candidates)

    write_csv(
        output_dir / "interim" / "papers_normalized.csv",
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
        output_dir / "interim" / "author_affiliations_expanded.csv",
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
        output_dir / "interim" / "institution_classification_candidates.csv",
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
        output_dir / "interim" / "affiliation_resolution_queue.csv",
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
    write_jsonl(output_dir / "interim" / "llm_resolution_input.jsonl", llm_rows)
    write_jsonl(output_dir / "interim" / "llm_resolution_output.jsonl", llm_rows)

    write_csv(
        output_dir / "output" / "2025-2026三大密码会_作者机构国家.csv",
        all_classified_rows,
        ["name", "year", "article_tag", "author_order", "inst", "country"],
    )
    write_csv(
        output_dir / "output" / "2025-2026三大密码会_作者机构国家_audit.csv",
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
    write_workbook(output_dir / "output" / "2025-2026三大密码会_作者机构国家.xlsx", all_classified_rows_final, ["name", "year", "article_tag", "author_order", "inst", "country"])

    combined_report = {
        "reports": reports,
        "papers_count": sum(report["papers_count"] for report in reports),
        "expanded_author_rows": len(all_rows),
        "classified_author_rows": len(all_classified_rows),
        "resolved_country_rows": len(all_classified_rows),
        "unresolved_country_rows": len(all_rows) - len(all_classified_rows),
        "affiliation_mismatch_issues": len(all_issues),
        "unresolved_affiliation_candidates": len(llm_rows),
        "pdf_download_reports": pdf_reports,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "notes": [
            "Main output contains author rows whose author and affiliation arrays aligned and whose country could be resolved conservatively.",
            "Mismatched author-affiliation papers are preserved in generated-data/extraction/interim/affiliation_resolution_queue.csv for review.",
            "LLM resolution output is conservative: unresolved institutions remain marked for manual review.",
        ],
    }
    report_path = output_dir / "output" / "validation_report.json"
    report_path.write_text(json.dumps(combined_report, ensure_ascii=False, indent=2), encoding="utf-8")
    return combined_report


def main(argv: list[str] | None = None) -> int:
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
            raw_json_path = args.output_dir / "raw" / f"{config.key}_papers.json"
            try:
                metadata = fetch_json(config.url, raw_json_path)
                metadata_path = args.output_dir / "raw" / f"{config.key}_fetch_metadata.json"
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
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
