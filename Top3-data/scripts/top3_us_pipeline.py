from __future__ import annotations

# Legacy compatibility script.
#
# This file preserves the historical Top3-data US-named entrypoint so old
# commands keep working. The current preferred entrypoints are:
# - `Top3-data/scripts/top3_pipeline.py` for a neutral local wrapper
# - `conference-paper-extraction/scripts/run_unified_pipeline.py` for the
#   canonical unified pipeline
#
# Keep this file stable unless compatibility behavior must change.

import argparse
import csv
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import Workbook


@dataclass(frozen=True)
class ConferenceConfig:
    key: str
    conference: str
    year: int
    url: str


@dataclass(frozen=True)
class AffiliationClassification:
    is_us: bool
    source: str
    confidence: float
    reason: str


EUROCRYPT_2026 = ConferenceConfig(
    key="eurocrypt_2026",
    conference="EUROCRYPT",
    year=2026,
    url="https://eurocrypt.iacr.org/2026/json/papers.json",
)

ASIACRYPT_2025 = ConferenceConfig(
    key="asiacrypt_2025",
    conference="ASIACRYPT",
    year=2025,
    url="https://asiacrypt.iacr.org/2025/json/papers.json",
)

CRYPTO_2025 = ConferenceConfig(
    key="crypto_2025",
    conference="CRYPTO",
    year=2025,
    url="https://crypto.iacr.org/2025/json/papers.json",
)

CONFERENCE_CONFIGS = {
    config.key: config
    for config in [ASIACRYPT_2025, CRYPTO_2025, EUROCRYPT_2026]
}

US_EXACT_ALIASES = {
    "mit",
    "nist",
    "sri",
    "uc san diego",
    "uc berkeley",
    "uc irvine",
    "uc davis",
    "uc santa barbara",
    "uc santa cruz",
    "uc los angeles",
    "ucla",
    "ut austin",
    "uiuc",
    "umd",
    "nyu",
    "yale",
    "duke",
    "cmu",
}

US_KEYWORD_PATTERNS = [
    r"\bmassachusetts institute of technology\b",
    r"\bcarnegie mellon university\b",
    r"\bstanford university\b",
    r"\bprinceton university\b",
    r"\bcornell university\b",
    r"\bcornell tech\b",
    r"\bbrown university\b",
    r"\bduke university\b",
    r"\byale university\b",
    r"\byale\b",
    r"\bcolumbia university\b",
    r"\bnew york university\b",
    r"\bnyu\b",
    r"\bboston university\b",
    r"\bjohns hopkins university\b",
    r"\bjhu\b",
    r"\buniversity of california\b",
    r"\buniversity of washington\b",
    r"\buniversity of wisconsin\b",
    r"\buw-madison\b",
    r"\buniversity of maryland\b",
    r"\bumd\b",
    r"\buniversity of pennsylvania\b",
    r"\buniversity of michigan\b",
    r"\buniversity of texas\b",
    r"\but austin\b",
    r"\buniversity of illinois\b",
    r"\buiuc\b",
    r"\burbana-champaign\b",
    r"\bgeorgia tech\b",
    r"\bgeorgia institute of technology\b",
    r"\bcity college of new york\b",
    r"\bcuny\b",
    r"\bnorth carolina state university\b",
    r"\bnortheastern university\b",
    r"\bpurdue university\b",
    r"\brice university\b",
    r"\bstony brook university\b",
    r"\btexas a&m university\b",
    r"\bunc chapel hill\b",
    r"\buniversity of connecticut\b",
    r"\bwashington state university\b",
    r"\bgoogle\b",
    r"\bmeta\b",
    r"\bmicrosoft\b",
    r"\bibm research\b",
    r"\bintel\b",
    r"\bcloudflare\b",
    r"\bvisa research\b",
    r"\bfujitsu research of america\b",
    r"\baptos labs\b",
    r"\bbain capital crypto\b",
    r"\bcategory labs\b",
    r"\boffchain labs\b",
    r"\bproof trading\b",
    r"\bntt research\b",
    r"\bnational institute of standards and technology\b",
]

