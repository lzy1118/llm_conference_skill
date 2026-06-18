from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
import re

from analytics_common import (
    choose_display_name,
    clean_institution_label,
    ensure_directory,
    infer_country,
    normalize_author_key,
    normalize_institution_key,
    normalize_paper_key,
    normalize_whitespace,
    read_csv_rows,
    split_institutions,
    stable_key,
    write_csv_rows,
    write_json,
)


DEFAULT_OUTPUT_ROOT = Path("generated-data")


CANONICAL_FIELDS = {
    "author": "name",
    "author_name": "name",
    "institution": "inst",
    "affiliation": "inst",
    "venue": "conference",
    "conf": "conference",
    "paper_title": "title",
    "position": "author_order",
}


def csv_row_get(row: dict[str, str], *keys: str) -> str:
    normalized = {
        normalize_whitespace(key).lstrip("\ufeff").strip('"'): value
        for key, value in row.items()
    }
    for key in keys:
        if key in normalized:
            return normalized[key]
    return ""


def load_reference_institutions() -> tuple[dict[str, str], dict[str, dict[str, str]], set[str]]:
    root = Path(__file__).resolve().parents[2]
    alias_path = root / "conference-dataset-normalization" / "references" / "institution_aliases.csv"
    registry_path = root / "conference-dataset-normalization" / "references" / "institution_registry.csv"
    alias_to_id: dict[str, str] = {}
    registry_by_id: dict[str, dict[str, str]] = {}
    reference_names: set[str] = set()

    if registry_path.exists():
        with registry_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                institution_id = normalize_whitespace(csv_row_get(row, "institution_id"))
                if not institution_id:
                    continue
                canonical_name = normalize_whitespace(csv_row_get(row, "canonical_name"))
                registry_by_id[institution_id] = {
                    "canonical_name": canonical_name,
                    "country": normalize_whitespace(csv_row_get(row, "country")),
                    "region": normalize_whitespace(csv_row_get(row, "region")),
                    "type": normalize_whitespace(csv_row_get(row, "type")),
                }
                if canonical_name:
                    reference_names.add(canonical_name.casefold())

    if alias_path.exists():
        with alias_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                alias = normalize_whitespace(csv_row_get(row, "alias"))
                institution_id = normalize_whitespace(csv_row_get(row, "institution_id"))
                if alias and institution_id:
                    alias_to_id[alias.casefold()] = institution_id
                    reference_names.add(alias.casefold())

    for institution_id, registry_row in registry_by_id.items():
        canonical_name = registry_row.get("canonical_name", "")
        if canonical_name:
            alias_to_id.setdefault(canonical_name.casefold(), institution_id)
    return alias_to_id, registry_by_id, reference_names


PARENT_COLLAPSE_TYPES = {
    "university",
    "research institute",
}
PARENT_COLLAPSE_EXACT_IDS = {
    "INST0035",  # Chinese Academy of Sciences
    "INST0094",  # University of Chinese Academy of Sciences
}
PARENT_COLLAPSE_SHORT_ALIASES = {
    "uestc",
}
SUBUNIT_PARENT_OVERRIDES = {
    "INST0022": "INST0035",  # Academy of Mathematics and Systems Science -> CAS
    "INST0052": "INST0035",  # Institute of Computing Technology -> CAS
    "INST0053": "INST0035",  # Institute of Information Engineering -> CAS
    "INST0054": "INST0035",  # Institute of Software -> CAS
    "INST0058": "INST0035",  # Key Laboratory ... IIE, CAS -> CAS
    "INST0084": "INST0035",  # State Key Lab of Processors, ICT, CAS -> CAS
    "INST0835": "INST0035",  # State Key Laboratory of Information Security... -> CAS
    "INST0063": "INST0094",  # National Computer Network Intrusion Protection Center, UCAS -> UCAS
    "INST0829": "INST0095",  # School of Information, UESTC -> UESTC
}

LEADING_ARTICLE_PATTERN = re.compile(r"^(?:the)\s+", re.IGNORECASE)


