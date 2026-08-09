from __future__ import annotations

import argparse
import csv
import difflib
import html
import json
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import security_affiliation_sources as security


CONFERENCE_PREFIXES = {
    "ccs": "CCS",
    "ieee_sp": "IEEE_S&P",
    "ndss": "NDSS",
    "usenix_security": "USENIX_SECURITY",
}


def repair_gbk_mojibake(value: str) -> str:
    return security.repair_gbk_mojibake(value)


def clean_text(value: Any) -> str:
    return security.normalize_space(repair_gbk_mojibake(str(value or "")))


def paper_doi(paper: dict[str, Any]) -> str:
    return security.extract_doi_from_url(clean_text(paper.get("url", ""))).casefold()


def title_needs_metadata_repair(title: str) -> bool:
    text = clean_text(title)
    if not text:
        return True
    if len(text) < 8:
        return True
    if text.startswith((".", ":", "-", ";")):
        return True
    if text.count("{") != text.count("}") or text.count("[") != text.count("]"):
        return True
    if "\ufffd" in text or "\u25a1" in text:
        return True
    return False


def clean_metadata_title(value: str) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<sup>(.*?)</sup>", r"^\1", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<sub>(.*?)</sub>", r"_\1", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return clean_text(text)


def fetch_title_from_doi_metadata(doi: str) -> str:
    if not doi:
        return ""
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='')}"
    try:
        payload = json.loads(security.fetch_text(url, timeout=20))
    except Exception:
        return ""
    titles = payload.get("message", {}).get("title", [])
    if not titles:
        return ""
    return clean_metadata_title(str(titles[0]))


def fixed_paper_title(
    paper: dict[str, Any],
    official_entry: dict[str, Any] | None = None,
    fetch_from_network: bool = False,
) -> str:
    title = clean_text(paper.get("title", ""))
    official_title = clean_text((official_entry or {}).get("title", ""))
    if title_needs_metadata_repair(title) and official_title and not title_needs_metadata_repair(official_title):
        title = official_title
    doi = paper_doi(paper)
    if fetch_from_network and doi and title_needs_metadata_repair(title):
        metadata_title = fetch_title_from_doi_metadata(doi)
        if metadata_title and not title_needs_metadata_repair(metadata_title):
            return metadata_title
    return title


def author_tuple(names: list[str]) -> tuple[str, ...]:
    return tuple(security.normalized_person_key(name) for name in names if name)


def official_entry_authors(entry: dict[str, Any]) -> list[str]:
    authors = [
        security.clean_author_name(str(author))
        for author in entry.get("authors", [])
        if security.clean_author_name(str(author))
    ]
    if authors:
        return authors
    rows = entry.get("official_affiliations") or []
    return [
        security.clean_author_name(str(row.get("name", "")))
        for row in rows
        if isinstance(row, dict) and security.clean_author_name(str(row.get("name", "")))
    ]


def load_official_lookup(config: security.ConferenceConfig) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, ...], dict[str, Any]]]:
    entries = security.load_official_affiliation_entries(config.key)
    by_title: dict[str, dict[str, Any]] = {}
    by_authors: dict[tuple[str, ...], dict[str, Any]] = {}
    for entry in entries:
        title_key = security.official_title_key(str(entry.get("title", "")))
        if title_key:
            by_title.setdefault(title_key, entry)
        authors_key = author_tuple(official_entry_authors(entry))
        if authors_key:
            by_authors.setdefault(authors_key, entry)
    return by_title, by_authors


def find_official_entry(
    paper: dict[str, Any],
    by_title: dict[str, dict[str, Any]],
    by_authors: dict[tuple[str, ...], dict[str, Any]],
) -> dict[str, Any] | None:
    title_key = security.official_title_key(fixed_paper_title(paper))
    if title_key and title_key in by_title:
        return by_title[title_key]
    authors_key = author_tuple(raw_author_names(paper))
    if authors_key and authors_key in by_authors:
        return by_authors[authors_key]
    authors = raw_author_names(paper)
    candidates = list(by_title.values())
    best_entry = None
    best_score = 0.0
    for entry in candidates:
        entry_title = str(entry.get("title", ""))
        if not entry_title:
            continue
        score = difflib.SequenceMatcher(
            None,
            security.official_title_key(fixed_paper_title(paper)),
            security.official_title_key(entry_title),
        ).ratio()
        entry_authors = official_entry_authors(entry)
        author_overlap_ratio = 0.0
        if authors and entry_authors:
            author_keys = set(author_tuple(authors))
            entry_author_keys = set(author_tuple(entry_authors))
            author_overlap = author_keys & entry_author_keys
            if author_keys:
                author_overlap_ratio = len(author_overlap) / len(author_keys)
            if score < 0.92 and (score < 0.85 or author_overlap_ratio < 0.75):
                continue
            if not author_overlap and len(authors) > 2:
                continue
        elif score < 0.92:
            continue
        if score <= best_score:
            continue
        best_entry = entry
        best_score = score
    if best_entry:
        return best_entry
    return None


