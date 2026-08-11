#!/usr/bin/env python3

"""Batch metadata-only runner for conference collection experiments.

The runner intentionally shells out to ``spider-pdf/run.sh --metadata-only`` so
source discovery, crawler core logic, GROBID, and the cleaning pipeline remain
unchanged.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CRAWLER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = CRAWLER_ROOT.parent
DEFAULT_CONFIG = CRAWLER_ROOT / "configs" / "conferences.yaml"
RUN_SH = CRAWLER_ROOT / "scripts" / "spider-pdf" / "run.sh"
DOWNLOAD_DIR = CRAWLER_ROOT / "scripts" / "download"
METADATA_DIR = DOWNLOAD_DIR / "metadata"
DEFAULT_REPORT = METADATA_DIR / "batch_metadata_report.json"
DEFAULT_MANIFEST = METADATA_DIR / "conference_collection_manifest.csv"
SKIP_TERMS = ("workshop", "demo", "companion")


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value.startswith("[") and value.endswith("]"):
        return [item.strip().strip("'\"") for item in value[1:-1].split(",") if item.strip()]
    try:
        return int(value)
    except ValueError:
        return value.strip("'\"")


def load_conference_config(path: Path) -> dict[str, dict[str, Any]]:
    """Load the small YAML subset used by configs/conferences.yaml."""
    conferences: dict[str, dict[str, Any]] = {}
    in_conferences = False
    current: str | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line == "conferences:":
            in_conferences = True
            continue
        if not in_conferences:
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = line.strip()
        if indent == 2 and stripped.endswith(":"):
            current = stripped[:-1]
            conferences[current] = {}
            continue
        if indent == 4 and current and ":" in stripped:
            key, value = stripped.split(":", 1)
            conferences[current][key.strip()] = _parse_scalar(value)

    if not conferences:
        raise ValueError(f"No conferences found in config: {path}")
    return conferences


def parse_conferences(value: str, config: dict[str, dict[str, Any]]) -> list[str]:
    if value == "all":
        return list(config.keys())
    conferences = [item.strip() for item in value.split(",") if item.strip()]
    unknown = [item for item in conferences if item not in config]
    if unknown:
        raise ValueError(f"Unsupported conferences: {', '.join(unknown)}")
    return conferences


def parse_years(value: str) -> list[int]:
    years: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if end < start:
                raise ValueError(f"Invalid year range: {part}")
            years.extend(range(start, end + 1))
        else:
            years.append(int(part))
    if not years:
        raise ValueError("At least one year is required")
    return sorted(set(years))


def _read_summary(summary_csv: str) -> tuple[int, int, int, bool]:
    summary_path = DOWNLOAD_DIR / summary_csv
    if not summary_path.exists():
        return 0, 0, 1, False
    with open(summary_path, encoding="utf-8-sig", newline="") as file_obj:
        rows = list(csv.DictReader(file_obj))
    url_count = len(rows)
    paper_count = sum(int(row.get("total") or 0) for row in rows)
    error_count = sum(int(row.get("error") or 0) for row in rows)
    has_skip_terms = any(
        any(term in (row.get("url", "").lower()) for term in SKIP_TERMS)
        for row in rows
    )
    return url_count, paper_count, error_count, has_skip_terms


def _run_metadata_only(conference: str, year: int) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HTTPS_PROXY"] = ""
    env["HTTP_PROXY"] = ""
    env["ALL_PROXY"] = ""
    command = [str(RUN_SH), conference, "--years", str(year), "--metadata-only"]
    return subprocess.run(command, cwd=REPO_ROOT, env=env, text=True, capture_output=True)


def write_report(report: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_obj:
        json.dump(report, file_obj, ensure_ascii=False, indent=2)
        file_obj.write("\n")


def write_collection_manifest(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "conference",
        "year",
        "source",
        "backend",
        "discovery_urls",
        "paper_count",
        "status",
        "contains_workshop_demo_companion",
        "summary_csv",
        "report_json",
        "started_at",
        "finished_at",
    ]
    with open(path, "w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def main() -> None:
    parser = argparse.ArgumentParser(description="Run metadata-only conference collection experiments.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Conference YAML config path.")
    parser.add_argument("--conferences", default="all", help="Comma-separated conferences or 'all'.")
    parser.add_argument("--years", required=True, help="Year list/range, e.g. 2024 or 2024-2025.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="Output metadata-only JSON report.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Output collection manifest CSV.")
    args = parser.parse_args()

    config = load_conference_config(Path(args.config).expanduser().resolve())
    conferences = parse_conferences(args.conferences, config)
    years = parse_years(args.years)
    report_path = Path(args.report).expanduser().resolve()
    manifest_path = Path(args.manifest).expanduser().resolve()

    report: list[dict[str, Any]] = []
    manifest_rows: list[dict[str, Any]] = []
    failures = 0

    for conference in conferences:
        conf_config = config[conference]
        for year in years:
            started_at = datetime.now(timezone.utc).isoformat()
            print(f"[BATCH] metadata-only conference={conference} year={year}")
            result = _run_metadata_only(conference, year)
            if result.stdout:
                print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)

            url_count, paper_count, error_count, has_skip_terms = _read_summary(str(conf_config["summary"]))
            status = "PASS" if result.returncode == 0 and error_count == 0 and not has_skip_terms else "FAIL"
            if status != "PASS":
                failures += 1
            finished_at = datetime.now(timezone.utc).isoformat()
            row = {
                "conference": conference,
                "year": year,
                "source": conf_config["source"],
                "backend": conf_config["backend"],
                "urls": url_count,
                "discovery_urls": url_count,
                "papers": paper_count,
                "paper_count": paper_count,
                "status": status,
                "contains_workshop_demo_companion": has_skip_terms,
                "summary_csv": conf_config["summary"],
                "report_json": str(report_path),
                "started_at": started_at,
                "finished_at": finished_at,
            }
            report.append(
                {
                    "conference": conference,
                    "year": year,
                    "source": conf_config["source"],
                    "backend": conf_config["backend"],
                    "urls": url_count,
                    "papers": paper_count,
                    "status": status,
                    "contains_workshop_demo_companion": has_skip_terms,
                }
            )
            manifest_rows.append(row)

    write_report(report, report_path)
    write_collection_manifest(manifest_rows, manifest_path)
    print(f"[BATCH] wrote report: {report_path}")
    print(f"[BATCH] wrote collection manifest: {manifest_path}")

    if failures:
        raise SystemExit(failures)


if __name__ == "__main__":
    main()
