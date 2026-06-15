from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "generated-data" / "cfp"
IACR_SNAPSHOT_PATH = ROOT / "conference-cfp-extraction" / "references" / "iacr_metadata_snapshots.json"
SECURITY_SNAPSHOT_PATH = ROOT / "conference-cfp-extraction" / "references" / "security_cfp_snapshots.json"

sys.path.insert(0, str(ROOT / "conference-paper-extraction" / "scripts"))
from conference_registry import CONFERENCES, expand_selection  # noqa: E402


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
    "first_round_notification",
    "rebuttal_start",
    "rebuttal_end",
    "interactive_rebuttal_end",
    "notification",
    "camera_ready",
    "conference_start",
    "conference_end",
}

CORE_EVENT_TYPES = (
    "paper_submission_deadline",
    "notification",
    "conference_start",
    "conference_end",
)

OUTPUT_STATUS_FIELDS = [
    "conference_key",
    "conference",
    "year",
    "event_count",
    "dated_event_count",
    "core_events_present",
    "edition_present",
    "needs_review_rows",
    "cfp_status",
]

REVIEW_QUEUE_FIELDS = [
    "conference_key",
    "conference",
    "year",
    "issue_type",
    "detail",
    "needs_review",
    "source",
]


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def strip_html_to_text(value: str) -> str:
    text = html.unescape(value)
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return normalize_space(text)


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
    text = normalize_space(value)
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


