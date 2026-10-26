from __future__ import annotations

import argparse
import csv
import html
import json
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "generated-data" / "visualizations"
SECURITY_INPUT_CSV = ROOT / "Graph" / "data" / "2020-2025四大安全会议中美全球论文统计数据.csv"
CRYPTO_DATA_DIR = ROOT / "Graph" / "data"

FONT_FAMILY = '"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC",Arial,sans-serif'
COLORS = {
    "bg": "#fbfaf7",
    "ink": "#1f2933",
    "muted": "#667085",
    "grid": "#d7dde8",
    "global": "#334e68",
    "china": "#c2410c",
    "us": "#2563eb",
    "china_light": "#f7d8ca",
    "us_light": "#d9e7ff",
    "panel": "#ffffff",
}


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    prefix: str
    title: str
    conferences: tuple[str, ...]
    conference_colors: dict[str, str]


SPECS = {
    "crypto": DatasetSpec(
        key="crypto",
        prefix="三大密码会",
        title="三大密码会（CRYPTO/EUROCRYPT/ASIACRYPT）",
        conferences=("CRYPTO", "EUROCRYPT", "ASIACRYPT"),
        conference_colors={"CRYPTO": "#2166AC", "EUROCRYPT": "#B2182B", "ASIACRYPT": "#4DAF4A"},
    ),
    "security": DatasetSpec(
        key="security",
        prefix="四大安全会",
        title="四大安全会（CCS/IEEE S&P/NDSS/USENIX Security）",
        conferences=("CCS", "IEEE S&P", "NDSS", "USENIX Security"),
        conference_colors={"CCS": "#2166AC", "IEEE S&P": "#B2182B", "NDSS": "#4DAF4A", "USENIX Security": "#7B3294"},
    ),
}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_security_rows(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = []
        for row in csv.DictReader(handle):
            rows.append(
                {
                    "会议": row["会议"],
                    "年份": int(row["年份"]),
                    "全球论文数": int(row["全球论文数"]),
                    "中国论文数": int(row["中国论文数"]),
                    "美国论文数": int(row["美国论文数"]),
                    "中国占比": float(row["中国占比"]),
                    "美国占比": float(row["美国占比"]),
                }
            )
        return rows


def read_crypto_rows(data_dir: Path) -> list[dict[str, object]]:
    global_counts: dict[tuple[str, int], int] = {}
    with (data_dir / "三大密码会_全球_20-25.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            global_counts[(row["conference"], int(row["year"]))] = int(row["paper_count"])

    def count_unique_papers(filename: str) -> dict[tuple[str, int], int]:
        paper_ids: dict[tuple[str, int], set[str]] = defaultdict(set)
        with (data_dir / filename).open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                article_tag = row["article_tag"]
                conference = article_tag.split("-", 1)[0]
                if conference == "Eurocrypt":
                    conference = "EUROCRYPT"
                paper_ids[(conference, int(row["year"]))].add(article_tag)
        return {key: len(value) for key, value in paper_ids.items()}

    china_counts = count_unique_papers("三大密码会_中国机构_20-25.csv")
    us_counts = count_unique_papers("三大密码会_美国机构_20-25.csv")
    rows = []
    for conference in SPECS["crypto"].conferences:
        for year in range(2020, 2026):
            global_papers = global_counts.get((conference, year), 0)
            china_papers = china_counts.get((conference, year), 0)
            us_papers = us_counts.get((conference, year), 0)
            rows.append(
                {
                    "会议": conference,
                    "年份": year,
                    "全球论文数": global_papers,
                    "中国论文数": china_papers,
                    "美国论文数": us_papers,
                    "中国占比": china_papers / global_papers if global_papers else 0.0,
                    "美国占比": us_papers / global_papers if global_papers else 0.0,
                }
            )
    return rows


def write_text(path: Path, text: str) -> str:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")
    return str(path)


def svg_header(width: int, height: int) -> list[str]:
    return [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="{COLORS["bg"]}"/>',
        "<style>"
        f"text{{font-family:{FONT_FAMILY};fill:{COLORS['ink']};}}"
        ".title{font-size:30px;font-weight:700;}"
        ".subtitle{font-size:15px;fill:#667085;}"
        ".axis{font-size:12px;fill:#667085;}"
        ".label{font-size:14px;}"
        ".small{font-size:12px;fill:#667085;}"
        ".legend{font-size:13px;}"
        "</style>",
    ]


def svg_footer(parts: list[str]) -> str:
    return "\n".join(parts + ["</svg>"]) + "\n"


def text(parts: list[str], x: float, y: float, value: object, klass: str = "label", color: str | None = None, anchor: str | None = None) -> None:
    attrs = [f'x="{x}"', f'y="{y}"', f'class="{klass}"']
    if color:
        attrs.append(f'fill="{color}"')
    if anchor:
        attrs.append(f'text-anchor="{anchor}"')
    parts.append(f'<text {" ".join(attrs)}>{html.escape(str(value))}</text>')


def line(parts: list[str], x1: float, y1: float, x2: float, y2: float, color: str, width: float = 1.0, dash: str | None = None) -> None:
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}"{dash_attr}/>' )


def path_line(points: list[tuple[float, float]]) -> str:
    return "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in points)


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def aggregate(rows: list[dict[str, object]]) -> dict[str, object]:
    by_year = defaultdict(lambda: {"全球论文数": 0, "中国论文数": 0, "美国论文数": 0})
    by_conf = defaultdict(lambda: {"全球论文数": 0, "中国论文数": 0, "美国论文数": 0})
    for row in rows:
        year = int(row["年份"])
        conf = str(row["会议"])
        for key in ["全球论文数", "中国论文数", "美国论文数"]:
            by_year[year][key] += int(row[key])
            by_conf[conf][key] += int(row[key])
    return {
        "years": sorted(by_year),
        "conferences": sorted(by_conf),
        "by_year": dict(by_year),
        "by_conf": dict(by_conf),
    }


def figure_yearly_trend(rows: list[dict[str, object]], output_dir: Path) -> str:
    metrics = aggregate(rows)
    years = metrics["years"]
    by_year = metrics["by_year"]
    width, height = 1320, 760
    left, top, chart_w, chart_h = 120, 150, 1060, 450
    max_value = max(by_year[year]["全球论文数"] for year in years)
    y_max = ((max_value + 199) // 200) * 200

    def x_pos(year: int) -> float:
        return left + years.index(year) * chart_w / (len(years) - 1)

    def y_pos(value: int) -> float:
        return top + chart_h - value * chart_h / y_max

    parts = svg_header(width, height)
    text(parts, 70, 62, "2020-2025 四大安全会议论文规模趋势", "title")
    text(parts, 70, 96, "按年份汇总 CCS、IEEE S&P、NDSS、USENIX Security 的全球、中国、美国论文数。", "subtitle")
    parts.append(f'<rect x="{left - 55}" y="{top - 35}" width="{chart_w + 110}" height="{chart_h + 95}" rx="14" fill="{COLORS["panel"]}" stroke="{COLORS["grid"]}"/>')

    for tick in range(0, y_max + 1, 200):
        y = y_pos(tick)
        line(parts, left, y, left + chart_w, y, COLORS["grid"], 1, "4 5" if tick else None)
        text(parts, left - 18, y + 4, tick, "axis", anchor="end")
    for year in years:
        x = x_pos(year)
        line(parts, x, top, x, top + chart_h, COLORS["grid"], 0.8, "3 7")
        text(parts, x, top + chart_h + 34, year, "axis", anchor="middle")

    series = [
        ("全球论文数", "全球", COLORS["global"]),
        ("中国论文数", "中国", COLORS["china"]),
        ("美国论文数", "美国", COLORS["us"]),
    ]
    for key, label, color in series:
        points = [(x_pos(year), y_pos(by_year[year][key])) for year in years]
        parts.append(f'<path d="{path_line(points)}" fill="none" stroke="{color}" stroke-width="4" stroke-linejoin="round"/>')
        for year, (x, y) in zip(years, points):
            parts.append(f'<circle cx="{x}" cy="{y}" r="5.5" fill="{color}"/>')
            text(parts, x, y - 12, by_year[year][key], "small", color, "middle")

    legend_x = 835
    for idx, (_, label, color) in enumerate(series):
        x = legend_x + idx * 125
        parts.append(f'<rect x="{x}" y="82" width="18" height="18" rx="4" fill="{color}"/>')
        text(parts, x + 28, 96, label, "legend")
    text(parts, left + chart_w / 2, height - 45, "数据来源：2020-2025四大安全会议中美全球论文统计数据.csv", "small", anchor="middle")

    return write_text(output_dir / "四大安全会_发文数量_曲线图.svg", svg_footer(parts))


def figure_yearly_grouped_bar(rows: list[dict[str, object]], output_dir: Path) -> str:
    metrics = aggregate(rows)
    years = metrics["years"]
    by_year = metrics["by_year"]
    width, height = 1320, 760
    left, top, chart_w, chart_h = 120, 150, 1060, 450
    max_value = max(by_year[year]["全球论文数"] for year in years)
    y_max = ((max_value + 199) // 200) * 200
    group_w, bar_w = chart_w / len(years), 38

    def y_pos(value: int) -> float:
        return top + chart_h - value * chart_h / y_max

    parts = svg_header(width, height)
    text(parts, 70, 62, "2020-2025 四大安全会议年度发文数量", "title")
    text(parts, 70, 96, "每年分别比较全球、中国、美国的论文数量；数值为四个会议的年度合计。", "subtitle")
    parts.append(f'<rect x="{left - 55}" y="{top - 35}" width="{chart_w + 110}" height="{chart_h + 95}" rx="14" fill="{COLORS["panel"]}" stroke="{COLORS["grid"]}"/>')
    for tick in range(0, y_max + 1, 200):
        y = y_pos(tick)
        line(parts, left, y, left + chart_w, y, COLORS["grid"], 1, "4 5" if tick else None)
        text(parts, left - 18, y + 4, tick, "axis", anchor="end")

    series = [("全球论文数", "全球", COLORS["global"]), ("中国论文数", "中国", COLORS["china"]), ("美国论文数", "美国", COLORS["us"])]
    for idx, (_, label, color) in enumerate(series):
        x = 825 + idx * 120
        parts.append(f'<rect x="{x}" y="82" width="18" height="18" rx="4" fill="{color}"/>')
        text(parts, x + 28, 96, label, "legend")

    for year_idx, year in enumerate(years):
        center = left + group_w * (year_idx + 0.5)
        text(parts, center, top + chart_h + 34, year, "axis", anchor="middle")
        for series_idx, (key, _, color) in enumerate(series):
            value = by_year[year][key]
            bar_x = center + (series_idx - 1) * (bar_w + 8) - bar_w / 2
            bar_y = y_pos(value)
            bar_h = top + chart_h - bar_y
            parts.append(f'<rect x="{bar_x:.1f}" y="{bar_y:.1f}" width="{bar_w}" height="{bar_h:.1f}" rx="4" fill="{color}"/>')
            text(parts, bar_x + bar_w / 2, bar_y - 9, value, "small", color, "middle")

    text(parts, left + chart_w / 2, height - 45, "数据来源：2020-2025四大安全会议中美全球论文统计数据.csv", "small", anchor="middle")
    return write_text(output_dir / "四大安全会_发文数量_柱状图.svg", svg_footer(parts))


def figure_by_conference(rows: list[dict[str, object]], output_dir: Path) -> str:
    years = sorted({int(row["年份"]) for row in rows})
    conferences = sorted({str(row["会议"]) for row in rows})
    by_key = {(str(row["会议"]), int(row["年份"])): row for row in rows}
    width, height = 1380, 940
    parts = svg_header(width, height)
    text(parts, 70, 62, "四大安全会议各会议年度发文数量", "title")
    text(parts, 70, 96, "每个面板内按年份比较全球、中国、美国论文数。", "subtitle")
    series = [("全球论文数", "全球", COLORS["global"]), ("中国论文数", "中国", COLORS["china"]), ("美国论文数", "美国", COLORS["us"])]
    for idx, (_, label, color) in enumerate(series):
        x = 885 + idx * 120
        parts.append(f'<rect x="{x}" y="82" width="18" height="18" rx="4" fill="{color}"/>')
        text(parts, x + 28, 96, label, "legend")

    panel_positions = [(70, 150), (720, 150), (70, 530), (720, 530)]
    panel_w, panel_h = 590, 320
    for conf, (panel_x, panel_y) in zip(conferences, panel_positions):
        plot_x, plot_y, plot_w, plot_h = panel_x + 62, panel_y + 55, 480, 210
        max_value = max(int(by_key[(conf, year)]["全球论文数"]) for year in years)
        y_max = ((max_value + 99) // 100) * 100
        parts.append(f'<rect x="{panel_x}" y="{panel_y}" width="{panel_w}" height="{panel_h}" rx="12" fill="{COLORS["panel"]}" stroke="{COLORS["grid"]}"/>')
        text(parts, panel_x + 24, panel_y + 34, conf, "label")
        for tick in range(0, y_max + 1, 100):
            y = plot_y + plot_h - tick * plot_h / y_max
            line(parts, plot_x, y, plot_x + plot_w, y, COLORS["grid"], 0.8, "3 5" if tick else None)
            text(parts, plot_x - 10, y + 4, tick, "axis", anchor="end")
        group_w, bar_w = plot_w / len(years), 13
        for year_idx, year in enumerate(years):
            center = plot_x + group_w * (year_idx + 0.5)
            text(parts, center, plot_y + plot_h + 25, str(year)[-2:], "axis", anchor="middle")
            for series_idx, (key, _, color) in enumerate(series):
                value = int(by_key[(conf, year)][key])
                bar_h = value * plot_h / y_max
                bar_x = center + (series_idx - 1) * (bar_w + 3) - bar_w / 2
                bar_y = plot_y + plot_h - bar_h
                parts.append(f'<rect x="{bar_x:.1f}" y="{bar_y:.1f}" width="{bar_w}" height="{bar_h:.1f}" rx="2" fill="{color}"/>')
    text(parts, width / 2, height - 38, "横轴标签为年份后两位，例如 20 表示 2020。", "small", anchor="middle")
    return write_text(output_dir / "四大安全会_各会议_柱状图.svg", svg_footer(parts))


def figure_share_trend(rows: list[dict[str, object]], output_dir: Path) -> str:
    metrics = aggregate(rows)
    years = metrics["years"]
    by_year = metrics["by_year"]
    china_shares = [by_year[year]["中国论文数"] / by_year[year]["全球论文数"] for year in years]
    us_shares = [by_year[year]["美国论文数"] / by_year[year]["全球论文数"] for year in years]
    width, height = 1320, 760
    left, top, chart_w, chart_h = 120, 150, 1060, 450
    y_max = 0.8

    def x_pos(year: int) -> float:
        return left + years.index(year) * chart_w / (len(years) - 1)

    def y_pos(value: float) -> float:
        return top + chart_h - value * chart_h / y_max

    parts = svg_header(width, height)
    text(parts, 70, 62, "2020-2025 四大安全会议中美论文占比趋势", "title")
    text(parts, 70, 96, "占比按年度汇总计算：国家论文数除以四个会议的全球论文总数。", "subtitle")
    parts.append(f'<rect x="{left - 55}" y="{top - 35}" width="{chart_w + 110}" height="{chart_h + 95}" rx="14" fill="{COLORS["panel"]}" stroke="{COLORS["grid"]}"/>')
    for tick in [0, 0.2, 0.4, 0.6, 0.8]:
        y = y_pos(tick)
        line(parts, left, y, left + chart_w, y, COLORS["grid"], 1, "4 5" if tick else None)
        text(parts, left - 18, y + 4, pct(tick), "axis", anchor="end")
    for year in years:
        x = x_pos(year)
        line(parts, x, top, x, top + chart_h, COLORS["grid"], 0.8, "3 7")
        text(parts, x, top + chart_h + 34, year, "axis", anchor="middle")

    for values, label, color in [(china_shares, "中国占比", COLORS["china"]), (us_shares, "美国占比", COLORS["us"])]:
        points = [(x_pos(year), y_pos(value)) for year, value in zip(years, values)]
        parts.append(f'<path d="{path_line(points)}" fill="none" stroke="{color}" stroke-width="4" stroke-linejoin="round"/>')
        for x, y, value in [(x, y, value) for (x, y), value in zip(points, values)]:
            parts.append(f'<circle cx="{x}" cy="{y}" r="5.5" fill="{color}"/>')
            text(parts, x, y - 13, pct(value), "small", color, "middle")
    for idx, (label, color) in enumerate([("中国占比", COLORS["china"]), ("美国占比", COLORS["us"]) ]):
        x = 910 + idx * 135
        parts.append(f'<rect x="{x}" y="82" width="18" height="18" rx="4" fill="{color}"/>')
        text(parts, x + 28, 96, label, "legend")
    text(parts, left + chart_w / 2, height - 45, "数据来源：2020-2025四大安全会议中美全球论文统计数据.csv", "small", anchor="middle")
    return write_text(output_dir / "四大安全会_占比趋势_曲线图.svg", svg_footer(parts))


def rasterize_svg(svg_path: str) -> str:
    png_path = str(Path(svg_path).with_suffix(".png"))
    subprocess.run(["sips", "-s", "format", "png", svg_path, "--out", png_path], check=True, capture_output=True, text=True)
    return png_path


# These renderers intentionally mirror the legacy crypto-conference chart style.
LEGACY = {
    "global": "#2196F3",
    "china": "#F44336",
    "us": "#4CAF50",
    "axis": "#111111",
    "grid": "#BDBDBD",
    "CCS": "#2166AC",
    "IEEE S&P": "#B2182B",
    "NDSS": "#4DAF4A",
    "USENIX Security": "#7B3294",
}


def legacy_header(width: int, height: int) -> list[str]:
    return [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        "<style>"
        f"text{{font-family:{FONT_FAMILY};fill:#111111;}}"
        ".title{font-size:27px;font-weight:700;} .subtitle{font-size:27px;font-weight:700;}"
        ".axis{font-size:20px;} .label{font-size:22px;} .small{font-size:18px;} .legend{font-size:21px;}"
        "</style>",
    ]


def legacy_axes(parts: list[str], left: float, top: float, chart_w: float, chart_h: float, years: list[int], y_max: int, y_step: int, y_label: str) -> None:
    for tick in range(0, y_max + 1, y_step):
        y = top + chart_h - tick * chart_h / y_max
        line(parts, left, y, left + chart_w, y, LEGACY["grid"], 1, "3 3")
        text(parts, left - 16, y + 6, tick, "axis", anchor="end")
    line(parts, left, top, left, top + chart_h, LEGACY["axis"], 2)
    line(parts, left, top + chart_h, left + chart_w, top + chart_h, LEGACY["axis"], 2)
    for idx, year in enumerate(years):
        x = left + (idx + 0.5) * chart_w / len(years)
        text(parts, x, top + chart_h + 34, year, "axis", anchor="middle")
    parts.append(
        f'<text x="{left - 66}" y="{top + chart_h / 2}" class="label" text-anchor="middle" transform="rotate(-90 {left - 66} {top + chart_h / 2})">{html.escape(y_label)}</text>'
    )


def legacy_legend(parts: list[str], items: list[tuple[str, str, str]], x: float, y: float) -> None:
    box_w, box_h = max(190, 52 + max(len(name) for name, _, _ in items) * 24), 44 * len(items) + 22
    parts.append(f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" fill="#ffffff" stroke="#111111" stroke-width="1.2"/>')
    for idx, (name, color, marker) in enumerate(items):
        cy = y + 28 + idx * 40
        line(parts, x + 16, cy, x + 60, cy, color, 4)
        if marker == "square":
            parts.append(f'<rect x="{x + 34}" y="{cy - 8}" width="16" height="16" fill="{color}"/>')
        elif marker == "triangle":
            parts.append(f'<polygon points="{x + 42},{cy - 10} {x + 32},{cy + 8} {x + 52},{cy + 8}" fill="{color}"/>')
        else:
            parts.append(f'<circle cx="{x + 42}" cy="{cy}" r="9" fill="{color}"/>')
        text(parts, x + 76, cy + 7, name, "legend")


def legacy_yearly_line(rows: list[dict[str, object]], output_dir: Path, spec: DatasetSpec) -> str:
    metrics = aggregate(rows)
    years, by_year = metrics["years"], metrics["by_year"]
    width, height, left, top, chart_w, chart_h = 2000, 1120, 95, 85, 1890, 900
    y_max = ((max(by_year[year]["全球论文数"] for year in years) + 99) // 100) * 100 + 100
    parts = legacy_header(width, height)
    text(parts, width / 2, 34, f"{spec.title}每年发文数量趋势", "title", anchor="middle")
    text(parts, width / 2, 67, "中国 vs 美国 vs 全球 (2020-2025)", "subtitle", anchor="middle")
    legacy_axes(parts, left, top, chart_w, chart_h, years, y_max, 200, "论文数量")
    for key, label, color, marker, label_offset in [
        ("全球论文数", "全球", LEGACY["global"], "circle", -18),
        ("中国论文数", "中国", LEGACY["china"], "square", 28),
        ("美国论文数", "美国", LEGACY["us"], "triangle", -18),
    ]:
        points = []
        for idx, year in enumerate(years):
            x = left + (idx + 0.5) * chart_w / len(years)
            y = top + chart_h - by_year[year][key] * chart_h / y_max
            points.append((x, y))
        parts.append(f'<path d="{path_line(points)}" fill="none" stroke="{color}" stroke-width="4.5"/>')
        for year, (x, y) in zip(years, points):
            if marker == "square":
                parts.append(f'<rect x="{x - 9}" y="{y - 9}" width="18" height="18" fill="{color}"/>')
            elif marker == "triangle":
                parts.append(f'<polygon points="{x},{y - 11} {x - 10},{y + 8} {x + 10},{y + 8}" fill="{color}"/>')
            else:
                parts.append(f'<circle cx="{x}" cy="{y}" r="9" fill="{color}"/>')
            text(parts, x, y + label_offset, by_year[year][key], "small", color, "middle")
    legacy_legend(parts, [("全球", LEGACY["global"], "circle"), ("中国", LEGACY["china"], "square"), ("美国", LEGACY["us"], "triangle")], 110, 105)
    text(parts, width / 2, height - 18, "年份", "label", anchor="middle")
    return write_text(output_dir / f"{spec.prefix}_发文数量_曲线图.svg", svg_footer(parts))


def legacy_yearly_stacked_bar(rows: list[dict[str, object]], output_dir: Path, spec: DatasetSpec) -> str:
    years = sorted({int(row["年份"]) for row in rows})
    conferences = list(spec.conferences)
    by_key = {(str(row["会议"]), int(row["年份"])): row for row in rows}
    width, height, left, top, chart_w, chart_h = 2000, 1180, 100, 95, 1885, 930
    totals = {year: sum(int(by_key[(conf, year)]["全球论文数"]) for conf in conferences) for year in years}
    y_max = ((max(totals.values()) + 199) // 200) * 200
    parts = legacy_header(width, height)
    text(parts, width / 2, 34, f"{spec.title}每年发文数量对比", "title", anchor="middle")
    text(parts, width / 2, 67, "全球 vs 中国 vs 美国 (2020-2025)", "subtitle", anchor="middle")
    legacy_axes(parts, left, top, chart_w, chart_h, years, y_max, 200, "论文数量")
    legend_x, legend_y = 110, 105
    legend_width = 170 + len(conferences) * 135
    parts.append(f'<rect x="{legend_x}" y="{legend_y}" width="{legend_width}" height="84" fill="#ffffff" stroke="#111111" stroke-width="1.2"/>')
    text(parts, legend_x + 295, legend_y + 25, "Conference", "legend", anchor="middle")
    for idx, conf in enumerate(conferences):
        x = legend_x + 22 + idx * 143
        parts.append(f'<rect x="{x}" y="{legend_y + 42}" width="24" height="20" fill="{spec.conference_colors[conf]}"/>')
        text(parts, x + 35, legend_y + 59, conf, "small")
    region_specs = [("中国", "中国论文数", LEGACY["china"]), ("美国", "美国论文数", LEGACY["global"]), ("全球", "全球论文数", "#111111")]
    group_w, bar_w = chart_w / len(years), 58
    for year_idx, year in enumerate(years):
        center = left + (year_idx + 0.5) * group_w
        for r_idx, (region, key, label_color) in enumerate(region_specs):
            x = center + (r_idx - 1) * 82 - bar_w / 2
            bottom = 0
            for conf in conferences:
                value = int(by_key[(conf, year)][key])
                bar_h = value * chart_h / y_max
                y = top + chart_h - (bottom + value) * chart_h / y_max
                parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w}" height="{bar_h:.1f}" fill="{spec.conference_colors[conf]}" stroke="#333333" stroke-width="0.8"/>')
                if value > 0:
                    text(parts, x + bar_w / 2, y + bar_h / 2 + 6, value, "small", "#ffffff", "middle")
                bottom += value
            text(parts, x + bar_w / 2, top + chart_h - bottom * chart_h / y_max - 14, f"{region}\n{bottom}", "small", label_color, "middle")
    text(parts, width / 2, height - 18, "年份", "label", anchor="middle")
    return write_text(output_dir / f"{spec.prefix}_发文数量_柱状图.svg", svg_footer(parts))


def legacy_by_conference(rows: list[dict[str, object]], output_dir: Path, spec: DatasetSpec) -> str:
    years = sorted({int(row["年份"]) for row in rows})
    conferences = list(spec.conferences)
    by_key = {(str(row["会议"]), int(row["年份"])): row for row in rows}
    width, height = (2000, 720) if len(conferences) == 3 else (2000, 1280)
    parts = legacy_header(width, height)
    text(parts, width / 2, 35, f"{spec.prefix}各会议每年发文数量对比 (2020-2025)", "title", anchor="middle")
    positions = [(70, 85), (700, 85), (1330, 85)] if len(conferences) == 3 else [(70, 85), (1050, 85), (70, 675), (1050, 675)]
    for conf, (panel_x, panel_y) in zip(conferences, positions):
        plot_x, plot_y = panel_x + 62, panel_y + 50
        plot_w, plot_h = (520, 405) if len(conferences) == 3 else (820, 405)
        max_value = max(int(by_key[(conf, year)]["全球论文数"]) for year in years)
        y_max = ((max_value + 49) // 50) * 50
        parts.append(f'<rect x="{plot_x}" y="{plot_y}" width="{plot_w}" height="{plot_h}" fill="#ffffff" stroke="#111111" stroke-width="1.2"/>')
        text(parts, plot_x + plot_w / 2, panel_y + 28, conf, "title", anchor="middle")
        for tick in range(0, y_max + 1, 50):
            y = plot_y + plot_h - tick * plot_h / y_max
            line(parts, plot_x, y, plot_x + plot_w, y, LEGACY["grid"], 1, "3 3")
            text(parts, plot_x - 12, y + 5, tick, "small", anchor="end")
        for idx, year in enumerate(years):
            center = plot_x + (idx + 0.5) * plot_w / len(years)
            text(parts, center, plot_y + plot_h + 30, year, "axis", anchor="middle")
            for series_idx, (key, color) in enumerate([("中国论文数", LEGACY["china"]), ("美国论文数", LEGACY["global"]), ("全球论文数", LEGACY["us"])]):
                value = int(by_key[(conf, year)][key])
                bar_w = 26
                bar_h = value * plot_h / y_max
                x = center + (series_idx - 1) * 28 - bar_w / 2
                y = plot_y + plot_h - bar_h
                parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w}" height="{bar_h:.1f}" fill="{color}"/>')
        legacy_legend(parts, [("中国", LEGACY["china"], "square"), ("美国", LEGACY["global"], "square"), ("全球", LEGACY["us"], "square")], plot_x + 12, plot_y + 12)
        text(parts, plot_x + plot_w / 2, panel_y + 530, "年份", "label", anchor="middle")
    return write_text(output_dir / f"{spec.prefix}_各会议_柱状图.svg", svg_footer(parts))


def legacy_share_line(rows: list[dict[str, object]], output_dir: Path, spec: DatasetSpec) -> str:
    metrics = aggregate(rows)
    years, by_year = metrics["years"], metrics["by_year"]
    china = [by_year[year]["中国论文数"] / by_year[year]["全球论文数"] * 100 for year in years]
    us = [by_year[year]["美国论文数"] / by_year[year]["全球论文数"] * 100 for year in years]
    width, height, left, top, chart_w, chart_h = 2000, 1120, 85, 50, 1900, 940
    y_max = 80
    parts = legacy_header(width, height)
    text(parts, width / 2, 35, f"{spec.prefix}中国和美国论文占比趋势 (2020-2025)", "title", anchor="middle")
    for tick in range(0, y_max, 10):
        y = top + chart_h - tick * chart_h / y_max
        line(parts, left, y, left + chart_w, y, LEGACY["grid"], 1, "3 3")
        text(parts, left - 16, y + 6, f"{tick}%", "axis", anchor="end")
    line(parts, left, top, left, top + chart_h, LEGACY["axis"], 2)
    line(parts, left, top + chart_h, left + chart_w, top + chart_h, LEGACY["axis"], 2)
    for idx, year in enumerate(years):
        x = left + (idx + 0.5) * chart_w / len(years)
        text(parts, x, top + chart_h + 34, year, "axis", anchor="middle")
    for values, label, color, marker, offset in [(china, "中国占比", LEGACY["china"], "square", -20), (us, "美国占比", LEGACY["us"], "triangle", 30)]:
        points = [(left + (idx + 0.5) * chart_w / len(years), top + chart_h - value * chart_h / y_max) for idx, value in enumerate(values)]
        parts.append(f'<path d="{path_line(points)}" fill="none" stroke="{color}" stroke-width="4.5"/>')
        for (x, y), value in zip(points, values):
            if marker == "square":
                parts.append(f'<rect x="{x - 9}" y="{y - 9}" width="18" height="18" fill="{color}"/>')
            else:
                parts.append(f'<polygon points="{x},{y - 11} {x - 10},{y + 8} {x + 10},{y + 8}" fill="{color}"/>')
            text(parts, x, y + offset, f"{value:.1f}%", "label", color, "middle")
    legacy_legend(parts, [("中国占比", LEGACY["china"], "square"), ("美国占比", LEGACY["us"], "triangle")], 100, 65)
    text(parts, width / 2, height - 18, "年份", "label", anchor="middle")
    return write_text(output_dir / f"{spec.prefix}_占比趋势_曲线图.svg", svg_footer(parts))


def figure_conference_totals(rows: list[dict[str, object]], output_dir: Path) -> str:
    metrics = aggregate(rows)
    by_conf = metrics["by_conf"]
    conferences = sorted(metrics["conferences"], key=lambda c: by_conf[c]["全球论文数"], reverse=True)
    width, height = 1320, 780
    left, top, max_w = 260, 160, 780
    row_gap, bar_h = 118, 24
    max_value = max(by_conf[conf]["全球论文数"] for conf in conferences)
    parts = svg_header(width, height)
    text(parts, 70, 62, "2020-2025 四大安全会议累计论文规模", "title")
    text(parts, 70, 96, "每个会议展示全球总量及其中中国、美国论文计数，便于比较会议规模与中美贡献。", "subtitle")
    parts.append(f'<rect x="65" y="125" width="1190" height="555" rx="14" fill="{COLORS["panel"]}" stroke="{COLORS["grid"]}"/>')

    series = [("全球论文数", "全球", COLORS["global"]), ("中国论文数", "中国", COLORS["china"]), ("美国论文数", "美国", COLORS["us"])]
    for idx, (key, label, color) in enumerate(series):
        x = 800 + idx * 120
        parts.append(f'<rect x="{x}" y="86" width="18" height="18" rx="4" fill="{color}"/>')
        text(parts, x + 28, 100, label, "legend")

    for c_idx, conf in enumerate(conferences):
        base_y = top + c_idx * row_gap
        text(parts, 92, base_y + 42, conf, "label")
        for s_idx, (key, label, color) in enumerate(series):
            y = base_y + s_idx * 30
            value = by_conf[conf][key]
            w = value * max_w / max_value
            parts.append(f'<rect x="{left}" y="{y}" width="{max_w}" height="{bar_h}" rx="7" fill="#eef2f7"/>')
            parts.append(f'<rect x="{left}" y="{y}" width="{w:.1f}" height="{bar_h}" rx="7" fill="{color}"/>')
            text(parts, left - 18, y + 17, label, "axis", anchor="end")
            text(parts, left + w + 10, y + 17, value, "small", color)

    text(parts, left + max_w / 2, height - 45, "按 2020-2025 六年累计；会议按全球论文数降序排列。", "small", anchor="middle")
    return write_text(output_dir / "四大安全会议_中美全球论文数_会议累计对比.svg", svg_footer(parts))


def heat_color(value: float, base: str) -> str:
    if base == "china":
        start, end = (252, 237, 231), (194, 65, 12)
    else:
        start, end = (235, 243, 255), (37, 99, 235)
    ratio = min(max(value, 0), 0.75) / 0.75
    rgb = tuple(int(start[i] + (end[i] - start[i]) * ratio) for i in range(3))
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def figure_share_heatmap(rows: list[dict[str, object]], output_dir: Path) -> str:
    years = sorted({int(row["年份"]) for row in rows})
    conferences = sorted({str(row["会议"]) for row in rows})
    by_key = {(str(row["会议"]), int(row["年份"])): row for row in rows}
    width, height = 1320, 860
    cell_w, cell_h = 130, 58
    left, top = 260, 160
    panel_gap = 315
    parts = svg_header(width, height)
    text(parts, 70, 62, "中美论文占比 conference-year 热力图", "title")
    text(parts, 70, 96, "颜色深浅表示该国家论文数占同会议同年份全球论文数的比例。", "subtitle")

    for panel_idx, (key, title, base) in enumerate([("中国占比", "中国占比", "china"), ("美国占比", "美国占比", "us")]):
        panel_y = top + panel_idx * panel_gap
        parts.append(f'<rect x="65" y="{panel_y - 55}" width="1190" height="270" rx="14" fill="{COLORS["panel"]}" stroke="{COLORS["grid"]}"/>')
        text(parts, 92, panel_y - 20, title, "label", COLORS["china"] if base == "china" else COLORS["us"])
        for y_idx, year in enumerate(years):
            text(parts, left + y_idx * cell_w + cell_w / 2, panel_y + 6, year, "axis", anchor="middle")
        for c_idx, conf in enumerate(conferences):
            y = panel_y + 28 + c_idx * cell_h
            text(parts, 92, y + 36, conf, "axis")
            for y_idx, year in enumerate(years):
                row = by_key[(conf, year)]
                value = float(row[key])
                x = left + y_idx * cell_w
                color = heat_color(value, base)
                parts.append(f'<rect x="{x}" y="{y}" width="{cell_w - 8}" height="{cell_h - 8}" rx="8" fill="{color}"/>')
                label_color = "#ffffff" if value >= 0.42 else COLORS["ink"]
                text(parts, x + (cell_w - 8) / 2, y + 32, pct(value), "label", label_color, "middle")

    text(parts, 660, height - 45, "占比 = 国家论文数 / 同会议同年份全球论文数。", "small", anchor="middle")
    return write_text(output_dir / "四大安全会议_中美论文占比_会议年份热力图.svg", svg_footer(parts))


def write_showcase(rows: list[dict[str, object]], rendered_files: list[str], output_dir: Path, spec: DatasetSpec, input_sources: list[Path]) -> str:
    metrics = aggregate(rows)
    total_global = sum(metrics["by_year"][year]["全球论文数"] for year in metrics["years"])
    total_china = sum(metrics["by_year"][year]["中国论文数"] for year in metrics["years"])
    total_us = sum(metrics["by_year"][year]["美国论文数"] for year in metrics["years"])
    first_year, last_year = metrics["years"][0], metrics["years"][-1]
    china_delta = metrics["by_year"][last_year]["中国论文数"] - metrics["by_year"][first_year]["中国论文数"]
    us_delta = metrics["by_year"][last_year]["美国论文数"] - metrics["by_year"][first_year]["美国论文数"]
    lines = [
        f"# 2020-2025 {spec.prefix}中美全球论文统计可视化",
        "",
        "输入数据：" + "、".join(f"`{source.relative_to(ROOT)}`" for source in input_sources),
        "",
        "## 核心指标",
        "",
        f"- 覆盖 {len(metrics['conferences'])} 个会议、{len(metrics['years'])} 个年份、{len(rows)} 个 conference-year。",
        f"- 全球论文累计 {total_global} 篇，中国论文累计 {total_china} 篇，美国论文累计 {total_us} 篇。",
        f"- {first_year} 到 {last_year}，中国年度论文数变化 {china_delta:+d} 篇，美国年度论文数变化 {us_delta:+d} 篇。",
        "",
        "## 输出图表",
        "",
    ]
    lines.extend(f"- `{Path(path).name}`" for path in rendered_files)
    lines.append("")
    return write_text(output_dir / f"{spec.prefix}_中美全球论文统计_可视化说明.md", "\n".join(lines))


def write_manifest(rows: list[dict[str, object]], rendered_files: list[str], png_files: list[str], showcase: str, output_dir: Path, spec: DatasetSpec, input_sources: list[Path]) -> str:
    metrics = aggregate(rows)
    payload = {
        "dataset": spec.key,
        "input_sources": [str(source) for source in input_sources],
        "output_dir": str(output_dir),
        "rendered_files": rendered_files,
        "png_files": png_files,
        "showcase_file": showcase,
        "charts": [
            "yearly_global_china_us_line_chart",
            "yearly_global_china_us_grouped_bar_chart",
            "conference_year_global_china_us_grouped_bar_chart",
            "yearly_china_us_share_line_chart",
        ],
        "scope": {
            "conference_count": len(metrics["conferences"]),
            "year_start": min(metrics["years"]),
            "year_end": max(metrics["years"]),
            "conference_year_rows": len(rows),
        },
    }
    return write_text(output_dir / f"{spec.prefix}_中美全球论文统计_visualization_manifest.json", json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="生成密码会或安全会的中美全球论文统计图表")
    parser.add_argument("--dataset", choices=["all", *SPECS], default="all", help="选择密码会、四大安全会或全部")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="图表输出目录")
    parser.add_argument("--security-input", type=Path, default=SECURITY_INPUT_CSV, help="四大安全会汇总 CSV")
    parser.add_argument("--crypto-data-dir", type=Path, default=CRYPTO_DATA_DIR, help="三大密码会历史 CSV 目录")
    args = parser.parse_args()
    ensure_dir(args.output_dir)

    dataset_keys = list(SPECS) if args.dataset == "all" else [args.dataset]
    for key in dataset_keys:
        spec = SPECS[key]
        if key == "crypto":
            rows = read_crypto_rows(args.crypto_data_dir)
            input_sources = [
                args.crypto_data_dir / "三大密码会_全球_20-25.csv",
                args.crypto_data_dir / "三大密码会_中国机构_20-25.csv",
                args.crypto_data_dir / "三大密码会_美国机构_20-25.csv",
            ]
        else:
            rows = read_security_rows(args.security_input)
            input_sources = [args.security_input]
        rendered_files = [
            legacy_yearly_line(rows, args.output_dir, spec),
            legacy_yearly_stacked_bar(rows, args.output_dir, spec),
            legacy_by_conference(rows, args.output_dir, spec),
            legacy_share_line(rows, args.output_dir, spec),
        ]
        png_files = [rasterize_svg(path) for path in rendered_files]
        showcase = write_showcase(rows, rendered_files, args.output_dir, spec, input_sources)
        write_manifest(rows, rendered_files, png_files, showcase, args.output_dir, spec, input_sources)


if __name__ == "__main__":
    main()