def build_parent_alias_candidates(
    alias_to_id: dict[str, str],
    registry_by_id: dict[str, dict[str, str]],
) -> list[tuple[str, str]]:
    candidates: dict[str, str] = {}
    explicit_parent_ids = set(PARENT_COLLAPSE_EXACT_IDS) | set(SUBUNIT_PARENT_OVERRIDES.values())
    for alias, institution_id in alias_to_id.items():
        registry_row = registry_by_id.get(institution_id, {})
        institution_type = normalize_whitespace(registry_row.get("type", ""))
        if institution_id in SUBUNIT_PARENT_OVERRIDES:
            continue
        if institution_type == "university":
            pass
        elif institution_id in explicit_parent_ids:
            pass
        elif institution_id in PARENT_COLLAPSE_EXACT_IDS and institution_type in PARENT_COLLAPSE_TYPES:
            pass
        else:
            continue
        if len(alias) < 8 and alias not in PARENT_COLLAPSE_SHORT_ALIASES:
            continue
        candidates.setdefault(alias, institution_id)
    return sorted(candidates.items(), key=lambda item: (-len(item[0]), item[0]))


def build_institution_lookup_candidates(institution: str) -> list[str]:
    text = normalize_whitespace(institution)
    if not text:
        return []
    variants = [
        text,
        clean_institution_label(text),
        LEADING_ARTICLE_PATTERN.sub("", text),
        clean_institution_label(LEADING_ARTICLE_PATTERN.sub("", text)),
    ]
    ordered: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        normalized = normalize_whitespace(variant).strip(" ,;")
        if not normalized:
            continue
        marker = normalized.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        ordered.append(normalized)
    return ordered


def resolve_institution_id(institution: str, alias_to_id: dict[str, str]) -> tuple[str, str]:
    for candidate in build_institution_lookup_candidates(institution):
        institution_id = alias_to_id.get(candidate.casefold(), "")
        if institution_id:
            return institution_id, candidate
    return "", normalize_whitespace(institution)


def collapse_to_parent_institution(
    institution: str,
    institution_id: str,
    registry_by_id: dict[str, dict[str, str]],
    parent_alias_candidates: list[tuple[str, str]],
) -> tuple[str, str]:
    text = normalize_whitespace(institution)
    if not text:
        return institution_id, text
    override_parent_id = SUBUNIT_PARENT_OVERRIDES.get(institution_id, "")
    if override_parent_id:
        parent_row = registry_by_id.get(override_parent_id, {})
        parent_name = normalize_whitespace(parent_row.get("canonical_name", ""))
        if parent_name:
            return override_parent_id, parent_name
    lowered = text.casefold()
    for alias, parent_id in parent_alias_candidates:
        if alias == lowered:
            continue
        if alias not in lowered:
            continue
        parent_row = registry_by_id.get(parent_id, {})
        parent_name = normalize_whitespace(parent_row.get("canonical_name", ""))
        if not parent_name:
            continue
        return parent_id, parent_name
    return institution_id, text


def recover_conference_and_title(article_tag: str) -> tuple[str, str]:
    normalized_tag = normalize_whitespace(article_tag)
    if not normalized_tag or "-" not in normalized_tag:
        return "", ""
    conference, title = normalized_tag.split("-", 1)
    return normalize_whitespace(conference), normalize_whitespace(title)


def remap_row(row: dict[str, str]) -> dict[str, str]:
    remapped: dict[str, str] = {}
    for key, value in row.items():
        normalized_key = CANONICAL_FIELDS.get(key.strip().lower(), key.strip().lower())
        remapped[normalized_key] = value
    return remapped


FRAGMENT_MERGE_RULES: list[tuple[str, str, str]] = [
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
    "Development",
    "Software",
}
ALWAYS_DROP_FRAGMENT_LABELS = {
    "Development",
}
IDENTIFIER_NOISE_PATTERN = re.compile(r"^\d{4}[-−]\d{4}[-−]\d{4}[-−][\dXx]{4}$")


def merge_fragmented_affiliation_parts(first: str, second: str) -> str | None:
    normalized_first = normalize_whitespace(first)
    normalized_second = normalize_whitespace(second)
    for prefix, continuation, merged_prefix in FRAGMENT_MERGE_RULES:
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


