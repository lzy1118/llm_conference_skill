from __future__ import annotations

import html
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERATED = ROOT / "generated-data"
EXTRACTION_BY_CONF = GENERATED / "extraction" / "output" / "by_conference"
NORMALIZED_DIR = GENERATED / "normalized"
ANALYSIS_DIR = GENERATED / "analysis"
CFP_DIR = GENERATED / "cfp" / "output"
OUTPUT_DIR = GENERATED / "paper_figures_cn"

FONT_FAMILY = '"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC","Source Han Sans SC",sans-serif'
COLORS = {
    "bg": "#fcfbf7",
    "ink": "#1f2937",
    "muted": "#5b6472",
    "line": "#94a3b8",
    "grid": "#d8dee9",
    "blue": "#2b6cb0",
    "teal": "#0f766e",
    "orange": "#c05621",
    "green": "#2f855a",
    "red": "#c53030",
    "gold": "#b7791f",
    "grayfill": "#eef2f7",
}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def collect_metrics() -> dict:
    reports = []
    for path in sorted(EXTRACTION_BY_CONF.glob("*/validation_report.json")):
        report = load_json(path)
        report["conference_key"] = path.parent.name
        reports.append(report)

    by_conf = defaultdict(int)
    by_conf_year = defaultdict(dict)
    for report in reports:
        conf = str(report.get("conference", ""))
        year = int(report.get("year", 0) or 0)
        papers = int(report.get("papers_count", 0) or 0)
        by_conf[conf] += papers
        by_conf_year[conf][year] = papers

    normalization = load_json(NORMALIZED_DIR / "normalization_report.json")
    audit = load_json(ANALYSIS_DIR / "audit" / "normalized" / "quality_audit.json")
    cfp = load_json(CFP_DIR / "cfp_validation_report.json")

    return {
        "conference_years": len(reports),
        "papers_total": sum(int(r.get("papers_count", 0) or 0) for r in reports),
        "classified_rows_total": sum(int(r.get("classified_author_rows", 0) or 0) for r in reports),
        "unresolved_country_total": sum(int(r.get("unresolved_country_rows", 0) or 0) for r in reports),
        "papers_without_affiliation_data": sum(int(r.get("papers_without_affiliation_data", 0) or 0) for r in reports),
        "partial_affiliation": sum(int(r.get("papers_with_partial_affiliation_coverage", 0) or 0) for r in reports),
        "author_match_failed": sum(int(r.get("papers_with_author_affiliation_match_failed", 0) or 0) for r in reports),
        "by_conf": dict(sorted(by_conf.items())),
        "by_conf_year": {key: dict(sorted(value.items())) for key, value in sorted(by_conf_year.items())},
        "normalization": normalization,
        "audit": audit,
        "cfp": cfp,
    }


def svg_header(width: int, height: int) -> list[str]:
    return [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="100%" height="100%" fill="{COLORS["bg"]}"/>',
        f'<style>text{{font-family:{FONT_FAMILY}; fill:{COLORS["ink"]};}} .title{{font-size:30px;font-weight:700;}} .subtitle{{font-size:15px;fill:{COLORS["muted"]};}} .boxtitle{{font-size:18px;font-weight:700;}} .body{{font-size:13px;}} .small{{font-size:11px;fill:{COLORS["muted"]};}} .caption{{font-size:12px;fill:{COLORS["muted"]};letter-spacing:1px;}}</style>',
    ]


def svg_footer(parts: list[str]) -> str:
    return "\n".join(parts + ["</svg>"]) + "\n"


def add_text(parts: list[str], x: float, y: float, text: str, klass: str = "body", color: str | None = None) -> None:
    extra = f' fill="{color}"' if color else ""
    parts.append(f'<text x="{x}" y="{y}" class="{klass}"{extra}>{html.escape(text)}</text>')


def add_multiline(parts: list[str], x: float, y: float, lines: list[str], line_gap: int = 26, klass: str = "body", color: str | None = None) -> None:
    for idx, line in enumerate(lines):
        add_text(parts, x, y + idx * line_gap, line, klass=klass, color=color)


def add_box(parts: list[str], x: float, y: float, w: float, h: float, stroke: str, title: str, lines: list[str]) -> None:
    parts.append(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="22" ry="22" fill="#ffffff" stroke="{stroke}" stroke-width="2.5"/>'
    )
    parts.append(f'<line x1="{x}" y1="{y + 58}" x2="{x + w}" y2="{y + 58}" stroke="{stroke}" stroke-width="1.5" opacity="0.35"/>')
    add_text(parts, x + 26, y + 46, title, "boxtitle", stroke)
    add_multiline(parts, x + 26, y + 92, lines, line_gap=28, klass="body")