def find_local_metadata_entry(
    prefix: str,
    year: int,
    paper: dict[str, Any],
    by_title: dict[tuple[str, int, str], dict[str, Any]],
    by_authors: dict[tuple[str, int, tuple[str, ...]], dict[str, Any]],
) -> dict[str, Any] | None:
    title_key = security.official_title_key(fixed_paper_title(paper))
    if title_key and (prefix, year, title_key) in by_title:
        return by_title[(prefix, year, title_key)]
    authors_key = author_tuple(raw_author_names(paper))
    if authors_key and (prefix, year, authors_key) in by_authors:
        return by_authors[(prefix, year, authors_key)]
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build author metadata CSVs with affiliation text only, without country classification."
    )
    parser.add_argument("--generated-data-dir", type=Path, default=Path("generated-data"))
    parser.add_argument("--raw-dir", type=Path, default=None)
    parser.add_argument(
        "--seed-metadata-dir",
        type=Path,
        default=Path("generated-data"),
        help="Existing generated-data directory used as a local metadata seed in no-network mode.",
    )
    parser.add_argument(
        "--no-network",
        action="store_true",
        help="Only use official list/cache sources; do not query fallback network sources.",
    )
    parser.add_argument(
        "--official-network",
        action="store_true",
        help="Fetch conference official lists even when fallback network enrichment is disabled.",
    )
    return parser.parse_args()


def load_local_metadata_lookup(
    seed_dir: Path,
) -> tuple[dict[tuple[str, int, str], dict[str, Any]], dict[tuple[str, int, tuple[str, ...]], dict[str, Any]]]:
    by_title: dict[tuple[str, int, str], dict[str, Any]] = {}
    by_authors: dict[tuple[str, int, tuple[str, ...]], dict[str, Any]] = {}
    for prefix in CONFERENCE_PREFIXES:
        path = seed_dir / f"{prefix}_full_output" / "paper_metadata.csv"
        if not path.exists():
            continue
        grouped: dict[int, list[dict[str, str]]] = {}
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                try:
                    year = int(row.get("year", ""))
                except ValueError:
                    continue
                grouped.setdefault(year, []).append(row)
        for year, rows in grouped.items():
            title_groups: dict[str, list[dict[str, str]]] = {}
            for row in rows:
                title = clean_text(row.get("title", ""))
                if not title:
                    continue
                title_groups.setdefault(title, []).append(row)
            for title, title_rows in title_groups.items():
                ordered = sorted(title_rows, key=lambda row: int(row.get("author_rank") or 0))
                authors = [security.clean_author_name(repair_gbk_mojibake(row.get("author", ""))) for row in ordered]
                entry = {
                    "title": title,
                    "authors": authors,
                    "official_affiliations": [
                        {
                            "name": security.clean_author_name(repair_gbk_mojibake(row.get("author", ""))),
                            "affiliations": [
                                part.strip()
                                for part in clean_text(row.get("affiliations", "")).split(";")
                                if part.strip()
                            ],
                        }
                        for row in ordered
                    ],
                }
                by_title[(prefix, year, security.official_title_key(title))] = entry
                authors_key = author_tuple(authors)
                if authors_key:
                    by_authors.setdefault((prefix, year, authors_key), entry)
    return by_title, by_authors


def conference_key_parts(conference_key: str) -> tuple[str, int] | None:
    for prefix in sorted(CONFERENCE_PREFIXES, key=len, reverse=True):
        marker = f"{prefix}_"
        if conference_key.startswith(marker):
            year_text = conference_key[len(marker):]
            if year_text.isdigit():
                return prefix, int(year_text)
    return None


