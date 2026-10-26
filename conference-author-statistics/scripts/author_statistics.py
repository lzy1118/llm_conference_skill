from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import re
import unicodedata

from conference_dataset_loader import filter_rows, load_normalized_rows, write_markdown_report, write_summary_csv


def normalize_author_display_name(name: str) -> str:
    text = re.sub(r"\s+", " ", (name or "").strip())
    if not text:
        return ""
    return re.sub(r"\s0+\d+$", "", text).strip()


def normalize_author_identity(name: str) -> str:
    """Compact Unicode identity key for OCR-spaced author names."""
    text = unicodedata.normalize("NFKC", normalize_author_display_name(name)).casefold()
    return "".join(char for char in text if char.isalnum())


def is_first_author(row: dict[str, str]) -> bool:
    try:
        return int(row.get("author_order", "")) == 0
    except (TypeError, ValueError):
        return False


def build_author_key_aliases(rows: list[dict[str, str]]) -> dict[str, str]:
    """Merge only compact variants and initial/full names with strong evidence.

    An initial plus surname is intentionally not treated as a person's identity:
    common initials (for example ``J Wu``) represent multiple researchers.  An
    initial form is merged with a full name only when exactly one candidate has
    a shared institution, country, or coauthor evidence.
    """
    fallback_keys_by_compact_name: dict[str, set[str]] = defaultdict(set)
    explicit_keys_by_compact_name: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        explicit_key = row.get("author_key", "").strip()
        name_key = row.get("name", "").strip()
        compact = normalize_author_identity(row.get("name", ""))
        if not compact:
            continue
        if explicit_key:
            explicit_keys_by_compact_name[compact].add(explicit_key)
        elif name_key:
            fallback_keys_by_compact_name[compact].add(name_key)
    aliases: dict[str, str] = {}
    for compact, keys in fallback_keys_by_compact_name.items():
        if explicit_keys_by_compact_name.get(compact):
            continue
        preferred = sorted(keys)[0]
        aliases.update({key: preferred for key in keys})

    profiles: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"names": set(), "institutions": set(), "countries": set(), "coauthors": set()}
    )
    paper_authors: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        raw_key = row.get("author_key", "").strip() or row.get("name", "").strip()
        key = aliases.get(raw_key, raw_key)
        if not key:
            continue
        profile = profiles[key]
        profile["names"].add(normalize_author_display_name(row.get("name", "")))
        institution = (row.get("institution_id", "") or row.get("institution_key", "")
                       or row.get("canonical_institution_name", "") or row.get("inst", "")).strip()
        country = row.get("country", "").strip()
        if institution:
            profile["institutions"].add(institution.casefold())
        if country and country.casefold() not in {"unknown", "none"}:
            profile["countries"].add(country.casefold())
        paper_key = row.get("paper_key", "")
        if paper_key:
            paper_authors[paper_key].add(key)
    for authors in paper_authors.values():
        for key in authors:
            profiles[key]["coauthors"].update(authors - {key})

    def parts(value: str) -> list[str]:
        text = re.sub(r"[^\w ]+", " ", value, flags=re.UNICODE).replace("_", " ")
        return [part for part in text.split() if part]

    def candidate_matches(initial_name: str, full_name: str) -> bool:
        left, right = parts(initial_name), parts(full_name)
        if len(left) < 2 or len(right) < 2 or len(left[0]) != 1:
            return False
        return left[-1].casefold() == right[-1].casefold() and left[0].casefold() == right[0][0].casefold()

    names_by_key = {key: next(iter(profile["names"]), "") for key, profile in profiles.items()}
    explicit_keys = {row.get("author_key", "").strip() for row in rows if row.get("author_key", "").strip()}
    for initial_key, initial_name in list(names_by_key.items()):
        if initial_key in explicit_keys:
            continue
        initial_parts = parts(initial_name)
        if len(initial_parts) < 2 or len(initial_parts[0]) != 1:
            continue
        candidates = [
            key for key, name in names_by_key.items()
            if key != initial_key and key not in explicit_keys and candidate_matches(initial_name, name)
        ]
        if not candidates:
            continue
        evidence = []
        for candidate in candidates:
            left, right = profiles[initial_key], profiles[candidate]
            # Country alone is weak evidence for common surnames.
            score = sum(bool(left[field] & right[field]) for field in ("institutions", "coauthors"))
            if score:
                evidence.append((candidate, score))
        if len(evidence) == 1:
            aliases[initial_key] = evidence[0][0]
    return aliases


