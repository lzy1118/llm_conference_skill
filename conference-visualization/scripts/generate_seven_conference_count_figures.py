from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from generate_visualizations import (
    COLORS,
    configure_style,
    display_conference,
    save_figure,
    write_text,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "generated-data" / "conference_year_paper_counts.csv"
DEFAULT_OUTPUT = ROOT / "generated-data" / "visualizations" / "seven_conferences_2020_2025"

CONFERENCES = [
    "ASIACRYPT",
    "CRYPTO",
    "EUROCRYPT",
    "CCS",
    "IEEE_S&P",
    "NDSS",
    "USENIX_SECURITY",
]
YEARS = list(range(2020, 2026))
REQUIRED_COLUMNS = {"year", "conference", "paper_count"}
SERIES_COLORS = ["#4472C4", "#ED7D31", "#70AD47", "#A5A5A5", "#5B9BD5", "#FFC000", "#8064A2"]
SERIES_MARKERS = ["o", "s", "^", "D", "P", "X", "v"]


def read_counts(path: Path) -> dict[tuple[str, int], int]:
    """Read and validate the complete seven-conference by year count matrix."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing_columns = REQUIRED_COLUMNS - columns
        if missing_columns:
            raise ValueError(f"Missing required columns: {sorted(missing_columns)}")

        counts: dict[tuple[str, int], int] = {}
        for line_number, row in enumerate(reader, start=2):
            conference = row["conference"].strip()
            year = int(row["year"])
            paper_count = int(row["paper_count"])
            key = (conference, year)
            if key in counts:
                raise ValueError(f"Duplicate conference-year cell at line {line_number}: {key}")
            if paper_count < 0:
                raise ValueError(f"Negative paper count at line {line_number}: {paper_count}")
            counts[key] = paper_count

    expected = {(conference, year) for conference in CONFERENCES for year in YEARS}
    actual = set(counts)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing or unexpected:
        raise ValueError(f"Incomplete seven-conference matrix; missing={missing}, unexpected={unexpected}")
    return counts


def plot_heatmap(counts: dict[tuple[str, int], int], output_dir: Path) -> list[str]:
    data = np.array([[counts[(conference, year)] for year in YEARS] for conference in CONFERENCES])
    labels = [display_conference(conference) for conference in CONFERENCES]

    fig, ax = plt.subplots(figsize=(11.8, 7.0))
    image = ax.imshow(data, cmap="Blues", aspect="auto")
    ax.set_xticks(range(len(YEARS)), YEARS)
    ax.set_yticks(range(len(labels)), labels)
    ax.set_xlabel("年份")
    ax.set_title("2020-2025年七个顶级会议论文规模分布", pad=12)

    threshold = float(data.max()) * 0.48
    for row_index in range(len(CONFERENCES)):
        for column_index in range(len(YEARS)):
            value = int(data[row_index, column_index])
            ax.text(
                column_index,
                row_index,
                str(value),
                ha="center",
                va="center",
                color="white" if value > threshold else COLORS["black"],
                fontsize=11,
                fontweight="bold",
            )

    colorbar = fig.colorbar(image, ax=ax, fraction=0.032, pad=0.02)
    colorbar.set_label("论文数量")
    fig.tight_layout()
    return save_figure(fig, output_dir, "七大会_conference-year_论文规模热力图")


def plot_conference_trends(counts: dict[tuple[str, int], int], output_dir: Path) -> list[str]:
    fig, ax = plt.subplots(figsize=(12.6, 7.2))
    for index, conference in enumerate(CONFERENCES):
        values = [counts[(conference, year)] for year in YEARS]
        label = display_conference(conference)
        color = SERIES_COLORS[index]
        ax.plot(
            YEARS,
            values,
            color=color,
            marker=SERIES_MARKERS[index],
            linewidth=2.5,
            markersize=7,
            label=label,
            zorder=3,
        )
        ax.text(YEARS[-1] + 0.06, values[-1], f"{label} {values[-1]}", color=color, va="center", fontsize=10)

    ax.set_title("2020-2025年七个顶级会议论文数量趋势", pad=12)
    ax.set_xlabel("年份")
    ax.set_ylabel("论文数量")
    ax.set_xticks(YEARS)
    ax.set_xlim(YEARS[0] - 0.1, YEARS[-1] + 1.0)
    ax.grid(axis="y", zorder=0)
    ax.legend(loc="upper left", ncol=2, frameon=True)
    fig.tight_layout()
    return save_figure(fig, output_dir, "七大会_年度论文数量趋势图")


def plot_cumulative_ranking(counts: dict[tuple[str, int], int], output_dir: Path) -> list[str]:
    totals = {
        conference: sum(counts[(conference, year)] for year in YEARS)
        for conference in CONFERENCES
    }
    ranked = sorted(totals.items(), key=lambda item: (-item[1], display_conference(item[0])))
    labels = [display_conference(conference) for conference, _ in ranked]
    values = [value for _, value in ranked]

    fig, ax = plt.subplots(figsize=(11.5, 6.4))
    y_positions = np.arange(len(labels))
    bars = ax.barh(y_positions, values, color=COLORS["blue"], zorder=3)
    ax.set_yticks(y_positions, labels)
    ax.invert_yaxis()
    ax.set_title("2020-2025年七个顶级会议累计论文规模", pad=12)
    ax.set_xlabel("论文数量")
    ax.grid(axis="x", zorder=0)
    padding = max(values) * 0.015
    for bar, value in zip(bars, values):
        ax.text(value + padding, bar.get_y() + bar.get_height() / 2, f"{value:,}", va="center", fontsize=11)
    ax.set_xlim(0, max(values) * 1.13)
    fig.tight_layout()
    return save_figure(fig, output_dir, "七大会_累计论文规模排名图")


def write_supporting_csv(counts: dict[tuple[str, int], int], output_dir: Path) -> str:
    path = output_dir / "七大会_会议年份论文数_数据.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["conference", "year", "paper_count"])
        writer.writeheader()
        for conference in CONFERENCES:
            for year in YEARS:
                writer.writerow(
                    {
                        "conference": display_conference(conference),
                        "year": year,
                        "paper_count": counts[(conference, year)],
                    }
                )
    return str(path)


def build_showcase(
    counts: dict[tuple[str, int], int],
    input_path: Path,
    output_dir: Path,
    rendered_files: list[str],
) -> str:
    totals_by_year = defaultdict(int)
    totals_by_conference = defaultdict(int)
    for (conference, year), value in counts.items():
        totals_by_year[year] += value
        totals_by_conference[conference] += value
    largest_conference = max(totals_by_conference.items(), key=lambda item: item[1])

    lines = [
        "# 七大会论文规模可视化",
        "",
        f"- 数据源：`{input_path}`",
        f"- 覆盖范围：`{YEARS[0]}-{YEARS[-1]}`，`{len(CONFERENCES)}` 个会议，`{len(counts)}` 个会议-年份单元",
        f"- 论文总量：`{sum(counts.values()):,}`",
        f"- 年度总量：`{totals_by_year[YEARS[0]]:,}`（{YEARS[0]}）至 `{totals_by_year[YEARS[-1]]:,}`（{YEARS[-1]}）",
        f"- 累计规模最大会议：`{display_conference(largest_conference[0])}`（`{largest_conference[1]:,}`）",
        "",
        "## 图表",
        "",
    ]
    lines.extend(f"- `{Path(path).name}`" for path in rendered_files if path.endswith(".svg"))
    lines.extend(["", "## 对应数据", "", "- `七大会_会议年份论文数_数据.csv`", ""])
    showcase_path = output_dir / "visualization_showcase.md"
    write_text(showcase_path, "\n".join(lines))
    return str(showcase_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate seven-conference paper-count visualizations.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Conference-year paper count CSV")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT), help="Visualization output directory")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    configure_style()
    counts = read_counts(input_path)
    rendered_files: list[str] = []
    rendered_files.extend(plot_heatmap(counts, output_dir))
    rendered_files.extend(plot_conference_trends(counts, output_dir))
    rendered_files.extend(plot_cumulative_ranking(counts, output_dir))
    supporting_file = write_supporting_csv(counts, output_dir)
    showcase_file = build_showcase(counts, input_path, output_dir, rendered_files)

    manifest = {
        "input_file": str(input_path),
        "output_dir": str(output_dir),
        "rendered_files": rendered_files,
        "supporting_files": [supporting_file, showcase_file],
        "conferences": CONFERENCES,
        "years": YEARS,
        "conference_year_cells": len(counts),
        "paper_total": sum(counts.values()),
        "missing_sections": ["country", "institution", "author", "collaboration"],
        "mode": "conference_year_counts",
    }
    write_text(output_dir / "visualization_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
