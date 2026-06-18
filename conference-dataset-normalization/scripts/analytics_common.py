from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable


def normalize_whitespace(value: str) -> str:
    """压缩重复空白，保证下游键值稳定。"""
    return re.sub(r"\s+", " ", value).strip()


def slug_text(value: str) -> str:
    """将展示文本转为小写 slug 片段，用于 ID 和键值。"""
    lowered = normalize_whitespace(value).casefold()
    cleaned = re.sub(r"[^a-z0-9]+", "-", lowered)
    return cleaned.strip("-")


def stable_key(*parts: str) -> str:
    """生成带短哈希后缀、可读且稳定的键值。"""
    cleaned = [slug_text(part) for part in parts if normalize_whitespace(part)]
    joined = "|".join(cleaned)
    if not joined:
        return ""
    digest = hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]
    preview = "-".join(part for part in cleaned[:3] if part)[:80].strip("-")
    return f"{preview}-{digest}" if preview else digest


def ensure_directory(path: Path) -> None:
    """为归一化产物创建所需的父目录。"""
    path.mkdir(parents=True, exist_ok=True)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """将 CSV 文件读取为字典行列表。"""
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    """将字典行写入 CSV，并忽略多余字段。"""
    ensure_directory(path.parent)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, object]) -> None:
    """以稳定格式写出 JSON，用于报告和清单产物。"""
    ensure_directory(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def choose_display_name(values: Iterable[str]) -> str:
    """选择清洗后出现最频繁的标签作为首选展示名。"""
    cleaned = [normalize_whitespace(value) for value in values if normalize_whitespace(value)]
    if not cleaned:
        return ""
    counts: dict[str, int] = defaultdict(int)
    for value in cleaned:
        counts[value] += 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


TRAILING_COUNTRY_PAREN_PATTERN = re.compile(
    r"\s*\(("
    r"United States|United Kingdom|China|Japan|Germany|France|Canada|Singapore|Australia|"
    r"Netherlands|Denmark|Switzerland|Israel|Spain|Italy|South Korea|India|Austria|Belgium|"
    r"Brazil|Qatar|Sweden|Norway|Finland|Ireland|Pakistan|Saudi Arabia|United Arab Emirates|"
    r"Greece|Czech Republic|New Zealand|Portugal|Romania|Thailand|Estonia|Mexico|Cyprus|"
    r"Sri Lanka|Colombia|Mongolia|Russia|Ukraine|Poland|Turkey|Hungary|Malaysia|Egypt|"
    r"Luxembourg|Taiwan|Hong Kong"
    r")\)$",
    re.IGNORECASE,
)


def clean_institution_label(value: str) -> str:
    """去除机构展示名尾部的国家后缀。"""
    text = normalize_whitespace(value)
    if not text:
        return ""
    return normalize_whitespace(TRAILING_COUNTRY_PAREN_PATTERN.sub("", text))


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
    r"Computer Science and Engineering|"
    r"Computer Science and Information Technology|"
    r"Computer and Cyber Security|"
    r"School of Electrical Engineering and Computer Science|"
    r"Mathematics and Computer Science|"
    r"Applied Mathematics and Computer Science|"
    r"Electrical and Computer Engineering|"
    r"Information and Engineering|"
    r"Information Engineering, CAS|"
    r"Trustworthy Distributed Computing and Service|"
    r"High Performance Computing and Networking|"
    r"Security and Privacy|"
    r"Technology and Economics|"
    r"Agriculture and Technology|"
    r"Computer Science and Control|"
    r"Network Sciences and Cyberspace|"
    r"Physical and Mathematical Sciences|"
    r"National and Kapodistrian University|"
    r"Budapest University of Technology and Economics|"
    r"Institute of Science and Technology Austria|"
    r"Applied Sciences and Arts|"
    r"Electronics and Telecommunications Research Institute|"
    r"Electronics and Applied Mathematics|"
    r"Advanced Computing and Intelligence Engineering|"
    r"London School of Economics and Political Science|"
    r"King Abdulaziz City for Science and Technology|"
    r"William & Mary|"
    r"Centrum Wiskunde & Informatica"
    r")\b",
    re.IGNORECASE,
)

