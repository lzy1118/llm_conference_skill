#!/usr/bin/env python3

"""Run source-discovery metadata-only smoke tests for supported conferences.

This intentionally tests only the four validated conference/year pairs:
CRYPTO 2024, WWW 2025, NeurIPS 2024, and ICML 2025.
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RUN_SH = ROOT / "conference-crawler" / "scripts" / "spider-pdf" / "run.sh"
DOWNLOAD_DIR = ROOT / "conference-crawler" / "scripts" / "download"
REPORT_PATH = DOWNLOAD_DIR / "metadata" / "discovery_test_report.json"

CASES = [
    ("crypto", "2024", "dblp", "summary_crypto.csv"),
    ("www", "2025", "acm", "summary_www.csv"),
    ("neurips", "2024", "neurips", "summary_neurips.csv"),
    ("icml", "2025", "pmlr", "summary_icml.csv"),
]


def _read_summary(summary_csv: str) -> tuple[int, int, int]:
    summary_path = DOWNLOAD_DIR / summary_csv
    with open(summary_path, encoding="utf-8-sig", newline="") as file_obj:
        rows = list(csv.DictReader(file_obj))
    paper_count = sum(int(row.get("total") or 0) for row in rows)
    error_count = sum(int(row.get("error") or 0) for row in rows)
    return len(rows), paper_count, error_count


def _has_discovery_terms(summary_csv: str) -> bool:
    summary_path = DOWNLOAD_DIR / summary_csv
    with open(summary_path, encoding="utf-8-sig", newline="") as file_obj:
        rows = list(csv.DictReader(file_obj))
    terms = ("workshop", "demo", "companion")
    return any(any(term in (row.get("url", "").lower()) for term in terms) for row in rows)


def main() -> None:
    env = os.environ.copy()
    env["HTTPS_PROXY"] = ""
    env["HTTP_PROXY"] = ""
    env["ALL_PROXY"] = ""

    failures = 0
    report: list[dict[str, object]] = []
    for conference, year, backend, summary_csv in CASES:
        print(f"[SOURCE_DISCOVERY] test conference={conference} year={year}")
        command = [str(RUN_SH), conference, "--years", year, "--metadata-only"]
        result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        if result.returncode != 0:
            failures += 1
            print(f"[CRAWLER] test failed conference={conference} returncode={result.returncode}")
            report.append(
                {
                    "conference": conference,
                    "year": int(year),
                    "backend": backend,
                    "urls": 0,
                    "papers": 0,
                    "status": "FAIL",
                }
            )
            continue
        url_count, paper_count, error_count = _read_summary(summary_csv)
        has_discovery_terms = _has_discovery_terms(summary_csv)
        status = "PASS" if error_count == 0 and not has_discovery_terms else "FAIL"
        print(
            "[CRAWLER] test summary "
            f"conference={conference} year={year} "
            f"discovery_urls={url_count} papers={paper_count} errors={error_count}"
        )
        report.append(
            {
                "conference": conference,
                "year": int(year),
                "backend": backend,
                "urls": url_count,
                "papers": paper_count,
                "status": status,
                "contains_workshop_demo_companion": has_discovery_terms,
            }
        )
        if status != "PASS":
            failures += 1

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as file_obj:
        json.dump(report, file_obj, ensure_ascii=False, indent=2)
        file_obj.write("\n")
    print(f"[CRAWLER] wrote report: {REPORT_PATH}")

    if failures:
        raise SystemExit(failures)


if __name__ == "__main__":
    main()
