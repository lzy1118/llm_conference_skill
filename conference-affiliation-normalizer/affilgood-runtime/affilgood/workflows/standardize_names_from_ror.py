#!/usr/bin/env python3
"""Add ROR canonical institution names without discarding observed aliases."""

import argparse
import csv
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from affilgood.components.entity_linking.registry import RegistryManager


GENERIC = {
    "security", "cybersecurity", "cryptography", "computer", "science",
    "technology", "information", "systems", "lab", "labs", "research",
    "center", "centre", "institute", "university", "department", "school",
    "faculty", "college", "laboratory", "laboratories",
}


def compact(value):
    return "".join(re.findall(r"[a-z0-9]", (value or "").casefold()))


def significant_tokens(value):
    stop = {"of", "the", "and", "for", "in", "at", "a", "an", "inc", "ltd", "llc", "co", "corp", "company"}
    return {token for token in re.findall(r"[a-z0-9]+", (value or "").casefold()) if token not in stop | GENERIC}


def initialism(value):
    ignored = {"of", "the", "and", "for", "in", "at", "a", "an"}
    return "".join(word[0] for word in re.findall(r"[A-Za-z0-9]+", value or "") if word.casefold() not in ignored)


def explicit_match(observed, record):
    observed_key = compact(observed)
    if len(observed_key) < 2:
        return False
    observed_terms = significant_tokens(observed)
    canonical_key = compact(record.name)
    if observed_terms and len(observed_key) >= 4 and (
        observed_key in canonical_key or canonical_key in observed_key
    ):
        return True
    if observed_key.upper() == compact(initialism(record.name)).upper():
        return True
    if any(observed_key == compact(acronym) for acronym in record.acronyms):
        return True
    canonical_terms = significant_tokens(record.name)
    obvious_abbreviation = not re.search(r"\s", observed.strip()) and len(observed_key) <= 12
    for alias in [*record.aliases, *record.labels]:
        # A historical ROR alias can establish a match only when the official
        # ROR name also retains a distinctive term from the observed name.
        # This blocks stale alias links such as UPMC -> a named hospital.
        if compact(observed) == compact(alias) and (
            observed_terms & canonical_terms or obvious_abbreviation
        ):
            return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    with args.input_csv.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields, rows = list(reader.fieldnames or []), list(reader)

    ror_records = {record.id: record for record in RegistryManager().get_records("ror", active_only=False)}
    for field in ("affilgood_standard_institutions", "affilgood_standardization_source"):
        if field not in fields:
            fields.append(field)

    standardized = 0
    needs_review = 0
    no_ror = 0
    for row in rows:
        ror_ids = [value.strip() for value in row.get("affilgood_ror_ids", "").split(" | ") if value.strip()]
        records = [ror_records[value] for value in ror_ids if value in ror_records]
        observed = [value.strip() for value in row.get("affilgood_institutions", "").split(" | ") if value.strip()]
        canonical = [record.name for record in records]
        evidence_ok = len(observed) == len(records) and all(
            explicit_match(value, record) for value, record in zip(observed, records)
        )
        if canonical and len(canonical) == len(ror_ids) and evidence_ok:
            row["affilgood_standard_institutions"] = " | ".join(canonical)
            row["affilgood_standardization_source"] = "ror"
            standardized += 1
        else:
            row["affilgood_standard_institutions"] = ""
            row["affilgood_standardization_source"] = "needs_review" if ror_ids else "unresolved"
            needs_review += bool(ror_ids)
            no_ror += not bool(ror_ids)

    if not args.no_backup:
        backup = args.input_csv.with_name(args.input_csv.stem + ".before_ror_standardization" + args.input_csv.suffix)
        if not backup.exists():
            shutil.copy2(args.input_csv, backup)
            print(f"backup: {backup}")
    with args.input_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"standardized={standardized}; needs_review={needs_review}; unresolved={no_ror}; total={len(rows)}")


if __name__ == "__main__":
    main()
