#!/usr/bin/env python3
"""Prepare split affiliations or post-fill AffilGood output from institution_raw."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from institution_reference import load_institution_table, normalized_key
from personal_rules import load_rules


ENRICHMENT_FIELDS = (
    "record_id",
    "country",
    "country_raw",
    "country_source",
    "country_confidence",
    "city",
    "affiliation_institution_candidate",
    "affiliation_subunits",
    "affiliation_unmatched_components",
    "affilgood_ror_ids",
    "affilgood_institutions",
    "affilgood_location_country",
    "affilgood_location_city",
    "affilgood_standard_institutions",
    "affilgood_standardization_source",
    "institution_reference_match_method",
    "institution_reference_id",
    "institution_reference_confidence",
    "institution_reference_status",
    "institution_reference_review",
)


COUNTRY_CANONICAL_ALIASES = {
    "u s": "United States",
    "u s a": "United States",
    "us": "United States",
    "usa": "United States",
    "united states of america": "United States",
    "u k": "United Kingdom",
    "uk": "United Kingdom",
    "great britain": "United Kingdom",
    "p r china": "China",
    "pr china": "China",
    "prc": "China",
    "people s republic of china": "China",
    "republic of korea": "South Korea",
    "the netherlands": "Netherlands",
    "czech republic": "Czechia",
    "turkey": "Türkiye",
    "uae": "United Arab Emirates",
    "u a e": "United Arab Emirates",
    "hong kong sar": "Hong Kong",
    "hong kong s a r": "Hong Kong",
    "macau": "Macao",
    "russian federation": "Russia",
    "viet nam": "Vietnam",
}


SUBUNIT_PATTERN = re.compile(
    r"\b(?:department|dept\.?|laborator(?:y|ies)|lab\.?|research group|group|faculty|"
    r"school|division|research unit|centre|center)\b",
    flags=re.IGNORECASE,
)

# These unit names describe an organizational level below a university or
# company.  They may remain in ``affiliation_subunits`` but must not win an
# institution reference match on their own.
SECONDARY_ONLY_PATTERN = re.compile(
    r"^\s*(?:the\s+)?(?:school|department|dept\.?|faculty|college|division|laborator(?:y|ies)|lab\.?|research\s+group|group)\b"
    r"(?:\s+of\b|\s+for\b|\s+[-:]|\s*$)",
    flags=re.IGNORECASE,
)

SECONDARY_NAMED_PATTERN = re.compile(
    r"^\s*institute\s+of\s+cyberspace\s+security\b",
    flags=re.IGNORECASE,
)

# These phrases are commonly written as an institute followed by its parent
# academy.  The reviewed table stores the institute as one institution, so do
# not let the parent academy win as a separate candidate.
COMPOSITE_REFERENCE_ALIASES = {
    ("institute of information engineering", "chinese academy of sciences"):
        "Institute of Information Engineering",
    ("institute of information engineering", "cas"):
        "Institute of Information Engineering",
}

NONINSTITUTIONAL_KEYS = {
    normalized_key(value)
    for value in (
        "Independent Researcher",
        "Independent Security Researcher",
        "Independent Reseacher",
        "Unaffiliated",
        "No Affiliation",
        "None",
        "Concept Artist",
    )
}


def is_secondary_unit(value: str) -> bool:
    text = " ".join((value or "").split())
    return bool(SECONDARY_ONLY_PATTERN.search(text) or SECONDARY_NAMED_PATTERN.search(text))


def stable_record_id(row: dict[str, str], line_no: int) -> str:
    parts = (
        row.get("conference", ""), row.get("year", ""), row.get("paper_id", ""),
        row.get("author_rank", ""), row.get("affiliation_rank", ""), str(line_no),
    )
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:20]


def phrase_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _phrase_key_with_offsets(value: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    offsets: list[int] = []
    for source_index, source_char in enumerate(value or ""):
        decomposed = unicodedata.normalize("NFKD", source_char)
        for character in decomposed:
            if unicodedata.combining(character):
                continue
            for folded in character.casefold():
                if "a" <= folded <= "z" or "0" <= folded <= "9":
                    chars.append(folded)
                    offsets.append(source_index)
                elif chars and chars[-1] != " ":
                    chars.append(" ")
                    offsets.append(source_index)
    while chars and chars[-1] == " ":
        chars.pop()
        offsets.pop()
    return "".join(chars), offsets


def canonical_country(value: str) -> str:
    compact = phrase_key(value)
    return COUNTRY_CANONICAL_ALIASES.get(compact, " ".join((value or "").strip().split()))


def split_components(value: str) -> list[str]:
    components: list[str] = []
    buffer: list[str] = []
    depth = 0
    for character in value or "":
        if character in "([{【":
            depth += 1
        elif character in ")]}】" and depth:
            depth -= 1
        if character in ",，" and depth == 0:
            component = " ".join("".join(buffer).strip().split())
            if component:
                components.append(component)
            buffer = []
        else:
            buffer.append(character)
    component = " ".join("".join(buffer).strip().split())
    if component:
        components.append(component)
    return components


def build_country_aliases(table_rows: list[dict[str, str]]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for row in table_rows:
        raw = row.get("affilgood_location_country", "").strip()
        if not raw or phrase_key(raw) in {"none", "unknown"}:
            continue
        aliases[phrase_key(raw)] = canonical_country(raw)
    for alias, canonical in COUNTRY_CANONICAL_ALIASES.items():
        aliases[phrase_key(alias)] = canonical
    return aliases


def extract_terminal_country(
    components: list[str], aliases: dict[str, str]
) -> tuple[list[str], str, str]:
    if not components:
        return [], "", ""
    last, offsets = _phrase_key_with_offsets(components[-1])
    for alias in sorted(aliases, key=lambda value: (-len(value.split()), -len(value))):
        if last == alias:
            return components[:-1], components[-1], aliases[alias]
        suffix = f" {alias}"
        if last.endswith(suffix):
            suffix_start = len(last) - len(alias)
            raw_start = offsets[suffix_start]
            raw_component = components[-1]
            raw_prefix = raw_component[:raw_start].strip()
            remaining = list(components[:-1])
            if raw_prefix:
                remaining.append(raw_prefix)
            return remaining, raw_component[raw_start:].strip(), aliases[alias]
    return list(components), "", ""


def build_city_index(table_rows: list[dict[str, str]]) -> dict[str, str]:
    values: dict[str, Counter[str]] = defaultdict(Counter)
    for row in table_rows:
        city = " ".join(row.get("affilgood_location_city", "").strip().split())
        if city:
            values[normalized_key(city)][city] += 1
    return {key: counts.most_common(1)[0][0] for key, counts in values.items()}


def extract_terminal_city(
    components: list[str], city_index: dict[str, str]
) -> tuple[list[str], str, str]:
    if not components:
        return [], "", ""
    key = normalized_key(components[-1])
    if key in city_index:
        return components[:-1], components[-1], city_index[key]
    return list(components), "", ""


def record_identity(item: dict[str, str]) -> tuple[str, ...]:
    stable = item.get("conference_final_id") or item.get("conference_id") or item.get("ror_id")
    if stable:
        return ("stable", stable)
    return (
        "name",
        normalized_key(item.get("standard_name") or item.get("observed_name")),
        canonical_country(item.get("country", "")),
    )


def unique_candidates(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    unique: dict[tuple[str, ...], dict[str, str]] = {}
    for item in candidates:
        unique.setdefault(record_identity(item), item)
    return list(unique.values())


def reviewed_rule_record(rule: dict, observed: str) -> dict[str, str]:
    institutions = rule.get("institutions") or []
    standard_name = rule.get("canonical_name", "")
    ror_id = rule.get("ror_id", "")
    if institutions:
        standard_name = ";".join(item.get("name", "") for item in institutions if item.get("name"))
        ror_id = ";".join(item.get("ror_id", "") for item in institutions if item.get("ror_id"))
    return {
        "observed_name": observed,
        "standard_name": standard_name,
        "ror_id": ror_id,
        "country": rule.get("country", ""),
        "city": rule.get("city", ""),
        "conference_id": f"RULE:{rule['id']}",
        "conference_final_id": f"RULE:{rule['id']}",
        "standardization_source": f"personal_reviewed_rule:{rule['id']}",
    }


def context_matches(row: dict[str, str], wanted: dict[str, str]) -> bool:
    return all(normalized_key(row.get(field, "")) == normalized_key(value) for field, value in wanted.items())


def select_reviewed_rule(
    row: dict[str, str], affiliation: str, rules: dict
) -> tuple[dict[str, str] | None, tuple[str, tuple[int, ...], str] | None]:
    scoped = next(
        (
            rule for rule in rules.get("scoped_replacements", [])
            if context_matches(row, rule.get("match", {}))
        ),
        None,
    )
    rule = scoped or rules["exact_aliases"].get(normalized_key(affiliation))
    if not rule:
        return None, None
    return reviewed_rule_record(rule, affiliation), (affiliation, tuple(), "personal_reviewed_rule")


def atomic_reference_id(affiliation: str, candidates: list[dict[str, str]]) -> str:
    identities = sorted("|".join(record_identity(item)) for item in unique_candidates(candidates))
    payload = "\x1f".join([normalized_key(affiliation), *identities])
    return "ATOMIC:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def unknown_reference_id(affiliation: str) -> str:
    return "UNKNOWN:" + hashlib.sha256(normalized_key(affiliation).encode("utf-8")).hexdigest()[:16]


def institution_candidate_spans(components: list[str]) -> list[tuple[str, tuple[int, ...], str]]:
    candidates: list[tuple[str, tuple[int, ...], str]] = []
    seen: set[str] = set()
    size = len(components)
    for length in range(size, 0, -1):
        for start in range(0, size - length + 1):
            indexes = tuple(range(start, start + length))
            text = ", ".join(components[index] for index in indexes).strip()
            key = normalized_key(text)
            if len(key) < 3 or key in seen:
                continue
            seen.add(key)
            method = "location_stripped_full" if length == size else ("component" if length == 1 else "contiguous_components")
            candidates.append((text, indexes, method))
            for acronym in re.findall(r"\(([^()]*)\)", text):
                acronym_key = normalized_key(acronym)
                if len(acronym_key) >= 2 and acronym_key not in seen:
                    seen.add(acronym_key)
                    candidates.append((acronym.strip(), indexes, "parenthetical_alias"))
    return candidates


def composite_reference_spans(
    components: list[str], table: dict
) -> list[tuple[dict[str, str], tuple[str, tuple[int, ...], str]]]:
    """Return reviewed composite institution aliases before generic spans."""
    matches: list[tuple[dict[str, str], tuple[str, tuple[int, ...], str]]] = []
    for start in range(len(components) - 1):
        pair = tuple(phrase_key(component) for component in components[start:start + 2])
        target = COMPOSITE_REFERENCE_ALIASES.get(pair)
        if not target:
            continue
        target_items = table["index"].get(normalized_key(target), [])
        if not target_items:
            continue
        text = ", ".join(components[start:start + 2])
        candidate = (text, (start, start + 1), "composite_alias")
        matches.extend((item, candidate) for item in unique_candidates(target_items))
    return matches


def select_reference_match(
    components: list[str],
    table: dict,
    country: str,
) -> tuple[dict[str, str] | None, tuple[str, tuple[int, ...], str] | None, str, list[dict[str, str]]]:
    # Apply reviewed composite aliases first.  This prevents the generic
    # candidate scan from selecting a parent academy instead of the institute.
    matches = composite_reference_spans(components, table)
    if not matches:
        matches = []
        for candidate in institution_candidate_spans(components):
            if is_secondary_unit(candidate[0]):
                continue
            for item in unique_candidates(table["index"].get(normalized_key(candidate[0]), [])):
                matches.append((item, candidate))
    if not matches:
        return None, None, "unmatched", []

    if country:
        compatible = [
            pair for pair in matches
            if not pair[0].get("country")
            or canonical_country(pair[0].get("country", "")) == canonical_country(country)
        ]
        if compatible:
            matches = compatible
        else:
            conflict_candidates = unique_candidates([item for item, _ in matches])
            if len({record_identity(item) for item in conflict_candidates}) == 1:
                return matches[0][0], matches[0][1], "conflict", conflict_candidates
            return None, None, "conflict", conflict_candidates

    identities = {record_identity(item) for item, _ in matches}
    if len(identities) != 1:
        return None, None, "ambiguous", unique_candidates([item for item, _ in matches])

    selected_item, selected_candidate = max(
        matches,
        key=lambda pair: (len(normalized_key(pair[1][0])), len(pair[1][1]), pair[1][0]),
    )
    acronym_only = selected_candidate[2] == "parenthetical_alias" or len(normalized_key(selected_candidate[0])) <= 5
    if acronym_only and not country:
        return None, None, "ambiguous", [selected_item]
    return selected_item, selected_candidate, "matched", [selected_item]


def select_affilgood_reference_match(
    row: dict[str, str], table: dict, country: str
) -> tuple[dict[str, str] | None, tuple[str, tuple[int, ...], str] | None, str, list[dict[str, str]]]:
    """Match exact AffilGood names before falling back to raw affiliation spans."""
    matches: list[tuple[dict[str, str], tuple[str, tuple[int, ...], str]]] = []
    values = [
        (row.get(field) or "").strip()
        for field in ("affilgood_standard_institutions", "affilgood_institutions")
        if (row.get(field) or "").strip()
    ]
    atomic_composite = any(";" in value for value in values)
    # One affiliation_rank is one institution identity. For composite output,
    # query the complete value only; never select one component as the row ID.
    names = values if atomic_composite else [
        part.strip() for value in values for part in value.split(";") if part.strip()
    ]
    for name in names:
        if is_secondary_unit(name):
            continue
        candidate = (name, tuple(), "affilgood_name_exact")
        for item in unique_candidates(table["index"].get(normalized_key(name), [])):
            matches.append((item, candidate))
    if not matches:
        return None, None, "unmatched", []
    if country:
        compatible = [
            pair for pair in matches
            if not pair[0].get("country")
            or canonical_country(pair[0].get("country", "")) == canonical_country(country)
        ]
        if compatible:
            matches = compatible
        else:
            conflict_candidates = unique_candidates([item for item, _ in matches])
            if len({record_identity(item) for item in conflict_candidates}) == 1:
                return matches[0][0], matches[0][1], "conflict", conflict_candidates
            return None, None, "conflict", conflict_candidates
    identities = {record_identity(item) for item, _ in matches}
    if len(identities) != 1:
        return None, None, "ambiguous", unique_candidates([item for item, _ in matches])
    selected_item, selected_candidate = matches[0]
    return selected_item, selected_candidate, "matched", [selected_item]


def review_payload(status: str, candidates: list[dict[str, str]], extracted_country: str) -> str:
    if status not in {"ambiguous", "conflict"}:
        return ""
    return json.dumps(
        {
            "status": status,
            "extracted_country": extracted_country,
            "candidates": [
                {
                    "observed_name": item.get("observed_name", ""),
                    "standard_name": item.get("standard_name", ""),
                    "country": item.get("country", ""),
                    "ror_id": item.get("ror_id", ""),
                }
                for item in candidates
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def enrich_row(
    source: dict[str, str], line_no: int, table: dict, *, prepare_only: bool = False
) -> dict[str, str]:
    row = dict(source)
    row["record_id"] = row.get("record_id") or stable_record_id(row, line_no)
    affiliation = row.get("affiliations") or row.get("affiliation_raw") or row.get("affiliation") or ""
    all_components = split_components(affiliation)
    country_aliases = table["country_aliases"]
    without_country, country_raw, country = extract_terminal_country(all_components, country_aliases)
    without_city, city_raw, city = extract_terminal_city(without_country, table["city_index"])

    # Keep both variants: a city may be part of an official campus name.
    candidate_components = without_country

    if country:
        if not row.get("country", "").strip():
            row.update({
                "country": country,
                "country_raw": country_raw,
                "country_source": "pdf_explicit",
                "country_confidence": "high",
            })
        if not row.get("affilgood_location_country", "").strip():
            row["affilgood_location_country"] = country
    if city:
        row["city"] = row.get("city") or city

    resolved_country = canonical_country(
        row.get("country") or row.get("affilgood_location_country") or country
    )
    affilgood_institution = (
        row.get("affilgood_standard_institutions")
        or row.get("affilgood_institutions")
        or ""
    ).strip()
    affilgood_ror = (row.get("affilgood_ror_ids") or "").strip()
    affilgood_complete = bool(affilgood_institution and affilgood_ror and resolved_country)
    atomic_composite = any(
        ";" in (row.get(field) or "")
        for field in ("affilgood_standard_institutions", "affilgood_institutions")
    )

    selected = None
    candidate = None
    review_candidates: list[dict[str, str]] = []
    automatic_reference_id = ""
    automatic_match_method = ""
    automatic_confidence = ""
    if prepare_only:
        status = "pending_affilgood"
    elif normalized_key(affiliation) in NONINSTITUTIONAL_KEYS:
        status = "not_applicable_noninstitutional"
        automatic_reference_id = "NONINSTITUTIONAL"
        automatic_match_method = "noninstitutional_marker"
        automatic_confidence = "high"
    elif affilgood_complete:
        status = "affilgood_resolved"
    else:
        selected, candidate, status, review_candidates = select_affilgood_reference_match(
            row, table, resolved_country
        )
        if status == "unmatched" and not atomic_composite:
            selected, candidate, status, review_candidates = select_reference_match(
                candidate_components, table, resolved_country
            )
        if status == "unmatched" and not atomic_composite and without_city != candidate_components:
            selected, candidate, status, review_candidates = select_reference_match(
                without_city, table, resolved_country
            )
        if status in {"unmatched", "ambiguous", "conflict"}:
            rule_selected, rule_candidate = select_reviewed_rule(
                row, affiliation, table["automation_rules"]
            )
            if rule_selected and rule_candidate:
                selected, candidate = rule_selected, rule_candidate
                review_candidates = []
                status = "resolved_reviewed_rule"
        if status == "matched":
            status = "matched_after_affilgood"
        elif status == "conflict" and selected and candidate:
            status = "resolved_unique_identity"
        elif status in {"ambiguous", "conflict"}:
            status = "resolved_atomic_composite"
            automatic_reference_id = atomic_reference_id(affiliation, review_candidates)
            automatic_match_method = "deterministic_atomic_composite"
            automatic_confidence = "structural"
            review_candidates = []
        elif status == "unmatched":
            status = "unknown_organization"
            automatic_reference_id = unknown_reference_id(affiliation)
            automatic_match_method = "no_reviewed_identity"
            automatic_confidence = "unknown"

    consumed = set(candidate[1]) if candidate else set()
    remaining = [
        component for index, component in enumerate(candidate_components)
        if index not in consumed and normalized_key(component) != normalized_key(city_raw)
    ]
    row["affiliation_subunits"] = ";".join(component for component in remaining if SUBUNIT_PATTERN.search(component))
    row["affiliation_unmatched_components"] = ";".join(
        component for component in remaining if not SUBUNIT_PATTERN.search(component)
    )
    row["institution_reference_status"] = status
    review_status = status.removesuffix("_after_affilgood")
    row["institution_reference_review"] = review_payload(
        review_status, review_candidates, resolved_country
    )

    if automatic_reference_id:
        row["institution_reference_id"] = automatic_reference_id
        row["institution_reference_match_method"] = automatic_match_method
        row["institution_reference_confidence"] = automatic_confidence
    if status == "not_applicable_noninstitutional":
        row["country_source"] = row.get("country_source") or "not_applicable"
        row["country_confidence"] = row.get("country_confidence") or "not_applicable"

    if selected and candidate:
        table_country = canonical_country(selected.get("country", ""))
        reference_country = resolved_country or table_country
        fill_values = {
            "country": reference_country,
            "country_source": "institution_raw",
            "country_confidence": "high",
            "city": city or selected.get("city", ""),
            "affiliation_institution_candidate": candidate[0],
            "affilgood_ror_ids": selected.get("ror_id", ""),
            "affilgood_institutions": selected.get("observed_name", ""),
            "affilgood_location_country": reference_country,
            "affilgood_location_city": city or selected.get("city", ""),
            "affilgood_standard_institutions": selected.get("standard_name", ""),
            "affilgood_standardization_source": selected.get("standardization_source", "") or "institution_raw",
            "institution_reference_match_method": candidate[2],
            "institution_reference_id": (
                selected.get("conference_final_id")
                or selected.get("conference_id")
                or selected.get("ror_id", "")
            ),
            "institution_reference_confidence": "high",
        }
        for field, value in fill_values.items():
            if not row.get(field, "").strip() and value:
                row[field] = value
    return row


def build_report(rows: list[dict[str, str]], table_path: str) -> dict[str, object]:
    statuses = Counter(row.get("institution_reference_status", "") for row in rows)
    sources = Counter(row.get("country_source", "") for row in rows)
    warnings = []
    matched = statuses.get("matched_after_affilgood", 0)
    resolved = statuses.get("affilgood_resolved", 0)
    deterministic_resolved = sum(
        statuses.get(status, 0)
        for status in (
            "resolved_reviewed_rule", "resolved_unique_identity", "resolved_atomic_composite",
        )
    )
    if rows and matched == 0 and resolved == 0 and deterministic_resolved == 0:
        warnings.append("institution_reference_zero_matches")
    review_required = sum(bool(row.get("institution_reference_review", "").strip()) for row in rows)
    blank_country_not_applicable = sum(
        not row.get("affilgood_location_country", "").strip()
        and row.get("institution_reference_status") == "not_applicable_noninstitutional"
        for row in rows
    )
    blank_country_actionable = sum(
        not row.get("affilgood_location_country", "").strip()
        and row.get("institution_reference_status") != "not_applicable_noninstitutional"
        for row in rows
    )
    if review_required:
        warnings.append("institution_reference_review_required")
    if blank_country_actionable:
        warnings.append("actionable_blank_country")
    return {
        "institution_table": table_path,
        "rows": len(rows),
        "affilgood_resolved": resolved,
        "matched": matched,
        "ambiguous": statuses.get("ambiguous_after_affilgood", 0),
        "conflict": statuses.get("conflict_after_affilgood", 0),
        "unmatched": statuses.get("unmatched_after_affilgood", 0),
        "resolved_reviewed_rule": statuses.get("resolved_reviewed_rule", 0),
        "resolved_unique_identity": statuses.get("resolved_unique_identity", 0),
        "resolved_atomic_composite": statuses.get("resolved_atomic_composite", 0),
        "not_applicable_noninstitutional": statuses.get("not_applicable_noninstitutional", 0),
        "unknown_organization": statuses.get("unknown_organization", 0),
        "review_required": review_required,
        "pending_affilgood": statuses.get("pending_affilgood", 0),
        "explicit_country_rows": sources.get("pdf_explicit", 0),
        "blank_country_rows": blank_country_not_applicable + blank_country_actionable,
        "blank_country_not_applicable": blank_country_not_applicable,
        "blank_country_actionable": blank_country_actionable,
        "warnings": warnings,
    }


def match_csv(
    input_path: Path,
    output_path: Path,
    table_path: Path | None = None,
    report_path: Path | None = None,
    *,
    prepare_only: bool = False,
) -> tuple[int, int, int]:
    table = load_institution_table(str(table_path) if table_path else None)
    table["country_aliases"] = build_country_aliases(table["rows"])
    table["city_index"] = build_city_index(table["rows"])
    automation_rules = load_rules()
    automation_rules["exact_aliases"] = {
        normalized_key(alias): rule
        for rule in automation_rules.get("aliases", [])
        for alias in rule.get("aliases", [])
    }
    table["automation_rules"] = automation_rules
    with input_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        source_fields = list(reader.fieldnames or [])
        rows = [
            enrich_row(source, line_no, table, prepare_only=prepare_only)
            for line_no, source in enumerate(reader, start=2)
        ]
    fields = source_fields + [field for field in ENRICHMENT_FIELDS if field not in source_fields]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    report = build_report(rows, table["path"])
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(rows), int(report["matched"]), int(report["review_required"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--institution-table", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Parse IDs, locations, and candidates without querying institution_raw; run AffilGood next.",
    )
    args = parser.parse_args()
    total, matched, review = match_csv(
        args.input, args.output, args.institution_table, args.report, prepare_only=args.prepare_only
    )
    print(f"wrote {total} rows to {args.output}; matched={matched}; review={review}")
    if args.report:
        print(f"institution match report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
