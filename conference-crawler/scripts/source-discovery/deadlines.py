"""Collect CFP deadlines from configured official conference pages."""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from registry import CONFERENCE_REGISTRY


OUTPUT_FIELDS = [
    "conference",
    "year",
    "source_kind",
    "source_url",
    "final_url",
    "source_sha256",
    "page_title",
    "deadline_type",
    "raw_deadline",
    "deadline_date",
    "deadline_timezone",
    "evidence_text",
    "status",
    "observed_at",
    "error",
]

MONTH_PATTERN = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)
MONTH_NUMBERS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
DATE_PATTERNS = [
    re.compile(
        rf"\b(?P<month>{MONTH_PATTERN})\.?\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?[,]?\s+(?P<year>(?:19|20)\d{{2}})\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month>{MONTH_PATTERN})\.?[,]?\s+(?P<year>(?:19|20)\d{{2}})\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?P<year>(?:19|20)\d{2})-(?P<month>0[1-9]|1[0-2])-(?P<day>0[1-9]|[12]\d|3[01])\b"),
]
DEADLINE_LABEL_RE = re.compile(
    r"\b(?P<label>"
    r"abstract(?:\s+submission)?\s+deadline|"
    r"deadline\s+for\s+abstract\s+submissions?|"
    r"full\s+paper\s+submission\s+deadline|"
    r"paper\s+submission\s+deadline|"
    r"submission\s+deadline|"
    r"deadline\s+for\s+(?:full\s+paper\s+)?submissions?"
    r")\b",
    re.IGNORECASE,
)
TIMEZONE_RE = re.compile(
    r"\b(?:AoE|Anywhere\s+on\s+Earth|UTC\s*[+-]\s*\d{1,2}(?::?\d{2})?)\b",
    re.IGNORECASE,
)


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _resolve_conference(name: str) -> tuple[str, dict[str, object]]:
    normalized = _normalize_name(name)
    for key, config in CONFERENCE_REGISTRY.items():
        aliases = [key, *config.get("aliases", [])]
        if normalized in {_normalize_name(str(alias)) for alias in aliases}:
            return key, config
    raise ValueError(f"Unknown conference: {name}")


def _date_matches(text: str) -> list[tuple[re.Match[str], date]]:
    matches: list[tuple[re.Match[str], date]] = []
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(text):
            year = int(match.group("year"))
            month_text = match.group("month")
            month = int(month_text) if month_text.isdigit() else MONTH_NUMBERS[month_text[:3].casefold()]
            day = int(match.group("day"))
            try:
                parsed = date(year, month, day)
            except ValueError:
                continue
            matches.append((match, parsed))
    return sorted(matches, key=lambda item: item[0].start())


def _deadline_type(label: str) -> str:
    normalized = label.casefold()
    if "abstract" in normalized:
        return "abstract_submission"
    if "paper" in normalized or "full" in normalized:
        return "full_paper_submission"
    return "submission"


def _timezone_near(text: str, start: int, end: int) -> str:
    matches = list(TIMEZONE_RE.finditer(text))
    if not matches:
        return ""
    closest = min(matches, key=lambda item: min(abs(item.start() - end), abs(start - item.end())))
    if min(abs(closest.start() - end), abs(start - closest.end())) > 100:
        return ""
    return closest.group(0)


def _candidate_blocks(soup: BeautifulSoup) -> list[str]:
    blocks: list[str] = []
    seen: set[str] = set()
    for element in soup.find_all(["p", "li", "tr"]):
        text = " ".join(element.stripped_strings)
        text = re.sub(r"\s+", " ", text).strip()
        if text and text not in seen:
            seen.add(text)
            blocks.append(text)
    if soup.body:
        text = re.sub(r"\s+", " ", " ".join(soup.body.stripped_strings)).strip()
        has_labeled_date = any(DEADLINE_LABEL_RE.search(block) and _date_matches(block) for block in blocks)
        if text and text not in seen and not has_labeled_date:
            blocks.append(text)
    return blocks


def extract_deadlines(html: str | bytes) -> tuple[str, list[dict[str, str]]]:
    """Return the page title and only explicitly labeled submission deadlines."""
    soup = BeautifulSoup(html, "lxml")
    for element in soup(["script", "style", "noscript"]):
        element.decompose()
    page_title = soup.title.get_text(" ", strip=True) if soup.title else ""
    blocks = _candidate_blocks(soup)
    if not blocks and soup.get_text(" ", strip=True):
        blocks = [re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()]

    found: dict[tuple[str, str], dict[str, str]] = {}
    for block in blocks:
        labels = list(DEADLINE_LABEL_RE.finditer(block))
        if not labels:
            continue
        for date_match, parsed_date in _date_matches(block):
            label_match = min(
                labels,
                key=lambda label: min(
                    abs(label.start() - date_match.end()),
                    abs(date_match.start() - label.end()),
                ),
            )
            distance = min(
                abs(label_match.start() - date_match.end()),
                abs(date_match.start() - label_match.end()),
            )
            if distance > 180:
                continue
            deadline_type = _deadline_type(label_match.group("label"))
            candidate = {
                "deadline_type": deadline_type,
                "raw_deadline": date_match.group(0),
                "deadline_date": parsed_date.isoformat(),
                "deadline_timezone": _timezone_near(block, date_match.start(), date_match.end()),
                "evidence_text": block,
                "status": "parsed",
            }
            key = (deadline_type, candidate["raw_deadline"])
            previous = found.get(key)
            if previous is None or len(block) < len(previous["evidence_text"]):
                found[key] = candidate

    return page_title, list(found.values())


