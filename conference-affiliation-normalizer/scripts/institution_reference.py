#!/usr/bin/env python3
"""Use institution_raw.csv as a conservative primary exact-reference layer."""

from __future__ import annotations

import csv
import copy
import os
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


DEFAULT_BUNDLED_TABLE = Path(__file__).resolve().parents[1] / "references" / "institution_raw.csv"


def normalized_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return "".join(char for char in text.casefold() if char.isalnum())


def default_table_path(affilgood_path: Optional[str] = None) -> Optional[Path]:
    candidates = []
    if os.environ.get("AFFILGOOD_INSTITUTION_TABLE"):
        candidates.append(Path(os.environ["AFFILGOOD_INSTITUTION_TABLE"]).expanduser())
    if affilgood_path:
        candidates.append(Path(affilgood_path).expanduser() / "data" / "institution_raw.csv")
    candidates.extend([
        DEFAULT_BUNDLED_TABLE,
    ])
    return next((path for path in candidates if path.is_file()), None)


def load_institution_table(path: Optional[str] = None, affilgood_path: Optional[str] = None) -> Dict[str, Any]:
    table_path = Path(path).expanduser() if path else default_table_path(affilgood_path)
    if table_path is None or not table_path.is_file():
        raise FileNotFoundError(
            "institution_raw.csv not found; pass --institution-table or set AFFILGOOD_INSTITUTION_TABLE"
        )
    with table_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    index = defaultdict(list)
    for row in rows:
        observed = row.get("affilgood_institutions", "").strip()
        standard = row.get("affilgood_standard_institutions", "").strip()
        keys = {normalized_key(observed), normalized_key(standard)} - {""}
        record = {
            "observed_name": observed,
            "standard_name": standard,
            "ror_id": row.get("affilgood_ror_ids", "").strip(),
            "country": row.get("affilgood_location_country", "").strip(),
            "city": row.get("affilgood_location_city", "").strip(),
            "conference_id": row.get("conference_id", "").strip(),
            "conference_final_id": row.get("conference_final_id", "").strip(),
            "standardization_source": row.get("affilgood_standardization_source", "").strip(),
            "notes": row.get("notes", "").strip(),
        }
        for key in keys:
            if record not in index[key]:
                index[key].append(record)
    return {"path": str(table_path), "rows": rows, "index": dict(index)}


def _candidate_key(candidate: Dict[str, Any]) -> tuple:
    stable_id = candidate.get("conference_final_id") or candidate.get("conference_id")
    if stable_id:
        return ("local_id", stable_id, str(candidate.get("country") or "").casefold())
    return (
        "institution",
        candidate.get("standard_name") or candidate.get("observed_name"),
        candidate.get("ror_id"),
        candidate.get("country"),
        candidate.get("city"),
    )


def _choose(candidates: Iterable[Dict[str, Any]], country: str) -> tuple[Optional[Dict[str, Any]], list[Dict[str, Any]]]:
    unique = []
    seen = set()
    for candidate in candidates:
        key = _candidate_key(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    if len(unique) == 1:
        return unique[0], unique
    if country:
        same_country = [candidate for candidate in unique if candidate.get("country", "").casefold() == country.casefold()]
        if len(same_country) == 1:
            return same_country[0], unique
        if same_country:
            unique = same_country
    return None, unique


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


def apply_institution_reference(payload: Any, table: Dict[str, Any]) -> Any:
    result = copy.deepcopy(payload)
    applied = []
    ambiguous = []
    for output in _outputs(result):
        output_country = str((output.get("location") or {}).get("country") or "")
        for institution in output.get("institutions") or []:
            if not isinstance(institution, dict):
                continue
            raw_observed = institution.get("raw") or ""
            name_observed = institution.get("name") or ""
            observed = raw_observed or name_observed
            candidate_groups = []
            for value in (raw_observed, name_observed):
                group = []
                seen_candidates = set()
                for candidate in table["index"].get(normalized_key(value), []):
                    candidate_key = _candidate_key(candidate)
                    if candidate_key not in seen_candidates:
                        seen_candidates.add(candidate_key)
                        group.append(candidate)
                if group:
                    candidate_groups.append(group)
            candidates = candidate_groups[0] if candidate_groups else []
            if not candidates:
                continue
            selected, all_candidates = _choose(candidates, output_country)
            if selected is None:
                ambiguous.append({"observed": observed, "candidates": all_candidates})
                continue
            standard_name = selected.get("standard_name") or selected.get("observed_name")
            institution["name"] = standard_name or institution.get("name", "")
            if selected.get("ror_id"):
                institution["id"] = {
                    "ror_id": selected["ror_id"],
                    "ror_name": standard_name,
                    "ror_country": selected.get("country"),
                    "ror_city": selected.get("city"),
                }
            reference = {
                "source": "institution_raw.csv",
                "observed_name": selected.get("observed_name"),
                "standard_name": standard_name,
                "conference_id": selected.get("conference_id"),
                "conference_final_id": selected.get("conference_final_id"),
                "standardization_source": selected.get("standardization_source"),
            }
            institution["institution_reference"] = reference
            applied.append(reference)
            location = dict(output.get("location") or {})
            sources = dict(location.get("source") or {})
            for field in ("country", "city"):
                if not location.get(field) and selected.get(field):
                    location[field] = selected[field]
                    sources[field] = "institution_raw.csv"
            if sources:
                location["source"] = sources
            if location:
                output["location"] = location

    if isinstance(result, dict):
        if applied:
            result["_institution_reference"] = {
                "source": Path(table["path"]).name,
                "matches": len(applied),
                "records": applied,
            }
        if ambiguous:
            result["_institution_reference_review"] = ambiguous
    return result