def add_arrow(parts: list[str], x1: float, y1: float, x2: float, y2: float, color: str | None = None, curved: bool = False) -> None:
    color = color or COLORS["line"]
    if curved:
        mx = (x1 + x2) / 2
        my = min(y1, y2) - 70
        parts.append(f'<path d="M {x1} {y1} Q {mx} {my} {x2} {y2}" fill="none" stroke="{color}" stroke-width="3"/>')
    else:
        parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="3"/>')
    parts.append(
        f'<polygon points="{x2},{y2} {x2 - 12},{y2 - 6} {x2 - 12},{y2 + 6}" fill="{color}" transform="rotate({0 if x2>=x1 else 180},{x2},{y2})"/>'
    )


def figure1_workflow(metrics: dict) -> None:
    width, height = 1600, 980
    parts = svg_header(width, height)
    add_text(parts, 70, 48, "FIGURE 1", "caption")
    add_text(parts, 70, 88, "技能化自动化工作流系统", "title")
    add_text(parts, 70, 126, "以统一数据契约连接抽取、治理、分析与反馈修复。", "subtitle")

    add_box(parts, 80, 210, 280, 220, COLORS["blue"], "1. 数据来源", [
        "官网 / CFP",
        "DBLP 元数据",
        "DOI / PDF / 网页",
        "跨会跨年输入",
    ])
    add_box(parts, 420, 210, 280, 220, COLORS["teal"], "2. 技能化抽取", [
        "会议族抽取 skill",
        "作者-机构对齐",
        "国家识别与补源",
        "局部重跑修复",
    ])
    add_box(parts, 760, 210, 250, 220, COLORS["orange"], "3. 治理化资产", [
        "raw / interim / output",
        "paper_facts",
        "author_affiliation_facts",
        "institution_dim",
    ])
    add_box(parts, 1070, 210, 240, 220, COLORS["green"], "4. 分析交付", [
        "国别 / 机构 / 作者",
        "趋势与合作分析",
        "图表与版本产物",
        "论文写作复用",
    ])
    add_box(parts, 220, 520, 430, 196, COLORS["teal"], "统一数据契约", [
        "共享事实表连接抽取、治理与分析",
        "统一 paper / author / institution 键",
        "支撑跨会跨年一致口径",
    ])
    add_box(parts, 720, 520, 540, 210, COLORS["red"], "5. 质量反馈闭环", [
        "覆盖审计 / 低置信度审计 / Unknown 国家审计 / review queue",
        f"覆盖 {metrics['conference_years']} 个 conference-year；抽取 {metrics['papers_total']} 篇；标准化 {metrics['normalization']['paper_count']} 篇",
        f"CFP 事件覆盖 {metrics['cfp']['conference_years_with_events']}/42，支持“修复 -> 重跑 -> 再审计”",
    ])

    add_arrow(parts, 360, 320, 420, 320)
    add_arrow(parts, 700, 320, 760, 320)
    add_arrow(parts, 1010, 320, 1070, 320)
    add_arrow(parts, 560, 430, 430, 520, COLORS["teal"])
    add_arrow(parts, 1190, 430, 1010, 520, COLORS["green"])
    add_arrow(parts, 650, 618, 720, 618, COLORS["line"])
    parts.append(f'<path d="M 990 700 Q 760 810 330 430" fill="none" stroke="{COLORS["red"]}" stroke-width="3"/>')
    parts.append(f'<polygon points="330,430 344,424 341,439" fill="{COLORS["red"]}"/>')

    add_text(parts, 80, 470, "证据进入，结构输出", "small")
    add_text(parts, 690, 824, "质量审计将问题重新送回规则与技能层，形成稳定的迭代治理回路。", "small")

    write_text(OUTPUT_DIR / "图1_技能化自动化工作流系统.svg", svg_footer(parts))