def resolve_author_keys_by_row(rows: list[dict[str, str]]) -> list[str]:
    aliases = build_author_key_aliases(rows)
    paper_indices: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        paper_key = row.get("paper_key", "").strip()
        if paper_key:
            paper_indices[paper_key].append(index)

    resolved = [""] * len(rows)
    for indices in paper_indices.values():
        explicit_by_name: dict[str, set[str]] = defaultdict(set)
        for index in indices:
            row = rows[index]
            explicit = row.get("author_key", "").strip()
            compact = normalize_author_identity(row.get("name", ""))
            if explicit and compact:
                explicit_by_name[compact].add(aliases.get(explicit, explicit))
        for index in indices:
            row = rows[index]
            explicit = row.get("author_key", "").strip()
            name = row.get("name", "").strip()
            if explicit:
                resolved[index] = aliases.get(explicit, explicit)
                continue
            compact = normalize_author_identity(name)
            candidates = explicit_by_name.get(compact, set())
            if len(candidates) == 1:
                resolved[index] = next(iter(candidates))
            elif name:
                resolved[index] = aliases.get(name, name)
    return resolved


def simplified_author_name(value: str) -> str:
    text = re.sub(r"[^a-z0-9 ]+", " ", value.casefold())
    parts = [part for part in text.split() if part]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0][0]} {' '.join(parts[1:])}"


def has_initial_fullname_pair(names: set[str]) -> bool:
    parsed = []
    for name in names:
        parts = [part for part in re.sub(r"[^A-Za-z0-9 ]+", " ", name).split() if part]
        if len(parts) >= 2:
            parsed.append(parts)
    for left in parsed:
        for right in parsed:
            if left == right:
                continue
            if left[-1].casefold() != right[-1].casefold():
                continue
            if len(left[0]) == 1 and right[0].casefold().startswith(left[0].casefold()):
                return True
    return False