def paper_identity_key(paper: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    return (
        security.official_title_key(fixed_paper_title(paper, fetch_from_network=False)),
        author_tuple(raw_author_names(paper)),
    )


def official_entry_to_paper(entry: dict[str, Any], prefix: str, year: int) -> dict[str, Any]:
    title = clean_text(entry.get("title", ""))
    authors = official_entry_authors(entry)
    rows = entry.get("official_affiliations") or []
    author_rows: list[dict[str, Any]] = []
    for index, author in enumerate(authors):
        affiliations = ""
        if index < len(rows):
            affiliations = normalize_affiliations(rows[index])
        author_rows.append({"name": author, "affiliations": affiliations})
    return {
        "paperId": entry.get("paperId") or f"official/{prefix}_{year}/{security.slug_text(title)}",
        "title": title,
        "authors": author_rows or authors,
        "official_affiliations": rows,
        "url": entry.get("url", ""),
        "pages": entry.get("pages", ""),
        "doi": entry.get("doi", ""),
    }


def author_overlap_ratio(left: set[str], right: set[str]) -> float:
    if not left:
        return 0.0
    matched = 0
    used_right: set[str] = set()
    for left_name in left:
        for right_name in right:
            if right_name in used_right:
                continue
            if left_name == right_name or security.names_match(left_name, right_name):
                matched += 1
                used_right.add(right_name)
                break
    return matched / len(left)


def official_entry_already_covered(entry: dict[str, Any], papers: list[dict[str, Any]]) -> bool:
    entry_title_key = security.official_title_key(str(entry.get("title", "")))
    entry_authors = set(author_tuple(official_entry_authors(entry)))
    for paper in papers:
        paper_title_key = security.official_title_key(fixed_paper_title(paper, fetch_from_network=False))
        if entry_title_key and paper_title_key == entry_title_key:
            return True
        if not entry_authors:
            continue
        paper_authors = set(author_tuple(raw_author_names(paper)))
        if not paper_authors:
            continue
        title_score = difflib.SequenceMatcher(None, entry_title_key, paper_title_key).ratio()
        author_overlap = author_overlap_ratio(entry_authors, paper_authors)
        if author_overlap >= 0.95 and len(entry_authors) >= 2:
            return True
        if author_overlap >= 0.9 and title_score >= 0.55:
            return True
        if author_overlap >= 0.75 and title_score >= 0.7:
            return True
    return False


def append_official_only_papers(
    papers: list[dict[str, Any]],
    official_entries: list[dict[str, Any]],
    prefix: str,
    year: int,
) -> list[dict[str, Any]]:
    merged = list(papers)
    for entry in official_entries:
        if not entry.get("title") or not official_entry_authors(entry):
            continue
        if official_entry_already_covered(entry, merged):
            continue
        merged.append(official_entry_to_paper(entry, prefix, year))
    return merged


def normalize_affiliations(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, list):
        parts = [normalize_affiliations(item) for item in value]
        return "; ".join(part for part in parts if part)
    if isinstance(value, dict):
        for key in ("affiliations", "affiliation", "institution", "name", "display_name", "raw_affiliation_string"):
            text = normalize_affiliations(value.get(key))
            if text:
                return text
    return clean_text(value)


def raw_author_names(paper: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for author in paper.get("authors") or []:
        if isinstance(author, dict):
            name = security.clean_author_name(repair_gbk_mojibake(str(author.get("name") or author.get("author") or "")))
        else:
            name = security.clean_author_name(repair_gbk_mojibake(str(author)))
        if name:
            names.append(name)
    return names


def raw_affiliation_by_index(paper: dict[str, Any], index: int) -> str:
    authors = paper.get("authors") or []
    if index < len(authors) and isinstance(authors[index], dict):
        author = authors[index]
        text = normalize_affiliations(
            author.get("affiliations")
            or author.get("affiliation")
            or author.get("institution")
        )
        if text:
            return text
    official_affiliations = paper.get("official_affiliations") or []
    if index < len(official_affiliations):
        return normalize_affiliations(official_affiliations[index])
    return ""


def official_affiliations_by_author(entry: dict[str, Any] | None) -> dict[str, list[str]]:
    if not entry:
        return {}
    rows = entry.get("official_affiliations") or []
    aff_map, _pairs = security.build_affiliation_map(rows)
    return aff_map


def matched_affiliations_from_entry(entry: dict[str, Any] | None, authors: list[str]) -> list[list[str]]:
    if not entry or not authors:
        return [[] for _ in authors]
    rows = entry.get("official_affiliations") or []
    if not rows:
        return [[] for _ in authors]
    aff_map, aff_name_pairs = security.build_affiliation_map(rows)
    return security.match_author_affiliations(authors, aff_map, aff_name_pairs, None)


def affiliation_matches(
    config: security.ConferenceConfig,
    paper: dict[str, Any],
    cache_dir: Path,
    fetch_from_network: bool,
) -> list[list[str]]:
    authors = raw_author_names(paper)
    if not authors:
        return []

    rows = security.resolve_affiliations_for_paper(
        config,
        paper,
        cache_dir,
        fetch_from_network=fetch_from_network,
        author_name_aliases=None,
    )
    if not rows:
        return [[] for _ in authors]
    aff_map, aff_name_pairs = security.build_affiliation_map(rows)
    matched = security.match_author_affiliations(authors, aff_map, aff_name_pairs, None)
    if any(not affs for affs in matched):
        matched = security.fill_shared_affiliation_gaps(matched)
    return matched


def author_rows_from_paper(
    prefix: str,
    year: int,
    config: security.ConferenceConfig,
    paper: dict[str, Any],
    cache_dir: Path,
    fetch_from_network: bool,
    metadata_entries: list[dict[str, Any] | None] | None = None,
) -> list[dict[str, Any]]:
    official_entry = next((entry for entry in (metadata_entries or []) if entry and entry.get("title")), None)
    title = fixed_paper_title(paper, official_entry, fetch_from_network=fetch_from_network)
    conference = CONFERENCE_PREFIXES[prefix]
    authors = raw_author_names(paper)
    lookup_paper = dict(paper)
    if official_entry and official_entry.get("title"):
        lookup_paper["title"] = official_entry["title"]
    matched_affiliations = affiliation_matches(config, lookup_paper, cache_dir, fetch_from_network)
    entry_matches = [
        matched_affiliations_from_entry(entry, authors)
        for entry in (metadata_entries or [])
        if entry
    ]
    rows: list[dict[str, Any]] = []

    for index, author_name in enumerate(authors):
        affiliations = raw_affiliation_by_index(paper, index)
        for matches in entry_matches:
            if affiliations:
                break
            if index < len(matches):
                affiliations = "; ".join(matches[index])
        if not affiliations and index < len(matched_affiliations):
            affiliations = "; ".join(matched_affiliations[index])
        rows.append(
            {
                "year": year,
                "conference": conference,
                "title": title,
                "author": author_name,
                "author_rank": index,
                "affiliations": affiliations,
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["year", "conference", "title", "author", "author_rank", "affiliations"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    generated_data_dir = args.generated_data_dir
    raw_dir = args.raw_dir or generated_data_dir / "extraction" / "raw" / "by_conference"
    cache_dir = generated_data_dir / "extraction" / "affiliation_cache"
    grouped_rows: dict[str, list[dict[str, Any]]] = {prefix: [] for prefix in CONFERENCE_PREFIXES}
    local_by_title, local_by_authors = load_local_metadata_lookup(args.seed_metadata_dir) if args.no_network else ({}, {})

    for papers_path in sorted(raw_dir.glob("*/papers.json")):
        conference_key = papers_path.parent.name
        parts = conference_key_parts(conference_key)
        if not parts or conference_key not in security.CONFERENCES:
            continue
        prefix, year = parts
        config = security.CONFERENCES[conference_key]
        official_entries = security.load_official_affiliation_entries(config.key) if (args.official_network or not args.no_network) else []
        official_by_title, official_by_authors = load_official_lookup(config) if official_entries else ({}, {})
        papers = json.loads(papers_path.read_text(encoding="utf-8"))
        if official_entries:
            papers = append_official_only_papers(papers, official_entries, prefix, year)
        seen_papers: set[tuple[str, tuple[str, ...]]] = set()
        for paper in papers:
            if isinstance(paper, dict):
                identity_key = paper_identity_key(paper)
                if identity_key in seen_papers:
                    continue
                seen_papers.add(identity_key)
                local_entry = find_local_metadata_entry(
                    prefix,
                    year,
                    paper,
                    local_by_title,
                    local_by_authors,
                )
                official_entry = find_official_entry(paper, official_by_title, official_by_authors)
                grouped_rows[prefix].extend(
                    author_rows_from_paper(
                        prefix,
                        year,
                        config,
                        paper,
                        cache_dir,
                        fetch_from_network=not args.no_network,
                        metadata_entries=[official_entry, local_entry],
                    )
                )
        print(f"{conference_key}: done")

    for prefix, rows in grouped_rows.items():
        rows.sort(key=lambda row: (row["year"], row["title"], row["author_rank"], row["author"]))
        write_csv(generated_data_dir / f"{prefix}_full_output" / "paper_metadata.csv", rows)
        filled = sum(1 for row in rows if row["affiliations"])
        print(f"{prefix}: {len(rows)} rows, {filled} with affiliations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
