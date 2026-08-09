from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
import re


def normalize_author_display_name(name: str) -> str:
    text = re.sub(r"\s+", " ", (name or "").strip())
    if not text:
        return ""
    return re.sub(r"\s0+\d+$", "", text).strip()


def normalize_author_identity(name: str) -> str:
    """Compact identity key for OCR-inserted spaces in author names."""
    return re.sub(r"[^a-z0-9]", "", normalize_author_display_name(name).casefold())


def normalize_institution_display_name(row: dict[str, str]) -> str:
    value = row.get("canonical_institution_name") or row.get("inst") or ""
    text = re.sub(r"^[|;]+\s*|\s*[|;]+$", "", value.replace("&amp;", "&").strip())
    return re.sub(r"\s+", " ", text)


def split_composite_name(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s*[|;]\s*", value or "") if part.strip()]


def expand_resolved_country_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Expand known country components and discard unresolved fragments."""
    candidates: dict[str, set[str]] = defaultdict(set)
    institution_country_candidates: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        components = split_composite_name(row.get("country", ""))
        if len(components) == 1 and components[0].casefold() not in {"", "unknown"}:
            candidates[components[0].casefold()].add(components[0])
            identities = split_composite_name(row.get("institution_id", "") or row.get("institution_key", ""))
            if len(identities) == 1:
                institution_country_candidates[identities[0]].add(components[0])
    registry = {key: next(iter(values)) for key, values in candidates.items() if len(values) == 1}
    institution_country_registry = {
        identity: next(iter(values))
        for identity, values in institution_country_candidates.items()
        if len(values) == 1
    }
    expanded: list[dict[str, str]] = []
    for row in rows:
        components = split_composite_name(row.get("country", ""))
        if len(components) < 2:
            expanded.append(row)
            continue
        resolved = [registry.get(component.casefold()) for component in components]
        resolved = [component for component in resolved if component]
        if not resolved:
            continue
        institution_names = split_composite_name(normalize_institution_display_name(row))
        institution_ids = split_composite_name(row.get("institution_id", "") or row.get("institution_key", ""))
        aligned_institutions = len(institution_names) == len(components) and len(institution_names) > 1
        if not aligned_institutions and len(institution_ids) == 1:
            canonical_country = institution_country_registry.get(institution_ids[0])
            if canonical_country:
                split_row = dict(row)
                split_row["country"] = canonical_country
                split_row["country_source"] = "resolved_institution_country"
                expanded.append(split_row)
            continue
        for country in dict.fromkeys(resolved):
            split_row = dict(row)
            split_row["country"] = country
            split_row["country_source"] = "resolved_composite_component"
            expanded.append(split_row)
    return expanded


def institution_name_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def is_authoritative_institution_identity(value: str) -> bool:
    identity = (value or "").strip()
    return bool(
        re.fullmatch(r"https?://ror\.org/[0-9a-z]+", identity, flags=re.IGNORECASE)
        or re.fullmatch(r"INST\d+", identity, flags=re.IGNORECASE)
        or re.fullmatch(r"institution:[0-9a-f]{8,}", identity, flags=re.IGNORECASE)
    )


def expand_resolved_composite_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Expand auditable composite affiliations for institution participation edges."""
    candidates: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in rows:
        display = normalize_institution_display_name(row)
        if len(split_composite_name(display)) != 1:
            continue
        identity = (row.get("institution_id", "") or row.get("institution_key", "")).strip()
        if not display or len(split_composite_name(identity)) != 1:
            continue
        candidates[institution_name_key(display)][identity] = {
            "institution_key": row.get("institution_key", ""),
            "institution_id": row.get("institution_id", ""),
            "institution_name": display,
            "country": row.get("country", ""),
        }

    registry = {
        name_key: next(iter(identities.values()))
        for name_key, identities in candidates.items()
        if len(identities) == 1
    }
    expanded: list[dict[str, str]] = []
    for row in rows:
        display = normalize_institution_display_name(row)
        components = split_composite_name(display)
        if len(components) < 2:
            identity_values = split_composite_name(
                row.get("institution_id", "") or row.get("institution_key", "")
            )
            if len(identity_values) > 1:
                component = registry.get(institution_name_key(display))
                if component is None:
                    continue
                split_row = dict(row)
                split_row["institution_key"] = component["institution_key"]
                split_row["institution_id"] = component["institution_id"]
                split_row["inst"] = component["institution_name"]
                split_row["canonical_institution_name"] = component["institution_name"]
                split_row["country"] = component["country"] or row.get("country", "")
                split_row["institution_source"] = "resolved_participation_component"
                expanded.append(split_row)
                continue
            expanded.append(row)
            continue
        identity_values = split_composite_name(
            row.get("institution_id", "") or row.get("institution_key", "")
        )
        if len(identity_values) == len(components):
            resolved = []
            for component, identity in zip(components, identity_values):
                known = registry.get(institution_name_key(component))
                if known and identity in {known["institution_id"], known["institution_key"]}:
                    resolved.append(known)
                elif is_authoritative_institution_identity(identity):
                    resolved.append({
                        "institution_key": identity,
                        "institution_id": identity,
                        "institution_name": component,
                        "country": row.get("country", ""),
                    })
                else:
                    resolved.append(None)
        else:
            resolved = [registry.get(institution_name_key(component)) for component in components]
        if not any(component is not None for component in resolved):
            # A fully unresolved composite is only an affiliation fragment.
            continue
        if any(component is None for component in resolved):
            # Keep known institutions and discard only the unresolved fragments.
            resolved = [component for component in resolved if component is not None]
        if not resolved:
            expanded.append(row)
            continue
        for component in resolved:
            split_row = dict(row)
            split_row["institution_key"] = component["institution_key"]
            split_row["institution_id"] = component["institution_id"]
            split_row["inst"] = component["institution_name"]
            split_row["canonical_institution_name"] = component["institution_name"]
            split_row["country"] = component["country"] or row.get("country", "")
            split_row["institution_source"] = "resolved_participation_component"
            expanded.append(split_row)
    return expanded


def build_author_key_aliases(rows: list[dict[str, str]]) -> dict[str, str]:
    compact_to_keys: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        key = row.get("author_key", "").strip() or row.get("name", "").strip()
        compact = normalize_author_identity(row.get("name", ""))
        if key and compact:
            compact_to_keys[compact].add(key)
    aliases: dict[str, str] = {}
    for keys in compact_to_keys.values():
        preferred = sorted(keys)[0]
        aliases.update({key: preferred for key in keys})
    return aliases


MODE_CHOICES = ("author", "country", "institution")
NON_COUNTING_INSTITUTION_SOURCES = {
    "secondary_unit_only",
    "unresolved_composite_fragment",
    "independent_researcher_default",
}


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def validate_input_rows(
    rows: list[dict[str, str]],
    mode: str,
    *,
    require_conference: bool = False,
    require_year: bool = False,
) -> None:
    if not rows:
        raise ValueError("Input fact table is empty")
    columns = set(rows[0])
    missing = {"paper_key"} - columns
    if require_conference:
        missing |= {"conference"} - columns
    if require_year:
        missing |= {"year"} - columns
    alternatives = {
        "author": ({"author_key", "name"}, "author_key or name"),
        "country": ({"country"}, "country"),
        "institution": ({"institution_key", "inst"}, "institution_key or inst"),
    }
    accepted, label = alternatives[mode]
    if not columns.intersection(accepted):
        missing.add(label)
    if missing:
        raise ValueError(f"Input fact table is missing required columns: {sorted(missing)}")


def filter_rows(
    rows: list[dict[str, str]],
    conference: str | None,
    year: str | None,
    year_start: int | None = None,
    year_end: int | None = None,
) -> list[dict[str, str]]:
    filtered = rows
    if conference:
        conference_key = conference.strip().casefold()
        filtered = [row for row in filtered if row.get("conference", "").strip().casefold() == conference_key]
    if year:
        filtered = [row for row in filtered if row.get("year", "").strip() == str(year).strip()]
    if year_start is not None:
        filtered = [
            row
            for row in filtered
            if row.get("year", "").strip().isdigit() and int(row["year"].strip()) >= year_start
        ]
    if year_end is not None:
        filtered = [
            row
            for row in filtered
            if row.get("year", "").strip().isdigit() and int(row["year"].strip()) <= year_end
        ]
    return filtered


def node_for_mode(row: dict[str, str], mode: str, author_key_aliases: dict[str, str] | None = None) -> tuple[str, str]:
    if mode == "author":
        raw_key = row.get("author_key") or row.get("name") or "Unknown"
        key = (author_key_aliases or {}).get(raw_key, raw_key)
        return key, normalize_author_display_name(row.get("name") or key)
    if mode == "country":
        key = row.get("country") or "Unknown"
        return key, key
    key = row.get("institution_id") or row.get("institution_key") or row.get("inst") or "Unknown"
    return key, row.get("inst") or key


def normalize_title_key(title: str) -> str:
    text = re.sub(r"\s+", " ", (title or "").strip().casefold()).rstrip(".")
    return re.sub(r"[^a-z0-9]", "", text)


def build_canonical_paper_keys(rows: list[dict[str, str]]) -> dict[str, str]:
    papers_to_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        paper_key = row.get("paper_key", "")
        if paper_key:
            papers_to_rows[paper_key].append(row)

    canonical: dict[str, str] = {}
    signature_groups: dict[tuple[object, ...], list[str]] = defaultdict(list)
    for paper_key, paper_rows in papers_to_rows.items():
        def order_value(item: dict[str, str]) -> int:
            try:
                return int(item.get("author_order", ""))
            except (TypeError, ValueError):
                return 10**9

        author_signature = tuple(
            (str(item.get("author_order", "")), normalize_author_identity(item.get("name", "")))
            for item in sorted(paper_rows, key=order_value)
        )
        sample = paper_rows[0]
        signature = (
            sample.get("conference", ""),
            sample.get("year", ""),
            normalize_title_key(sample.get("title", "")),
            author_signature,
        )
        signature_groups[signature].append(paper_key)

    for paper_keys in signature_groups.values():
        preferred = sorted(paper_keys, key=lambda key: (key.endswith("a"), key))
        canonical_key = preferred[0]
        for paper_key in paper_keys:
            canonical[paper_key] = canonical_key
    return canonical


def aggregate_edges(rows: list[dict[str, str]], mode: str) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    paper_nodes: dict[str, dict[str, tuple[str, str]]] = defaultdict(dict)
    paper_meta: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"conferences": set(), "years": set()})
    edge_stats: dict[tuple[str, str], dict[str, object]] = {}
    canonical_paper_keys = build_canonical_paper_keys(rows)
    if mode == "institution":
        rows = expand_resolved_composite_rows(rows)
    elif mode == "country":
        rows = expand_resolved_country_rows(rows)
    author_key_aliases = build_author_key_aliases(rows)

    for row in rows:
        if mode == "institution":
            if row.get("institution_source") in NON_COUNTING_INSTITUTION_SOURCES:
                continue
            if not (row.get("institution_id") or row.get("institution_key") or row.get("inst")):
                continue
        elif mode == "country" and not row.get("country", "").strip():
            continue
        paper_key = canonical_paper_keys.get(row.get("paper_key", ""), row.get("paper_key", ""))
        if not paper_key:
            continue
        node_key, node_name = node_for_mode(row, mode, author_key_aliases)
        paper_nodes[paper_key][node_key] = (node_key, node_name)
        conference = row.get("conference", "")
        year = row.get("year", "")
        if conference:
            paper_meta[paper_key]["conferences"].add(conference)
        if year:
            paper_meta[paper_key]["years"].add(year)

    for paper_key, nodes_map in paper_nodes.items():
        nodes = [nodes_map[key] for key in sorted(nodes_map)]
        if len(nodes) < 2:
            continue
        conferences = paper_meta[paper_key]["conferences"]
        years = paper_meta[paper_key]["years"]
        for index, (left_key, left_name) in enumerate(nodes):
            for right_key, right_name in nodes[index + 1 :]:
                edge_key = (left_key, right_key)
                edge = edge_stats.setdefault(
                    edge_key,
                    {
                        "mode": mode,
                        "left_key": left_key,
                        "left_name": left_name,
                        "right_key": right_key,
                        "right_name": right_name,
                        "shared_papers": 0,
                        "conferences": set(),
                        "years": set(),
                    },
                )
                edge["shared_papers"] += 1
                edge["conferences"].update(conferences)
                edge["years"].update(years)

    edge_rows: list[dict[str, object]] = []
    nodes_all = set()
    repeated_edge_count = 0
    max_shared_papers = 0
    for edge in edge_stats.values():
        nodes_all.add(str(edge["left_key"]))
        nodes_all.add(str(edge["right_key"]))
        shared = int(edge["shared_papers"])
        if shared > 1:
            repeated_edge_count += 1
        max_shared_papers = max(max_shared_papers, shared)
        years = sorted(str(year) for year in edge["years"] if year)
        edge_rows.append(
            {
                "mode": edge["mode"],
                "left_key": edge["left_key"],
                "left_name": edge["left_name"],
                "right_key": edge["right_key"],
                "right_name": edge["right_name"],
                "shared_papers": shared,
                "conference_count": len(edge["conferences"]),
                "year_first": years[0] if years else "",
                "year_last": years[-1] if years else "",
            }
        )

    summary_rows = [
        {
            "mode": mode,
            "paper_count": len(paper_nodes),
            "node_count": len(nodes_all),
            "edge_count": len(edge_rows),
            "repeated_edge_count": repeated_edge_count,
            "max_shared_papers": max_shared_papers,
        }
    ]
    return (
        sorted(edge_rows, key=lambda row: (-int(row["shared_papers"]), str(row["left_name"]), str(row["right_name"]))),
        summary_rows,
    )


