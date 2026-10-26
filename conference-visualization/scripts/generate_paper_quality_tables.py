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
OUT = GENERATED / "paper_tables_quality"
OFFICIAL_TOTAL_OVERRIDES = {
    ("USENIX_SECURITY", 2025): 407,
}

FONT = '"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC","Source Han Sans SC",sans-serif'
COLORS = {
    "bg": "#ffffff",
    "ink": "#1f2937",
    "muted": "#667085",
    "line": "#cbd5e1",
    "header": "#f8fafc",
}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def official_total(conf: str, year: int, reported_total: int) -> int:
    return int(OFFICIAL_TOTAL_OVERRIDES.get((conf, year), reported_total))


def normalized_counts() -> dict[tuple[str, int], int]:
    counts: dict[tuple[str, int], int] = defaultdict(int)
    with (NORMALIZED / "paper_facts.csv").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            counts[(row["conference"], int(row["year"]))] += 1
    return counts


def collect_rows() -> tuple[list[dict], dict]:
    norm_counts = normalized_counts()
    rows: list[dict] = []
    overall = defaultdict(int)
    for path in sorted(BY_CONF.glob("*/validation_report.json")):
        report = load_json(path)
        conf = str(report["conference"])
        year = int(report["year"])
        total = official_total(conf, year, int(report.get("papers_count", 0) or 0))
        in_main = int(norm_counts.get((conf, year), 0))
        no_aff = int(report.get("papers_without_affiliation_data", 0) or 0)
        partial = int(report.get("papers_with_partial_affiliation_coverage", 0) or 0)
        match_failed = int(report.get("papers_with_author_affiliation_match_failed", 0) or 0)
        full_coverage = max(total - no_aff - partial - match_failed, 0)
        row = {
            "conference": conf,
            "year": year,
            "total_papers": total,
            "in_main_data": in_main,
            "in_main_ratio": round(in_main / total * 100, 2) if total else 0.0,
            "full_affiliation_coverage": full_coverage,
            "full_coverage_ratio": round(full_coverage / total * 100, 2) if total else 0.0,
            "partial_affiliation_coverage": partial,
            "partial_ratio": round(partial / total * 100, 2) if total else 0.0,
            "papers_without_affiliation_data": no_aff,
            "no_aff_ratio": round(no_aff / total * 100, 2) if total else 0.0,
            "author_affiliation_match_failed": match_failed,
            "match_failed_ratio": round(match_failed / total * 100, 2) if total else 0.0,
        }
        rows.append(row)
        for key in [
            "total_papers",
            "in_main_data",
            "full_affiliation_coverage",
            "partial_affiliation_coverage",
            "papers_without_affiliation_data",
            "author_affiliation_match_failed",
        ]:
            overall[key] += int(row[key])

    overall_row = {
        "conference": "OVERALL",
        "total_papers": overall["total_papers"],
        "in_main_data": overall["in_main_data"],
        "in_main_ratio": round(overall["in_main_data"] / overall["total_papers"] * 100, 2),
        "full_affiliation_coverage": overall["full_affiliation_coverage"],
        "full_coverage_ratio": round(overall["full_affiliation_coverage"] / overall["total_papers"] * 100, 2),
        "partial_affiliation_coverage": overall["partial_affiliation_coverage"],
        "partial_ratio": round(overall["partial_affiliation_coverage"] / overall["total_papers"] * 100, 2),
        "papers_without_affiliation_data": overall["papers_without_affiliation_data"],
        "no_aff_ratio": round(overall["papers_without_affiliation_data"] / overall["total_papers"] * 100, 2),
        "author_affiliation_match_failed": overall["author_affiliation_match_failed"],
        "match_failed_ratio": round(overall["author_affiliation_match_failed"] / overall["total_papers"] * 100, 2),
    }
    return rows, overall_row


