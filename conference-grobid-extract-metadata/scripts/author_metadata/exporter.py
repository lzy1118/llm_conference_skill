import csv
import json
import os


CSV_FIELDNAMES = [
    "paper_id",
    "year",
    "conference",
    "title",
    "author",
    "author_rank",
    "affiliation_rank",
    "affiliations",
    "emails",
    "first_author",
    "co_first_author",
    "corresponding",
    "equal_contribution",
    "country",
    "orcid",
]

ABSTRACT_FIELDNAMES = [
    "conference",
    "year",
    "title",
    "abstract",
]

INDEX_FIELDNAMES = [
    "paper_id",
    "status",
    "source_file",
    "source_path",
    "stage_pdf",
    "tei_xml",
    "metadata_json",
    "evidence_json",
    "candidate_json",
]

REVIEW_FIELDNAMES = [
    "paper_id",
    "source_file",
    "code",
    "field",
    "author",
    "stage",
    "details",
]


def export_json(json_path, metadata):
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, ensure_ascii=False, indent=2)


def export_csv(csv_path, rows):
    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def export_abstract_csv(csv_path, rows):
    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=ABSTRACT_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def write_index(index_path, skipped_path, records):
    os.makedirs(os.path.dirname(index_path) or ".", exist_ok=True)
    with open(index_path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=INDEX_FIELDNAMES)
        writer.writeheader()
        writer.writerows(records)

    skipped_records = [record for record in records if record["status"] != "staged"]
    with open(skipped_path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=INDEX_FIELDNAMES)
        writer.writeheader()
        writer.writerows(skipped_records)


def export_review_queue(path, rows):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
