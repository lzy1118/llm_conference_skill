from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "generated-data" / "cfp"

sys.path.insert(0, str(ROOT / "conference-paper-extraction" / "scripts"))
from conference_registry import CONFERENCES  # noqa: E402


EVENT_FIELDS = [
    "conference_key",
    "conference",
    "year",
    "event_type",
    "event_date",
    "event_datetime",
    "timezone",
    "deadline_scope",
    "source_text",
    "source_url",
    "source_kind",
    "confidence",
    "needs_review",
    "notes",
]

EDITION_FIELDS = [
    "conference_key",
    "conference",
    "year",
    "family",
    "location",
    "country",
    "start_date",
    "end_date",
    "timezone",
    "website_url",
    "cfp_url",
    "proceedings_url",
    "source_url",
    "confidence",
    "needs_review",
    "notes",
]

VALID_EVENT_TYPES = {
    "abstract_submission_deadline",
    "paper_submission_deadline",
    "artifact_submission_deadline",
    "rebuttal_start",
    "rebuttal_end",
    "notification",
    "camera_ready",
    "conference_start",
    "conference_end",
}


def read_csv(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def normalize_date(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if match:
        year, month, day = match.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    match = re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", text)
    if match:
        year, month, day = match.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return text


def bool_text(value: object) -> str:
    return "true" if str(value).strip().lower() in {"1", "true", "yes", "y"} else "false"


def confidence_value(value: str, default: str = "0.0") -> str:
    text = value.strip() or default
    try:
        number = float(text)
    except ValueError:
        return default
    return str(min(max(number, 0.0), 1.0))


def template_event_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for key, conference in sorted(CONFERENCES.items(), key=lambda item: (item[1].family, item[1].conference, item[1].year)):
        for event_type in ("paper_submission_deadline", "notification", "conference_start", "conference_end"):
            rows.append(
                {
                    "conference_key": key,
                    "conference": conference.conference,
                    "year": conference.year,
                    "event_type": event_type,
                    "event_date": "",
                    "event_datetime": "",
                    "timezone": "",
                    "deadline_scope": "",
                    "source_text": "",
                    "source_url": "",
                    "source_kind": "manual",
                    "confidence": "",
                    "needs_review": "true",
                    "notes": "",
                }
            )
    return rows


def template_edition_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for key, conference in sorted(CONFERENCES.items(), key=lambda item: (item[1].family, item[1].conference, item[1].year)):
        rows.append(
            {
                "conference_key": key,
                "conference": conference.conference,
                "year": conference.year,
                "family": conference.family,
                "location": "",
                "country": "",
                "start_date": "",
                "end_date": "",
                "timezone": "",
                "website_url": "",
                "cfp_url": "",
                "proceedings_url": "",
                "source_url": "",
                "confidence": "",
                "needs_review": "true",
                "notes": "",
            }
        )
    return rows


def normalize_events(rows: list[dict[str, str]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    normalized: list[dict[str, object]] = []
    findings: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        key = row.get("conference_key", "").strip()
        event_type = row.get("event_type", "").strip()
        event_date = normalize_date(row.get("event_date", ""))
        needs_review = bool_text(row.get("needs_review", ""))
        if event_type and event_type not in VALID_EVENT_TYPES:
            findings.append({"severity": "medium", "code": "unknown_event_type", "row": index, "message": event_type})
            needs_review = "true"
        if not key or key not in CONFERENCES:
            findings.append({"severity": "high", "code": "unknown_conference_key", "row": index, "message": key})
            needs_review = "true"
        if not event_date:
            findings.append({"severity": "medium", "code": "missing_event_date", "row": index, "message": key})
            needs_review = "true"
        conference = CONFERENCES.get(key)
        normalized.append(
            {
                "conference_key": key,
                "conference": row.get("conference", "").strip() or (conference.conference if conference else ""),
                "year": row.get("year", "").strip() or (conference.year if conference else ""),
                "event_type": event_type,
                "event_date": event_date,
                "event_datetime": row.get("event_datetime", "").strip(),
                "timezone": row.get("timezone", "").strip(),
                "deadline_scope": row.get("deadline_scope", "").strip(),
                "source_text": row.get("source_text", "").strip(),
                "source_url": row.get("source_url", "").strip(),
                "source_kind": row.get("source_kind", "").strip() or "manual",
                "confidence": confidence_value(row.get("confidence", ""), default="0.5" if event_date else "0.0"),
                "needs_review": needs_review,
                "notes": row.get("notes", "").strip(),
            }
        )
    return normalized, findings


def normalize_editions(rows: list[dict[str, str]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    normalized: list[dict[str, object]] = []
    findings: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        key = row.get("conference_key", "").strip()
        needs_review = bool_text(row.get("needs_review", ""))
        if not key or key not in CONFERENCES:
            findings.append({"severity": "high", "code": "unknown_conference_key", "row": index, "message": key})
            needs_review = "true"
        conference = CONFERENCES.get(key)
        normalized.append(
            {
                "conference_key": key,
                "conference": row.get("conference", "").strip() or (conference.conference if conference else ""),
                "year": row.get("year", "").strip() or (conference.year if conference else ""),
                "family": row.get("family", "").strip() or (conference.family if conference else ""),
                "location": row.get("location", "").strip(),
                "country": row.get("country", "").strip(),
                "start_date": normalize_date(row.get("start_date", "")),
                "end_date": normalize_date(row.get("end_date", "")),
                "timezone": row.get("timezone", "").strip(),
                "website_url": row.get("website_url", "").strip(),
                "cfp_url": row.get("cfp_url", "").strip(),
                "proceedings_url": row.get("proceedings_url", "").strip(),
                "source_url": row.get("source_url", "").strip(),
                "confidence": confidence_value(row.get("confidence", ""), default="0.5"),
                "needs_review": needs_review,
                "notes": row.get("notes", "").strip(),
            }
        )
    return normalized, findings


def write_reports(output_dir: Path, events: list[dict[str, object]], editions: list[dict[str, object]], findings: list[dict[str, object]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    event_keys = {str(row.get("conference_key", "")) for row in events if row.get("conference_key")}
    edition_keys = {str(row.get("conference_key", "")) for row in editions if row.get("conference_key")}
    payload = {
        "registered_conference_years": len(CONFERENCES),
        "event_rows": len(events),
        "edition_rows": len(editions),
        "conference_years_with_events": len(event_keys),
        "conference_years_with_editions": len(edition_keys),
        "missing_event_conference_years": len(set(CONFERENCES) - event_keys),
        "missing_edition_conference_years": len(set(CONFERENCES) - edition_keys),
        "findings": findings,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (output_dir / "cfp_validation_report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# CFP Extraction Report",
        "",
        "## Summary",
        "",
        f"- registered_conference_years: {payload['registered_conference_years']}",
        f"- event_rows: {payload['event_rows']}",
        f"- edition_rows: {payload['edition_rows']}",
        f"- conference_years_with_events: {payload['conference_years_with_events']}",
        f"- missing_event_conference_years: {payload['missing_event_conference_years']}",
        f"- findings: {len(findings)}",
        "",
        "## Notes",
        "",
        "- This minimal pipeline is template-first and does not fetch external CFP pages by default.",
        "- Rows with missing dates or unknown event types are marked for review.",
    ]
    (output_dir / "cfp_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and normalize CFP metadata tables.")
    parser.add_argument("--events-input", type=Path, help="Optional CSV containing CFP event rows")
    parser.add_argument("--edition-input", type=Path, help="Optional CSV containing conference edition metadata")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    template_dir = output_dir / "input_templates"
    final_dir = output_dir / "output"

    write_csv(template_dir / "cfp_events_template.csv", template_event_rows(), EVENT_FIELDS)
    write_csv(template_dir / "conference_edition_template.csv", template_edition_rows(), EDITION_FIELDS)

    event_input_rows = read_csv(args.events_input.resolve() if args.events_input else None)
    edition_input_rows = read_csv(args.edition_input.resolve() if args.edition_input else None)

    events, event_findings = normalize_events(event_input_rows)
    editions, edition_findings = normalize_editions(edition_input_rows)
    write_csv(final_dir / "conference_events.csv", events, EVENT_FIELDS)
    write_csv(final_dir / "conference_edition_metadata.csv", editions, EDITION_FIELDS)
    write_reports(final_dir, events, editions, event_findings + edition_findings)


if __name__ == "__main__":
    main()
