from __future__ import annotations

import csv
import json
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from backend_common import write_csv, write_jsonl


BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass(frozen=True)
class ResolutionTask:
    resolution_id: str
    conference: str
    year: int
    paper_id: str
    title: str
    issue: str
    authors: list[str]
    affiliations: list[str]
    article_tag: str


@dataclass(frozen=True)
class SourceCandidate:
    resolution_id: str
    source_type: str
    url: str
    title: str
    authors: list[str]
    doi: str
    score: float
    retrieved_at: str


def normalize_text(value: str) -> str:
    value = re.sub(r"\$([^$]+)\$", r"\1", value)
    value = re.sub(r"[^0-9a-zA-Z]+", " ", value.casefold())
    return re.sub(r"\s+", " ", value).strip()


def normalize_name(value: str) -> str:
    return normalize_text(value).replace(" ", "")


def split_pipe(value: str) -> list[str]:
    return [item.strip() for item in value.split("|") if item.strip()]


def build_resolution_id(conference: str, year: str | int, paper_id: str | int) -> str:
    safe_paper_id = re.sub(r"[^0-9A-Za-z]+", "_", str(paper_id)).strip("_")
    return f"{conference}_{year}_{safe_paper_id}"


def read_resolution_queue(path: Path) -> list[ResolutionTask]:
    tasks: list[ResolutionTask] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            conference = row["conference"].strip()
            year = int(row["year"])
            paper_id = row["paper_id"].strip()
            title = row["title"].strip()
            tasks.append(
                ResolutionTask(
                    resolution_id=build_resolution_id(conference, year, paper_id),
                    conference=conference,
                    year=year,
                    paper_id=paper_id,
                    title=title,
                    issue=row["issue"].strip(),
                    authors=split_pipe(row.get("authors", "")),
                    affiliations=split_pipe(row.get("affiliations", "")),
                    article_tag=f"{conference}-{title}",
                )
            )
    return tasks


def title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio()


def author_set_similarity(left: list[str], right: list[str]) -> float:
    if not left or not right:
        return 0.0
    left_set = {normalize_name(name) for name in left}
    right_set = {normalize_name(name) for name in right}
    return len(left_set & right_set) / len(left_set | right_set)


def rank_source_candidates(target_title: str, target_authors: list[str], candidates: list[SourceCandidate]) -> list[SourceCandidate]:
    source_bonus = {
        "springer": 0.04,
        "pdf": 0.03,
        "eprint": 0.02,
        "dblp": 0.01,
        "local_iacr": 0.0,
        "search": 0.0,
    }
    ranked: list[SourceCandidate] = []
    for candidate in candidates:
        title_score = title_similarity(target_title, candidate.title)
        author_score = author_set_similarity(target_authors, candidate.authors)
        score = min(1.0, title_score * 0.75 + author_score * 0.2 + source_bonus.get(candidate.source_type, 0.0))
        ranked.append(
            SourceCandidate(
                resolution_id=candidate.resolution_id,
                source_type=candidate.source_type,
                url=candidate.url,
                title=candidate.title,
                authors=candidate.authors,
                doi=candidate.doi,
                score=round(score, 4),
                retrieved_at=candidate.retrieved_at,
            )
        )
    return sorted(ranked, key=lambda item: item.score, reverse=True)


def search_url(base: str, title: str) -> str:
    return base + urllib.parse.quote_plus(title)


def coerce_author_list(value: Any) -> list[str]:
    if isinstance(value, dict):
        value = value.get("author", [])
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return []
    authors = []
    for item in value:
        if isinstance(item, dict):
            authors.append(str(item.get("text", "")).strip())
        else:
            authors.append(str(item).strip())
    return [author for author in authors if author]


def parse_dblp_hits(resolution_id: str, payload: dict[str, Any], retrieved_at: str) -> list[SourceCandidate]:
    hits = payload.get("result", {}).get("hits", {}).get("hit", [])
    if isinstance(hits, dict):
        hits = [hits]
    candidates = []
    for hit in hits:
        info = hit.get("info", {})
        title = str(info.get("title", "")).rstrip(".").strip()
        authors = coerce_author_list(info.get("authors", {}))
        ee = str(info.get("ee", "")).strip()
        dblp_url = str(info.get("url", "")).strip()
        doi = str(info.get("doi", "")).strip()
        if ee:
            source_type = "eprint" if "eprint.iacr.org" in ee else "pdf"
            candidates.append(SourceCandidate(resolution_id, source_type, ee, title, authors, doi, 0.0, retrieved_at))
        if dblp_url:
            candidates.append(SourceCandidate(resolution_id, "dblp", dblp_url, title, authors, doi, 0.0, retrieved_at))
    return candidates


