#!/usr/bin/env python3
"""
拆分作者机构 CSV：
- 按同一作者的多机构分隔符 ; / ； 拆成多行
- 从机构末尾保守抽取国家/地区；未识别则 country 留空，不猜
- 在识别到国家/地区后，从尾部剥离城市、省/州

默认：
  输入 data/asiacrypt_raw.csv
  输出 data/asiacrypt_raw_机构拆分.csv
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_INPUT = PROJECT_ROOT / "data" / "asiacrypt_raw.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "asiacrypt_raw_机构拆分.csv"


COUNTRY_ALIASES = {
    "australia": "Australia",
    "austria": "Austria",
    "belgium": "Belgium",
    "brazil": "Brazil",
    "canada": "Canada",
    "china": "China",
    "people's republic of china": "China",
    "pr china": "China",
    "colombia": "Colombia",
    "costa rica": "Costa Rica",
    "czech republic": "Czech Republic",
    "denmark": "Denmark",
    "england": "UK",
    "estonia": "Estonia",
    "finland": "Finland",
    "france": "France",
    "german": "Germany",
    "germany": "Germany",
    "greece": "Greece",
    "hong kong": "Hong Kong",
    "hungary": "Hungary",
    "india": "India",
    "iran": "Iran",
    "israel": "Israel",
    "italy": "Italy",
    "japan": "Japan",
    "korea": "South Korea",
    "republic of korea": "South Korea",
    "south korea": "South Korea",
    "luxembourg": "Luxembourg",
    "mexico": "Mexico",
    "netherlands": "Netherlands",
    "the netherlands": "Netherlands",
    "new zealand": "New Zealand",
    "norway": "Norway",
    "poland": "Poland",
    "portugal": "Portugal",
    "romania": "Romania",
    "saudi arabia": "Saudi Arabia",
    "singapore": "Singapore",
    "slovakia": "Slovakia",
    "spain": "Spain",
    "sweden": "Sweden",
    "switzerland": "Switzerland",
    "taiwan": "Taiwan",
    "uae": "United Arab Emirates",
    "united arab emirates": "United Arab Emirates",
    "uk": "UK",
    "united kingdom": "UK",
    "usa": "USA",
    "united states": "USA",
    "united states of america": "USA",
    "vietnam": "Vietnam",
}

US_STATE_CODES = {
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "FL",
    "GA",
    "HI",
    "IA",
    "ID",
    "IL",
    "IN",
    "KS",
    "KY",
    "LA",
    "MA",
    "MD",
    "ME",
    "MI",
    "MN",
    "MO",
    "MS",
    "MT",
    "NC",
    "ND",
    "NE",
    "NH",
    "NJ",
    "NM",
    "NV",
    "NY",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VA",
    "VT",
    "WA",
    "WI",
    "WV",
    "WY",
    "DC",
}

CHINA_PROVINCES = {
    "Anhui",
    "Beijing",
    "Fujian",
    "Guangdong",
    "Guizhou",
    "Hunan",
    "Jiangsu",
    "Shandong",
    "Shanghai",
    "Zhejiang",
}

CHINA_MUNICIPALITIES = {
    "Beijing",
    "Shanghai",
}

JAPAN_PREFECTURES = {
    "Saitama",
}

LEGAL_SUFFIX_RE = re.compile(
    r"^(?:co\.?|ltd\.?|limited|inc\.?|corp\.?|corporation|llc|gmbh|sarl|sas|bv|plc)$",
    re.IGNORECASE,
)

OCR_FIXES = {
    "U nited Arab Emirates": "United Arab Emirates",
    "U niversity": "University",
    "Universit y": "University",
    "Unive rsity": "University",
    "Univeristy": "University",
    "D efense": "Defense",
    "T echnology": "Technology",
    "S cience": "Science",
    "I nstitute": "Institute",
    "C ryptology": "Cryptology",
    "F aculty": "Faculty",
    "E ngineering": "Engineering",
    "M athematics": "Mathematics",
    "C omputing": "Computing",
    "C hina": "China",
    "Bloc kchain": "Blockchain",
    "Innov ation": "Innovation",
    "Researc h": "Research",
    "Luxemb ourg": "Luxembourg",
    "Tsingh ua": "Tsinghua",
    "Toky o": "Tokyo",
    "Zuric h": "Zurich",
    "Univ ersity": "University",
    "S tate": "State",
    "R esearch": "Research",
    "P ower": "Power",
    "S ydney": "Sydney",
    "Academ y": "Academy",
    "U rbana": "Urbana",
    "V erne": "Verne",
    "Z hejiang": "Zhejiang",
    "B erkeley": "Berkeley",
    "U SA": "USA",
    "Mon tréal": "Montréal",
    "German y": "Germany",
    "Luxem bourg": "Luxembourg",
}

NO_COMMA_ORG_CITY_PATTERNS = [
    (re.compile(r"^(Bitdefender)\s+(Bucharest)$"), ("institution", "city")),
    (re.compile(r"^(Cornell Tech)\s+(New York City)$"), ("institution", "city")),
    (re.compile(r"^(Google)\s+(Menlo Park)$"), ("institution", "city")),
    (re.compile(r"^(Data61)$"), ("institution", "")),
    (re.compile(r"^(Inria)(?:\s+(Rennes))?$"), ("institution", "city")),
    (re.compile(r"^(IT University of Copenhagen)$"), ("institution", "")),
    (re.compile(r"^(NTT Research)$"), ("institution", "")),
    (re.compile(r"^(MongoDB)$"), ("institution", "")),
    (re.compile(r"^(Primev)\s+(Manchester)$"), ("institution", "city")),
    (re.compile(r"^(Qredo)\s+(London)$"), ("institution", "city")),
    (re.compile(r"^(SandboxAQ)$"), ("institution", "")),
    (re.compile(r"^(Thales)\s+(Gennevilliers)$"), ("institution", "city")),
    (re.compile(r"^(Thales)\s+(Gennevilliers)\s+Gennevilliers$"), ("institution", "city")),
    (re.compile(r"^(University of California, Berkeley)$"), ("institution", "")),
    (re.compile(r"^(University of California)$"), ("institution", "")),
    (re.compile(r"^(Zama)\s+(Paris)$"), ("institution", "city")),
    (re.compile(r"^(University of Edinburgh)$"), ("institution", "")),
    (re.compile(r"^(Aalto University)$"), ("institution", "")),
    (re.compile(r"^(Nanyang Technological University)$"), ("institution", "")),
    (re.compile(r"^(National University of Singapore)$"), ("institution", "")),
    (re.compile(r"^(University of Wollongong)$"), ("institution", "")),
    (re.compile(r"^(University of Texas at Austin)$"), ("institution", "")),
    (re.compile(r"^(Eindhoven University of Technology)$"), ("institution", "")),
    (re.compile(r"^(Ruhr University Bochum)$"), ("institution", "")),
    (re.compile(r"^(CISPA Helmholtz Center for Information Security)$"), ("institution", "")),
    (re.compile(r"^(KU Leuven)$"), ("institution", "")),
    (re.compile(r"^(University of the Bundeswehr Munich)$"), ("institution", "")),
    (re.compile(r"^(University of California San Diego)$"), ("institution", "")),
    (re.compile(r"^(Tohoku University)$"), ("institution", "")),
    (re.compile(r"^(University of California, San Diego)$"), ("institution", "")),
    (re.compile(r"^(Institut universitaire de France \\(IUF\\))$"), ("institution", "")),
]

OUTPUT_FIELDS = [
    "year",
    "conference",
    "title",
    "author",
    "author_rank",
    "affiliation_rank",
    "affiliation_raw",
    "institution",
    "city",
    "province",
    "country",
]


def clean_text(value: str | None) -> str:
    value = " ".join((value or "").strip().split())
    for old, new in OCR_FIXES.items():
        value = value.replace(old, new)
    value = value.strip(" '\"")
    if value.endswith(")") and "(" not in value:
        value = value[:-1].rstrip()
    return value


def split_affiliations(value: str | None) -> list[str]:
    return [part for part in (clean_text(x) for x in re.split(r"[;；]", value or "")) if part]


def split_commas(value: str) -> list[str]:
    parts: list[str] = []
    for part in (clean_text(part) for part in value.split(",")):
        if not part:
            continue
        if parts and LEGAL_SUFFIX_RE.fullmatch(part):
            parts[-1] = clean_text(f"{parts[-1]}, {part}")
        else:
            parts.append(part)
    return parts


def normalize_country(value: str) -> str:
    token = clean_text(value).strip(" .;)'\"").lower()
    return COUNTRY_ALIASES.get(token, "")


def strip_postal_code(value: str) -> str:
    value = clean_text(value)
    value = re.sub(r"\b\d{3,}\b", "", value)
    return clean_text(value.strip(", "))


def split_no_comma_org_city(value: str) -> tuple[str, str] | None:
    value = clean_text(value)
    for pattern, _groups in NO_COMMA_ORG_CITY_PATTERNS:
        match = pattern.fullmatch(value)
        if match:
            if len(match.groups()) == 1:
                return match.group(1), ""
            return match.group(1), match.group(2) or ""
    return None


def looks_like_org(value: str) -> bool:
    return bool(
        re.search(
            r"\b(university|institute|institut|academy|academia|agency|foundation|school|department|laborator(?:y|ies)|lab|center|centre|research|technology|technologies|systems|solutions|co\.?|ltd\.?|inc\.?|corp\.?|cnrs|inria|mit|eth|epfl|ku leuven|uclouvain|jst|ntt|google|microsoft|ibm|mongodb|zama|primev|qredo|thales|bitdefender)\b",
            value,
            re.I,
        )
    )


def parse_affiliation(affiliation: str) -> dict[str, str]:
    affiliation = clean_text(affiliation)
    tokens = split_commas(affiliation)
    if not tokens:
        return {
            "affiliation_raw": affiliation,
            "institution": "",
            "city": "",
            "province": "",
            "country": "",
        }

    country = normalize_country(tokens[-1])
    if not country:
        # 保守处理：国家无法从末尾确认时，不继续猜城市/省份。
        return {
            "affiliation_raw": affiliation,
            "institution": affiliation,
            "city": "",
            "province": "",
            "country": "",
        }

    body = tokens[:-1]
    if not body:
        return {
            "affiliation_raw": affiliation,
            "institution": "",
            "city": "",
            "province": "",
            "country": country,
        }

    tail = strip_postal_code(body[-1])
    city = ""
    province = ""

    if len(body) >= 2 and (
        tail.upper() in US_STATE_CODES
        or re.fullmatch(r"[A-Z]{2,3}", tail)
        or (country in {"USA", "Australia", "Canada"} and re.search(r"\b[A-Z]{2,3}\b", tail))
    ):
        city_state = re.fullmatch(r"(.+?)\s+([A-Z]{2,3})", tail)
        if country in {"USA", "Australia", "Canada"} and city_state:
            province = city_state.group(2)
            city = clean_text(city_state.group(1))
            institution_tokens = body[:-1]
        else:
            province = tail
            city_candidate = strip_postal_code(body[-2])
            if re.search(r"\b(university|institute|institut|laborator(?:y|ies)|lab|school|department|cnrs|inria|mit|eth|epfl|ku leuven|ntt|google|microsoft|ibm|mongodb|zama|data61|csiro|thales|sandboxaq)\b", city_candidate, re.IGNORECASE):
                city = ""
                institution_tokens = body[:-1]
            else:
                city = city_candidate
                institution_tokens = body[:-2]
    else:
        if len(body) >= 2 and clean_text(body[-2]).lower() == clean_text(body[-1]).lower():
            city = tail
            institution_tokens = body[:-2]
        elif country == "China" and tail in CHINA_MUNICIPALITIES:
            city = tail
            institution_tokens = body[:-1]
        elif country == "China" and tail in CHINA_PROVINCES:
            province = tail
            if len(body) >= 2:
                city_candidate = strip_postal_code(body[-2])
                if looks_like_org(city_candidate):
                    city = ""
                    institution_tokens = body[:-1]
                else:
                    city = city_candidate
                    institution_tokens = body[:-2]
            else:
                city = ""
                institution_tokens = body[:-1]
        elif country == "China" and (words := tail.split()) and len(words) >= 2 and words[-1] in CHINA_PROVINCES:
            city = " ".join(words[:-1])
            province = words[-1]
            institution_tokens = body[:-1]
        elif country == "Japan" and tail in JAPAN_PREFECTURES:
            province = tail
            if len(body) >= 2:
                city_candidate = strip_postal_code(body[-2])
                if looks_like_org(city_candidate):
                    city = ""
                    institution_tokens = body[:-1]
                else:
                    city = city_candidate
                    institution_tokens = body[:-2]
            else:
                city = ""
                institution_tokens = body[:-1]
        else:
            if len(body) >= 2 and clean_text(body[-2]) == "University of St":
                tail_words = tail.split()
                if tail_words and tail_words[0] in {"Thomas", "Gallen"}:
                    institution = f"University of St. {tail_words[0]}"
                    city = clean_text(" ".join(tail_words[1:]) or f"St. {tail_words[0]}")
                    prefix = clean_text(", ".join(body[:-2]))
                    if prefix:
                        institution = clean_text(f"{prefix}, {institution}")
                    return {
                        "affiliation_raw": affiliation,
                        "institution": institution,
                        "city": city,
                        "province": province,
                        "country": country,
                    }
            split_tail = split_no_comma_org_city(tail)
            if split_tail:
                institution, city = split_tail
                prefix = clean_text(", ".join(body[:-1]))
                if prefix:
                    institution = clean_text(f"{prefix}, {institution}")
                return {
                    "affiliation_raw": affiliation,
                    "institution": institution,
                    "city": city,
                    "province": province,
                    "country": country,
                }
            if len(body) == 1 and (
                looks_like_org(tail)
                or re.search(r"\b(institut universitaire|sandboxaq)\b", tail, re.IGNORECASE)
            ):
                city = ""
                institution_tokens = body
            elif len(body) == 1 and looks_like_org(body[0]) and not looks_like_org(tail):
                institution_tokens = body
                city = tail
            else:
                city = tail
                institution_tokens = body[:-1]

    return {
        "affiliation_raw": affiliation,
        "institution": clean_text(", ".join(institution_tokens)),
        "city": city,
        "province": province,
        "country": country,
    }


def split_csv(input_path: Path, output_path: Path) -> int:
    output_rows = []
    with input_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            affiliations = split_affiliations(row.get("affiliations")) or [""]
            for index, affiliation in enumerate(affiliations):
                output_rows.append(
                    {
                        "year": row.get("year", ""),
                        "conference": row.get("conference", ""),
                        "title": row.get("title", ""),
                        "author": row.get("author", ""),
                        "author_rank": row.get("author_rank", ""),
                        "affiliation_rank": str(index),
                        **parse_affiliation(affiliation),
                    }
                )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(output_rows)
    return len(output_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Split author affiliations into normalized rows.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Input CSV path.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output CSV path.")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    row_count = split_csv(input_path, output_path)
    print(f"wrote {row_count} rows to {output_path}")


if __name__ == "__main__":
    main()
