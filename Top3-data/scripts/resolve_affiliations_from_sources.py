from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.top3_us_pipeline import build_article_tag, classify_affiliation, ConferenceConfig

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


CONFERENCE_BY_NAME = {
    "ASIACRYPT": ConferenceConfig(
        key="asiacrypt_2025",
        conference="ASIACRYPT",
        year=2025,
        url="https://asiacrypt.iacr.org/2025/json/papers.json",
    ),
    "CRYPTO": ConferenceConfig(
        key="crypto_2025",
        conference="CRYPTO",
        year=2025,
        url="https://crypto.iacr.org/2025/json/papers.json",
    ),
    "EUROCRYPT": ConferenceConfig(
        key="eurocrypt_2026",
        conference="EUROCRYPT",
        year=2026,
        url="https://eurocrypt.iacr.org/2026/json/papers.json",
    ),
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
    value = re.sub(r"\\$([^$]+)\\$", r"\1", value)
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
            config = CONFERENCE_BY_NAME[conference]
            article_tag = build_article_tag(config, {"title": title})
            tasks.append(
                ResolutionTask(
                    resolution_id=build_resolution_id(conference, year, paper_id),
                    conference=conference,
                    year=year,
                    paper_id=paper_id,
                    title=title,
                    issue=row["issue"].strip(),
                    authors=split_pipe(row["authors"]),
                    affiliations=split_pipe(row["affiliations"]),
                    article_tag=article_tag,
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


def rank_source_candidates(
    target_title: str,
    target_authors: list[str],
    candidates: list[SourceCandidate],
) -> list[SourceCandidate]:
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


def parse_dblp_hits(
    resolution_id: str,
    payload: dict[str, Any],
    retrieved_at: str,
) -> list[SourceCandidate]:
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
        html = fetch_text(url, timeout=8)
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
        candidates.append(
            SourceCandidate(
                task.resolution_id,
                "eprint",
                page_url,
                task.title,
                task.authors,
                "",
                0.0,
                retrieved_at,
            )
        )
    return candidates


def collect_source_candidates(task: ResolutionTask, query_dblp: bool = False) -> list[SourceCandidate]:
    now = datetime.now(timezone.utc).isoformat() if query_dblp else "offline_search_template"
    candidates = [
        SourceCandidate(
            task.resolution_id,
            "local_iacr",
            f"data/raw/{task.conference.lower()}_{task.year}_papers.json",
            task.title,
            task.authors,
            "",
            0.0,
            now,
        ),
        SourceCandidate(
            task.resolution_id,
            "search",
            search_url("https://link.springer.com/search?query=", task.title),
            task.title,
            task.authors,
            "",
            0.0,
            now,
        ),
        SourceCandidate(
            task.resolution_id,
            "search",
            search_url("https://dblp.org/search/publ?q=", task.title),
            task.title,
            task.authors,
            "",
            0.0,
            now,
        ),
        SourceCandidate(
            task.resolution_id,
            "search",
            search_url("https://eprint.iacr.org/search?q=", task.title),
            task.title,
            task.authors,
            "",
            0.0,
            now,
        ),
    ]
    if query_dblp:
        eprint_candidates = query_eprint_search_candidates(task, now)
        candidates.extend(eprint_candidates)
        if not eprint_candidates:
            candidates.extend(query_dblp_candidates(task, now))
    return rank_source_candidates(task.title, task.authors, candidates)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def extract_frontmatter_from_pdf(pdf_path: Path, max_pages: int = 2) -> str:
    try:
        result = subprocess.run(
            [
                "pdftotext",
                "-f",
                "1",
                "-l",
                str(max_pages),
                str(pdf_path),
                "-",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
    except Exception:
        pass

    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            import pdfplumber
        except ImportError:
            return ""
        with pdfplumber.open(str(pdf_path)) as pdf:
            texts = [page.extract_text() or "" for page in pdf.pages[:max_pages]]
        return "\n".join(texts)

    reader = PdfReader(str(pdf_path))
    texts = [page.extract_text() or "" for page in reader.pages[:max_pages]]
    return "\n".join(texts)


def extract_frontmatter_from_html(html: str) -> str:
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_frontmatter_text(title: str, authors: list[str], text: str) -> dict[str, Any]:
    normalized_text = normalize_text(text)
    title_match = normalize_text(title) in normalized_text
    author_rows = []
    found_authors = []

    for author in authors:
        pattern = re.compile(rf"{re.escape(author)}\s*:\s*(.+)", re.IGNORECASE)
        match = pattern.search(text)
        if not match:
            continue
        affiliation = re.split(r"\n|;(?=\s*[A-Z][a-z]+ [A-Z])", match.group(1).strip())[0].strip()
        affiliation = re.sub(r"\s+", " ", affiliation)
        if not affiliation:
            continue
        found_authors.append(author)
        author_rows.append(
            {
                "author": author,
                "affiliations": [affiliation],
                "evidence_text": f"{author}: {affiliation}",
                "confidence": 0.95,
            }
        )

    authors_match = {normalize_name(name) for name in found_authors} == {normalize_name(name) for name in authors}
    needs_review = not (title_match and authors_match and len(author_rows) == len(authors))
    return {
        "title_match": title_match,
        "authors_match": authors_match,
        "author_affiliations": author_rows,
        "needs_manual_review": needs_review,
        "reason": "parsed_by_author_colon_rule" if not needs_review else "insufficient_structured_frontmatter",
    }


def parse_confirmed_single_affiliation(
    title: str,
    authors: list[str],
    affiliations: list[str],
    text: str,
) -> dict[str, Any]:
    normalized_text = normalize_text(text)
    title_match = normalize_text(title) in normalized_text
    author_hits = [author for author in authors if normalize_text(author) in normalized_text]
    authors_match = len(author_hits) == len(authors)
    if not (title_match and authors_match and len(affiliations) == 1):
        return {
            "title_match": title_match,
            "authors_match": authors_match,
            "author_affiliations": [],
            "needs_manual_review": True,
            "reason": "single_affiliation_confirmation_failed",
        }

    affiliation = affiliations[0]
    return {
        "title_match": True,
        "authors_match": True,
        "author_affiliations": [
            {
                "author": author,
                "affiliations": [affiliation],
                "evidence_text": (
                    f"Source confirms title and author list; IACR JSON has a single affiliation: {affiliation}"
                ),
                "confidence": 0.9,
            }
            for author in authors
        ],
        "needs_manual_review": False,
        "reason": "source_confirmed_authors_with_single_iacr_affiliation",
    }


def accept_resolved_mapping(
    resolution_id: str,
    conference: str,
    year: int,
    paper_id: str,
    title: str,
    article_tag: str,
    source_url: str,
    title_score: float,
    parsed: dict[str, Any],
) -> list[dict[str, Any]]:
    if not parsed.get("title_match") or not parsed.get("authors_match"):
        return []
    if parsed.get("needs_manual_review"):
        return []
    if title_score < 0.98:
        return []

    accepted: list[dict[str, Any]] = []
    for order, item in enumerate(parsed.get("author_affiliations", [])):
        confidence = float(item.get("confidence", 0.0))
        if confidence < 0.9:
            continue
        affiliations = item.get("affiliations", [])
        us_affiliations = [aff for aff in affiliations if classify_affiliation(aff).is_us]
        if not us_affiliations:
            continue
        inst = "; ".join(affiliations)
        accepted.append(
            {
                "resolution_id": resolution_id,
                "conference": conference,
                "year": year,
                "paper_id": paper_id,
                "title": title,
                "name": item["author"],
                "author_order": order,
                "inst": inst,
                "source_url": source_url,
                "evidence_text": item.get("evidence_text", ""),
                "confidence": confidence,
                "classification_source": "source_pdf",
                "classification_confidence": confidence,
                "classification_reason": "source_evidence",
                "article_tag": article_tag,
            }
        )
    return accepted


def write_resolution_outputs(
    output_dir: Path,
    resolved: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    parsed: list[dict[str, Any]],
    tasks_count: int | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "parsed_affiliations.jsonl", parsed)
    write_csv(
        output_dir / "resolved_author_affiliations.csv",
        resolved,
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
    write_csv(
        output_dir / "merge_candidates_us_rows.csv",
        resolved,
        ["name", "year", "article_tag", "author_order", "inst"],
    )
    write_csv(
        output_dir / "unresolved_after_source_lookup.csv",
        unresolved,
        [
            "resolution_id",
            "conference",
            "year",
            "paper_id",
            "title",
            "reason",
            "best_source_url",
            "best_source_score",
        ],
    )
    report = {
        "tasks": tasks_count if tasks_count is not None else len(unresolved),
        "resolved_us_rows": len(resolved),
        "unresolved_tasks": len(unresolved),
        "parsed_records": len(parsed),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (output_dir / "resolution_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_candidates(path: Path, candidates: list[SourceCandidate]) -> None:
    write_csv(
        path,
        [asdict(candidate) | {"authors": " | ".join(candidate.authors)} for candidate in candidates],
        ["resolution_id", "source_type", "url", "title", "authors", "doi", "score", "retrieved_at"],
    )


def fetch_text(url: str, timeout: int = 20) -> str:
    request = urllib.request.Request(url, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def source_to_pdf_url(url: str) -> str:
    if re.fullmatch(r"https://eprint\.iacr\.org/\d{4}/\d+", url):
        return f"{url}.pdf"
    return url


def download_binary(url: str, output_path: Path, timeout: int = 30) -> bool:
    request = urllib.request.Request(url, headers=BROWSER_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("content-type", "")
            data = response.read()
    except Exception:
        return False
    if "pdf" not in content_type.casefold() and not data.startswith(b"%PDF"):
        return False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)
    return True


def append_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


def save_checkpoint(
    output_dir: Path,
    resolved: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    parsed_records: list[dict[str, Any]],
    all_candidates: list[SourceCandidate],
    total_tasks: int,
) -> None:
    write_resolution_outputs(output_dir, resolved, unresolved, parsed_records, tasks_count=total_tasks)
    write_candidates(output_dir / "source_candidates.csv", all_candidates)
    write_candidates(output_dir / "search_results.csv", all_candidates)


def run_resolution(
    queue_path: Path,
    output_dir: Path,
    start: int = 0,
    limit: int | None = None,
    query_dblp: bool = False,
    checkpoint_every: int = 25,
) -> dict[str, Any]:
    tasks = read_resolution_queue(queue_path)
    end = len(tasks) if limit is None else min(start + limit, len(tasks))
    tasks = tasks[start:end]

    all_candidates: list[SourceCandidate] = []
    parsed_records: list[dict[str, Any]] = []
    resolved: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    total_queue_size = end - start

    for index, task in enumerate(tasks, start=1):
        global_index = start + index
        if index == 1 or index % 25 == 0 or index == len(tasks):
            print(f"resolving {global_index} (batch {index}/{len(tasks)}) {task.resolution_id}", file=sys.stderr, flush=True)
        ranked = collect_source_candidates(task, query_dblp=query_dblp)
        all_candidates.extend(ranked)
        best = ranked[0] if ranked else None

        extracted_path = output_dir / "extracted_text" / f"{task.resolution_id}_page1.txt"
        text = extracted_path.read_text(encoding="utf-8") if extracted_path.exists() else ""
        if not text:
            for candidate in ranked:
                if candidate.source_type not in {"eprint", "pdf", "springer"}:
                    continue
                pdf_url = source_to_pdf_url(candidate.url)
                pdf_path = output_dir / "downloaded_pdfs" / f"{task.resolution_id}.pdf"
                if pdf_path.exists() and pdf_path.stat().st_size > 0:
                    text = extract_frontmatter_from_pdf(pdf_path, max_pages=2)
                    if text:
                        extracted_path.parent.mkdir(parents=True, exist_ok=True)
                        extracted_path.write_text(text, encoding="utf-8")
                        best = candidate
                        break
                if download_binary(pdf_url, pdf_path):
                    text = extract_frontmatter_from_pdf(pdf_path, max_pages=2)
                    extracted_path.parent.mkdir(parents=True, exist_ok=True)
                    extracted_path.write_text(text, encoding="utf-8")
                    best = candidate
                    break
                if candidate.source_type == "eprint":
                    try:
                        text = fetch_text(candidate.url, timeout=20)
                    except Exception:
                        text = ""
                    if text:
                        extracted_path.parent.mkdir(parents=True, exist_ok=True)
                        extracted_path.write_text(text, encoding="utf-8")
                        best = candidate
                        break
        parsed = parse_frontmatter_text(task.title, task.authors, text) if text else {
            "title_match": False,
            "authors_match": False,
            "author_affiliations": [],
            "needs_manual_review": True,
            "reason": "no_source_text_available",
        }
        if parsed.get("needs_manual_review") and text:
            single_affiliation_parsed = parse_confirmed_single_affiliation(
                task.title,
                task.authors,
                task.affiliations,
                text,
            )
            if not single_affiliation_parsed.get("needs_manual_review"):
                parsed = single_affiliation_parsed
        parsed["resolution_id"] = task.resolution_id
        parsed["source_url"] = best.url if best else ""
        parsed_records.append(parsed)

        accepted = accept_resolved_mapping(
            task.resolution_id,
            task.conference,
            task.year,
            task.paper_id,
            task.title,
            task.article_tag,
            best.url if best else "",
            title_similarity(task.title, best.title) if best else 0.0,
            parsed,
        )
        if accepted:
            resolved.extend(accepted)
        else:
            unresolved.append(
                {
                    "resolution_id": task.resolution_id,
                    "conference": task.conference,
                    "year": task.year,
                    "paper_id": task.paper_id,
                    "title": task.title,
                    "reason": parsed.get("reason", "not_accepted"),
                    "best_source_url": best.url if best else "",
                    "best_source_score": best.score if best else 0.0,
                }
            )

        if checkpoint_every > 0 and index % checkpoint_every == 0 and index < len(tasks):
            save_checkpoint(output_dir, resolved, unresolved, parsed_records, all_candidates, total_queue_size)
            print(f"checkpoint saved: {len(resolved)} resolved, {len(unresolved)} unresolved", file=sys.stderr, flush=True)

    save_checkpoint(output_dir, resolved, unresolved, parsed_records, all_candidates, total_queue_size)
    return {
        "tasks": total_queue_size,
        "start": start,
        "end": end,
        "source_candidates": len(all_candidates),
        "resolved_us_rows": len(resolved),
        "unresolved_tasks": len(unresolved),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, default=Path("data/interim/affiliation_resolution_queue.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/resolution"))
    parser.add_argument("--start", type=int, default=0, help="Skip first N tasks in queue")
    parser.add_argument("--limit", type=int, help="Process at most N tasks")
    parser.add_argument("--query-dblp", action="store_true")
    parser.add_argument("--checkpoint-every", type=int, default=25, help="Save checkpoint every N tasks (0 to disable)")
    args = parser.parse_args(argv)

    summary = run_resolution(
        args.queue,
        args.output_dir,
        start=args.start,
        limit=args.limit,
        query_dblp=args.query_dblp,
        checkpoint_every=args.checkpoint_every,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
