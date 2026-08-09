#!/usr/bin/env python3
"""Apply reviewed personal affiliation rules to AffilGood public output."""

from __future__ import annotations

import copy
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_RULES = Path(__file__).resolve().parents[1] / "references" / "personal-rules.json"


def normalized_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return "".join(char for char in text.casefold() if char.isalnum())


def load_rules(path: Optional[str] = None) -> Dict[str, Any]:
    rule_path = Path(path).expanduser() if path else DEFAULT_RULES
    with rule_path.open(encoding="utf-8") as handle:
        rules = json.load(handle)
    if rules.get("schema_version") != "1.0":
        raise ValueError(f"Unsupported personal rule schema: {rules.get('schema_version')!r}")
    return rules


def _outputs(payload: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(payload, list):
        for item in payload:
            yield from _outputs(item)
    elif isinstance(payload, dict):
        outputs = payload.get("outputs")
        if isinstance(outputs, list):
            for item in outputs:
                if isinstance(item, dict):
                    yield item
        elif "institutions" in payload:
            yield payload


def _ror_id(rule: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not rule.get("ror_id"):
        return None
    return {
        "ror_id": rule["ror_id"],
        "ror_name": rule["canonical_name"],
        "ror_country": rule.get("country"),
        "ror_city": rule.get("city"),
    }


def _institution(rule: Dict[str, Any], raw: str) -> Dict[str, Any]:
    return {
        "name": rule["canonical_name"],
        "raw": raw or rule["canonical_name"],
        "id": _ror_id(rule),
        "confidence": 1.0,
        "source": "personal_reviewed_rule",
        "personal_rule_id": rule["id"],
    }


def _set_location(output: Dict[str, Any], rule: Dict[str, Any]) -> None:
    if not rule.get("country") and not rule.get("city"):
        return
    location = dict(output.get("location") or {})
    sources = dict(location.get("source") or {})
    for field in ("country", "city"):
        if rule.get(field):
            location[field] = rule[field]
            sources[field] = "personal_reviewed_rule"
    location["source"] = sources
    output["location"] = location


def _context_matches(source_record: Dict[str, Any], wanted: Dict[str, Any]) -> bool:
    return all(normalized_key(source_record.get(key)) == normalized_key(value) for key, value in wanted.items())


def apply_personal_rules(
    payload: Any,
    rules: Dict[str, Any],
    source_record: Optional[Dict[str, Any]] = None,
) -> Any:
    result = copy.deepcopy(payload)
    source_record = source_record or {}
    applied: List[str] = []

    alias_map = {}
    for rule in rules.get("aliases", []):
        for alias in rule.get("aliases", []):
            alias_map[normalized_key(alias)] = rule

    compiled_patterns = [
        (
            rule,
            re.compile(rule["pattern"], re.IGNORECASE),
            re.compile(rule["exclude_pattern"], re.IGNORECASE) if rule.get("exclude_pattern") else None,
        )
        for rule in rules.get("patterns", [])
    ]

    output_items = list(_outputs(result))
    scoped = next(
        (
            rule for rule in rules.get("scoped_replacements", [])
            if _context_matches(source_record, rule.get("match", {}))
        ),
        None,
    )
    if scoped and output_items:
        output_items[0]["institutions"] = [
            _institution({**item, "id": scoped["id"], "canonical_name": item["name"]}, item.get("raw", ""))
            for item in scoped.get("institutions", [])
        ]
        _set_location(output_items[0], scoped)
        applied.append(scoped["id"])

    for output in output_items:
        if scoped:
            continue

        institutions = output.get("institutions")
        if not isinstance(institutions, list):
            continue
        matched_rules = []
        for index, institution in enumerate(institutions):
            if not isinstance(institution, dict):
                continue
            observed = institution.get("raw") or institution.get("name") or ""
            rule = alias_map.get(normalized_key(observed))
            if rule:
                institutions[index] = _institution(rule, observed)
                matched_rules.append(rule)
                applied.append(rule["id"])

        input_text = str(output.get("input") or "")
        for rule, pattern, exclude in compiled_patterns:
            if not pattern.search(input_text) or (exclude and exclude.search(input_text)):
                continue
            reject = set(rule.get("reject_ror_ids", []))
            kept = []
            for institution in institutions:
                if not isinstance(institution, dict):
                    kept.append(institution)
                    continue
                identity = institution.get("id") if isinstance(institution.get("id"), dict) else {}
                observed = f"{institution.get('name', '')} {institution.get('raw', '')}"
                if identity.get("ror_id") in reject or pattern.search(observed):
                    continue
                kept.append(institution)
            kept.append(_institution(rule, rule["canonical_name"]))
            output["institutions"] = institutions = kept
            matched_rules.append(rule)
            applied.append(rule["id"])

        if len(institutions) == 1 and matched_rules:
            _set_location(output, matched_rules[-1])
            output["confidence"] = 1.0

    if isinstance(result, dict) and applied:
        result["_personal_rules"] = list(dict.fromkeys(applied))
    return result
