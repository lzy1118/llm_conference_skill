from __future__ import annotations

import csv
import html
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERATED = ROOT / "generated-data"
BY_CONF = GENERATED / "extraction" / "output" / "by_conference"
NORMALIZED = GENERATED / "normalized"
OUT = ROOT / "generated-data" / "paper_tables"
OFFICIAL_TOTAL_OVERRIDES = {
    ("USENIX_SECURITY", 2025): 407,
}

FONT = '"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC","Source Han Sans SC",sans-serif'
COLORS = {
    "bg": "#ffffff",
    "ink": "#1f2937",
    "muted": "#667085",
    "line": "#cbd5e1",
    "header": "#eef4fb",
    "accent": "#2b6cb0",
    "good": "#0f766e",
}


def ensure_dir(path: Path) -> None:
    """创建覆盖率表格产物的目标目录。"""
    path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> dict:
    """读取验证报告或清单 JSON 文件。"""
    return json.loads(path.read_text(encoding="utf-8"))


def official_total(conf: str, year: int, reported_total: int) -> int:
    """当报告总数口径不同步时，应用已知的官方总数覆盖值。"""
    return int(OFFICIAL_TOTAL_OVERRIDES.get((conf, year), reported_total))


def csv_rows(path: Path) -> list[dict[str, str]]:
    """将 CSV 表读取为字典行列表。"""
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def collect() -> tuple[list[dict], list[dict], dict]:
    """将官方总数、验证报告和归一化输出合并为覆盖率记录。"""
    paper_facts = csv_rows(NORMALIZED / "paper_facts.csv")
    normalized_by_conf_year: dict[tuple[str, int], set[str]] = defaultdict(set)
    for row in paper_facts:
        key = (row["conference"], int(row["year"]))
        normalized_by_conf_year[key].add(row.get("paper_id") or row.get("paper_key") or row["title"])

    detail_rows: list[dict] = []
    summary_rows: list[dict] = []
    agg: dict[str, dict[str, int]] = defaultdict(lambda: {
        "total_papers": 0,
        "normalized_papers": 0,
        "papers_without_affiliation_data": 0,
        "partial_affiliation_coverage": 0,
        "author_affiliation_match_failed": 0,
    })

    for path in sorted(BY_CONF.glob("*/validation_report.json")):
        report = load_json(path)
        conf = str(report["conference"])
        year = int(report["year"])
        total = official_total(conf, year, int(report.get("papers_count", 0) or 0))
        normalized_count = len(normalized_by_conf_year.get((conf, year), set()))
        row = {
            "conference": conf,
            "year": year,
            "total_papers": total,
            "normalized_papers": normalized_count,
            "coverage_ratio": round(normalized_count / total * 100, 2) if total else 0.0,
            "missing_papers": max(total - normalized_count, 0),
            "papers_without_affiliation_data": int(report.get("papers_without_affiliation_data", 0) or 0),
            "partial_affiliation_coverage": int(report.get("papers_with_partial_affiliation_coverage", 0) or 0),
            "author_affiliation_match_failed": int(report.get("papers_with_author_affiliation_match_failed", 0) or 0),
        }
        detail_rows.append(row)

        bucket = agg[conf]
        for key in [
            "total_papers",
            "normalized_papers",
            "papers_without_affiliation_data",
            "partial_affiliation_coverage",
            "author_affiliation_match_failed",
        ]:
            bucket[key] += int(row[key])

    for conf in sorted(agg):
        bucket = agg[conf]
        summary_rows.append({
            "conference": conf,
            "total_papers": bucket["total_papers"],
            "normalized_papers": bucket["normalized_papers"],
            "coverage_ratio": round(bucket["normalized_papers"] / bucket["total_papers"] * 100, 2),
            "missing_papers": bucket["total_papers"] - bucket["normalized_papers"],
            "papers_without_affiliation_data": bucket["papers_without_affiliation_data"],
            "partial_affiliation_coverage": bucket["partial_affiliation_coverage"],
            "author_affiliation_match_failed": bucket["author_affiliation_match_failed"],
        })

    overall = {
        "conference": "OVERALL",
        "total_papers": sum(r["total_papers"] for r in summary_rows),
        "normalized_papers": sum(r["normalized_papers"] for r in summary_rows),
        "papers_without_affiliation_data": sum(r["papers_without_affiliation_data"] for r in summary_rows),
        "partial_affiliation_coverage": sum(r["partial_affiliation_coverage"] for r in summary_rows),
        "author_affiliation_match_failed": sum(r["author_affiliation_match_failed"] for r in summary_rows),
    }
    overall["missing_papers"] = overall["total_papers"] - overall["normalized_papers"]
    overall["coverage_ratio"] = round(overall["normalized_papers"] / overall["total_papers"] * 100, 2)
    return summary_rows, detail_rows, overall


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    """将最终论文使用的覆盖率表之一写出为 CSV。"""
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, summary_rows: list[dict], overall: dict) -> None:
    """将汇总表写为 Markdown，便于快速查看和引用。"""
    lines = [
        "# 顶会论文自动抽取覆盖率总表",
        "",
        "口径说明：以“进入最终归一化主数据层（paper_facts.csv）”的论文数作为 skills 自动抽取成功数。",
        "",
        "| 会议 | 论文总数 | 自动抽取成功数 | 自动抽取比例 | 未进入归一化层 | 无作者机构数据 | 部分作者机构缺失 | 作者-机构对齐失败 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_rows:
        lines.append(
            f"| {row['conference']} | {row['total_papers']} | {row['normalized_papers']} | {row['coverage_ratio']:.2f}\\% | {row['missing_papers']} | {row['papers_without_affiliation_data']} | {row['partial_affiliation_coverage']} | {row['author_affiliation_match_failed']} |"
        )
    lines.append(
        f"| **总体** | **{overall['total_papers']}** | **{overall['normalized_papers']}** | **{overall['coverage_ratio']:.2f}\\%** | **{overall['missing_papers']}** | **{overall['papers_without_affiliation_data']}** | **{overall['partial_affiliation_coverage']}** | **{overall['author_affiliation_match_failed']}** |"
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_latex(path: Path, summary_rows: list[dict], overall: dict) -> None:
    """将同一份覆盖率汇总表写为可直接入论文的 LaTeX。"""
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{2020--2025年七个顶会论文自动抽取覆盖率统计。本文以进入最终归一化主数据层（\texttt{paper\_facts.csv}）的论文数作为自动抽取成功数。}",
        r"\label{tab:auto-extraction-coverage}",
        r"\small",
        r"\begin{tabular}{lrrrrrrr}",
        r"\toprule",
        r"会议 & 论文总数 & 自动抽取成功数 & 自动抽取比例(\%) & 未进入归一化层 & 无作者机构数据 & 部分作者机构缺失 & 作者-机构对齐失败 \\",
        r"\midrule",
    ]
    for row in summary_rows:
        lines.append(
            f"{row['conference']} & {row['total_papers']} & {row['normalized_papers']} & {row['coverage_ratio']:.2f} & {row['missing_papers']} & {row['papers_without_affiliation_data']} & {row['partial_affiliation_coverage']} & {row['author_affiliation_match_failed']} \\\\"
        )
    lines.extend([
        r"\midrule",
        f"Overall & {overall['total_papers']} & {overall['normalized_papers']} & {overall['coverage_ratio']:.2f} & {overall['missing_papers']} & {overall['papers_without_affiliation_data']} & {overall['partial_affiliation_coverage']} & {overall['author_affiliation_match_failed']} \\\\",
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table*}",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_svg_table(path: Path, summary_rows: list[dict], overall: dict) -> None:
    """将汇总表渲染为适合论文风格的 SVG 表格图。"""
    rows = summary_rows + [overall]
    width = 1800
    row_h = 58
    height = 180 + row_h * (len(rows) + 1) + 50
    cols = [
        ("会议", 220),
        ("论文总数", 140),
        ("自动抽取成功数", 200),
        ("自动抽取比例", 170),
        ("未进入归一化层", 170),
        ("无作者机构数据", 170),
        ("部分作者机构缺失", 190),
        ("作者-机构对齐失败", 190),
    ]
    xs = [70]
    for _, w in cols[:-1]:
        xs.append(xs[-1] + w)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="100%" height="100%" fill="{COLORS["bg"]}"/>',
        f'<style>text{{font-family:{FONT}; fill:{COLORS["ink"]};}} .cap{{font-size:16px;fill:{COLORS["muted"]};letter-spacing:1px;}} .title{{font-size:30px;font-weight:700;}} .sub{{font-size:14px;fill:{COLORS["muted"]};}} .head{{font-size:15px;font-weight:700;}} .cell{{font-size:14px;}} .strong{{font-size:14px;font-weight:700;}}</style>',
        '<text x="70" y="44" class="cap">TABLE AS FIGURE</text>',
        '<text x="70" y="84" class="title">顶会论文自动抽取覆盖率总表</text>',
        '<text x="70" y="116" class="sub">口径：以进入最终归一化主数据层（paper_facts.csv）的论文数作为自动抽取成功数。</text>',
    ]
    table_x, table_y = 70, 150
    total_w = sum(w for _, w in cols)
    parts.append(f'<rect x="{table_x}" y="{table_y}" width="{total_w}" height="{row_h}" fill="{COLORS["header"]}" stroke="{COLORS["line"]}" stroke-width="1.2"/>')
    for i, (label, w) in enumerate(cols):
        x = xs[i]
        parts.append(f'<line x1="{x}" y1="{table_y}" x2="{x}" y2="{table_y + row_h * (len(rows) + 1)}" stroke="{COLORS["line"]}" stroke-width="1"/>')
        parts.append(f'<text x="{x + 16}" y="{table_y + 36}" class="head">{html.escape(label)}</text>')
    parts.append(f'<line x1="{table_x + total_w}" y1="{table_y}" x2="{table_x + total_w}" y2="{table_y + row_h * (len(rows) + 1)}" stroke="{COLORS["line"]}" stroke-width="1"/>')

    for ridx, row in enumerate(rows, start=1):
        y = table_y + ridx * row_h
        fill = "#f8fafc" if row["conference"] == "OVERALL" else "#ffffff"
        parts.append(f'<rect x="{table_x}" y="{y}" width="{total_w}" height="{row_h}" fill="{fill}" stroke="{COLORS["line"]}" stroke-width="1"/>')
        values = [
            str(row["conference"] if row["conference"] != "OVERALL" else "总体"),
            str(row["total_papers"]),
            str(row["normalized_papers"]),
            f'{row["coverage_ratio"]:.2f}%',
            str(row["missing_papers"]),
            str(row["papers_without_affiliation_data"]),
            str(row["partial_affiliation_coverage"]),
            str(row["author_affiliation_match_failed"]),
        ]
        klass = "strong" if row["conference"] == "OVERALL" else "cell"
        for i, value in enumerate(values):
            parts.append(f'<text x="{xs[i] + 16}" y="{y + 36}" class="{klass}">{html.escape(value)}</text>')

    bottom = table_y + row_h * (len(rows) + 1)
    parts.append(f'<line x1="{table_x}" y1="{bottom}" x2="{table_x + total_w}" y2="{bottom}" stroke="{COLORS["line"]}" stroke-width="1"/>')
    parts.append('</svg>\n')
    path.write_text("\n".join(parts), encoding="utf-8")


def write_manifest(path: Path, summary_rows: list[dict], detail_rows: list[dict], overall: dict) -> None:
    """用 JSON 记录生成的表格包及其核心指标。"""
    payload = {
        "topic": "skills 自动抽取数据覆盖率",
        "metric_definition": "进入最终归一化主数据层（paper_facts.csv）的论文数 / 对应会议官方论文总数",
        "overall": overall,
        "conference_count": len(summary_rows),
        "conference_year_count": len(detail_rows),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    """生成覆盖率表格包，包含 CSV、Markdown、LaTeX 与 SVG。"""
    ensure_dir(OUT)
    summary_rows, detail_rows, overall = collect()
    summary_fields = [
        "conference",
        "total_papers",
        "normalized_papers",
        "coverage_ratio",
        "missing_papers",
        "papers_without_affiliation_data",
        "partial_affiliation_coverage",
        "author_affiliation_match_failed",
    ]
    detail_fields = [
        "conference",
        "year",
        "total_papers",
        "normalized_papers",
        "coverage_ratio",
        "missing_papers",
        "papers_without_affiliation_data",
        "partial_affiliation_coverage",
        "author_affiliation_match_failed",
    ]
    write_csv(OUT / "auto_extraction_coverage_summary.csv", summary_rows + [overall], summary_fields)
    write_csv(OUT / "auto_extraction_coverage_by_conference_year.csv", detail_rows, detail_fields)
    write_markdown(OUT / "auto_extraction_coverage_summary.md", summary_rows, overall)
    write_latex(OUT / "auto_extraction_coverage_summary.tex", summary_rows, overall)
    write_svg_table(OUT / "auto_extraction_coverage_summary.svg", summary_rows, overall)
    write_manifest(OUT / "coverage_manifest.json", summary_rows, detail_rows, overall)


if __name__ == "__main__":
    main()
