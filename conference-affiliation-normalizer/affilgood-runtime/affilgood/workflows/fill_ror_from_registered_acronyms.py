#!/usr/bin/env python3
"""Fill missing ROR IDs using group evidence and strict registered acronyms."""

import csv
import json
import re
import shutil
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from affilgood.components.entity_linking.registry import RegistryManager


def key(value):
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]", "", value)


def number(value):
    match = re.fullmatch(r"INST(\d+)", value or "")
    return int(match.group(1)) if match else 10**12


def acronym_style(value):
    letters = [char for char in value if char.isalpha()]
    return len(letters) >= 4 and sum(char.isupper() for char in letters) / len(letters) >= 0.75


def fill(row, record, source):
    row["affilgood_ror_ids"] = record.id
    row["affilgood_standard_institutions"] = record.name
    row["affilgood_standardization_source"] = source


def main():
    data_dir = Path(__file__).resolve().parents[2] / "data"
    path = data_dir / "institution_raw.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields, rows = list(reader.fieldnames or []), list(reader)

    records = RegistryManager().get_records("ror", active_only=True)
    by_id = {record.id: record for record in records}
    acronym_index = defaultdict(dict)
    for record in records:
        for acronym in record.acronyms:
            if key(acronym):
                acronym_index[key(acronym)][record.id] = record

    report = []
    by_group = defaultdict(list)
    for row in rows:
        by_group[row["conference_id"]].append(row)

    propagated = 0
    for conference_id, group in by_group.items():
        rors = {row["affilgood_ror_ids"].strip() for row in group if row["affilgood_ror_ids"].strip()}
        if len(rors) != 1:
            continue
        ror = next(iter(rors))
        record = by_id.get(ror)
        if not record:
            continue
        for row in group:
            if row["affilgood_ror_ids"].strip():
                continue
            fill(row, record, "ror_group_propagation")
            propagated += 1
            report.append(["accepted", "same_conference_id_unique_ror", conference_id,
                           row["affilgood_institutions"], record.id, record.name,
                           record.country, ""])

    acronym_filled = 0
    for row in rows:
        if row["affilgood_ror_ids"].strip() or not acronym_style(row["affilgood_institutions"]):
            continue
        candidates = list(acronym_index.get(key(row["affilgood_institutions"]), {}).values())
        if not candidates:
            continue
        country = row["affilgood_location_country"].strip().casefold()
        selected = None
        reason = ""
        if len(candidates) == 1:
            selected = candidates[0]
            reason = "globally_unique_registered_acronym"
        elif country:
            same_country = [candidate for candidate in candidates if candidate.country.casefold() == country]
            if len(same_country) == 1:
                selected = same_country[0]
                reason = "registered_acronym_country"
        if selected:
            fill(row, selected, "ror_registered_acronym")
            acronym_filled += 1
            report.append(["accepted", reason, row["conference_id"], row["affilgood_institutions"],
                           selected.id, selected.name, selected.country, ""])
        else:
            report.append(["needs_review", "ambiguous_or_country_conflict", row["conference_id"],
                           row["affilgood_institutions"], "", "", "",
                           json.dumps([candidate.to_dict() for candidate in candidates], ensure_ascii=False)])

    # A newly accepted acronym establishes the same ROR for all aliases that
    # already share its conference ID.
    by_group.clear()
    for row in rows:
        by_group[row["conference_id"]].append(row)
    second_propagated = 0
    for conference_id, group in by_group.items():
        rors = {row["affilgood_ror_ids"].strip() for row in group if row["affilgood_ror_ids"].strip()}
        if len(rors) != 1:
            continue
        record = by_id.get(next(iter(rors)))
        if not record:
            continue
        for row in group:
            if not row["affilgood_ror_ids"].strip():
                fill(row, record, "ror_group_propagation")
                second_propagated += 1

    # Collapse current institution groups when the exact same ROR now proves
    # that they are aliases of one organization.
    ids_by_ror = defaultdict(set)
    for row in rows:
        if row["affilgood_ror_ids"].strip():
            ids_by_ror[row["affilgood_ror_ids"].strip()].add(row["conference_id"])
    target_by_ror = {
        ror: min(ids, key=number) for ror, ids in ids_by_ror.items()
    }
    merged_ids = set()
    for row in rows:
        ror = row["affilgood_ror_ids"].strip()
        if ror and row["conference_id"] != target_by_ror[ror]:
            merged_ids.add(row["conference_id"])
            row["conference_id"] = target_by_ror[ror]

    backup = path.with_name(path.stem + ".before_acronym_ror_fill" + path.suffix)
    if not backup.exists():
        shutil.copy2(path, backup)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    report_path = data_dir / "institution_ror_acronym_review.csv"
    with report_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["status", "reason", "conference_id", "observed_name", "ror_id",
                         "ror_name", "ror_country", "candidates_json"])
        writer.writerows(report)
    print(f"group_propagated={propagated + second_propagated}; acronym_filled={acronym_filled}; "
          f"merged_source_ids={len(merged_ids)}")
    print(f"backup={backup}; report={report_path}")


if __name__ == "__main__":
    main()
