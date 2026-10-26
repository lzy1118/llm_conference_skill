#!/usr/bin/env python3
"""Normalize four security-conference affiliation CSVs with resumable checkpoints.

The source CSVs are never changed.  Each distinct non-empty affiliation is sent to
AffilGood once, and the result is reused for every source row that has that text.
"""

import argparse
import csv
import json
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

# Expose the editable project root when this file is executed directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from affilgood import AffilGood


INPUTS = (
    "ieee_s&p_raw_作者机构拆分.csv",
    "ndss_raw_作者机构拆分.csv",
    "usenix_security_raw_作者机构拆分.csv",
    "ccs_raw_作者机构拆分.csv",
)
EXTRA_FIELDS = (
    "affilgood_raw_text", "affilgood_institutions", "conference_id",
    "affilgood_ror_ids", "affilgood_subunits", "affilgood_language",
    "affilgood_confidence", "affilgood_location_country",
    "affilgood_location_city", "affilgood_location_lat",
    "affilgood_location_lon", "affilgood_output_json",
)


def clean(value):
    return " ".join((value or "").split())


def key_name(value):
    """Conservative name key: only punctuation/case differences collapse."""
    return re.sub(r"[^a-z0-9]", "", (value or "").casefold())


def value_join(items, field):
    result = []
    for item in items or []:
        value = item.get(field)
        if isinstance(value, dict):
            value = value.get("ror_id") or value.get("ror_name")
        if value and str(value) not in result:
            result.append(str(value))
    return " | ".join(result)


def flatten(result):
    """Flatten every parsed segment while retaining institution-level identity."""
    outputs = result.get("outputs") or []
    output = outputs[0] if outputs else {}
    institutions = []
    subunits = []
    entries = []
    for segment in outputs:
        location = segment.get("location") or {}
        for institution in segment.get("institutions") or []:
            institutions.append(institution)
            identifier = institution.get("id")
            ror = identifier.get("ror_id", "") if isinstance(identifier, dict) else (identifier or "")
            entries.append({
                "name": institution.get("name", ""),
                "ror": ror,
                "country": location.get("country") or "",
                "city": location.get("city") or "",
            })
        subunits.extend(segment.get("subunits") or [])
    location = output.get("location") or {}
    return {
        "affilgood_raw_text": result.get("raw_text", ""),
        "affilgood_institutions": value_join(institutions, "name"),
        "affilgood_ror_ids": value_join(institutions, "id"),
        "affilgood_subunits": value_join(subunits, "name"),
        "affilgood_language": output.get("language") or "",
        "affilgood_confidence": output.get("confidence") or "",
        "affilgood_location_country": location.get("country") or "",
        "affilgood_location_city": location.get("city") or "",
        "affilgood_location_lat": location.get("lat") or "",
        "affilgood_location_lon": location.get("lon") or "",
        "affilgood_output_json": json.dumps(outputs, ensure_ascii=False, separators=(",", ":")),
        "institution_entries": entries,
    }


def read_checkpoint(path):
    results = {}
    if not path.exists():
        return results
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                entry = json.loads(line)
                results[entry["affiliation"]] = entry["result"]
            except (json.JSONDecodeError, KeyError):
                continue
    return results


def load_sources(data_dir):
    source_rows, texts = {}, set()
    for filename in INPUTS:
        with (data_dir / filename).open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        source_rows[filename] = rows
        texts.update(clean(row.get("affiliations")) for row in rows if clean(row.get("affiliations")))
    return source_rows, sorted(texts)


def process_texts(texts, checkpoint, batch_size):
    done = read_checkpoint(checkpoint)
    pending = [text for text in texts if text not in done]
    print(f"checkpoint: {len(done)}; pending: {len(pending)}")
    if not pending:
        return done

    ag = AffilGood(
        device="cpu", batch_size=batch_size, enable_entity_linking=True,
        enable_normalization=True, linking_config={"reranker": "cross_encoder"},
    )
    with checkpoint.open("a", encoding="utf-8") as handle:
        for offset in range(0, len(pending), batch_size):
            chunk = pending[offset : offset + batch_size]
            try:
                batch = ag.process(chunk, batch_size=batch_size)
            except Exception as exc:  # Keep a durable error record then continue one at a time.
                print(f"batch failed at {offset}: {exc}; retrying individually")
                batch = []
                for text in chunk:
                    try:
                        batch.append(ag.process(text))
                    except Exception as item_exc:
                        batch.append({"raw_text": text, "outputs": [], "error": str(item_exc)})
            for text, result in zip(chunk, batch):
                done[text] = result
                handle.write(json.dumps({"affiliation": text, "result": result}, ensure_ascii=False) + "\n")
            handle.flush()
            print(f"processed {offset + len(chunk)}/{len(pending)}")
    return done