def aggregate_by_conference(detail_rows: list[dict]) -> list[dict]:
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in detail_rows:
        conf = row["conference"]
        for key in [
            "total_papers",
            "in_main_data",
            "full_affiliation_coverage",
            "partial_affiliation_coverage",
            "papers_without_affiliation_data",
            "author_affiliation_match_failed",
        ]:
            buckets[conf][key] += int(row[key])
    out = []
    for conf in sorted(buckets):
        b = buckets[conf]
        total = b["total_papers"]
        out.append({
            "conference": conf,
            "total_papers": total,
            "in_main_data": b["in_main_data"],
            "in_main_ratio": round(b["in_main_data"] / total * 100, 2),
            "full_affiliation_coverage": b["full_affiliation_coverage"],
            "full_coverage_ratio": round(b["full_affiliation_coverage"] / total * 100, 2),
            "partial_affiliation_coverage": b["partial_affiliation_coverage"],
            "partial_ratio": round(b["partial_affiliation_coverage"] / total * 100, 2),
            "papers_without_affiliation_data": b["papers_without_affiliation_data"],
            "no_aff_ratio": round(b["papers_without_affiliation_data"] / total * 100, 2),
            "author_affiliation_match_failed": b["author_affiliation_match_failed"],
            "match_failed_ratio": round(b["author_affiliation_match_failed"] / total * 100, 2),
        })
    return out


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_md(path: Path, rows: list[dict], overall: dict) -> None:
    lines = [
        "# skills 自动抽取与作者机构覆盖率总表",
        "",
        "更严格口径说明：",
        "- 进入主数据层：论文进入最终归一化主数据层 `paper_facts.csv`。",
        "- 作者机构完整覆盖：论文作者机构信息完整，无缺失、无对齐失败。",
        "- 部分覆盖：仅部分作者拿到机构信息。",
        "- 无作者机构数据：整篇论文没有可用作者机构信息。",
        "- 对齐失败：拿到作者和机构片段，但未能完成作者-机构对应。",
        "",
        "| 会议 | 论文总数 | 进入主数据层 | 比例 | 作者机构完整覆盖 | 比例 | 部分覆盖 | 无作者机构数据 | 对齐失败 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['conference']} | {row['total_papers']} | {row['in_main_data']} | {row['in_main_ratio']:.2f}\\% | {row['full_affiliation_coverage']} | {row['full_coverage_ratio']:.2f}\\% | {row['partial_affiliation_coverage']} | {row['papers_without_affiliation_data']} | {row['author_affiliation_match_failed']} |"
        )
    lines.append(
        f"| **总体** | **{overall['total_papers']}** | **{overall['in_main_data']}** | **{overall['in_main_ratio']:.2f}\\%** | **{overall['full_affiliation_coverage']}** | **{overall['full_coverage_ratio']:.2f}\\%** | **{overall['partial_affiliation_coverage']}** | **{overall['papers_without_affiliation_data']}** | **{overall['author_affiliation_match_failed']}** |"
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_tex(path: Path, rows: list[dict], overall: dict) -> None:
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{2020--2025年七个顶会论文自动抽取与作者机构覆盖率统计。进入主数据层表示论文已进入最终归一化主数据层；作者机构完整覆盖表示该论文作者机构信息完整，无缺失且无作者-机构对齐失败。}",
        r"\label{tab:auto-extraction-strict}",
        r"\small",
        r"\begin{tabular}{lrrrrrrrr}",
        r"\toprule",
        r"会议 & 论文总数 & 进入主数据层 & 比例(\%) & 作者机构完整覆盖 & 比例(\%) & 部分覆盖 & 无作者机构数据 & 对齐失败 \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(
            f"{row['conference']} & {row['total_papers']} & {row['in_main_data']} & {row['in_main_ratio']:.2f} & {row['full_affiliation_coverage']} & {row['full_coverage_ratio']:.2f} & {row['partial_affiliation_coverage']} & {row['papers_without_affiliation_data']} & {row['author_affiliation_match_failed']} \\\\"
        )
    lines.extend([
        r"\midrule",
        f"Overall & {overall['total_papers']} & {overall['in_main_data']} & {overall['in_main_ratio']:.2f} & {overall['full_affiliation_coverage']} & {overall['full_coverage_ratio']:.2f} & {overall['partial_affiliation_coverage']} & {overall['papers_without_affiliation_data']} & {overall['author_affiliation_match_failed']} \\\\",
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table*}",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_svg(path: Path, rows: list[dict], overall: dict) -> None:
    all_rows = rows + [overall]
    cols = [
        ("会议", 210),
        ("论文总数", 120),
        ("进入主数据层", 160),
        ("比例", 100),
        ("作者机构完整覆盖", 180),
        ("比例", 100),
        ("部分覆盖", 120),
        ("无作者机构数据", 160),
        ("对齐失败", 120),
    ]
    width = 1640
    row_h = 56
    height = 190 + row_h * (len(all_rows) + 1) + 40
    xs = [60]
    for _, w in cols[:-1]:
        xs.append(xs[-1] + w)
    total_w = sum(w for _, w in cols)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="100%" height="100%" fill="{COLORS["bg"]}"/>',
        f'<style>text{{font-family:{FONT}; fill:{COLORS["ink"]};}} .cap{{font-size:15px;fill:{COLORS["muted"]};letter-spacing:1px;}} .title{{font-size:28px;font-weight:700;}} .sub{{font-size:13px;fill:{COLORS["muted"]};}} .head{{font-size:14px;font-weight:700;}} .cell{{font-size:13px;}} .strong{{font-size:13px;font-weight:700;}}</style>',
        '<text x="60" y="42" class="cap">TABLE AS FIGURE</text>',
        '<text x="60" y="80" class="title">skills 自动抽取与作者机构覆盖率总表</text>',
        '<text x="60" y="110" class="sub">更严格口径：将“进入主数据层”和“作者机构完整覆盖”分开统计，避免总比例掩盖缺口。</text>',
    ]
    y0 = 145
    parts.append(f'<rect x="60" y="{y0}" width="{total_w}" height="{row_h}" fill="{COLORS["header"]}" stroke="{COLORS["line"]}" stroke-width="1"/>')
    for i, (label, _) in enumerate(cols):
        x = xs[i]
        parts.append(f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y0 + row_h * (len(all_rows) + 1)}" stroke="{COLORS["line"]}" stroke-width="1"/>')
        parts.append(f'<text x="{x + 12}" y="{y0 + 34}" class="head">{html.escape(label)}</text>')
    parts.append(f'<line x1="{60 + total_w}" y1="{y0}" x2="{60 + total_w}" y2="{y0 + row_h * (len(all_rows) + 1)}" stroke="{COLORS["line"]}" stroke-width="1"/>')
    for ridx, row in enumerate(all_rows, start=1):
        y = y0 + ridx * row_h
        fill = "#f8fafc" if row["conference"] == "OVERALL" else "#ffffff"
        parts.append(f'<rect x="60" y="{y}" width="{total_w}" height="{row_h}" fill="{fill}" stroke="{COLORS["line"]}" stroke-width="1"/>')
        vals = [
            "总体" if row["conference"] == "OVERALL" else row["conference"],
            str(row["total_papers"]),
            str(row["in_main_data"]),
            f'{row["in_main_ratio"]:.2f}%',
            str(row["full_affiliation_coverage"]),
            f'{row["full_coverage_ratio"]:.2f}%',
            str(row["partial_affiliation_coverage"]),
            str(row["papers_without_affiliation_data"]),
            str(row["author_affiliation_match_failed"]),
        ]
        klass = "strong" if row["conference"] == "OVERALL" else "cell"
        for i, val in enumerate(vals):
            parts.append(f'<text x="{xs[i] + 12}" y="{y + 34}" class="{klass}">{html.escape(val)}</text>')
    bottom = y0 + row_h * (len(all_rows) + 1)
    parts.append(f'<line x1="60" y1="{bottom}" x2="{60 + total_w}" y2="{bottom}" stroke="{COLORS["line"]}" stroke-width="1"/>')
    parts.append("</svg>\n")
    path.write_text("\n".join(parts), encoding="utf-8")