NON_US_KEYWORD_PATTERNS = [
    r"\beth zurich\b",
    r"\beth zürich\b",
    r"\busi, lugano\b",
    r"\buniversity of luxembourg\b",
    r"\bruhr university bochum\b",
    r"\bkings? college london\b",
    r"\broyal holloway\b",
    r"\buniversity of auckland\b",
    r"\btechnical university of denmark\b",
    r"\bibm research europe\b",
    r"\borange\b",
]


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def build_article_tag(config: ConferenceConfig, paper: dict[str, Any]) -> str:
    title = normalize_space(str(paper.get("title", "")))
    return f"{config.conference}-{title}"


def classify_affiliation(
    affiliation: str,
    overrides: dict[str, AffiliationClassification] | None = None,
) -> AffiliationClassification:
    normalized = normalize_space(affiliation)
    lower = normalized.casefold()
    if overrides and lower in overrides:
        return overrides[lower]

    if lower in US_EXACT_ALIASES:
        return AffiliationClassification(True, "rule", 1.0, "exact_us_alias")

    for pattern in NON_US_KEYWORD_PATTERNS:
        if re.search(pattern, lower):
            return AffiliationClassification(False, "rule", 1.0, "non_us_keyword")

    for pattern in US_KEYWORD_PATTERNS:
        if re.search(pattern, lower):
            return AffiliationClassification(True, "rule", 0.95, "us_keyword")

    if re.search(r"\b(united states|usa|u\.s\.a\.|, us|, usa)\b", lower):
        return AffiliationClassification(True, "rule", 0.95, "us_location_marker")

    return AffiliationClassification(False, "unresolved", 0.0, "needs_review")


def expand_author_rows(
    config: ConferenceConfig,
    papers: list[dict[str, Any]],
    overrides: dict[str, AffiliationClassification] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []

    for paper in papers:
        authors = [normalize_space(str(author)) for author in paper.get("authors", [])]
        affiliations = [
            normalize_space(str(affiliation))
            for affiliation in paper.get("affiliations", [])
        ]
        paper_id = str(paper.get("paperId", ""))
        title = normalize_space(str(paper.get("title", "")))
        article_tag = build_article_tag(config, paper)

        if len(authors) != len(affiliations):
            issues.append(
                {
                    "conference": config.conference,
                    "year": str(config.year),
                    "paper_id": paper_id,
                    "title": title,
                    "issue": "author_affiliation_count_mismatch",
                    "authors_count": str(len(authors)),
                    "affiliations_count": str(len(affiliations)),
                    "authors": " | ".join(authors),
                    "affiliations": " | ".join(affiliations),
                }
            )
            continue

        for order, (author, affiliation) in enumerate(zip(authors, affiliations)):
            classification = classify_affiliation(affiliation, overrides)
            rows.append(
                {
                    "conference": config.conference,
                    "year": config.year,
                    "paper_id": paper_id,
                    "title": title,
                    "name": author,
                    "article_tag": article_tag,
                    "author_order": order,
                    "inst": affiliation,
                    "is_us_institution": classification.is_us,
                    "classification_source": classification.source,
                    "classification_confidence": classification.confidence,
                    "classification_reason": classification.reason,
                }
            )

    return rows, issues


def filter_us_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row["is_us_institution"]]


def normalize_papers(
    config: ConferenceConfig,
    papers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "conference": config.conference,
            "year": config.year,
            "paper_id": str(paper.get("paperId", "")),
            "title": normalize_space(str(paper.get("title", ""))),
            "article_tag": build_article_tag(config, paper),
            "authors_count": len(paper.get("authors", [])),
            "affiliations_count": len(paper.get("affiliations", [])),
        }
        for paper in papers
    ]


def build_affiliation_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["inst"], row["classification_reason"])
        candidates.setdefault(
            key,
            {
                "inst": row["inst"],
                "is_us_institution": row["is_us_institution"],
                "classification_source": row["classification_source"],
                "classification_confidence": row["classification_confidence"],
                "classification_reason": row["classification_reason"],
                "example_conference": row["conference"],
                "example_paper_id": row["paper_id"],
                "example_title": row["title"],
            },
        )
    return sorted(candidates.values(), key=lambda item: (item["inst"], item["classification_reason"]))


def load_institution_overrides(path: Path) -> dict[str, AffiliationClassification]:
    if not path.exists():
        return {}

    overrides: dict[str, AffiliationClassification] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            inst = normalize_space(row.get("inst", ""))
            if not inst:
                continue
            is_us_text = normalize_space(row.get("is_us_institution", "")).casefold()
            is_us = is_us_text in {"true", "1", "yes", "y"}
            reason = normalize_space(row.get("reason", "override"))
            overrides[inst.casefold()] = AffiliationClassification(
                is_us,
                "override",
                1.0,
                reason or "override",
            )
    return overrides


