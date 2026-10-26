from __future__ import annotations

import csv
import html
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERATED = ROOT / "generated-data"
BY_CONF = GENERATED / "extraction" / "output" / "by_conference"
OUT = GENERATED / "paper_tables_ambiguity"

FONT = '"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC","Source Han Sans SC",sans-serif'
AMBIG_REASONS = {
    "multi_affiliation_consensus",
    "shared_multi_affiliation_mixed_country",
    "shared_multi_affiliation_same_country",
    "multiple_countries",
}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def collect() -> tuple[list[dict], dict]:
    ambiguous_papers: dict[tuple[str, int], set[str]] = defaultdict(set)
    for path in BY_CONF.glob("*/author_affiliations_audit.csv"):
        with path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if row.get("classification_reason") in AMBIG_REASONS:
                    key = (row["conference"], int(row["year"]))
                    paper_key = row.get("paper_id") or row.get("article_tag") or row.get("title")
                    ambiguous_papers[key].add(paper_key)

    detail_rows: list[dict] = []
    conf_buckets: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    overall = defaultdict(int)
    for path in sorted(BY_CONF.glob("*/validation_report.json")):
        report = load_json(path)
        conf = str(report["conference"])
        year = int(report["year"])
        total = int(report.get("papers_count", 0) or 0)
        partial = int(report.get("papers_with_partial_affiliation_coverage", 0) or 0)
        no_data = int(report.get("papers_without_affiliation_data", 0) or 0)
        match_failed = int(report.get("papers_with_author_affiliation_match_failed", 0) or 0)
        ambiguous = len(ambiguous_papers.get((conf, year), set()))
        clean_full = total - partial - no_data - match_failed - ambiguous
        if clean_full < 0:
            clean_full = 0
        row = {
            "conference": conf,
            "year": year,
            "total_papers": total,
            "clean_full_coverage": clean_full,
            "clean_ratio": round(clean_full / total * 100, 2) if total else 0.0,
            "ambiguous_multiple_coverage": ambiguous,
            "ambiguous_ratio": round(ambiguous / total * 100, 2) if total else 0.0,
            "partial_affiliation_coverage": partial,
            "no_affiliation_data": no_data,
            "author_affiliation_match_failed": match_failed,
        }
        detail_rows.append(row)
        for key in row:
            if key not in {"conference", "year", "clean_ratio", "ambiguous_ratio"}:
                conf_buckets[conf][key] += int(row[key])
                overall[key] += int(row[key])

    summary_rows: list[dict] = []
    for conf in sorted(conf_buckets):
        b = conf_buckets[conf]
        total = b["total_papers"]
        summary_rows.append({
            "conference": conf,
            "total_papers": total,
            "clean_full_coverage": b["clean_full_coverage"],
            "clean_ratio": round(b["clean_full_coverage"] / total * 100, 2) if total else 0.0,
            "ambiguous_multiple_coverage": b["ambiguous_multiple_coverage"],
            "ambiguous_ratio": round(b["ambiguous_multiple_coverage"] / total * 100, 2) if total else 0.0,
            "partial_affiliation_coverage": b["partial_affiliation_coverage"],
            "no_affiliation_data": b["no_affiliation_data"],
            "author_affiliation_match_failed": b["author_affiliation_match_failed"],
        })

    overall_row = {
        "conference": "OVERALL",
        "total_papers": overall["total_papers"],
        "clean_full_coverage": overall["clean_full_coverage"],
        "clean_ratio": round(overall["clean_full_coverage"] / overall["total_papers"] * 100, 2),
        "ambiguous_multiple_coverage": overall["ambiguous_multiple_coverage"],
        "ambiguous_ratio": round(overall["ambiguous_multiple_coverage"] / overall["total_papers"] * 100, 2),
        "partial_affiliation_coverage": overall["partial_affiliation_coverage"],
        "no_affiliation_data": overall["no_affiliation_data"],
        "author_affiliation_match_failed": overall["author_affiliation_match_failed"],
    }
    return summary_rows, detail_rows, overall_row


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_md(path: Path, rows: list[dict], overall: dict) -> None:
    lines = [
        "# skills 自动抽取覆盖质量分层表",
        "",
        "分层口径说明：",
        "- 干净完整覆盖：作者机构信息完整，且不包含 `multiple` 类歧义覆盖。",
        "- 歧义覆盖（multiple）：已经拿到机构信息，但存在多机构、多国家或共享多机构等歧义，需要额外消歧。",
        "- 部分覆盖：仅部分作者拿到机构信息。",
        "- 无作者机构数据：整篇论文没有可用作者机构信息。",
        "- 对齐失败：拿到作者与机构片段，但未能完成作者-机构对应。",
        "",
        "| 会议 | 论文总数 | 干净完整覆盖 | 比例 | 歧义覆盖（multiple） | 比例 | 部分覆盖 | 无作者机构数据 | 对齐失败 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['conference']} | {row['total_papers']} | {row['clean_full_coverage']} | {row['clean_ratio']:.2f}\\% | {row['ambiguous_multiple_coverage']} | {row['ambiguous_ratio']:.2f}\\% | {row['partial_affiliation_coverage']} | {row['no_affiliation_data']} | {row['author_affiliation_match_failed']} |"
        )
    lines.append(
        f"| **总体** | **{overall['total_papers']}** | **{overall['clean_full_coverage']}** | **{overall['clean_ratio']:.2f}\\%** | **{overall['ambiguous_multiple_coverage']}** | **{overall['ambiguous_ratio']:.2f}\\%** | **{overall['partial_affiliation_coverage']}** | **{overall['no_affiliation_data']}** | **{overall['author_affiliation_match_failed']}** |"
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_tex(path: Path, rows: list[dict], overall: dict) -> None:
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{2020--2025年七个顶会作者机构覆盖质量分层统计。本文将包含多机构、多国家或共享多机构等歧义情况的论文单列为“歧义覆盖（multiple）”，不计入“干净完整覆盖”。}",
        r"\label{tab:coverage-with-ambiguity}",
        r"\small",
        r"\begin{tabular}{lrrrrrrrr}",
        r"\toprule",
        r"会议 & 论文总数 & 干净完整覆盖 & 比例(\%) & 歧义覆盖（multiple） & 比例(\%) & 部分覆盖 & 无作者机构数据 & 对齐失败 \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(
            f"{row['conference']} & {row['total_papers']} & {row['clean_full_coverage']} & {row['clean_ratio']:.2f} & {row['ambiguous_multiple_coverage']} & {row['ambiguous_ratio']:.2f} & {row['partial_affiliation_coverage']} & {row['no_affiliation_data']} & {row['author_affiliation_match_failed']} \\\\"
        )
    lines.extend([
        r"\midrule",
        f"Overall & {overall['total_papers']} & {overall['clean_full_coverage']} & {overall['clean_ratio']:.2f} & {overall['ambiguous_multiple_coverage']} & {overall['ambiguous_ratio']:.2f} & {overall['partial_affiliation_coverage']} & {overall['no_affiliation_data']} & {overall['author_affiliation_match_failed']} \\\\",
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
        ("干净完整覆盖", 160),
        ("比例", 95),
        ("歧义覆盖（multiple）", 200),
        ("比例", 95),
        ("部分覆盖", 120),
        ("无作者机构数据", 150),
        ("对齐失败", 110),
    ]
    width = 1600
    row_h = 56
    height = 190 + row_h * (len(all_rows) + 1) + 40
    xs = [60]
    for _, w in cols[:-1]:
        xs.append(xs[-1] + w)
    total_w = sum(w for _, w in cols)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<style>text{{font-family:{FONT}; fill:#1f2937;}} .cap{{font-size:15px;fill:#667085;letter-spacing:1px;}} .title{{font-size:28px;font-weight:700;}} .sub{{font-size:13px;fill:#667085;}} .head{{font-size:14px;font-weight:700;}} .cell{{font-size:13px;}} .strong{{font-size:13px;font-weight:700;}}</style>',
        '<text x="60" y="42" class="cap">TABLE AS FIGURE</text>',
        '<text x="60" y="80" class="title">skills 自动抽取覆盖质量分层表</text>',
        '<text x="60" y="110" class="sub">将 “multiple” 类歧义覆盖从完整成功中拆出后，覆盖质量会更接近真实情况。</text>',
    ]
    y0 = 145
    parts.append(f'<rect x="60" y="{y0}" width="{total_w}" height="{row_h}" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1"/>')
    for i, (label, _) in enumerate(cols):
        x = xs[i]
        parts.append(f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y0 + row_h * (len(all_rows) + 1)}" stroke="#cbd5e1" stroke-width="1"/>')
        parts.append(f'<text x="{x + 12}" y="{y0 + 34}" class="head">{html.escape(label)}</text>')
    parts.append(f'<line x1="{60 + total_w}" y1="{y0}" x2="{60 + total_w}" y2="{y0 + row_h * (len(all_rows) + 1)}" stroke="#cbd5e1" stroke-width="1"/>')
    for ridx, row in enumerate(all_rows, start=1):
        y = y0 + ridx * row_h
        fill = "#f8fafc" if row["conference"] == "OVERALL" else "#ffffff"
        parts.append(f'<rect x="60" y="{y}" width="{total_w}" height="{row_h}" fill="{fill}" stroke="#cbd5e1" stroke-width="1"/>')
        vals = [
            "总体" if row["conference"] == "OVERALL" else row["conference"],
            str(row["total_papers"]),
            str(row["clean_full_coverage"]),
            f'{row["clean_ratio"]:.2f}%',
            str(row["ambiguous_multiple_coverage"]),
            f'{row["ambiguous_ratio"]:.2f}%',
            str(row["partial_affiliation_coverage"]),
            str(row["no_affiliation_data"]),
            str(row["author_affiliation_match_failed"]),
        ]
        klass = "strong" if row["conference"] == "OVERALL" else "cell"
        for i, val in enumerate(vals):
            parts.append(f'<text x="{xs[i] + 12}" y="{y + 34}" class="{klass}">{html.escape(val)}</text>')
    bottom = y0 + row_h * (len(all_rows) + 1)
    parts.append(f'<line x1="60" y1="{bottom}" x2="{60 + total_w}" y2="{bottom}" stroke="#cbd5e1" stroke-width="1"/>')
    parts.append("</svg>\n")
    path.write_text("\n".join(parts), encoding="utf-8")


def write_manifest(path: Path, rows: list[dict], overall: dict) -> None:
    payload = {
        "topic": "skills 自动抽取覆盖质量分层",
        "ambiguous_reasons": sorted(AMBIG_REASONS),
        "overall": overall,
        "conference_count": len(rows),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    ensure_dir(OUT)
    summary_rows, detail_rows, overall = collect()
    fields = [
        "conference",
        "total_papers",
        "clean_full_coverage",
        "clean_ratio",
        "ambiguous_multiple_coverage",
        "ambiguous_ratio",
        "partial_affiliation_coverage",
        "no_affiliation_data",
        "author_affiliation_match_failed",
    ]
    write_csv(OUT / "ambiguity_coverage_summary.csv", summary_rows + [overall], fields)
    write_csv(OUT / "ambiguity_coverage_by_conference_year.csv", detail_rows, ["conference", "year"] + fields[1:])
    write_md(OUT / "ambiguity_coverage_summary.md", summary_rows, overall)
    write_tex(OUT / "ambiguity_coverage_summary.tex", summary_rows, overall)
    write_svg(OUT / "ambiguity_coverage_summary.svg", summary_rows, overall)
    write_manifest(OUT / "ambiguity_coverage_manifest.json", summary_rows, overall)


if __name__ == "__main__":
    main()
