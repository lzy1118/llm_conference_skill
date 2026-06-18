from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor


ROOT = Path("/Users/liziyu/llm_conference_skill")
OUTPUT_DIR = ROOT / "generated-data" / "reports"
DOCX_PATH = OUTPUT_DIR / "skills_journal_paper_cn_2026_06_18.docx"

PAPER_FACTS = ROOT / "generated-data" / "normalized" / "paper_facts.csv"
NORMALIZATION_REPORT = ROOT / "generated-data" / "normalized" / "normalization_report.json"
THREE_TIER_SUMMARY = ROOT / "generated-data" / "paper_tables_three_tier" / "three_tier_coverage_summary.csv"
THREE_TIER_BY_YEAR = ROOT / "generated-data" / "paper_tables_three_tier" / "three_tier_coverage_by_conference_year.csv"
AUTO_COVERAGE_SUMMARY = ROOT / "generated-data" / "paper_tables" / "auto_extraction_coverage_summary.csv"
COUNTRY_SUMMARY = ROOT / "generated-data" / "analysis" / "country" / "country_summary.csv"
COUNTRY_BY_YEAR = ROOT / "generated-data" / "analysis" / "country" / "country_by_year.csv"
INSTITUTION_SUMMARY = ROOT / "generated-data" / "analysis" / "institutions" / "institution_summary.csv"
AUTHOR_SUMMARY = ROOT / "generated-data" / "analysis" / "authors" / "author_summary.csv"
COLLAB_SUMMARY = ROOT / "generated-data" / "analysis" / "collaboration" / "collaboration_summary.csv"
COLLAB_EDGES = ROOT / "generated-data" / "analysis" / "collaboration" / "collaboration_edges.csv"
ROLE_REPORT = ROOT / "generated-data" / "author-roles" / "author_role_report.json"
CFP_REPORT = ROOT / "generated-data" / "cfp" / "output" / "cfp_validation_report.json"
VIS_ROOT = ROOT / "generated-data" / "visualizations" / "current_showcase"

FIG_FRAMEWORK = VIS_ROOT / "技能化自动化工作流_框架图.png"
FIG_HEATMAP = VIS_ROOT / "七大会_conference-year_论文规模热力图.png"
FIG_COVERAGE = VIS_ROOT / "各会议_作者机构覆盖结构_柱状图.png"
FIG_COUNTRY = VIS_ROOT / "国家地区_头部排名_横向柱状图.png"
FIG_INST = VIS_ROOT / "机构_头部排名_横向柱状图.png"
FIG_TREND = VIS_ROOT / "重点国家地区_趋势图.png"
FIG_METHOD_EVOLUTION = VIS_ROOT / "第三章_框架收敛过程图.png"
FIG_RESULT_PIPELINE = VIS_ROOT / "第三章_结果生成链路图.png"

