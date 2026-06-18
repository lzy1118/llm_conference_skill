from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


SECTION_FILES = {
    "country": Path("country/country_summary.csv"),
    "institution": Path("institutions/institution_summary.csv"),
    "author": Path("authors/author_summary.csv"),
    "trend": Path("trends/trend_summary.csv"),
}

DEFAULT_OUTPUT_DIR = Path("generated-data") / "visualizations"

COLORS = {
    "blue": "#4F81BD",
    "red": "#C0504D",
    "green": "#69B964",
    "orange": "#F39C34",
    "gray": "#B8C2CC",
    "light_grid": "#BFBFBF",
    "black": "#222222",
}

PLOT_FILES = {
    "heatmap": "七大会_conference-year_论文规模热力图",
    "coverage": "各会议_作者机构覆盖结构_柱状图",
    "country_rank": "国家地区_头部排名_横向柱状图",
    "institution_rank": "机构_头部排名_横向柱状图",
    "trend": "重点国家地区_趋势图",
}

PLOT_TITLES = {
    "heatmap": "2020-2025年七个顶级会议论文规模分布",
    "coverage": "各会议作者机构信息覆盖结构",
    "country_rank": "国家（地区）发文规模前列分布",
    "institution_rank": "机构发文规模前列分布",
    "trend": "重点国家（地区）发文趋势",
}

EXCLUDED_COUNTRY_KEYS = {"Multiple"}

COUNTRY_DISPLAY = {
    "United States": "美国",
    "China": "中国",
    "Germany": "德国",
    "Switzerland": "瑞士",
    "United Kingdom": "英国",
    "France": "法国",
    "Israel": "以色列",
    "Hong Kong": "中国香港",
    "Singapore": "新加坡",
    "Taiwan": "中国台湾",
    "Japan": "日本",
    "South Korea": "韩国",
    "Canada": "加拿大",
    "Australia": "澳大利亚",
    "Netherlands": "荷兰",
}

CONFERENCE_DISPLAY = {
    "ASIACRYPT": "ASIACRYPT",
    "CRYPTO": "CRYPTO",
    "EUROCRYPT": "EUROCRYPT",
    "CCS": "ACM CCS",
    "IEEE_S&P": "IEEE S&P",
    "NDSS": "NDSS",
    "USENIX_SECURITY": "USENIX Security",
}


def display_country(name: str) -> str:
    """将规范化国家标签转换为论文展示用中文名称。"""
    return COUNTRY_DISPLAY.get(name, name)


def display_conference(name: str) -> str:
    """将内部会议键转换为图表展示名称。"""
    return CONFERENCE_DISPLAY.get(name, name)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """读取可视化层使用的 CSV 数据表。"""
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict:
    """读取报告或清单等小型 JSON 产物。"""
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    """写出展示包所需的 Markdown 或辅助文本文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> str:
    """写出可视化配套数据表，并返回其路径。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


def format_markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    """将数据行渲染为简洁的 Markdown 表格。"""
    header_line = "| " + " | ".join(headers) + " |"
    sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
    body_lines = ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join([header_line, sep_line, *body_lines])


def configure_style() -> None:
    """为全部图表应用统一的论文风格 Matplotlib 主题。"""
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [
                "Arial Unicode MS",
                "PingFang SC",
                "Hiragino Sans GB",
                "Heiti SC",
                "Microsoft YaHei",
                "SimHei",
                "DejaVu Sans",
            ],
            "axes.unicode_minus": False,
            "axes.titlesize": 18,
            "axes.labelsize": 14,
            "xtick.labelsize": 11,
            "ytick.labelsize": 11,
            "legend.fontsize": 11,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": COLORS["black"],
            "axes.linewidth": 1.1,
            "grid.color": COLORS["light_grid"],
            "grid.alpha": 0.35,
            "grid.linestyle": "-",
        }
    )


