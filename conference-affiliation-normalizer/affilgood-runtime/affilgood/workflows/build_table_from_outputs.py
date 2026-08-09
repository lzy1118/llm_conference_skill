#!/usr/bin/env python3
"""Rebuild institution IDs and dictionary from conference output CSVs."""

import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from affilgood.components.entity_linking.registry import RegistryManager


BAD_STANDALONE = {
    "and", "or", "the", "of", "at", "in", "inc", "incorporated", "ltd",
    "limited", "co", "company", "research", "technology", "engineering",
    "university", "institute", "security", "state",
}


def name_key(value):
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().casefold().strip()
    value = re.sub(
        r"(?:[,\s]+)(?:incorporated|corporation|company|limited|inc|corp|llc|ltd|gmbh|plc|sarl|sas|co)\.?$",
        "",
        value,
    )
    return re.sub(r"[^a-z0-9]", "", value)


def split(value):
    return [part.strip() for part in (value or "").split(" | ") if part.strip()]


def bad_slice(value):
    text = " ".join((value or "").split()).strip()
    alphanumeric = "".join(char for char in text if char.isalnum())
    normalized = text.casefold().strip(".,;:()[]{}")
    return (
        len(alphanumeric) <= 1
        or alphanumeric.isdigit()
        or normalized in BAD_STANDALONE
        or bool(re.search(r"\b(?:and|or)$", normalized))
    )


def json_ror_map(row):
    result = defaultdict(set)
    try:
        outputs = json.loads(row.get("affilgood_output_json", "")) if row.get("affilgood_output_json") else []
    except json.JSONDecodeError:
        return result
    if isinstance(outputs, dict):
        outputs = [outputs]
    for output in outputs:
        for institution in output.get("institutions") or []:
            identifier = institution.get("id")
            ror = identifier.get("ror_id") if isinstance(identifier, dict) else identifier
            if not ror:
                continue
            for value in (institution.get("name"), institution.get("raw")):
                if name_key(value):
                    result[name_key(value)].add(ror)
    return result


def mode(values):
    values = [value for value in values if value]
    if not values:
        return ""
    counts = Counter(values)
    highest = max(counts.values())
    return sorted(value for value, count in counts.items() if count == highest)[0]


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    data_dir = Path(__file__).resolve().parents[2] / "data"
    output_paths = sorted(data_dir.glob("*_affilgood_作者机构拆分_output.csv"))
    registry = {record.id: record for record in RegistryManager().get_records("ror", active_only=False)}

    conference_data = []
    global_evidence = defaultdict(set)
    for path in output_paths:
        fields, rows = read(path)
        conference_data.append((path, fields, rows))
        for row in rows:
            names = split(row["affilgood_institutions"])
            rors = split(row["affilgood_ror_ids"])
            if len(names) == len(rors):
                for name, ror in zip(names, rors):
                    if ror in registry:
                        global_evidence[name_key(name)].add(ror)
            for key, values in json_ror_map(row).items():
                global_evidence[key].update(value for value in values if value in registry)
    unique_global_ror = {
        key: next(iter(values)) for key, values in global_evidence.items() if len(values) == 1
    }

    identity_data = defaultdict(lambda: {
        "aliases": set(), "countries": [], "cities": [], "ror": "", "bad": False,
    })
    row_identities = {}
    for path, _, rows in conference_data:
        for row_index, row in enumerate(rows):
            names = split(row["affilgood_institutions"])
            top_rors = split(row["affilgood_ror_ids"])
            local = json_ror_map(row)
            identities = []
            for index, name in enumerate(names):
                ror = ""
                if len(names) == len(top_rors) and index < len(top_rors) and top_rors[index] in registry:
                    ror = top_rors[index]
                if not ror and len(local[name_key(name)]) == 1:
                    candidate = next(iter(local[name_key(name)]))
                    if candidate in registry:
                        ror = candidate
                if not ror:
                    ror = unique_global_ror.get(name_key(name), "")
                identity = ("ror", ror) if ror else ("name", name_key(name))
                if not identity[1]:
                    continue
                data = identity_data[identity]
                data["aliases"].add(name)
                data["countries"].append(row["affilgood_location_country"].strip())
                data["cities"].append(row["affilgood_location_city"].strip())
                data["ror"] = ror
                data["bad"] = data["bad"] or bad_slice(name)
                identities.append(identity)
            row_identities[(path, row_index)] = list(dict.fromkeys(identities))

    ror_identities = sorted(
        (identity for identity in identity_data if identity[0] == "ror"),
        key=lambda identity: (registry[identity[1]].name.casefold(), identity[1]),
    )
    name_identities = sorted(
        (identity for identity in identity_data if identity[0] == "name"),
        key=lambda identity: identity[1],
    )
    ordered = ror_identities + name_identities
    assigned = {identity: f"INST{index:04d}" for index, identity in enumerate(ordered)}

    dictionary_rows = []
    for identity in ordered:
        data = identity_data[identity]
        institution_id = assigned[identity]
        record = registry.get(data["ror"])
        country = record.country if record else mode(data["countries"])
        city = record.city if record else mode(data["cities"])
        standard = record.name if record else ""
        source = "ror" if record else ("unresolved" if data["bad"] else "")
        for alias in sorted(data["aliases"], key=str.casefold):
            dictionary_rows.append({
                "affilgood_ror_ids": data["ror"],
                "conference_id": institution_id,
                "affilgood_institutions": alias,
                "affilgood_location_country": country,
                "affilgood_location_city": city,
                "conference_final_id": institution_id,
                "affilgood_standard_institutions": standard,
                "affilgood_standardization_source": source,
            })

    for path, fields, rows in conference_data:
        for row_index, row in enumerate(rows):
            identities = row_identities[(path, row_index)]
            ids = [assigned[identity] for identity in identities]
            names = []
            rors = []
            for identity in identities:
                data = identity_data[identity]
                record = registry.get(data["ror"])
                names.append(record.name if record else sorted(data["aliases"], key=str.casefold)[0])
                if data["ror"]:
                    rors.append(data["ror"])
            row["conference_id"] = " | ".join(ids)
            row["affilgood_institutions"] = " | ".join(names)
            row["affilgood_ror_ids"] = " | ".join(rors)
        write(path, fields, rows)
        print(f"wrote {path.name}: {len(rows)} rows")

    institution_fields = [
        "affilgood_ror_ids", "conference_id", "affilgood_institutions",
        "affilgood_location_country", "affilgood_location_city", "conference_final_id",
        "affilgood_standard_institutions", "affilgood_standardization_source",
    ]
    write(data_dir / "institution_raw.csv", institution_fields, dictionary_rows)
    print(
        f"identities={len(ordered)}; ror={len(ror_identities)}; no_ror={len(name_identities)}; "
        f"dictionary_rows={len(dictionary_rows)}"
    )


if __name__ == "__main__":
    main()