def _base_record(conference: str, year: int, source_url: str, source_kind: str) -> dict[str, str]:
    return {
        "conference": conference,
        "year": str(year),
        "source_kind": source_kind,
        "source_url": source_url,
        "final_url": "",
        "source_sha256": "",
        "page_title": "",
        "deadline_type": "",
        "raw_deadline": "",
        "deadline_date": "",
        "deadline_timezone": "",
        "evidence_text": "",
        "status": "",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "error": "",
    }


def collect_deadlines(
    conferences: list[str],
    years: list[int],
    source_url_override: str | None = None,
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for conference_name in conferences:
        try:
            conference, config = _resolve_conference(conference_name)
        except ValueError as exc:
            for year in years:
                row = _base_record(conference_name, year, source_url_override or "", "unconfigured")
                row.update(status="unknown_conference", error=str(exc))
                records.append(row)
            continue

        template = config.get("cfp_url_template")
        for year in years:
            if source_url_override:
                source_url = source_url_override
                source_kind = "user_supplied"
            elif template:
                source_url = str(template).format(year=year)
                source_kind = "configured_official_cfp"
            else:
                row = _base_record(conference, year, "", "unconfigured")
                row.update(status="no_configured_source", error="No CFP URL template is configured")
                records.append(row)
                continue

            base = _base_record(conference, year, source_url, source_kind)
            try:
                response = requests.get(
                    source_url,
                    headers={"User-Agent": "conference-crawler-deadline-audit/1.0"},
                    timeout=30,
                )
                response.raise_for_status()
                content = response.content
                page_title, deadlines = extract_deadlines(content)
                digest = hashlib.sha256(content).hexdigest()
                common = {
                    "final_url": str(getattr(response, "url", "") or source_url),
                    "source_sha256": digest,
                    "page_title": page_title,
                }
                if deadlines:
                    for deadline in deadlines:
                        row = {**base, **common, **deadline}
                        records.append(row)
                else:
                    row = {**base, **common}
                    row.update(status="no_deadline_found")
                    records.append(row)
            except requests.RequestException as exc:
                base.update(status="fetch_failed", error=str(exc))
                records.append(base)
            except (OSError, ValueError) as exc:
                base.update(status="parse_failed", error=str(exc))
                records.append(base)
    return records


def save_deadline_observations(records: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged: dict[tuple[str, ...], dict[str, str]] = {}
    if output_path.exists():
        with output_path.open(encoding="utf-8-sig", newline="") as file_obj:
            for row in csv.DictReader(file_obj):
                key = tuple(row.get(field, "") for field in (
                    "conference", "year", "source_url", "source_sha256",
                    "deadline_type", "raw_deadline", "status", "error",
                ))
                merged[key] = row

    for row in records:
        key = tuple(row.get(field, "") for field in (
            "conference", "year", "source_url", "source_sha256",
            "deadline_type", "raw_deadline", "status", "error",
        ))
        merged[key] = row

    rows = sorted(
        merged.values(),
        key=lambda row: (
            row.get("conference", ""),
            row.get("year", ""),
            row.get("source_url", ""),
            row.get("deadline_type", ""),
            row.get("deadline_date", ""),
            row.get("observed_at", ""),
        ),
    )
    with output_path.open("w", newline="", encoding="utf-8-sig") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in OUTPUT_FIELDS} for row in rows)


def main(argv: list[str] | None = None) -> int:
    crawler_root = Path(__file__).resolve().parents[2]
    default_output = crawler_root / "scripts" / "download" / "metadata" / "conference_deadline_observations.csv"
    parser = argparse.ArgumentParser(description="Collect auditable deadlines from configured official CFP pages")
    parser.add_argument("--conferences", required=True, help="Comma-separated registry names or aliases")
    parser.add_argument("--years", required=True, help="Comma-separated conference years")
    parser.add_argument("--source-url", help="Override the CFP URL; use for one conference/year only")
    parser.add_argument("--output", type=Path, default=default_output)
    args = parser.parse_args(argv)
    conferences = [item.strip() for item in args.conferences.split(",") if item.strip()]
    years = [int(item.strip()) for item in args.years.split(",") if item.strip()]
    if not conferences or not years:
        parser.error("at least one conference and year are required")
    if args.source_url and (len(conferences) != 1 or len(years) != 1):
        parser.error("--source-url requires exactly one conference and one year")

    records = collect_deadlines(conferences, years, args.source_url)
    save_deadline_observations(records, args.output)
    for row in records:
        print(
            f"[DEADLINE] {row['conference']} {row['year']} "
            f"status={row['status']} type={row['deadline_type']} date={row['deadline_date']}"
        )
    return int(any(row["status"] in {"fetch_failed", "parse_failed", "no_configured_source", "unknown_conference"} for row in records))


if __name__ == "__main__":
    sys.exit(main())