def looks_like_author_token_affiliation(author: str, inst: str) -> bool:
    normalized_author = normalize_whitespace(author)
    normalized_inst = normalize_whitespace(inst)
    if not normalized_author or not normalized_inst:
        return False
    if any(marker in normalized_inst for marker in [",", ";", "&", " and ", "/"]):
        return False
    inst_tokens = normalized_inst.casefold().split()
    author_tokens = normalized_author.casefold().split()
    if len(inst_tokens) != 1 or len(author_tokens) < 3:
        return False
    return inst_tokens[0] in author_tokens


def looks_like_identifier_noise(inst: str) -> bool:
    normalized_inst = normalize_whitespace(inst)
    if not normalized_inst:
        return False
    if IDENTIFIER_NOISE_PATTERN.fullmatch(normalized_inst):
        return True
    compact = normalized_inst.replace("-", "").replace("−", "")
    return compact.isdigit() and len(compact) >= 12


def should_drop_generic_fragment_affiliation(inst: str, sibling_institutions: list[str]) -> bool:
    normalized_inst = normalize_whitespace(inst)
    if normalized_inst in ALWAYS_DROP_FRAGMENT_LABELS:
        return True
    if normalized_inst not in DROP_IF_SUBSTRING_FRAGMENT_LABELS:
        return False
    lowered = normalized_inst.casefold()
    for sibling in sibling_institutions:
        normalized_sibling = normalize_whitespace(sibling)
        if not normalized_sibling or normalized_sibling == normalized_inst:
            continue
        if lowered in normalized_sibling.casefold() and len(normalized_sibling) > len(normalized_inst):
            return True
    return False