def heat_color(value: float, max_value: float) -> str:
    start = (236, 244, 246)
    end = (15, 118, 110)
    ratio = 0 if max_value <= 0 else value / max_value
    rgb = tuple(int(start[i] + (end[i] - start[i]) * ratio) for i in range(3))
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def figure2_overview(metrics: dict) -> None:
    width, height = 1680, 1180
    parts = svg_header(width, height)
    add_text(parts, 70, 48, "FIGURE 2", "caption")
    add_text(parts, 70, 88, "实验范围与运行结果总览", "title")
    add_text(parts, 70, 126, "覆盖规模、产物规模与剩余质量缺口的统一快照。", "subtitle")

    # Panel A heatmap
    px, py, pw, ph = 70, 170, 650, 430
    parts.append(f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="18" fill="#ffffff" stroke="{COLORS["grid"]}" stroke-width="2"/>')
    add_text(parts, px + 24, py + 38, "A. 七会年度覆盖热力图", "boxtitle", COLORS["ink"])
    conferences = ["ASIACRYPT", "CRYPTO", "EUROCRYPT", "CCS", "IEEE_S&P", "NDSS", "USENIX_SECURITY"]
    years = [2020, 2021, 2022, 2023, 2024, 2025]
    maxv = max(v for conf in metrics["by_conf_year"].values() for v in conf.values())
    cell_w, cell_h = 80, 58
    grid_x, grid_y = px + 150, py + 90
    for c_idx, conf in enumerate(conferences):
        add_text(parts, px + 24, grid_y + c_idx * cell_h + 36, conf, "body")
        for y_idx, year in enumerate(years):
            val = metrics["by_conf_year"][conf][year]
            cx = grid_x + y_idx * cell_w
            cy = grid_y + c_idx * cell_h
            color = heat_color(val, maxv)
            parts.append(f'<rect x="{cx}" y="{cy}" width="{cell_w - 4}" height="{cell_h - 4}" fill="{color}" rx="8"/>')
            add_text(parts, cx + 22, cy + 36, str(val), "body", "#ffffff" if val > maxv * 0.45 else COLORS["ink"])
    for y_idx, year in enumerate(years):
        add_text(parts, grid_x + y_idx * cell_w + 18, grid_y - 16, str(year), "body")

    # Panel B bars
    bx, by, bw, bh = 810, 170, 800, 430
    parts.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="18" fill="#ffffff" stroke="{COLORS["grid"]}" stroke-width="2"/>')
    add_text(parts, bx + 24, by + 38, "B. 各会议累计论文规模", "boxtitle", COLORS["ink"])
    conf_order = sorted(metrics["by_conf"].items(), key=lambda item: item[1], reverse=True)
    max_bar = max(v for _, v in conf_order)
    bar_x, bar_y = bx + 210, by + 86
    for idx, (name, val) in enumerate(conf_order):
        y = bar_y + idx * 46
        parts.append(f'<rect x="{bar_x}" y="{y}" width="500" height="26" rx="8" fill="{COLORS["grayfill"]}"/>')
        fill_w = int(500 * val / max_bar)
        parts.append(f'<rect x="{bar_x}" y="{y}" width="{fill_w}" height="26" rx="8" fill="{COLORS["blue"]}"/>')
        add_text(parts, bx + 24, y + 18, name, "body")
        add_text(parts, bar_x + fill_w + 12, y + 18, str(val), "body")

    # Panel C KPI
    cx, cy, cw, ch = 70, 650, 730, 420
    parts.append(f'<rect x="{cx}" y="{cy}" width="{cw}" height="{ch}" rx="18" fill="#ffffff" stroke="{COLORS["grid"]}" stroke-width="2"/>')
    add_text(parts, cx + 24, cy + 38, "C. 端到端产物规模", "boxtitle", COLORS["ink"])
    kpis = [
        ("会议年份", metrics["conference_years"], COLORS["gold"]),
        ("抽取论文", metrics["papers_total"], COLORS["teal"]),
        ("标准化论文", metrics["normalization"]["paper_count"], COLORS["blue"]),
        ("作者-机构事实行", metrics["normalization"]["normalized_rows"], COLORS["green"]),
        ("CFP 事件完整年份", metrics["cfp"]["conference_years_with_events"], COLORS["orange"]),
    ]
    for idx, (label, value, color) in enumerate(kpis):
        x = cx + 34 + (idx % 2) * 345
        y = cy + 86 + (idx // 2) * 108
        w = 300
        h = 74
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="#fafafa" stroke="{color}" stroke-width="2"/>')
        add_text(parts, x + 18, y + 28, label, "body", COLORS["muted"])
        add_text(parts, x + 18, y + 58, str(value), "boxtitle", color)

    # Panel D quality gaps
    dx, dy, dw, dh = 860, 650, 750, 420
    parts.append(f'<rect x="{dx}" y="{dy}" width="{dw}" height="{dh}" rx="18" fill="#ffffff" stroke="{COLORS["grid"]}" stroke-width="2"/>')
    add_text(parts, dx + 24, dy + 38, "D. 当前剩余质量缺口", "boxtitle", COLORS["ink"])
    gaps = [
        ("Unknown 国家", metrics["audit"]["normalized_checks"]["unknown_country_rows"], COLORS["red"]),
        ("低置信度行", metrics["audit"]["normalized_checks"]["low_confidence_rows"], COLORS["orange"]),
        ("机构需复核", metrics["audit"]["institution_dim_checks"]["needs_review_rows"], COLORS["gold"]),
        ("机构 Unknown 国家", metrics["audit"]["institution_dim_checks"]["unknown_country_rows"], COLORS["muted"]),
    ]
    max_gap = max(v for _, v, _ in gaps)
    gx = dx + 220
    gy = dy + 94
    for idx, (label, value, color) in enumerate(gaps):
        y = gy + idx * 64
        parts.append(f'<rect x="{gx}" y="{y}" width="430" height="30" rx="8" fill="{COLORS["grayfill"]}"/>')
        parts.append(f'<rect x="{gx}" y="{y}" width="{int(430 * value / max_gap)}" height="30" rx="8" fill="{color}"/>')
        add_text(parts, dx + 24, y + 20, label, "body")
        add_text(parts, gx + int(430 * value / max_gap) + 12, y + 20, str(value), "body")

    add_text(parts, 70, 1135, "基线：7 个会议、42 个 conference-year、7075 篇论文、35873 条作者-机构事实。", "small")
    write_text(OUTPUT_DIR / "图2_实验范围与运行结果总览.svg", svg_footer(parts))


def figure3_contract(metrics: dict) -> None:
    width, height = 1600, 930
    parts = svg_header(width, height)
    add_text(parts, 70, 48, "FIGURE 3", "caption")
    add_text(parts, 70, 88, "统一数据契约支撑可复用分析", "title")
    add_text(parts, 70, 126, "共享事实层吸收上游异构性，并为下游统计与治理修复提供稳定中枢。", "subtitle")

    add_box(parts, 90, 210, 340, 238, COLORS["blue"], "上游会议级产物", [
        "逐会议 extraction output",
        "author_affiliations / audit",
        "validation_report / CFP",
        "保留可追溯证据",
    ])
    add_box(parts, 590, 178, 400, 282, COLORS["teal"], "标准化共享事实层", [
        f"paper_facts：{metrics['normalization']['paper_count']} 行",
        f"author_affiliation_facts：{metrics['normalization']['normalized_rows']} 行",
        f"institution_dim：{metrics['normalization']['institution_count']} 行",
        "统一键：paper / author / institution",
    ])
    add_box(parts, 1150, 210, 320, 238, COLORS["green"], "下游复用分析层", [
        "国家 / 机构 / 作者统计",
        "趋势与合作分析",
        "可视化与版本归档",
        "论文写作复用",
    ])

    add_box(parts, 220, 590, 330, 176, COLORS["red"], "治理控制", [
        "机构标准库 / alias 表",
        "override 规则 / 人工复核",
        "覆盖率与错配审计",
    ])
    add_box(parts, 640, 588, 300, 184, COLORS["gold"], "复用价值", [
        "避免重复解析原始数据",
        "保持跨会跨年口径一致",
        "让修复优先作用于中间层",
    ])
    add_box(parts, 1030, 590, 320, 176, COLORS["orange"], "当前状态", [
        f"Unknown 国家：{metrics['audit']['normalized_checks']['unknown_country_rows']}",
        f"低置信度：{metrics['audit']['normalized_checks']['low_confidence_rows']}",
        f"CFP 覆盖：{metrics['cfp']['conference_years_with_events']}/42",
    ])

    add_arrow(parts, 430, 329, 590, 329)
    add_arrow(parts, 990, 329, 1150, 329)
    add_arrow(parts, 385, 590, 650, 460, COLORS["red"])
    add_arrow(parts, 790, 588, 790, 460, COLORS["gold"])
    add_arrow(parts, 1190, 590, 960, 460, COLORS["orange"])
    add_text(parts, 500, 836, "统一事实层既服务下游分析复用，也承接上游修复后的稳定回写。", "small")

    write_text(OUTPUT_DIR / "图3_统一数据契约与复用分析.svg", svg_footer(parts))


def write_manifest(metrics: dict) -> None:
    payload = {
        "topic": "顶会数据治理与科研分析的技能化自动化工作流系统",
        "files": [
            str(OUTPUT_DIR / "图1_技能化自动化工作流系统.svg"),
            str(OUTPUT_DIR / "图2_实验范围与运行结果总览.svg"),
            str(OUTPUT_DIR / "图3_统一数据契约与复用分析.svg"),
        ],
        "baseline_metrics": {
            "conference_years": metrics["conference_years"],
            "papers_total": metrics["papers_total"],
            "normalized_papers": metrics["normalization"]["paper_count"],
            "normalized_rows": metrics["normalization"]["normalized_rows"],
            "unknown_country_rows": metrics["audit"]["normalized_checks"]["unknown_country_rows"],
            "low_confidence_rows": metrics["audit"]["normalized_checks"]["low_confidence_rows"],
        },
    }
    write_text(OUTPUT_DIR / "figure_manifest.json", json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    ensure_dir(OUTPUT_DIR)
    metrics = collect_metrics()
    figure1_workflow(metrics)
    figure2_overview(metrics)
    figure3_contract(metrics)
    write_manifest(metrics)


if __name__ == "__main__":
    main()