def write_manifest(path: Path, rows: list[dict], overall: dict) -> None:
    payload = {
        "topic": "skills 自动抽取与作者机构覆盖率",
        "strict_metric_definition": {
            "in_main_data": "进入最终归一化主数据层（paper_facts.csv）的论文数",
            "full_affiliation_coverage": "作者机构信息完整，无缺失且无作者-机构对齐失败的论文数",
            "partial_affiliation_coverage": "仅部分作者拿到机构信息的论文数",
            "papers_without_affiliation_data": "整篇论文没有可用作者机构信息的论文数",
            "author_affiliation_match_failed": "拿到作者与机构片段但未完成对齐的论文数",
        },
        "conference_count": len(rows),
        "overall": overall,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    ensure_dir(OUT)
    detail_rows, overall = collect_rows()
    summary_rows = aggregate_by_conference(detail_rows)
    fields = [
        "conference",
        "total_papers",
        "in_main_data",
        "in_main_ratio",
        "full_affiliation_coverage",
        "full_coverage_ratio",
        "partial_affiliation_coverage",
        "partial_ratio",
        "papers_without_affiliation_data",
        "no_aff_ratio",
        "author_affiliation_match_failed",
        "match_failed_ratio",
    ]
    write_csv(OUT / "strict_coverage_summary.csv", summary_rows + [overall], fields)
    write_csv(OUT / "strict_coverage_by_conference_year.csv", detail_rows, ["conference", "year"] + fields[1:])
    write_md(OUT / "strict_coverage_summary.md", summary_rows, overall)
    write_tex(OUT / "strict_coverage_summary.tex", summary_rows, overall)
    write_svg(OUT / "strict_coverage_summary.svg", summary_rows, overall)
    write_manifest(OUT / "strict_coverage_manifest.json", summary_rows, overall)


if __name__ == "__main__":
    main()