def query_dblp_candidates(task: ResolutionTask, retrieved_at: str) -> list[SourceCandidate]:
    query = urllib.parse.quote_plus(task.title)
    url = f"https://dblp.org/search/publ/api?q={query}&format=json&h=5"
    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": BROWSER_HEADERS["User-Agent"],
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception:
        return []
    return parse_dblp_hits(task.resolution_id, payload, retrieved_at)


def query_eprint_search_candidates(task: ResolutionTask, retrieved_at: str) -> list[SourceCandidate]:
    url = search_url("https://eprint.iacr.org/search?q=", task.title)
    try:
        request = urllib.request.Request(url, headers=BROWSER_HEADERS)
        with urllib.request.urlopen(request, timeout=8) as response:
            html = response.read().decode("utf-8", errors="replace")
    except Exception:
        return []
    seen = set()
    candidates = []
    for href in re.findall(r'href="([^"]+)"', html):
        match = re.fullmatch(r"/(\d{4})/(\d+)(?:\.pdf)?", href)
        if not match:
            continue
        page_url = f"https://eprint.iacr.org/{match.group(1)}/{match.group(2)}"
        if page_url in seen:
            continue
        seen.add(page_url)
        candidates.append(SourceCandidate(task.resolution_id, "eprint", page_url, task.title, task.authors, "", 0.0, retrieved_at))
    return candidates


def collect_source_candidates(task: ResolutionTask, query_dblp: bool = False) -> list[SourceCandidate]:
    now = datetime.now(timezone.utc).isoformat() if query_dblp else "offline_search_template"
    candidates = [
        SourceCandidate(task.resolution_id, "local_iacr", f"generated-data/extraction/raw/{task.conference.lower()}_{task.year}_papers.json", task.title, task.authors, "", 0.0, now),
        SourceCandidate(task.resolution_id, "search", search_url("https://link.springer.com/search?query=", task.title), task.title, task.authors, "", 0.0, now),
        SourceCandidate(task.resolution_id, "search", search_url("https://dblp.org/search/publ?q=", task.title), task.title, task.authors, "", 0.0, now),
        SourceCandidate(task.resolution_id, "search", search_url("https://eprint.iacr.org/search?q=", task.title), task.title, task.authors, "", 0.0, now),
    ]
    if query_dblp:
        eprint_candidates = query_eprint_search_candidates(task, now)
        candidates.extend(eprint_candidates)
        if not eprint_candidates:
            candidates.extend(query_dblp_candidates(task, now))
    return rank_source_candidates(task.title, task.authors, candidates)


def write_candidates(path: Path, candidates: list[SourceCandidate]) -> None:
    write_csv(
        path,
        [asdict(candidate) | {"authors": " | ".join(candidate.authors)} for candidate in candidates],
        ["resolution_id", "source_type", "url", "title", "authors", "doi", "score", "retrieved_at"],
    )


def run_resolution(queue_path: Path, output_dir: Path, query_dblp: bool = False) -> dict[str, Any]:
    tasks = read_resolution_queue(queue_path)
    all_candidates: list[SourceCandidate] = []
    unresolved_rows: list[dict[str, Any]] = []
    search_rows: list[dict[str, Any]] = []

    for task in tasks:
        ranked = collect_source_candidates(task, query_dblp=query_dblp)
        all_candidates.extend(ranked)
        best = ranked[0] if ranked else None
        unresolved_rows.append(
            {
                "resolution_id": task.resolution_id,
                "conference": task.conference,
                "year": task.year,
                "paper_id": task.paper_id,
                "title": task.title,
                "reason": task.issue,
                "best_source_url": best.url if best else "",
                "best_source_score": best.score if best else 0.0,
            }
        )
        for candidate in ranked:
            search_rows.append(asdict(candidate) | {"authors": " | ".join(candidate.authors)})

    output_dir.mkdir(parents=True, exist_ok=True)
    write_candidates(output_dir / "source_candidates.csv", all_candidates)
    write_csv(
        output_dir / "unresolved_after_source_lookup.csv",
        unresolved_rows,
        ["resolution_id", "conference", "year", "paper_id", "title", "reason", "best_source_url", "best_source_score"],
    )
    write_csv(
        output_dir / "search_results.csv",
        search_rows,
        ["resolution_id", "source_type", "url", "title", "authors", "doi", "score", "retrieved_at"],
    )
    write_jsonl(output_dir / "parsed_affiliations.jsonl", [])
    write_csv(
        output_dir / "resolved_author_affiliations.csv",
        [],
        [
            "resolution_id",
            "conference",
            "year",
            "paper_id",
            "title",
            "name",
            "author_order",
            "inst",
            "source_url",
            "evidence_text",
            "confidence",
            "classification_source",
            "classification_confidence",
            "classification_reason",
            "article_tag",
        ],
    )
    report = {
        "tasks": len(tasks),
        "resolved_rows": 0,
        "unresolved_tasks": len(unresolved_rows),
        "parsed_records": 0,
        "query_dblp": query_dblp,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (output_dir / "resolution_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
