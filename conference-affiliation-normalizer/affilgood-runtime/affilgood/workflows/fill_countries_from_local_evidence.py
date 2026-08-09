#!/usr/bin/env python3
"""Fill missing institution countries from unique local evidence."""

import csv
import glob
import re
import shutil
import unicodedata
from collections import defaultdict
from pathlib import Path


def key(value):
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]", "", value)


def main():
    data_dir = Path(__file__).resolve().parents[2] / "data"
    path = data_dir / "institution_raw.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields, rows = list(reader.fieldnames or []), list(reader)

    by_id = defaultdict(set)
    by_name = defaultdict(set)
    for row in rows:
        country = row["affilgood_location_country"].strip()
        if country:
            by_id[row["conference_id"]].add(country)
            by_name[key(row["affilgood_institutions"])].add(country)

    output_by_name = defaultdict(set)
    for output_path in data_dir.glob("*_affilgood_作者机构拆分_output.csv"):
        with output_path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                country = row["affilgood_location_country"].strip()
                if not country:
                    continue
                for name in row["affilgood_institutions"].split(" | "):
                    if key(name):
                        output_by_name[key(name)].add(country)

    counts = defaultdict(int)
    for row in rows:
        if row["affilgood_location_country"].strip():
            continue
        name_key = key(row["affilgood_institutions"])
        if len(by_id[row["conference_id"]]) == 1:
            row["affilgood_location_country"] = next(iter(by_id[row["conference_id"]]))
            counts["same_conference_id"] += 1
        elif len(by_name[name_key]) == 1:
            row["affilgood_location_country"] = next(iter(by_name[name_key]))
            counts["same_name"] += 1
        elif len(output_by_name[name_key]) == 1:
            row["affilgood_location_country"] = next(iter(output_by_name[name_key]))
            counts["conference_output"] += 1

    backup = path.with_name(path.stem + ".before_deterministic_country_fill" + path.suffix)
    if not backup.exists():
        shutil.copy2(path, backup)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(dict(counts), "total", sum(counts.values()), "remaining", sum(not r["affilgood_location_country"] for r in rows))
    print(f"backup={backup}")


if __name__ == "__main__":
    main()