def default_input_path(path: Path) -> Path | None:
    return path if path.exists() else None


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/json,*/*;q=0.8"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_json(url: str) -> dict[str, object]:
    return json.loads(fetch_text(url))


def load_iacr_snapshots() -> dict[str, dict[str, object]]:
    if not IACR_SNAPSHOT_PATH.exists():
        return {}
    payload = json.loads(IACR_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def load_security_snapshots() -> dict[str, dict[str, object]]:
    if not SECURITY_SNAPSHOT_PATH.exists():
        return {}
    payload = json.loads(SECURITY_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def infer_cfp_urls(conference_key: str, conference: str, year: int) -> dict[str, str]:
    if conference in {"ASIACRYPT", "CRYPTO", "EUROCRYPT"}:
        family_slug = conference.casefold()
        base = f"https://{family_slug}.iacr.org/{year}/"
        return {
            "website_url": base,
            "cfp_url": base + "callforpapers.php",
            "proceedings_url": base + "acceptedpapers.php",
        }
    if conference == "USENIX_SECURITY":
        base = f"https://www.usenix.org/conference/usenixsecurity{str(year)[-2:]}"
        return {
            "website_url": base,
            "cfp_url": base + "/call-for-papers",
            "proceedings_url": base + "/technical-sessions",
        }
    if conference == "NDSS":
        base = f"https://www.ndss-symposium.org/ndss{year}/"
        return {
            "website_url": base,
            "cfp_url": base + ("submisions/call-for-papers/" if year == 2025 else "submissions/call-for-papers/" if year == 2024 else "call-for-papers/"),
            "proceedings_url": base + "program/",
        }
    if conference == "IEEE_S&P":
        base = f"https://www.ieee-security.org/TC/SP{year}/"
        return {
            "website_url": base,
            "cfp_url": base + "cfpapers.html",
            "proceedings_url": base + "program.html",
        }
    if conference == "CCS":
        base = f"https://www.sigsac.org/ccs/CCS{year}/"
        if year == 2020:
            cfp_path = "call-for-papers.html"
        elif year == 2021:
            cfp_path = "call-for-papers.html"
        elif year == 2023:
            cfp_path = "call-for-paper.html"
        elif year >= 2025:
            cfp_path = "call-for-papers/"
        else:
            cfp_path = "call-for/call-for-papers.html"
        return {
            "website_url": base,
            "cfp_url": base + cfp_path,
            "proceedings_url": base + "accepted-papers/",
        }
    return {"website_url": "", "cfp_url": "", "proceedings_url": ""}


def inferred_edition_row(conference_key: str) -> dict[str, object]:
    conference = CONFERENCES[conference_key]
    urls = infer_cfp_urls(conference_key, conference.conference, conference.year)
    return {
        "conference_key": conference.key,
        "conference": conference.conference,
        "year": conference.year,
        "family": conference.family,
        "location": "",
        "country": "",
        "start_date": "",
        "end_date": "",
        "timezone": "",
        "website_url": urls.get("website_url", ""),
        "cfp_url": urls.get("cfp_url", ""),
        "proceedings_url": urls.get("proceedings_url", ""),
        "source_url": urls.get("cfp_url") or urls.get("website_url", ""),
        "confidence": "0.3",
        "needs_review": "true",
        "notes": "inferred_from_registry_url_pattern",
    }


def normalize_country_name(value: str) -> str:
    text = normalize_space(value)
    if text == "USA":
        return "United States"
    if text == "Conference":
        return ""
    return text


def metadata_to_event_rows(conference_key: str, metadata: dict[str, object], cfp_url: str) -> list[dict[str, str]]:
    conference = CONFERENCES[conference_key]
    rows: list[dict[str, str]] = []

    def add_row(event_type: str, raw_value: object, *, notes: str = "") -> None:
        value = normalize_space(str(raw_value or ""))
        if not value:
            return
        rows.append(
            {
                "conference_key": conference.key,
                "conference": conference.conference,
                "year": str(conference.year),
                "event_type": event_type,
                "event_date": value,
                "event_datetime": "",
                "timezone": "",
                "deadline_scope": "",
                "source_text": value,
                "source_url": cfp_url,
                "source_kind": "official_metadata_json",
                "confidence": "0.9",
                "needs_review": "false",
                "notes": notes,
            }
        )

    rebuttal_range = normalize_space(str(metadata.get("rebuttalDue") or metadata.get("rebuttals") or ""))
    if " - " in rebuttal_range and not metadata.get("rebuttalStart") and not metadata.get("rebuttalEnd"):
        start_text, end_text = [normalize_space(part) for part in rebuttal_range.split(" - ", 1)]
        add_row("rebuttal_start", start_text)
        add_row("rebuttal_end", end_text)
    else:
        add_row("rebuttal_start", metadata.get("rebuttalStart") or metadata.get("rebuttalPhaseBeg"))
        add_row("rebuttal_end", metadata.get("rebuttalEnd") or metadata.get("rebuttalDue") or metadata.get("rebuttalPhaseEnd") or metadata.get("rebuttals"))

    add_row("abstract_submission_deadline", metadata.get("aesubmitdate"), notes="auto_inferred_abstract_deadline")
    add_row("abstract_submission_deadline", metadata.get("aesubmitdate2"), notes="auto_inferred_abstract_deadline")
    add_row("paper_submission_deadline", metadata.get("submitdate"))
    add_row("artifact_submission_deadline", metadata.get("artifactDue") or metadata.get("artifactsubmitdate"))
    add_row("first_round_notification", metadata.get("firstRound") or metadata.get("firstNotif") or metadata.get("reviewsOut") or metadata.get("earlyReject") or metadata.get("earlyRej") or metadata.get("earlyRejec"))
    add_row("interactive_rebuttal_end", metadata.get("rebuPerEnd"))
    add_row("notification", metadata.get("finalNotif") or metadata.get("finalNotification") or metadata.get("finalDecisionNotif") or metadata.get("paperNotification") or metadata.get("notification") or metadata.get("notificationdate"))
    add_row("camera_ready", metadata.get("finalVers") or metadata.get("finalVersion") or metadata.get("finalversions") or metadata.get("cameraReady") or metadata.get("camReady"))
    add_row("conference_start", metadata.get("startdate"))
    add_row("conference_end", metadata.get("enddate"))
    return rows


def merge_metadata_into_edition(base_row: dict[str, object], metadata: dict[str, object], urls: dict[str, str]) -> dict[str, object]:
    return {
        **base_row,
        "location": normalize_space(str(metadata.get("location", ""))) or str(base_row.get("location", "")),
        "country": normalize_country_name(str(metadata.get("country", ""))) or str(base_row.get("country", "")),
        "start_date": normalize_date(str(metadata.get("startdate", ""))) or str(base_row.get("start_date", "")),
        "end_date": normalize_date(str(metadata.get("enddate", ""))) or str(base_row.get("end_date", "")),
        "website_url": urls.get("website_url", "") or str(base_row.get("website_url", "")),
        "cfp_url": urls.get("cfp_url", "") or str(base_row.get("cfp_url", "")),
        "proceedings_url": urls.get("proceedings_url", "") or str(base_row.get("proceedings_url", "")),
        "source_url": urls.get("cfp_url", "") or str(base_row.get("source_url", "")),
        "confidence": "0.9",
        "needs_review": "false",
        "notes": "official_iacr_metadata_json",
    }


def auto_fetch_iacr_data(selected_keys: list[str]) -> tuple[list[dict[str, str]], dict[str, dict[str, object]], list[dict[str, object]]]:
    event_rows: list[dict[str, str]] = []
    editions: dict[str, dict[str, object]] = {}
    findings: list[dict[str, object]] = []
    snapshots = load_iacr_snapshots()
    for key in selected_keys:
        conference = CONFERENCES[key]
        if conference.family != "crypto":
            continue
        urls = infer_cfp_urls(key, conference.conference, conference.year)
        metadata_url = (urls.get("website_url", "") or "") + "json/metadata.json"
        try:
            metadata = fetch_json(metadata_url)
        except Exception as exc:
            metadata = snapshots.get(key)
            if not metadata:
                findings.append(
                    {
                        "severity": "high",
                        "code": "iacr_metadata_fetch_failed",
                        "row": key,
                        "message": f"{metadata_url} :: {exc}",
                    }
                )
                continue
            findings.append(
                {
                    "severity": "low",
                    "code": "iacr_metadata_snapshot_fallback",
                    "row": key,
                    "message": f"{metadata_url} :: {exc}",
                }
            )
        event_rows.extend(metadata_to_event_rows(key, metadata, urls.get("cfp_url", metadata_url)))
        editions[key] = merge_metadata_into_edition(inferred_edition_row(key), metadata, urls)
    return event_rows, editions, findings


def parse_date_range_text(value: str) -> tuple[str, str]:
    text = normalize_space(value)
    if not text:
        return "", ""
    dual_day_month_year = re.fullmatch(r"(\d{1,2}) ([A-Za-z]+) to (\d{1,2}) ([A-Za-z]+) (\d{4})", text)
    if dual_day_month_year:
        start_day, start_month, end_day, end_month, year = dual_day_month_year.groups()
        return f"{int(start_day)} {start_month} {year}", f"{int(end_day)} {end_month} {year}"
    month_day_year = re.fullmatch(r"([A-Za-z]+) (\d{1,2})[–—-](\d{1,2}), (\d{4})", text)
    if month_day_year:
        month, start_day, end_day, year = month_day_year.groups()
        return f"{month} {int(start_day)}, {year}", f"{month} {int(end_day)}, {year}"
    short_month_day_year = re.fullmatch(r"([A-Za-z]{3}) (\d{1,2})-(\d{1,2}), (\d{4})", text)
    if short_month_day_year:
        month, start_day, end_day, year = short_month_day_year.groups()
        return f"{month} {int(start_day)}, {year}", f"{month} {int(end_day)}, {year}"
    day_month_year = re.fullmatch(r"(\d{1,2}) ?(?:-|–|—|to) ?(\d{1,2}) ([A-Za-z]+) (\d{4})", text)
    if day_month_year:
        start_day, end_day, month, year = day_month_year.groups()
        return f"{int(start_day)} {month} {year}", f"{int(end_day)} {month} {year}"
    dual_month_day_year = re.fullmatch(r"([A-Za-z]+ \d{1,2}) ?(?:-|–|—|to) ?([A-Za-z]+ \d{1,2}), (\d{4})", text)
    if dual_month_day_year:
        start_part, end_part, year = dual_month_day_year.groups()
        return f"{start_part}, {year}", f"{end_part}, {year}"
    for separator in ("–", "—", " - "):
        if separator in text:
            left, right = [normalize_space(part) for part in text.split(separator, 1)]
            if left and right:
                return left, right
    return text, ""


def add_security_event_row(
    rows: list[dict[str, str]],
    conference_key: str,
    event_type: str,
    raw_value: str,
    source_url: str,
    *,
    notes: str = "",
    confidence: str = "0.8",
) -> None:
    value = normalize_space(raw_value)
    if not value:
        return
    conference = CONFERENCES[conference_key]
    rows.append(
        {
            "conference_key": conference.key,
            "conference": conference.conference,
            "year": str(conference.year),
            "event_type": event_type,
            "event_date": value,
            "event_datetime": "",
            "timezone": "",
            "deadline_scope": "",
            "source_text": value,
            "source_url": source_url,
            "source_kind": "official_cfp_page",
            "confidence": confidence,
            "needs_review": "false",
            "notes": notes,
        }
    )


def extract_security_header_metadata(conference_key: str, text: str) -> dict[str, str]:
    conference = CONFERENCES[conference_key]
    result = {"location": "", "country": "", "start_date": "", "end_date": ""}
    if conference.conference == "USENIX_SECURITY":
        match = re.search(r"held (?:on )?([A-Za-z]+ \d{1,2}[–-]\d{1,2}, \d{4}), in ([^.]+)\.", text)
        if not match:
            match = re.search(r"held as a virtual event on ([A-Za-z]+ \d{1,2}[–-]\d{1,2}, \d{4})", text)
            if match:
                result["location"] = "Virtual"
                result["country"] = ""
                result["start_date"], result["end_date"] = parse_date_range_text(match.group(1))
                return result
        if not match:
            match = re.search(r"held ([A-Za-z]+ \d{1,2}[–-]\d{1,2}, \d{4})\.", text)
        if match:
            if match.lastindex and match.lastindex >= 2:
                result["location"] = normalize_space(match.group(2))
                result["country"] = "United States" if any(marker in match.group(2) for marker in ("USA", ", CA", ", WA", ", PA")) else ""
            result["start_date"], result["end_date"] = parse_date_range_text(match.group(1))
    elif conference.conference == "NDSS":
        match = re.search(r"will take place in ([^.]+), from ([^.]+?)\.", text)
        if match:
            result["location"] = normalize_space(match.group(1))
            result["country"] = "United States" if "USA" in match.group(1) else ""
            result["start_date"], result["end_date"] = parse_date_range_text(match.group(2))
        else:
            match = re.search(r"(?:NDSS \d{4} Workshops and Symposium|NDSS Symposium,? and Workshops):?\s*([A-Za-z]+ \d{1,2}[–-]\d{1,2}, \d{4}|\d{1,2} ?[–-] ?\d{1,2} [A-Za-z]+ \d{4}|February \d{1,2}-\d{1,2}, \d{4})\s*[—-]\s*([A-Za-z ,]+)", text)
            if match:
                result["location"] = normalize_space(match.group(2))
                result["country"] = "United States" if "CA" in match.group(2) or "USA" in match.group(2) else ""
                result["start_date"], result["end_date"] = parse_date_range_text(match.group(1))
    elif conference.conference == "IEEE_S&P":
        match = re.search(r"The Symposium will be held on ([A-Za-z]+ \d{1,2}[–-]\d{1,2}, \d{4}).*? in ([^.]+)\.", text)
        if not match:
            match = re.search(r"([A-Z]+ \d{1,2}[–-]\d{1,2}, \d{4}) AT ([A-Za-z0-9 ,.'-]+)", text)
        if match:
            if match.lastindex and match.lastindex >= 2:
                result["location"] = normalize_space(match.group(2)).title()
                result["country"] = "United States" if any(marker in match.group(2) for marker in ("CA", "USA", "San Francisco")) else ""
            result["start_date"], result["end_date"] = parse_date_range_text(match.group(1).title())
        else:
            match = re.search(r"([A-Z]+ \d{1,2}[–-]\d{1,2}, \d{4})", text)
            if match:
                result["start_date"], result["end_date"] = parse_date_range_text(match.group(1).title())
    elif conference.conference == "CCS":
        match = re.search(r"ACM CCS \d{4} ([A-Za-z]+ \d{1,2}[–-]\d{1,2}, \d{4}) ([A-Za-z ,.'-]+?(?:U\.S\.A\.|USA|Taiwan))", text)
        if match:
            result["location"] = normalize_space(match.group(2))
            if "Taiwan" in match.group(2):
                result["country"] = "Taiwan"
            elif "USA" in match.group(2) or "U.S.A." in match.group(2):
                result["country"] = "United States"
            result["start_date"], result["end_date"] = parse_date_range_text(match.group(1))
        else:
            match = re.search(r"ACM CCS \d{4},? ([A-Za-z]+ \d{1,2}[–-]\d{1,2})", text)
            if match:
                result["location"] = "Virtual"
                result["start_date"], result["end_date"] = parse_date_range_text(match.group(1) + ", 2021")
            else:
                match = re.search(r"ACM CCS 2020 - ([A-Za-z]+ \d{1,2}[–-]\d{1,2}, \d{4})", text)
                if match:
                    result["location"] = "Virtual"
                    result["start_date"], result["end_date"] = parse_date_range_text(match.group(1))
    return result


def extract_security_events(conference_key: str, text: str, source_url: str) -> list[dict[str, str]]:
    conference = CONFERENCES[conference_key]
    rows: list[dict[str, str]] = []
    if conference.conference == "USENIX_SECURITY":
        patterns = [
            (r"submissions? due:\s*([^\n*]+?\d{4}(?:, 11:59 pm [A-Za-z]+)?)", "paper_submission_deadline"),
            (r"Early reject notification:\s*([^\n*]+?\d{4})", "first_round_notification"),
            (r"Rebuttal Period:\s*([A-Za-z]+ \d{1,2}[–-]\d{1,2}, \d{4})", "rebuttal_range"),
            (r"Notification to authors:\s*([^\n*]+?\d{4})", "notification"),
            (r"Decisions? sent to authors:\s*([^\n*]+?\d{4})", "notification"),
            (r"Final paper files due:\s*([^\n*]+?\d{4})", "camera_ready"),
            (r"Final papers due:\s*([^\n*]+?\d{4})", "camera_ready")
        ]
    elif conference.conference == "NDSS":
        patterns = [
            (r"(?:Full )?[Pp]aper submission deadline(?: for technical papers)?\s*[:]?\s*([^\n]+?\d{4})", "paper_submission_deadline"),
            (r"Early (?:reject|notification).*?([A-Za-z]{3,9} ?\d{1,2},? \d{4})", "first_round_notification"),
            (r"Author rebuttal(?: period)?(?: starts)?\s*[:]?\s*([^\n]+?\d{4}|[^\n]+?\d{1,2})", "rebuttal_range"),
            (r"Author notification(?: of acceptance/minor revision/major revision/rejection| for Major Revision papers)?\s*[:]?\s*([^\n]+?\d{4})", "notification"),
            (r"Camera Ready deadline\s*[:]?\s*([^\n]+?\d{4})", "camera_ready")
        ]
        old_style_patterns = [
            (r"([A-Za-z]+ \d{1,2}, \d{4}): Full submissions? for technical papers", "paper_submission_deadline"),
            (r"([A-Za-z]+ \d{1,2}, \d{4}): Early notification", "first_round_notification"),
            (r"([A-Za-z]+ \d{1,2}[–-]\d{1,2}, \d{4}): Author rebuttal", "rebuttal_range"),
            (r"([A-Za-z]+ \d{1,2}, \d{4}): Notification(?: of acceptance|min|major revision|rejection| of acceptance/minor revision/major revision/rejection)?", "notification"),
            (r"([A-Za-z]+ \d{1,2}, \d{4}): Resubmission of revised papers", "camera_ready"),
            (r"([A-Za-z]+ \d{1,2}, \d{4}): Camera Ready deadline", "camera_ready")
        ]
        for pattern, event_type in old_style_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                value = normalize_space(match.group(1))
                if event_type == "rebuttal_range":
                    start_value, end_value = parse_date_range_text(value)
                    add_security_event_row(rows, conference_key, "rebuttal_start", start_value, source_url, notes="auto_extracted_rebuttal_range")
                    if end_value:
                        add_security_event_row(rows, conference_key, "rebuttal_end", end_value, source_url, notes="auto_extracted_rebuttal_range")
                else:
                    add_security_event_row(rows, conference_key, event_type, value, source_url)
    elif conference.conference == "IEEE_S&P":
        patterns = [
            (r"Paper submission deadline:\s*([A-Za-z]+ \d{1,2}, \d{4})", "paper_submission_deadline"),
            (r"Early-reject notification:\s*([A-Za-z]+ \d{1,2}, \d{4})", "first_round_notification"),
            (r"Rebuttal period \(interactive\):\s*([A-Za-z]+ \d{1,2} - [A-Za-z]+ \d{1,2}, \d{4})", "rebuttal_range"),
            (r"Rebuttal text due:\s*([A-Za-z]+ \d{1,2}, \d{4})", "rebuttal_end"),
            (r"Acceptance notification:\s*([A-Za-z]+ \d{1,2}, \d{4})", "notification"),
            (r"Camera-ready deadline:\s*([A-Za-z]+ \d{1,2}, \d{4})", "camera_ready")
        ]
    else:
        patterns = [
            (r"Abstract submission deadline.*?([A-Za-z]+ \d{1,2}, \d{4}|[A-Za-z]+ \d{1,2}th, \d{4}|\d{1,2} [A-Za-z]+, \d{4})", "abstract_submission_deadline"),
            (r"Full paper submission deadline.*?([A-Za-z]+ \d{1,2}, \d{4}|[A-Za-z]+ \d{1,2}th, \d{4}|\d{1,2} [A-Za-z]+, \d{4})", "paper_submission_deadline"),
            (r"Paper submission deadline.*?([A-Za-z]+ \d{1,2}, \d{4}|[A-Za-z]+ \d{1,2}th, \d{4}|\d{1,2} [A-Za-z]+, \d{4})", "paper_submission_deadline"),
            (r"Notification of early-rejection papers.*?([A-Za-z]+ \d{1,2}, \d{4})", "first_round_notification"),
            (r"Author rebuttal period.*?([A-Za-z]+ \d{1,2}[—–-]\d{1,2}, \d{4}|[A-Za-z]{3,9} \d{1,2}-\d{1,2}, \d{4}|\d{1,2} [A-Za-z]+ ?- ?\d{1,2} [A-Za-z]+ \d{4})", "rebuttal_range"),
            (r"Rebuttal deadline.*?([A-Za-z]+ \d{1,2}, \d{4})", "rebuttal_end"),
            (r"Author notification.*?([A-Za-z]+ \d{1,2}, \d{4})", "notification")
        ]

    for pattern, event_type in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            value = normalize_space(match.group(1))
            if event_type == "rebuttal_range":
                start_value, end_value = parse_date_range_text(value)
                add_security_event_row(rows, conference_key, "rebuttal_start", start_value, source_url, notes="auto_extracted_rebuttal_range")
                if end_value:
                    add_security_event_row(rows, conference_key, "rebuttal_end", end_value, source_url, notes="auto_extracted_rebuttal_range")
            else:
                add_security_event_row(rows, conference_key, event_type, value, source_url)
    header = extract_security_header_metadata(conference_key, text)
    add_security_event_row(rows, conference_key, "conference_start", header.get("start_date", ""), source_url)
    add_security_event_row(rows, conference_key, "conference_end", header.get("end_date", ""), source_url)
    return rows


def merge_security_edition(base_row: dict[str, object], header: dict[str, str]) -> dict[str, object]:
    if not any(header.values()):
        return base_row
    return {
        **base_row,
        "location": header.get("location", "") or str(base_row.get("location", "")),
        "country": header.get("country", "") or str(base_row.get("country", "")),
        "start_date": normalize_date(header.get("start_date", "")) or str(base_row.get("start_date", "")),
        "end_date": normalize_date(header.get("end_date", "")) or str(base_row.get("end_date", "")),
        "confidence": "0.8",
        "needs_review": "false" if header.get("start_date") and header.get("end_date") else str(base_row.get("needs_review", "true")),
        "notes": "official_security_cfp_page",
    }


def snapshot_event_rows(conference_key: str, snapshot: dict[str, object], source_url: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in snapshot.get("events", []):
        event_type = normalize_space(str(item.get("event_type", "")))
        event_date = normalize_space(str(item.get("event_date", "")))
        if event_type and event_date:
            add_security_event_row(
                rows,
                conference_key,
                event_type,
                event_date,
                source_url,
                notes=normalize_space(str(item.get("notes", ""))) or "snapshot_fallback",
                confidence=normalize_space(str(item.get("confidence", ""))) or "0.85",
            )
            rows[-1]["deadline_scope"] = normalize_space(str(item.get("deadline_scope", "")))
            rows[-1]["source_text"] = normalize_space(str(item.get("source_text", ""))) or rows[-1]["source_text"]
    return rows


def snapshot_edition_row(base_row: dict[str, object], snapshot: dict[str, object]) -> dict[str, object]:
    edition = snapshot.get("edition", {})
    if not isinstance(edition, dict):
        return base_row
    return {
        **base_row,
        "location": normalize_space(str(edition.get("location", ""))) or str(base_row.get("location", "")),
        "country": normalize_space(str(edition.get("country", ""))) or str(base_row.get("country", "")),
        "start_date": normalize_date(str(edition.get("start_date", ""))) or str(base_row.get("start_date", "")),
        "end_date": normalize_date(str(edition.get("end_date", ""))) or str(base_row.get("end_date", "")),
        "confidence": "0.85",
        "needs_review": "false",
        "notes": "security_snapshot_fallback",
    }


def auto_fetch_security_data(selected_keys: list[str]) -> tuple[list[dict[str, str]], dict[str, dict[str, object]], list[dict[str, object]]]:
    event_rows: list[dict[str, str]] = []
    editions: dict[str, dict[str, object]] = {}
    findings: list[dict[str, object]] = []
    snapshots = load_security_snapshots()
    for key in selected_keys:
        conference = CONFERENCES[key]
        if conference.family != "security":
            continue
        urls = infer_cfp_urls(key, conference.conference, conference.year)
        cfp_url = urls.get("cfp_url", "")
        website_url = urls.get("website_url", "")
        if not cfp_url:
            continue
        snapshot = snapshots.get(key)
        try:
            text = strip_html_to_text(fetch_text(cfp_url))
        except Exception as exc:
            if snapshot:
                event_rows.extend(snapshot_event_rows(key, snapshot, cfp_url))
                editions[key] = snapshot_edition_row(inferred_edition_row(key), snapshot)
                findings.append({"severity": "low", "code": "security_snapshot_fallback", "row": key, "message": f"{cfp_url} :: {exc}"})
            else:
                findings.append({"severity": "medium", "code": "security_cfp_fetch_failed", "row": key, "message": f"{cfp_url} :: {exc}"})
            continue
        rows = extract_security_events(key, text, cfp_url)
        if rows:
            event_rows.extend(rows)
        else:
            findings.append({"severity": "medium", "code": "security_cfp_parse_empty", "row": key, "message": cfp_url})
        header = extract_security_header_metadata(key, text)
        if not any(header.values()) and website_url and website_url != cfp_url:
            try:
                header = extract_security_header_metadata(key, strip_html_to_text(fetch_text(website_url)))
            except Exception:
                pass
        edition_row = merge_security_edition(inferred_edition_row(key), header)
        if snapshot:
            event_rows.extend(snapshot_event_rows(key, snapshot, cfp_url))
            edition_row = snapshot_edition_row(edition_row, snapshot)
            findings.append({"severity": "low", "code": "security_snapshot_fallback", "row": key, "message": cfp_url})
        editions[key] = edition_row
    return event_rows, editions, findings


def merge_row_values(base: dict[str, object], override: dict[str, str], fieldnames: list[str]) -> dict[str, object]:
    merged = dict(base)
    for field in fieldnames:
        value = normalize_space(str(override.get(field, "")))
        if value:
            merged[field] = value
    return merged


def selected_conference_keys(args: argparse.Namespace) -> list[str]:
    selected = expand_selection(args.conference, args.group)
    return selected or sorted(CONFERENCES)


def template_event_rows(selected_keys: list[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for key in sorted(selected_keys, key=lambda value: (CONFERENCES[value].family, CONFERENCES[value].conference, CONFERENCES[value].year)):
        conference = CONFERENCES[key]
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


def template_edition_rows(selected_keys: list[str]) -> list[dict[str, object]]:
    return [inferred_edition_row(key) for key in sorted(selected_keys, key=lambda value: (CONFERENCES[value].family, CONFERENCES[value].conference, CONFERENCES[value].year))]


def load_seeded_events(selected_keys: list[str], input_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    selected_set = set(selected_keys)
    return [row for row in input_rows if row.get("conference_key", "").strip() in selected_set]


def load_seeded_editions(selected_keys: list[str], input_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    selected_set = set(selected_keys)
    merged_by_key = {key: inferred_edition_row(key) for key in selected_keys}
    for row in input_rows:
        key = row.get("conference_key", "").strip()
        if key not in selected_set:
            continue
        merged_by_key[key] = merge_row_values(merged_by_key.get(key, inferred_edition_row(key)), row, EDITION_FIELDS)
    return [merged_by_key[key] for key in selected_keys]


def merge_auto_editions(base_rows: list[dict[str, object]], fetched_rows: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    merged: list[dict[str, object]] = []
    for row in base_rows:
        key = str(row.get("conference_key", ""))
        merged.append(fetched_rows.get(key, row))
    return merged


def normalize_events(rows: list[dict[str, str]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    normalized: list[dict[str, object]] = []
    findings: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        key = normalize_space(row.get("conference_key", ""))
        event_type = normalize_space(row.get("event_type", ""))
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
                "conference": normalize_space(row.get("conference", "")) or (conference.conference if conference else ""),
                "year": normalize_space(row.get("year", "")) or (conference.year if conference else ""),
                "event_type": event_type,
                "event_date": event_date,
                "event_datetime": normalize_space(row.get("event_datetime", "")),
                "timezone": normalize_space(row.get("timezone", "")),
                "deadline_scope": normalize_space(row.get("deadline_scope", "")),
                "source_text": normalize_space(row.get("source_text", "")),
                "source_url": normalize_space(row.get("source_url", "")),
                "source_kind": normalize_space(row.get("source_kind", "")) or "manual",
                "confidence": confidence_value(row.get("confidence", ""), default="0.5" if event_date else "0.0"),
                "needs_review": needs_review,
                "notes": normalize_space(row.get("notes", "")),
            }
        )
    return normalized, findings


def normalize_editions(rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    normalized: list[dict[str, object]] = []
    findings: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        key = normalize_space(str(row.get("conference_key", "")))
        needs_review = bool_text(row.get("needs_review", ""))
        if not key or key not in CONFERENCES:
            findings.append({"severity": "high", "code": "unknown_conference_key", "row": index, "message": key})
            needs_review = "true"
        conference = CONFERENCES.get(key)
        normalized.append(
            {
                "conference_key": key,
                "conference": normalize_space(str(row.get("conference", ""))) or (conference.conference if conference else ""),
                "year": normalize_space(str(row.get("year", ""))) or (conference.year if conference else ""),
                "family": normalize_space(str(row.get("family", ""))) or (conference.family if conference else ""),
                "location": normalize_space(str(row.get("location", ""))),
                "country": normalize_space(str(row.get("country", ""))),
                "start_date": normalize_date(row.get("start_date", "")),
                "end_date": normalize_date(row.get("end_date", "")),
                "timezone": normalize_space(str(row.get("timezone", ""))),
                "website_url": normalize_space(str(row.get("website_url", ""))),
                "cfp_url": normalize_space(str(row.get("cfp_url", ""))),
                "proceedings_url": normalize_space(str(row.get("proceedings_url", ""))),
                "source_url": normalize_space(str(row.get("source_url", ""))),
                "confidence": confidence_value(row.get("confidence", ""), default="0.5"),
                "needs_review": needs_review,
                "notes": normalize_space(str(row.get("notes", ""))),
            }
        )
    return normalized, findings


def dedupe_event_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped: list[dict[str, object]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in rows:
        key = (
            str(row.get("conference_key", "")),
            str(row.get("event_type", "")),
            str(row.get("event_date", "")),
            str(row.get("source_url", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def build_review_queue(events: list[dict[str, object]], editions: list[dict[str, object]], findings: list[dict[str, object]], selected_keys: list[str]) -> list[dict[str, object]]:
    queue: list[dict[str, object]] = []
    events_by_key: dict[str, list[dict[str, object]]] = {}
    editions_by_key = {str(row.get("conference_key", "")): row for row in editions}
    for row in events:
        key = str(row.get("conference_key", ""))
        if key:
            events_by_key.setdefault(key, []).append(row)

    for key in selected_keys:
        conference = CONFERENCES[key]
        key_events = events_by_key.get(key, [])
        available_types = {str(row.get("event_type", "")) for row in key_events if str(row.get("event_date", ""))}
        for event_type in CORE_EVENT_TYPES:
            if event_type not in available_types:
                queue.append(
                    {
                        "conference_key": key,
                        "conference": conference.conference,
                        "year": conference.year,
                        "issue_type": "missing_core_event",
                        "detail": event_type,
                        "needs_review": "true",
                        "source": "pipeline_check",
                    }
                )
        edition = editions_by_key.get(key)
        if not edition:
            queue.append(
                {
                    "conference_key": key,
                    "conference": conference.conference,
                    "year": conference.year,
                    "issue_type": "missing_edition_row",
                    "detail": "conference_edition_metadata",
                    "needs_review": "true",
                    "source": "pipeline_check",
                }
            )
            continue
        for field in ("website_url", "cfp_url", "proceedings_url", "start_date", "end_date"):
            if not str(edition.get(field, "")).strip():
                queue.append(
                    {
                        "conference_key": key,
                        "conference": conference.conference,
                        "year": conference.year,
                        "issue_type": "missing_edition_field",
                        "detail": field,
                        "needs_review": "true",
                        "source": "pipeline_check",
                    }
                )
    for finding in findings:
        if str(finding.get("severity", "")).lower() == "low":
            continue
        row_number = finding.get("row", "")
        queue.append(
            {
                "conference_key": "",
                "conference": "",
                "year": "",
                "issue_type": str(finding.get("code", "finding")),
                "detail": f"row={row_number} {finding.get('message', '')}".strip(),
                "needs_review": "true",
                "source": "validation_finding",
            }
        )
    return queue


def compute_cfp_status(events: list[dict[str, object]], editions: list[dict[str, object]], selected_keys: list[str]) -> list[dict[str, object]]:
    events_by_key: dict[str, list[dict[str, object]]] = {}
    editions_by_key = {str(row.get("conference_key", "")): row for row in editions}
    for row in events:
        key = str(row.get("conference_key", ""))
        if key:
            events_by_key.setdefault(key, []).append(row)

    rows: list[dict[str, object]] = []
    for key in selected_keys:
        conference = CONFERENCES[key]
        key_events = events_by_key.get(key, [])
        edition = editions_by_key.get(key)
        core_present = sorted(
            {
                str(row.get("event_type", ""))
                for row in key_events
                if str(row.get("event_type", "")) in CORE_EVENT_TYPES and str(row.get("event_date", ""))
            }
        )
        review_count = sum(1 for row in key_events if str(row.get("needs_review", "")).lower() == "true")
        if edition and str(edition.get("needs_review", "")).lower() == "true":
            review_count += 1
        if not key_events and not edition:
            status = "missing"
        elif review_count > 0:
            status = "needs_review"
        elif len(core_present) == len(CORE_EVENT_TYPES) and edition:
            status = "complete_unverified"
        else:
            status = "partial"
        rows.append(
            {
                "conference_key": key,
                "conference": conference.conference,
                "year": conference.year,
                "event_count": len(key_events),
                "dated_event_count": sum(1 for row in key_events if str(row.get("event_date", ""))),
                "core_events_present": ", ".join(core_present),
                "edition_present": "true" if edition else "false",
                "needs_review_rows": review_count,
                "cfp_status": status,
            }
        )
    return rows


def write_reports(
    output_dir: Path,
    events: list[dict[str, object]],
    editions: list[dict[str, object]],
    findings: list[dict[str, object]],
    selected_keys: list[str],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    event_keys = {str(row.get("conference_key", "")) for row in events if row.get("conference_key")}
    edition_keys = {str(row.get("conference_key", "")) for row in editions if row.get("conference_key")}
    coverage_rows = compute_cfp_status(events, editions, selected_keys)
    review_queue = build_review_queue(events, editions, findings, selected_keys)
    status_counts = Counter(str(row["cfp_status"]) for row in coverage_rows)
    payload = {
        "registered_conference_years": len(selected_keys),
        "event_rows": len(events),
        "edition_rows": len(editions),
        "conference_years_with_events": len(event_keys),
        "conference_years_with_editions": len(edition_keys),
        "missing_event_conference_years": len(set(selected_keys) - event_keys),
        "missing_edition_conference_years": len(set(selected_keys) - edition_keys),
        "coverage_status_counts": dict(status_counts),
        "review_queue_rows": len(review_queue),
        "findings": findings,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (output_dir / "cfp_validation_report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(output_dir / "cfp_review_queue.csv", review_queue, REVIEW_QUEUE_FIELDS)
    write_csv(output_dir / "cfp_coverage_summary.csv", coverage_rows, OUTPUT_STATUS_FIELDS)

    lines = [
        "# CFP Extraction Report",
        "",
        "## Summary",
        "",
        f"- registered_conference_years: {payload['registered_conference_years']}",
        f"- event_rows: {payload['event_rows']}",
        f"- edition_rows: {payload['edition_rows']}",
        f"- conference_years_with_events: {payload['conference_years_with_events']}",
        f"- conference_years_with_editions: {payload['conference_years_with_editions']}",
        f"- missing_event_conference_years: {payload['missing_event_conference_years']}",
        f"- missing_edition_conference_years: {payload['missing_edition_conference_years']}",
        f"- review_queue_rows: {payload['review_queue_rows']}",
        f"- findings: {len(findings)}",
        "",
        "## Notes",
        "",
        "- This pipeline is seed-first: it auto-prefills conference-edition metadata from registry URL patterns and merges user-provided inputs.",
        "- It does not fetch external CFP pages by default; inferred rows stay marked needs_review until verified.",
        "- Rows with missing dates or unknown event types are emitted into cfp_review_queue.csv.",
    ]
    (output_dir / "cfp_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and normalize CFP metadata tables.")
    parser.add_argument("--conference", action="append", default=[], help="Conference key to include. Repeatable.")
    parser.add_argument("--group", action="append", default=[], help="Conference group to include. Repeatable.")
    parser.add_argument("--events-input", type=Path, help="Optional CSV containing CFP event rows")
    parser.add_argument("--edition-input", type=Path, help="Optional CSV containing conference edition metadata")
    parser.add_argument("--fetch-iacr", action="store_true", help="Fetch CFP metadata for IACR conferences from official metadata.json files")
    parser.add_argument("--fetch-security", action="store_true", help="Fetch CFP metadata for security conferences from official CFP pages")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    template_dir = output_dir / "input_templates"
    final_dir = output_dir / "output"
    input_dir = output_dir / "input"
    selected_keys = selected_conference_keys(args)

    write_csv(template_dir / "cfp_events_template.csv", template_event_rows(selected_keys), EVENT_FIELDS)
    write_csv(template_dir / "conference_edition_template.csv", template_edition_rows(selected_keys), EDITION_FIELDS)

    events_input_path = args.events_input.resolve() if args.events_input else default_input_path(input_dir / "cfp_events_input.csv")
    edition_input_path = args.edition_input.resolve() if args.edition_input else default_input_path(input_dir / "conference_edition_input.csv")

    event_input_rows = load_seeded_events(selected_keys, read_csv(events_input_path))
    edition_input_rows = load_seeded_editions(selected_keys, read_csv(edition_input_path))

    auto_event_rows: list[dict[str, str]] = []
    auto_edition_rows: dict[str, dict[str, object]] = {}
    auto_findings: list[dict[str, object]] = []
    if args.fetch_iacr:
        auto_event_rows, auto_edition_rows, auto_findings = auto_fetch_iacr_data(selected_keys)
        event_input_rows = auto_event_rows + event_input_rows
        edition_input_rows = merge_auto_editions(edition_input_rows, auto_edition_rows)
    if args.fetch_security:
        security_event_rows, security_edition_rows, security_findings = auto_fetch_security_data(selected_keys)
        event_input_rows = security_event_rows + event_input_rows
        edition_input_rows = merge_auto_editions(edition_input_rows, security_edition_rows)
        auto_findings.extend(security_findings)

    events, event_findings = normalize_events(event_input_rows)
    editions, edition_findings = normalize_editions(edition_input_rows)
    events = dedupe_event_rows(events)
    write_csv(final_dir / "conference_events.csv", events, EVENT_FIELDS)
    write_csv(final_dir / "conference_edition_metadata.csv", editions, EDITION_FIELDS)
    write_reports(final_dir, events, editions, auto_findings + event_findings + edition_findings, selected_keys)


if __name__ == "__main__":
    main()