def existing_indexes(institution_csv):
    by_ror, by_name_country, ids, existing_rows = {}, defaultdict(set), set(), set()
    with institution_csv.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            inst_id = row["conference_id"].strip()
            ids.add(inst_id)
            ror = row["affilgood_ror_ids"].strip()
            if ror:
                by_ror.setdefault(ror, inst_id)
            name = key_name(row["affilgood_institutions"])
            country = clean(row["affilgood_location_country"]).casefold()
            existing_rows.add((ror, name, country))
            if name and country:
                by_name_country[(name, country)].add(inst_id)
    return by_ror, by_name_country, ids, existing_rows


def next_id(existing):
    highest = max(int(value[4:]) for value in existing if re.fullmatch(r"INST\d{4}", value))
    return highest + 1


def assign_ids(results, institution_csv):
    by_ror, by_name_country, existing, existing_rows = existing_indexes(institution_csv)
    generated, next_number = {}, next_id(existing)
    new_dictionary = []
    for text, result in results.items():
        flat = flatten(result)
        ids_for_entries = []
        for entry in flat.pop("institution_entries"):
            ror = entry["ror"]
            name = key_name(entry["name"])
            country = clean(entry["country"]).casefold()
            inst_id = by_ror.get(ror) if ror else None
            candidates = by_name_country.get((name, country), set()) if name and country else set()
            if not inst_id and len(candidates) == 1:
                inst_id = next(iter(candidates))
            signature = (ror, name, country)
            if not inst_id and signature in generated:
                inst_id = generated[signature]
            if not inst_id and name:
                inst_id = f"INST{next_number:04d}"
                next_number += 1
                generated[signature] = inst_id
            if inst_id:
                ids_for_entries.append(inst_id)
                # Preserve canonical spellings/abbreviations from the four
                # conferences as aliases under their resolved identifier.
                if signature not in existing_rows:
                    new_dictionary.append({
                        "affilgood_ror_ids": ror, "conference_id": inst_id,
                        "affilgood_institutions": entry["name"],
                        "affilgood_location_country": entry["country"],
                        "affilgood_location_city": entry["city"],
                    })
                    existing_rows.add(signature)
                    if ror:
                        by_ror.setdefault(ror, inst_id)
                    if name and country:
                        by_name_country[(name, country)].add(inst_id)
        flat["conference_id"] = " | ".join(dict.fromkeys(ids_for_entries))
        results[text] = {"result": result, "flat": flat}
    return results, new_dictionary


def write_outputs(data_dir, source_rows, enriched):
    for filename, rows in source_rows.items():
        output_name = filename.replace("_raw_作者机构拆分.csv", "_affilgood_作者机构拆分_output.csv")
        output_path = data_dir / output_name
        fields = list(rows[0]) + list(EXTRA_FIELDS)
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                text = clean(row.get("affiliations"))
                flat = enriched.get(text, {}).get("flat", {})
                writer.writerow({**row, **{field: flat.get(field, "") for field in EXTRA_FIELDS}})
        print(f"wrote {output_path} ({len(rows)} rows)")


def extend_dictionary(institution_csv, additions):
    if not additions:
        print("No new dictionary rows.")
        return
    backup = institution_csv.with_suffix(".csv.before_security_conferences.bak")
    if not backup.exists():
        shutil.copy2(institution_csv, backup)
    with institution_csv.open(encoding="utf-8-sig", newline="") as handle:
        old = list(csv.DictReader(handle))
        fields = handle.seek(0) or csv.DictReader(handle).fieldnames
    with institution_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(old)
        writer.writerows(additions)
    print(f"extended {institution_csv} by {len(additions)} rows; backup: {backup}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parents[2] / "data")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--write-only", action="store_true", help="Use existing checkpoint only.")
    parser.add_argument("--extend-dictionary", action="store_true")
    args = parser.parse_args()
    checkpoint = args.checkpoint or args.data_dir / "security_conferences_affilgood_checkpoint.jsonl"
    sources, texts = load_sources(args.data_dir)
    results = read_checkpoint(checkpoint) if args.write_only else process_texts(texts, checkpoint, args.batch_size)
    if len(results) != len(texts):
        raise SystemExit(f"checkpoint incomplete: {len(results)}/{len(texts)} affiliations")
    enriched, additions = assign_ids(results, args.data_dir / "institution_raw.csv")
    write_outputs(args.data_dir, sources, enriched)
    if args.extend_dictionary:
        extend_dictionary(args.data_dir / "institution_raw.csv", additions)
    print(f"unique affiliations={len(texts)}; new institution records={len(additions)}")


if __name__ == "__main__":
    main()
