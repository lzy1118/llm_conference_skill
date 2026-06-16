from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from security_real_backend import CONFERENCES, extract_doi_from_url, resolve_pdf_url  # noqa: E402


def load_problem_rows(output_dir: Path, conference_key: str) -> list[dict[str, str]]:
    path = output_dir / "interim" / "by_conference" / conference_key / "affiliation_resolution_queue.csv"
    if not path.exists():
        return []
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    return [
        row for row in rows
        if row.get("issue") in {
            "no_affiliation_data",
            "partial_author_affiliation_coverage",
            "author_affiliation_match_failed",
        }
    ]


def load_papers(output_dir: Path, conference_key: str) -> dict[str, dict]:
    path = output_dir / "raw" / "by_conference" / conference_key / "papers.json"
    if not path.exists():
        return {}
    papers = json.loads(path.read_text(encoding="utf-8"))
    return {paper["paperId"]: paper for paper in papers}


def build_manifest_rows(output_dir: Path, conference_keys: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for conference_key in conference_keys:
        config = CONFERENCES[conference_key]
        problem_rows = load_problem_rows(output_dir, conference_key)
        papers = load_papers(output_dir, conference_key)
        for issue_row in problem_rows:
            paper = papers.get(issue_row["paper_id"])
            if not paper:
                continue
            url = str(paper.get("url", "")).strip()
            doi = extract_doi_from_url(url)
            pdf_url = ""
            pdf_source = ""
            pdf_status = "no_pdf_url"
            try:
                pdf_url, pdf_source = resolve_pdf_url(config, paper)
            except Exception as exc:
                pdf_status = f"resolve_error: {exc}"
            else:
                if pdf_url:
                    pdf_status = "pdf_url_found"
            rows.append({
                "conference": config.conference,
                "year": str(config.year),
                "conference_key": conference_key,
                "paper_id": issue_row.get("paper_id", ""),
                "title": issue_row.get("title", ""),
                "issue": issue_row.get("issue", ""),
                "authors_count": issue_row.get("authors_count", ""),
                "affiliations_count": issue_row.get("affiliations_count", ""),
                "authors": issue_row.get("authors", ""),
                "affiliations": issue_row.get("affiliations", ""),
                "doi": doi,
                "url": url,
                "pdf_status": pdf_status,
                "pdf_source": pdf_source,
                "pdf_url": pdf_url,
                "pdf_path": "",
            })
    return rows


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    output_dir = Path(argv[0]) if argv else Path("generated-data/extraction")
    conference_keys = [key for key in CONFERENCES if key.startswith("ccs_") and key.split("_")[-1].isdigit() and 2020 <= int(key.split("_")[-1]) <= 2025]
    rows = build_manifest_rows(output_dir, sorted(conference_keys))
    out_dir = output_dir / "manifests"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "problem_paper_pdf_manifest.csv"
    json_path = out_dir / "problem_paper_pdf_manifest.json"
    fieldnames = [
        "conference", "year", "conference_key", "paper_id", "title", "issue",
        "authors_count", "affiliations_count", "authors", "affiliations",
        "doi", "url", "pdf_status", "pdf_source", "pdf_url", "pdf_path",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "rows": len(rows),
        "csv_path": str(csv_path),
        "json_path": str(json_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