SPLIT_NORMALIZATION_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"^\s*School of Electrical Engineering\s*;\s*Computer Science,\s*Oregon State University,\s*Corvallis,\s*OR,\s*USA\s*$",
            re.IGNORECASE,
        ),
        "School of Electrical Engineering and Computer Science, Oregon State University, Corvallis, OR, USA",
    ),
    (
        re.compile(
            r"^\s*ICTEAM\s*/\s*ELEN\s*/\s*Crypto Group,\s*UCL,\s*Louvain-la-Neuve,\s*Belgium\s*$",
            re.IGNORECASE,
        ),
        "Crypto Group, ICTEAM Institute, UCLouvain, Louvain-la-Neuve, Belgium",
    ),
    (
        re.compile(
            r"^\s*National Research Council\s*;\s*Institute for High Performance Computing and Networking\s*$",
            re.IGNORECASE,
        ),
        "National Research Council, Institute for High Performance Computing and Networking",
    ),
    (
        re.compile(r"^\s*Brown,\s*UVa\s*$", re.IGNORECASE),
        "Brown University; University of Virginia",
    ),
    (
        re.compile(r"^\s*TAU,\s*Stellar Foundation\s*$", re.IGNORECASE),
        "TAU; Stellar Foundation",
    ),
    (
        re.compile(r"^\s*Technion,\s*Amazon(?:/AWS)?\s*$", re.IGNORECASE),
        "Technion; Amazon Web Services",
    ),
    (
        re.compile(
            r"^\s*College of Computer Science\s*;\s*Engineering,\s*Taibah University,\s*Medina,\s*Saudi Arabia\s*$",
            re.IGNORECASE,
        ),
        "College of Computer Science and Engineering, Taibah University, Medina, Saudi Arabia",
    ),
    (
        re.compile(
            r"^\s*Department of Applied Mathematics\s*;\s*Computer Science,\s*Technical University of Denmark\s*$",
            re.IGNORECASE,
        ),
        "Department of Applied Mathematics and Computer Science, Technical University of Denmark",
    ),
    (
        re.compile(
            r"^\s*School of Computing\s*;\s*Information Technology,\s*University of Wollongong\s*$",
            re.IGNORECASE,
        ),
        "School of Computing and Information Technology, University of Wollongong",
    ),
    (
        re.compile(
            r"^\s*Paul G\. Allen School of Computer Science\s*;\s*Engineering,\s*University of Washington\s*$",
            re.IGNORECASE,
        ),
        "Paul G. Allen School of Computer Science and Engineering, University of Washington",
    ),
    (
        re.compile(
            r"^\s*Institute of Information\s*;\s*Engineering,\s*CAS\s*$",
            re.IGNORECASE,
        ),
        "Institute of Information Engineering, CAS",
    ),
    (
        re.compile(
            r"^\s*Key Laboratory of Trustworthy Distributed Computing\s*;\s*Service\s*\(BUPT\),\s*Ministry of Education\s*$",
            re.IGNORECASE,
        ),
        "Key Laboratory of Trustworthy Distributed Computing and Service (BUPT), Ministry of Education",
    ),
    (
        re.compile(
            r"^\s*BULL SAS,\s*Universit[ée]\s+Grenoble Alpes\s*$",
            re.IGNORECASE,
        ),
        "BULL SAS; Université Grenoble Alpes",
    ),
    (
        re.compile(
            r"^\s*IBM Research Zurich,\s*TU Munich\s*$",
            re.IGNORECASE,
        ),
        "IBM Research Europe - Zurich; Technical University Munich",
    ),
    (
        re.compile(
            r"\bIBM Research Zurich,\s*TU Munich\b",
            re.IGNORECASE,
        ),
        "IBM Research Europe - Zurich; Technical University Munich",
    ),
    (
        re.compile(
            r"^\s*Max Planck Institute for Security and Privacy and IMDEA Software Institute\s*$",
            re.IGNORECASE,
        ),
        "Max Planck Institute for Security and Privacy; IMDEA Software Institute",
    ),
    (
        re.compile(
            r"\bMax Planck Institute for Security and Privacy and IMDEA Software Institute\b",
            re.IGNORECASE,
        ),
        "Max Planck Institute for Security and Privacy; IMDEA Software Institute",
    ),
    (
        re.compile(
            r"^\s*Shanghai Qi Zhi Institute,\s*PADO Labs\s*$",
            re.IGNORECASE,
        ),
        "Shanghai Qi Zhi Institute; PADO Labs",
    ),
    (
        re.compile(
            r"\bShanghai Qi Zhi Institute,\s*PADO Labs\b",
            re.IGNORECASE,
        ),
        "Shanghai Qi Zhi Institute; PADO Labs",
    ),
    (
        re.compile(
            r"^\s*LIX,\s*Nomadic Labs\s*$",
            re.IGNORECASE,
        ),
        "LIX; Nomadic Labs",
    ),
    (
        re.compile(
            r"\bLIX,\s*Nomadic Labs\b",
            re.IGNORECASE,
        ),
        "LIX; Nomadic Labs",
    ),
    (
        re.compile(
            r"^\s*Univ\.\s*Bordeaux,\s*INRIA\s*$",
            re.IGNORECASE,
        ),
        "University of Bordeaux; Inria",
    ),
    (
        re.compile(
            r"\bUniv\.\s*Bordeaux,\s*INRIA\b",
            re.IGNORECASE,
        ),
        "University of Bordeaux; Inria",
    ),
    (
        re.compile(
            r"^\s*Rennes Univ,\s*Inria\s*$",
            re.IGNORECASE,
        ),
        "Rennes University; Inria",
    ),
    (
        re.compile(
            r"\bRennes Univ,\s*Inria\b",
            re.IGNORECASE,
        ),
        "Rennes University; Inria",
    ),
    (
        re.compile(
            r"^\s*UVSQ,\s*University Paris-Saclay\s*$",
            re.IGNORECASE,
        ),
        "Université Paris-Saclay",
    ),
    (
        re.compile(
            r"Departments of Computer Science\s*;\s*Mathematics,\s*Queens College,\s*City University of New York,\s*U\.S\.\}\s*;\s*\{Department of Computer Science\s*;\s*Engineering,\s*Tandon School of Engineering,\s*New York University,\s*U\.S\.",
            re.IGNORECASE,
        ),
        "Queens College, CUNY; New York University",
    ),
    (
        re.compile(
            r"Institute of Cybersecurity and Cryptology,\s*School of Computing and Information Technology,\s*University of Wollongong\.?",
            re.IGNORECASE,
        ),
        "University of Wollongong",
    ),
    (
        re.compile(
            r"Institute of Cybersecurity\s*;\s*Cryptology,\s*School of Computing\s*;\s*Information Technology,\s*University of Wollongong\.?",
            re.IGNORECASE,
        ),
        "University of Wollongong",
    ),
    (
        re.compile(
            r"University of Applied Sciences,\s*Emden\s*;\s*Leer,\s*Germany",
            re.IGNORECASE,
        ),
        "University of Applied Sciences Emden/Leer, Germany",
    ),
    (
        re.compile(
            r"\bUniv\.\s*Rennes\s*,\s*Inria\s*,\s*CNRS\s*,\s*IRISA\b",
            re.IGNORECASE,
        ),
        "University of Rennes; Inria; IRISA",
    ),
    (
        re.compile(
            r"^\s*University Rennes\s*;\s*NTT Research\s*;\s*Development\s*$",
            re.IGNORECASE,
        ),
        "Université de Rennes; NTT Research",
    ),
    (
        re.compile(
            r"\bELEN\s*;\s*Crypto Group,\s*Belgium\b",
            re.IGNORECASE,
        ),
        "UCLouvain",
    ),
    (
        re.compile(
            r"\bCryptography Research Centre,\s*Technology Innovation Institute\b",
            re.IGNORECASE,
        ),
        "Technology Innovation Institute",
    ),
    (
        re.compile(
            r"\bImperial College London,\s*UCL Centre for Blockchain Technologies\b",
            re.IGNORECASE,
        ),
        "Imperial College London; UCL Centre for Blockchain Technologies",
    ),
    (
        re.compile(
            r"\bInstitute for Network Science and Cyberspace\s*&\s*BNRist,\s*Tsinghua University\b",
            re.IGNORECASE,
        ),
        "Institute for Network Science and Cyberspace, Tsinghua University; BNRist, Tsinghua University",
    ),
    (
        re.compile(
            r"\b((?:Department|School) of Computer Science)\s*;\s*Engineering\b",
            re.IGNORECASE,
        ),
        r"\1 and Engineering",
    ),
    (
        re.compile(
            r"\bInstitute of Information\s*;\s*Communication Technologies,\s*Electronics\s*;\s*Applied Mathematics\b",
            re.IGNORECASE,
        ),
        "Institute of Information, Communication Technologies, Electronics and Applied Mathematics",
    ),
    (
        re.compile(
            r"\bDept\.\s+of Computer Science\s*;\s*Engineering\b",
            re.IGNORECASE,
        ),
        "Dept. of Computer Science and Engineering",
    ),
    (
        re.compile(
            r"\bDepartment of Computer Science\s*;\s*Engineering\b",
            re.IGNORECASE,
        ),
        "Department of Computer Science and Engineering",
    ),
    (
        re.compile(
            r"\bElectrical\s*;\s*Computer Engineering\b",
            re.IGNORECASE,
        ),
        "Electrical and Computer Engineering",
    ),
    (
        re.compile(
            r"\bLaboratory for Advanced Computing\s*;\s*Intelligence Engineering\b",
            re.IGNORECASE,
        ),
        "Laboratory for Advanced Computing and Intelligence Engineering",
    ),
    (
        re.compile(
            r"\bImperial College London\s*&amp\s*;?",
            re.IGNORECASE,
        ),
        "Imperial College London &",
    ),
    (
        re.compile(
            r"\b(ETH Zurich|Georgia Institute of Technology|Paderborn University|Purdue University|Tokyo Institute of Technology)\s*&amp\s*$",
            re.IGNORECASE,
        ),
        r"\1",
    ),
]

