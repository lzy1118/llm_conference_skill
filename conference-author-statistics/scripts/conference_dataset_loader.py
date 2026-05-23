from __future__ import annotations

import csv
from pathlib import Path


def load_normalized_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def filter_rows(rows: list[dict[str, str]], conference: str | None, year: str | None) -> list[dict[str, str]]:
    filtered = rows
    if conference:
        filtered = [row for row in filtered if row.get("conference") == conference]
    if year:
        filtered = [row for row in filtered if row.get("year") == str(year)]
    return filtered


def write_summary_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown_report(path: Path, title: str, scope: dict[str, object], highlights: list[dict[str, object]]) -> None:
    lines = [f"# {title}", "", "## Scope", ""]
    for key, value in scope.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Highlights", ""])
    if not highlights:
        lines.append("No rows matched the selected filters.")
    else:
        for row in highlights:
            lines.append(f"- {row.get('author_name', 'item')}: {row}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
