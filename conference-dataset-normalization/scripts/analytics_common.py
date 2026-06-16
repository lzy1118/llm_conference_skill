from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def slug_text(value: str) -> str:
    lowered = normalize_whitespace(value).casefold()
    cleaned = re.sub(r"[^a-z0-9]+", "-", lowered)
    return cleaned.strip("-")


def stable_key(*parts: str) -> str:
    cleaned = [slug_text(part) for part in parts if normalize_whitespace(part)]
    joined = "|".join(cleaned)
    if not joined:
        return ""
    digest = hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]
    preview = "-".join(part for part in cleaned[:3] if part)[:80].strip("-")
    return f"{preview}-{digest}" if preview else digest


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    ensure_directory(path.parent)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, object]) -> None:
    ensure_directory(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def choose_display_name(values: Iterable[str]) -> str:
    cleaned = [normalize_whitespace(value) for value in values if normalize_whitespace(value)]
    if not cleaned:
        return ""
    counts: dict[str, int] = defaultdict(int)
    for value in cleaned:
        counts[value] += 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


PROTECTED_COMPOSITE_INSTITUTION_PATTERN = re.compile(
    r"\b("
    r"Science and Technology|"
    r"Posts and Telecommunications|"
    r"Economics and Technology|"
    r"Research and Technology|"
    r"Information and Communications Technology|"
    r"Polytechnic Institute and State University|"
    r"Academy of Mathematics and System Science|"
    r"Academy of Mathematics and Systems Science|"
    r"Beijing Institute of Mathematical Sciences and Application|"
    r"Beijing Institute of Mathematical Sciences and Applications|"
    r"Computer Science and Artificial Intelligence|"
    r"Security and Privacy|"
    r"Technology and Economics|"
    r"Agriculture and Technology|"
    r"Computer Science and Control|"
    r"Network Sciences and Cyberspace|"
    r"Physical and Mathematical Sciences|"
    r"National and Kapodistrian University|"
    r"Budapest University of Technology and Economics|"
    r"Institute of Science and Technology Austria|"
    r"King Abdulaziz City for Science and Technology|"
    r"William & Mary|"
    r"Centrum Wiskunde & Informatica"
    r")\b",
    re.IGNORECASE,
)


def split_institutions(value: str, known_names: set[str] | None = None) -> list[str]:
    text = normalize_whitespace(value)
    if not text:
        return []
    if PROTECTED_COMPOSITE_INSTITUTION_PATTERN.search(text):
        return [text]

    parts: list[str] = [text]
    if ", and " in text:
        parts = [part.strip(" ,") for part in re.split(r",\s+and\s+", text) if part.strip(" ,")]
    elif ", " in text and known_names is not None:
        comma_parts = [part.strip(" ,") for part in text.split(",") if part.strip(" ,")]
        if len(comma_parts) > 1 and all(part.casefold() in known_names for part in comma_parts):
            parts = comma_parts
    elif ";" in text:
        parts = [part.strip() for part in text.split(";") if part.strip()]
    elif "/" in text:
        parts = [part.strip() for part in text.split("/") if part.strip()]
    elif " & " in text:
        parts = [part.strip() for part in text.split(" & ") if part.strip()]
    elif " and " in text:
        parts = [part.strip() for part in text.split(" and ") if part.strip()]

    cleaned = [normalize_whitespace(part) for part in parts if normalize_whitespace(part)]
    if len(cleaned) <= 1:
        return [text]
    if known_names is not None and not all(part.casefold() in known_names for part in cleaned):
        return [text]
    return cleaned


COUNTRY_RULES: list[tuple[str, str]] = [
    (r"\b(united states|usa|u\.s\.a\.|us)\b", "United States"),
    (r"\bchina\b", "China"),
    (r"\bjapan\b", "Japan"),
    (r"\bgermany\b|\bdeutschland\b", "Germany"),
    (r"\buk\b|\bunited kingdom\b|\bengland\b", "United Kingdom"),
    (r"\bfrance\b", "France"),
    (r"\bcanada\b", "Canada"),
    (r"\bsingapore\b", "Singapore"),
    (r"\baustralia\b", "Australia"),
    (r"\bnetherlands\b|\bnl\b", "Netherlands"),
    (r"\bdenmark\b|\bdk\b", "Denmark"),
    (r"\bswitzerland\b", "Switzerland"),
    (r"\bisrael\b", "Israel"),
    (r"\bspain\b", "Spain"),
    (r"\bitaly\b", "Italy"),
    (r"\bkorea\b", "South Korea"),
    (r"\bindia\b", "India"),
]


def infer_country(inst: str) -> str:
    lowered = normalize_whitespace(inst).casefold()
    for pattern, country in COUNTRY_RULES:
        if re.search(pattern, lowered):
            return country
    return "Unknown"


def normalize_author_key(name: str) -> str:
    return stable_key(name)


def normalize_author_display_name(name: str) -> str:
    text = normalize_whitespace(name)
    if not text:
        return ""
    return normalize_whitespace(re.sub(r"\s0+\d+$", "", text))


def normalize_institution_key(inst: str) -> str:
    return stable_key(inst)


def normalize_paper_key(conference: str, year: str, title: str, paper_id: str) -> str:
    if normalize_whitespace(paper_id):
        return stable_key(conference, year, paper_id)
    return stable_key(conference, year, title)