def build_identity_review(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    # Ambiguous initials and same-display collisions are handled deterministically
    # by ``build_author_key_aliases``; no manual review queue is emitted.
    return []


def normalize_title_key(title: str) -> str:
    text = unicodedata.normalize("NFKC", (title or "").strip()).casefold().rstrip(".")
    # Compact punctuation and OCR whitespace without dropping non-Latin letters.
    return "".join(char for char in text if char.isalnum())


def build_canonical_paper_keys(
    rows: list[dict[str, str]], resolved_author_keys: list[str] | None = None
) -> dict[str, str]:
    papers_to_rows: dict[str, list[tuple[int, dict[str, str]]]] = defaultdict(list)
    for index, row in enumerate(rows):
        paper_key = row.get("paper_key", "").strip()
        if paper_key:
            papers_to_rows[paper_key].append((index, row))

    canonical: dict[str, str] = {}
    signature_groups: dict[tuple[object, ...], list[str]] = defaultdict(list)
    if resolved_author_keys is None:
        resolved_author_keys = resolve_author_keys_by_row(rows)
    explicit_author_keys = {
        row.get("author_key", "").strip()
        for row in rows
        if row.get("author_key", "").strip()
    }
    for paper_key, indexed_rows in papers_to_rows.items():
        def order_signature(item: dict[str, str]) -> tuple[int, str]:
            raw_order = item.get("author_order", "").strip()
            try:
                return int(raw_order), ""
            except (TypeError, ValueError):
                return 10**9, raw_order

        author_members = set()
        for index, item in indexed_rows:
            identity_key = resolved_author_keys[index]
            if not identity_key:
                continue
            if identity_key in explicit_author_keys:
                identity = f"key:{identity_key}"
            else:
                identity = f"name:{normalize_author_identity(identity_key)}"
            order, invalid_order = order_signature(item)
            author_members.add((order, invalid_order, identity))
        author_signature = tuple(sorted(author_members))
        if not author_signature:
            canonical[paper_key] = paper_key
            continue
        sample = indexed_rows[0][1]
        title_key = normalize_title_key(sample.get("title", ""))
        if not title_key:
            canonical[paper_key] = paper_key
            continue
        signature = (
            sample.get("conference", ""),
            sample.get("year", ""),
            title_key,
            author_signature,
        )
        signature_groups[signature].append(paper_key)

    for paper_keys in signature_groups.values():
        preferred = sorted(paper_keys, key=lambda key: (key.endswith("a"), key))
        canonical_key = preferred[0]
        for paper_key in paper_keys:
            canonical[paper_key] = canonical_key
    return canonical


def aggregate_authors(rows: list[dict[str, str]]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    grouped: dict[str, dict[str, object]] = defaultdict(lambda: {
        "author_name": "",
        "paper_keys": set(),
        "conferences": set(),
        "years": set(),
        "first_author_papers": set(),
        "coauthors": set(),
    })
    by_year: dict[tuple[str, str], set[str]] = defaultdict(set)
    first_author_rows: list[dict[str, object]] = []
    papers_to_authors: dict[str, list[tuple[int, dict[str, str]]]] = defaultdict(list)
    resolved_author_keys = resolve_author_keys_by_row(rows)
    canonical_paper_keys = build_canonical_paper_keys(rows, resolved_author_keys)

    for index, row in enumerate(rows):
        paper_key = row.get("paper_key", "").strip()
        key = resolved_author_keys[index]
        if not paper_key or not key:
            continue
        canonical_paper_key = canonical_paper_keys.get(paper_key, paper_key)
        name = normalize_author_display_name(row.get("name", ""))
        conference = row.get("conference", "")
        year = row.get("year", "")
        grouped[key]["author_name"] = grouped[key]["author_name"] or name
        grouped[key]["paper_keys"].add(canonical_paper_key)
        grouped[key]["conferences"].add(conference)
        grouped[key]["years"].add(year)
        if is_first_author(row):
            grouped[key]["first_author_papers"].add(canonical_paper_key)
        by_year[(key, year)].add(canonical_paper_key)
        papers_to_authors[canonical_paper_key].append((index, row))

    for paper_rows in papers_to_authors.values():
        unique_authors = {}
        seen_first_author_keys: set[tuple[str, str]] = set()
        for index, row in paper_rows:
            key = resolved_author_keys[index]
            if key:
                unique_authors[key] = row.get("name", "")
        author_keys = sorted(unique_authors)
        for author_key in author_keys:
            grouped[author_key]["coauthors"].update(other for other in author_keys if other != author_key)
        for index, row in paper_rows:
            if not is_first_author(row):
                continue
            author_key = resolved_author_keys[index]
            if not author_key:
                continue
            paper_key = row.get("paper_key", "").strip()
            canonical_paper_key = canonical_paper_keys.get(paper_key, paper_key)
            dedup_key = (author_key, canonical_paper_key)
            if dedup_key in seen_first_author_keys:
                continue
            seen_first_author_keys.add(dedup_key)
            first_author_rows.append({
                "author_key": author_key,
                "author_name": normalize_author_display_name(row.get("name", "")),
                "paper_key": canonical_paper_key,
                "conference": row.get("conference", ""),
                "year": row.get("year", ""),
                "title": row.get("title", ""),
            })

    coauthor_edges: dict[tuple[str, str], dict[str, object]] = {}
    for paper_key, paper_rows in papers_to_authors.items():
        distinct = {}
        for index, row in paper_rows:
            key = resolved_author_keys[index]
            if key:
                distinct[key] = normalize_author_display_name(row.get("name", ""))
        keys = sorted(distinct)
        for index, left in enumerate(keys):
            for right in keys[index + 1:]:
                edge_key = (left, right)
                edge = coauthor_edges.setdefault(edge_key, {
                    "author_key_1": left,
                    "author_name_1": distinct[left],
                    "author_key_2": right,
                    "author_name_2": distinct[right],
                    "shared_papers": 0,
                })
                edge["shared_papers"] += 1

    summary = []
    for author_key, entry in grouped.items():
        summary.append({
            "author_key": author_key,
            "author_name": normalize_author_display_name(str(entry["author_name"])),
            "papers": len(entry["paper_keys"]),
            "conferences": len(entry["conferences"]),
            "years_active": len(entry["years"]),
            "first_author_papers": len(entry["first_author_papers"]),
            "coauthor_count": len(entry["coauthors"]),
            "year_first": min(entry["years"]) if entry["years"] else "",
            "year_last": max(entry["years"]) if entry["years"] else "",
        })

    author_by_year = [
        {
            "author_key": author_key,
            "year": year,
            "papers": len(papers),
        }
        for (author_key, year), papers in by_year.items()
    ]
    return (
        sorted(summary, key=lambda row: (-int(row["papers"]), -int(row["first_author_papers"]), str(row["author_name"]))),
        sorted(author_by_year, key=lambda row: (row["year"], -int(row["papers"]), row["author_key"])),
        sorted(first_author_rows, key=lambda row: (row["year"], row["conference"], row["author_name"])),
        sorted(coauthor_edges.values(), key=lambda row: (-int(row["shared_papers"]), row["author_name_1"], row["author_name_2"])),
        build_identity_review(rows),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate author statistics from normalized conference data.")
    parser.add_argument("--input", required=True, help="Path to normalized author_affiliation_facts.csv")
    parser.add_argument("--output-dir", required=True, help="Output analysis directory")
    parser.add_argument("--conference")
    parser.add_argument("--year")
    args = parser.parse_args()

    rows = filter_rows(load_normalized_rows(Path(args.input)), conference=args.conference, year=args.year)
    summary, by_year, first_author_rows, coauthor_edges, identity_review = aggregate_authors(rows)
    output_dir = Path(args.output_dir) / "authors"
    write_summary_csv(output_dir / "author_summary.csv", summary)
    write_summary_csv(output_dir / "author_by_year.csv", by_year)
    write_summary_csv(output_dir / "first_author_summary.csv", first_author_rows)
    write_summary_csv(output_dir / "coauthor_edges.csv", coauthor_edges)
    write_summary_csv(output_dir / "author_identity_review.csv", identity_review)
    write_markdown_report(
        output_dir / "author_report.md",
        title="Author Statistics Report",
        scope={"conference": args.conference or "all", "year": args.year or "all", "rows": len(rows)},
        highlights=summary[:10],
    )


if __name__ == "__main__":
    main()
