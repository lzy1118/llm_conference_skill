"""Supplement PDF metadata from the four security-conference websites.

PDF extraction remains the primary record. Official web metadata fills only
missing titles, authors, and affiliations. Conflicting non-empty PDF values are
preserved as publication evidence and recorded in the reconciliation report.
"""

from __future__ import annotations

import argparse
import copy
import csv
import difflib
import html
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
PAPER_EXTRACTION_SCRIPTS = WORKSPACE_ROOT / "conference-paper-extraction" / "scripts"
if str(PAPER_EXTRACTION_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PAPER_EXTRACTION_SCRIPTS))

import security_affiliation_sources as security
import ieee_sp_strategy
from author_metadata.artifacts import (
    abstract_csv_row,
    author_csv_rows,
    new_metrics,
    review_csv_rows,
    trailing_country,
    update_metrics,
)
from author_metadata.exporter import CSV_FIELDNAMES, REVIEW_FIELDNAMES
from author_metadata.paper_fields import build_paper_relationship_summary


OFFICIAL_SOURCE = "conference_official_web"
OFFICIAL_STAGE = "official_web_reconciliation"
PDF_COUNTRY_STAGE = "pdf_country_preservation"
PLACEHOLDER_AUTHORS = {"NO_AUTHORS_EXTRACTED", "PARSE_ERROR"}
ROLE_ONLY_AFFILIATION_RE = re.compile(
    r"^(?:equal contributions?|contributed equally|co[- ]?first authors?|"
    r"corresponding authors?)\.?$",
    re.IGNORECASE,
)
TRUSTED_MATCH_STATUSES = {
    "normalized_title_exact",
    "normalized_title_compact_exact",
    "source_filename_exact",
    "source_filename_unique_containment",
    "author_sequence_exact",
    "normalized_title_unique_containment",
    "normalized_title_unique_fuzzy",
}
SUPPORTED_CONFERENCES = {
    "ccs": "ccs",
    "ndss": "ndss",
    "ieee_s&p": "ieee_sp",
    "ieee_sp": "ieee_sp",
    "sp": "ieee_sp",
    "usenix_security": "usenix_security",
    "usenix security": "usenix_security",
    "usenix": "usenix_security",
}
REPORT_FIELDS = [
    "paper_id",
    "title",
    "match_status",
    "local_author_count",
    "official_author_count",
    "authors_recovered",
    "authors_rebuilt",
    "affiliations_filled",
    "author_conflict",
    "affiliation_conflicts",
    "blank_affiliations_after",
    "official_title",
    "source_url",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fill blank affiliations from official CCS, NDSS, IEEE S&P, or USENIX Security pages."
    )
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--conference", required=True)
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def conference_config_key(conference: str, year: int) -> str:
    normalized = security.normalize_space(conference).casefold().replace("-", "_")
    prefix = SUPPORTED_CONFERENCES.get(normalized)
    if not prefix:
        raise ValueError(f"unsupported security conference: {conference}")
    key = f"{prefix}_{year}"
    if key not in security.CONFERENCES:
        raise ValueError(f"official source is not configured: {key}")
    return key


def official_list_url(config: security.ConferenceConfig) -> str:
    year = config.year
    if config.conference == "CCS":
        if year <= 2021:
            return f"https://www.sigsac.org/ccs/CCS{year}/accepted-papers.html"
        if year == 2023:
            return "https://www.sigsac.org/ccs/CCS2023/assets/data/accepted_papers.xml"
        if year == 2025:
            return "https://www.sigsac.org/ccs/CCS2025/assets/accepted-papers.json"
        return f"https://www.sigsac.org/ccs/CCS{year}/program/accepted-papers.html"
    if config.conference == "NDSS":
        return f"https://www.ndss-symposium.org/ndss{year}/accepted-papers/"
    if config.conference == "IEEE_S&P":
        return (
            f"https://www.ieee-security.org/TC/SP{year}/program-papers.html"
            if year <= 2023
            else f"https://sp{year}.ieee-security.org/accepted-papers.html"
        )
    yy = str(year)[-2:]
    return f"https://www.usenix.org/conference/usenixsecurity{yy}/technical-sessions"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def csv_author_sequence(rows: list[dict[str, str]]) -> list[str]:
    """Return one author occurrence per paper from affiliation-granular CSV rows."""
    result: list[str] = []
    previous_key = ""
    # Exporters already emit rows in metadata-author order.  Sorting by the
    # display rank is unsafe because co-first authors intentionally share rank 0.
    for row in rows:
        name = str(row.get("author", ""))
        key = security.normalized_person_key(name)
        if not key or name in PLACEHOLDER_AUTHORS:
            continue
        if key == previous_key:
            continue
        previous_key = key
        result.append(name)
    return result


