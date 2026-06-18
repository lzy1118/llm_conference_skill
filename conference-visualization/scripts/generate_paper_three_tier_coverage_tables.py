from __future__ import annotations

import csv
import html
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERATED = ROOT / "generated-data"
BY_CONF = GENERATED / "extraction" / "output" / "by_conference"
OUT = GENERATED / "paper_tables_three_tier"
OFFICIAL_TOTAL_OVERRIDES = {
    ("USENIX_SECURITY", 2025): 407,
}

FONT = '"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC","Source Han Sans SC",sans-serif'
CLEAR_SAME_COUNTRY_MULTI = {
    "multi_affiliation_consensus",
    "shared_multi_affiliation_same_country",
}
AMBIGUOUS_MULTI = {
    "shared_multi_affiliation_mixed_country",
    "multiple_countries",
}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def official_total(conf: str, year: int, reported_total: int) -> int:
    return int(OFFICIAL_TOTAL_OVERRIDES.get((conf, year), reported_total))


def collect() -> tuple[list[dict], list[dict], dict]:
    detail_rows: list[dict] = []
    by_conf: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    overall = defaultdict(int)

    for report_path in sorted(BY_CONF.glob("*/validation_report.json")):
        report = load_json(report_path)
        conf = str(report["conference"])
        year = int(report["year"])
        total = official_total(conf, year, int(report.get("papers_count", 0) or 0))
        partial = int(report.get("papers_with_partial_affiliation_coverage", 0) or 0)
        no_data = int(report.get("papers_without_affiliation_data", 0) or 0)
        match_failed = int(report.get("papers_with_author_affiliation_match_failed", 0) or 0)

        paper_reasons: dict[str, set[str]] = defaultdict(set)
        audit_path = report_path.parent / "author_affiliations_audit.csv"
        with audit_path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                paper_key = row.get("paper_id") or row.get("title") or row.get("article_tag") or ""
                paper_reasons[paper_key].add(row.get("classification_reason", ""))

        single_clean = 0
        same_country_multi_clear = 0
        unresolved_ambiguity = 0
        for _, reasons in paper_reasons.items():
            if reasons & AMBIGUOUS_MULTI:
                unresolved_ambiguity += 1
            elif reasons & CLEAR_SAME_COUNTRY_MULTI:
                same_country_multi_clear += 1
            else:
                single_clean += 1

        single_clean = max(single_clean - partial - no_data - match_failed, 0)
        row = {
            "conference": conf,
            "year": year,
            "total_papers": total,
            "single_clean_coverage": single_clean,
            "single_clean_ratio": round(single_clean / total * 100, 2) if total else 0.0,
            "same_country_multi_clear": same_country_multi_clear,
            "same_country_multi_ratio": round(same_country_multi_clear / total * 100, 2) if total else 0.0,
            "unresolved_multi_ambiguity": unresolved_ambiguity,
            "unresolved_multi_ratio": round(unresolved_ambiguity / total * 100, 2) if total else 0.0,
            "partial_affiliation_coverage": partial,
            "no_affiliation_data": no_data,
            "author_affiliation_match_failed": match_failed,
        }
        detail_rows.append(row)
        for key, value in row.items():
            if key not in {"conference", "year", "single_clean_ratio", "same_country_multi_ratio", "unresolved_multi_ratio"}:
                by_conf[conf][key] += int(value)
                overall[key] += int(value)

    summary_rows: list[dict] = []
    for conf in sorted(by_conf):
        b = by_conf[conf]
        total = b["total_papers"]
        summary_rows.append({
            "conference": conf,
            "total_papers": total,
            "single_clean_coverage": b["single_clean_coverage"],
            "single_clean_ratio": round(b["single_clean_coverage"] / total * 100, 2) if total else 0.0,
            "same_country_multi_clear": b["same_country_multi_clear"],
            "same_country_multi_ratio": round(b["same_country_multi_clear"] / total * 100, 2) if total else 0.0,
            "unresolved_multi_ambiguity": b["unresolved_multi_ambiguity"],
            "unresolved_multi_ratio": round(b["unresolved_multi_ambiguity"] / total * 100, 2) if total else 0.0,
            "partial_affiliation_coverage": b["partial_affiliation_coverage"],
            "no_affiliation_data": b["no_affiliation_data"],
            "author_affiliation_match_failed": b["author_affiliation_match_failed"],
        })

    overall_row = {
        "conference": "OVERALL",
        "total_papers": overall["total_papers"],
        "single_clean_coverage": overall["single_clean_coverage"],
        "single_clean_ratio": round(overall["single_clean_coverage"] / overall["total_papers"] * 100, 2),
        "same_country_multi_clear": overall["same_country_multi_clear"],
        "same_country_multi_ratio": round(overall["same_country_multi_clear"] / overall["total_papers"] * 100, 2),
        "unresolved_multi_ambiguity": overall["unresolved_multi_ambiguity"],
        "unresolved_multi_ratio": round(overall["unresolved_multi_ambiguity"] / overall["total_papers"] * 100, 2),
        "partial_affiliation_coverage": overall["partial_affiliation_coverage"],
        "no_affiliation_data": overall["no_affiliation_data"],
        "author_affiliation_match_failed": overall["author_affiliation_match_failed"],
    }
    overall_row["success_total"] = overall_row["single_clean_coverage"] + overall_row["same_country_multi_clear"]
    overall_row["success_ratio"] = round(overall_row["success_total"] / overall_row["total_papers"] * 100, 2)
    return summary_rows, detail_rows, overall_row


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_md(path: Path, rows: list[dict], overall: dict) -> None:
    lines = [
        "# skills 作者机构覆盖三层口径总表",
        "",
        "口径说明：",
        "- 单机构干净覆盖：作者机构完整，且不存在多机构歧义。",
        "- 同国多机构清晰覆盖：作者存在多机构，但都落在同一国家，视为有效成功层级。",
        "- 未消歧多机构歧义：多机构/多国家仍需进一步消歧。",
        "- 部分覆盖：仅部分作者拿到机构信息。",
        "- 无作者机构数据：整篇论文没有可用作者机构信息。",
        "- 对齐失败：拿到作者与机构片段，但未完成对应。",
        "",
        f"总体有效成功率（前两层合并）= **{overall['success_total']} / {overall['total_papers']} = {overall['success_ratio']:.2f}\\%**。",
        "",
        "| 会议 | 论文总数 | 单机构干净覆盖 | 比例 | 同国多机构清晰覆盖 | 比例 | 未消歧多机构歧义 | 部分覆盖 | 无作者机构数据 | 对齐失败 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['conference']} | {row['total_papers']} | {row['single_clean_coverage']} | {row['single_clean_ratio']:.2f}\\% | {row['same_country_multi_clear']} | {row['same_country_multi_ratio']:.2f}\\% | {row['unresolved_multi_ambiguity']} | {row['partial_affiliation_coverage']} | {row['no_affiliation_data']} | {row['author_affiliation_match_failed']} |"
        )
    lines.append(
        f"| **总体** | **{overall['total_papers']}** | **{overall['single_clean_coverage']}** | **{overall['single_clean_ratio']:.2f}\\%** | **{overall['same_country_multi_clear']}** | **{overall['same_country_multi_ratio']:.2f}\\%** | **{overall['unresolved_multi_ambiguity']}** | **{overall['partial_affiliation_coverage']}** | **{overall['no_affiliation_data']}** | **{overall['author_affiliation_match_failed']}** |"
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_tex(path: Path, rows: list[dict], overall: dict) -> None:
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{2020--2025年七个顶会作者机构覆盖三层口径统计。本文将“同国且多机构但已清晰抽到”的论文单列为有效成功层级，而不再全部压入歧义覆盖。}",
        r"\label{tab:coverage-three-tier}",
        r"\small",
        r"\begin{tabular}{lrrrrrrrrr}",
        r"\toprule",
        r"会议 & 论文总数 & 单机构干净覆盖 & 比例(\%) & 同国多机构清晰覆盖 & 比例(\%) & 未消歧多机构歧义 & 部分覆盖 & 无作者机构数据 & 对齐失败 \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(
            f"{row['conference']} & {row['total_papers']} & {row['single_clean_coverage']} & {row['single_clean_ratio']:.2f} & {row['same_country_multi_clear']} & {row['same_country_multi_ratio']:.2f} & {row['unresolved_multi_ambiguity']} & {row['partial_affiliation_coverage']} & {row['no_affiliation_data']} & {row['author_affiliation_match_failed']} \\\\"
        )
    lines.extend([
        r"\midrule",
        f"Overall & {overall['total_papers']} & {overall['single_clean_coverage']} & {overall['single_clean_ratio']:.2f} & {overall['same_country_multi_clear']} & {overall['same_country_multi_ratio']:.2f} & {overall['unresolved_multi_ambiguity']} & {overall['partial_affiliation_coverage']} & {overall['no_affiliation_data']} & {overall['author_affiliation_match_failed']} \\\\",
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table*}",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_svg(path: Path, rows: list[dict], overall: dict) -> None:
    all_rows = rows + [overall]
    cols = [
        ("会议", 180),
        ("论文总数", 105),
        ("单机构干净覆盖", 150),
        ("比例", 85),
        ("同国多机构清晰覆盖", 180),
        ("比例", 85),
        ("未消歧多机构歧义", 160),
        ("部分覆盖", 95),
        ("无作者机构数据", 130),
        ("对齐失败", 95),
    ]
    xs = [60]
    for _, w in cols[:-1]:
        xs.append(xs[-1] + w)
    total_w = sum(w for _, w in cols)
    width = 1540
    row_h = 54
    height = 200 + row_h * (len(all_rows) + 1) + 40
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<style>text{{font-family:{FONT}; fill:#1f2937;}} .cap{{font-size:15px;fill:#667085;letter-spacing:1px;}} .title{{font-size:28px;font-weight:700;}} .sub{{font-size:13px;fill:#667085;}} .head{{font-size:14px;font-weight:700;}} .cell{{font-size:13px;}} .strong{{font-size:13px;font-weight:700;}}</style>',
        '<text x="60" y="42" class="cap">TABLE AS FIGURE</text>',
        '<text x="60" y="80" class="title">skills 作者机构覆盖三层口径总表</text>',
        f'<text x="60" y="110" class="sub">将“同国且多机构但已清晰抽到”单列为成功层级后，总体有效成功率为 {overall["success_ratio"]:.2f}%。</text>',
    ]
    y0 = 145
    parts.append(f'<rect x="60" y="{y0}" width="{total_w}" height="{row_h}" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1"/>')
    for i, (label, _) in enumerate(cols):
        x = xs[i]
        parts.append(f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y0 + row_h * (len(all_rows) + 1)}" stroke="#cbd5e1" stroke-width="1"/>')
        parts.append(f'<text x="{x + 10}" y="{y0 + 33}" class="head">{html.escape(label)}</text>')
    parts.append(f'<line x1="{60 + total_w}" y1="{y0}" x2="{60 + total_w}" y2="{y0 + row_h * (len(all_rows) + 1)}" stroke="#cbd5e1" stroke-width="1"/>')
    for ridx, row in enumerate(all_rows, start=1):
        y = y0 + ridx * row_h
        fill = "#f8fafc" if row["conference"] == "OVERALL" else "#ffffff"
        parts.append(f'<rect x="60" y="{y}" width="{total_w}" height="{row_h}" fill="{fill}" stroke="#cbd5e1" stroke-width="1"/>')
        vals = [
            "总体" if row["conference"] == "OVERALL" else row["conference"],
            str(row["total_papers"]),
            str(row["single_clean_coverage"]),
            f'{row["single_clean_ratio"]:.2f}%',
            str(row["same_country_multi_clear"]),
            f'{row["same_country_multi_ratio"]:.2f}%',
            str(row["unresolved_multi_ambiguity"]),
            str(row["partial_affiliation_coverage"]),
            str(row["no_affiliation_data"]),
            str(row["author_affiliation_match_failed"]),
        ]
        klass = "strong" if row["conference"] == "OVERALL" else "cell"
        for i, val in enumerate(vals):
            parts.append(f'<text x="{xs[i] + 10}" y="{y + 33}" class="{klass}">{html.escape(val)}</text>')
    parts.append("</svg>\n")
    path.write_text("\n".join(parts), encoding="utf-8")


def write_manifest(path: Path, rows: list[dict], overall: dict) -> None:
    payload = {
        "topic": "skills 作者机构覆盖三层口径",
        "tier_definition": {
            "single_clean_coverage": "作者机构完整，且不存在多机构歧义",
            "same_country_multi_clear": "同国且多机构但已清晰抽到",
            "unresolved_multi_ambiguity": "多机构/多国家仍需进一步消歧",
        },
        "conference_count": len(rows),
        "overall": overall,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    ensure_dir(OUT)
    summary_rows, detail_rows, overall = collect()
    fields = [
        "conference",
        "total_papers",
        "single_clean_coverage",
        "single_clean_ratio",
        "same_country_multi_clear",
        "same_country_multi_ratio",
        "unresolved_multi_ambiguity",
        "unresolved_multi_ratio",
        "partial_affiliation_coverage",
        "no_affiliation_data",
        "author_affiliation_match_failed",
    ]
    write_csv(OUT / "three_tier_coverage_summary.csv", summary_rows + [overall], fields)
    write_csv(OUT / "three_tier_coverage_by_conference_year.csv", detail_rows, ["conference", "year"] + fields[1:])
    write_md(OUT / "three_tier_coverage_summary.md", summary_rows, overall)
    write_tex(OUT / "three_tier_coverage_summary.tex", summary_rows, overall)
    write_svg(OUT / "three_tier_coverage_summary.svg", summary_rows, overall)
    write_manifest(OUT / "three_tier_coverage_manifest.json", summary_rows, overall)


if __name__ == "__main__":
    main()
