#!/usr/bin/env python3
"""
为已提取的作者机构表增加机构类型列。

输入默认：
  data/crypt_raw_机构主体.csv

输出默认：
  data/crypt_raw_机构主体_类型.csv

规则：
- 不修改原 CSV
- 合并 `stat_institution` / `institution` / `affiliation_raw` 的判断结果，只保留一列
- 有明确类型时优先保留更具体的那个，无法明确时落到 `organization`
- 仅输出五类：
  university / company / research institute / organization / government
- 采用保守分类，无法明确时落到 `organization`
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_INPUT = PROJECT_ROOT / "data" / "crypt_raw_机构主体.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "crypt_raw_机构主体_类型.csv"


UNIVERSITY_PATTERNS = [
    r"\buniversity\b",
    r"\buniversit[eéèàäïöü]{0,2}\b",
    r"\buniversit[aä]t\b",
    r"\buniversidad\b",
    r"\buniversidade\b",
    r"\buniversità\b",
    r"\bpolytechnic\b",
    r"\btechnological university\b",
    r"\btechnology university\b",
    r"\binstitute of technology\b",
    r"\btechnische universität\b",
    r"\bindian institute of technology\b",
    r"\bcollege of\b",
    r"\bschool of\b",
    r"\buclouvain\b",
    r"\beth z[uü]rich\b",
    r"\bepfl\b",
    r"\bku leuven\b",
    r"\bécole polytechnique fédérale de lausanne\b",
    r"\bruh[r-]universit[aä]t bochum\b",
    r"\bruh[r-]university bochum\b",
    r"\buniversity of edinburgh\b",
    r"\buniversity of sydney\b",
    r"\btechnion\b",
]

COMPANY_PATTERNS = [
    r"\binc\.?\b",
    r"\bltd\.?\b",
    r"\blimited\b",
    r"\bllc\b",
    r"\bcorp\.?\b",
    r"\bcorporation\b",
    r"\bgmbh\b",
    r"\bsarl\b",
    r"\bsas\b",
    r"\bbv\b",
    r"\bplc\b",
    r"\bag\b",
    r"\bab\b",
    r"\bco\.?\s*,?\s*ltd\.?\b",
    r"\bcompany\b",
    r"\btechnologies\b",
    r"\btechnology\b",
    r"\bsystems\b",
    r"\bsolutions\b",
    r"\blabs?\b",
    r"\bGoogle\b",
    r"\bMicrosoft\b",
    r"\bIBM\b",
    r"\bHuawei\b",
    r"\bAmazon\b",
    r"\bApple\b",
    r"\bMeta\b",
    r"\bIntel\b",
    r"\bQualcomm\b",
    r"\bOracle\b",
    r"\bSamsung\b",
    r"\bNVIDIA\b",
    r"\bThales\b",
    r"\bBitdefender\b",
    r"\bMongoDB\b",
    r"\bZama\b",
    r"\bSandboxAQ\b",
    r"\bPQShield\b",
    r"\bQredo\b",
    r"\bPrimev\b",
    r"\bArcium\b",
    r"\bNTT\b",
    r"\bOrange\b",
    r"\bSAP\b",
    r"\bJ\.P\. Morgan\b",
    r"\bCryptoplexity Darmstadt\b",
]

RESEARCH_PATTERNS = [
    r"\bresearch institute\b",
    r"\binstitute for\b",
    r"\binstitute of\b",
    r"\binstitut\b",
    r"\binstitute\b",
    r"\blaboratoire\b",
    r"\blaboratory\b",
    r"\blab\b",
    r"\bresearch center\b",
    r"\bresearch centre\b",
    r"\bcenter for\b",
    r"\bcentre for\b",
    r"\bcenter\b",
    r"\bcentre\b",
    r"\bcnrs\b",
    r"\binria\b",
    r"\bcwi\b",
    r"\bcispa\b",
    r"\bcosic\b",
    r"\bimec\b",
    r"\bimdea\b",
    r"\bdata61\b",
    r"\bcsiro\b",
    r"\bacademy of sciences\b",
    r"\bacademia sinica\b",
    r"\bnational laboratory\b",
    r"\baist\b",
    r"\bnict\b",
    r"\bacademy of mathematics and systems science\b",
    r"\bbeijing academy of blockchain and edge computing\b",
    r"\bshanghai qi zhi institute\b",
]

GOVERNMENT_PATTERNS = [
    r"\bministry\b",
    r"\bgovernment\b",
    r"\bgovt\.?\b",
    r"\bbureau\b",
    r"\bagency\b",
    r"\badministration\b",
    r"\boffice of\b",
    r"\bdepartment of defense\b",
    r"\bdepartment of defence\b",
    r"\bparliament\b",
    r"\bcourt\b",
    r"\bsecretariat\b",
    r"\bmunicipalit(y|ies)\b",
    r"\bcity hall\b",
    r"\bstate council\b",
    r"\bpublic service\b",
    r"\barmy\b",
    r"\bnavy\b",
    r"\bair force\b",
]

UNIVERSITY_RE = re.compile("|".join(UNIVERSITY_PATTERNS), re.IGNORECASE)
COMPANY_RE = re.compile("|".join(COMPANY_PATTERNS), re.IGNORECASE)
RESEARCH_RE = re.compile("|".join(RESEARCH_PATTERNS), re.IGNORECASE)
GOVERNMENT_RE = re.compile("|".join(GOVERNMENT_PATTERNS), re.IGNORECASE)


def clean_text(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def classify_institution_type(row: dict[str, str]) -> str:
    stat_institution = clean_text(row.get("stat_institution"))
    institution = clean_text(row.get("institution"))
    raw = clean_text(row.get("affiliation_raw"))

    def classify_text(text: str) -> str | None:
        if not text:
            return None
        if UNIVERSITY_RE.search(text):
            return "university"
        if RESEARCH_RE.search(text):
            return "research institute"
        if GOVERNMENT_RE.search(text):
            return "government"
        if COMPANY_RE.search(text):
            return "company"
        return None

    # Prefer the extracted body institution first; fall back to progressively noisier fields.
    for text in (stat_institution, institution, raw):
        label = classify_text(text)
        if label:
            return label

    return "organization"


def process_row(row: dict[str, str]) -> dict[str, str]:
    out = dict(row)
    out["institution_type"] = classify_institution_type(row)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify institution type from affiliation text.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Input CSV path.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output CSV path.")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    with input_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = [process_row(row) for row in reader]
        fieldnames = list(reader.fieldnames or [])
        if "institution_type" not in fieldnames:
            fieldnames.append("institution_type")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {len(rows)} rows to {output_path}")


if __name__ == "__main__":
    main()
