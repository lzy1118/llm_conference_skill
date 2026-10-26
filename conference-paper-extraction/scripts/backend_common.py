from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

try:
    from openpyxl import Workbook
except ImportError:
    Workbook = None


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_workbook(path: Path, rows: list[dict[str, Any]], header: list[str]) -> None:
    if Workbook is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "英文版"
    sheet.append(header)
    for row in rows:
        sheet.append([row.get(column, "") for column in header])
    workbook.save(path)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def slug_path_part(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "unknown"


def conference_output_dir(root: Path, conference_key: str) -> Path:
    return root / "output" / "by_conference" / conference_key


def conference_interim_dir(root: Path, conference_key: str) -> Path:
    return root / "interim" / "by_conference" / conference_key


def summary_output_dir(root: Path, summary_key: str) -> Path:
    return root / "output" / "summaries" / summary_key


def summary_interim_dir(root: Path, summary_key: str) -> Path:
    return root / "interim" / "summaries" / summary_key


def conference_raw_dir(root: Path, conference_key: str) -> Path:
    return root / "raw" / "by_conference" / conference_key


def conference_pdf_dir(root: Path, conference_key: str) -> Path:
    return root / "pdfs" / "by_conference" / conference_key