def grouped_csv_authors(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Collapse affiliation-granular rows while retaining country rank positions."""
    result: list[dict[str, Any]] = []
    previous_key = ""
    for row in rows:
        name = str(row.get("author", ""))
        key = security.normalized_person_key(name)
        if not key or name in PLACEHOLDER_AUTHORS:
            continue
        if key != previous_key:
            result.append({"name": name, "pdf_countries": []})
            previous_key = key
        result[-1]["pdf_countries"].append(trailing_country(row.get("country", "")))
    return result


def earliest_pdf_country_csv(dataset_dir: Path, current_csv_path: Path) -> Path:
    """Use the oldest pre-official snapshot as the immutable PDF-country source."""
    backups = sorted(
        path
        for path in (dataset_dir / "backups").glob("before_official_web_*/paper_metadata.csv")
        if path.is_file()
    )
    return backups[0] if backups else current_csv_path


def restore_pdf_countries(
    metadata: dict[str, Any],
    source_rows: list[dict[str, str]],
) -> tuple[int, int]:
    """Persist PDF countries without replacing evidence saved by an earlier run."""
    authors = metadata.get("authors", [])
    source_authors = grouped_csv_authors(source_rows)
    alignment, _unmatched_local, _unmatched_source = unique_author_alignment(authors, source_authors)
    if len(authors) == len(source_authors) and all(
        local_index == source_index
        for local_index, source_index in alignment.items()
    ):
        for index in range(len(authors)):
            alignment.setdefault(index, index)
    restored_authors = 0
    restored_values = 0
    for local_index, source_index in alignment.items():
        author = authors[local_index]
        existing = [trailing_country(value) for value in author.get("pdf_countries", [])]
        if any(existing):
            continue
        countries = list(source_authors[source_index].get("pdf_countries", []))
        if not any(countries):
            continue
        author["pdf_countries"] = countries
        restored_authors += 1
        restored_values += sum(bool(country) for country in countries)
    if restored_authors:
        metadata.setdefault("_extraction", {}).setdefault("decisions", []).append({
            "action": "preserve_pdf_countries_before_official_web",
            "stage": PDF_COUNTRY_STAGE,
            "field": "country",
            "authors_restored": restored_authors,
            "country_values_restored": restored_values,
            "source": "pdf_extraction_csv",
        })
    return restored_authors, restored_values


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def load_official_entries_with_cache(
    config_key: str,
    config: security.ConferenceConfig,
    source_url: str,
    dataset_dir: Path,
) -> tuple[list[dict[str, Any]], Path, str]:
    cache_path = dataset_dir / "official_web_evidence" / f"{config_key}.json"
    try:
        entries = security.load_official_affiliation_entries(config_key)
    except Exception:
        entries = []
    if entries:
        write_json(
            cache_path,
            {
                "conference": config.conference,
                "year": config.year,
                "source_url": source_url,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "entries": entries,
            },
        )
        return entries, cache_path, "live_dom"
    if cache_path.exists():
        cached = read_json(cache_path)
        cached_entries = cached.get("entries", [])
        if cached_entries:
            return cached_entries, cache_path, "cached_dom"
    return [], cache_path, "unavailable"


def official_authors(entry: dict[str, Any]) -> list[str]:
    names = [
        security.clean_author_name(str(name))
        for name in entry.get("authors", [])
        if security.clean_author_name(str(name))
    ]
    if not names:
        names = [
        security.clean_author_name(str(row.get("name", "")))
        for row in entry.get("official_affiliations", [])
        if security.clean_author_name(str(row.get("name", "")))
        ]
    result: list[str] = []
    seen: set[str] = set()
    for name in names:
        key = security.normalized_person_key(name)
        if key and key not in seen:
            seen.add(key)
            result.append(name)
    return result


def official_rows(entry: dict[str, Any]) -> list[dict[str, Any]]:
    by_name = [
        {
            "name": security.clean_author_name(str(row.get("name", ""))),
            "affiliations": security.normalize_affiliation_values(row.get("affiliations", [])),
        }
        for row in entry.get("official_affiliations", [])
        if security.clean_author_name(str(row.get("name", "")))
    ]
    if by_name:
        merged: list[dict[str, Any]] = []
        by_key: dict[str, dict[str, Any]] = {}
        for row in by_name:
            key = security.normalized_person_key(row["name"])
            if key not in by_key:
                selected = {"name": row["name"], "affiliations": []}
                by_key[key] = selected
                merged.append(selected)
            selected = by_key[key]
            selected["affiliations"] = security.normalize_affiliation_values(
                list(selected["affiliations"]) + list(row["affiliations"])
            )
        return merged
    return [{"name": name, "affiliations": []} for name in official_authors(entry)]


def repair_missing_official_affiliations_from_pdf(
    metadata: dict[str, Any],
    entry: dict[str, Any] | None,
    conference: str,
) -> dict[str, Any]:
    """Recover direct PDF affiliations when a matched official DOM omits them."""
    if conference != "IEEE_S&P" or entry is None:
        return metadata
    web_rows = official_rows(entry)
    if not web_rows or any(row.get("affiliations") for row in web_rows):
        return metadata
    authors = metadata.get("authors", [])
    current_affiliations = [
        str(affiliation).strip()
        for author in authors
        for affiliation in author.get("affiliations", [])
        if str(affiliation).strip()
    ]
    if current_affiliations and not all(
        ROLE_ONLY_AFFILIATION_RE.fullmatch(affiliation)
        for affiliation in current_affiliations
    ):
        return metadata
    pdf_lines = [
        str(evidence.get("raw_text", ""))
        for evidence in metadata.get("_extraction", {}).get("evidence", [])
        if evidence.get("source") == "pdf_text"
        and evidence.get("field") == "header_line"
        and evidence.get("raw_text")
    ]
    if not pdf_lines:
        return metadata
    refined = ieee_sp_strategy.refine_authors(
        copy.deepcopy(authors),
        pdf_lines=pdf_lines,
        title=str(metadata.get("title", "")),
    )
    official_keys = {security.normalized_person_key(row["name"]) for row in web_rows}
    refined_by_key = {
        security.normalized_person_key(str(author.get("name", ""))): author
        for author in refined
    }
    if set(refined_by_key) != official_keys:
        return metadata
    if any(
        not author.get("affiliations")
        or any(ROLE_ONLY_AFFILIATION_RE.fullmatch(str(value).strip()) for value in author["affiliations"])
        for author in refined
    ):
        return metadata
    result = copy.deepcopy(metadata)
    for author in result.get("authors", []):
        refined_author = refined_by_key[security.normalized_person_key(str(author.get("name", "")))]
        author["affiliations"] = list(refined_author["affiliations"])
        author["affiliation_source"] = "pdf_symbol_affiliation"
        for field in ("first_author", "co_first_author", "equal_contribution", "corresponding"):
            author[field] = bool(refined_author.get(field, author.get(field, False)))
    result.setdefault("_extraction", {}).setdefault("decisions", []).append({
        "action": "fill_official_dom_affiliation_gap_from_pdf_symbol_line",
        "stage": OFFICIAL_STAGE,
        "field": "affiliations",
        "selected": {
            author.get("name", ""): list(author.get("affiliations", []))
            for author in result.get("authors", [])
        },
        "source": "pdf_text",
    })
    return result


def official_entry_content_signature(entry: dict[str, Any]) -> tuple[Any, ...]:
    return (
        tuple(security.normalized_person_key(name) for name in official_authors(entry)),
        tuple(
            (
                security.normalized_person_key(row["name"]),
                tuple(sorted(affiliation_key(row["affiliations"]))),
            )
            for row in official_rows(entry)
        ),
    )


def preferred_duplicate_entry(
    current: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any] | None:
    if official_entry_content_signature(current) == official_entry_content_signature(candidate):
        return current
    if author_sequence_key(official_authors(current)) != author_sequence_key(official_authors(candidate)):
        return None
    current_auto = "auto-draft" in str(current.get("url", "")).casefold()
    candidate_auto = "auto-draft" in str(candidate.get("url", "")).casefold()
    if current_auto != candidate_auto:
        return candidate if current_auto else current
    return None


def make_title_lookup(entries: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], set[str]]:
    lookup: dict[str, dict[str, Any]] = {}
    ambiguous: set[str] = set()
    for entry in entries:
        key = security.official_title_key(str(entry.get("title", "")))
        if not key:
            continue
        if key in lookup:
            preferred = preferred_duplicate_entry(lookup[key], entry)
            if preferred is None:
                ambiguous.add(key)
            else:
                lookup[key] = preferred
        else:
            lookup[key] = entry
    for key in ambiguous:
        lookup.pop(key, None)
    return lookup, ambiguous


def make_compact_title_lookup(entries: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], set[str]]:
    lookup: dict[str, dict[str, Any]] = {}
    ambiguous: set[str] = set()
    for entry in entries:
        key = security.official_title_key(str(entry.get("title", ""))).replace(" ", "")
        if not key:
            continue
        if key in lookup:
            preferred = preferred_duplicate_entry(lookup[key], entry)
            if preferred is None:
                ambiguous.add(key)
            else:
                lookup[key] = preferred
        else:
            lookup[key] = entry
    for key in ambiguous:
        lookup.pop(key, None)
    return lookup, ambiguous


def author_sequence_key(names: list[str]) -> tuple[str, ...]:
    return tuple(security.normalized_person_key(name) for name in names if name)


def make_author_lookup(entries: list[dict[str, Any]]) -> tuple[dict[tuple[str, ...], dict[str, Any]], set[tuple[str, ...]]]:
    lookup: dict[tuple[str, ...], dict[str, Any]] = {}
    ambiguous: set[tuple[str, ...]] = set()
    for entry in entries:
        key = author_sequence_key(official_authors(entry))
        if not key:
            continue
        if key in lookup:
            ambiguous.add(key)
        else:
            lookup[key] = entry
    for key in ambiguous:
        lookup.pop(key, None)
    return lookup, ambiguous


def unique_fuzzy_title_match(
    title: str,
    title_lookup: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, float]:
    key = security.official_title_key(title)
    if len(key.replace(" ", "")) < 20:
        return None, 0.0
    ranked = sorted(
        [
            (
                difflib.SequenceMatcher(None, key, candidate_key).ratio(),
                entry,
            )
            for candidate_key, entry in title_lookup.items()
        ],
        key=lambda item: item[0],
    )
    if not ranked:
        return None, 0.0
    best_score, best_entry = ranked[-1]
    second_score = ranked[-2][0] if len(ranked) > 1 else 0.0
    if best_score < 0.85 or best_score - second_score < 0.12:
        return None, best_score
    return best_entry, best_score


def unique_contained_title_match(
    title: str,
    title_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Match a safely long title when either side is a unique truncation of the other."""
    key = security.official_title_key(title)
    compact_key = key.replace(" ", "")
    if len(compact_key) < 24 or len(key.split()) < 4:
        return None
    matches: list[dict[str, Any]] = []
    for candidate_key, entry in title_lookup.items():
        compact_candidate = candidate_key.replace(" ", "")
        shorter = compact_key if len(compact_key) <= len(compact_candidate) else compact_candidate
        if len(shorter) < 24:
            continue
        if compact_key in compact_candidate or compact_candidate in compact_key:
            matches.append(entry)
    return matches[0] if len(matches) == 1 else None


def unique_author_alignment(
    local_authors: list[dict[str, Any]],
    web_rows: list[dict[str, Any]],
) -> tuple[dict[int, int], list[str], list[str]]:
    alignment: dict[int, int] = {}
    used_web: set[int] = set()
    for local_index, author in enumerate(local_authors):
        local_key = security.normalized_person_key(str(author.get("name", "")))
        matches = [
            web_index
            for web_index, row in enumerate(web_rows)
            if web_index not in used_web
            and local_key == security.normalized_person_key(str(row.get("name", "")))
        ]
        if len(matches) == 1:
            alignment[local_index] = matches[0]
            used_web.add(matches[0])
    for local_index, author in enumerate(local_authors):
        if local_index in alignment:
            continue
        matches = [
            web_index
            for web_index, row in enumerate(web_rows)
            if web_index not in used_web
            and security.names_match(str(author.get("name", "")), str(row.get("name", "")))
        ]
        if len(matches) == 1:
            alignment[local_index] = matches[0]
            used_web.add(matches[0])
    unmatched_local = [
        str(author.get("name", ""))
        for index, author in enumerate(local_authors)
        if index not in alignment
    ]
    unmatched_web = [
        str(row.get("name", ""))
        for index, row in enumerate(web_rows)
        if index not in used_web
    ]
    return alignment, unmatched_local, unmatched_web


def affiliation_key(values: list[str]) -> set[str]:
    return {
        security.normalize_space(value).casefold().strip(" ,;.")
        for value in values
        if security.normalize_space(value)
    }


def reconcile_metadata(
    metadata: dict[str, Any],
    entry: dict[str, Any] | None,
    source_url: str,
    match_status: str = "normalized_title_exact",
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = copy.deepcopy(metadata)
    authors = result.get("authors", [])
    extraction = result.setdefault("_extraction", {})
    extraction["review_reasons"] = [
        reason
        for reason in extraction.get("review_reasons", [])
        if reason.get("stage") != OFFICIAL_STAGE
    ]
    extraction["evidence"] = [
        evidence
        for evidence in extraction.get("evidence", [])
        if evidence.get("source") != OFFICIAL_SOURCE
    ]
    extraction["decisions"] = [
        decision
        for decision in extraction.get("decisions", [])
        if decision.get("stage") != OFFICIAL_STAGE
    ]

    outcome = {
        "match_status": "unmatched",
        "affiliations_filled": 0,
        "author_conflict": False,
        "affiliation_conflicts": 0,
        "official_author_count": 0,
        "authors_recovered": 0,
        "authors_rebuilt": False,
        "author_count_delta": 0,
        "official_title": "",
        "source_url": source_url,
        "blank_affiliations_after": 0,
    }
    if entry is None:
        outcome["blank_affiliations_after"] = sum(
            not author.get("affiliations") for author in authors
        )
        extraction["review_reasons"].append({
            "code": "official_web_paper_unmatched",
            "stage": OFFICIAL_STAGE,
            "field": "paper",
            "reason": "no_unique_exact_official_title_match",
        })
        extraction.setdefault("candidates", {})["official_web"] = outcome
        return result, outcome

    web_rows = official_rows(entry)
    outcome.update({
        "match_status": match_status,
        "official_author_count": len(official_authors(entry)),
        "official_title": str(entry.get("title", "")),
        "source_url": str(entry.get("url", "")) or source_url,
    })
    if not security.normalize_space(result.get("title", "")) and match_status in TRUSTED_MATCH_STATUSES:
        result["title"] = security.normalize_space(entry.get("title", ""))
        extraction["decisions"].append({
            "action": "fill_blank_title_from_official_web",
            "stage": OFFICIAL_STAGE,
            "field": "title",
            "selected": result["title"],
            "source": OFFICIAL_SOURCE,
        })
    if not authors and match_status in TRUSTED_MATCH_STATUSES and web_rows:
        authors = [
            {
                "order": index,
                "name": row["name"],
                "email": "",
                "affiliations": list(row.get("affiliations", [])),
                "affiliation_source": OFFICIAL_SOURCE,
                "first_author": index == 0,
                "co_first_author": False,
                "corresponding": False,
                "equal_contribution": False,
            }
            for index, row in enumerate(web_rows)
        ]
        result["authors"] = authors
        if not security.normalize_space(result.get("title", "")):
            result["title"] = security.normalize_space(entry.get("title", ""))
        outcome["authors_recovered"] = len(authors)
        outcome["author_count_delta"] = len(authors)
        extraction["review_reasons"].append({
            "code": "official_web_author_list_recovered_from_empty_extraction",
            "stage": OFFICIAL_STAGE,
            "field": "authors",
            "official_authors": [author["name"] for author in authors],
            "reason": "pdf_text_layer_unreadable_and_official_match_trusted",
        })
        extraction["decisions"].append({
            "action": "recover_empty_author_list_from_official_web",
            "stage": OFFICIAL_STAGE,
            "field": "authors",
            "selected": [author["name"] for author in authors],
            "source": OFFICIAL_SOURCE,
        })
    alignment, unmatched_local, unmatched_web = unique_author_alignment(authors, web_rows)
    author_conflict = bool(unmatched_local or unmatched_web or len(authors) != len(official_authors(entry)))
    if author_conflict:
        outcome["author_conflict"] = True
        extraction["review_reasons"].append({
            "code": "official_web_author_list_conflict",
            "stage": OFFICIAL_STAGE,
            "field": "authors",
            "local_authors": [author.get("name", "") for author in authors],
            "official_authors": official_authors(entry),
            "unmatched_local": unmatched_local,
            "unmatched_official": unmatched_web,
        })

    for web_index, row in enumerate(web_rows):
        extraction["evidence"].append({
            "evidence_id": f"official_web:author:{web_index}",
            "source": OFFICIAL_SOURCE,
            "source_url": outcome["source_url"],
            "field": "author_affiliation_relation",
            "author": row["name"],
            "affiliations": row["affiliations"],
        })

    for local_index, web_index in alignment.items():
        author = authors[local_index]
        web_affiliations = list(web_rows[web_index].get("affiliations", []))
        if not web_affiliations:
            continue
        local_affiliations = list(author.get("affiliations", []))
        if not local_affiliations:
            author["affiliations"] = web_affiliations
            author["affiliation_source"] = OFFICIAL_SOURCE
            outcome["affiliations_filled"] += 1
            extraction["decisions"].append({
                "action": "fill_blank_affiliation_from_official_web",
                "stage": OFFICIAL_STAGE,
                "field": "affiliations",
                "author": author.get("name", ""),
                "selected": web_affiliations,
                "source": OFFICIAL_SOURCE,
            })
        elif affiliation_key(local_affiliations) != affiliation_key(web_affiliations):
            outcome["affiliation_conflicts"] += 1
            extraction["review_reasons"].append({
                "code": "official_web_affiliation_conflict",
                "stage": OFFICIAL_STAGE,
                "field": "affiliations",
                "author": author.get("name", ""),
                "pdf_affiliations": local_affiliations,
                "official_affiliations": web_affiliations,
            })

    result.update(build_paper_relationship_summary(authors))
    outcome["blank_affiliations_after"] = sum(
        not author.get("affiliations") for author in authors
    )
    extraction.setdefault("candidates", {})["official_web"] = {
        **outcome,
        "authors": web_rows,
    }
    return result, outcome


def make_backup(dataset_dir: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup_dir = dataset_dir / "backups" / f"before_official_web_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    for name in ("paper_metadata.csv", "review_queue.csv", "extraction_metrics.json"):
        source = dataset_dir / name
        if source.exists():
            shutil.copy2(source, backup_dir / name)
    for name in ("metadata_json", "evidence_json", "candidate_json"):
        source = dataset_dir / name
        if source.is_dir():
            shutil.copytree(source, backup_dir / name)
    return backup_dir


def main() -> int:
    args = parse_args()
    dataset_dir = args.dataset_dir.resolve()
    config_key = conference_config_key(args.conference, args.year)
    config = security.CONFERENCES[config_key]
    source_url = official_list_url(config)
    index_path = dataset_dir / "paper_index.csv"
    metadata_dir = dataset_dir / "metadata_json"
    csv_path = dataset_dir / "paper_metadata.csv"
    metrics_path = dataset_dir / "extraction_metrics.json"
    if not index_path.exists() or not metadata_dir.is_dir() or not csv_path.exists():
        raise SystemExit("dataset is missing paper_index.csv, metadata_json, or paper_metadata.csv")

    entries, official_cache_path, official_evidence_source = load_official_entries_with_cache(
        config_key,
        config,
        source_url,
        dataset_dir,
    )
    if not entries:
        report_name = "official_web_reconciliation.csv" if args.apply else "official_web_reconciliation_dry_run.csv"
        report_path = dataset_dir / report_name
        write_csv(report_path, REPORT_FIELDS, [])
        print(json.dumps({
            "mode": "apply" if args.apply else "dry-run",
            "conference": config.conference,
            "year": args.year,
            "status": "official_supplement_unavailable",
            "official_entries": 0,
            "official_evidence_source": official_evidence_source,
            "official_evidence": str(official_cache_path),
            "source_url": source_url,
            "report": str(report_path),
        }, ensure_ascii=False, indent=2))
        return 0
    title_lookup, ambiguous_titles = make_title_lookup(entries)
    compact_title_lookup, ambiguous_compact_titles = make_compact_title_lookup(entries)
    author_lookup, ambiguous_authors = make_author_lookup(entries)
    index_rows = [row for row in read_csv(index_path) if row.get("status", "staged") == "staged"]
    current_csv_rows = read_csv(csv_path)
    pdf_country_csv_path = earliest_pdf_country_csv(dataset_dir, csv_path)
    pdf_country_csv_rows = read_csv(pdf_country_csv_path)
    previous_metrics = read_json(metrics_path) if metrics_path.exists() else {}
    current_csv_by_paper: dict[str, list[dict[str, str]]] = {}
    for row in current_csv_rows:
        current_csv_by_paper.setdefault(row.get("paper_id", ""), []).append(row)
    pdf_country_csv_by_paper: dict[str, list[dict[str, str]]] = {}
    for row in pdf_country_csv_rows:
        pdf_country_csv_by_paper.setdefault(row.get("paper_id", ""), []).append(row)

    enriched: list[tuple[dict[str, str], dict[str, Any], dict[str, Any]]] = []
    report_rows: list[dict[str, Any]] = []
    pdf_country_authors_restored = 0
    pdf_country_values_restored = 0
    for index_row in index_rows:
        paper_id = index_row["paper_id"]
        metadata_path = metadata_dir / f"{paper_id}.json"
        if not metadata_path.exists():
            raise SystemExit(f"metadata JSON is missing: {metadata_path}")
        metadata = read_json(metadata_path)
        csv_names = csv_author_sequence(current_csv_by_paper.get(paper_id, []))
        metadata_names = [author.get("name", "") for author in metadata.get("authors", [])]
        if csv_names != metadata_names:
            raise SystemExit(f"CSV/metadata author sequence mismatch: {paper_id}")
        restored_authors, restored_values = restore_pdf_countries(
            metadata,
            pdf_country_csv_by_paper.get(paper_id, []),
        )
        pdf_country_authors_restored += restored_authors
        pdf_country_values_restored += restored_values
        title_key = security.official_title_key(str(metadata.get("title", "")))
        entry = None if title_key in ambiguous_titles else title_lookup.get(title_key)
        match_status = "normalized_title_exact"
        if entry is None:
            author_key = author_sequence_key(metadata_names)
            if author_key and author_key not in ambiguous_authors:
                entry = author_lookup.get(author_key)
                match_status = "author_sequence_exact"
        if entry is None:
            compact_title_key = title_key.replace(" ", "")
            if compact_title_key and compact_title_key not in ambiguous_compact_titles:
                entry = compact_title_lookup.get(compact_title_key)
                if entry is not None:
                    match_status = "normalized_title_compact_exact"
        if entry is None:
            source_stem = Path(index_row.get("source_file", "")).stem
            source_title = html.unescape(re.sub(r"^\d+[_-]", "", source_stem))
            source_key = security.official_title_key(source_title)
            if source_key and source_key not in ambiguous_titles:
                entry = title_lookup.get(source_key)
                if entry is not None:
                    match_status = "source_filename_exact"
        if entry is None:
            entry = unique_contained_title_match(source_title, title_lookup)
            if entry is not None:
                match_status = "source_filename_unique_containment"
        if entry is None:
            entry = unique_contained_title_match(
                str(metadata.get("title", "")),
                title_lookup,
            )
            if entry is not None:
                match_status = "normalized_title_unique_containment"
        if entry is None:
            entry, _fuzzy_score = unique_fuzzy_title_match(
                str(metadata.get("title", "")),
                title_lookup,
            )
            if entry is not None:
                match_status = "normalized_title_unique_fuzzy"
        metadata = repair_missing_official_affiliations_from_pdf(
            metadata,
            entry,
            config.conference,
        )
        updated, outcome = reconcile_metadata(
            metadata,
            entry,
            source_url,
            match_status,
        )
        enriched.append((index_row, updated, outcome))
        report_rows.append({
            "paper_id": paper_id,
            "title": updated.get("title", ""),
            "match_status": outcome["match_status"],
            "local_author_count": len(updated.get("authors", [])),
            "official_author_count": outcome["official_author_count"],
            "authors_recovered": outcome["authors_recovered"],
            "authors_rebuilt": str(outcome["authors_rebuilt"]).lower(),
            "affiliations_filled": outcome["affiliations_filled"],
            "author_conflict": str(outcome["author_conflict"]).lower(),
            "affiliation_conflicts": outcome["affiliation_conflicts"],
            "blank_affiliations_after": outcome["blank_affiliations_after"],
            "official_title": outcome["official_title"],
            "source_url": outcome["source_url"],
        })

    recovered_authors = sum(outcome["authors_recovered"] for _, _, outcome in enriched)
    author_count_delta = sum(outcome["author_count_delta"] for _, _, outcome in enriched)
    current_author_count = sum(
        len(csv_author_sequence(rows))
        for rows in current_csv_by_paper.values()
    )
    if sum(len(metadata.get("authors", [])) for _, metadata, _ in enriched) != current_author_count + author_count_delta:
        raise SystemExit("official reconciliation changed the author row count outside an approved exact-title rebuild")

    report_name = "official_web_reconciliation.csv" if args.apply else "official_web_reconciliation_dry_run.csv"
    report_path = dataset_dir / report_name
    write_csv(report_path, REPORT_FIELDS, report_rows)
    summary = {
        "mode": "apply" if args.apply else "dry-run",
        "conference": config.conference,
        "year": args.year,
        "papers": len(enriched),
        "official_entries": len(entries),
        "papers_matched": sum(outcome["match_status"] != "unmatched" for _, _, outcome in enriched),
        "affiliations_filled": sum(outcome["affiliations_filled"] for _, _, outcome in enriched),
        "authors_recovered": recovered_authors,
        "author_lists_rebuilt": sum(outcome["authors_rebuilt"] for _, _, outcome in enriched),
        "author_conflict_papers": sum(outcome["author_conflict"] for _, _, outcome in enriched),
        "affiliation_conflicts": sum(outcome["affiliation_conflicts"] for _, _, outcome in enriched),
        "blank_affiliations_after": sum(outcome["blank_affiliations_after"] for _, _, outcome in enriched),
        "pdf_country_authors_restored": pdf_country_authors_restored,
        "pdf_country_values_restored": pdf_country_values_restored,
        "pdf_country_source": str(pdf_country_csv_path),
        "official_evidence_source": official_evidence_source,
        "official_evidence": str(official_cache_path),
        "report": str(report_path),
    }
    if not args.apply:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    backup_dir = make_backup(dataset_dir)
    csv_rows: list[dict[str, Any]] = []
    abstract_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    metrics = new_metrics(len(enriched), include_extended=True)
    for index_row, metadata, _outcome in enriched:
        paper_id = index_row["paper_id"]
        extraction = metadata.get("_extraction", {})
        update_metrics(metrics, metadata)
        review_rows.extend(
            review_csv_rows(
                paper_id,
                index_row.get("source_file", ""),
                extraction.get("review_reasons", []),
            )
        )
        csv_rows.extend(
            row
            for author in metadata.get("authors", [])
            for row in author_csv_rows(paper_id, metadata, author, args.conference)
        )
        abstract_rows.append(abstract_csv_row(metadata, args.conference, fallback_title=paper_id, fallback_year=str(args.year)))
        write_json(metadata_dir / f"{paper_id}.json", metadata)
        write_json(
            dataset_dir / "evidence_json" / f"{paper_id}.json",
            {"paper_id": paper_id, "evidence": extraction.get("evidence", [])},
        )
        write_json(
            dataset_dir / "candidate_json" / f"{paper_id}.json",
            {
                "paper_id": paper_id,
                "candidates": extraction.get("candidates", {}),
                "decisions": extraction.get("decisions", []),
            },
        )

    metrics.update({
        "official_web_reconciled_papers": summary["papers_matched"],
        "official_web_affiliations_filled": summary["affiliations_filled"],
        "official_web_authors_recovered": summary["authors_recovered"],
        "official_web_author_lists_rebuilt": summary["author_lists_rebuilt"],
        "official_web_author_conflict_papers": summary["author_conflict_papers"],
        "official_web_affiliation_conflicts": summary["affiliation_conflicts"],
    })
    for key, value in previous_metrics.items():
        if key not in metrics:
            metrics[key] = value
    write_csv(csv_path, CSV_FIELDNAMES, csv_rows)
    write_csv(
        dataset_dir / "conference_year_paper_abstract.csv",
        ["conference", "year", "title", "abstract"],
        abstract_rows,
    )
    write_csv(dataset_dir / "review_queue.csv", REVIEW_FIELDNAMES, review_rows)
    write_json(metrics_path, metrics)
    summary["backup"] = str(backup_dir)
    summary["review_reasons_after"] = len(review_rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
