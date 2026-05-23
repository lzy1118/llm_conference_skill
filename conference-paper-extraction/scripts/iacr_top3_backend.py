from __future__ import annotations

import argparse
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

from backend_common import write_csv, write_jsonl, write_workbook
from classification_common import classify_with_patterns, load_override_rows, normalize_space
from iacr_resolution import run_resolution


@dataclass(frozen=True)
class ConferenceConfig:
    key: str
    conference: str
    year: int
    url: str


@dataclass(frozen=True)
class AffiliationClassification:
    country: str
    is_us: bool
    source: str
    confidence: float
    reason: str


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
EUROCRYPT_2026 = ConferenceConfig(
    key="eurocrypt_2026",
    conference="EUROCRYPT",
    year=2026,
    url="https://eurocrypt.iacr.org/2026/json/papers.json",
)

CONFERENCE_CONFIGS = {
    config.key: config for config in [ASIACRYPT_2025, CRYPTO_2025, EUROCRYPT_2026]
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


def build_article_tag(config: ConferenceConfig, paper: dict[str, Any]) -> str:
    title = normalize_space(str(paper.get("title", "")))
    return f"{config.conference}-{title}"


def classify_affiliation(
    affiliation: str,
    overrides: dict[str, AffiliationClassification] | None = None,
) -> AffiliationClassification:
    return classify_with_patterns(
        affiliation,
        overrides=overrides,
        exact_aliases=US_EXACT_ALIASES,
        non_us_patterns=NON_US_KEYWORD_PATTERNS,
        us_patterns=US_KEYWORD_PATTERNS,
        classification_factory=AffiliationClassification,
    )


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
                    "country": classification.country,
                    "is_us_institution": classification.is_us,
                    "classification_source": classification.source,
                    "classification_confidence": classification.confidence,
                    "classification_reason": classification.reason,
                }
            )

    return rows, issues


def filter_us_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row["is_us_institution"]]


def filter_classified_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("country") and row["country"] != "Unknown"]


