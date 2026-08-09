import argparse
import csv
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


OUTPUT_FIELDS = [
    "paper_id", "source_file", "code", "field", "author", "stage",
    "priority", "queue_class", "recommended_action", "resolution_status",
    "selected_value", "candidate_value", "confidence", "rationale",
    "evidence_json", "candidate_json", "details",
]


def _key(value):
    if isinstance(value, list):
        value = "; ".join(str(item) for item in value)
    folded = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", folded)


def _equivalent(left, right):
    left_key, right_key = _key(left), _key(right)
    return bool(
        left_key
        and right_key
        and (
            left_key == right_key
            or (len(left_key) >= 8 and left_key in right_key)
            or (len(right_key) >= 8 and right_key in left_key)
        )
    )


def _load_decisions(candidate_path):
    try:
        payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    return payload.get("decisions", [])


def classify(row, details, decisions):
    code = row.get("code", "")
    field = row.get("field", "")
    selected = details.get("selected", "")
    candidate = details.get("candidate", "")
    confidence = details.get("confidence", "")

    if code == "field_restored_after_loss":
        return "low", "resolved_restore", "close", "resolved", "Direct non-empty evidence was restored after a later stage dropped it."
    if code == "nonempty_field_dropped_with_reason":
        reason = details.get("reason", "")
        return "low", "rejected_weak_candidate", "close", "resolved", f"Candidate was intentionally rejected: {reason}."
    if code == "author_field_conflict" and field == "affiliations" and _equivalent(details.get("baseline"), selected):
        return "low", "equivalent_affiliation_extension", "close", "resolved", "Selected value preserves the same institution and adds formatting, location, or subunit detail."
    if code == "author_field_conflict" and field == "email" and _equivalent(details.get("baseline"), selected):
        return "low", "equivalent_email", "close", "resolved", "Email values are equivalent after conservative normalization."
    if code == "layout_affiliation_conflict" and float(confidence or 0) >= 0.92:
        return "high", "pdf_official_or_parser_difference", "verify_pdf_then_keep_pdf", "open", "High-confidence local PDF relation conflicts with the selected value. If the rendered PDF card is intact, retain the PDF institution and label publication_affiliation_adjustment when the official source differs."
    if code == "author_count_changed":
        rebuilt = any(item.get("action") == "rebuild_author_list_from_pdf_layout" for item in decisions)
        if rebuilt:
            return "medium", "geometry_author_rebuild", "verify_author_order", "open", "Author count changed through a geometry-supported page-author rebuild; verify order and role flags."
        return "high", "unverified_author_count_change", "inspect_pdf_authors", "open", "Author count changed without a recorded geometry rebuild."
    if code == "author_field_conflict" and row.get("stage") == "author_name_cleanup":
        return "medium", "author_name_cleanup_conflict", "inspect_affiliation_text", "open", "Author-name cleanup changed a non-equivalent value; check that an institution token was not removed."
    if code == "author_field_conflict":
        return "medium", "non_equivalent_strategy_conflict", "inspect_pdf_field", "open", "Conference strategy and baseline disagree; inspect the PDF field before choosing either value."
    return "medium", "uncategorized", "inspect_record", "open", "No automatic disposition rule matched."


def main():
    parser = argparse.ArgumentParser(description="Triage metadata extraction review queue without modifying it.")
    parser.add_argument("--review-queue", required=True)
    parser.add_argument("--dataset-dir", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    args = parser.parse_args()
    dataset_dir = Path(args.dataset_dir).resolve()
    with open(args.review_queue, encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    result = []
    decision_cache = {}
    for row in rows:
        paper_id = row.get("paper_id", "")
        candidate_path = dataset_dir / "candidate_json" / f"{paper_id}.json"
        evidence_path = dataset_dir / "evidence_json" / f"{paper_id}.json"
        if paper_id not in decision_cache:
            decision_cache[paper_id] = _load_decisions(candidate_path)
        try:
            details = json.loads(row.get("details", "") or "{}")
        except json.JSONDecodeError:
            details = {"unparsed_details": row.get("details", "")}
        priority, queue_class, action, status, rationale = classify(
            row,
            details,
            decision_cache[paper_id],
        )
        result.append({
            "paper_id": paper_id,
            "source_file": row.get("source_file", ""),
            "code": row.get("code", ""),
            "field": row.get("field", ""),
            "author": row.get("author", ""),
            "stage": row.get("stage", ""),
            "priority": priority,
            "queue_class": queue_class,
            "recommended_action": action,
            "resolution_status": status,
            "selected_value": json.dumps(details.get("selected", ""), ensure_ascii=False) if "selected" in details else "",
            "candidate_value": json.dumps(details.get("candidate", ""), ensure_ascii=False) if "candidate" in details else "",
            "confidence": details.get("confidence", ""),
            "rationale": rationale,
            "evidence_json": str(evidence_path) if evidence_path.exists() else "",
            "candidate_json": str(candidate_path) if candidate_path.exists() else "",
            "details": json.dumps(details, ensure_ascii=False, sort_keys=True),
        })

    output_path = Path(args.output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(result)
    summary = {
        "rows": len(result),
        "papers": len({row["paper_id"] for row in result}),
        "by_status": dict(Counter(row["resolution_status"] for row in result)),
        "by_priority": dict(Counter(row["priority"] for row in result)),
        "by_class": dict(Counter(row["queue_class"] for row in result).most_common()),
        "by_action": dict(Counter(row["recommended_action"] for row in result).most_common()),
    }
    Path(args.summary_json).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