def write_report(
    path: Path,
    mode: str,
    conference: str | None,
    year: str | None,
    year_start: int | None,
    year_end: int | None,
    summary: list[dict[str, object]],
    edges: list[dict[str, object]],
) -> None:
    lines = [
        "# Conference Collaboration Analysis Report",
        "",
        "## Scope",
        "",
        f"- mode: {mode}",
        f"- conference: {conference or 'all'}",
        f"- year: {year or 'all'}",
        f"- year_start: {year_start if year_start is not None else 'all'}",
        f"- year_end: {year_end if year_end is not None else 'all'}",
        "- composite_participation: split known institution or country components; discard unresolved fragments",
        "",
        "## Highlights",
        "",
    ]
    if summary:
        row = summary[0]
        lines.append(f"- papers: {row['paper_count']}")
        lines.append(f"- nodes: {row['node_count']}")
        lines.append(f"- edges: {row['edge_count']}")
        lines.append(f"- repeated_edges: {row['repeated_edge_count']}")
    for edge in edges[:10]:
        lines.append(f"- {edge['left_name']} <-> {edge['right_name']}: shared_papers={edge['shared_papers']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate collaboration edge tables from normalized conference data.")
    parser.add_argument("--input", required=True, help="Path to normalized author_affiliation_facts.csv")
    parser.add_argument("--output-dir", required=True, help="Output analysis directory root")
    parser.add_argument("--mode", required=True, choices=MODE_CHOICES, help="Collaboration mode")
    parser.add_argument("--conference")
    parser.add_argument("--year")
    parser.add_argument("--year-start", type=int)
    parser.add_argument("--year-end", type=int)
    args = parser.parse_args()

    if args.year and (args.year_start is not None or args.year_end is not None):
        parser.error("--year cannot be combined with --year-start or --year-end")
    if args.year_start is not None and args.year_end is not None and args.year_start > args.year_end:
        parser.error("--year-start must be less than or equal to --year-end")

    all_rows = read_rows(Path(args.input))
    try:
        validate_input_rows(
            all_rows,
            args.mode,
            require_conference=bool(args.conference),
            require_year=bool(args.year or args.year_start is not None or args.year_end is not None),
        )
    except ValueError as exc:
        parser.error(str(exc))

    rows = filter_rows(
        all_rows,
        args.conference,
        args.year,
        args.year_start,
        args.year_end,
    )
    if not rows:
        parser.error("No input rows matched the requested conference and year scope")
    edges, summary = aggregate_edges(rows, args.mode)
    output_dir = Path(args.output_dir) / "collaboration"
    write_rows(output_dir / "collaboration_edges.csv", edges)
    write_rows(output_dir / "collaboration_summary.csv", summary)
    write_report(
        output_dir / "collaboration_report.md",
        args.mode,
        args.conference,
        args.year,
        args.year_start,
        args.year_end,
        summary,
        edges,
    )


if __name__ == "__main__":
    main()