def save_figure(fig: plt.Figure, output_dir: Path, filename_base: str) -> list[str]:
    """将单张图同时保存为 PNG 和 SVG，并关闭图对象。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    png_path = output_dir / f"{filename_base}.png"
    svg_path = output_dir / f"{filename_base}.svg"
    fig.savefig(png_path, dpi=220, bbox_inches="tight")
    fig.savefig(svg_path, bbox_inches="tight")
    plt.close(fig)
    return [str(png_path), str(svg_path)]


def build_metrics(analysis_dir: Path) -> dict:
    """收集当前展示图组所需的跨脚本指标数据。"""
    generated_root = analysis_dir.parent
    paper_facts = generated_root / "normalized" / "paper_facts.csv"
    coverage_summary = generated_root / "paper_tables_three_tier" / "three_tier_coverage_summary.csv"
    trend_summary = analysis_dir / "trends" / "trend_summary.csv"
    country_summary = analysis_dir / "country" / "country_summary.csv"
    institution_summary = analysis_dir / "institutions" / "institution_summary.csv"
    normalization_report = generated_root / "normalized" / "normalization_report.json"
    role_report = generated_root / "author-roles" / "author_role_report.json"
    cfp_report = generated_root / "cfp" / "output" / "cfp_validation_report.json"

    counts_by_conference_year: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    counts_by_conference: Counter[str] = Counter()
    for row in read_csv_rows(paper_facts):
        conf = row["conference"]
        year = int(row["year"])
        counts_by_conference_year[conf][year] += 1
        counts_by_conference[conf] += 1

    coverage_rows = read_csv_rows(coverage_summary)
    coverage_by_conference = [row for row in coverage_rows if row["conference"] != "OVERALL"]
    overall = next(row for row in coverage_rows if row["conference"] == "OVERALL")
    overall = dict(overall)
    success_total = int(overall["single_clean_coverage"]) + int(overall["same_country_multi_clear"])
    overall["success_total"] = success_total
    overall["success_ratio"] = round(success_total * 100 / int(overall["total_papers"]), 2)

    country_rows = [row for row in read_csv_rows(country_summary) if row["country"] not in EXCLUDED_COUNTRY_KEYS]
    institution_rows = read_csv_rows(institution_summary)
    trend_rows = [
        row
        for row in read_csv_rows(trend_summary)
        if row["entity_type"] == "country" and row["entity_name"] not in EXCLUDED_COUNTRY_KEYS
    ][:5]

    return {
        "counts_by_conference_year": counts_by_conference_year,
        "counts_by_conference": counts_by_conference,
        "coverage_by_conference": coverage_by_conference,
        "coverage_overall": overall,
        "country_rows": country_rows,
        "institution_rows": institution_rows,
        "trend_rows": trend_rows,
        "normalization_report": read_json(normalization_report),
        "role_report": read_json(role_report),
        "cfp_report": read_json(cfp_report),
    }


def set_common_axes(ax, *, xlabel: str = "", ylabel: str = "", ylim=None) -> None:
    """为不同图表应用统一的坐标轴样式。"""
    ax.spines["top"].set_visible(True)
    ax.spines["right"].set_visible(True)
    ax.spines["left"].set_linewidth(1.1)
    ax.spines["bottom"].set_linewidth(1.1)
    ax.grid(axis="y", zorder=0)
    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)
    if ylim is not None:
        ax.set_ylim(*ylim)


def plot_heatmap(metrics: dict, output_dir: Path) -> list[str]:
    """绘制会议-年份论文数量热力图。"""
    filename = PLOT_FILES["heatmap"]
    title = PLOT_TITLES["heatmap"]
    conferences = ["ASIACRYPT", "CRYPTO", "EUROCRYPT", "CCS", "IEEE_S&P", "NDSS", "USENIX_SECURITY"]
    years = [2020, 2021, 2022, 2023, 2024, 2025]
    data = np.array([[metrics["counts_by_conference_year"][conf][year] for year in years] for conf in conferences])
    conference_labels = [display_conference(conf) for conf in conferences]

    fig, ax = plt.subplots(figsize=(11.8, 7.0))
    im = ax.imshow(data, cmap="Blues", aspect="auto")
    ax.set_xticks(range(len(years)), years)
    ax.set_yticks(range(len(conferences)), conference_labels)
    ax.set_title(title, pad=12)
    for i in range(len(conferences)):
        for j in range(len(years)):
            value = data[i, j]
            ax.text(j, i, str(value), ha="center", va="center", color="white" if value > data.max() * 0.48 else COLORS["black"], fontsize=11, fontweight="bold")
    plt.colorbar(im, ax=ax, fraction=0.032, pad=0.02)
    return save_figure(fig, output_dir, filename)


def plot_coverage(metrics: dict, output_dir: Path) -> list[str]:
    """按会议绘制堆叠式覆盖结构柱状图。"""
    filename = PLOT_FILES["coverage"]
    title = PLOT_TITLES["coverage"]
    rows = metrics["coverage_by_conference"]
    labels = [display_conference(row["conference"]) for row in rows]
    total = np.array([int(row["total_papers"]) for row in rows], dtype=float)
    single = np.array([int(row["single_clean_coverage"]) for row in rows], dtype=float) / total * 100
    same = np.array([int(row["same_country_multi_clear"]) for row in rows], dtype=float) / total * 100
    unresolved = np.array([int(row["unresolved_multi_ambiguity"]) for row in rows], dtype=float) / total * 100
    residual = np.array(
        [
            int(row["partial_affiliation_coverage"]) + int(row["no_affiliation_data"]) + int(row["author_affiliation_match_failed"])
            for row in rows
        ],
        dtype=float,
    ) / total * 100

    fig, ax = plt.subplots(figsize=(12.2, 8.4))
    x = np.arange(len(labels))
    ax.bar(x, single, color=COLORS["blue"], label="单机构干净覆盖", zorder=3)
    ax.bar(x, same, bottom=single, color=COLORS["green"], label="同国多机构清晰覆盖", zorder=3)
    ax.bar(x, unresolved, bottom=single + same, color=COLORS["red"], label="未消歧歧义", zorder=3)
    ax.bar(x, residual, bottom=single + same + unresolved, color=COLORS["gray"], label="剩余问题", zorder=3)
    success = single + same
    for i, val in enumerate(success):
        ax.text(i, min(val + 2.2, 101.8), f"{val:.1f}%", ha="center", va="bottom", fontsize=11, color=COLORS["black"])
    ax.set_xticks(x, labels)
    ax.set_title(title, pad=10)
    set_common_axes(ax, ylabel="占比（%）", ylim=(0, 106))
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, frameon=True, borderpad=0.6, columnspacing=1.4)
    fig.subplots_adjust(bottom=0.2)
    return save_figure(fig, output_dir, filename)


def plot_country_rank(metrics: dict, output_dir: Path) -> list[str]:
    """绘制国家论文数量头部排名图。"""
    filename = PLOT_FILES["country_rank"]
    title = PLOT_TITLES["country_rank"]
    countries = metrics["country_rows"][:8]
    country_labels = [display_country(row["country"]) for row in countries]
    country_vals = [int(row["papers"]) for row in countries]
    fig, ax = plt.subplots(figsize=(11.5, 6.2))
    y = np.arange(len(country_labels))
    ax.barh(y, country_vals, color=COLORS["blue"], zorder=3)
    ax.set_yticks(y, country_labels)
    ax.invert_yaxis()
    ax.set_title(title, fontsize=18, pad=10)
    set_common_axes(ax, xlabel="论文数量")
    for i, v in enumerate(country_vals):
        ax.text(v + max(country_vals) * 0.02, i, str(v), va="center", fontsize=11)
    fig.tight_layout()
    return save_figure(fig, output_dir, filename)

def plot_institution_rank(metrics: dict, output_dir: Path) -> list[str]:
    """绘制机构论文数量头部排名图。"""
    filename = PLOT_FILES["institution_rank"]
    title = PLOT_TITLES["institution_rank"]
    institutions = metrics["institution_rows"][:8]
    inst_labels = [row["institution_name"] for row in institutions]
    inst_vals = [int(row["papers"]) for row in institutions]
    fig, ax = plt.subplots(figsize=(11.8, 6.4))
    y2 = np.arange(len(inst_labels))
    ax.barh(y2, inst_vals, color=COLORS["green"], zorder=3)
    ax.set_yticks(y2, inst_labels)
    ax.invert_yaxis()
    ax.set_title(title, fontsize=18, pad=10)
    set_common_axes(ax, xlabel="论文数量")
    for i, v in enumerate(inst_vals):
        ax.text(v + max(inst_vals) * 0.02, i, str(v), va="center", fontsize=11)
    fig.tight_layout()
    return save_figure(fig, output_dir, filename)


def plot_trend(metrics: dict, output_dir: Path) -> list[str]:
    """绘制头部国家或地区的多年趋势图。"""
    filename = PLOT_FILES["trend"]
    title = PLOT_TITLES["trend"]
    rows = metrics["trend_rows"]
    years = [2020, 2021, 2022, 2023, 2024, 2025]

    top_names = [row["entity_name"] for row in rows]
    data = {}
    year_table = read_csv_rows(Path(output_dir).parent.parent / "analysis" / "country" / "country_by_year.csv")
    for name in top_names:
        data[name] = [0] * len(years)
    for row in year_table:
        if row["country"] in EXCLUDED_COUNTRY_KEYS:
            continue
        if row["country"] in data and int(row["year"]) in years:
            idx = years.index(int(row["year"]))
            data[row["country"]][idx] = int(row["papers"])

    fig, ax = plt.subplots(figsize=(11.5, 6.4))
    color_cycle = [COLORS["blue"], COLORS["red"], COLORS["green"], COLORS["orange"], COLORS["gray"]]
    marker_cycle = ["o", "s", "^", "D", "P"]
    for idx, name in enumerate(top_names):
        values = data[name]
        ax.plot(years, values, color=color_cycle[idx], marker=marker_cycle[idx], linewidth=2.6, markersize=8, label=display_country(name), zorder=3)
        ax.text(years[-1] + 0.03, values[-1], str(values[-1]), color=color_cycle[idx], fontsize=11, va="center")
    ax.set_title(title, pad=10)
    set_common_axes(ax, xlabel="年份", ylabel="论文数量")
    ax.legend(loc="upper left", frameon=True)
    ax.set_xticks(years)
    return save_figure(fig, output_dir, filename)


def export_supporting_tables(metrics: dict, output_dir: Path) -> list[str]:
    """导出每张图背后的源数据表，便于人工核对。"""
    exported: list[str] = []

    heatmap_headers = ["conference", "year", "papers"]
    heatmap_rows: list[dict[str, object]] = []
    for conference in ["ASIACRYPT", "CRYPTO", "EUROCRYPT", "CCS", "IEEE_S&P", "NDSS", "USENIX_SECURITY"]:
        for year in [2020, 2021, 2022, 2023, 2024, 2025]:
            heatmap_rows.append(
                {
                    "conference": display_conference(conference),
                    "year": year,
                    "papers": metrics["counts_by_conference_year"][conference][year],
                }
            )
    exported.append(write_csv(output_dir / "七大会_conference-year_论文规模热力图_数据.csv", heatmap_headers, heatmap_rows))

    coverage_headers = [
        "conference",
        "total_papers",
        "single_clean_coverage",
        "same_country_multi_clear",
        "unresolved_multi_ambiguity",
        "partial_affiliation_coverage",
        "no_affiliation_data",
        "author_affiliation_match_failed",
        "single_clean_ratio_pct",
        "same_country_multi_ratio_pct",
        "unresolved_ratio_pct",
        "residual_ratio_pct",
        "success_ratio_pct",
    ]
    coverage_rows: list[dict[str, object]] = []
    for row in metrics["coverage_by_conference"]:
        total = int(row["total_papers"])
        single = int(row["single_clean_coverage"])
        same = int(row["same_country_multi_clear"])
        unresolved = int(row["unresolved_multi_ambiguity"])
        residual = int(row["partial_affiliation_coverage"]) + int(row["no_affiliation_data"]) + int(row["author_affiliation_match_failed"])
        coverage_rows.append(
            {
                "conference": row["conference"],
                "conference_display": display_conference(row["conference"]),
                "total_papers": total,
                "single_clean_coverage": single,
                "same_country_multi_clear": same,
                "unresolved_multi_ambiguity": unresolved,
                "partial_affiliation_coverage": int(row["partial_affiliation_coverage"]),
                "no_affiliation_data": int(row["no_affiliation_data"]),
                "author_affiliation_match_failed": int(row["author_affiliation_match_failed"]),
                "single_clean_ratio_pct": round(single * 100 / total, 2),
                "same_country_multi_ratio_pct": round(same * 100 / total, 2),
                "unresolved_ratio_pct": round(unresolved * 100 / total, 2),
                "residual_ratio_pct": round(residual * 100 / total, 2),
                "success_ratio_pct": round((single + same) * 100 / total, 2),
            }
        )
    for row in coverage_rows:
        row["conference"] = row["conference_display"]
        row.pop("conference_display", None)
    exported.append(write_csv(output_dir / "各会议_作者机构覆盖结构_柱状图_数据.csv", coverage_headers, coverage_rows))

    country_rows = [
        {"country": display_country(row["country"]), "papers": int(row["papers"]), "authors": int(row["authors"]), "institutions": int(row["institutions"])}
        for row in metrics["country_rows"][:8]
    ]
    exported.append(write_csv(output_dir / "国家地区_头部排名_横向柱状图_数据.csv", ["country", "papers", "authors", "institutions"], country_rows))

    institution_rows = [
        {
            "institution_name": row["institution_name"],
            "papers": int(row["papers"]),
            "authors": int(row["authors"]),
            "country": row["country"],
        }
        for row in metrics["institution_rows"][:8]
    ]
    exported.append(write_csv(output_dir / "机构_头部排名_横向柱状图_数据.csv", ["institution_name", "papers", "authors", "country"], institution_rows))

    years = [2020, 2021, 2022, 2023, 2024, 2025]
    trend_year_table = read_csv_rows(Path(output_dir).parent.parent / "analysis" / "country" / "country_by_year.csv")
    top_names = [row["entity_name"] for row in metrics["trend_rows"]]
    trend_rows: list[dict[str, object]] = []
    for name in top_names:
        year_map = {int(row["year"]): int(row["papers"]) for row in trend_year_table if row["country"] == name}
        trend_row = {"country": display_country(name)}
        for year in years:
            trend_row[str(year)] = year_map.get(year, 0)
        trend_rows.append(trend_row)
    exported.append(write_csv(output_dir / "重点国家地区_趋势图_数据.csv", ["country", *[str(year) for year in years]], trend_rows))

    markdown_sections = [
        "# 图表对应数据表",
        "",
        "## 七大会_conference-year_论文规模热力图",
        "",
        format_markdown_table(
            ["conference", "year", "papers"],
            [[row["conference"], row["year"], row["papers"]] for row in heatmap_rows],
        ),
        "",
        "## 各会议_作者机构覆盖结构_柱状图",
        "",
        format_markdown_table(
            ["conference", "total", "single_pct", "same_pct", "unresolved_pct", "residual_pct", "success_pct"],
            [
                [
                    row["conference"],
                    row["total_papers"],
                    row["single_clean_ratio_pct"],
                    row["same_country_multi_ratio_pct"],
                    row["unresolved_ratio_pct"],
                    row["residual_ratio_pct"],
                    row["success_ratio_pct"],
                ]
                for row in coverage_rows
            ],
        ),
        "",
        "## 国家地区_头部排名_横向柱状图",
        "",
        format_markdown_table(
            ["country", "papers", "authors", "institutions"],
            [[row["country"], row["papers"], row["authors"], row["institutions"]] for row in country_rows],
        ),
        "",
        "## 机构_头部排名_横向柱状图",
        "",
        format_markdown_table(
            ["institution", "papers", "authors", "country"],
            [[row["institution_name"], row["papers"], row["authors"], row["country"]] for row in institution_rows],
        ),
        "",
        "## 重点国家地区_趋势图",
        "",
        format_markdown_table(
            ["country", "2020", "2021", "2022", "2023", "2024", "2025"],
            [[row["country"], row["2020"], row["2021"], row["2022"], row["2023"], row["2024"], row["2025"]] for row in trend_rows],
        ),
        "",
    ]
    md_path = output_dir / "图表对应数据表.md"
    write_text(md_path, "\n".join(markdown_sections))
    exported.append(str(md_path))
    return exported


def build_showcase_markdown(metrics: dict, output_dir: Path, rendered_files: list[str]) -> str:
    """为当前可视化展示结果生成简洁的 Markdown 索引页。"""
    overall = metrics["coverage_overall"]
    top_countries = ", ".join(f"{display_country(row['country'])}({row['papers']})" for row in metrics["country_rows"][:5])
    top_institutions = ", ".join(f"{row['institution_name']}({row['papers']})" for row in metrics["institution_rows"][:5])
    lines = [
        "# 当前论文风格配图成果",
        "",
        f"- 标准化主表论文数：`{sum(metrics['counts_by_conference'].values())}`",
        f"- 有效成功覆盖率：`{overall['success_ratio']}%`",
        f"- 标准化机构数：`{metrics['normalization_report']['institution_count']}`",
        f"- 作者角色覆盖论文：`{metrics['role_report']['papers']}`",
        f"- CFP 事件记录数：`{metrics['cfp_report']['event_rows']}`",
        "",
        "## 头部结果",
        "",
        f"- 国家/地区：{top_countries}",
        f"- 机构：{top_institutions}",
        "",
        "## 正式图表文件",
        "",
    ]
    for path in rendered_files:
        if path.endswith(".png"):
            lines.append(f"- `{Path(path).name}`")
    lines.extend(
        [
            "",
            "## 对应数据表",
            "",
            "- `图表对应数据表.md`",
            "- `七大会_conference-year_论文规模热力图_数据.csv`",
            "- `各会议_作者机构覆盖结构_柱状图_数据.csv`",
            "- `国家地区_头部排名_横向柱状图_数据.csv`",
            "- `机构_头部排名_横向柱状图_数据.csv`",
            "- `重点国家地区_趋势图_数据.csv`",
        ]
    )
    result = output_dir / "visualization_showcase.md"
    write_text(result, "\n".join(lines) + "\n")
    return str(result)


def main() -> None:
    """生成当前展示用图表包及其配套数据表。"""
    parser = argparse.ArgumentParser(description="Generate paper-style conference visualizations.")
    parser.add_argument("--analysis-dir", required=True, help="Root analysis directory")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory")
    args = parser.parse_args()

    configure_style()
    analysis_dir = Path(args.analysis_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    metrics = build_metrics(analysis_dir)
    rendered_files: list[str] = []
    for builder in [plot_heatmap, plot_coverage, plot_country_rank, plot_institution_rank, plot_trend]:
        rendered_files.extend(builder(metrics, output_dir))
    rendered_files.extend(export_supporting_tables(metrics, output_dir))
    rendered_files.append(build_showcase_markdown(metrics, output_dir, rendered_files))

    manifest = {
        "analysis_dir": str(analysis_dir),
        "output_dir": str(output_dir),
        "rendered_files": rendered_files,
        "paper_total": sum(metrics["counts_by_conference"].values()),
        "coverage_success_ratio": metrics["coverage_overall"]["success_ratio"],
    }
    write_text(output_dir / "visualization_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