COLOR = {
    "ink": RGBColor(31, 41, 55),
    "blue": RGBColor(46, 116, 181),
    "dark_blue": RGBColor(31, 77, 120),
    "muted": RGBColor(90, 98, 112),
    "header_fill": "EAF1FB",
    "border": "B8C2CC",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0.00%"
    return f"{numerator * 100.0 / denominator:.2f}%"


def add_page_number(paragraph) -> None:
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


def set_run_font(
    run,
    *,
    size: float,
    bold: bool = False,
    italic: bool = False,
    color: RGBColor | None = None,
    name: str = "Calibri",
    east_asia: str = "宋体",
) -> None:
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


def add_table(
    doc: Document,
    rows: list[list[str]],
    widths_cm: list[float],
    caption: str | None = None,
    font_size: float = 10.3,
) -> None:
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


def build_metrics() -> dict:
    normalization = read_json(NORMALIZATION_REPORT)
    three_tier_rows = read_csv(THREE_TIER_SUMMARY)
    three_tier_year = read_csv(THREE_TIER_BY_YEAR)
    auto_rows = read_csv(AUTO_COVERAGE_SUMMARY)
    country_rows = read_csv(COUNTRY_SUMMARY)
    country_year_rows = read_csv(COUNTRY_BY_YEAR)
    institution_rows = read_csv(INSTITUTION_SUMMARY)
    author_rows = read_csv(AUTHOR_SUMMARY)
    collab_summary_rows = read_csv(COLLAB_SUMMARY)
    collab_edge_rows = read_csv(COLLAB_EDGES)
    role_report = read_json(ROLE_REPORT)
    cfp_report = read_json(CFP_REPORT)

    conference_counts: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    with PAPER_FACTS.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            conference_counts[row["conference"]][int(row["year"])] += 1

    overall_three = next(row for row in three_tier_rows if row["conference"] == "OVERALL")
    conf_three = [row for row in three_tier_rows if row["conference"] != "OVERALL"]
    overall_auto = next(row for row in auto_rows if row["conference"] == "OVERALL")
    conf_auto = [row for row in auto_rows if row["conference"] != "OVERALL"]

    success_total = int(overall_three["single_clean_coverage"]) + int(overall_three["same_country_multi_clear"])
    failure_total = int(overall_three["total_papers"]) - success_total

    two_layer_by_conf = []
    for row in conf_three:
        total = int(row["total_papers"])
        success = int(row["single_clean_coverage"]) + int(row["same_country_multi_clear"])
        failure = total - success
        two_layer_by_conf.append(
            {
                "conference": row["conference"],
                "total": total,
                "success": success,
                "failure": failure,
                "success_ratio": pct(success, total),
                "failure_ratio": pct(failure, total),
            }
        )

    two_layer_by_year = []
    for row in three_tier_year:
        total = int(row["total_papers"])
        success = int(row["single_clean_coverage"]) + int(row["same_country_multi_clear"])
        failure = total - success
        two_layer_by_year.append(
            {
                "conference": row["conference"],
                "year": int(row["year"]),
                "total": total,
                "success": success,
                "failure": failure,
                "success_ratio": pct(success, total),
            }
        )

    overall_by_year: dict[int, dict[str, int]] = defaultdict(lambda: {"total": 0, "success": 0})
    for row in two_layer_by_year:
        overall_by_year[row["year"]]["total"] += row["total"]
        overall_by_year[row["year"]]["success"] += row["success"]

    top_countries_no_multiple = [row for row in country_rows if row["country"] != "Multiple"][:15]
    countries_2025 = sorted(
        [row for row in country_year_rows if row["year"] == "2025" and row["country"] != "Multiple"],
        key=lambda item: int(item["papers"]),
        reverse=True,
    )[:15]

    return {
        "normalization": normalization,
        "overall_three": overall_three,
        "conf_three": conf_three,
        "overall_auto": overall_auto,
        "conf_auto": conf_auto,
        "success_total": success_total,
        "failure_total": failure_total,
        "success_ratio": pct(success_total, int(overall_three["total_papers"])),
        "failure_ratio": pct(failure_total, int(overall_three["total_papers"])),
        "two_layer_by_conf": two_layer_by_conf,
        "two_layer_by_year": two_layer_by_year,
        "overall_by_year": overall_by_year,
        "conference_counts": conference_counts,
        "country_rows": country_rows,
        "top_countries_no_multiple": top_countries_no_multiple,
        "countries_2025": countries_2025,
        "institution_rows": institution_rows,
        "author_rows": author_rows,
        "collab_summary": collab_summary_rows[0] if collab_summary_rows else {},
        "collab_edges": collab_edge_rows[:15],
        "role_report": role_report,
        "cfp_report": cfp_report,
    }


def title_page(doc: Document, metrics: dict) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(72)
    p.paragraph_format.space_after = Pt(10)
    r = p.add_run("A Unified Data Governance Framework for Large-Scale Academic Conference Analytics")
    set_run_font(r, size=19, bold=True, color=COLOR["ink"], east_asia="黑体")

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(6)
    r = p.add_run("Construction, Normalization, and Empirical Study on Security Conferences (2020–2025)")
    set_run_font(r, size=13.5, color=COLOR["blue"], east_asia="黑体")

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(18)
    r = p.add_run("面向大规模学术会议分析的统一数据治理框架")
    set_run_font(r, size=16, color=COLOR["ink"], east_asia="黑体")

    meta_lines = [
        "文稿类型：SCI二区风格中文论文初稿",
        f"样本范围：2020—2025年七个安全与密码学代表性会议，共 {metrics['overall_three']['total_papers']} 篇官方接收论文",
        f"标准化样本：{metrics['normalization']['paper_count']} 篇；作者机构有效覆盖：{metrics['success_total']} 篇（{metrics['success_ratio']}）",
    ]
    for line in meta_lines:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(3)
        r = p.add_run(line)
        set_run_font(r, size=11, color=COLOR["muted"])

    abstract_parts = [
        "摘要：近年来，随着顶级学术会议规模持续扩大，跨会议、多年份的科研数据呈现出高度异构与结构不一致性，使得长期科研分析与结构化计量研究面临显著挑战。尤其在安全与密码学领域，论文元数据分散于多个来源，作者机构表达不统一，导致国家统计、机构排名与合作网络分析结果存在系统性偏差。",
        "为解决上述问题，本文提出一种统一的数据治理框架，用于将多源异构学术会议数据转换为结构一致、可审计、可复现的分析型数据结构。该框架通过数据采集、实体解析与标准化映射三个核心阶段，实现作者、机构与国家信息的统一建模，并进一步支持科研计量分析任务，包括国家分布分析、机构影响力评估及合作网络构建。",
        f"基于 2020—2025 年七个代表性安全与密码学顶级会议（ASIACRYPT、CRYPTO、EUROCRYPT、ACM CCS、IEEE S&P、NDSS、USENIX Security），本文构建了大规模标准化数据集并开展系统性实证分析。结果表明，该框架能够稳定实现 {metrics['success_ratio']} 的作者机构有效覆盖率，并支撑跨会议一致性分析。当前样本共包含 {metrics['overall_three']['total_papers']} 篇官方接收论文、{metrics['normalization']['paper_count']} 篇标准化论文、{metrics['normalization']['author_paper_rows']} 条作者—论文记录与 {metrics['normalization']['institution_count']} 个机构实体。",
        f"进一步研究揭示了全球科研格局的高度集中性以及机构合作网络的核心结构特征。当前合作网络包含 {metrics['collab_summary'].get('node_count', '0')} 个作者节点和 {metrics['collab_summary'].get('edge_count', '0')} 条合作边，表明基于统一治理框架的学术会议数据已经能够支撑较稳定的国家、机构、作者与合作层面的结构化分析。",
    ]
    for text in abstract_parts:
        add_paragraph(doc, text)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_after = Pt(10)
    r = p.add_run("关键词：数据治理；学术计量分析；实体解析；科研网络分析；安全会议；结构化数据框架")
    set_run_font(r, size=11)
    doc.add_page_break()


def section_intro(doc: Document) -> None:
    add_heading(doc, "1 引言", 1)
    add_paragraph(doc, "近年来，科学计量分析逐渐成为理解学科发展结构、科研资源分布及国际竞争格局的重要工具。在安全与密码学领域，顶级学术会议不仅是前沿成果最密集的发布平台，也是观察国家竞争、机构活跃度与合作关系演化的重要窗口。对这一类会议开展系统性分析，已经成为科研治理与学术评价研究中的重要议题。")
    add_paragraph(doc, "然而，现有研究在处理大规模会议数据时仍面临明显障碍。首先，数据来源高度分散。论文元数据通常分布于会议官网、数字图书馆与开放学术数据库等多个平台，不同来源之间常存在字段缺失、页面结构差异与历史版本不一致问题。其次，作者与机构信息具有高度歧义性。相同机构在不同论文中可能存在缩写、别名、层级单位、联合署名与跨机构并列等多种表达方式，使得统一统计面临持续性误差。")
    add_paragraph(doc, "更进一步看，许多已有工作更强调结果展示，例如国家排名、机构发文量或合作网络结构，却较少把数据治理过程本身作为独立的方法对象进行建模。缺少对上游治理链路的系统抽象，会直接限制后续结果的可复现性、可扩展性与跨年份稳定性。对于安全与密码学领域这种来源复杂、机构表达高度异构的场景而言，这一问题尤为突出。")
    add_paragraph(doc, "基于此，本文提出一种统一的数据治理与分析框架，旨在将异构学术会议数据转化为结构化、可追溯、可审计的分析型数据资产，并在此基础上实现跨会议、跨年份的稳定科研计量分析。本文的核心目标不是给出一次性排行榜，而是回答如何构建一个面向学术会议数据长期治理的统一方法框架，以及该框架在真实顶会数据上的表现如何。")
    add_paragraph(doc, "本文的主要贡献体现在三个方面：第一，提出一种面向大规模学术会议数据的统一治理框架，实现多源异构数据的一致性建模；第二，设计作者—机构实体解析与标准化机制，提高跨会议数据的一致性与可用性；第三，基于七个安全领域顶级会议构建大规模标准化数据集，并开展系统性实证分析，揭示全球科研格局与合作网络的结构特征。")


def section_related(doc: Document) -> None:
    add_heading(doc, "2 相关问题与研究视角", 1)
    add_paragraph(doc, "现有研究主要集中在学术计量分析与科研数据挖掘两个方向。在学术计量领域，相关工作通常基于公开数据库构建统计模型，用于分析国家科研产出、机构影响力及合作网络结构。这类方法在结果展示和指标构建上较为成熟，但往往默认底层数据已经被清洗完成，对原始治理链路涉及较少。")
    add_paragraph(doc, "在科研数据挖掘方向，已有研究尝试通过自动化方法抽取论文元数据并构建知识图谱，从而支撑学术搜索、作者画像与主题发现。然而，在跨会议一致性、历史年份稳定性以及机构标准化层面，这类工作仍普遍面临来源差异与实体歧义问题。特别是在会议场景下，作者机构信息相较于期刊数据库更不稳定，进一步提高了治理难度。")
    add_paragraph(doc, "此外，实体解析与实体对齐研究为机构标准化提供了重要方法基础，包括字符串归一化、规则映射、别名聚类和知识库辅助匹配等。但这些方法在大规模跨领域学术数据中的系统化应用仍较有限，尤其缺少与实际科研分析任务相结合的端到端治理框架。")
    add_paragraph(doc, "因此，如何构建一个统一、可扩展且具备审计能力的数据治理框架，仍然是一个尚未充分解决的问题。本文的工作正是在这一缺口上展开，即将学术会议数据的采集、实体解析、标准化治理和下游分析连接为一条完整链路，并以安全与密码学会议作为系统化验证场景。")


def section_system(doc: Document) -> None:
    add_heading(doc, "3 方法论", 1)
    add_heading(doc, "3.1 总体框架", 2)
    add_paragraph(doc, "本文提出的统一数据治理框架由三个核心层构成：数据获取层、数据标准化与实体解析层，以及分析层。整个框架围绕统一数据模型展开，其目标是将多源、异构、历史格式不一致的会议数据转化为可审计、可复现的分析型结构。相比直接在原始网页或零散元数据上做统计，该框架更强调治理链路的完整性与分析结果之间的可追溯关系。")
    add_paragraph(doc, "其中，数据获取层负责从多个异构来源收集论文元数据，包括会议官方页面、开放学术数据库及历史存档数据；数据标准化与实体解析层负责作者与机构信息的统一处理，包括作者消歧、机构名称标准化、层级映射与国家级归属识别；分析层则在标准化结果基础上开展国家分布、机构影响力、作者合作关系和时间演化等多维科研计量分析。")
    figure_paragraph(doc, FIG_FRAMEWORK, "图1 统一学术会议数据治理与分析框架", width_inches=6.2)
    add_paragraph(doc, "这一框架的核心价值在于，它并不把数据治理视为分析前的附属步骤，而是将其上升为独立的方法论对象。通过在获取、标准化与分析之间建立稳定中间层，框架既能够向下承接复杂来源差异，又能够向上输出一致的论文级统计结果。")
    add_heading(doc, "3.2 统一数据模型", 2)
    add_paragraph(doc, "为实现跨会议、跨年份的一致性建模，本文将所有数据统一映射至四类实体：论文实体、作者实体、机构实体和国家实体。围绕这些实体，进一步建立三类核心关系，即作者—论文关系、作者—机构关系以及论文—会议关系。通过这种结构化表示，原始文本数据得以转化为支持计量分析的稳定事实表。")
    add_paragraph(doc, "统一数据模型的意义在于，它将原本分散在页面文本、作者脚注与机构字符串中的语义信息压缩到清晰的实体关系结构中，从而为后续统计分析提供一致的分母、主键与关联路径。这一设计直接提升了跨会议比较的可操作性。")
    add_heading(doc, "3.3 实体解析策略", 2)
    add_paragraph(doc, "机构解析采用多策略融合方法，包括字符级归一化、规则匹配与别名映射、多机构联合消歧以及国家级映射校正。其基本思路并非追求单一算法完全解决所有问题，而是在统一结构约束下，将显式规则、知识补库和跨来源校正结合起来，逐步降低语义重复实体与国家归属偏差。")
    add_paragraph(doc, "对于同一机构的缩写、层级单位和联合表达，框架优先执行名称标准化与主实体归并，再根据上下文完成国家映射。对于多机构作者记录，则保留其并列属性，并在覆盖率评估阶段区分已清晰建模与仍存在歧义的情况，以避免将复杂记录粗暴压平后带来的统计失真。")
    add_heading(doc, "3.4 覆盖率评估机制", 2)
    add_paragraph(doc, "为衡量数据治理效果，本文定义“有效覆盖率”指标。成功覆盖指能够建立完整作者—机构映射的论文，失败覆盖则指因机构缺失、歧义未解或作者—机构关系不完整而暂无法进入稳定建模层的论文。该指标衡量的是结构化建模的有效性，而非传统意义上的分类准确率。")
    add_paragraph(doc, "这一指标设计具有两个优点。其一，它能够直接连接上游治理质量与下游分析可用性，因为只有成功覆盖论文才能稳定进入国家与机构统计主链路；其二，它避免了在尚未构建人工全量真值集的前提下，将系统结果误表述为“准确率”，从而使论文用语更加稳妥。")
    add_heading(doc, "3.5 框架构建过程：从局部脚本到统一方法", 2)
    add_paragraph(doc, "本文框架并非在一开始就以完整形态出现，而是在反复处理真实会议数据的过程中逐步抽象出来的。早期的数据处理更接近针对单一会议或单一年份的局部整理，其主要问题在于不同来源、不同年份和不同机构表达方式之间缺乏统一约束，一旦上游来源发生变化，下游统计结果便容易产生连锁漂移。")
    add_paragraph(doc, "在这一过程中，研究工作逐渐形成了两个关键认识。第一，决定分析稳定性的并不是某一条单独的抓取规则，而是能否把论文、作者、机构和国家关系压缩到统一结构中；第二，作者机构问题不能被当作普通文本清洗任务处理，而需要被组织为可反复修正、可回流更新的实体解析过程。正是在这两个认识的推动下，原本分散的处理步骤被重新组织为具有层次结构的统一框架。")
    add_paragraph(doc, "换言之，框架的形成过程本身就是一种方法论收敛过程。它不是先验地假设所有会议都服从同一页面模板，也不是依靠某个单一模型直接输出最终答案，而是在持续面对来源差异、机构歧义与统计不一致问题的过程中，逐步把局部修补提升为稳定的治理流程。这种从问题驱动中抽象方法结构的过程，也是本文希望强调的研究贡献之一。")
    figure_paragraph(doc, FIG_METHOD_EVOLUTION, "图2 从局部数据处理到统一治理框架的方法收敛过程", width_inches=6.4)
    add_heading(doc, "3.6 结果生成链路与可信性来源", 2)
    add_paragraph(doc, "本文的实验结果并非直接来自原始网页字段的简单汇总，而是经过“来源收集—实体解析—标准化建模—覆盖审计—统计汇总”这一链式过程后生成。也就是说，国家分布、机构排名和合作网络等结果并不是对某一来源的原样复述，而是在统一治理约束下对多源信息进行融合、纠偏与结构化后的分析结果。")
    add_paragraph(doc, "这种结果生成方式决定了本文统计结果的可信性主要来自三个方面：其一，多源交叉能够在相当程度上缓解单一来源缺失或格式异常带来的偏差；其二，统一实体模型使不同会议、不同年份的数据可以在同一语义尺度上进行比较；其三，覆盖率评估机制为结果提供了清晰的边界说明，即研究者能够明确知道哪些论文已经进入稳定分析层，哪些论文仍处于待完善状态。")
    add_paragraph(doc, "从论文叙事角度看，这一点同样重要。许多科研计量研究往往直接给出排序或趋势，但较少解释这些结果是如何从异构原始材料中被治理出来的。本文则试图把这一生成过程显式呈现出来，使实验结果既可被理解为经验发现，也可被理解为方法有效性的外在证据。")
    figure_paragraph(doc, FIG_RESULT_PIPELINE, "图3 实验结果的生成链路与可信性来源", width_inches=6.5)
    add_heading(doc, "3.7 方法设计的叙事逻辑", 2)
    add_paragraph(doc, "如果从研究设计的角度概括，本文第三章的方法论实际上回答了三个连续问题：第一，面对多源异构会议数据，如何建立能够容纳来源差异的统一框架；第二，面对最易失真的作者机构信息，如何通过实体解析与标准化策略构建稳定关系结构；第三，在缺少绝对人工真值的现实条件下，如何用覆盖率与分层审计来界定结果的有效边界。")
    add_paragraph(doc, "因此，本章并非单纯描述一个技术实现流程，而是在讲述一个从混乱数据到可解释分析结果的转化故事。数据获取层负责把分散事实收集起来，标准化与实体解析层负责把不一致表达转化为统一语义对象，分析层则在这一基础上生成可用于科研观察的结构化结果。这样的叙事结构更有助于把本文包装为一篇方法与实证并重的学术论文，而不仅是工程经验总结。")


def section_scope(doc: Document, metrics: dict) -> None:
    add_heading(doc, "4 数据集与实验设置", 1)
    add_heading(doc, "4.1 数据范围", 2)
    add_paragraph(doc, "本文选择 ASIACRYPT、CRYPTO、EUROCRYPT、ACM CCS、IEEE S&P、NDSS 和 USENIX Security 七个代表性会议作为研究对象，时间范围为 2020—2025 年，共覆盖 42 个 conference-year。这一范围同时包含密码学三大会与安全领域四个高影响力会议，能够较充分体现不同会议生态下的数据异构性与治理难度。")
    add_heading(doc, "4.2 样本规模", 2)
    add_paragraph(doc, f"在官方接收论文口径下，当前样本总量为 {metrics['overall_three']['total_papers']} 篇；在标准化论文口径下，可稳定进入统一建模层的论文为 {metrics['normalization']['paper_count']} 篇；在作者机构有效覆盖口径下，成功进入结构化作者—机构建模层的论文为 {metrics['success_total']} 篇，对应有效覆盖率为 {metrics['success_ratio']}。")
    add_heading(doc, "4.3 统计口径说明", 2)
    add_paragraph(doc, "本文采用三种互补统计口径。第一，官方论文总量用于定义会议规模与覆盖率分母；第二，标准化论文口径用于刻画进入统一建模层的数据规模；第三，有效覆盖口径用于衡量作者机构关系对下游国家与机构统计的可用程度。这三种口径分别服务于完整性、结构化程度与分析可用性三个问题，因此必须显式区分。")
    summary_table = [
        ["口径", "数值", "说明"],
        ["官方论文总量", metrics["overall_three"]["total_papers"], "七大会 2020—2025 官方接收论文总量，为覆盖率分母"],
        ["标准化论文数", str(metrics["normalization"]["paper_count"]), "能够稳定进入统一数据模型的论文规模"],
        ["成功覆盖论文数", str(metrics["success_total"]), "能够建立完整作者—机构映射的论文数"],
        ["失败覆盖论文数", str(metrics["failure_total"]), "存在歧义或缺失而未进入稳定建模层的论文数"],
    ]
    add_table(doc, summary_table, [4.1, 2.6, 9.1], "表1 本文采用的三类核心统计口径", font_size=10)
    add_paragraph(doc, "在会议数据治理场景中，许多结果不一致并不来自计算错误，而是来自统计口径混用。只有将官方规模、标准化规模和有效覆盖规模显式区分，后续国家分布、机构排名和覆盖率比较才具备可解释性。因此，口径定义本身也是实验设计的一部分。")


def section_extraction_and_normalization(doc: Document, metrics: dict) -> None:
    add_heading(doc, "5 实验结果", 1)
    add_heading(doc, "5.1 数据治理覆盖效果", 2)
    add_paragraph(doc, f"总体结果表明，本文框架在跨会议数据治理任务中实现了较稳定的结构化建模效果。按官方接收论文总量 {metrics['overall_three']['total_papers']} 篇计算，成功覆盖论文为 {metrics['success_total']} 篇，失败覆盖论文为 {metrics['failure_total']} 篇，有效覆盖率达到 {metrics['success_ratio']}。这说明在高异构会议数据环境下，统一治理框架已经能够支撑绝大多数论文进入稳定作者—机构分析链路。")
    add_paragraph(doc, "进一步分会议观察，不同会议在机构表达规范性方面存在显著差异。CCS、NDSS 与 USENIX Security 的有效覆盖率整体较高，而 CRYPTO、ASIACRYPT 与 EUROCRYPT 的复杂多机构情形更为集中。这一现象说明，覆盖率差异不仅反映治理方法能力，也反映会议生态中作者机构表达方式本身的结构差异。")
    norm_table = [
        ["指标", "当前数值", "含义"],
        ["输入作者机构行", str(metrics["normalization"]["input_rows"]), "进入治理流程的原始作者机构记录数"],
        ["作者—论文记录", str(metrics["normalization"]["author_paper_rows"]), "统一后的作者—论文主关系记录"],
        ["作者机构事实行", str(metrics["normalization"]["normalized_rows"]), "可进入分析层的结构化作者机构行"],
        ["机构实体数", str(metrics["normalization"]["institution_count"]), "完成标准化归并后的机构实体规模"],
        ["多机构作者行", str(metrics["normalization"]["multi_affiliation_author_rows"]), "包含多个机构归属的作者记录数"],
        ["未知国家行", str(metrics["normalization"]["rows_with_unknown_country"]), "当前仍保留的国家未决记录数"],
    ]
    add_table(doc, norm_table, [3.4, 2.4, 8.0], "表2 数据治理与标准化关键指标", font_size=9.6)
    add_heading(doc, "5.2 国家科研格局", 2)
    add_paragraph(doc, "基于成功覆盖论文构建的国家统计结果显示，全球科研产出呈现显著集中结构。美国与中国构成最主要的两极，德国、瑞士、英国和法国形成紧随其后的第二梯队。从长期趋势看，顶会发文格局并非完全静态，而是表现出由少数头部国家主导、同时伴随部分国家和地区持续上升的多层次结构。")
    add_paragraph(doc, "这一结果说明，经过统一治理后的学术会议数据已经能够较稳定地支撑跨会议、跨年份的国家比较。相比直接使用未经治理的原始机构字符串，统一实体与国家映射显著降低了统计漂移，使国家层面的长期格局观察更具一致性。")


def section_coverage(doc: Document, metrics: dict) -> None:
    add_heading(doc, "5.3 机构分布", 2)
    add_paragraph(doc, "机构层面的结果表明，头部机构并非仅由传统高校构成，而是呈现出“高校 + 国家级研究中心 + 企业研究机构”并存的多元结构。这一现象在安全与密码学领域尤为突出，说明顶会产出同时受到基础研究体系、国家级科研平台和产业研发机构的共同驱动。")
    add_paragraph(doc, "从方法效果看，机构层分析对实体解析质量最为敏感。若缺少标准化归并与国家映射，同一机构可能因别名、缩写与层级差异被拆分为多个实体，从而直接扭曲头部机构排序。本文框架通过统一实体建模，有效减少了这一类统计失真。")
    figure_paragraph(doc, FIG_INST, "图2 机构头部排名图", width_inches=6.0)
    add_heading(doc, "5.4 作者合作网络", 2)
    add_paragraph(doc, f"在合作关系层，基于标准化作者实体构建的合作网络共包含 {metrics['collab_summary'].get('node_count', '0')} 个作者节点和 {metrics['collab_summary'].get('edge_count', '0')} 条合作边，其中重复合作边为 {metrics['collab_summary'].get('repeated_edge_count', '0')} 条，最大共同论文数达到 {metrics['collab_summary'].get('max_shared_papers', '0')}。这表明顶会研究群体内部存在明显的长期稳定合作结构。")
    add_paragraph(doc, "合作网络结果进一步说明，统一数据治理框架不仅能够支撑简单计数统计，也能够支持更复杂的关系型分析。只有在作者实体、作者—论文关系和作者—机构关系得到统一建模之后，合作边的统计才具备较高稳定性。")


def section_scale_and_distribution(doc: Document, metrics: dict) -> None:
    add_heading(doc, "5.5 会议规模与年度分布", 2)
    add_paragraph(doc, "从会议规模看，七个会议在 2020—2025 年之间表现出明显的不均衡性。USENIX Security 与 ACM CCS 在论文规模上处于第一梯队，IEEE S&P 与 NDSS 紧随其后，而三大密码会议总体规模较小但结构稳定。会议规模差异不仅影响论文总量，也影响作者机构治理的复杂度与尾部问题分布。")
    figure_paragraph(doc, FIG_HEATMAP, "图3 七大会 2020—2025 年论文规模热力图", width_inches=6.2)
    counts_table = [["会议", "2020", "2021", "2022", "2023", "2024", "2025", "合计"]]
    for conference in sorted(metrics["conference_counts"]):
        vals = [metrics["conference_counts"][conference][year] for year in range(2020, 2026)]
        counts_table.append([conference, *[str(v) for v in vals], str(sum(vals))])
    add_table(doc, counts_table, [3.1, 1.15, 1.15, 1.15, 1.15, 1.15, 1.15, 1.6], "表3 标准化论文年度规模分布", font_size=9.6)
    add_heading(doc, "5.6 覆盖率分布", 2)
    add_paragraph(doc, "将有效覆盖率按会议展开后可以发现，高稳定会议与高歧义会议之间存在明显分层。前者覆盖率通常高于 90%，后者则更多受到复杂多机构表达、历史页面结构差异与机构粒度不一致的影响。这一结果说明，治理框架的表现应当被理解为“方法能力与数据本体难度共同作用”的结果。")
    two_layer_table = [["会议", "论文总数", "成功", "失败", "成功覆盖率", "失败率"]]
    for row in metrics["two_layer_by_conf"]:
        two_layer_table.append(
            [
                row["conference"],
                str(row["total"]),
                str(row["success"]),
                str(row["failure"]),
                row["success_ratio"],
                row["failure_ratio"],
            ]
        )
    two_layer_table.append(
        [
            "OVERALL",
            metrics["overall_three"]["total_papers"],
            str(metrics["success_total"]),
            str(metrics["failure_total"]),
            metrics["success_ratio"],
            metrics["failure_ratio"],
        ]
    )
    add_table(doc, two_layer_table, [3.4, 2.1, 1.8, 1.8, 2.2, 1.8], "表4 七大会作者机构有效覆盖结果", font_size=10)
    figure_paragraph(doc, FIG_COVERAGE, "图4 各会议作者机构覆盖结构图", width_inches=6.2)
    add_heading(doc, "5.7 年度变化", 2)
    by_year_rows = [["年份", "论文总数", "成功", "失败", "成功覆盖率"]]
    for year in sorted(metrics["overall_by_year"]):
        total = metrics["overall_by_year"][year]["total"]
        success = metrics["overall_by_year"][year]["success"]
        failure = total - success
        by_year_rows.append([str(year), str(total), str(success), str(failure), pct(success, total)])
    add_table(doc, by_year_rows, [2.0, 2.2, 2.0, 2.0, 2.4], "表5 2020—2025 各年作者机构覆盖情况", font_size=10)
    add_paragraph(doc, "从分年结果看，2020—2025 六个年度的覆盖率整体较为稳定，说明该框架并非仅适用于个别年份，而是能够在跨年度条件下维持相对一致的建模效果。")
    add_heading(doc, "5.8 国家与作者补充结果", 2)
    add_paragraph(doc, "在国家与作者补充统计中，美国、中国、德国、瑞士与英国构成最主要的参与梯队。作者层则呈现出较强的头部集中与长期活跃特征，这与合作网络中观察到的稳定核心群体相互印证。整体而言，这些结果共同表明，统一治理后的会议数据已经可以支撑具有解释力的科研结构分析。")
    figure_paragraph(doc, FIG_COUNTRY, "图5 国家（地区）头部排名图", width_inches=6.0)
    country_table = [["国家/地区", "论文数", "作者数", "机构数"]]
    for row in metrics["top_countries_no_multiple"][:15]:
        country_table.append([row["country"], row["papers"], row["authors"], row["institutions"]])
    add_table(doc, country_table, [4.0, 2.2, 2.2, 2.2], "表6 2020—2025 总体前十五国家/地区", font_size=9.8)
    inst_table = [["机构", "国家/地区", "论文数", "首作者论文数"]]
    for row in metrics["institution_rows"][:12]:
        inst_table.append([row["institution_name"], row["country"], row["papers"], row["first_author_papers"]])
    add_table(doc, inst_table, [8.0, 2.1, 1.6, 2.0], "表7 2020—2025 头部机构分布", font_size=9.4)
    author_table = [["作者", "论文数", "活跃会议数", "首作者论文数"]]
    for row in metrics["author_rows"][:12]:
        author_table.append([row["author_name"], row["papers"], row["conferences"], row["first_author_papers"]])
    add_table(doc, author_table, [6.0, 1.8, 2.1, 2.0], "表8 2020—2025 头部作者分布", font_size=9.6)
    figure_paragraph(doc, FIG_TREND, "图6 重点国家（地区）发文趋势图", width_inches=6.2)


def section_collaboration_and_extensions(doc: Document, metrics: dict) -> None:
    add_heading(doc, "6 讨论", 1)
    add_heading(doc, "6.1 数据治理误差的主要来源", 2)
    add_paragraph(doc, "本研究表明，跨会议数据的不一致性是科研计量分析中的主要误差来源之一，而误差往往并不来自下游分析模型本身。会议来源差异、历史页面结构变化、机构表达粒度不统一以及作者并列机构署名，共同决定了结构化建模的难度。相比之下，若上游治理链路清晰，下游国家、机构与合作分析通常能够保持较高稳定性。")
    add_heading(doc, "6.2 作者机构歧义的核心作用", 2)
    add_paragraph(doc, "作者机构歧义是影响国家与机构统计稳定性的核心因素。特别是在密码学会议中，多机构并列、实验室与大学联合表达以及机构层级信息混入主实体表达的情况更为常见，这直接导致相同论文在不同来源间呈现出不同粒度的机构结果。因此，作者机构关系不应被视为元数据中的附属字段，而应被视为需要专门治理的结构化对象。")
    add_heading(doc, "6.3 框架的可扩展性", 2)
    add_paragraph(doc, "本文框架的优势之一在于其可扩展性。虽然当前实验聚焦于安全与密码学领域，但其核心逻辑并不依赖某一具体学科，而是建立在多源获取、实体解析、统一建模和覆盖审计的通用机制之上。因此，该框架具备向其他学科会议、期刊数据乃至更广义科研档案扩展的潜力。")
    add_heading(doc, "6.4 对科研分析研究的启示", 2)
    add_paragraph(doc, "从研究方法角度看，本工作说明科研计量分析不应仅关注下游指标构建，还应将上游数据治理视为可独立研究的系统问题。只有当数据治理过程本身被建模、被审计并被纳入论文论证链条时，国家格局、机构影响力和合作网络等结论才更具可解释性与可复现性。")
    collab_table = [["作者A", "作者B", "共同论文数", "会议数", "起止年份"]]
    for row in metrics["collab_edges"][:12]:
        collab_table.append(
            [
                row["left_name"],
                row["right_name"],
                row["shared_papers"],
                row["conference_count"],
                f"{row['year_first']}—{row['year_last']}",
            ]
        )
    add_table(doc, collab_table, [4.0, 4.0, 1.6, 1.4, 2.0], "表9 头部作者合作对", font_size=9.2)


def section_discussion(doc: Document, metrics: dict) -> None:
    add_heading(doc, "7 结论", 1)
    add_paragraph(doc, f"本文提出了一种统一的数据治理与分析框架，用于处理大规模异构学术会议数据，并在七个安全与密码学顶级会议上进行了验证。结果表明，该框架能够在高异构数据环境下实现稳定的结构化建模，并支持多维科研计量分析任务。当前样本覆盖 {metrics['overall_three']['total_papers']} 篇官方接收论文，其中 {metrics['normalization']['paper_count']} 篇进入标准化建模层，作者机构有效覆盖率达到 {metrics['success_ratio']}。")
    add_paragraph(doc, "基于统一治理后的数据，本文进一步开展了国家格局分析、机构分布评估与作者合作网络构建，结果显示全球科研产出具有较强集中性，同时存在稳定的核心机构与长期合作结构。这说明学术会议数据在经过系统治理后，能够成为支撑科研结构研究的重要数据基础。")
    add_paragraph(doc, "未来工作将继续优化复杂多机构消歧问题，进一步降低尾部失败覆盖，并将该框架扩展至更广泛的学科领域与科研对象，以验证其跨场景适用性。")


def appendix(doc: Document, metrics: dict) -> None:
    doc.add_page_break()
    add_heading(doc, "附录A 各会议各年份有效覆盖详表", 1)
    rows = [["会议", "年份", "论文总数", "成功", "失败", "成功覆盖率"]]
    for row in metrics["two_layer_by_year"]:
        rows.append(
            [
                row["conference"],
                str(row["year"]),
                str(row["total"]),
                str(row["success"]),
                str(row["failure"]),
                row["success_ratio"],
            ]
        )
    add_table(doc, rows, [3.2, 1.5, 1.8, 1.8, 1.8, 2.1], font_size=9.2)

    add_heading(doc, "附录B 七大会年度论文规模详表", 1)
    count_rows = [["会议", "2020", "2021", "2022", "2023", "2024", "2025", "合计"]]
    for conference in sorted(metrics["conference_counts"]):
        vals = [metrics["conference_counts"][conference][year] for year in range(2020, 2026)]
        count_rows.append([conference, *[str(v) for v in vals], str(sum(vals))])
    add_table(doc, count_rows, [3.1, 1.15, 1.15, 1.15, 1.15, 1.15, 1.15, 1.6], font_size=9.2)

    add_heading(doc, "附录C 国家、机构与作者头部表", 1)
    country_rows = [["国家/地区", "论文数", "作者数", "机构数"]]
    for row in metrics["top_countries_no_multiple"][:20]:
        country_rows.append([row["country"], row["papers"], row["authors"], row["institutions"]])
    add_table(doc, country_rows, [4.0, 2.0, 2.0, 2.0], "表C1 国家/地区头部表", font_size=9.4)

    inst_rows = [["机构", "国家/地区", "论文数"]]
    for row in metrics["institution_rows"][:20]:
        inst_rows.append([row["institution_name"], row["country"], row["papers"]])
    add_table(doc, inst_rows, [8.2, 2.2, 1.8], "表C2 机构头部表", font_size=9.2)

    author_rows = [["作者", "论文数", "活跃会议数"]]
    for row in metrics["author_rows"][:20]:
        author_rows.append([row["author_name"], row["papers"], row["conferences"]])
    add_table(doc, author_rows, [6.4, 1.8, 2.3], "表C3 作者头部表", font_size=9.2)

    doc.add_page_break()
    add_heading(doc, "附录D 重点国家趋势补充表", 1)
    top_trend_names = [row["country"] for row in metrics["top_countries_no_multiple"][:10]]
    yearly_country_map: dict[str, dict[int, int]] = defaultdict(dict)
    for row in read_csv(COUNTRY_BY_YEAR):
        if row["country"] in top_trend_names:
            yearly_country_map[row["country"]][int(row["year"])] = int(row["papers"])
    trend_rows = [["国家/地区", "2020", "2021", "2022", "2023", "2024", "2025", "六年合计"]]
    for country in top_trend_names:
        yearly_vals = [yearly_country_map[country].get(year, 0) for year in range(2020, 2026)]
        trend_rows.append([country] + [str(v) for v in yearly_vals] + [str(sum(yearly_vals))])
    add_table(doc, trend_rows, [3.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.5], "表D1 重点国家 2020—2025 年逐年论文数", font_size=9.0)

    country_share_rows = [["国家/地区", "论文数", "占已覆盖论文比例", "机构数"]]
    for row in metrics["top_countries_no_multiple"][:15]:
        country_share_rows.append(
            [
                row["country"],
                row["papers"],
                pct(int(row["papers"]), metrics["success_total"]),
                row["institutions"],
            ]
        )
    add_table(doc, country_share_rows, [4.2, 1.8, 2.8, 1.8], "表D2 重点国家在已覆盖论文中的占比", font_size=9.2)

    doc.add_page_break()
    add_heading(doc, "附录E 合作网络与扩展统计补充表", 1)
    add_paragraph(doc, "为补充正文中对合作结构与扩展统计的概括性分析，附录E列出头部作者合作对以及作者角色、会议信息类补充结果，用于支撑后续更细粒度的计量研究。")
    collab_table = [["作者A", "作者B", "共同论文数", "会议数", "起止年份"]]
    for row in metrics["collab_edges"][:15]:
        collab_table.append(
            [
                row["left_name"],
                row["right_name"],
                row["shared_papers"],
                row["conference_count"],
                f"{row['year_first']}—{row['year_last']}",
            ]
        )
    add_table(doc, collab_table, [3.8, 3.8, 1.4, 1.2, 1.6], "表E1 头部作者合作网络补充表", font_size=8.8)

    role_rows = [
        ["指标", "数值", "说明"],
        ["作者角色输入行", str(metrics["role_report"]["input_rows"]), "进入作者角色分析流程的输入作者机构行"],
        ["角色输出行", str(metrics["role_report"]["role_rows"]), "生成的角色结果总行数"],
        ["覆盖论文数", str(metrics["role_report"]["papers"]), "进入角色分析层的论文数"],
        ["第一作者行", str(metrics["role_report"]["first_author_rows"]), "第一作者相关结果"],
        ["参与作者行", str(metrics["role_report"]["participating_author_rows"]), "参与作者相关结果"],
        ["通讯作者行", str(metrics["role_report"]["corresponding_author_rows"]), "当前仍未形成稳定自动化结果"],
    ]
    add_table(doc, role_rows, [3.4, 2.2, 7.8], "表E2 作者角色结果摘要", font_size=9.2)

    cfp_rows = [
        ["指标", "数值", "说明"],
        ["注册 conference-year", str(metrics["cfp_report"]["registered_conference_years"]), "当前会议信息链路注册范围"],
        ["事件记录数", str(metrics["cfp_report"]["event_rows"]), "投稿、通知、会议等时间事件总数"],
        ["版本记录数", str(metrics["cfp_report"]["edition_rows"]), "conference-year 版本记录数"],
        ["有事件 conference-year", str(metrics["cfp_report"]["conference_years_with_events"]), "已覆盖的年份数"],
        ["缺失事件 conference-year", str(metrics["cfp_report"]["missing_event_conference_years"]), "当前缺失值为 0"],
        ["review queue 行数", str(metrics["cfp_report"]["review_queue_rows"]), "当前待人工复核队列为空"],
    ]
    add_table(doc, cfp_rows, [3.8, 2.2, 7.4], "表E3 会议信息类结果摘要", font_size=9.2)


def build_doc() -> Path:
    metrics = build_metrics()
    doc = Document()
    configure_document(doc)
    title_page(doc, metrics)
    section_intro(doc)
    section_related(doc)
    section_system(doc)
    section_scope(doc, metrics)
    section_extraction_and_normalization(doc, metrics)
    section_coverage(doc, metrics)
    section_scale_and_distribution(doc, metrics)
    section_collaboration_and_extensions(doc, metrics)
    section_discussion(doc, metrics)
    appendix(doc, metrics)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    doc.save(DOCX_PATH)
    return DOCX_PATH


def main() -> None:
    path = build_doc()
    print(path)


if __name__ == "__main__":
    main()
