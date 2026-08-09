#!/usr/bin/env python3
"""Assign conservative final institution IDs for obvious name variants."""

import argparse
import csv
import re
import shutil
import unicodedata
from collections import defaultdict
from pathlib import Path


def compact(value):
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().casefold()
    value = re.sub(
        r"(?:[,\s]+)(?:incorporated|corporation|company|limited|inc|corp|llc|ltd|gmbh|plc|sarl|sas|co)\.?$",
        "",
        value.strip(),
    )
    return re.sub(r"[^a-z0-9]", "", value)


def visible(value):
    value = unicodedata.normalize("NFKC", value or "").casefold().strip()
    return " ".join(value.split())


def id_number(value):
    match = re.fullmatch(r"INST(\d+)", value or "")
    return int(match.group(1)) if match else 10**12


class UnionFind:
    def __init__(self, values):
        self.parent = {value: value for value in values}

    def find(self, value):
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, values):
        values = list(dict.fromkeys(values))
        if len(values) < 2:
            return
        root = min((self.find(value) for value in values), key=id_number)
        for value in values:
            self.parent[self.find(value)] = root


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", type=Path)
    args = parser.parse_args()

    with args.input_csv.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields, rows = list(reader.fieldnames or []), list(reader)
    if "conference_final_id" not in fields:
        fields.append("conference_final_id")

    ids = {row["conference_id"].strip() for row in rows if row.get("conference_id", "").strip()}
    union = UnionFind(ids)
    reasons = []

    by_ror = defaultdict(list)
    for row in rows:
        ror = row.get("affilgood_ror_ids", "").strip()
        if ror:
            by_ror[ror].append(row)
    for ror, group in by_ror.items():
        group_ids = {row["conference_id"] for row in group}
        if len(group_ids) > 1:
            union.union(group_ids)
            reasons.append(("same_ror", ror, sorted(group_ids, key=id_number)))

    by_name = defaultdict(list)
    for row in rows:
        key = compact(row.get("affilgood_institutions", ""))
        if key:
            by_name[key].append(row)

    for key, group in by_name.items():
        group_ids = {row["conference_id"] for row in group}
        if len(group_ids) < 2:
            continue
        rors = {row["affilgood_ror_ids"].strip() for row in group if row.get("affilgood_ror_ids", "").strip()}
        if len(rors) > 1:
            continue
        if len(rors) == 1:
            union.union(group_ids)
            reasons.append(("name_variant_single_ror", key, sorted(group_ids, key=id_number)))
            continue

        visible_forms = {visible(row.get("affilgood_institutions", "")) for row in group}
        if len(visible_forms) > 1:
            union.union(group_ids)
            reasons.append(("spacing_punctuation_case", key, sorted(group_ids, key=id_number)))
            continue

        by_country = defaultdict(set)
        blank_country = set()
        for row in group:
            country = visible(row.get("affilgood_location_country", ""))
            if country:
                by_country[country].add(row["conference_id"])
            else:
                blank_country.add(row["conference_id"])
        for country, country_ids in by_country.items():
            if len(country_ids) > 1:
                union.union(country_ids)
                reasons.append(("same_name_country", f"{key}|{country}", sorted(country_ids, key=id_number)))
        if len(by_country) == 1 and blank_country:
            all_ids = blank_country | next(iter(by_country.values()))
            union.union(all_ids)
            reasons.append(("same_name_blank_country", key, sorted(all_ids, key=id_number)))
        elif not by_country and len(blank_country) > 1:
            union.union(blank_country)
            reasons.append(("same_name_no_country", key, sorted(blank_country, key=id_number)))

    components = defaultdict(list)
    for value in ids:
        components[union.find(value)].append(value)
    final_by_id = {}
    for members in components.values():
        final_id = min(members, key=id_number)
        for member in members:
            final_by_id[member] = final_id

    for row in rows:
        source_id = row.get("conference_id", "").strip()
        row["conference_final_id"] = final_by_id.get(source_id, source_id)

    backup = args.input_csv.with_name(args.input_csv.stem + ".before_final_id_merge" + args.input_csv.suffix)
    if not backup.exists():
        shutil.copy2(args.input_csv, backup)
    with args.input_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    report = args.input_csv.with_name("institution_final_id_merge_report.csv")
    with report.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["reason", "match_key", "conference_ids", "conference_final_id"])
        for reason, key, members in reasons:
            finals = {final_by_id[value] for value in members}
            if len(set(members)) > 1 and len(finals) == 1:
                writer.writerow([reason, key, " | ".join(members), next(iter(finals))])

    merged_ids = sum(source != final for source, final in final_by_id.items())
    print(f"records={len(rows)}; source_ids={len(ids)}; final_ids={len(set(final_by_id.values()))}; merged_ids={merged_ids}")
    print(f"backup={backup}; report={report}")


if __name__ == "__main__":
    main()
