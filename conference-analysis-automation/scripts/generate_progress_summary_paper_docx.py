from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont


ROOT = Path("/Users/liziyu/llm_conference_skill")
OUTPUT_DIR = ROOT / "generated-data" / "reports"
ASSET_DIR = OUTPUT_DIR / "progress_summary_paper_assets"
DOCX_PATH = OUTPUT_DIR / "skills_progress_summary_paper_2026_06_17.docx"

PAPER_FACTS = ROOT / "generated-data" / "normalized" / "paper_facts.csv"
NORMALIZATION_REPORT = ROOT / "generated-data" / "normalized" / "normalization_report.json"
COVERAGE_SUMMARY = ROOT / "generated-data" / "paper_tables_three_tier" / "three_tier_coverage_summary.csv"
COVERAGE_BY_YEAR = ROOT / "generated-data" / "paper_tables_three_tier" / "three_tier_coverage_by_conference_year.csv"
COUNTRY_SUMMARY = ROOT / "generated-data" / "analysis" / "country" / "country_summary.csv"
COUNTRY_BY_YEAR = ROOT / "generated-data" / "analysis" / "country" / "country_by_year.csv"
INSTITUTION_SUMMARY = ROOT / "generated-data" / "analysis" / "institutions" / "institution_summary.csv"
AUTHOR_SUMMARY = ROOT / "generated-data" / "analysis" / "authors" / "author_summary.csv"
TREND_SUMMARY = ROOT / "generated-data" / "analysis" / "trends" / "trend_summary.csv"
COLLAB_SUMMARY = ROOT / "generated-data" / "analysis" / "collaboration" / "collaboration_summary.csv"
COLLAB_EDGES = ROOT / "generated-data" / "analysis" / "collaboration" / "collaboration_edges.csv"
CFP_REPORT = ROOT / "generated-data" / "cfp" / "output" / "cfp_validation_report.json"
ROLE_REPORT = ROOT / "generated-data" / "author-roles" / "author_role_report.json"
README_PATH = ROOT / "README.md"

FIG_FRAMEWORK = ASSET_DIR / "figure_framework.png"
FIG_COUNTS = ASSET_DIR / "figure_conference_counts.png"
FIG_COVERAGE = ASSET_DIR / "figure_coverage_tiers.png"
FIG_COUNTRIES = ASSET_DIR / "figure_country_dual.png"

COLOR = {
    "ink": RGBColor(31, 41, 55),
    "blue": RGBColor(46, 116, 181),
    "dark_blue": RGBColor(31, 77, 120),
    "muted": RGBColor(90, 98, 112),
    "border": "B8C2CC",
    "header_fill": "EAF1FB",
}

PALETTE = {
    "bg": "#FFFFFF",
    "text": "#1F2937",
    "muted": "#5B6472",
    "line": "#CBD5E1",
    "blue": "#3B82F6",
    "blue_soft": "#EAF2FF",
    "teal": "#14B8A6",
    "teal_soft": "#E8FCF8",
    "amber": "#F59E0B",
    "amber_soft": "#FFF6E5",
    "rose": "#E85D75",
    "rose_soft": "#FFECEF",
    "slate": "#64748B",
    "slate_soft": "#F8FAFC",
    "purple": "#8B5CF6",
    "purple_soft": "#F3EEFF",
    "green": "#10B981",
    "green_soft": "#ECFDF5",
}

FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size, index=0)
            except Exception:
                continue
    return ImageFont.load_default()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def pct(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator * 100.0 / denominator


def build_metrics() -> dict:
    coverage_rows = read_csv(COVERAGE_SUMMARY)
    coverage_year_rows = read_csv(COVERAGE_BY_YEAR)
    country_rows = read_csv(COUNTRY_SUMMARY)
    country_year_rows = read_csv(COUNTRY_BY_YEAR)
    institution_rows = read_csv(INSTITUTION_SUMMARY)
    author_rows = read_csv(AUTHOR_SUMMARY)
    trend_rows = read_csv(TREND_SUMMARY)
    collab_summary_rows = read_csv(COLLAB_SUMMARY)
    collab_edge_rows = read_csv(COLLAB_EDGES)
    normalization_report = read_json(NORMALIZATION_REPORT)
    cfp_report = read_json(CFP_REPORT)
    role_report = read_json(ROLE_REPORT)

    standardized_counts = Counter()
    counts_by_year = defaultdict(lambda: defaultdict(int))
    with PAPER_FACTS.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            standardized_counts[row["conference"]] += 1
            counts_by_year[row["conference"]][int(row["year"])] += 1

    overall_coverage = next(row for row in coverage_rows if row["conference"] == "OVERALL")
    conference_coverage = [row for row in coverage_rows if row["conference"] != "OVERALL"]
    overall_coverage = dict(overall_coverage)
    overall_coverage["success_total"] = str(
        int(overall_coverage["single_clean_coverage"]) + int(overall_coverage["same_country_multi_clear"])
    )
    overall_coverage["success_ratio"] = f"{pct(int(overall_coverage['success_total']), int(overall_coverage['total_papers'])):.2f}"

    official_totals = {
        row["conference"]: int(row["total_papers"]) for row in conference_coverage
    }
    official_total = int(overall_coverage["total_papers"])
    standardized_total = sum(standardized_counts.values())

    conf_gap_rows = []
    for row in conference_coverage:
        conf = row["conference"]
        conf_gap_rows.append(
            {
                "conference": conf,
                "official_total": int(row["total_papers"]),
                "standardized_total": standardized_counts[conf],
                "gap": int(row["total_papers"]) - standardized_counts[conf],
                "success_total": int(row["single_clean_coverage"]) + int(row["same_country_multi_clear"]),
            }
        )

    countries_2025 = sorted(
        [row for row in country_year_rows if row["year"] == "2025"],
        key=lambda row: int(row["papers"]),
        reverse=True,
    )

    top_trend_countries = [row for row in trend_rows if row["entity_type"] == "country"][:12]
    top_collab_pair = collab_edge_rows[0] if collab_edge_rows else None
    collab_summary = collab_summary_rows[0] if collab_summary_rows else None

    skill_descriptions = {
        "conference-paper-extraction": "负责从 IACR、DBLP、IEEE Xplore、ACM DL 等来源获取论文、作者与机构原始数据，是主链路的采集入口。",
        "conference-dataset-normalization": "负责把抽取层的行级结果整理为可复用事实表与维表，统一 paper_key、author_key、institution_id 等稳定键。",
        "conference-analysis-automation": "负责串联标准化、审计、国家统计、机构统计、作者统计、趋势分析、合作分析、报告与图表生成。",
        "conference-cfp-extraction": "负责会议投稿截止日期、通知日期、rebuttal 与会议日期等 CFP 生命周期元数据。",
        "conference-report-generation": "负责基于已生成的分析 CSV 产物拼接摘要层报告，形成可读的文字结果。",
        "conference-country-statistics / conference-institution-statistics / conference-author-statistics": "负责在统一事实表上输出国家、机构和作者多维统计结果。",
    }

    return {
        "coverage_rows": coverage_rows,
        "coverage_year_rows": coverage_year_rows,
        "conference_coverage": conference_coverage,
        "overall_coverage": overall_coverage,
        "country_rows": country_rows,
        "country_year_rows": country_year_rows,
        "countries_2025": countries_2025,
        "institution_rows": institution_rows,
        "author_rows": author_rows,
        "trend_rows": trend_rows,
        "top_trend_countries": top_trend_countries,
        "normalization_report": normalization_report,
        "cfp_report": cfp_report,
        "role_report": role_report,
        "standardized_counts": standardized_counts,
        "counts_by_year": counts_by_year,
        "official_totals": official_totals,
        "official_total": official_total,
        "standardized_total": standardized_total,
        "conf_gap_rows": conf_gap_rows,
        "collab_summary": collab_summary,
        "top_collab_pair": top_collab_pair,
        "skill_descriptions": skill_descriptions,
        "project_readme": README_PATH.read_text(encoding="utf-8"),
    }


def add_page_number(paragraph):
    run = paragraph.add_run()
    fld_char_begin = OxmlElement("w:fldChar")
    fld_char_begin.set(qn("w:fldCharType"), "begin")
    instr_text = OxmlElement("w:instrText")
    instr_text.set(qn("xml:space"), "preserve")
    instr_text.text = " PAGE "
    fld_char_end = OxmlElement("w:fldChar")
    fld_char_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_char_begin)
    run._r.append(instr_text)
    run._r.append(fld_char_end)