PROTECTED_TOKEN_TEMPLATE = "__INST_PROTECTED_{index}__"
DROP_IF_SUBSTRING_FRAGMENT_LABELS = {
    "Software",
}


def _normalize_split_text(value: str) -> str:
    """在机构字符串拆分前执行底层清洗规则。"""
    text = value
    for pattern, replacement in SPLIT_NORMALIZATION_RULES:
        text = pattern.sub(replacement, text)
    return text


def _protect_composite_phrases(value: str) -> tuple[str, dict[str, str]]:
    """在拆分过程中临时保护不应被拆开的多词机构短语。"""
    replacements: dict[str, str] = {}

    def replacer(match: re.Match[str]) -> str:
        token = PROTECTED_TOKEN_TEMPLATE.format(index=len(replacements))
        protected = re.sub(r"\s*&\s*", " __AMP__ ", match.group(0))
        protected = re.sub(r"\s+and\s+", " __AND__ ", protected, flags=re.IGNORECASE)
        replacements[token] = protected
        return token

    return PROTECTED_COMPOSITE_INSTITUTION_PATTERN.sub(replacer, value), replacements


def _restore_composite_phrases(value: str, replacements: dict[str, str]) -> str:
    """在拆分完成后恢复被保护的机构短语。"""
    restored = value
    for token, protected in replacements.items():
        restored = restored.replace(token, protected)
    restored = restored.replace("__AMP__", "&").replace("__AND__", "and")
    return normalize_whitespace(restored)


