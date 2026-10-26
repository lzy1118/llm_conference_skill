#!/usr/bin/env python3
"""Extract one auditable primary institution for the three IACR conferences."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from institution_reference import load_institution_table, normalized_key


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_INPUT_DIR = REPO_ROOT / "generated-data" / "crypto_2020_2025_run" / "extraction_affilgood"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "generated-data" / "crypto_2020_2025_run" / "primary_institution"
DEFAULT_TABLE = REPO_ROOT / "generated-data" / "institution_raw.csv"
DEFAULT_RULES = SCRIPT_DIR.parent / "references" / "personal-rules.json"
CONFERENCES = {"asiacrypt", "crypto", "eurocrypt"}
UNKNOWN = {"", "unknown", "none", "null", "n/a", "na", "-"}
OUTPUT_FIELDS = (
    "primary_institution",
    "primary_country",
    "primary_ror_id",
    "primary_institution_id",
    "primary_city",
    "primary_institution_source",
    "primary_country_source",
    "primary_match_status",
    "primary_review_reason",
)

COUNTRY_ALIASES = {
    "u s": "United States",
    "u s a": "United States",
    "us": "United States",
    "usa": "United States",
    "united states of america": "United States",
    "u k": "United Kingdom",
    "uk": "United Kingdom",
    "great britain": "United Kingdom",
    "republic of korea": "South Korea",
    "korea": "South Korea",
    "the netherlands": "Netherlands",
    "p r china": "China",
    "pr china": "China",
    "prc": "China",
    "people s republic of china": "China",
}

SECONDARY_RE = re.compile(
    r"^\s*(?:the\s+)?(?:department|dept\.?|school|faculty|college|division|"
    r"laborator(?:y|ies)|lab\.?|research group|center|centre)\b",
    re.IGNORECASE,
)


def clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def phrase_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value).casefold()).strip()


def canonical_country(value: Any) -> str:
    text = clean(value)
    key = phrase_key(text)
    if key in UNKNOWN:
        return ""
    return COUNTRY_ALIASES.get(key, text)


def despace_ocr(value: str) -> str:
    """Repair strings such as ``Z a m a , P a r i s , F r a n c e``."""
    text = clean(value)
    for _ in range(8):
        updated = re.sub(r"(?i)(?<![A-Za-z])([A-Za-z])\s+(?=[A-Za-z](?:\s|[,;.]|$))", r"\1", text)
        if updated == text:
            break
        text = updated
    return re.sub(r"\s*([,;])\s*", r"\1 ", text).strip()


def split_values(value: Any) -> list[str]:
    return [clean(part) for part in str(value or "").split(";") if clean(part)]


def compatible_country(candidate: dict[str, str], country: str) -> bool:
    candidate_country = canonical_country(
        candidate.get("country") or candidate.get("affilgood_location_country")
    )
    return not country or not candidate_country or candidate_country.casefold() == country.casefold()


def _city_hints(source: dict[str, str]) -> list[str]:
    values = [
        clean(source.get("city")),
        clean(source.get("affilgood_location_city")),
    ]
    raw = despace_ocr(source.get("affiliations", ""))
    values.extend(clean(part) for part in raw.split(",") if clean(part))
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = normalized_key(value)
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _inria_candidates(
    table: dict[str, Any], names: Iterable[str], country: str, city_hints: Iterable[str]
) -> list[dict[str, str]]:
    """Resolve generic Inria labels with center/city evidence.

    The institution table contains several French Inria centers.  A bare
    ``Inria`` must not be treated as one global center when the source row
    carries Paris, Saclay, Rennes, etc.  We only return a candidate when the
    city or an explicit center token narrows the result to one local ID.
    """
    name_values = [clean(name) for name in names if clean(name)]
    if not any("inria" in phrase_key(name) for name in name_values):
        return []
    candidates: list[dict[str, str]] = []
    for item in table["rows"]:
        source = clean(item.get("standardization_source") or item.get("affilgood_standardization_source"))
        if source and not source.startswith("ror"):
            continue
        haystack = " ".join([
            item.get("observed_name", ""),
            item.get("standard_name", ""),
            item.get("affilgood_institutions", ""),
            item.get("affilgood_standard_institutions", ""),
        ])
        if "inria" not in phrase_key(haystack):
            continue
        if "centre inria" not in phrase_key(haystack) and not phrase_key(haystack).startswith("inria "):
            continue
        if country and not compatible_country(item, country):
            continue
        candidates.append(item)
    if not candidates:
        return []
    hints = [normalized_key(value) for value in city_hints if normalized_key(value)]
    explicit = [phrase_key(name) for name in name_values if "inria" in phrase_key(name)]
    narrowed: list[dict[str, str]] = []
    for item in candidates:
        item_city = normalized_key(item.get("city") or item.get("affilgood_location_city"))
        item_name = phrase_key(
            f"{item.get('observed_name', '')} {item.get('standard_name', '')} "
            f"{item.get('affilgood_institutions', '')} "
            f"{item.get('affilgood_standard_institutions', '')}"
        )
        if item_city and any(
            hint == item_city or hint in item_city or item_city in hint
            for hint in hints
        ):
            narrowed.append(item)
            continue
        if any(
            token
            and token not in {"inria", "centre", "center", "france"}
            and len(token) >= 4
            and token in item_name
            for hint in (phrase_key(value) for value in city_hints)
            for token in hint.split()
        ):
            narrowed.append(item)
            continue
        if any(
            token and token not in {"inria", "centre", "de", "l", "universite", "université"}
            and token in item_name
            for name in explicit
            for token in name.split()
        ):
            narrowed.append(item)
    identities = {
        (
            item.get("conference_final_id") or item.get("conference_id") or "",
            item.get("ror_id") or item.get("affilgood_ror_ids") or "",
            normalized_key(
                item.get("standard_name")
                or item.get("observed_name")
                or item.get("affilgood_standard_institutions")
                or item.get("affilgood_institutions")
            ),
        )
        for item in narrowed
    }
    return narrowed if len(identities) == 1 else []


def reference_by_local_id(table: dict[str, Any], local_id: str) -> dict[str, str] | None:
    target = clean(local_id)
    if not target:
        return None
    matches = [
        row for row in table["rows"]
        if clean(row.get("conference_final_id") or row.get("conference_id")) == target
    ]
    if not matches:
        return None
    # Prefer the canonical row, then the row with a ROR.  Duplicate aliases all
    # share the same local identity.
    return sorted(
        matches,
        key=lambda row: (
            not bool(clean(row.get("affilgood_standard_institutions"))),
            not bool(clean(row.get("affilgood_ror_ids"))),
            clean(row.get("affilgood_institutions")).casefold(),
        ),
    )[0]


def reference_match(row: dict[str, str], reference: dict[str, str], country: str) -> dict[str, str]:
    return {
        "name": (
            reference.get("standard_name")
            or reference.get("observed_name")
            or reference.get("affilgood_standard_institutions")
            or reference.get("affilgood_institutions")
            or ""
        ),
        "ror_id": reference.get("ror_id") or reference.get("affilgood_ror_ids") or "",
        "local_id": (
            reference.get("conference_final_id")
            or reference.get("conference_id")
            or row.get("institution_reference_id")
            or ""
        ),
        "country": country or canonical_country(
            reference.get("country") or reference.get("affilgood_location_country")
        ),
        "city": reference.get("city") or reference.get("affilgood_location_city") or "",
    }


def unique_reference(
    table: dict[str, Any], names: Iterable[str], country: str = "",
    city_hints: Iterable[str] = (),
) -> dict[str, str] | None:
    matches: dict[tuple[str, str, str], dict[str, str]] = {}
    for name in names:
        for candidate in table["index"].get(normalized_key(name), []):
            if not compatible_country(candidate, country):
                continue
            identity = (
                candidate.get("conference_final_id") or candidate.get("conference_id") or "",
                candidate.get("ror_id") or "",
                normalized_key(candidate.get("standard_name") or candidate.get("observed_name")),
            )
            matches.setdefault(identity, candidate)
    if len(matches) == 1:
        return next(iter(matches.values()))
    if matches and any(";" in name for name in names):
        longest_key = max((normalized_key(name) for name in names), key=len, default="")
        exact_matches = {
            key: candidate
            for key, candidate in matches.items()
            if normalized_key(candidate.get("standard_name") or candidate.get("observed_name"))
            == longest_key
        }
        if len(exact_matches) == 1:
            return next(iter(exact_matches.values()))
    center_matches = _inria_candidates(table, names, country, city_hints)
    center_identities = {
        (
            candidate.get("conference_final_id") or candidate.get("conference_id") or "",
            candidate.get("ror_id") or "",
            normalized_key(candidate.get("standard_name") or candidate.get("observed_name")),
        )
        for candidate in center_matches
    }
    if len(center_identities) == 1:
        return center_matches[0]
    return None


def load_reviewed_aliases(path: Path) -> dict[str, list[dict[str, str]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    aliases: dict[str, list[dict[str, str]]] = defaultdict(list)
    for rule in payload.get("aliases", []):
        record = {
            "name": clean(rule.get("canonical_name")),
            "ror_id": clean(rule.get("ror_id")),
            "country": canonical_country(rule.get("country")),
            "city": clean(rule.get("city")),
            "rule_id": clean(rule.get("id")),
        }
        for alias in rule.get("aliases", []):
            aliases[normalized_key(alias)].append(record)
    return dict(aliases)


def unique_reviewed_alias(
    aliases: dict[str, list[dict[str, str]]], names: Iterable[str], country: str = ""
) -> dict[str, str] | None:
    matches: dict[tuple[str, str, str], dict[str, str]] = {}
    for name in names:
        for candidate in aliases.get(normalized_key(name), []):
            if country and candidate["country"] and candidate["country"].casefold() != country.casefold():
                continue
            identity = (candidate["name"], candidate["ror_id"], candidate["country"])
            matches.setdefault(identity, candidate)
    return next(iter(matches.values())) if len(matches) == 1 else None


def explicit_country(raw: str, known_countries: Iterable[str]) -> str:
    text = despace_ocr(raw)
    terms = list(COUNTRY_ALIASES.items()) + [(country.casefold(), country) for country in known_countries]
    found: list[str] = []
    for term, country in sorted(terms, key=lambda item: len(item[0]), reverse=True):
        # A country token inside an institution name (for example University
        # of Georgia) is not location evidence. Only accept a terminal token.
        if re.search(r"(?:^|[,;])\s*" + re.escape(term) + r"\s*[.]?$", text, re.IGNORECASE):
            canonical = canonical_country(country)
            if canonical and canonical not in found:
                found.append(canonical)
    return found[0] if len(found) == 1 else ""


def institution_score(value: str) -> int:
    text = clean(value)
    if SECONDARY_RE.search(text):
        return 20
    if re.search(r"\b(university|universit[eéäà]|college|polytechnic)\b", text, re.IGNORECASE):
        return 500
    if re.search(r"\b(academy of sciences|national institute|institute of technology)\b", text, re.IGNORECASE):
        return 460
    if re.search(r"\b(cnrs|inria|cwi|cispa|epfl|eth|kaist|kias|nist)\b", text, re.IGNORECASE):
        return 430
    if re.search(r"\b(institute|academy|research|technolog(?:y|ies)|labs?)\b", text, re.IGNORECASE):
        return 350
    return 250


def plausible_primary(value: str, country: str, known_cities: set[str]) -> bool:
    text = clean(value)
    key = normalized_key(text)
    if not key or (country and canonical_country(text).casefold() == country.casefold()) or key in known_cities:
        return False
    if re.search(r"\b(?:avenue|street|road|rue|boulevard|postal|postcode|zip|cedex)\b", text, re.IGNORECASE):
        return False
    if re.match(r"^\s*(?:[A-Z]{0,3}-)?\d{3,}\b", text, re.IGNORECASE):
        return False
    return True


def _city_initials(city: str) -> str:
    return "".join(part[:1] for part in phrase_key(city).split() if part)


def is_location_only_candidate(
    value: str,
    row: dict[str, str],
    country: str,
    known_cities: set[str],
) -> bool:
    """Return true when a fallback institution candidate is only location text."""
    text = clean(value)
    key = normalized_key(text)
    if not key:
        return True
    if country and canonical_country(text).casefold() == country.casefold():
        return True
    city_values = [
        clean(row.get("city")),
        clean(row.get("affilgood_location_city")),
    ]
    city_keys = {normalized_key(city) for city in city_values if normalized_key(city)}
    city_keys.update(known_cities)
    if key in city_keys:
        return True
    # Handle rows such as "New York, NY, USA", where a location abbreviation
    # was captured as a candidate institution.
    for city in city_values:
        initials = _city_initials(city)
        if len(initials) >= 2 and key == initials:
            return True
    return False


def ordered_names(row: dict[str, str]) -> list[str]:
    values: list[str] = []
    candidate = clean(row.get("affiliation_institution_candidate"))
    if candidate and not SECONDARY_RE.search(candidate):
        values.append(candidate)
    affilgood_values = [
        clean(row.get(field))
        for field in ("affilgood_standard_institutions", "affilgood_institutions")
        if clean(row.get(field))
    ]
    atomic_composite = any(";" in value for value in affilgood_values)
    if atomic_composite:
        # Keep the complete affiliation_rank as one institution label.
        values.extend(affilgood_values)
    else:
        for value in affilgood_values:
            values.extend(split_values(value))
    raw = despace_ocr(row.get("affiliations", ""))
    values.extend(clean(part) for part in raw.split(",") if clean(part))
    unique: list[str] = []
    seen = set()
    for value in values:
        key = normalized_key(value)
        if key and key not in seen:
            seen.add(key)
            unique.append(value)
    return unique


def choose_affilgood_ror(row: dict[str, str], country: str) -> dict[str, str] | None:
    rors = split_values(row.get("affilgood_ror_ids"))
    if not rors or not country:
        return None
    canonical = split_values(row.get("affilgood_standard_institutions"))
    observed = split_values(row.get("affilgood_institutions"))
    names = canonical or observed
    if not names:
        return None
    if len(names) > 1:
        return {
            "name": ";".join(names),
            "ror_id": ";".join(rors),
            "country": country,
            "city": clean(row.get("affilgood_location_city")),
        }
    # The flattened CSV omits empty ROR slots. Positional pairing is safe only
    # for a one-to-one list or a single institution. Otherwise defer to the
    # exact institution table rather than attaching an ID to the wrong body.
    if len(names) != len(rors):
        return None
    candidate_name = clean(row.get("affiliation_institution_candidate"))
    selected_index = 0
    if candidate_name:
        candidate_key = normalized_key(candidate_name)
        for index, name in enumerate(names):
            name_key = normalized_key(name)
            if candidate_key == name_key or candidate_key in name_key or name_key in candidate_key:
                selected_index = index
                break
        else:
            selected_index = max(range(len(names)), key=lambda index: (institution_score(names[index]), -index))
    else:
        selected_index = max(range(len(names)), key=lambda index: (institution_score(names[index]), -index))
    ror_id = rors[selected_index]
    if not ror_id:
        return None
    return {
        "name": names[selected_index],
        "ror_id": ror_id,
        "country": country,
        "city": clean(row.get("affilgood_location_city")),
    }


def enrich_row(
    source: dict[str, str],
    table: dict[str, Any],
    aliases: dict[str, list[dict[str, str]]],
    known_countries: set[str],
    known_cities: set[str] | None = None,
) -> dict[str, str]:
    row = dict(source)
    known_cities = known_cities or set()
    names = ordered_names(row)
    country = canonical_country(row.get("affilgood_location_country") or row.get("country"))
    country_source = clean(row.get("country_source")) or ("affilgood" if country else "")

    # Stage 1: fill missing country before country-aware institution linking.
    if not country:
        country = explicit_country(row.get("affiliations", ""), known_countries)
        if country:
            country_source = "raw_affiliation_explicit_backfill"
    if not country:
        reference = unique_reference(table, names, city_hints=_city_hints(row))
        if reference and reference.get("country"):
            country = canonical_country(reference["country"])
            country_source = "institution_raw_country_backfill"
    if not country:
        reviewed = unique_reviewed_alias(aliases, names)
        if reviewed and reviewed.get("country"):
            country = reviewed["country"]
            country_source = f"reviewed_rule_country_backfill:{reviewed['rule_id']}"

    # Stage 2: consume AffilGood/ROR output with country context.
    match = choose_affilgood_ror(row, country)
    institution_source = "affilgood_ror" if match else ""

    # Stage 3: consume an already-reviewed local institution ID, then exact
    # country-compatible lookup in institution_raw.csv.
    if not match:
        reference = reference_by_local_id(table, row.get("institution_reference_id", ""))
        if reference:
            match = reference_match(row, reference, country)
            institution_source = (
                "institution_raw_conflict"
                if "conflict" in clean(row.get("institution_reference_status"))
                else "institution_raw"
            )
    if not match:
        reference = unique_reference(table, names, country, _city_hints(row))
        if reference:
            match = reference_match(row, reference, country)
            institution_source = "institution_raw"

    # Stage 4: reviewed supplements, followed by a traceable unlinked fallback.
    if not match:
        reviewed = unique_reviewed_alias(aliases, names, country)
        if reviewed:
            match = reviewed
            institution_source = f"reviewed_supplement:{reviewed['rule_id']}"
    if not match and names:
        plausible = [
            value for value in names
            if plausible_primary(value, country, known_cities)
            and not is_location_only_candidate(value, row, country, known_cities)
        ]
        primary = max(plausible, key=lambda value: (institution_score(value), -names.index(value))) if plausible else ""
        if primary and not SECONDARY_RE.search(primary):
            match = {"name": primary, "ror_id": "", "country": country, "city": ""}
            institution_source = "unlinked_candidate"

    # A reviewed alias may correct the display label while preserving an
    # already-resolved ROR/local identity. Do not let a registry spelling
    # override a reviewed project canonical name for the same institution.
    reviewed = unique_reviewed_alias(aliases, names, country)
    atomic_local_identity = bool(
        match
        and clean(match.get("local_id"))
        and ";" in clean(match.get("name"))
    )
    if match and reviewed and not atomic_local_identity:
        match_ror = clean(match.get("ror_id"))
        reviewed_ror = clean(reviewed.get("ror_id"))
        match_country = canonical_country(match.get("country"))
        reviewed_country = canonical_country(reviewed.get("country"))
        identity_compatible = not match_ror or not reviewed_ror or match_ror == reviewed_ror
        country_compatible = (
            not match_country
            or not reviewed_country
            or match_country.casefold() == reviewed_country.casefold()
        )
        if identity_compatible and country_compatible:
            canonical_name = clean(reviewed.get("name"))
            if canonical_name and canonical_name != clean(match.get("name")):
                match = dict(match)
                match["name"] = canonical_name
                match["ror_id"] = match_ror or reviewed_ror
                match["country"] = match_country or reviewed_country
                match["city"] = clean(match.get("city") or reviewed.get("city"))
                institution_source = (
                    f"{institution_source}+reviewed_alias:{reviewed['rule_id']}"
                )

    primary_name = clean((match or {}).get("name"))
    primary_country = country or canonical_country((match or {}).get("country"))
    primary_ror = clean((match or {}).get("ror_id"))
    primary_id = clean(
        (match or {}).get("local_id")
        or row.get("institution_reference_id")
        or primary_ror
    )
    if not primary_name:
        primary_name = "Independent Researcher"
        primary_country = primary_country or "none"
        independent_reference = unique_reference(table, ["Independent Researcher"])
        primary_id = clean(
            (independent_reference or {}).get("conference_final_id")
            or (independent_reference or {}).get("conference_id")
            or "INDEPENDENT_RESEARCHER"
        )
        institution_source = "independent_researcher_default"
    reasons = []
    if not primary_country:
        reasons.append("missing_country")
    if primary_name and not primary_id:
        reasons.append("missing_institution_id")
    status = "complete" if not reasons else "needs_supplement"
    row.update({
        "primary_institution": primary_name,
        "primary_country": primary_country,
        "primary_ror_id": primary_ror,
        "primary_institution_id": primary_id,
        "primary_city": clean((match or {}).get("city") or row.get("affilgood_location_city")),
        "primary_institution_source": institution_source,
        "primary_country_source": country_source,
        "primary_match_status": status,
        "primary_review_reason": ";".join(reasons),
    })
    return row


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def process_file(
    input_path: Path,
    output_path: Path,
    institution_table: Path,
    personal_rules: Path,
) -> dict[str, Any]:
    """Process one conference/year CSV without changing the batch workflow."""
    table = load_institution_table(str(institution_table))
    aliases = load_reviewed_aliases(personal_rules)
    known_countries = {
        canonical_country(row.get("affilgood_location_country"))
        for row in table["rows"]
        if canonical_country(row.get("affilgood_location_country"))
    }
    known_cities = {
        normalized_key(row.get("affilgood_location_city"))
        for row in table["rows"]
        if normalized_key(row.get("affilgood_location_city"))
    }
    with input_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        source_fields = list(reader.fieldnames or [])
        rows = [enrich_row(row, table, aliases, known_countries, known_cities) for row in reader]
    fields = source_fields + [field for field in OUTPUT_FIELDS if field not in source_fields]
    write_csv(output_path, rows, fields)
    return {
        "input": str(input_path.resolve()),
        "output": str(output_path.resolve()),
        "rows": len(rows),
        "complete": sum(row["primary_match_status"] == "complete" for row in rows),
        "needs_supplement": sum(row["primary_match_status"] != "complete" for row in rows),
    }


def process_directory(
    input_dir: Path,
    output_dir: Path,
    institution_table: Path,
    personal_rules: Path,
) -> dict[str, Any]:
    table = load_institution_table(str(institution_table))
    aliases = load_reviewed_aliases(personal_rules)
    known_countries = {
        canonical_country(row.get("affilgood_location_country"))
        for row in table["rows"]
        if canonical_country(row.get("affilgood_location_country"))
    }
    known_cities = {
        normalized_key(row.get("affilgood_location_city"))
        for row in table["rows"]
        if normalized_key(row.get("affilgood_location_city"))
    }
    files = sorted(input_dir.glob("*_affilgood_作者机构拆分_output.csv"))
    files = [path for path in files if path.name.split("_", 1)[0].casefold() in CONFERENCES]
    if not files:
        raise FileNotFoundError(f"no three-conference AffilGood CSV files found in {input_dir}")

    combined: list[dict[str, str]] = []
    field_order: list[str] = []
    by_file = []
    for input_path in files:
        with input_path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            source_fields = list(reader.fieldnames or [])
            rows = [enrich_row(row, table, aliases, known_countries, known_cities) for row in reader]
        fields = source_fields + [field for field in OUTPUT_FIELDS if field not in source_fields]
        if not field_order:
            field_order = fields
        output_path = output_dir / input_path.name.replace(
            "_affilgood_作者机构拆分_output.csv", "_主体机构.csv"
        )
        write_csv(output_path, rows, fields)
        combined.extend(rows)
        by_file.append({
            "input": str(input_path),
            "output": str(output_path),
            "rows": len(rows),
            "complete": sum(row["primary_match_status"] == "complete" for row in rows),
            "needs_supplement": sum(row["primary_match_status"] != "complete" for row in rows),
        })

    combined_path = output_dir / "三大密码会_2020-2025_主体机构.csv"
    review_path = output_dir / "三大密码会_2020-2025_主体机构_补充队列.csv"
    report_path = output_dir / "三大密码会_2020-2025_主体机构_报告.json"
    write_csv(combined_path, combined, field_order)
    review_rows = [row for row in combined if row["primary_match_status"] != "complete"]
    write_csv(review_path, review_rows, field_order)
    statuses = Counter(row["primary_match_status"] for row in combined)
    reasons = Counter(
        reason
        for row in review_rows
        for reason in row["primary_review_reason"].split(";")
        if reason
    )
    report = {
        "input_dir": str(input_dir.resolve()),
        "institution_table": str(institution_table.resolve()),
        "files": len(files),
        "rows": len(combined),
        "complete": statuses["complete"],
        "needs_supplement": statuses["needs_supplement"],
        "missing_primary_institution": reasons["missing_primary_institution"],
        "missing_country": reasons["missing_country"],
        "missing_ror": sum(
            bool(row["primary_institution"]) and not bool(row["primary_ror_id"])
            for row in combined
        ),
        "missing_institution_id": reasons["missing_institution_id"],
        "by_file": by_file,
        "combined_output": str(combined_path),
        "supplement_queue": str(review_path),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Process one conference/year CSV.")
    parser.add_argument("--output", type=Path, help="Output path used with --input.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--institution-table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--personal-rules", type=Path, default=DEFAULT_RULES)
    args = parser.parse_args()
    if bool(args.input) != bool(args.output):
        parser.error("--input and --output must be supplied together")
    if args.input:
        report = process_file(
            args.input, args.output, args.institution_table, args.personal_rules
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    report = process_directory(
        args.input_dir, args.output_dir, args.institution_table, args.personal_rules
    )
    print(json.dumps({key: report[key] for key in (
        "files", "rows", "complete", "needs_supplement", "missing_primary_institution",
        "missing_country", "missing_ror", "missing_institution_id", "combined_output", "supplement_queue",
    )}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