def set_run_font(run, *, size: float, bold: bool = False, italic: bool = False, color: RGBColor | None = None, name: str = "Calibri", east_asia: str = "宋体"):
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), east_asia)
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    if color is not None:
        run.font.color.rgb = color


def configure_document(doc: Document) -> None:
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.header_distance = Inches(0.49)
    section.footer_distance = Inches(0.49)

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    normal.font.size = Pt(11)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(8)
    normal.paragraph_format.line_spacing = 1.33

    for style_name, size, color, before, after in [
        ("Heading 1", 16, COLOR["blue"], 18, 10),
        ("Heading 2", 13, COLOR["blue"], 12, 6),
        ("Heading 3", 12, COLOR["dark_blue"], 8, 4),
    ]:
        style = doc.styles[style_name]
        style.font.name = "Calibri"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "黑体")
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = color
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.line_spacing = 1.2

    footer_p = section.footer.paragraphs[0]
    footer_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = footer_p.add_run("第 ")
    set_run_font(run, size=9, color=COLOR["muted"])
    add_page_number(footer_p)
    run = footer_p.add_run(" 页")
    set_run_font(run, size=9, color=COLOR["muted"])


def title_page(doc: Document) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(96)
    p.paragraph_format.space_after = Pt(12)
    r = p.add_run("面向顶会数据治理与科研分析的技能化自动化工作流系统")
    set_run_font(r, size=22, bold=True, color=COLOR["ink"], east_asia="黑体")

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(18)
    r = p.add_run("2020—2025 年七大会数据抽取、统计分析与系统进展汇总")
    set_run_font(r, size=15, color=COLOR["blue"], east_asia="黑体")

    for text in [
        "摘要本文面向密码学与信息安全领域七个代表性顶级会议，围绕论文获取、作者机构抽取、国家识别、标准化治理、统计分析、会议征文日期抽取与结果表达等环节，构建了一套技能化自动化工作流系统。系统以 Skill 为组织单元，以统一事实表为共享中间层，以质量审计为约束机制，支持跨会议、跨年份、可追溯的数据治理与科研分析。本文在 2026 年 6 月 17 日主线正式产物基础上，对当前系统进展进行阶段性汇总。",
        "从会议总体规模看，当前正式口径覆盖 ASIACRYPT、CRYPTO、EUROCRYPT、ACM CCS、IEEE S&P、NDSS 与 USENIX Security 七个会议 2020—2025 年全部 42 个 conference-year。按会议接收总量口径计算，当前覆盖论文总数为 7075 篇；按已进入标准化主表口径计算，`paper_facts.csv` 中已稳定入表论文 7066 篇。说明主数据链路已经完成绝大多数论文的标准化入表，剩余缺口主要集中在极少数论文的标准化承接与会议级对齐差异。",
        "从作者机构覆盖质量看，当前三层口径下的单机构干净覆盖为 4867 篇，占全部论文的 68.79%；同国多机构但已清晰抽到的论文为 1389 篇，占 19.63%；两者合计构成 6256 篇有效成功覆盖，占 88.42%。未消歧的多机构歧义论文为 785 篇，占 11.10%；此外，仍有 18 篇部分覆盖、6 篇无作者机构数据、1 篇作者机构对齐失败。该结果表明，系统已经能够支撑大规模顶会作者机构统计，但多机构歧义仍是后续质量提升的主要阻力。",
        "从统计分析能力看，系统已经形成全量国家、机构、作者、趋势、合作、角色与 CFP 元数据的自动化链路。国家总表显示，美国、中国、德国、瑞士、英国和法国等国家在当前数据中构成主要科研产出梯队；机构总表显示，CISPA、清华大学、普渡大学、浙江大学、ETH Zurich、UIUC 等机构在七大会 2020—2025 数据中具有较高活跃度。作者角色链路已可稳定输出第一作者与参与作者结果，CFP 主链路已在 42 个 conference-year 范围内建立完整的 event 与 edition 记录。",
        "关键词顶会数据治理；作者机构抽取；国家统计；科研分析自动化；Skill 框架；质量审计",
    ]:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.first_line_indent = Cm(0.74)
        p.paragraph_format.space_after = Pt(10)
        run = p.add_run(text)
        set_run_font(run, size=11)

    doc.add_page_break()


def add_heading(doc: Document, text: str, level: int) -> None:
    doc.add_heading(text, level=level)


def add_paragraph(doc: Document, text: str, *, first_line: bool = True) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    if first_line:
        p.paragraph_format.first_line_indent = Cm(0.74)
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.line_spacing = 1.33
    run = p.add_run(text)
    set_run_font(run, size=11)


