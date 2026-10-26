#!/usr/bin/env python3
"""Synchronize reviewed institution metadata into conference output CSVs.

The reviewed institution table is authoritative for local institution IDs, ROR
IDs, countries, and cities. Raw affiliation and AffilGood evidence fields are
left unchanged.
"""

import argparse
import csv
import re
import shutil
import tempfile
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


SYNC_FIELDS = (
    "affilgood_ror_ids",
    "affilgood_location_country",
    "affilgood_location_city",
)


def split_tokens(value):
    return [part.strip() for part in (value or "").split(" | ") if part.strip()]


def unique(values):
    return list(dict.fromkeys(value for value in values if value))


def name_key(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = value.encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]", "", value)


class InstitutionIndex:
    def __init__(self, rows):
        self.by_id = defaultdict(list)
        for row in rows:
            source_id = row.get("conference_id", "").strip()
            final_id = row.get("conference_final_id", "").strip()
            if not source_id or not final_id:
                raise ValueError("institution_raw.csv contains a blank conference ID")
            self.by_id[source_id].append(row)
            if final_id != source_id:
                self.by_id[final_id].append(row)

    def candidates(self, institution_id, names):
        candidates = self.by_id.get(institution_id, [])
        if not candidates:
            return [], "missing"

        keys = {name_key(name) for name in names if name_key(name)}
        observed = [
            row for row in candidates
            if name_key(row.get("affilgood_institutions")) in keys
        ]
        if observed:
            return observed, "observed_name"

        standard = [
            row for row in candidates
            if name_key(row.get("affilgood_standard_institutions")) in keys
        ]
        if standard:
            return standard, "standard_name"
        return candidates, "institution_id"


def resolve_value(candidates, field):
    values = unique(row.get(field, "").strip() for row in candidates)
    if len(values) > 1:
        return None
    return values[0] if values else ""


def synchronize_row(row, index):
    names = split_tokens(row.get("affilgood_institutions"))
    source_ids = split_tokens(row.get("conference_id"))
    if not source_ids:
        return Counter(), []

    resolutions = []
    conflicts = []
    final_ids = []
    for position, source_id in enumerate(source_ids):
        scoped_names = [names[position]] if len(names) == len(source_ids) else names
        candidates, match_mode = index.candidates(source_id, scoped_names)
        if not candidates:
            conflicts.append((source_id, "conference_id", "missing", match_mode))
            continue

        candidate_final_ids = unique(
            candidate.get("conference_final_id", "").strip()
            for candidate in candidates
        )
        if len(candidate_final_ids) != 1:
            conflicts.append(
                (source_id, "conference_id", " | ".join(candidate_final_ids), match_mode)
            )
            continue
        final_ids.append(candidate_final_ids[0])
        resolutions.append((source_id, candidates, match_mode))

    if conflicts or len(resolutions) != len(source_ids):
        return Counter(), conflicts

    changes = Counter()
    desired_id = " | ".join(unique(final_ids))
    if row.get("conference_id", "") != desired_id:
        row["conference_id"] = desired_id
        changes["conference_id"] += 1

    for field in SYNC_FIELDS:
        values = []
        field_conflicts = []
        for source_id, candidates, match_mode in resolutions:
            value = resolve_value(candidates, field)
            if value is None:
                choices = " | ".join(
                    unique(candidate.get(field, "").strip() for candidate in candidates)
                )
                field_conflicts.append((source_id, field, choices, match_mode))
            elif value:
                values.extend(split_tokens(value))
        if field_conflicts:
            conflicts.extend(field_conflicts)
            continue

        desired = " | ".join(unique(values))
        # A blank reviewed city does not erase a more specific extracted city.
        if field == "affilgood_location_city" and not desired:
            continue
        if row.get(field, "") != desired:
            row[field] = desired
            changes[field] += 1

    return changes, conflicts


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv_atomic(path, fields, rows):
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        temporary = Path(handle.name)
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir", type=Path)
    parser.add_argument(
        "--apply", action="store_true",
        help="write changes; without this flag only report the proposed synchronization",
    )
    parser.add_argument(
        "--backup-dir", type=Path,
        help="optional directory for pre-write CSV snapshots",
    )
    args = parser.parse_args()

    institution_path = args.data_dir / "institution_raw.csv"
    _, institution_rows = read_csv(institution_path)
    index = InstitutionIndex(institution_rows)

    all_conflicts = []
    totals = Counter()
    paths = sorted(args.data_dir.glob("*_affilgood_作者机构拆分_output.csv"))
    if not paths:
        raise SystemExit(f"no conference output CSVs found in {args.data_dir}")

    for path in paths:
        fields, rows = read_csv(path)
        missing_fields = {"conference_id", "affilgood_institutions", *SYNC_FIELDS} - set(fields)
        if missing_fields:
            raise SystemExit(f"{path.name}: missing fields: {sorted(missing_fields)}")

        file_changes = Counter()
        for line_number, row in enumerate(rows, start=2):
            changes, conflicts = synchronize_row(row, index)
            file_changes.update(changes)
            for conflict in conflicts:
                all_conflicts.append((path.name, line_number, row.get("paper_id", ""), *conflict))

        if args.apply and file_changes:
            if args.backup_dir:
                args.backup_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, args.backup_dir / path.name)
            write_csv_atomic(path, fields, rows)
        totals.update(file_changes)
        details = ", ".join(f"{field}={file_changes[field]}" for field in ("conference_id", *SYNC_FIELDS))
        print(f"{path.name}: rows={len(rows)}; {details}")

    print("mode=" + ("apply" if args.apply else "dry-run"))
    print("totals=" + ", ".join(f"{field}={totals[field]}" for field in ("conference_id", *SYNC_FIELDS)))
    print(f"conflicts={len(all_conflicts)}")
    for conflict in all_conflicts[:50]:
        print("CONFLICT " + "\t".join(str(value) for value in conflict))
    if len(all_conflicts) > 50:
        print(f"... {len(all_conflicts) - 50} additional conflicts omitted")


if __name__ == "__main__":
    main()
