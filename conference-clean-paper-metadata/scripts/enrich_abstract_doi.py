#!/usr/bin/env python3
import argparse
import csv
import glob
import html
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict


CONF_OUTPUT = {
    "asiacrypt": "asiacrypt_full_output",
    "crypto": "crypto_full_output",
    "eurocrypt": "eurocrypt_full_output",
}


def normalize_space(value):
    return re.sub(r"\s+", " ", (value or "").strip())


def normalize_title_key(value):
    value = normalize_space(value).casefold()
    value = re.sub(r"[\u2010-\u2015]", "-", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    # Compact whitespace so OCR-inserted spaces inside a word do not block a
    # title match. The surrounding year/conference scope remains part of the
    # lookup key.
    return re.sub(r"\s+", "", normalize_space(value))


def clean_doi(value):
    value = html.unescape(normalize_space(value))
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value, flags=re.I)
    return value.strip(" \t\r\n,;")


def title_from_staged_path(path):
    name = os.path.splitext(os.path.basename(path or ""))[0]
    name = re.sub(r"^\d+[_\s-]+", "", name)
    name = name.replace("_", " ")
    return normalize_space(name)


def paper_index_titles(dataset_dir):
    path = os.path.join(dataset_dir, "paper_index.csv")
    titles = {}
    if not os.path.exists(path):
        return titles
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stem = row.get("paper_id", "")
            staged = row.get("staged_rel_path", "") or row.get("source_file", "")
            title = title_from_staged_path(staged)
            if stem and title:
                titles[stem] = title
    return titles


def text_from_xml(elem):
    return normalize_space("".join(elem.itertext()))


def tei_root(path):
    if not path or not os.path.exists(path):
        return None
    try:
        return ET.parse(path).getroot()
    except Exception:
        return None


def first_tei_text(path, tag_name, attr=None):
    root = tei_root(path)
    if root is None:
        return ""
    for elem in root.iter():
        tag = elem.tag.split("}", 1)[-1]
        if tag != tag_name:
            continue
        if attr:
            ok = True
            for want_key, want_value in attr.items():
                got = ""
                for key, value in elem.attrib.items():
                    if key.split("}", 1)[-1] == want_key:
                        got = value
                        break
                if got != want_value:
                    ok = False
                    break
            if not ok:
                continue
        value = text_from_xml(elem)
        if value:
            return value
    return ""


def title_from_tei(path):
    return first_tei_text(path, "title", {"level": "a", "type": "main"})


def abstract_from_tei(path):
    return first_tei_text(path, "abstract")


def clean_abstract(value, title):
    value = normalize_space(value)
    if not value:
        return ""
    # GROBID sometimes captures the visible author line as an abstract when header
    # parsing fails. Keep these empty rather than writing known-bad prose.
    norm_value = normalize_title_key(value)
    norm_title = normalize_title_key(title)
    if norm_title and norm_value.startswith(norm_title) and len(value) < 140:
        if re.search(r"\b(and|et al|[0-9])\b|,", value, flags=re.I):
            return ""
    return value


def doi_from_tei(path):
    if not path or not os.path.exists(path):
        return ""
    try:
        root = ET.parse(path).getroot()
        for elem in root.iter():
            tag = elem.tag.split("}", 1)[-1]
            if tag != "idno":
                continue
            typ = ""
            for k, v in elem.attrib.items():
                if k.split("}", 1)[-1].lower() == "type":
                    typ = (v or "").lower()
                    break
            if typ == "doi":
                doi = clean_doi(text_from_xml(elem))
                if doi:
                    return doi
        text = text_from_xml(root)
    except Exception:
        with open(path, encoding="utf-8", errors="ignore") as f:
            text = f.read()
    m = re.search(r"10\.\d{4,9}/[^\s<>()\"']+", text)
    return clean_doi(m.group(0)) if m else ""


def conference_from_output_root(root):
    base = os.path.basename(os.path.normpath(root))
    for conf, dirname in CONF_OUTPUT.items():
        if base == dirname or base.startswith(conf):
            return conf
    return ""