def repair_author_affiliation_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[tuple[str, str, str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[
            (
                normalize_whitespace(row.get("conference", "")),
                normalize_whitespace(row.get("year", "")),
                normalize_whitespace(row.get("paper_id", "")),
                normalize_whitespace(row.get("article_tag", "")),
                normalize_whitespace(row.get("name", "")),
                normalize_whitespace(row.get("author_order", "")),
            )
        ].append(dict(row))

    repaired: list[dict[str, str]] = []
    for group in grouped.values():
        merged_group: list[dict[str, str]] = []
        index = 0
        original_institutions = [normalize_whitespace(row.get("inst", "")) for row in group if normalize_whitespace(row.get("inst", ""))]
        while index < len(group):
            current = dict(group[index])
            if index + 1 < len(group):
                # Some extraction runs split one institution into adjacent fragments like
                # "Department of Computer Science" + "Engineering, ...". Stitch them back here.
                merged_inst = merge_fragmented_affiliation_parts(
                    current.get("inst", ""),
                    group[index + 1].get("inst", ""),
                )
                if merged_inst is not None:
                    current["inst"] = merged_inst
                    if normalize_whitespace(current.get("country", "")) in {"", "Unknown"}:
                        current["country"] = group[index + 1].get("country", current.get("country", ""))
                    merged_group.append(current)
                    index += 2
                    continue
            if looks_like_author_token_affiliation(current.get("name", ""), current.get("inst", "")):
                current["inst"] = ""
                current["country"] = "Unknown"
                current["classification_source"] = "author_affiliation_sanitized"
                current["classification_confidence"] = "0.0"
                current["classification_reason"] = "author_name_token_misparsed_as_affiliation"
            elif looks_like_identifier_noise(current.get("inst", "")):
                current["inst"] = ""
                current["country"] = "Unknown"
                current["classification_source"] = "author_affiliation_sanitized"
                current["classification_confidence"] = "0.0"
                current["classification_reason"] = "identifier_noise_misparsed_as_affiliation"
            elif should_drop_generic_fragment_affiliation(current.get("inst", ""), original_institutions):
                current["inst"] = ""
                current["country"] = "Unknown"
                current["classification_source"] = "author_affiliation_sanitized"
                current["classification_confidence"] = "0.0"
                current["classification_reason"] = "generic_fragment_dropped_in_favor_of_longer_affiliation"
            merged_group.append(current)
            index += 1

        non_empty_rows = [row for row in merged_group if normalize_whitespace(row.get("inst", ""))]
        repaired.extend(non_empty_rows if non_empty_rows else merged_group[:1])
    return repaired


def expand_ordered_shared_bundle_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[
            (
                normalize_whitespace(row.get("conference", "")),
                normalize_whitespace(row.get("year", "")),
                normalize_whitespace(row.get("paper_id", "")),
                normalize_whitespace(row.get("article_tag", "")),
            )
        ].append(dict(row))

    expanded: list[dict[str, str]] = []
    for group in grouped.values():
        if not group:
            continue
        classification_sources = {
            normalize_whitespace(row.get("classification_source", ""))
            for row in group
        }
        bundle_values = {
            normalize_whitespace(row.get("inst", ""))
            for row in group
            if normalize_whitespace(row.get("inst", ""))
        }
        if (
            len(classification_sources) == 1
            and "mismatch_fallback_shared_multi_affiliation_bundle" in classification_sources
            and len(bundle_values) == 1
        ):
            bundle_value = next(iter(bundle_values))
            # Reuse the same split logic as normalization so comma/semicolon mixed bundles
            # can still be expanded into a stable per-author ordered assignment.
            bundle_parts = split_institutions(bundle_value) or [part.strip() for part in bundle_value.split(";") if normalize_whitespace(part)]
            unique_parts: list[str] = []
            seen_parts: set[str] = set()
            for part in bundle_parts:
                marker = normalize_whitespace(part).casefold()
                if marker in seen_parts:
                    continue
                seen_parts.add(marker)
                unique_parts.append(normalize_whitespace(part))
            ordered_group = sorted(group, key=lambda row: int(normalize_whitespace(row.get("author_order", "")) or "0"))
            if len(unique_parts) == len(ordered_group):
                for row, inst in zip(ordered_group, unique_parts):
                    row["inst"] = inst
                    row["country"] = ""
                    # Keep the provenance explicit: this is an automatic repair over a
                    # shared-bundle fallback, not a source-native author-affiliation parse.
                    row["classification_source"] = "ordered_shared_bundle_heuristic"
                    row["classification_confidence"] = "0.7"
                    row["classification_reason"] = "ordered_shared_bundle_author_affiliation_assignment"
                expanded.extend(ordered_group)
                continue
        expanded.extend(group)
    return expanded


def collect_input_rows(inputs: list[Path]) -> tuple[list[dict[str, str]], list[str]]:
    rows: list[dict[str, str]] = []
    input_files: list[str] = []
    for path in inputs:
        input_files.append(str(path))
        rows.extend(remap_row(row) for row in read_csv_rows(path))
    rows = expand_ordered_shared_bundle_rows(rows)
    return repair_author_affiliation_rows(rows), input_files


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = normalize_whitespace(value)
        marker = normalized.casefold()
        if not normalized or marker in seen:
            continue
        seen.add(marker)
        ordered.append(normalized)
    return ordered


def join_semicolon(values: list[str]) -> str:
    return "; ".join(value for value in values if normalize_whitespace(value))


def effective_country_value(value: str) -> str:
    normalized = normalize_whitespace(value)
    if normalized in {"", "Unknown"}:
        return ""
    return normalized


def build_author_paper_rollups(author_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, int], list[dict[str, object]]] = defaultdict(list)
    for row in author_rows:
        grouped[(str(row["paper_key"]), str(row["author_key"]), int(row["author_order"]))].append(row)

    rollups: list[dict[str, object]] = []
    for (_paper_key, _author_key, _author_order), grouped_rows in sorted(
        grouped.items(),
        key=lambda item: (
            str(item[1][0]["conference"]),
            str(item[1][0]["year"]),
            str(item[1][0]["title"]),
            int(item[1][0]["author_order"]),
            str(item[1][0]["name"]),
        ),
    ):
        ordered_rows = list(grouped_rows)
        primary_row = ordered_rows[0]
        participating_institutions = unique_preserve_order([str(row["inst"]) for row in ordered_rows])
        participating_institution_keys = unique_preserve_order([str(row["institution_key"]) for row in ordered_rows])
        participating_institution_ids = unique_preserve_order([str(row.get("institution_id", "")) for row in ordered_rows])
        participating_canonical_names = unique_preserve_order([str(row.get("canonical_institution_name", "")) for row in ordered_rows])
        participating_inst_countries = [str(row.get("country", "")) for row in ordered_rows]
        participating_countries = unique_preserve_order(
            [str(row.get("country", "")) for row in ordered_rows if str(row.get("country", "")) not in {"", "Unknown"}]
        )
        all_countries = unique_preserve_order([str(row.get("country", "")) for row in ordered_rows if str(row.get("country", ""))])
        rollups.append(
            {
                "author_paper_key": stable_key(
                    str(primary_row["paper_key"]),
                    str(primary_row["author_key"]),
                    str(primary_row["author_order"]),
                ),
                "paper_key": primary_row["paper_key"],
                "conference": primary_row["conference"],
                "year": primary_row["year"],
                "title": primary_row["title"],
                "article_tag": primary_row["article_tag"],
                "paper_id": primary_row["paper_id"],
                "name": primary_row["name"],
                "author_key": primary_row["author_key"],
                "author_order": primary_row["author_order"],
                "affiliation_record_count": len(ordered_rows),
                "affiliation_institution_count": len(participating_institutions),
                "resolved_affiliation_count": sum(
                    1 for row in ordered_rows if str(row.get("country", "")) not in {"", "Unknown"}
                ),
                "has_multi_affiliation": len(participating_institutions) > 1,
                "first_inst": primary_row["inst"],
                "first_institution_key": primary_row["institution_key"],
                "first_institution_id": primary_row.get("institution_id", ""),
                "first_canonical_institution_name": primary_row.get("canonical_institution_name", ""),
                "first_country": primary_row["country"],
                "first_classification_source": primary_row["classification_source"],
                "first_classification_confidence": primary_row["classification_confidence"],
                "first_classification_reason": primary_row["classification_reason"],
                "participating_insts": join_semicolon(participating_institutions),
                "participating_institution_keys": join_semicolon(participating_institution_keys),
                "participating_institution_ids": join_semicolon(participating_institution_ids),
                "participating_canonical_institution_names": join_semicolon(participating_canonical_names),
                "participating_inst_countries": join_semicolon(participating_inst_countries),
                "participating_countries": join_semicolon(participating_countries),
                "participating_country_count": len(participating_countries),
                "participating_country_scope": (
                    "multiple_countries"
                    if len(participating_countries) > 1
                    else "single_country"
                    if len(participating_countries) == 1
                    else "unknown"
                ),
                "all_record_countries": join_semicolon(all_countries),
            }
        )
    return rollups


def build_normalized_tables(
    rows: list[dict[str, str]]
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    author_rows: list[dict[str, object]] = []
    paper_index: dict[str, dict[str, object]] = {}
    institution_rows: dict[str, list[dict[str, object]]] = defaultdict(list)
    duplicate_row_keys = 0
    seen_row_keys: set[str] = set()
    alias_to_id, registry_by_id, reference_names = load_reference_institutions()
    parent_alias_candidates = build_parent_alias_candidates(alias_to_id, registry_by_id)
    duplicate_author_keys_within_paper: dict[tuple[str, str], set[str]] = defaultdict(set)

    for row in rows:
        article_tag = normalize_whitespace(row.get("article_tag", ""))
        recovered_conference, recovered_title = recover_conference_and_title(article_tag)
        conference = normalize_whitespace(row.get("conference", "")) or recovered_conference
        year = normalize_whitespace(row.get("year", ""))
        title = normalize_whitespace(row.get("title", "")) or recovered_title
        paper_id = normalize_whitespace(row.get("paper_id", ""))
        name = normalize_whitespace(row.get("name", ""))
        author_order_text = normalize_whitespace(row.get("author_order", ""))
        paper_key = normalize_paper_key(conference, year, title, paper_id)
        base_author_key = normalize_author_key(name)
        if paper_key and base_author_key:
            duplicate_author_keys_within_paper[(paper_key, base_author_key)].add(author_order_text or "0")

    paper_author_key_overrides: dict[tuple[str, str, str], str] = {}
    disambiguated_author_instances = 0
    for (paper_key, base_author_key), author_orders in duplicate_author_keys_within_paper.items():
        if len(author_orders) <= 1:
            continue
        for author_order_text in sorted(author_orders):
            paper_author_key_overrides[(paper_key, base_author_key, author_order_text)] = stable_key(
                base_author_key,
                paper_key,
                author_order_text,
            )
            disambiguated_author_instances += 1

    for row in rows:
        article_tag = normalize_whitespace(row.get("article_tag", ""))
        recovered_conference, recovered_title = recover_conference_and_title(article_tag)
        conference = normalize_whitespace(row.get("conference", "")) or recovered_conference
        year = normalize_whitespace(row.get("year", ""))
        title = normalize_whitespace(row.get("title", "")) or recovered_title
        paper_id = normalize_whitespace(row.get("paper_id", ""))
        name = normalize_whitespace(row.get("name", ""))
        author_order_text = normalize_whitespace(row.get("author_order", ""))
        inst_value = normalize_whitespace(row.get("inst", ""))
        source_country = normalize_whitespace(row.get("country", ""))
        classification_source = normalize_whitespace(row.get("classification_source", ""))
        classification_confidence = normalize_whitespace(row.get("classification_confidence", ""))
        classification_reason = normalize_whitespace(row.get("classification_reason", ""))

        paper_key = normalize_paper_key(conference, year, title, paper_id)
        base_author_key = normalize_author_key(name)
        author_key = paper_author_key_overrides.get(
            (paper_key, base_author_key, author_order_text or "0"),
            base_author_key,
        )

        institutions = split_institutions(inst_value, known_names=reference_names) or [inst_value]
        split_combined_institutions = len(institutions) > 1

        paper_entry = paper_index.setdefault(
            paper_key,
            {
                "paper_key": paper_key,
                "conference": conference,
                "year": year,
                "title": title,
                "article_tag": article_tag,
                "paper_id": paper_id,
                "author_count": 0,
            },
        )
        paper_entry["author_count"] = max(int(paper_entry["author_count"]), int(author_order_text or "0") + 1)

        for institution in institutions:
            institution_id, institution = resolve_institution_id(institution, alias_to_id)
            institution_id, institution = collapse_to_parent_institution(
                institution,
                institution_id,
                registry_by_id,
                parent_alias_candidates,
            )
            registry_row = registry_by_id.get(institution_id, {})
            registry_country = normalize_whitespace(registry_row.get("country", ""))
            canonical_name = normalize_whitespace(registry_row.get("canonical_name", ""))
            if canonical_name:
                institution = canonical_name
            institution_key = normalize_institution_key(institution)
            registry_type = normalize_whitespace(registry_row.get("type", ""))
            split_safe_source_country = source_country
            if split_combined_institutions and source_country in {"", "Unknown", "Multiple"}:
                split_safe_source_country = ""
            country = registry_country or effective_country_value(split_safe_source_country) or infer_country(institution)
            if registry_type == "independent":
                country = "None"
            row_key = stable_key(paper_key, author_order_text, institution_key)
            if row_key in seen_row_keys:
                duplicate_row_keys += 1
                continue
            seen_row_keys.add(row_key)

            normalized_row = {
                "row_key": row_key,
                "paper_key": paper_key,
                "conference": conference,
                "year": year,
                "title": title,
                "article_tag": article_tag,
                "paper_id": paper_id,
                "name": name,
                "author_key": author_key,
                "author_order": int(author_order_text or "0"),
                "inst": institution,
                "institution_key": institution_key,
                "institution_id": institution_id,
                "canonical_institution_name": canonical_name,
                "country": country,
                "classification_source": classification_source,
                "classification_confidence": classification_confidence,
                "classification_reason": classification_reason,
            }
            author_rows.append(normalized_row)
            institution_rows[institution_key].append(normalized_row)

    paper_facts = sorted(paper_index.values(), key=lambda row: (row["conference"], row["year"], row["title"]))
    institution_dim: list[dict[str, object]] = []
    for institution_key, grouped_rows in institution_rows.items():
        countries = {str(row["country"]) for row in grouped_rows if str(row["country"])}
        display_names = [str(row["inst"]) for row in grouped_rows]
        institution_ids = [str(row.get("institution_id", "")) for row in grouped_rows if str(row.get("institution_id", ""))]
        canonical_names = [str(row.get("canonical_institution_name", "")) for row in grouped_rows if str(row.get("canonical_institution_name", ""))]
        institution_id = choose_display_name(institution_ids)
        registry_row = registry_by_id.get(institution_id, {}) if institution_id else {}
        institution_dim.append(
            {
                "institution_key": institution_key,
                "inst_display": choose_display_name(display_names),
                "institution_id": institution_id,
                "canonical_name": choose_display_name(canonical_names) or str(registry_row.get("canonical_name", "")),
                "country": choose_display_name(sorted(countries)) or str(registry_row.get("country", "")),
                "region": str(registry_row.get("region", "")),
                "type": str(registry_row.get("type", "")),
                "source_count": len(grouped_rows),
                "needs_review": "Unknown" in countries,
            }
        )

    author_paper_rollups = build_author_paper_rollups(author_rows)

    report = {
        "input_rows": len(rows),
        "normalized_rows": len(author_rows),
        "author_paper_rows": len(author_paper_rollups),
        "paper_count": len(paper_facts),
        "institution_count": len(institution_dim),
        "rows_with_reference_institution_id": sum(1 for row in author_rows if row.get("institution_id")),
        "duplicate_row_keys_skipped": duplicate_row_keys,
        "same_name_author_instances_disambiguated_within_paper": disambiguated_author_instances,
        "rows_missing_name": sum(1 for row in author_rows if not row["name"]),
        "rows_missing_inst": sum(1 for row in author_rows if not row["inst"]),
        "rows_with_unknown_country": sum(1 for row in author_rows if row["country"] == "Unknown"),
        "multi_affiliation_author_rows": sum(1 for row in author_paper_rollups if bool(row["has_multi_affiliation"])),
    }
    return author_rows, author_paper_rollups, paper_facts, sorted(institution_dim, key=lambda row: str(row["inst_display"])), report


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize conference datasets for downstream analytics.")
    parser.add_argument("inputs", nargs="+", help="Input CSV files with author affiliation rows")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_ROOT), help="Output analysis root directory")
    args = parser.parse_args()

    input_paths = [Path(value) for value in args.inputs]
    output_dir = Path(args.output_dir) / "normalized"
    ensure_directory(output_dir)

    rows, input_files = collect_input_rows(input_paths)
    author_rows, author_paper_rollups, paper_facts, institution_dim, report = build_normalized_tables(rows)
    report["input_files"] = input_files

    write_csv_rows(
        output_dir / "author_affiliation_facts.csv",
        author_rows,
        [
            "row_key",
            "paper_key",
            "conference",
            "year",
            "title",
            "article_tag",
            "paper_id",
            "name",
            "author_key",
            "author_order",
            "inst",
            "institution_key",
            "institution_id",
            "canonical_institution_name",
            "country",
            "classification_source",
            "classification_confidence",
            "classification_reason",
        ],
    )
    write_csv_rows(
        output_dir / "author_paper_affiliation_facts.csv",
        author_paper_rollups,
        [
            "author_paper_key",
            "paper_key",
            "conference",
            "year",
            "title",
            "article_tag",
            "paper_id",
            "name",
            "author_key",
            "author_order",
            "affiliation_record_count",
            "affiliation_institution_count",
            "resolved_affiliation_count",
            "has_multi_affiliation",
            "first_inst",
            "first_institution_key",
            "first_institution_id",
            "first_canonical_institution_name",
            "first_country",
            "first_classification_source",
            "first_classification_confidence",
            "first_classification_reason",
            "participating_insts",
            "participating_institution_keys",
            "participating_institution_ids",
            "participating_canonical_institution_names",
            "participating_inst_countries",
            "participating_countries",
            "participating_country_count",
            "participating_country_scope",
            "all_record_countries",
        ],
    )
    write_csv_rows(
        output_dir / "paper_facts.csv",
        paper_facts,
        ["paper_key", "conference", "year", "title", "article_tag", "paper_id", "author_count"],
    )
    write_csv_rows(
        output_dir / "institution_dim.csv",
        institution_dim,
        ["institution_key", "inst_display", "institution_id", "canonical_name", "country", "region", "type", "source_count", "needs_review"],
    )
    write_json(output_dir / "normalization_report.json", report)


if __name__ == "__main__":
    main()
