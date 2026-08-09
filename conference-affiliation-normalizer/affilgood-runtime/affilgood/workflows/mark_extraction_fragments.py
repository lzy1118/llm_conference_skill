#!/usr/bin/env python3
"""Reserve the unresolved status for obvious extraction fragments only."""

import csv
import re
import shutil
from pathlib import Path


BAD_STANDALONE = {
    "and", "or", "the", "of", "at", "in", "inc", "incorporated", "ltd",
    "limited", "co", "company", "research", "technology", "engineering",
    "university", "institute", "security", "state",
}


def is_bad_slice(value):
    text = " ".join((value or "").split()).strip()
    alphanumeric = "".join(char for char in text if char.isalnum())
    normalized = text.casefold().strip(".,;:()[]{}")
    return (
        len(alphanumeric) <= 1
        or alphanumeric.isdigit()
        or normalized in BAD_STANDALONE
        or bool(re.search(r"\b(?:and|or)$", normalized))
    )


def main():
    path = Path(__file__).resolve().parents[2] / "data" / "institution_raw.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields, rows = list(reader.fieldnames or []), list(reader)
    unresolved = 0
    cleared = 0
    for row in rows:
        if row["affilgood_ror_ids"].strip():
            continue
        desired = "unresolved" if is_bad_slice(row["affilgood_institutions"]) else ""
        if desired == "unresolved":
            unresolved += 1
        if row.get("affilgood_standardization_source", "") != desired:
            if not desired:
                cleared += 1
            row["affilgood_standardization_source"] = desired
    backup = path.with_name(path.stem + ".before_unresolved_slice_cleanup" + path.suffix)
    if not backup.exists():
        shutil.copy2(path, backup)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"unresolved={unresolved}; cleared={cleared}; backup={backup}")


if __name__ == "__main__":
    main()