def build_index(full_outputs):
    index = {}
    duplicates = defaultdict(list)
    def add_record(key, record, source):
        if key in index:
            duplicates[key].append(source)
            if not index[key].get("abstract") and record["abstract"]:
                index[key]["abstract"] = record["abstract"]
            if not index[key].get("doi") and record["doi"]:
                index[key]["doi"] = record["doi"]
        else:
            index[key] = dict(record)

    for output_root in full_outputs:
        conf = conference_from_output_root(output_root)
        for json_path in glob.glob(os.path.join(output_root, "author_metadata_dataset_*", "metadata_json", "*.json")):
            dataset_dir = os.path.dirname(os.path.dirname(json_path))
            stem = os.path.splitext(os.path.basename(json_path))[0]
            tei_path = os.path.join(dataset_dir, "tei_header_xml", stem + ".tei.xml")
            index_titles = paper_index_titles(dataset_dir)
            data = {}
            try:
                with open(json_path, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as exc:
                print(f"warning: cannot read JSON {json_path}: {exc}", file=sys.stderr)
            index_title = index_titles.get(stem, "")
            title = index_title or normalize_space(data.get("title", "")) or title_from_tei(tei_path)
            year = normalize_space(str(data.get("year", "")))
            if not title:
                continue
            if not year:
                m = re.search(r"author_metadata_dataset_(\d{4})", dataset_dir)
                year = m.group(1) if m else ""
            aliases = []
            for candidate in [normalize_space(data.get("title", "")), title_from_tei(tei_path), index_title]:
                if candidate and candidate not in aliases:
                    aliases.append(candidate)
            abstract = normalize_space(data.get("abstract", "")) or abstract_from_tei(tei_path)
            record = {
                "abstract": clean_abstract(abstract, title),
                "doi": doi_from_tei(tei_path),
                "json": json_path,
                "tei": tei_path,
            }
            for alias in aliases:
                add_record((year, conf, alias), record, json_path)
    return index, duplicates


def normalized_lookup(index):
    lookup = {}
    ambiguous = set()
    for key, record in index.items():
        norm = (key[0], key[1], normalize_title_key(key[2]))
        if norm in lookup:
            ambiguous.add(norm)
        else:
            lookup[norm] = record
    for norm in ambiguous:
        lookup.pop(norm, None)
    return lookup, ambiguous


def detect_full_outputs(csv_path, rows, explicit):
    if explicit:
        return explicit
    data_dir = os.path.dirname(os.path.abspath(csv_path))
    conferences = sorted({r.get("conference", "") for r in rows if r.get("conference", "")})
    roots = []
    for conf in conferences:
        dirname = CONF_OUTPUT.get(conf, f"{conf}_full_output")
        root = os.path.join(data_dir, dirname)
        if os.path.isdir(root):
            roots.append(root)
    if not roots:
        for root in glob.glob(os.path.join(data_dir, "*_full_output")):
            if os.path.isdir(root):
                roots.append(root)
    return sorted(set(roots))


def enrich_csv(csv_path, full_outputs, dry_run=False):
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise SystemExit("empty CSV")
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    roots = detect_full_outputs(csv_path, rows, full_outputs)
    if not roots:
        raise SystemExit("no *_full_output directories found; pass --full-output")

    index, duplicates = build_index(roots)
    norm_index, ambiguous_norm_keys = normalized_lookup(index)
    paper_keys = sorted({(r["year"], r["conference"], normalize_space(r["title"])) for r in rows})
    matched = {}
    unmatched = []
    missing_abstract = []
    missing_doi = []

    for key in paper_keys:
        rec = index.get(key)
        if not rec:
            rec = norm_index.get((key[0], key[1], normalize_title_key(key[2])))
        if not rec:
            unmatched.append(key)
            continue
        matched[key] = rec
        if not rec.get("abstract"):
            missing_abstract.append(key)
        if not rec.get("doi"):
            missing_doi.append(key)

    for col in ["abstract", "doi"]:
        if col not in fieldnames:
            fieldnames.append(col)

    changed_rows = 0
    for row in rows:
        key = (row["year"], row["conference"], normalize_space(row["title"]))
        rec = matched.get(key)
        new_abstract = rec.get("abstract", "") if rec else row.get("abstract", "")
        new_doi = rec.get("doi", "") if rec else row.get("doi", "")
        if row.get("abstract", "") != new_abstract or row.get("doi", "") != new_doi:
            changed_rows += 1
        row["abstract"] = new_abstract
        row["doi"] = new_doi

    print("CSV:", csv_path)
    print("full_outputs:", ", ".join(roots))
    print("rows:", len(rows))
    print("papers:", len(paper_keys))
    print("matched_papers:", len(matched))
    print("unmatched_papers:", len(unmatched))
    print("papers_missing_abstract:", len(missing_abstract))
    print("papers_missing_doi:", len(missing_doi))
    print("duplicate_index_keys:", len(duplicates))
    print("ambiguous_normalized_title_aliases:", len(ambiguous_norm_keys))
    print("changed_rows:", changed_rows)

    for title, items in [
        ("unmatched_sample", unmatched[:20]),
        ("missing_abstract_sample", missing_abstract[:20]),
        ("missing_doi_sample", missing_doi[:20]),
    ]:
        print(f"\n{title}: {len(items)}")
        for item in items:
            print("  -", item)

    if dry_run:
        return

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Add or update abstract and doi columns in paper-author CSV files.")
    parser.add_argument("csv", help="CSV file to update in place")
    parser.add_argument("--full-output", action="append", default=[], help="Conference *_full_output directory; can be repeated")
    parser.add_argument("--dry-run", action="store_true", help="Report coverage without writing")
    args = parser.parse_args()
    enrich_csv(args.csv, args.full_output, args.dry_run)


if __name__ == "__main__":
    main()
