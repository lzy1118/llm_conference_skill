from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def normalize_author_display_name(name: str) -> str:
    import re
    text = (name or "").strip()
    if not text:
        return ""
    return re.sub(r"\s0+\d+$", "", text).strip()


SECTION_FILES = {
    "country": Path("country/country_summary.csv"),
    "institution": Path("institutions/institution_summary.csv"),
    "author": Path("authors/author_summary.csv"),
    "trend": Path("trends/trend_summary.csv"),
    "collaboration": Path("collaboration/collaboration_edges.csv"),
}

DEFAULT_OUTPUT_DIR = Path("generated-data") / "reports"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def top_rows(rows: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    return rows[:limit]


def detect_sections(analysis_dir: Path) -> tuple[dict[str, Path], list[str]]:
    included: dict[str, Path] = {}
    missing: list[str] = []
    for name, relative_path in SECTION_FILES.items():
        path = analysis_dir / relative_path
        if path.exists():
            included[name] = path
        else:
            missing.append(name)
    return included, missing


def build_markdown(analysis_dir: Path, data: dict[str, list[dict[str, str]]], missing: list[str], limit: int) -> str:
    lines = [
        "# Conference Analysis Report",
        "",
        "## Overview",
        "",
        f"- analysis_dir: {analysis_dir}",
        f"- included_sections: {', '.join(data.keys()) or 'none'}",
        f"- missing_sections: {', '.join(missing) or 'none'}",
    ]
    section_titles = {
        "country": "Top Countries",
        "institution": "Top Institutions",
        "author": "Top Authors",
        "trend": "Trend Highlights",
        "collaboration": "Collaboration Highlights",
    }
    label_fields = {
        "country": "country",
        "institution": "institution_name",
        "author": "author_name",
        "trend": "entity_name",
        "collaboration": "left_name",
    }
    metric_fields = {
        "country": "papers",
        "institution": "papers",
        "author": "papers",
        "trend": "papers_peak",
        "collaboration": "shared_papers",
    }
    for section, rows in data.items():
        lines.extend(["", f"## {section_titles[section]}", ""])
        for row in top_rows(rows, limit):
            label = row.get(label_fields[section], "item")
            if section == "collaboration":
                label = normalize_author_display_name(label)
                right_name = normalize_author_display_name(row.get("right_name", "item"))
                lines.append(f"- {label} <-> {right_name}: {metric_fields[section]}={row.get(metric_fields[section], '')}")
            else:
                if section == "author":
                    label = normalize_author_display_name(label)
                lines.append(f"- {label}: {metric_fields[section]}={row.get(metric_fields[section], '')}")
        if not rows:
            lines.append("- No rows available.")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a Markdown report from conference analysis outputs.")
    parser.add_argument("--analysis-dir", required=True, help="Root analysis directory containing section subdirectories")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory for generated reports")
    parser.add_argument("--top-n", type=int, default=5, help="Number of headline rows per section")
    args = parser.parse_args()

    analysis_dir = Path(args.analysis_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    included_paths, missing = detect_sections(analysis_dir)
    if not included_paths:
        raise SystemExit("No supported analysis outputs found")

    data = {section: read_csv_rows(path) for section, path in included_paths.items()}
    metadata = {
        "analysis_dir": str(analysis_dir),
        "included_sections": list(included_paths.keys()),
        "missing_sections": missing,
        "section_counts": {section: len(rows) for section, rows in data.items()},
    }
    (output_dir / "conference_report.md").write_text(
        build_markdown(analysis_dir, data, missing, args.top_n),
        encoding="utf-8",
    )
    (output_dir / "conference_report.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
