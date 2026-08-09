#!/usr/bin/env python3
import argparse
import csv
import glob
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
ORG_COLUMNS = ["laboratory", "department", "institution"]


def normalize_space(value):
    return re.sub(r"\s+", " ", (value or "").strip())


def normalize_title_key(value):
    value = normalize_space(value).casefold()
    value = re.sub(r"[\u2010-\u2015]", "-", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", "", normalize_space(value))


def normalize_name(value):
    value = normalize_space(value).casefold()
    value = value.replace(".", "")
    value = re.sub(r"[{}]", "", value)
    value = re.sub(r"[^a-z0-9\u00c0-\u024f]+", " ", value)
    return normalize_space(value)


def text_from_xml(elem):
    return normalize_space("".join(elem.itertext()))


def local_name(tag):
    return tag.split("}", 1)[-1]


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


def conference_from_output_root(root):
    base = os.path.basename(os.path.normpath(root))
    for conf, dirname in CONF_OUTPUT.items():
        if base == dirname or base.startswith(conf):
            return conf
    return ""


def first_tei_title(root):
    for elem in root.iter():
        if local_name(elem.tag) != "title":
            continue
        attrs = {local_name(k): v for k, v in elem.attrib.items()}
        if attrs.get("level") == "a" and attrs.get("type") == "main":
            value = text_from_xml(elem)
            if value:
                return value
    return ""


def json_title_year(json_path):
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        return normalize_space(data.get("title", "")), normalize_space(str(data.get("year", "")))
    except Exception:
        return "", ""


def author_name(author_elem):
    pers = None
    for child in author_elem.iter():
        if local_name(child.tag) == "persName":
            pers = child
            break
    if pers is None:
        return ""
    parts = []
    surname = ""
    for child in list(pers):
        tag = local_name(child.tag)
        value = text_from_xml(child)
        if not value:
            continue
        if tag == "surname":
            surname = value
        elif tag == "forename":
            parts.append(value)
    if surname:
        parts.append(surname)
    return normalize_space(" ".join(parts)) or text_from_xml(pers)


def dedupe_join(values):
    out = []
    seen = set()
    for value in values:
        value = normalize_space(value)
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            out.append(value)
    return "; ".join(out)


def author_org_segments(author_elem):
    values = {col: [] for col in ORG_COLUMNS}
    for elem in author_elem.iter():
        if local_name(elem.tag) != "orgName":
            continue
        typ = ""
        for key, value in elem.attrib.items():
            if local_name(key) == "type":
                typ = value
                break
        if typ in values:
            values[typ].append(text_from_xml(elem))
    return {col: dedupe_join(values[col]) for col in ORG_COLUMNS}


def parse_tei_record(tei_path):
    try:
        root = ET.parse(tei_path).getroot()
    except Exception as exc:
        print(f"warning: cannot parse TEI {tei_path}: {exc}", file=sys.stderr)
        return "", []
    title = first_tei_title(root)
    authors = []
    in_analytic = False
    for elem in root.iter():
        tag = local_name(elem.tag)
        if tag == "analytic":
            in_analytic = True
            continue
        if in_analytic and tag == "monogr":
            break
        if in_analytic and tag == "author":
            name = author_name(elem)
            segments = author_org_segments(elem)
            if name or any(segments.values()):
                authors.append({"name": name, "norm_name": normalize_name(name), **segments})
    return title, authors


def add_record(index, key, record):
    if key not in index:
        index[key] = record


def build_index(full_outputs):
    index = {}
    for output_root in full_outputs:
        conf = conference_from_output_root(output_root)
        for tei_path in glob.glob(os.path.join(output_root, "author_metadata_dataset_*", "tei_header_xml", "*.tei.xml")):
            dataset_dir = os.path.dirname(os.path.dirname(tei_path))
            stem = os.path.splitext(os.path.basename(tei_path))[0]
            json_path = os.path.join(dataset_dir, "metadata_json", stem + ".json")
            index_title = paper_index_titles(dataset_dir).get(stem, "")
            tei_title, authors = parse_tei_record(tei_path)
            json_title, year = json_title_year(json_path)
            if not year:
                m = re.search(r"author_metadata_dataset_(\d{4})", dataset_dir)
                year = m.group(1) if m else ""
            if not authors:
                continue
            aliases = []
            for title in [json_title, tei_title, index_title]:
                title = normalize_space(title)
                if title and title not in aliases:
                    aliases.append(title)
            record = {"authors": authors, "tei": tei_path}
            for title in aliases:
                add_record(index, (year, conf, title), record)
    return index


def normalized_lookup(index):
    lookup = {}
    ambiguous = set()
    for key, record in index.items():
        norm = (key[0], key[1], normalize_title_key(key[2]))
        if norm in lookup and lookup[norm] is not record:
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
        roots = [root for root in glob.glob(os.path.join(data_dir, "*_full_output")) if os.path.isdir(root)]
    return sorted(set(roots))


def match_author(row, paper_rows, record, row_position):
    authors = record["authors"]
    norm = normalize_name(row.get("author", ""))
    name_matches = [a for a in authors if a["norm_name"] == norm]
    if len(name_matches) == 1:
        return name_matches[0], "name"

    # Some GROBID names are malformed but author order is still reliable.
    if len(authors) == len(paper_rows) and row_position < len(authors):
        return authors[row_position], "order_equal_count"

    # If TEI has extra fake authors appended, same-position fallback is usually
    # still safer than losing all organization segmentation for valid early rows.
    if row_position < len(authors):
        candidate = authors[row_position]
        if candidate["name"] or any(candidate[col] for col in ORG_COLUMNS):
            return candidate, "order_prefix"

    return None, "unmatched"


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

    index = build_index(roots)
    norm_index, ambiguous = normalized_lookup(index)

    for col in ORG_COLUMNS:
        if col not in fieldnames:
            fieldnames.append(col)

    groups = defaultdict(list)
    for idx, row in enumerate(rows):
        key = (row["year"], row["conference"], normalize_space(row["title"]))
        groups[key].append((idx, row))

    matched_papers = 0
    unmatched_papers = []
    matched_rows = 0
    changed_rows = 0
    method_counts = defaultdict(int)

    for key, items in groups.items():
        record = index.get(key) or norm_index.get((key[0], key[1], normalize_title_key(key[2])))
        if not record:
            unmatched_papers.append(key)
            continue
        matched_papers += 1
        paper_rows = [row for _, row in items]
        for position, (idx, row) in enumerate(items):
            match, method = match_author(row, paper_rows, record, position)
            method_counts[method] += 1
            if not match:
                continue
            matched_rows += 1
            for col in ORG_COLUMNS:
                new_value = match.get(col, "")
                if row.get(col, "") != new_value:
                    changed_rows += 1
                row[col] = new_value

    print("CSV:", csv_path)
    print("full_outputs:", ", ".join(roots))
    print("rows:", len(rows))
    print("papers:", len(groups))
    print("matched_papers:", matched_papers)
    print("unmatched_papers:", len(unmatched_papers))
    print("matched_rows:", matched_rows)
    print("changed_cell_events:", changed_rows)
    print("ambiguous_normalized_title_aliases:", len(ambiguous))
    print("match_methods:", dict(sorted(method_counts.items())))
    print()
    print("unmatched_sample:", len(unmatched_papers[:20]))
    for item in unmatched_papers[:20]:
        print("  -", item)

    if dry_run:
        return

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Add or update laboratory, department, and institution columns from TEI author affiliations.")
    parser.add_argument("csv", help="CSV file to update in place")
    parser.add_argument("--full-output", action="append", default=[], help="Conference *_full_output directory; can be repeated")
    parser.add_argument("--dry-run", action="store_true", help="Report coverage without writing")
    args = parser.parse_args()
    enrich_csv(args.csv, args.full_output, args.dry_run)


if __name__ == "__main__":
    main()
