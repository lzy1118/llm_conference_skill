#!/usr/bin/env python3
"""
将已拆分的作者机构表进一步归并为“主体机构”。

输入默认：
  data/crypt_raw_机构拆分.csv

输出默认：
  data/crypt_raw_机构主体.csv

规则：
- 优先使用已剥离城市/省份/国家后的 `institution`
- 若 `institution` 为空，则回溯 `affiliation_raw`
- 继续将学院/实验室/系/中心等附属层级拆出到 `sub_institution`
- `stat_institution` 只保留用于统计的主体机构实体
- 不修改原文件
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_INPUT = PROJECT_ROOT / "data" / "crypt_raw_机构拆分.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "crypt_raw_机构主体.csv"


BODY_PATTERNS = [
    r"University of [^,]+",
    r"[^,]+ University(?: [^,]+)?",
    r"Universit[eéäà][^,]*",
    r"[^,]*Universit[aä][^,]*",
    r"Chinese Academy of Sciences",
    r"Polish Academy of Sciences",
    r"Academia Sinica",
    r"Institute for [^,]+",
    r"National Institute of [^,]+",
    r"Institute of Science Tokyo",
    r"Georgia Institute of Technology",
    r"Technology Innovation Institute",
    r"Indian Institute of Technology[^,]*",
    r"[^,]*Institute of Technology[^,]*",
    r"[^,]*Polytechnic[^,]*",
    r"CNRS",
    r"Inria",
    r"INRIA",
    r"CWI",
    r"CISPA[^,]*",
    r"COSIC",
    r"EPFL",
    r"ETH Zurich",
    r"MIT",
    r"KAIST",
    r"UCLouvain",
    r"JST",
    r"NTT(?: [^,]+)?",
    r"IBM(?: [^,]+)?",
    r"Google(?: [^,]+)?",
    r"Microsoft(?: [^,]+)?",
    r"Huawei(?: [^,]+)?",
    r"Orange Labs",
    r"SAP(?: [^,]+)?",
    r"Zama(?: [^,]+)?",
    r"SandboxAQ",
    r"CSIRO Data61",
    r"Data61",
    r"IMDEA Software Institute",
    r"MongoDB",
    r"J\.P\. Morgan[^,]*",
    r"PQShield",
    r"Thales",
    r"ZkSecurity",
    r"Arcium",
    r"Cryptoplexity Darmstadt",
    r"Ruhr University Bochum",
    r"Nanyang Technological University",
    r"KU Leuven",
    r"TU Darmstadt",
    r"University of California San Diego",
    r"University of California, San Diego",
    r"University of California",
    r"University of Edinburgh",
    r"Aalto University",
    r"National University of Singapore",
    r"University of Wollongong",
    r"University of Texas at Austin",
    r"Eindhoven University of Technology",
    r"University of the Bundeswehr Munich",
    r"Tohoku University",
    r"IT University of Copenhagen",
    r"Institut universitaire de France \(IUF\)",
]

SUB_PATTERNS = [
    r"department",
    r"dept\.?",
    r"school",
    r"faculty",
    r"college",
    r"division",
    r"laborator(?:y|ies)",
    r"lab(?:s)?",
    r"key laboratory",
    r"state key laboratory",
    r"national laboratory",
    r"center",
    r"centre",
    r"research center",
    r"research centre",
    r"group",
    r"chair",
    r"team",
    r"institute for",
    r"institute of (?:computer|information|network|cyber|mathematical|mathematics|software|cryptology|cryptography|engineering|advanced|physical|science|sciences)",
]

BODY_RE = re.compile(r"^(?:" + "|".join(BODY_PATTERNS) + r")$", re.IGNORECASE)
BODY_SEARCH_RE = re.compile(r"(?:" + "|".join(BODY_PATTERNS) + r")", re.IGNORECASE)
SUB_RE = re.compile(r"\b(?:" + "|".join(SUB_PATTERNS) + r")\b", re.IGNORECASE)
LEGAL_SUFFIX_RE = re.compile(
    r"^(?:co\.?|ltd\.?|limited|inc\.?|corp\.?|corporation|llc|gmbh|sarl|sas|bv|plc)$",
    re.IGNORECASE,
)

MAIN_PRIORITY = [
    re.compile(r"University|Universit[eéäà]", re.IGNORECASE),
    re.compile(r"College|School|Academy|Polytechnic|Institute of Science Tokyo|National Institute", re.IGNORECASE),
    re.compile(r"EPFL|ETH Zurich|KU Leuven|UCLouvain|Aalto University|Nanyang Technological University|National University of Singapore|University of Wollongong|University of Texas at Austin|Eindhoven University of Technology|University of the Bundeswehr Munich|Tohoku University|IT University of Copenhagen|University of California|University of Edinburgh|Ruhr University Bochum|Georgia Institute of Technology", re.IGNORECASE),
    re.compile(r"CNRS|INRIA|Inria|CWI|CISPA|COSIC|JST|NTT|IBM|Google|Microsoft|Huawei|Orange Labs|SAP|Zama|SandboxAQ|CSIRO|Data61|IMDEA Software Institute|MongoDB|PQShield|Thales|ZkSecurity|Arcium|Cryptoplexity Darmstadt|Technology Innovation Institute|J\.P\. Morgan|Institut universitaire de France", re.IGNORECASE),
    re.compile(r"State Key Laboratory|Key Laboratory|Laboratoire|Laboratory|Lab|Center|Centre", re.IGNORECASE),
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
    "stat_institution",
    "sub_institution",
    "city",
    "province",
    "country",
    "clean_method",
]

COUNTRY_BY_INSTITUTION = {
    "CNRS": "France",
    "Inria": "France",
    "Microsoft Research": "USA",
    "Nanyang Technological University": "Singapore",
    "Technische Universität Darmstadt": "Germany",
    "University of Birmingham": "UK",
    "University of California": "USA",
    "University of Chinese Academy of Sciences": "China",
    "University of Luxembourg": "Luxembourg",
    "University of Science and Technology of China": "China",
    "Zhejiang University": "China",
    "Tsinghua University": "China",
    "PSL University": "France",
    "Univ. Rennes": "France",
    "Chalmers University of Technology": "Sweden",
    "ZkSecurity": "Germany",
    "Luxembourg University": "Luxembourg",
}

CANONICAL_INSTITUTIONS = {
    "AWS-Wickr": "AWS Wickr",
    "Centrum Wiskunde and Informatica": "Centrum Wiskunde & Informatica",
    "Chinese University of Hong Kong": "The Chinese University of Hong Kong",
    "CISPA -Helmholtz Center for Information Security": "CISPA Helmholtz Center for Information Security",
    "CISPA Helmoltz Center for Information Security": "CISPA Helmholtz Center for Information Security",
    "CISPA Helmholtz Center": "CISPA Helmholtz Center for Information Security",
    "Helmholtz Center for Information Security (CISPA)": "CISPA Helmholtz Center for Information Security",
    "Centrum Wiskunde and Informatica (CWI)": "CWI",
    "Centrum Wiskunde & Informatica": "CWI",
    "Guangdong Key Lab oratory of Information Security": "Guangdong Key Laboratory of Information Security",
    "Associate of National Institute of Standards and Technology": "National Institute of Standards and Technology",
    "Ben-Gurion University": "Ben-Gurion University of the Negev",
    "ETH Zürich": "ETH Zurich",
    "ETH Zuric h": "ETH Zurich",
    "IBM Research -Zurich": "IBM Research Zurich",
    "IBM Research Zürich": "IBM Research Zurich",
    "IBM Zurich": "IBM Research Zurich",
    "IBM Research Europe -Zurich": "IBM Research Zurich",
    "IBM Research India": "IBM Research",
    "INRIA": "Inria",
    "INRIA Lyon": "Inria Lyon",
    "Institut universitaire de France (IUF)": "Institut Universitaire de France",
    "J.P. Morgan AI Research and J.P. Morgan AlgoCRYPT CoE": "J.P. Morgan AI Research & J.P. Morgan AlgoCRYPT CoE",
    "J.P. Morgan AI Research & J.P. Morgan AlgoCRYPT CoE": "J.P. Morgan AI Research & AlgoCRYPT CoE",
    "J. P. Morgan AI Research and AlgoCRYPT CoE": "J.P. Morgan AI Research & AlgoCRYPT CoE",
    "KDDI Research, Inc": "KDDI Research",
    "Leiden University": "Universiteit Leiden",
    "Luxembourg University": "University of Luxembourg",
    "University of Luxemb ourg": "University of Luxembourg",
    "Max-Planck Institute for Security and Privacy": "Max Planck Institute for Security and Privacy",
    "National Institute of Advanced Industrial Science and Technology (AIST)": "National Institute of Advanced Industrial Science and Technology",
    "Norwegian University of Science and Technology (NTNU)": "Norwegian University of Science and Technology",
    "NTNU -Norwegian University of Science and Technology": "Norwegian University of Science and Technology",
    "NTT Researc h": "NTT Research",
    "NTT Research, Inc": "NTT Research",
    "Pengcheng Laboratory": "Peng Cheng Laboratory",
    "Ruhr Universität Bochum": "Ruhr University Bochum",
    "Ruhr-University Bochum": "Ruhr University Bochum",
    "Ruhr-Universität Bochum": "Ruhr Universität Bochum",
    "Shanghai Jiaotong University": "Shanghai Jiao Tong University",
    "Sorbonne Université": "Sorbonne University",
    "The State Key Laboratory of Cryptology": "State Key Laboratory of Cryptology",
    "The University of Edinburgh": "University of Edinburgh",
    "The University of Sydney": "University of Sydney",
    "Technical University of Darmstadt": "Technische Universität Darmstadt",
    "Tsingh ua University": "Tsinghua University",
    "The University of Toky o": "The University of Tokyo",
    "Universidad Politénica de Madrid": "Universidad Politécnica de Madrid",
    "Université de Limoges": "University of Limoges",
    "Univ ersity of California": "University of California",
    "University of Illinois Urbana-Champaign": "University of Illinois at Urbana-Champaign",
    "University of the Bundeswehr Munich": "Universität der Bundeswehr München",
    "Universidad Politecnica de Madrid": "Universidad Politécnica de Madrid",
    "Universite de Limoges": "Université de Limoges",
    "Univ Montpellier": "Université de Montpellier",
    "Univ. Rennes": "Université de Rennes",
    "University of Porto (FCUP)": "University of Porto",
    "SnT -University of Luxembourg": "University of Luxembourg",
    "Université Libre de Bruxelles": "Université libre de Bruxelles",
    "VISA Research": "Visa Research",
    "Zama Inc": "Zama",
    "Shangdong Institute of Blockchain": "Shandong Institute of Blockchain",
    "Shanghai Qizhi Institute": "Shanghai Qi Zhi Institute",
    "Technology Innov ation Institute": "Technology Innovation Institute",
    "Brown Unive rsity": "Brown University",
    "Crypto Lab Inc": "CryptoLab Inc",
    "École polytechnique fédérale de Lausanne": "École Polytechnique Fédérale de Lausanne",
}


def canonicalize_institution(value: str) -> str:
    current = clean_text(value)
    seen: set[str] = set()
    while current in CANONICAL_INSTITUTIONS and current not in seen:
        seen.add(current)
        current = clean_text(CANONICAL_INSTITUTIONS[current])
    return current


def clean_text(value: str | None) -> str:
    return " ".join((value or "").strip().split())


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


def body_score(part: str) -> int:
    part = clean_text(part)
    if LEGAL_SUFFIX_RE.fullmatch(part):
        return 0
    for idx, rx in enumerate(MAIN_PRIORITY):
        if rx.search(part):
            return 100 - idx * 10
    if BODY_RE.fullmatch(part):
        return 60
    if BODY_SEARCH_RE.search(part):
        return 50
    low = part.lower()
    if any(x in low for x in ["university", "université", "universität", "academy", "institute of technology", "polytechnic"]):
        return 80
    if any(x in low for x in ["microsoft", "google", "ibm", "huawei", "ntt", "jst", "cnrs", "inria", "epfl", "eth", "mit", "kaist", "cwi", "cispa", "uclouvain"]):
        return 70
    if looks_like_org(part):
        return 65
    if SUB_RE.search(part):
        return 10
    return 40


def looks_like_org(value: str) -> bool:
    return bool(
        re.search(
            r"\b(university|institute|institut|academy|agency|foundation|school|department|laborator(?:y|ies)|lab|center|centre|technology|technologies|systems|solutions|cnrs|inria|mit|eth|epfl|ku leuven|uclouvain|jst|ntt|google|microsoft|ibm|mongodb|zama|primev|qredo|thales|bitdefender|sandboxaq|data61|csiro)\b",
            value,
            re.IGNORECASE,
        )
    )


def normalize_candidate(raw: str, institution: str) -> tuple[str, str, str]:
    """Return (stat_institution, sub_institution, method)."""
    raw = clean_text(raw)
    institution = clean_text(institution)
    source = institution or raw
    parts = split_commas(source)
    if not parts:
        return "", "", "empty"

    # Use the last highest-scoring body-like part as the main institution.
    scores = [(idx, body_score(part)) for idx, part in enumerate(parts)]
    best_idx, best_score = max(scores, key=lambda x: (x[1], x[0]))
    main = parts[best_idx]
    sub_parts = parts[:best_idx] + parts[best_idx + 1 :]

    # Prefer obvious principal institutions over labs/centers if both appear.
    if len(parts) > 1:
        preferred_idx = None
        preferred_score = -1
        for idx, part in enumerate(parts):
            s = clean_text(part)
            if re.search(r"\b(university|universit[eéäà]|epfl|eth zurich|ku leuven|nanyang technological university|national university of singapore|university of wollongong|university of texas at austin|eindhoven university of technology|tohoku university|it university of copenhagen|university of california|university of edinburgh|ruhr university bochum|georgia institute of technology|mit|technische universität)\b", s, re.IGNORECASE):
                score = 300
            elif re.search(r"\b(academy|polytechnic)\b", s, re.IGNORECASE):
                score = 260
            elif re.search(r"\b(cnrs|inria|inria|cwi|cispa|cosic|jst|ntt|ibm|google|microsoft|huawei|orange labs|sap|zama|sandboxaq|csiro|data61|imdea software institute|mongodb|pqshield|thales|zksecurity|arcium|cryptoplexity darmstadt|technology innovation institute|j\.p\. morgan|institut universitaire de france)\b", s, re.IGNORECASE):
                score = 220
            elif re.search(r"\b(institute for|institute of|research institute|agency|foundation|technology|technologies|systems|solutions)\b", s, re.IGNORECASE):
                score = 180
            elif re.search(r"\b(state key laboratory|key laboratory|laboratoire|laboratory|lab|center|centre)\b", s, re.IGNORECASE):
                score = 120
            elif looks_like_org(s):
                score = 80
            elif re.search(r"\b(college|school|department)\b", s, re.IGNORECASE):
                score = 60
            else:
                score = 0
            if score > preferred_score:
                preferred_idx = idx
                preferred_score = score
        if preferred_idx is not None and preferred_idx != best_idx and preferred_score >= 120:
            best_idx = preferred_idx
            main = parts[best_idx]
            sub_parts = parts[:best_idx] + parts[best_idx + 1 :]
            best_score = preferred_score

    method = "body_keyword" if best_score >= 75 else "fallback"
    if re.fullmatch(r"CWI Amsterdam", main, re.IGNORECASE):
        sub_parts.append("Amsterdam")
        main = "CWI"
    main = canonicalize_institution(main)
    return main, clean_text(", ".join(sub_parts)), method


def process_row(row: dict[str, str]) -> dict[str, str]:
    inst = clean_text(row.get("institution"))
    raw = clean_text(row.get("affiliation_raw"))
    if not inst and (clean_text(row.get("city")) or clean_text(row.get("country"))):
        stat_institution, sub_institution, method = "", "", "empty"
    else:
        stat_institution, sub_institution, method = normalize_candidate(raw, inst)
    out = dict(row)
    out["stat_institution"] = stat_institution
    out["sub_institution"] = sub_institution
    out["clean_method"] = method
    if not clean_text(out.get("country")) and stat_institution in COUNTRY_BY_INSTITUTION:
        out["country"] = COUNTRY_BY_INSTITUTION[stat_institution]
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract body institution from split affiliation CSV.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Input CSV path.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output CSV path.")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    with input_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = [process_row(row) for row in reader]
        fieldnames = list(reader.fieldnames or []) + ["stat_institution", "sub_institution", "clean_method"]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {len(rows)} rows to {output_path}")


if __name__ == "__main__":
    main()