def normalize_papers(config: ConferenceConfig, papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
                "country": row["country"],
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
    return load_override_rows(path, AffiliationClassification)


def build_llm_resolution_rows(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for candidate in candidates:
        if candidate["classification_source"] != "unresolved":
            continue
        rows.append(
            {
                "inst": candidate["inst"],
                "country": candidate.get("country", "Unknown"),
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


def run_single_conference(
    config: ConferenceConfig,
    raw_json_path: Path,
    output_dir: Path,
    resolve_mismatches: bool = False,
    query_dblp_for_resolution: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    papers = load_papers(raw_json_path)
    overrides = load_institution_overrides(output_dir / "reference" / "institution_country_overrides.csv")
    paper_rows = normalize_papers(config, papers)
    rows, issues = expand_author_rows(config, papers, overrides)
    us_rows = filter_us_rows(rows)
    classified_rows = filter_classified_rows(rows)

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
            "country",
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
        output_dir / "output" / f"{config.key}_author_affiliations.csv",
        classified_rows,
        ["name", "year", "article_tag", "author_order", "inst", "country"],
    )
    write_csv(
        output_dir / "output" / f"{config.key}_author_affiliations_audit.csv",
        classified_rows,
        [
            "conference",
            "year",
            "paper_id",
            "title",
            "name",
            "article_tag",
            "author_order",
            "inst",
            "country",
            "is_us_institution",
            "classification_source",
            "classification_confidence",
            "classification_reason",
        ],
    )
    write_workbook(output_dir / "output" / f"{config.key}_author_affiliations.xlsx", classified_rows, ["name", "year", "article_tag", "author_order", "inst", "country"])
    write_csv(
        output_dir / "interim" / f"{config.key}_institution_classification_candidates.csv",
        build_affiliation_candidates(rows),
        [
            "inst",
            "country",
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
            "country",
            "classification_source",
            "classification_confidence",
            "classification_reason",
        ],
    )
    write_workbook(output_dir / "output" / f"{config.key}_us_institutions.xlsx", us_rows, ["name", "year", "article_tag", "author_order", "inst"])

    report = {
        "conference": config.conference,
        "year": config.year,
        "raw_json": str(raw_json_path),
        "papers_count": len(papers),
        "expanded_author_rows": len(rows),
        "classified_author_rows": len(classified_rows),
        "resolved_country_rows": len(classified_rows),
        "unresolved_country_rows": len(rows) - len(classified_rows),
        "us_author_rows": len(us_rows),
        "affiliation_mismatch_issues": len(issues),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if resolve_mismatches and issues:
        resolution_dir = output_dir / "resolution" / config.key
        resolution_queue = output_dir / "interim" / f"{config.key}_affiliation_resolution_queue.csv"
        resolution_report = run_resolution(
            resolution_queue,
            resolution_dir,
            query_dblp=query_dblp_for_resolution,
        )
        report["resolution_report_path"] = str(resolution_dir / "resolution_report.json")
        report["resolution_tasks"] = resolution_report["tasks"]
    report_path = output_dir / "output" / f"{config.key}_validation_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report, paper_rows, rows, issues


def run_all_pipelines(
    output_dir: Path,
    conference_keys: list[str] | None = None,
    resolve_mismatches: bool = False,
    query_dblp_for_resolution: bool = False,
) -> dict[str, Any]:
    selected_keys = conference_keys or list(CONFERENCE_CONFIGS.keys())
    reports: list[dict[str, Any]] = []
    all_papers: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    all_issues: list[dict[str, str]] = []

    for key in selected_keys:
        config = CONFERENCE_CONFIGS[key]
        raw_json_path = output_dir / "raw" / f"{config.key}_papers.json"
        report, paper_rows, rows, issues = run_single_conference(
            config,
            raw_json_path,
            output_dir,
            resolve_mismatches=resolve_mismatches,
            query_dblp_for_resolution=query_dblp_for_resolution,
        )
        reports.append(report)
        all_papers.extend(paper_rows)
        all_rows.extend(rows)
        all_issues.extend(issues)

    all_us_rows = filter_us_rows(all_rows)
    all_classified_rows = filter_classified_rows(all_rows)
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
            "country",
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
            "country",
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
        output_dir / "interim" / "institution_classification_candidates.csv",
        candidates,
        [
            "inst",
            "country",
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
        output_dir / "output" / "2025-2026三大密码会_作者机构国家.csv",
        all_classified_rows,
        ["name", "year", "article_tag", "author_order", "inst", "country"],
    )
    write_csv(
        output_dir / "output" / "2025-2026三大密码会_作者机构国家_audit.csv",
        all_classified_rows,
        [
            "conference",
            "year",
            "paper_id",
            "title",
            "name",
            "article_tag",
            "author_order",
            "inst",
            "country",
            "is_us_institution",
            "classification_source",
            "classification_confidence",
            "classification_reason",
        ],
    )
    write_workbook(output_dir / "output" / "2025-2026三大密码会_作者机构国家.xlsx", all_classified_rows, ["name", "year", "article_tag", "author_order", "inst", "country"])

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
            "country",
            "classification_source",
            "classification_confidence",
            "classification_reason",
        ],
    )
    write_workbook(output_dir / "output" / "2025-2026三大密码会_美国机构.xlsx", all_us_rows, ["name", "year", "article_tag", "author_order", "inst"])

    combined_report = {
        "reports": reports,
        "papers_count": sum(report["papers_count"] for report in reports),
        "expanded_author_rows": len(all_rows),
        "classified_author_rows": len(all_classified_rows),
        "resolved_country_rows": len(all_classified_rows),
        "unresolved_country_rows": len(all_rows) - len(all_classified_rows),
        "us_author_rows": len(all_us_rows),
        "affiliation_mismatch_issues": len(all_issues),
        "unresolved_affiliation_candidates": len(llm_rows),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "notes": [
            "Main output contains author rows whose author and affiliation arrays aligned and whose country could be resolved conservatively.",
            "Mismatched author-affiliation papers are preserved in data/interim/affiliation_resolution_queue.csv for review.",
            "LLM resolution output is conservative: unresolved institutions remain marked for manual review.",
        ],
    }
    report_path = output_dir / "output" / "validation_report.json"
    report_path.write_text(json.dumps(combined_report, ensure_ascii=False, indent=2), encoding="utf-8")
    return combined_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--conference", nargs="*", default=["all"], help="Conference keys or 'all'")
    parser.add_argument("--raw-json", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--list-conferences", action="store_true")
    parser.add_argument("--resolve-mismatches", action="store_true")
    parser.add_argument("--query-dblp-for-resolution", action="store_true")
    args = parser.parse_args(argv)

    if args.list_conferences:
        for key, config in CONFERENCE_CONFIGS.items():
            print(f"  {key}: {config.conference} {config.year}")
        return 0

    if "all" in args.conference:
        keys = list(CONFERENCE_CONFIGS.keys())
    else:
        keys = args.conference

    if args.fetch:
        for key in keys:
            config = CONFERENCE_CONFIGS[key]
            raw_json_path = args.output_dir / "raw" / f"{config.key}_papers.json"
            try:
                metadata = fetch_json(config.url, raw_json_path)
                metadata_path = args.output_dir / "raw" / f"{config.key}_fetch_metadata.json"
                metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            except urllib.error.HTTPError as exc:
                print(
                    f"Fetch for {config.key} failed with HTTP {exc.code}. Provide saved raw snapshots before running.",
                    file=sys.stderr,
                )
                return 2

    if len(keys) == 1 and args.raw_json:
        config = CONFERENCE_CONFIGS[keys[0]]
        report, _paper_rows, _rows, _issues = run_single_conference(
            config,
            args.raw_json,
            args.output_dir,
            resolve_mismatches=args.resolve_mismatches,
            query_dblp_for_resolution=args.query_dblp_for_resolution,
        )
    else:
        report = run_all_pipelines(
            args.output_dir,
            keys,
            resolve_mismatches=args.resolve_mismatches,
            query_dblp_for_resolution=args.query_dblp_for_resolution,
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
