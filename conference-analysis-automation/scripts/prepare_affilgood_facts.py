#!/usr/bin/env python3
"""Convert the current AffilGood split CSV into analytics fact tables."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from pathlib import Path


FACT_FIELDS = [
    "paper_key", "conference", "year", "title", "author_key", "name",
    "author_order", "institution_key", "institution_id", "inst",
    "canonical_institution_name", "country", "classification_confidence",
    "institution_source", "subunit", "country_source", "country_confidence",
    "institution_match_method", "institution_match_confidence",
    "institution_reference_status", "record_id", "affiliation_rank", "raw_affiliation",
]

INDEPENDENT_RESEARCHER = "Independent Researcher"
CISPA_CANONICAL_NAME = "Helmholtz Center for Information Security"
CISPA_ROR_ID = "https://ror.org/02njgxr09"
NONINSTITUTIONAL_KEYS = {
    "independent researcher",
    "independent security researcher",
    "independent reseacher",
    "unaffiliated",
    "no affiliation",
    "none",
    "concept artist",
}
NON_COUNTING_INSTITUTION_SOURCES = {
    "secondary_unit_only",
    "unresolved_composite_fragment",
    "independent_researcher_default",
}

SECONDARY_ONLY_PATTERN = re.compile(
    r"^\s*(?:the\s+)?(?:school|department|dept\.?|faculty|college|division|laborator(?:y|ies)|lab\.?|research\s+group|group)\b"
    r"(?:\s+of\b|\s+for\b|\s+[-:]|\s*$)",
    flags=re.IGNORECASE,
)

SECONDARY_NAMED_PATTERN = re.compile(
    r"^\s*institute\s+of\s+cyberspace\s+security\b",
    flags=re.IGNORECASE,
)


def normalized_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def normalize_author_display_name(value: str) -> str:
    """Collapse OCR whitespace/case noise while preserving the readable name."""
    text = unicodedata.normalize("NFKC", value or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compact_author_name(value: str) -> str:
    """Return a conservative comparison key for whitespace-inserted name variants."""
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", value or "").casefold())


def build_author_aliases(source_rows: list[dict[str, str]]) -> tuple[dict[int, str], dict[str, str]]:
    """Resolve obvious OCR name variants such as ``Xiaoyun Wa Ng``.

    Names are grouped only when their compact spelling is identical.  The most
    frequent display spelling wins, with fewer name tokens preferred as a
    deterministic tie-break.  This keeps the raw affiliation and source rows
    unchanged while giving analytics one stable author identity.
    """
    groups: dict[str, dict[str, int]] = {}
    for source in source_rows:
        display = normalize_author_display_name(source.get("author", ""))
        compact = compact_author_name(display)
        if not compact:
            continue
        groups.setdefault(compact, {})[display] = groups.setdefault(compact, {}).get(display, 0) + 1

    canonical_by_compact: dict[str, str] = {}
    aliases: dict[str, str] = {}
    for compact, displays in groups.items():
        def quality(value: str) -> tuple[int, int, int, str]:
            parts = value.split()
            mixed_case_penalty = sum(
                1 for part in parts[1:]
                if any(character.isupper() for character in part[1:])
                and any(character.islower() for character in part[1:])
            )
            return (abs(len(parts) - 2), mixed_case_penalty, -displays[value], value.casefold())

        preferred = sorted(
            displays,
            key=quality,
        )[0]
        if len(displays) > 1:
            preferred = " ".join(
                part[:1].upper() + part[1:].lower() if part else part
                for part in preferred.split()
            )
        canonical_by_compact[compact] = preferred
        for display in displays:
            if display != preferred:
                aliases[display] = preferred

    canonical_by_index: dict[int, str] = {}
    for index, source in enumerate(source_rows):
        display = normalize_author_display_name(source.get("author", ""))
        canonical_by_index[index] = canonical_by_compact.get(compact_author_name(display), display)
    return canonical_by_index, aliases


def stable_key(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(normalized_text(part) for part in parts)
    return f"{prefix}:{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def split_values(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s*[|;]\s*", value or "") if part.strip()]


def is_secondary_only_affiliation(value: str) -> bool:
    """Return true for a raw affiliation that contains only a subunit label."""
    text = " ".join((value or "").split())
    return bool(SECONDARY_ONLY_PATTERN.search(text) or SECONDARY_NAMED_PATTERN.search(text))


def is_cispa_alias(value: str) -> bool:
    return bool(re.search(r"\bcispa\b", value or "", flags=re.IGNORECASE))


def build_institution_registries(
    source_rows: list[dict[str, str]],
) -> tuple[dict[str, str], dict[str, str]]:
    """Build conservative name-to-identity and name-to-country registries.

    Singleton rows provide the useful cross-row evidence needed to repair a
    composite whose identity list is shorter than its institution list.  An
    aligned composite is deliberately not added to the registry because one
    malformed composite row must not override stronger singleton evidence.
    """
    identity_candidates: dict[str, set[str]] = {}
    country_candidates: dict[str, set[str]] = {}

    def add_candidate(bucket: dict[str, set[str]], name: str, value: str) -> None:
        name_key = normalized_text(name)
        value = (value or "").strip()
        if name_key and value and value.casefold() != "unknown":
            bucket.setdefault(name_key, set()).add(value)

    for source in source_rows:
        canonical = split_values(source.get("affilgood_standard_institutions", ""))
        observed = split_values(source.get("affilgood_institutions", ""))
        names = canonical or observed
        identities = split_values(
            source.get("affilgood_ror_ids", "").strip()
            or source.get("primary_institution_id", "").strip()
            or source.get("institution_reference_id", "").strip()
        )
        if len(names) == 1 and len(identities) == 1:
            add_candidate(identity_candidates, names[0], identities[0])

        countries = split_values(
            source.get("primary_country", "").strip()
            or source.get("affilgood_location_country", "").strip()
        )
        countries = ["None" if country.casefold() == "unknown" else country for country in countries]
        if len(names) == 1 and len(countries) == 1:
            add_candidate(country_candidates, names[0], countries[0])
        elif len(names) > 1 and len(countries) == 1:
            for name in names:
                add_candidate(country_candidates, name, countries[0])
        elif len(names) > 1 and len(names) == len(countries):
            for name, country in zip(names, countries):
                add_candidate(country_candidates, name, country)

    identity_registry = {
        name_key: next(iter(values))
        for name_key, values in identity_candidates.items()
        if len(values) == 1
    }
    country_registry = {
        name_key: next(iter(values))
        for name_key, values in country_candidates.items()
        if len(values) == 1
    }
    return identity_registry, country_registry


def resolve_composite_institution_components(
    canonical: list[str],
    observed: list[str],
    ror_ids: list[str],
    local_ids: list[str],
    identity_registry: dict[str, str],
) -> list[dict[str, str]]:
    """Keep only institution components with a defensible identity.

    Canonical names define the component order when present.  For unequal
    identity lists, names are resolved through the cross-row registry rather
    than being paired by position, which prevents a missing middle component
    from assigning the next ROR to the wrong institution.
    """
    names = canonical or observed
    identities = ror_ids or local_ids
    components: list[dict[str, str]] = []
    for index, name in enumerate(names):
        if not name or is_secondary_only_affiliation(name):
            continue
        name_key = normalized_text(name)
        identity = identity_registry.get(name_key, "")
        if not identity:
            if len(names) == len(identities) and len(names) > 1:
                identity = identities[index]
            elif len(names) == 1 and len(identities) == 1:
                identity = identities[0]
        if not identity:
            # A composite component without a reliable identity is a fragment.
            continue

        observed_name = ""
        if len(observed) == len(names):
            observed_name = observed[index]
        elif len(names) == 1 and len(observed) == 1:
            observed_name = observed[0]
        elif index < len(observed):
            # AffilGood commonly appends a duplicate observed fragment after
            # the canonical sequence.  Keep the positional prefix only.
            observed_name = observed[index]
        components.append({
            "canonical": name,
            "observed": observed_name or name,
            "institution_id": identity,
            "name": name,
        })
    return components


def convert_rows(source_rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    facts: list[dict[str, str]] = []
    institution_dim: dict[str, dict[str, str]] = {}
    canonical_authors, _ = build_author_aliases(source_rows)
    identity_registry, country_registry = build_institution_registries(source_rows)
    for source_index, source in enumerate(source_rows):
        canonical = split_values(source.get("affilgood_standard_institutions", ""))
        observed = split_values(source.get("affilgood_institutions", ""))
        ror_ids = split_values(source.get("affilgood_ror_ids", ""))
        raw_affiliation = source.get("affiliations", "").strip()
        institution_values = canonical + observed
        fallback = not canonical and not observed
        local_ids = split_values(
            source.get("primary_institution_id", "").strip()
            or source.get("institution_reference_id", "").strip()
        )
        composite_input = max(len(canonical), len(observed)) > 1
        if composite_input:
            institution_components = resolve_composite_institution_components(
                canonical,
                observed,
                ror_ids,
                local_ids,
                identity_registry,
            )
            if not institution_components and all(
                is_secondary_only_affiliation(value) for value in institution_values
            ):
                institution_components = [{
                    "canonical": "", "observed": "", "institution_id": "", "name": "",
                }]
        elif institution_values:
            institution_components = []
            component = {
                "canonical": canonical[0] if canonical else "",
                "observed": observed[0] if observed else canonical[0] if canonical else "",
                "institution_id": ror_ids[0] if len(ror_ids) == 1 else local_ids[0] if len(local_ids) == 1 else "",
                "name": canonical[0] if canonical else observed[0],
            }
            if not is_secondary_only_affiliation(component["name"]):
                institution_components.append(component)
            else:
                institution_components = [{"canonical": "", "observed": "", "institution_id": "", "name": ""}]
        elif is_secondary_only_affiliation(raw_affiliation):
            institution_components = [{"canonical": "", "observed": "", "institution_id": "", "name": ""}]
        else:
            institution_components = [{
                "canonical": "",
                "observed": raw_affiliation,
                "institution_id": local_ids[0] if len(local_ids) == 1 else "",
                "name": raw_affiliation,
            }]

        countries = split_values(
            source.get("primary_country", "").strip()
            or source.get("affilgood_location_country", "").strip()
        )
        countries = ["None" if country.casefold() == "unknown" else country for country in countries]
        explicit_countries = bool(countries)
        countries = list(dict.fromkeys(countries or ["None"]))
        author_name = canonical_authors.get(source_index, normalize_author_display_name(source.get("author", "")))
        reference_status = source.get("institution_reference_status", "").strip()
        match_confidence = source.get("institution_reference_confidence", "").strip()
        secondary_placeholder = bool(
            (institution_values and all(is_secondary_only_affiliation(value) for value in institution_values))
            or (not institution_values and is_secondary_only_affiliation(raw_affiliation))
        )
        real_institution_components = [
            component for component in institution_components
            if component.get("name") or component.get("canonical") or component.get("observed")
        ]
        for component in real_institution_components:
            component_values = (
                component.get("name", ""),
                component.get("canonical", ""),
                component.get("observed", ""),
            )
            if any(is_cispa_alias(value) for value in component_values):
                component["canonical"] = CISPA_CANONICAL_NAME
                component["observed"] = CISPA_CANONICAL_NAME
                component["name"] = CISPA_CANONICAL_NAME
                component["institution_id"] = CISPA_ROR_ID
                component["cispa_rule"] = "cispa-helmholtz-reviewed-pattern"

        component_pairs: list[tuple[dict[str, str], str, str]]
        if not real_institution_components:
            placeholder_kind = "secondary_only" if secondary_placeholder else "country_only"
            component_pairs = [
                (
                    {"canonical": "", "observed": "", "institution_id": "", "name": ""},
                    country,
                    placeholder_kind,
                )
                for country in countries
            ]
        elif len(countries) == len(real_institution_components) or len(countries) == 1:
            component_pairs = [
                (component, country, "institution")
                for component, country in (
                    list(zip(real_institution_components, countries))
                    if len(countries) == len(real_institution_components)
                    else [(component, countries[0]) for component in real_institution_components]
                )
            ]
        elif not explicit_countries:
            component_pairs = [(component, "None", "institution") for component in real_institution_components]
        else:
            # Keep institutions without inventing a positional institution-country
            # mapping, then add explicit country-only facts for the paper/author.
            component_pairs = [
                (
                    component,
                    country_registry.get(normalized_text(component["canonical"]), ""),
                    "institution",
                )
                for component in real_institution_components
            ]
            covered_countries = {
                country.casefold() for _, country, _ in component_pairs if country
            }
            component_pairs.extend(
                (
                    {"canonical": "", "observed": "", "institution_id": "", "name": ""},
                    country,
                    "country_only",
                )
                for country in countries
                if country.casefold() not in covered_countries
            )
        for component_index, (component, country, pair_kind) in enumerate(component_pairs):
            canonical_name = component["canonical"]
            observed_name = component["observed"] or canonical_name
            institution_name = canonical_name or observed_name
            secondary_only = not institution_name
            cispa_rule = bool(component.get("cispa_rule"))
            if cispa_rule:
                observed_name = institution_name = canonical_name = CISPA_CANONICAL_NAME
            if pair_kind == "country_only":
                if real_institution_components:
                    institution_source = "unresolved_composite_fragment"
                    canonical_name = observed_name = institution_name = ""
                else:
                    institution_source = "independent_researcher_default"
                    canonical_name = observed_name = institution_name = INDEPENDENT_RESEARCHER
            elif pair_kind == "secondary_only":
                institution_source = "independent_researcher_default"
                canonical_name = observed_name = institution_name = INDEPENDENT_RESEARCHER
            elif secondary_only:
                institution_source = "independent_researcher_default"
                canonical_name = observed_name = institution_name = INDEPENDENT_RESEARCHER
            elif normalized_text(institution_name) in NONINSTITUTIONAL_KEYS:
                institution_source = "independent_researcher_default"
                canonical_name = observed_name = institution_name = INDEPENDENT_RESEARCHER
            elif cispa_rule:
                institution_source = "reviewed_canonical_rule"
            elif fallback:
                institution_source = "raw_affiliation_fallback"
            elif composite_input:
                institution_source = "resolved_institution_component"
            elif reference_status in {"matched", "matched_after_affilgood"}:
                institution_source = "institution_raw"
            else:
                institution_source = source.get("affilgood_standardization_source", "").strip() or "affilgood"
            institution_id = component["institution_id"]
            if institution_source == "independent_researcher_default":
                institution_id = "NONINSTITUTIONAL"
            if institution_source == "unresolved_composite_fragment":
                continue
            institution_key = (
                stable_key("institution", canonical_name or institution_name, country)
                if institution_name
                else ""
            )
            record_id = source.get("record_id", "").strip()
            if len(component_pairs) > 1 and record_id:
                record_id = f"{record_id}:component-{component_index}"
            fact = {
                "paper_key": source.get("paper_id", "").strip(),
                "conference": source.get("conference", "").strip(),
                "year": source.get("year", "").strip(),
                "title": source.get("title", "").strip(),
                "author_key": stable_key("author", author_name),
                "name": author_name,
                "author_order": source.get("author_rank", "").strip(),
                "institution_key": institution_key,
                "institution_id": institution_id,
                "inst": observed_name,
                "canonical_institution_name": canonical_name,
                "country": country,
                "classification_confidence": match_confidence,
                "institution_source": institution_source,
                "subunit": source.get("affiliation_subunits", "").strip(),
                "country_source": (
                    source.get("primary_country_source", "").strip()
                    or source.get("country_source", "").strip()
                ),
                "country_confidence": source.get("country_confidence", "").strip(),
                "institution_match_method": source.get("institution_reference_match_method", "").strip(),
                "institution_match_confidence": match_confidence,
                "institution_reference_status": reference_status,
                "record_id": record_id,
                "affiliation_rank": source.get("affiliation_rank", "").strip(),
                "raw_affiliation": source.get("affiliations", "").strip(),
            }
            facts.append(fact)
            if institution_source not in NON_COUNTING_INSTITUTION_SOURCES:
                institution_dim.setdefault(institution_key, {
                    "institution_key": institution_key,
                    "institution_id": institution_id,
                    "inst_display": canonical_name or observed_name,
                    "country": country,
                    "source": fact["institution_source"],
                    "needs_review": "false",
                })
    facts.sort(key=lambda row: (
        row["paper_key"], int(row["author_order"] or 0), int(row["affiliation_rank"] or 0),
        row["institution_key"],
    ))
    dimensions = sorted(institution_dim.values(), key=lambda row: (row["country"], row["inst_display"]))
    return facts, dimensions


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def prepare(input_path: Path, output_dir: Path) -> dict[str, object]:
    with input_path.open(encoding="utf-8-sig", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    facts, dimensions = convert_rows(source_rows)
    write_csv(output_dir / "author_affiliation_facts.csv", FACT_FIELDS, facts)
    write_csv(output_dir / "author_paper_affiliation_facts.csv", FACT_FIELDS, facts)
    dim_fields = ["institution_key", "institution_id", "inst_display", "country", "source", "needs_review"]
    write_csv(output_dir / "institution_dim.csv", dim_fields, dimensions)
    report = {
        "source": str(input_path.resolve()),
        "source_rows": len(source_rows),
        "fact_rows": len(facts),
        "paper_count": len({row["paper_key"] for row in facts}),
        "author_count": len({row["author_key"] for row in facts}),
        "institution_count": len(dimensions),
        "none_country_rows": sum(row["country"] == "None" for row in facts),
        "raw_affiliation_fallback_rows": sum(row["institution_source"] == "raw_affiliation_fallback" for row in facts),
        "identity_policy": "compact OCR-aware author display normalization; no ORCID-level disambiguation",
    }
    (output_dir / "normalization_report.json").write_text(
        json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    report = prepare(Path(args.input), Path(args.output_dir))
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
