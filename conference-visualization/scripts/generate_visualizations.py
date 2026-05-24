from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path


SECTION_FILES = {
    "country": Path("country/country_summary.csv"),
    "institution": Path("institutions/institution_summary.csv"),
    "author": Path("authors/author_summary.csv"),
    "trend": Path("trends/trend_by_entity_year.csv"),
    "collaboration": Path("collaboration/collaboration_edges.csv"),
}

DEFAULT_OUTPUT_DIR = Path("generated-data") / "visualizations"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def detect_sections(analysis_dir: Path) -> tuple[dict[str, Path], list[str]]:
    included: dict[str, Path] = {}
    missing: list[str] = []
    for section, relative_path in SECTION_FILES.items():
        candidate = analysis_dir / relative_path
        if candidate.exists():
            included[section] = candidate
        else:
            missing.append(section)
    return included, missing


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def bar_chart_svg(title: str, labels: list[str], values: list[float], value_suffix: str = "") -> str:
    width = 960
    top = 70
    left = 220
    bar_height = 28
    bar_gap = 18
    chart_width = 620
    rows = max(len(labels), 1)
    height = top + rows * (bar_height + bar_gap) + 60
    max_value = max(values) if values else 1.0
    max_value = max(max_value, 1.0)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="40" y="40" font-size="24" font-family="Arial, Helvetica, sans-serif" font-weight="700">{escape(title)}</text>',
    ]

    for index, (label, value) in enumerate(zip(labels, values)):
        y = top + index * (bar_height + bar_gap)
        bar_width = 0 if max_value == 0 else chart_width * (float(value) / max_value)
        parts.append(f'<text x="40" y="{y + 19}" font-size="14" font-family="Arial, Helvetica, sans-serif">{escape(label)}</text>')
        parts.append(f'<rect x="{left}" y="{y}" width="{chart_width}" height="{bar_height}" rx="4" fill="#edf2f7"/>')
        parts.append(f'<rect x="{left}" y="{y}" width="{bar_width:.2f}" height="{bar_height}" rx="4" fill="#2563eb"/>')
        parts.append(f'<text x="{left + bar_width + 10:.2f}" y="{y + 19}" font-size="13" font-family="Arial, Helvetica, sans-serif" fill="#111827">{escape(f"{value}{value_suffix}")}</text>')

    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def line_chart_svg(title: str, series_by_name: dict[str, list[tuple[str, float]]]) -> str:
    width = 960
    height = 520
    margin_left = 80
    margin_right = 40
    margin_top = 70
    margin_bottom = 70
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom

    all_years = sorted({year for points in series_by_name.values() for year, _ in points})
    year_positions = {year: index for index, year in enumerate(all_years)}
    all_values = [value for points in series_by_name.values() for _, value in points]
    max_value = max(all_values) if all_values else 1.0
    max_value = max(max_value, 1.0)
    x_steps = max(len(all_years) - 1, 1)
    colors = ["#2563eb", "#dc2626", "#16a34a", "#7c3aed", "#ea580c"]

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="40" y="40" font-size="24" font-family="Arial, Helvetica, sans-serif" font-weight="700">{escape(title)}</text>',
        f'<line x1="{margin_left}" y1="{margin_top + plot_height}" x2="{margin_left + plot_width}" y2="{margin_top + plot_height}" stroke="#111827" stroke-width="2"/>',
        f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_height}" stroke="#111827" stroke-width="2"/>',
    ]

    for year in all_years:
        x = margin_left + plot_width * (year_positions[year] / x_steps)
        parts.append(f'<line x1="{x:.2f}" y1="{margin_top}" x2="{x:.2f}" y2="{margin_top + plot_height}" stroke="#e5e7eb" stroke-width="1"/>')
        parts.append(f'<text x="{x:.2f}" y="{margin_top + plot_height + 24}" text-anchor="middle" font-size="13" font-family="Arial, Helvetica, sans-serif">{escape(year)}</text>')

    for tick in range(6):
        value = max_value * tick / 5
        y = margin_top + plot_height - plot_height * (value / max_value)
        parts.append(f'<line x1="{margin_left}" y1="{y:.2f}" x2="{margin_left + plot_width}" y2="{y:.2f}" stroke="#e5e7eb" stroke-width="1"/>')
        parts.append(f'<text x="{margin_left - 12}" y="{y + 4:.2f}" text-anchor="end" font-size="12" font-family="Arial, Helvetica, sans-serif">{escape(round(value, 1))}</text>')

    for index, (name, points) in enumerate(series_by_name.items()):
        color = colors[index % len(colors)]
        ordered = sorted(points, key=lambda item: item[0])
        coordinates: list[tuple[float, float]] = []
        for year, value in ordered:
            x = margin_left + plot_width * (year_positions[year] / x_steps)
            y = margin_top + plot_height - plot_height * (float(value) / max_value)
            coordinates.append((x, y))
        polyline = " ".join(f"{x:.2f},{y:.2f}" for x, y in coordinates)
        parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="3" points="{polyline}"/>')
        for x, y in coordinates:
            parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="{color}"/>')
        legend_y = margin_top + 18 + index * 22
        parts.append(f'<rect x="{width - 220}" y="{legend_y - 10}" width="14" height="14" fill="{color}" rx="2"/>')
        parts.append(f'<text x="{width - 198}" y="{legend_y + 2}" font-size="13" font-family="Arial, Helvetica, sans-serif">{escape(name)}</text>')

    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def build_country_chart(rows: list[dict[str, str]], output_dir: Path, top_n: int) -> str:
    top_rows = rows[:top_n]
    labels = [row.get("country", "Unknown") for row in top_rows]
    values = [float(row.get("papers", "0") or "0") for row in top_rows]
    path = output_dir / "country_top_papers.svg"
    write_text(path, bar_chart_svg("Top Countries By Papers", labels, values))
    return str(path)