def add_caption(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run(text)
    set_run_font(run, size=10.5, bold=True)


def shade_cell(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_table_borders(table) -> None:
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    tbl_borders = tbl_pr.first_child_found_in("w:tblBorders")
    if tbl_borders is None:
        tbl_borders = OxmlElement("w:tblBorders")
        tbl_pr.append(tbl_borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        elem = tbl_borders.find(qn(f"w:{edge}"))
        if elem is None:
            elem = OxmlElement(f"w:{edge}")
            tbl_borders.append(elem)
        elem.set(qn("w:val"), "single")
        elem.set(qn("w:sz"), "6")
        elem.set(qn("w:space"), "0")
        elem.set(qn("w:color"), COLOR["border"])


def add_table(doc: Document, rows: list[list[str]], widths_cm: list[float], caption: str | None = None, font_size: float = 10.5) -> None:
    if caption:
        add_caption(doc, caption)
    table = doc.add_table(rows=len(rows), cols=len(rows[0]))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    table.style = "Table Grid"
    set_table_borders(table)
    for row in table.rows:
        for idx, width in enumerate(widths_cm):
            row.cells[idx].width = Cm(width)
    for r_idx, row in enumerate(rows):
        for c_idx, value in enumerate(row):
            cell = table.cell(r_idx, c_idx)
            cell.text = ""
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if c_idx == 0 or len(value) <= 16 else WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.15
            run = p.add_run(value)
            set_run_font(run, size=font_size, bold=(r_idx == 0))
            if r_idx == 0:
                shade_cell(cell, COLOR["header_fill"])
    doc.add_paragraph()


def figure_paragraph(doc: Document, path: Path, caption: str, width_inches: float = 6.0) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    run.add_picture(str(path), width=Inches(width_inches))
    add_caption(doc, caption)


def canvas(width: int, height: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (width, height), hex_to_rgb(PALETTE["bg"]))
    return image, ImageDraw.Draw(image)


def centered_text(draw, box, text, size, fill, bold=False, spacing=6):
    font = load_font(size, bold=bold)
    x0, y0, x1, y1 = box
    bbox = draw.multiline_textbbox((0, 0), text, font=font, align="center", spacing=spacing)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.multiline_text(
        (x0 + (x1 - x0 - tw) / 2, y0 + (y1 - y0 - th) / 2),
        text,
        font=font,
        fill=hex_to_rgb(fill),
        align="center",
        spacing=spacing,
    )


def left_text(draw, xy, text, size, fill, bold=False, spacing=4):
    draw.multiline_text(xy, text, font=load_font(size, bold=bold), fill=hex_to_rgb(fill), spacing=spacing)


def rounded_box(draw, box, fill, outline, radius=24, width=3):
    draw.rounded_rectangle(box, radius=radius, fill=hex_to_rgb(fill), outline=hex_to_rgb(outline), width=width)


def arrow(draw, start, end, fill="#94A3B8", width=5, head_len=18, head_w=10):
    draw.line([start, end], fill=hex_to_rgb(fill), width=width)
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    angle = math.atan2(dy, dx)
    bx = end[0] - head_len * math.cos(angle)
    by = end[1] - head_len * math.sin(angle)
    left = (bx + head_w * math.sin(angle), by - head_w * math.cos(angle))
    right = (bx - head_w * math.sin(angle), by + head_w * math.cos(angle))
    draw.polygon([end, left, right], fill=hex_to_rgb(fill))


def build_framework_figure():
    image, draw = canvas(2200, 1350)
    left_text(draw, (110, 80), "图 1  技能化自动化工作流系统框架", 42, PALETTE["text"], bold=True)
    left_text(draw, (110, 140), "以统一事实表与质量审计为核心的多层 Skill 协同关系", 24, PALETTE["muted"])

    top = (220, 240, 1980, 360)
    rounded_box(draw, top, PALETTE["purple_soft"], PALETTE["purple"])
    centered_text(draw, top, "自动化编排层\n统一入口 | 批量执行 | 结果归档 | 运行记录", 28, PALETTE["text"], bold=True)

    columns = [
        ((140, 470, 660, 1120), PALETTE["blue_soft"], PALETTE["blue"], "采集层", [
            "会议注册表\n会议选择与年份范围",
            "论文获取\nIACR / DBLP / 官网 / PDF",
            "作者机构提取\n作者名、affiliation、审计字段",
        ]),
        ((840, 470, 1360, 1120), PALETTE["teal_soft"], PALETTE["teal"], "治理层", [
            "标准化\npaper_key / institution_id",
            "质量增强\n去噪、国家识别、机构治理",
            "覆盖审计\n完整性判断与对齐修复",
        ]),
        ((1540, 470, 2060, 1120), PALETTE["amber_soft"], PALETTE["amber"], "分析层", [
            "国家、机构、作者统计",
            "趋势、合作、作者角色分析",
            "CFP 元数据、图表与论文报告",
        ]),
    ]
    for outer, fill, outline, title, items in columns:
        rounded_box(draw, outer, fill, outline)
        centered_text(draw, (outer[0], outer[1] + 12, outer[2], outer[1] + 84), title, 28, outline, bold=True)
        y = outer[1] + 120
        for item in items:
            box = (outer[0] + 28, y, outer[2] - 28, y + 130)
            rounded_box(draw, box, "#FFFFFF", outline, radius=20, width=2)
            centered_text(draw, box, item, 22, PALETTE["text"])
            y += 170
    arrow(draw, (660, 795), (820, 795), fill=PALETTE["slate"])
    arrow(draw, (1360, 795), (1520, 795), fill=PALETTE["slate"])
    arrow(draw, (1100, 360), (1100, 430), fill=PALETTE["slate"])

    footer = (180, 1180, 2020, 1280)
    rounded_box(draw, footer, PALETTE["slate_soft"], PALETTE["line"], radius=24, width=2)
    centered_text(
        draw,
        footer,
        "质量增强型模块决定覆盖率与一致性；分析扩展型模块决定系统的科研分析表达能力。",
        24,
        PALETTE["muted"],
    )
    image.save(FIG_FRAMEWORK)


def build_counts_figure(metrics: dict):
    image, draw = canvas(2200, 1400)
    left_text(draw, (110, 80), "图 2  七大会 2020—2025 年论文规模变化", 42, PALETTE["text"], bold=True)
    left_text(draw, (110, 140), "按标准化主表口径统计的年度论文数，用于刻画七个会议的规模扩张趋势", 24, PALETTE["muted"])

    plot = (180, 260, 2050, 1170)
    draw.rectangle(plot, outline=hex_to_rgb(PALETTE["line"]), width=2)
    years = [2020, 2021, 2022, 2023, 2024, 2025]
    max_y = max(max(v.values()) for v in metrics["counts_by_year"].values())
    colors = ["#2563EB", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#14B8A6", "#0F766E"]
    for idx, yv in enumerate(range(0, max_y + 1, 50)):
        y = plot[3] - (plot[3] - plot[1]) * yv / max_y
        draw.line([(plot[0], y), (plot[2], y)], fill=hex_to_rgb("#E5E7EB"), width=1)
        left_text(draw, (120, y - 10), str(yv), 16, PALETTE["muted"])
    x_positions = {
        year: plot[0] + (plot[2] - plot[0]) * i / (len(years) - 1)
        for i, year in enumerate(years)
    }
    for year, x in x_positions.items():
        draw.line([(x, plot[1]), (x, plot[3])], fill=hex_to_rgb("#EEF2F7"), width=1)
        left_text(draw, (x - 24, plot[3] + 18), str(year), 18, PALETTE["muted"])
    for idx, (conf, counts) in enumerate(sorted(metrics["counts_by_year"].items())):
        series = [(x_positions[year], plot[3] - (plot[3] - plot[1]) * counts[year] / max_y) for year in years]
        draw.line(series, fill=hex_to_rgb(colors[idx]), width=5)
        for x, y in series:
            draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=hex_to_rgb(colors[idx]), outline=hex_to_rgb(colors[idx]))
        legend_x = 260 + (idx % 3) * 560
        legend_y = 1220 + (idx // 3) * 58
        draw.line([(legend_x, legend_y + 14), (legend_x + 50, legend_y + 14)], fill=hex_to_rgb(colors[idx]), width=5)
        left_text(draw, (legend_x + 70, legend_y), conf.replace("_", " "), 22, PALETTE["text"])
    image.save(FIG_COUNTS)


def build_coverage_figure(metrics: dict):
    image, draw = canvas(2200, 1350)
    left_text(draw, (110, 80), "图 3  作者机构覆盖三层口径分布", 42, PALETTE["text"], bold=True)
    left_text(draw, (110, 140), "按会议展示单机构干净覆盖、同国多机构清晰覆盖与未消歧多机构歧义的结构差异", 24, PALETTE["muted"])
    x0, y0, x1, y1 = 240, 260, 1960, 1120
    draw.rectangle((x0, y0, x1, y1), outline=hex_to_rgb(PALETTE["line"]), width=2)
    labels = [row["conference"] for row in metrics["conference_coverage"]]
    bar_width = 150
    spacing = 90
    total_bar_area = len(labels) * bar_width + (len(labels) - 1) * spacing
    start_x = x0 + (x1 - x0 - total_bar_area) / 2
    colors = {
        "single": PALETTE["blue"],
        "same_country": PALETTE["green"],
        "amb": PALETTE["amber"],
    }
    for row_idx, row in enumerate(metrics["conference_coverage"]):
        total = int(row["total_papers"])
        vals = [
            ("single", int(row["single_clean_coverage"])),
            ("same_country", int(row["same_country_multi_clear"])),
            ("amb", int(row["unresolved_multi_ambiguity"])),
        ]
        x = start_x + row_idx * (bar_width + spacing)
        base_y = y1 - 20
        for key, val in vals:
            height = (y1 - y0 - 100) * val / total
            top_y = base_y - height
            draw.rectangle((x, top_y, x + bar_width, base_y), fill=hex_to_rgb(colors[key]), outline=hex_to_rgb(colors[key]))
            base_y = top_y
        left_text(draw, (x + 20, y1 + 10), row["conference"].replace("_", " "), 16, PALETTE["text"])
        left_text(draw, (x + 18, y0 - 26), str(total), 15, PALETTE["muted"])
    legend = [
        ("单机构干净覆盖", colors["single"]),
        ("同国多机构清晰覆盖", colors["same_country"]),
        ("未消歧多机构歧义", colors["amb"]),
    ]
    lx = 360
    for label, col in legend:
        draw.rectangle((lx, 1200, lx + 28, 1228), fill=hex_to_rgb(col), outline=hex_to_rgb(col))
        left_text(draw, (lx + 44, 1194), label, 22, PALETTE["text"])
        lx += 440
    image.save(FIG_COVERAGE)


def build_country_figure(metrics: dict):
    image, draw = canvas(2200, 1500)
    left_text(draw, (110, 80), "图 4  全量国家格局与 2025 年快照", 42, PALETTE["text"], bold=True)
    left_text(draw, (110, 140), "左图为 2020—2025 总体前十国家，右图为 2025 年单年快照前十国家", 24, PALETTE["muted"])

    def panel(rows, title, box, color):
        rounded_box(draw, box, "#FFFFFF", PALETTE["line"], radius=20, width=2)
        left_text(draw, (box[0] + 24, box[1] + 18), title, 28, PALETTE["text"], bold=True)
        top_rows = rows[:10]
        max_val = max(int(row["papers"]) for row in top_rows)
        y = box[1] + 90
        for row in top_rows:
            label = row["country"]
            val = int(row["papers"])
            left_text(draw, (box[0] + 26, y), label, 18, PALETTE["text"])
            bar_x0 = box[0] + 210
            bar_x1 = bar_x0 + 520 * val / max_val
            draw.rounded_rectangle((bar_x0, y + 4, bar_x1, y + 28), radius=10, fill=hex_to_rgb(color))
            left_text(draw, (bar_x1 + 14, y - 2), str(val), 18, PALETTE["muted"])
            y += 52

    panel(metrics["country_rows"], "2020—2025 总体前十国家", (110, 240, 1020, 1330), PALETTE["blue"])
    panel(metrics["countries_2025"], "2025 年快照前十国家", (1130, 240, 2040, 1330), PALETTE["teal"])
    image.save(FIG_COUNTRIES)


def build_figures(metrics: dict):
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    build_framework_figure()
    build_counts_figure(metrics)
    build_coverage_figure(metrics)
    build_country_figure(metrics)


def section_intro(doc: Document):
    add_heading(doc, "1 引言", 1)
    add_paragraph(doc, "近年来，围绕顶级学术会议开展的数据治理与科研分析逐渐从一次性统计工作，演变为需要长期维护、持续复核、可重复生成的系统性任务。对于密码学与信息安全等变化快、会议生态复杂的学科方向而言，仅依靠单次人工整理，很难在跨会议、跨年份和跨统计口径的场景下保持结果稳定。尤其是在作者机构抽取这一关键环节，不同官网、数字图书馆和 PDF 页面往往使用不同字段组织方式，同一机构也可能存在多种写法，导致上游抽取与下游统计之间出现显著断层。")
    add_paragraph(doc, "本文将当前项目视为一个面向顶会数据治理与科研分析的技能化自动化工作流系统，而不是简单的脚本集合。这里的 Skill 并非泛化概念，而是职责边界清晰、可独立执行、又能够通过统一输入输出契约接入主流程的功能模块。围绕这一组织方式，系统在数据采集、标准化治理、质量增强、统计分析、结果表达和自动化编排六个层次上逐步形成较为稳定的主链路。")
    add_paragraph(doc, "本报告以 2026 年 6 月 17 日主线正式产物为基准，面向七个代表性会议 2020—2025 年数据，对当前自动化进展进行阶段性汇总。全文的目标不是给出软件使用说明，而是以正式论文的写法回答三个核心问题：第一，当前系统已经在多大范围内打通了论文、作者、机构、国家和会议元数据的自动化链路；第二，主数据链路在覆盖率、一致性和审计能力方面已经达到何种程度；第三，国家、机构、作者、合作、角色与 CFP 等分析能力目前完成到了哪一步，后续的主要质量瓶颈又集中在哪里。")


def section_scope_and_contract(doc: Document, metrics: dict):
    add_heading(doc, "2 数据范围、统计口径与正式产物", 1)
    add_heading(doc, "2.1 研究对象与数据范围", 2)
    add_paragraph(doc, f"当前主线覆盖七个会议：ASIACRYPT、CRYPTO、EUROCRYPT、ACM CCS、IEEE S&P、NDSS 与 USENIX Security，时间范围为 2020—2025 年，共 42 个 conference-year。按覆盖审计口径计算，会议接收论文总量为 {metrics['official_total']} 篇；按已进入标准化主表口径计算，`paper_facts.csv` 中稳定入表论文为 {metrics['standardized_total']} 篇。这意味着主链路已经对绝大多数论文完成了承接，但在标准化入表层仍保留少量会议级差异。")
    add_paragraph(doc, "当前正式数据目录已经收束为统一主线结构：抽取层输出集中在 `generated-data/extraction/output/by_conference/`，标准化事实表集中在 `generated-data/normalized/`，国家、机构、作者、趋势与合作分析集中在 `generated-data/analysis/`，CFP 元数据集中在 `generated-data/cfp/output/`，作者角色结果集中在 `generated-data/author-roles/`。这样的组织方式将当前可用结果、标准化共享层和扩展分析层明确区分，便于后续版本对比与实验复现。")
    add_heading(doc, "2.2 两个关键口径：会议总量与标准化入表", 2)
    add_paragraph(doc, "为了避免正文中的数字互相打架，本文明确区分两个互补口径。其一是“会议接收总量口径”，用于衡量某会议某年份理论上应覆盖多少篇被接收论文；其二是“标准化入表口径”，用于衡量主数据链路中已有多少论文进入稳定事实表，可直接被后续统计模块消费。前者是覆盖率评估的分母，后者是统一事实表层的成熟度指标。二者不完全相同并不必然意味着错误，而是说明系统在“已知总量”和“可直接分析”之间仍存在少量待补齐差异。")
    gap_table = [["会议", "会议接收总量", "标准化入表论文", "差值"]]
    for row in metrics["conf_gap_rows"]:
        gap_table.append([row["conference"], str(row["official_total"]), str(row["standardized_total"]), str(row["gap"])])
    gap_table.append(["合计", str(metrics["official_total"]), str(metrics["standardized_total"]), str(metrics["official_total"] - metrics["standardized_total"])])
    add_table(doc, gap_table, [3.0, 3.2, 3.2, 2.3], "表 1  会议接收总量口径与标准化入表口径对照")
    add_paragraph(doc, "从表 1 可以看到，当前差值主要集中在 NDSS 和 IEEE S&P，分别存在 8 篇和 1 篇未完全进入 `paper_facts.csv` 的论文。其余五个会议在 2020—2025 范围内，会议总量口径与标准化主表口径已经对齐。这一结果说明当前主线的数据一致性问题已经从“系统性缺口”收缩为“少量会议级尾部差异”，后续修复也可以更聚焦。")
    add_heading(doc, "2.3 三层覆盖口径", 2)
    add_paragraph(doc, "作者机构质量评估采用当前项目已经保留的三层口径：单机构干净覆盖、同国多机构清晰覆盖、未消歧多机构歧义。之所以采用这一结构，是因为仅用“拿到 / 没拿到”二值判断，会把一部分已经清晰获取、但因并列机构写法较复杂的论文错误压入失败区。三层口径能够更真实地反映当前系统的有效成功层、审慎保留层和剩余问题层。")
    overall = metrics["overall_coverage"]
    cov_table = [
        ["口径", "论文数", "占总论文比重"],
        ["单机构干净覆盖", overall["single_clean_coverage"], f"{overall['single_clean_ratio']}%"],
        ["同国多机构清晰覆盖", overall["same_country_multi_clear"], f"{overall['same_country_multi_ratio']}%"],
        ["未消歧多机构歧义", overall["unresolved_multi_ambiguity"], f"{overall['unresolved_multi_ratio']}%"],
        ["部分覆盖", overall["partial_affiliation_coverage"], f"{pct(int(overall['partial_affiliation_coverage']), metrics['official_total']):.2f}%"],
        ["无作者机构数据", overall["no_affiliation_data"], f"{pct(int(overall['no_affiliation_data']), metrics['official_total']):.2f}%"],
        ["作者机构对齐失败", overall["author_affiliation_match_failed"], f"{pct(int(overall['author_affiliation_match_failed']), metrics['official_total']):.2f}%"],
        ["有效成功覆盖合计", overall["success_total"], f"{overall['success_ratio']}%"],
    ]
    add_table(doc, cov_table, [4.4, 2.5, 3.8], "表 2  当前三层覆盖口径总体结果")


def section_framework(doc: Document, metrics: dict):
    add_heading(doc, "3 Skills 框架与系统设计", 1)
    add_heading(doc, "3.1 技能化工作流的组织原则", 2)
    add_paragraph(doc, "当前项目不是将所有逻辑堆叠在单一脚本中，而是以 Skill 作为可编排的能力单元进行组织。这样做有三个直接收益。第一，采集、标准化、统计和报告生成可以相对独立演化，避免某一层的频繁修改牵连全部流程。第二，每个 Skill 都有相对清晰的输入契约和输出契约，便于在主流程中留下稳定中间层。第三，出现问题时可以明确定位是来源获取、机构治理、国家识别、论文对齐还是报告表达环节，而不是将所有问题混成一个“结果不对”的黑箱。")
    skills_table = [["Skill", "当前作用"]]
    for key, value in metrics["skill_descriptions"].items():
        skills_table.append([key, value])
    add_table(doc, skills_table, [5.4, 10.4], "表 3  当前项目的核心 Skills 及其职责", font_size=9.8)
    add_heading(doc, "3.2 六层系统结构", 2)
    add_paragraph(doc, "从系统实现角度看，当前主线可以概括为六层：采集层、治理层、分析层、结果表达层、自动化编排层以及贯穿全链路的质量审计机制。采集层负责解决“从哪里拿数据”；治理层负责解决“拿到的数据是否能稳定进入共享事实表”；分析层负责解决“统一数据层之上能够回答哪些科研分析问题”；结果表达层负责把多维统计产物转写为图表、表格与报告；自动化编排层则负责把这些模块组织为可复现运行。质量审计并不单独依附于某一层，而是贯穿采集、治理和分析三部分。")
    figure_paragraph(doc, FIG_FRAMEWORK, "图 1  技能化自动化工作流系统框架", width_inches=6.2)
    add_heading(doc, "3.3 统一事实表与数据契约", 2)
    add_paragraph(doc, "当前系统的关键设计不是“每个 Skill 都直接生成最终结论”，而是把下游统计建立在统一事实表之上。标准化层输出的 `paper_facts.csv`、`author_affiliation_facts.csv` 与 `institution_dim.csv`，分别承载论文级、作者机构级与机构维度级事实。国家、机构、作者、趋势和合作分析都围绕这些事实表工作，避免了每个模块重复回读官网或历史 HTML 文件，也显著降低了统计口径漂移风险。")
    add_paragraph(doc, "这一设计直接提升了系统的可追溯性。若某项统计结果出现异常，可以回溯到标准化表中具体的 `paper_key`、`author_key`、`institution_id` 或审计字段，而不需要重新定位原始网页。对论文撰写而言，这也使结果描述可以建立在稳定表格快照上，而不是一次性运行日志上。")


def section_scale(doc: Document, metrics: dict):
    add_heading(doc, "4 七大会整体规模与年度演化", 1)
    add_heading(doc, "4.1 各会议总体规模", 2)
    add_paragraph(doc, "从会议规模看，USENIX Security 和 ACM CCS 构成当前样本中规模最大的两类会议群。按会议接收总量口径，USENIX Security 2020—2025 六年累计 1941 篇，CCS 六年累计 1401 篇；IEEE S&P 为 1082 篇，NDSS 为 707 篇。三大密码会中，CRYPTO、ASIACRYPT 与 EUROCRYPT 分别为 710、654 与 580 篇。由此可以看到，安全类会议在论文总量上明显高于三大密码会，这决定了两类会议在作者机构治理难度和统计结构上的差异。")
    conf_rows = [["会议", "2020", "2021", "2022", "2023", "2024", "2025", "六年合计"]]
    for conf in sorted(metrics["counts_by_year"]):
        vals = [metrics["counts_by_year"][conf][year] for year in range(2020, 2026)]
        conf_rows.append([conf] + [str(v) for v in vals] + [str(sum(vals))])
    add_table(doc, conf_rows, [3.0, 1.4, 1.4, 1.4, 1.4, 1.4, 1.4, 2.0], "表 4  七大会 2020—2025 年标准化主表论文数")
    add_heading(doc, "4.2 年度变化趋势", 2)
    add_paragraph(doc, "按标准化主表口径观察，七个会议在 2020—2025 年总体呈增长态势，但增长速度与结构并不一致。三大密码会保持了较稳定的扩张曲线，ASIACRYPT 从 2020 年的 85 篇增长到 2025 年的 143 篇，CRYPTO 从 85 篇增长到 156 篇，EUROCRYPT 从 81 篇增长到 123 篇。安全类会议中，USENIX Security 的增长最为显著，从 159 篇快速增长至 439 篇，CCS 也从 121 篇增长至 311 篇。")
    add_paragraph(doc, "年度规模扩张直接影响作者机构治理难度。一方面，论文数增加会放大多源数据异构、机构命名分化和多机构并列出现的频率；另一方面，大规模会议更容易出现某些尾部论文在官网、数字图书馆和开放平台之间的字段差异。因此，会议规模增长本身也是对自动化系统稳定性的持续压力测试。")
    figure_paragraph(doc, FIG_COUNTS, "图 2  七大会 2020—2025 年论文规模变化", width_inches=6.2)


def section_coverage(doc: Document, metrics: dict):
    add_heading(doc, "5 作者机构覆盖质量与审计结果", 1)
    add_heading(doc, "5.1 总体覆盖现状", 2)
    overall = metrics["overall_coverage"]
    success_total = int(overall["success_total"])
    unresolved = int(overall["unresolved_multi_ambiguity"])
    partial = int(overall["partial_affiliation_coverage"])
    missing = int(overall["no_affiliation_data"])
    failed = int(overall["author_affiliation_match_failed"])
    add_paragraph(doc, f"当前作者机构治理的核心结果可以概括为“有效成功覆盖已接近九成，但多机构歧义仍是第一大尾部问题”。按会议接收总量 {metrics['official_total']} 篇计算，单机构干净覆盖 {overall['single_clean_coverage']} 篇，占 {overall['single_clean_ratio']}%；同国多机构清晰覆盖 {overall['same_country_multi_clear']} 篇，占 {overall['same_country_multi_ratio']}%。两者合计 {success_total} 篇，占全部论文的 {overall['success_ratio']}%。与此同时，仍有 {unresolved} 篇论文停留在未消歧多机构歧义层，另有 {partial} 篇部分覆盖、{missing} 篇无作者机构数据和 {failed} 篇对齐失败。")
    add_paragraph(doc, "这一结果说明，当前系统的主要问题已不再是“大面积什么都没拿到”，而是如何进一步降低复杂并列机构情况下的歧义保留。换句话说，当前质量瓶颈从“有没有数据”转向了“怎样让已经获取的数据更适合无歧义统计”。这也是为什么本文采用三层覆盖口径，而不是简单将所有多机构论文都判为失败。")
    conf_cov_rows = [["会议", "单机构干净覆盖", "同国多机构清晰覆盖", "未消歧多机构歧义", "有效成功率"]]
    for row in metrics["conference_coverage"]:
        success = int(row["single_clean_coverage"]) + int(row["same_country_multi_clear"])
        total = int(row["total_papers"])
        conf_cov_rows.append([
            row["conference"],
            row["single_clean_coverage"],
            row["same_country_multi_clear"],
            row["unresolved_multi_ambiguity"],
            f"{pct(success, total):.2f}%",
        ])
    add_table(doc, conf_cov_rows, [3.2, 3.0, 3.2, 3.0, 2.6], "表 5  各会议三层覆盖口径结构")
    add_heading(doc, "5.2 会议间差异", 2)
    add_paragraph(doc, "会议间的覆盖结构差异非常鲜明。CCS 虽然单机构干净覆盖比例只有 52.46%，但同国多机构清晰覆盖高达 43.47%，意味着其大量论文实际上已经拿到可用于国别统计的清晰机构集合，只是在机构并列写法上更复杂。与此相对，NDSS 和 USENIX Security 的单机构干净覆盖本身已经较高，分别达到 85.43% 和 81.92%，说明这两类会议在主线抽取与标准化链路上更接近“直接可统计”状态。三大密码会则普遍表现为未消歧多机构歧义占比较高，说明密码学论文中的并列机构与跨机构合作写法，对系统提出了更高的机构拆分与合并要求。")
    figure_paragraph(doc, FIG_COVERAGE, "图 3  作者机构覆盖三层口径分布", width_inches=6.2)
    add_heading(doc, "5.3 标准化层的稳定性", 2)
    nr = metrics["normalization_report"]
    add_paragraph(doc, f"标准化层的行级稳定性已经较为成熟。当前 `normalization_report.json` 显示，输入作者机构行 {nr['input_rows']} 条，标准化后事实行 {nr['normalized_rows']} 条，稳定入表论文 {nr['paper_count']} 篇，机构数 {nr['institution_count']} 个，未知国家行仅 {nr['rows_with_unknown_country']} 条。需要强调的是，标准化层中的“行级字段完整”与论文级“完全覆盖”并不是同一概念；前者说明已进入事实表的记录结构稳定，后者仍需结合覆盖审计表来判断。")
    add_paragraph(doc, "因此，当前系统在质量评估上已经形成了较清晰的双层结构：标准化报告负责说明事实表本身是否稳定可用，覆盖审计负责说明从会议总量到事实表之间还剩多少论文级问题。对于系统论文写作而言，这种分层可以有效避免把“行级完整性”和“论文级完整性”混写在一起。")


def section_country(doc: Document, metrics: dict):
    add_heading(doc, "6 全量国家格局与时间变化", 1)
    add_heading(doc, "6.1 2020—2025 总体国家格局", 2)
    top_countries = metrics["country_rows"][:15]
    add_paragraph(doc, "相较于只围绕中美做局部对比的报告写法，当前系统已经能够在统一事实上输出全量国家视角。总体国家统计显示，美国仍然是七大会 2020—2025 期间最主要的论文参与国，共涉及 3697 篇论文；中国以 1516 篇位居第二；德国、瑞士、英国、法国和以色列构成第二梯队。值得注意的是，当前国家统计中还保留了 `Multiple` 类别，用于审慎承载尚未被完全消歧但已表现出多国参与信号的论文。")
    country_table = [["国家/地区", "论文数", "作者数", "机构数", "论文占比"]]
    for row in top_countries:
        country_table.append([row["country"], row["papers"], row["authors"], row["institutions"], f"{float(row['paper_share']) * 100:.2f}%"])
    add_table(doc, country_table, [3.7, 2.0, 2.0, 2.0, 2.2], "表 6  2020—2025 总体前十五国家/地区")
    add_heading(doc, "6.2 2025 年快照与增量变化", 2)
    add_paragraph(doc, "如果把视角收缩到 2025 年单年，美国依然以 749 篇位居首位，中国则上升到 456 篇，并且是当前前十国家中增长最显著的一支。从趋势摘要可见，中国在 2020 年仅为 85 篇，到 2025 年达到 456 篇，六年净增长 371 篇；德国则从 80 篇增长到 201 篇；新加坡从 18 篇增长到 91 篇。美国虽仍处于绝对领先位置，但 2024 年 761 篇已高于 2025 年的 749 篇，说明其高位增长开始出现一定波动。")
    add_paragraph(doc, "这一结果表明，当前系统不仅可以回答“谁在总体上更活跃”，还可以回答“谁在最近几年增长更快”。对于后续论文写作而言，全量国家格局、2025 快照与 2020—2025 时间序列三种视角可以共同构成比单纯中美对比更完整的国际科研格局描述。")
    figure_paragraph(doc, FIG_COUNTRIES, "图 4  全量国家格局与 2025 年快照", width_inches=6.2)
    add_heading(doc, "6.3 口径边界与地区字段说明", 2)
    add_paragraph(doc, "需要说明的是，当前国家统计表中仍保留 `Hong Kong` 和 `Taiwan` 独立列示，这是现行机构映射字段的输出结果，而不是报告写作者额外增加的新口径。同样，`Multiple` 也不是一个真实国家，而是为了保留尚未完全消歧的多国参与信号。在正式论文写作中，应把这部分如实写作“当前系统输出口径”，并与常规国家实体区分开来。")


def section_institution_author(doc: Document, metrics: dict):
    add_heading(doc, "7 机构、作者与合作网络分析", 1)
    add_heading(doc, "7.1 机构画像", 2)
    add_paragraph(doc, "机构总表显示，当前七大会 2020—2025 数据中，CISPA Helmholtz Center for Information Security 以 255 篇论文位列第一，清华大学以 240 篇位列第二，普渡大学、浙江大学、ETH Zurich、UIUC、Georgia Tech 和 Carnegie Mellon University 等机构构成紧随其后的高活跃梯队。值得关注的是，NTT Research 也以 155 篇进入前十，说明在当前机构治理逻辑下，企业研究机构的活跃度已经能够被较稳定地识别出来。")
    inst_table = [["机构", "国家/地区", "论文数", "首作者论文数"]]
    for row in metrics["institution_rows"][:15]:
        inst_table.append([row["institution_name"], row["country"], row["papers"], row["first_author_papers"]])
    add_table(doc, inst_table, [7.1, 2.4, 1.8, 2.6], "表 7  2020—2025 总体前十五机构", font_size=9.8)
    add_heading(doc, "7.2 作者画像", 2)
    add_paragraph(doc, "作者总表层面，Haixin Duan 以 61 篇位列首位，Yuval Ishai 与 Xiapu Luo 分别以 52 篇并列第二，Shouling Ji、Min Yang、Giulio Malavolta 与 Qi Li 等作者也保持了较高活跃度。由于当前作者角色模块尚未把通讯作者自动化纳入稳定主链路，因此本文对作者画像的主要解读仍建立在论文参与数与首作者论文数之上。")
    author_table = [["作者", "论文数", "活跃会议数", "首作者论文数"]]
    for row in metrics["author_rows"][:15]:
        author_table.append([row["author_name"], row["papers"], row["conferences"], row["first_author_papers"]])
    add_table(doc, author_table, [5.3, 2.0, 2.2, 2.6], "表 8  2020—2025 总体前十五作者")
    add_heading(doc, "7.3 合作关系", 2)
    collab = metrics["collab_summary"]
    pair = metrics["top_collab_pair"]
    if collab and pair:
        add_paragraph(doc, f"合作分析目前已形成基于作者节点的合作网络。当前摘要显示，合作网络共有 {collab['node_count']} 个作者节点、{collab['edge_count']} 条合作边，其中重复合作边 {collab['repeated_edge_count']} 条，最大重复合作强度为 {collab['max_shared_papers']} 篇。当前最强合作对为 {pair['left_name']} 与 {pair['right_name']}，在 2020—2025 间共同出现在 {pair['shared_papers']} 篇论文中，覆盖 {pair['conference_count']} 个会议。")
    add_paragraph(doc, "合作网络的意义不只是展示谁与谁合作更多，还在于为后续机构联盟、跨国合作和稳定研究团体识别提供基础。由于作者消歧仍有进一步改进空间，当前合作网络更适合作为趋势性分析结果，而不是精细的人物关系图谱终稿。")


def section_extensions(doc: Document, metrics: dict):
    add_heading(doc, "8 扩展自动化能力：作者角色与 CFP", 1)
    add_heading(doc, "8.1 作者角色自动化", 2)
    rr = metrics["role_report"]
    add_paragraph(doc, f"作者角色模块当前已经具备基础自动化能力，但仍应作为“扩展分析层”而不是“主覆盖率层”来解读。当前 `author_role_report.json` 显示，角色流水线输入 {rr['input_rows']} 条作者行，产出 {rr['role_rows']} 条角色行，覆盖 {rr['papers']} 篇论文，其中第一作者行 {rr['first_author_rows']} 条、参与作者行 {rr['participating_author_rows']} 条。与此同时，通讯作者与共同贡献作者目前仍为 0，说明该模块在通讯作者证据链上尚未进入稳定自动化阶段。")
    add_paragraph(doc, "项目内部已经明确给出说明：当前角色报告不是全批次论文级覆盖报告，只覆盖已经进入规范化作者行流水线的论文。因此，在论文写作中更适合将其定位为“当前已经实现的作者角色分析能力”，而不宜把它直接写成与 7075 篇总论文同口径的完成度指标。")
    add_heading(doc, "8.2 CFP 与会议时间元数据", 2)
    cfp = metrics["cfp_report"]
    add_paragraph(doc, f"CFP 自动化是当前系统中完成度较高的一条扩展链路。最新 `cfp_validation_report.json` 显示，系统已在 42 个 conference-year 上建立 {cfp['event_rows']} 条事件记录和 {cfp['edition_rows']} 条版本记录，`conference_years_with_events` 与 `conference_years_with_editions` 都达到 42，缺失 conference-year 为 0。覆盖状态全部为 `complete_unverified`，说明在当前实验范围内，会议关键日期链路已经基本跑通。")
    add_paragraph(doc, "需要注意的是，CFP 报告中的低风险提示主要来自 IACR `metadata.json` 页面返回 403 后转用回退来源，并不代表会议时间信息缺失。对系统论文而言，这一点应被解释为“主链路可用但保留来源级回退说明”，而不是“数据缺口”。")


def section_progress(doc: Document, metrics: dict):
    add_heading(doc, "9 当前进展判断、剩余缺口与下一步方向", 1)
    add_heading(doc, "9.1 已经完成到什么程度", 2)
    add_paragraph(doc, "综合当前正式产物，可以将系统进展概括为“三个已经完成、三个正在收口”。第一，七大会 2020—2025 的会议级论文清单与主标准化事实表已经基本打通，五个会议实现会议总量口径与标准化主表口径完全一致。第二，全量国家、机构、作者、趋势与合作分析已经可在统一事实表之上稳定输出。第三，CFP 主链路已经形成完整元数据表，可支撑截止日期、通知日期与会议日期的自动化汇总。")
    add_paragraph(doc, "与此同时，仍在持续收口的部分主要包括：其一，NDSS 与 IEEE S&P 极少数论文尚未完全进入 `paper_facts.csv`；其二，785 篇论文仍停留在未消歧多机构歧义层，是机构归并与并列机构拆分的主要质量尾部；其三，作者角色链路中的通讯作者自动化尚未成熟，不适合纳入“已完成能力”列表。")
    add_heading(doc, "9.2 当前最关键的技术缺口", 2)
    add_paragraph(doc, "若以“下一步最值得投入的修复方向”排序，第一优先级仍是多机构歧义治理。因为当前已经拿到作者和 affiliation 文本的论文中，相当一部分问题并不是“缺少数据”，而是“并列机构是否能被稳定拆开并归并到机构库”。第二优先级是继续清理标准化入表尾部差异，特别是 NDSS 和 IEEE S&P 中尚未完全进入 `paper_facts.csv` 的 9 篇论文。第三优先级是补强通讯作者、共同贡献和更细粒度角色证据链，使作者分析从“参与者统计”进一步走向“角色结构统计”。")
    add_paragraph(doc, "从论文表达角度看，当前系统已经完全具备写作一篇“顶会数据治理与科研分析自动化工作流系统”论文的主体素材：有完整的多会议多年份实验范围，有统一事实表与 Skill 分层架构，有覆盖率与一致性指标，有国家、机构、作者与 CFP 等扩展分析能力，也有明确剩余问题。后续工作的重点不再是“能不能写”，而是“如何把现有能力组织成更有说服力的实验叙述与图表表达”。")


def section_conclusion(doc: Document, metrics: dict):
    add_heading(doc, "10 结论", 1)
    add_paragraph(doc, f"本文基于 2026 年 6 月 17 日的主线正式产物，对当前顶会数据治理与科研分析自动化系统进行了阶段性汇总。结果表明，系统已经在七个会议、42 个 conference-year 范围内形成较稳定的技能化工作流：按会议接收总量口径覆盖 {metrics['official_total']} 篇论文，按标准化主表口径稳定入表 {metrics['standardized_total']} 篇；作者机构三层口径下的有效成功覆盖达到 {metrics['overall_coverage']['success_ratio']}%；国家、机构、作者、趋势、合作、角色与 CFP 元数据链路均已具备明确产物。")
    add_paragraph(doc, "总体而言，当前项目已经完成了从“零散脚本集合”到“可用于正式论文汇报的系统工程对象”的转变。其价值不只在于生成统计表，更在于通过 Skill 分层、统一事实表和质量审计，把原本难以复用、难以复核的顶会数据整理工作，收束为可持续迭代的科研数据治理流程。对后续论文撰写而言，当前最重要的工作不是重新发明新的统计口径，而是在现有正式产物基础上继续降低尾部歧义、增强角色链路并优化图表表达。")


def appendix(doc: Document, metrics: dict):
    doc.add_page_break()
    add_heading(doc, "附录 A  七大会 conference-year 规模总表", 1)
    rows = [["会议", "年份", "会议总量", "标准化入表", "差值"]]
    coverage_year_map = {(r["conference"], r["year"]): r for r in metrics["coverage_year_rows"]}
    for conf in sorted(metrics["counts_by_year"]):
        for year in range(2020, 2026):
            total = coverage_year_map[(conf, str(year))]["total_papers"]
            std = str(metrics["counts_by_year"][conf][year])
            rows.append([conf, str(year), total, std, str(int(total) - int(std))])
    add_table(doc, rows, [3.1, 1.8, 2.2, 2.2, 1.8], font_size=9.6)

    add_heading(doc, "附录 B  各会议各年份覆盖率详表", 1)
    cov_rows = [["会议", "年份", "单机构", "同国多机构", "未消歧", "有效成功率"]]
    for row in metrics["coverage_year_rows"]:
        success = int(row["single_clean_coverage"]) + int(row["same_country_multi_clear"])
        total = int(row["total_papers"])
        cov_rows.append([
            row["conference"],
            row["year"],
            row["single_clean_coverage"],
            row["same_country_multi_clear"],
            row["unresolved_multi_ambiguity"],
            f"{pct(success, total):.2f}%",
        ])
    add_table(doc, cov_rows, [3.1, 1.6, 2.0, 2.5, 2.0, 2.4], font_size=9.4)

    add_heading(doc, "附录 C  国家、机构与作者头部表", 1)
    country_rows = [["国家/地区", "论文数", "作者数", "机构数"]]
    for row in metrics["country_rows"][:20]:
        country_rows.append([row["country"], row["papers"], row["authors"], row["institutions"]])
    add_table(doc, country_rows, [4.2, 2.0, 2.0, 2.0], "表 C1  国家/地区头部表", font_size=9.6)

    inst_rows = [["机构", "国家/地区", "论文数"]]
    for row in metrics["institution_rows"][:20]:
        inst_rows.append([row["institution_name"], row["country"], row["papers"]])
    add_table(doc, inst_rows, [8.2, 2.5, 1.8], "表 C2  机构头部表", font_size=9.4)

    author_rows = [["作者", "论文数", "活跃会议数"]]
    for row in metrics["author_rows"][:20]:
        author_rows.append([row["author_name"], row["papers"], row["conferences"]])
    add_table(doc, author_rows, [6.6, 2.0, 2.4], "表 C3  作者头部表", font_size=9.6)

    doc.add_page_break()
    add_heading(doc, "附录 D  当前正式产物与结果出口", 1)
    add_paragraph(doc, "为了保证后续论文写作、结果复核和代码逻辑调整能够围绕同一批正式产物展开，当前项目已经把主线输出收束到相对稳定的目录结构中。附录 D 的作用不是给出使用说明，而是为正文中的系统描述提供“正式结果存放位置”的证据层，说明当前哪些目录应被视为主线结果、哪些产物能够直接作为论文统计依据。")
    artifact_rows = [
        ["层次", "目录或文件", "当前用途"],
        ["抽取层", "generated-data/extraction/output/by_conference/", "保存各会议各年份的正式抽取结果与审计表"],
        ["标准化层", "generated-data/normalized/paper_facts.csv", "保存稳定论文主表，供规模统计与后续 join 使用"],
        ["标准化层", "generated-data/normalized/author_affiliation_facts.csv", "保存作者—机构事实长表，是国家/机构/作者统计的核心输入"],
        ["分析层", "generated-data/analysis/country/、institutions/、authors/", "保存国家、机构、作者头部表与趋势表"],
        ["覆盖审计", "generated-data/paper_tables_three_tier/", "保存当前保留的三层覆盖口径总表与 conference-year 详表"],
        ["CFP 元数据", "generated-data/cfp/output/", "保存会议日期、截稿日期与 validation report"],
        ["角色分析", "generated-data/author-roles/author_role_report.json", "保存第一作者与参与作者角色自动化结果摘要"],
        ["论文报告", "generated-data/reports/skills_progress_summary_paper_2026_06_17.docx", "保存本次阶段性研究汇总文档"],
    ]
    add_table(doc, artifact_rows, [2.4, 5.9, 7.1], "表 D1  当前正式产物地图", font_size=9.2)
    add_paragraph(doc, "这一结果地图说明，当前系统已经不再依赖分散在历史目录中的临时文件来支撑统计结论。对后续“根据结果反推代码逻辑”的工作而言，最重要的是围绕标准化层、覆盖审计层和分析层三处正式产物进行闭环，而不是回到零散 HTML、测试目录或历史实验报告中寻找依据。")

    doc.add_page_break()
    add_heading(doc, "附录 E  2025 年重点国家快照与趋势增量", 1)
    add_paragraph(doc, "为了补强正文对全量国家格局的讨论，附录 E 进一步列出 2025 年前十五国家快照，以及若干重点国家从 2020 年到 2025 年的净增量。相较只列总体头部表，这一附录更适合在后续论文中支撑“阶段性上升国家”和“高位稳定国家”的对比分析。")
    country_2025_rows = [["国家/地区", "2025 论文数", "2025 作者数", "2025 机构数"]]
    for row in metrics["countries_2025"][:15]:
        country_2025_rows.append([row["country"], row["papers"], row["authors"], row["institutions"]])
    add_table(doc, country_2025_rows, [4.0, 2.3, 2.3, 2.3], "表 E1  2025 年前十五国家/地区快照", font_size=9.6)

    trend_focus_rows = [["国家/地区", "2020 论文数", "2025 论文数", "峰值年份", "净增量"]]
    for row in metrics["top_trend_countries"][:12]:
        trend_focus_rows.append([row["entity_name"], row["papers_first"], row["papers_last"], row["peak_year"], row["net_change"]])
    add_table(doc, trend_focus_rows, [4.0, 2.1, 2.1, 2.1, 2.1], "表 E2  重点国家 2020—2025 变化摘要", font_size=9.6)
    add_paragraph(doc, "从表 E2 可以看出，中国是 2020—2025 期间增长最显著的国家，净增量达到 371 篇；美国虽然仍保持最大规模，但其峰值出现在 2024 年而非 2025 年，反映出其高位平台期特征；德国、新加坡与 Hong Kong 等实体则体现出更明显的阶段性上升态势。这样的附录表既可以支撑正文中的总结性论断，也便于后续将不同国家进一步拆分到会议层或机构层做交叉分析。")


def build_doc(metrics: dict):
    doc = Document()
    configure_document(doc)
    title_page(doc)
    section_intro(doc)
    section_scope_and_contract(doc, metrics)
    section_framework(doc, metrics)
    section_scale(doc, metrics)
    section_coverage(doc, metrics)
    section_country(doc, metrics)
    section_institution_author(doc, metrics)
    section_extensions(doc, metrics)
    section_progress(doc, metrics)
    section_conclusion(doc, metrics)
    appendix(doc, metrics)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    doc.save(DOCX_PATH)


def main():
    metrics = build_metrics()
    build_figures(metrics)
    build_doc(metrics)
    print(DOCX_PATH)


if __name__ == "__main__":
    main()