def split_institutions(value: str, known_names: set[str] | None = None) -> list[str]:
    """将混合机构字符串拆分为干净的机构级条目。"""
    text = clean_institution_label(value)
    if not text:
        return []
    text = _normalize_split_text(text)
    protected_text, replacements = _protect_composite_phrases(text)

    parts: list[str] = [protected_text]
    split_mode = "none"
    if ";" in protected_text:
        parts = [part.strip() for part in protected_text.split(";") if part.strip()]
        split_mode = "semicolon"
    elif ", and " in protected_text:
        parts = [part.strip(" ,") for part in re.split(r",\s+and\s+", protected_text) if part.strip(" ,")]
        split_mode = "comma_and"
    elif " & " in protected_text:
        parts = [part.strip() for part in protected_text.split(" & ") if part.strip()]
        split_mode = "ampersand"
    elif " and " in protected_text:
        parts = [part.strip() for part in re.split(r"\s+and\s+", protected_text) if part.strip()]
        split_mode = "and"
    elif "/" in protected_text:
        parts = [part.strip() for part in protected_text.split("/") if part.strip()]
        split_mode = "slash"
    elif ", " in protected_text and known_names is not None:
        comma_parts = [part.strip(" ,") for part in protected_text.split(",") if part.strip(" ,")]
        if len(comma_parts) > 1 and all(part.casefold() in known_names for part in comma_parts):
            parts = comma_parts
            split_mode = "comma_known"

    cleaned = [
        clean_institution_label(_restore_composite_phrases(part, replacements))
        for part in parts
        if normalize_whitespace(part)
    ]
    if len(cleaned) > 1:
        cleaned = [
            part
            for part in cleaned
            if not (
                part in DROP_IF_SUBSTRING_FRAGMENT_LABELS
                and any(part.casefold() in other.casefold() and len(other) > len(part) for other in cleaned if other != part)
            )
        ]
    if len(cleaned) <= 1:
        return [text]
    if split_mode == "comma_known" and known_names is not None and not all(part.casefold() in known_names for part in cleaned):
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
    (r"\bnetherlands\b|\bnetherland\b|\bnl\b", "Netherlands"),
    (r"\bdenmark\b|\bdk\b", "Denmark"),
    (r"\bswitzerland\b", "Switzerland"),
    (r"\bisrael\b", "Israel"),
    (r"\bspain\b", "Spain"),
    (r"\bitaly\b", "Italy"),
    (r"\bkorea\b", "South Korea"),
    (r"\bindia\b", "India"),
    (r"\baustria\b", "Austria"),
    (r"\bbelgium\b", "Belgium"),
    (r"\bbrazil\b", "Brazil"),
    (r"\bcolombia\b", "Colombia"),
    (r"\bczech republic\b|\bczechia\b", "Czech Republic"),
    (r"\bfinland\b", "Finland"),
    (r"\bgreece\b", "Greece"),
    (r"\bhungary\b", "Hungary"),
    (r"\biran\b", "Iran"),
    (r"\bireland\b", "Ireland"),
    (r"\bluxembourg\b", "Luxembourg"),
    (r"\bnew zealand\b", "New Zealand"),
    (r"\bnorway\b", "Norway"),
    (r"\bpakistan\b", "Pakistan"),
    (r"\bpoland\b", "Poland"),
    (r"\bportugal\b", "Portugal"),
    (r"\bqatar\b", "Qatar"),
    (r"\bromania\b", "Romania"),
    (r"\bsaudi arabia\b", "Saudi Arabia"),
    (r"\bsweden\b", "Sweden"),
    (r"\btaiwan\b", "Taiwan"),
    (r"\bthailand\b", "Thailand"),
    (r"\bturkey\b", "Turkey"),
    (r"\buae\b|\bunited arab emirates\b|\babu dhabi\b", "United Arab Emirates"),
    (r"\bukraine\b", "Ukraine"),
]


def infer_country(inst: str) -> str:
    """在可能时根据规范化机构字符串推断国家标签。"""
    lowered = normalize_whitespace(inst).casefold()
    for pattern, country in COUNTRY_RULES:
        if re.search(pattern, lowered):
            return country
    return "Unknown"


def normalize_author_key(name: str) -> str:
    """将作者姓名规范化为稳定的匹配键。"""
    return stable_key(name)


def normalize_author_display_name(name: str) -> str:
    """清洗作者展示名，同时尽量避免过度改写原文。"""
    text = normalize_whitespace(name)
    if not text:
        return ""
    return normalize_whitespace(re.sub(r"\s0+\d+$", "", text))


def normalize_institution_key(inst: str) -> str:
    """将机构文本规范化为适合连接与去重的键值。"""
    return stable_key(inst)


def normalize_paper_key(conference: str, year: str, title: str, paper_id: str) -> str:
    """根据会议信息与标题构造稳定的论文级键值。"""
    if normalize_whitespace(paper_id):
        return stable_key(conference, year, paper_id)
    return stable_key(conference, year, title)