def build_institution_chart(rows: list[dict[str, str]], output_dir: Path, top_n: int) -> str:
    top_rows = rows[:top_n]
    labels = [row.get("institution_name", "Unknown") for row in top_rows]
    values = [float(row.get("papers", "0") or "0") for row in top_rows]
    path = output_dir / "institution_top_papers.svg"
    write_text(path, bar_chart_svg("Top Institutions By Papers", labels, values))
    return str(path)


def build_author_chart(rows: list[dict[str, str]], output_dir: Path, top_n: int) -> str:
    top_rows = rows[:top_n]
    labels = [row.get("author_name", "Unknown") for row in top_rows]
    values = [float(row.get("papers", "0") or "0") for row in top_rows]
    path = output_dir / "author_top_papers.svg"
    write_text(path, bar_chart_svg("Top Authors By Papers", labels, values))
    return str(path)


def build_trend_chart(rows: list[dict[str, str]], output_dir: Path, top_n: int) -> str:
    series_names = []
    for row in rows:
        name = row.get("entity_name", "Unknown")
        if name not in series_names:
            series_names.append(name)
    selected = series_names[:top_n]
    series_by_name: dict[str, list[tuple[str, float]]] = {name: [] for name in selected}
    for row in rows:
        name = row.get("entity_name", "Unknown")
        if name not in series_by_name:
            continue
        series_by_name[name].append((row.get("year", ""), float(row.get("papers", "0") or "0")))
    path = output_dir / "trend_entity_year.svg"
    write_text(path, line_chart_svg("Trend By Entity And Year", series_by_name))
    return str(path)


def build_collaboration_chart(rows: list[dict[str, str]], output_dir: Path, top_n: int) -> str:
    top_rows = rows[:top_n]
    labels = [f"{row.get('left_name', 'Unknown')} <-> {row.get('right_name', 'Unknown')}" for row in top_rows]
    values = [float(row.get("shared_papers", "0") or "0") for row in top_rows]
    path = output_dir / "collaboration_top_edges.svg"
    write_text(path, bar_chart_svg("Top Collaboration Edges By Shared Papers", labels, values))
    return str(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SVG visualizations from conference analysis outputs.")
    parser.add_argument("--analysis-dir", required=True, help="Root analysis directory containing section subdirectories")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory for generated visualizations")
    parser.add_argument("--top-n", type=int, default=8, help="Number of items or series to visualize")
    args = parser.parse_args()

    analysis_dir = Path(args.analysis_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    included_paths, missing_sections = detect_sections(analysis_dir)
    if not included_paths:
        raise SystemExit("No supported analysis outputs found")

    rendered_files: list[str] = []
    empty_sections: list[str] = []
    for section, path in included_paths.items():
        rows = read_csv_rows(path)
        if not rows:
            empty_sections.append(section)
            continue
        if section == "country":
            rendered_files.append(build_country_chart(rows, output_dir, args.top_n))
        elif section == "institution":
            rendered_files.append(build_institution_chart(rows, output_dir, args.top_n))
        elif section == "author":
            rendered_files.append(build_author_chart(rows, output_dir, args.top_n))
        elif section == "trend":
            rendered_files.append(build_trend_chart(rows, output_dir, args.top_n))
        elif section == "collaboration":
            rendered_files.append(build_collaboration_chart(rows, output_dir, args.top_n))

    manifest = {
        "analysis_dir": str(analysis_dir),
        "rendered_files": rendered_files,
        "missing_sections": missing_sections,
        "empty_sections": empty_sections,
        "top_n": args.top_n,
    }
    write_text(output_dir / "visualization_manifest.json", json.dumps(manifest, indent=2, ensure_ascii=True) + "\n")


if __name__ == "__main__":
    main()