def build_llm_resolution_rows(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for candidate in candidates:
        if candidate["classification_source"] != "unresolved":
            continue
        rows.append(
            {
                "inst": candidate["inst"],
                "is_us_institution": False,
                "normalized_institution": candidate["inst"],
                "reason": "Conservative unresolved classification. Requires manual review before inclusion.",
                "confidence": 0.0,
                "needs_manual_review": True,
                "example_conference": candidate["example_conference"],
                "example_paper_id": candidate["example_paper_id"],
                "example_title": candidate["example_title"],
            }
        )
    return rows


def load_papers(raw_json_path: Path) -> list[dict[str, Any]]:
    data = json.loads(raw_json_path.read_text(encoding="utf-8"))
    papers = data.get("acceptedPapers")
    if not isinstance(papers, list):
        raise ValueError(f"{raw_json_path} does not contain acceptedPapers[]")
    return papers


def fetch_json(url: str, output_path: Path) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
            "Referer": url.rsplit("/", 2)[0] + "/acceptedpapers.php",
        },
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        content = response.read()
        status = getattr(response, "status", 200)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(content)
    return {
        "url": url,
        "status": status,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "path": str(output_path),
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_workbook(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "英文版"
    header = ["name", "year", "article_tag", "author_order", "inst"]
    sheet.append(header)
    for row in rows:
        sheet.append([row[column] for column in header])
    workbook.save(path)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def run_single_conference(
    config: ConferenceConfig,
    raw_json_path: Path,
    output_dir: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    papers = load_papers(raw_json_path)
    overrides = load_institution_overrides(
        output_dir / "reference" / "institution_country_overrides.csv"
    )
    paper_rows = normalize_papers(config, papers)
    rows, issues = expand_author_rows(config, papers, overrides)
    us_rows = filter_us_rows(rows)

    write_csv(
        output_dir / "interim" / f"{config.key}_author_affiliations_expanded.csv",
        rows,
        [
            "conference",
            "year",
            "paper_id",
            "title",
            "name",
            "article_tag",
            "author_order",
            "inst",
            "is_us_institution",
            "classification_source",
            "classification_confidence",
            "classification_reason",
        ],
    )
    write_csv(
        output_dir / "interim" / f"{config.key}_affiliation_resolution_queue.csv",
        issues,
        [
            "conference",
            "year",
            "paper_id",
            "title",
            "issue",
            "authors_count",
            "affiliations_count",
            "authors",
            "affiliations",
        ],
    )
    write_csv(
        output_dir / "output" / f"{config.key}_us_institutions.csv",
        us_rows,
        ["name", "year", "article_tag", "author_order", "inst"],
    )
    write_csv(
        output_dir / "output" / f"{config.key}_us_institutions_audit.csv",
        us_rows,
        [
            "conference",
            "year",
            "paper_id",
            "title",
            "name",
            "article_tag",
            "author_order",
            "inst",
            "classification_source",
            "classification_confidence",
            "classification_reason",
        ],
    )
    write_workbook(output_dir / "output" / f"{config.key}_us_institutions.xlsx", us_rows)

    report = {
        "conference": config.conference,
        "year": config.year,
        "raw_json": str(raw_json_path),
        "papers_count": len(papers),
        "expanded_author_rows": len(rows),
        "us_author_rows": len(us_rows),
        "affiliation_mismatch_issues": len(issues),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    report_path = output_dir / "output" / f"{config.key}_validation_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report, paper_rows, rows, issues


def run_all_pipelines(output_dir: Path) -> dict[str, Any]:
    reports: list[dict[str, Any]] = []
    all_papers: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    all_issues: list[dict[str, str]] = []

    for config in CONFERENCE_CONFIGS.values():
        raw_json_path = output_dir / "raw" / f"{config.key}_papers.json"
        report, paper_rows, rows, issues = run_single_conference(config, raw_json_path, output_dir)
        reports.append(report)
        all_papers.extend(paper_rows)
        all_rows.extend(rows)
        all_issues.extend(issues)

    all_us_rows = filter_us_rows(all_rows)
    candidates = build_affiliation_candidates(all_rows)
    llm_rows = build_llm_resolution_rows(candidates)

    write_csv(
        output_dir / "interim" / "papers_normalized.csv",
        all_papers,
        [
            "conference",
            "year",
            "paper_id",
            "title",
            "article_tag",
            "authors_count",
            "affiliations_count",
        ],
    )
    write_csv(
        output_dir / "interim" / "author_affiliations_expanded.csv",
        all_rows,
        [
            "conference",
            "year",
            "paper_id",
            "title",
            "name",
            "article_tag",
            "author_order",
            "inst",
            "is_us_institution",
            "classification_source",
            "classification_confidence",
            "classification_reason",
        ],
    )
    write_csv(
        output_dir / "interim" / "us_institution_candidates.csv",
        candidates,
        [
            "inst",
            "is_us_institution",
            "classification_source",
            "classification_confidence",
            "classification_reason",
            "example_conference",
            "example_paper_id",
            "example_title",
        ],
    )
    write_csv(
        output_dir / "interim" / "affiliation_resolution_queue.csv",
        all_issues,
        [
            "conference",
            "year",
            "paper_id",
            "title",
            "issue",
            "authors_count",
            "affiliations_count",
            "authors",
            "affiliations",
        ],
    )
    write_jsonl(output_dir / "interim" / "llm_resolution_input.jsonl", llm_rows)
    write_jsonl(output_dir / "interim" / "llm_resolution_output.jsonl", llm_rows)

    write_csv(
        output_dir / "output" / "2025-2026三大密码会_美国机构.csv",
        all_us_rows,
        ["name", "year", "article_tag", "author_order", "inst"],
    )
    write_csv(
        output_dir / "output" / "2025-2026三大密码会_美国机构_audit.csv",
        all_us_rows,
        [
            "conference",
            "year",
            "paper_id",
            "title",
            "name",
            "article_tag",
            "author_order",
            "inst",
            "classification_source",
            "classification_confidence",
            "classification_reason",
        ],
    )
    write_workbook(output_dir / "output" / "2025-2026三大密码会_美国机构.xlsx", all_us_rows)

    combined_report = {
        "reports": reports,
        "papers_count": sum(report["papers_count"] for report in reports),
        "expanded_author_rows": len(all_rows),
        "us_author_rows": len(all_us_rows),
        "affiliation_mismatch_issues": len(all_issues),
        "unresolved_affiliation_candidates": len(llm_rows),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "notes": [
            "Main output contains only author rows whose author and affiliation arrays aligned and whose institution matched US rules.",
            "Mismatched author-affiliation papers are preserved in data/interim/affiliation_resolution_queue.csv for review.",
            "LLM resolution output is conservative: unresolved institutions remain marked for manual review.",
        ],
    }
    report_path = output_dir / "output" / "validation_report.json"
    report_path.write_text(
        json.dumps(combined_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return combined_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--conference",
        choices=[*CONFERENCE_CONFIGS.keys(), "all"],
        default="all",
    )
    parser.add_argument("--raw-json", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args(argv)

    if args.conference == "all":
        if args.fetch:
            for config in CONFERENCE_CONFIGS.values():
                raw_json_path = args.output_dir / "raw" / f"{config.key}_papers.json"
                try:
                    metadata = fetch_json(config.url, raw_json_path)
                    metadata_path = args.output_dir / "raw" / f"{config.key}_fetch_metadata.json"
                    metadata_path.write_text(
                        json.dumps(metadata, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                except urllib.error.HTTPError as exc:
                    print(
                        f"Fetch for {config.key} failed with HTTP {exc.code}. "
                        "Provide saved raw snapshots before running all.",
                        file=sys.stderr,
                    )
                    return 2
        report = run_all_pipelines(args.output_dir)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    config = CONFERENCE_CONFIGS[args.conference]
    raw_json_path = args.raw_json or args.output_dir / "raw" / f"{config.key}_papers.json"

    if args.fetch:
        try:
            metadata = fetch_json(config.url, raw_json_path)
            metadata_path = args.output_dir / "raw" / f"{config.key}_fetch_metadata.json"
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except urllib.error.HTTPError as exc:
            print(
                f"Fetch failed with HTTP {exc.code}. Provide --raw-json with a saved snapshot.",
                file=sys.stderr,
            )
            return 2

    report, _paper_rows, _rows, _issues = run_single_conference(
        config,
        raw_json_path,
        args.output_dir,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
