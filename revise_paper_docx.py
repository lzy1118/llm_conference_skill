from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from docx.text.paragraph import Paragraph


SRC = Path("/Users/liziyu/Desktop/论文/基于Skill的学术会议论文元数据处理研究v3.docx")
DST = Path("/Users/liziyu/Desktop/论文/基于Skill的学术会议论文元数据处理研究v4.docx")
BODY_EAST_ASIA = "SimSun"
DISPLAY_EAST_ASIA = "SimHei"


def para_text(p: Paragraph) -> str:
    return p.text.replace("\n", " ").strip()


def find_para(doc: Document, exact: str | None = None, starts: str | None = None) -> Paragraph:
    for p in doc.paragraphs:
        text = para_text(p)
        if exact is not None and text == exact:
            return p
        if starts is not None and text.startswith(starts):
            return p
    raise KeyError(exact or starts)


def clear_para(p: Paragraph) -> None:
    for child in list(p._p):
        if child.tag != qn("w:pPr"):
            p._p.remove(child)


def clear_field_artifacts(p: Paragraph) -> None:
    """Remove stale MathType/Word field runs left in the title template."""
    for child in list(p._p):
        if child.tag == qn("w:pPr"):
            continue
        if child.xpath(".//w:fldChar | .//w:instrText"):
            p._p.remove(child)


def set_rfonts(rpr, font_name: str, east_asia: str) -> None:
    rfonts = rpr.rFonts
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    rfonts.set(qn("w:ascii"), font_name)
    rfonts.set(qn("w:hAnsi"), font_name)
    rfonts.set(qn("w:cs"), font_name)
    rfonts.set(qn("w:eastAsia"), east_asia)
    rfonts.set(qn("w:hint"), "eastAsia")


def set_fonts(
    run,
    font_name: str = "Times New Roman",
    east_asia: str = BODY_EAST_ASIA,
    size: float = 10.5,
) -> None:
    run.font.name = font_name
    run.font.size = Pt(size)
    rpr = run._element.get_or_add_rPr()
    set_rfonts(rpr, font_name, east_asia)


def set_para(p: Paragraph, text: str, style: str | None = None, *, bold: bool = False,
             align=None, font_size: float = 10.5, font: str = "Times New Roman",
             east_asia: str = BODY_EAST_ASIA) -> Paragraph:
    clear_para(p)
    if style is not None:
        p.style = style
    if align is not None:
        p.alignment = align
    run = p.add_run(text)
    run.bold = bold
    set_fonts(run, font, east_asia, font_size)
    return p


def new_para_after(doc: Document, ref: Paragraph, text: str = "", style: str = "摘要",
                   *, font_size: float = 10.5, font: str = "Times New Roman",
                   east_asia: str = BODY_EAST_ASIA, bold: bool = False) -> Paragraph:
    p = doc.add_paragraph(style=style)
    set_para(p, text, style, bold=bold, font_size=font_size, font=font, east_asia=east_asia)
    ref._p.addnext(p._p)
    return p


def remove_num_level(p: Paragraph, level: int) -> None:
    ppr = p._p.get_or_add_pPr()
    numpr = ppr.find(qn("w:numPr"))
    if numpr is None:
        numpr = OxmlElement("w:numPr")
        ppr.insert(0, numpr)
    ilvl = numpr.find(qn("w:ilvl"))
    if ilvl is None:
        ilvl = OxmlElement("w:ilvl")
        numpr.insert(0, ilvl)
    ilvl.set(qn("w:val"), str(level))


def take_range(body, start_el, end_el):
    children = list(body)
    start = children.index(start_el)
    end = children.index(end_el)
    items = children[start:end]
    for item in items:
        body.remove(item)
    return items


def paragraph_with_drawing(doc: Document, after: Paragraph) -> Paragraph:
    body = doc.element.body
    children = list(body)
    start = children.index(after._p)
    for el in children[start + 1 :]:
        if el.tag == qn("w:p") and el.xpath(".//w:drawing"):
            return Paragraph(el, after._parent)
        if el.tag == qn("w:p") and para_text(Paragraph(el, after._parent)).startswith("数据采集Skill是"):
            break
    raise RuntimeError("data collection figure paragraph not found")


def find_table_with_text(doc: Document, needle: str):
    for t in doc.tables:
        if needle in t.cell(0, 0).text:
            return t
    raise KeyError(needle)


def set_table_text(table, values):
    for row, row_values in zip(table.rows, values):
        for cell, value in zip(row.cells, row_values):
            cell.text = value
            for p in cell.paragraphs:
                for run in p.runs:
                    set_fonts(run, "Times New Roman", BODY_EAST_ASIA, 9.5)


def contains_cjk(text: str) -> bool:
    return any(
        "\u3400" <= ch <= "\u9fff" or "\uf900" <= ch <= "\ufaff"
        for ch in text
    )


def style_uses_display_font(style_name: str) -> bool:
    name = style_name.lower()
    return any(
        marker in name
        for marker in ("heading", "title", "caption", "标题", "题注", "图题")
    )


def force_cjk_fonts(doc: Document) -> None:
    """Write explicit CJK families so Word and LibreOffice render identically."""
    display_style_ids = set()
    for style in doc.styles:
        east_asia = DISPLAY_EAST_ASIA if style_uses_display_font(style.name) else BODY_EAST_ASIA
        if style_uses_display_font(style.name):
            display_style_ids.add(style.style_id)
        rpr = style._element.get_or_add_rPr()
        set_rfonts(rpr, "Times New Roman", east_asia)

    roots = [doc.element]
    for section in doc.sections:
        for part in (
            section.header,
            section.first_page_header,
            section.even_page_header,
            section.footer,
            section.first_page_footer,
            section.even_page_footer,
        ):
            if part._element not in roots:
                roots.append(part._element)

    for root in roots:
        for run_el in root.xpath(".//w:r"):
            text = "".join(run_el.xpath(".//w:t/text()"))
            if not contains_cjk(text):
                continue
            paragraph_el = run_el.getparent()
            while paragraph_el is not None and paragraph_el.tag != qn("w:p"):
                paragraph_el = paragraph_el.getparent()
            style_id = ""
            if paragraph_el is not None:
                pstyle = paragraph_el.find("./w:pPr/w:pStyle", paragraph_el.nsmap)
                if pstyle is not None:
                    style_id = pstyle.get(qn("w:val"), "")
            east_asia = DISPLAY_EAST_ASIA if style_id in display_style_ids else BODY_EAST_ASIA
            rpr = run_el.find(qn("w:rPr"))
            if rpr is None:
                rpr = OxmlElement("w:rPr")
                run_el.insert(0, rpr)
            set_rfonts(rpr, "Times New Roman", east_asia)


def keep_layout_pairs(doc: Document) -> None:
    for p in doc.paragraphs:
        if p.style and style_uses_display_font(p.style.name):
            p.paragraph_format.keep_together = True
            style_name = p.style.name.lower()
            is_caption = any(marker in style_name for marker in ("caption", "题注", "图题"))
            p.paragraph_format.keep_with_next = not is_caption
        if p._p.xpath(".//w:drawing"):
            p.paragraph_format.keep_with_next = True


def prevent_row_split(row) -> None:
    trpr = row._tr.get_or_add_trPr()
    if trpr.find(qn("w:cantSplit")) is None:
        trpr.append(OxmlElement("w:cantSplit"))


def repeat_table_header(row) -> None:
    trpr = row._tr.get_or_add_trPr()
    header = trpr.find(qn("w:tblHeader"))
    if header is None:
        header = OxmlElement("w:tblHeader")
        trpr.append(header)
    header.set(qn("w:val"), "1")


def scale_inline_drawing(p: Paragraph, factor: float) -> None:
    for extent in p._p.xpath(".//wp:extent | .//a:xfrm/a:ext"):
        for attr in ("cx", "cy"):
            value = extent.get(attr)
            if value is not None:
                extent.set(attr, str(round(int(value) * factor)))


def main() -> None:
    doc = Document(str(SRC))

    # Capture anchors before adding or moving any blocks.
    p_intro_plan = find_para(doc, starts="本文其余部分安排如下")
    p_title = doc.paragraphs[0]
    p_method_intro = find_para(doc, starts="本章介绍基于Skill")
    p_arch = find_para(doc, exact="总体架构")
    p_skill_design = find_para(doc, exact="Skill模块设计")
    p_skill_overview = find_para(doc, starts="本文按照会议论文元数据处理阶段")
    p_equation = find_para(doc, starts="设第 个Skill表示为")
    eq_index = next(i for i, p in enumerate(doc.paragraphs) if p._p is p_equation._p)
    p_equation_blank = doc.paragraphs[eq_index + 1]
    p_skill_link = find_para(doc, starts="其中，表示输入数据")
    p_skill_table_intro = find_para(doc, starts="结合图1中的处理阶段")
    p_skill_table_caption = find_para(doc, starts="表1")
    p_skill_handoff = find_para(doc, starts="各Skill通过阶段性数据结果")

    p_collect_h = find_para(doc, exact="数据采集Skill")
    p_collect = find_para(doc, starts="数据采集Skill是")
    p_collect_modules = find_para(doc, starts="数据采集Skill主要包括")
    p_collect_source = find_para(doc, starts="会议来源发现模块")
    p_collect_list = find_para(doc, starts="论文列表获取模块")
    p_collect_pdf = find_para(doc, starts="PDF 下载与整理模块")
    p_collect_cfp = find_para(doc, starts="CFP 元数据采集模块")
    p_collect_handoff = find_para(doc, starts="在采集流程中，协调流水线")

    p_parse_h = find_para(doc, exact="信息解析Skill")
    p_parse = find_para(doc, starts="信息解析 Skill 负责")
    p_parse_modules = find_para(doc, starts="信息解析 Skill 主要由")
    p_parse_raw = find_para(doc, starts="原始论文数据解析模块")
    p_parse_pdf = find_para(doc, starts="PDF/TEI 元数据抽取模块")
    p_parse_layout = find_para(doc, starts="由于不同会议的论文首页结构差异")
    p_parse_clean = find_para(doc, starts="论文元数据清洗模块")
    p_parse_role = find_para(doc, starts="作者角色事实抽取模块")
    p_parse_output = find_para(doc, starts="信息解析 Skill 的输出包括")

    p_aff_h = find_para(doc, exact="机构规范化Skill")
    p_aff = find_para(doc, starts="机构规范化 Skill 负责")
    p_aff_input = find_para(doc, starts="该 Skill 以信息解析阶段")
    p_aff_prepare = find_para(doc, starts="机构规范化采用分阶段处理策略")
    p_aff_main = find_para(doc, starts="第二阶段为 AffilGood")
    p_aff_fill = find_para(doc, starts="第三阶段为参考表补全")
    p_aff_country = find_para(doc, starts="机构规范化过程中需要区分")
    p_aff_quality = find_para(doc, starts="该 Skill 的质量控制包括")

    p_metric_h = find_para(doc, exact="计量分析Skill")
    p_metric = find_para(doc, starts="计量分析 Skill 负责")
    p_metric_input = find_para(doc, starts="计量分析 Skill 的统一输入")
    p_metric_country = find_para(doc, starts="国家统计模块")
    p_metric_inst = find_para(doc, starts="作者统计模块")
    p_metric_trend = find_para(doc, starts="趋势分析模块")
    p_metric_collab = find_para(doc, starts="合作分析模块")
    p_metric_benchmark = find_para(doc, starts="基准比较模块")
    p_metric_quality = find_para(doc, starts="质量审计模块")
    p_metric_viz = find_para(doc, starts="可视化模块")
    p_metric_close = find_para(doc, starts="因此，计量分析 Skill")

    p_stats_h = find_para(doc, exact="统计口径")
    p_exp = find_para(doc, exact="实验设置")
    p_application = find_para(doc, exact="应用分析")
    p_exp_process = find_para(doc, exact="实验过程")
    p_scope = find_para(doc, exact="研究范围")
    p_scope_table_caption = find_para(doc, starts="表2  各年度各会议论文数")
    p_pdf_h = find_para(doc, exact="PDF获取")
    p_meta_h = find_para(doc, exact="元数据提取")
    p_aff_method_h = find_para(doc, exact="机构规范化")
    p_aff_llm = find_para(doc, starts="对于最高得分低于0.50")

    # Chapter-level framing and the generic-conference boundary.
    set_para(
        p_title,
        "基于Skill的学术会议论文\n元数据自动化处理方法研究",
        "Heading 1",
        font_size=18,
        font="Times New Roman",
        east_asia=DISPLAY_EAST_ASIA,
    )
    clear_field_artifacts(p_title)
    set_para(
        p_intro_plan,
        "本文其余部分安排如下：第2章介绍论文数据抽取、作者机构规范化和学术数据处理自动化等相关研究；第3章说明总体架构、SKILL.md统一契约、四类Skill设计以及三项执行方法；第4章给出案例范围和数据集规模；第5章基于标准化数据开展应用分析；第6章总结全文。",
    )
    set_para(
        p_method_intro,
        "本章介绍面向所有学术会议论文的元数据处理框架。框架以可插拔的来源、版式和机构规则适配器承接不同出版环境，核心链路包括论文数据采集、信息解析、作者—机构关系识别、机构名称规范化和标准化数据生成。本章先说明总体架构和SKILL.md设计，再给出数据采集、元数据解析与机构规范化的执行方法。",
    )
    set_para(
        p_arch,
        "总体架构",
        "Heading 3",
        font_size=10.5,
        font="Times New Roman",
        east_asia=DISPLAY_EAST_ASIA,
    )
    set_para(
        p_skill_overview,
        "为使Skill能够被智能体按同一规则调用，本文将本节定义为SKILL.md设计与统一契约。每个Skill由SKILL.md、scripts和references组成：SKILL.md声明任务范围、触发条件、输入输出、阶段顺序、降级策略和质量门；scripts实现可执行步骤；references保存版式规则、会议入口、机构别名、字段模式和统计指标。会议名称只作为运行参数，案例配置可以插拔，不构成通用Skill的支持边界。",
    )
    set_para(
        p_skill_design,
        "SKILL.md设计与统一契约",
        "Heading 3",
        font_size=10.5,
        font="Times New Roman",
        east_asia=DISPLAY_EAST_ASIA,
    )
    set_para(p_equation, "可将第 k 个 Skill 抽象为 S_k = <T_k, I_k, A_k, R_k, O_k, G_k, M_k>。")
    set_para(
        p_equation_blank,
        "其中，T_k表示触发语义与任务边界，I_k表示输入字段和来源证据，A_k表示有先后关系的处理阶段，R_k表示脚本、词典和参考资源，O_k表示结构化输出，G_k表示质量门，M_k表示统计指标及其计数语义。",
    )
    set_para(
        p_skill_link,
        "相邻Skill通过稳定文件契约交接，而不是依赖输出行序或隐式状态。前一Skill的输出满足后一Skill的输入条件时形成顺序衔接；输入、规则或脚本发生变化时，只重跑受影响阶段，并在manifest中记录运行参数、输入哈希、输出路径和失败状态。",
    )
    set_para(
        p_skill_table_intro,
        "结合图1的处理阶段，公共链路设置表1所示四类Skill。每类Skill的SKILL.md都同时声明数据对象、证据保留方式、质量门和下游统计接口。",
    )
    set_para(p_skill_table_caption, "表1  Skill类型及阶段交接")
    set_para(
        p_skill_handoff,
        "数据采集阶段形成来源清单、论文清单和已审核PDF；信息解析阶段形成论文、作者、作者角色及原始机构事实；机构规范化阶段形成完整富化事实、机构维表和展示表；计量分析阶段只读取通过质量门的标准化事实，并输出可复现的统计、审计、报告和可视化产物。",
    )
    set_table_text(
        doc.tables[0],
        [
            ("Skill类型", "公共输入/阶段", "输出与下游交接"),
            ("数据采集Skill", "会议/年份/来源，或已审核PDF目录", "source_manifest、paper_manifest、accepted PDF"),
            ("信息解析Skill", "accepted PDF、JSON/API记录、GROBID TEI", "论文元数据、作者事实、角色事实、证据与复核队列"),
            ("机构规范化Skill", "作者—机构明细和原始affiliation", "富化事实、institution_dim、15列展示表"),
            ("计量分析Skill", "author_affiliation_facts、机构维表、角色和年份", "统计摘要、合作边、审计、报告和可视化"),
        ],
    )

    # Make the four existing 3.2.x titles real Heading 4 paragraphs.
    for p, title in [
        (p_collect_h, "数据采集 Skill"),
        (p_parse_h, "信息解析 Skill"),
        (p_aff_h, "机构规范化 Skill"),
        (p_metric_h, "计量分析 Skill"),
    ]:
        set_para(p, title, "Heading 4", font_size=10.5, font="Times New Roman", east_asia=DISPLAY_EAST_ASIA)

    set_para(
        p_collect,
        "数据采集Skill是论文元数据流程的通用入口，负责来源发现、论文清单构建、PDF获取、清洗审查和可选的CFP事件采集。它面向所有会议论文数据集；当前已运行的ASIACRYPT、CRYPTO、EUROCRYPT、IEEE S&P、CCS、NDSS和USENIX Security只是验证案例，不是白名单，也不限定后续输入。",
    )
    set_para(
        p_collect_modules,
        "输入契约包括conference、year或year range、来源参数、输出目录和运行选项；当会议没有专用入口时，也可以直接输入经过审核的PDF目录。SKILL.md将数据采集拆为来源发现、论文列表、PDF下载与整理、CFP事件四个模块，并将来源状态和复核队列作为一等输出，执行契约示意见图2。",
    )
    set_para(
        p_collect_source,
        "来源发现遵循“Registry → Resolver → Unified Source Record → Spider Backend”结构。注册表维护会议别名、年份、来源类型和解析后端；解析器返回conference、year、source、backend、url和status等统一字段；source_manifest.csv采用追加并去重语义，记录paper_count和validation_status。DBLP、PMLR、NeurIPS等解析器以及IEEE/ACM浏览器会话均是可替换适配器。",
    )
    set_para(
        p_collect_list,
        "论文列表模块按会议和年份获取题名、作者、链接、DOI等外部标识，初步排除workshop、poster、tutorial、proceedings和前言等非目标内容；多卷论文集在全部卷册完成后按官方顺序合并。任何来源字段冲突都保留原始值和诊断，不在采集阶段判断作者角色或机构身份。",
    )
    set_para(
        p_collect_pdf,
        "PDF整理模块先小范围试运行并遵守访问频率，再执行可恢复下载、文件头/类型/大小检查和SHA-256去重。题名匹配只用于生成候选，分数较低的记录进入人工复核；清洗阶段输出accepted、review、excluded和failed状态。只有经过审核的accepted PDF及其paper_manifest才可交给GROBID。",
    )
    set_para(
        p_collect_cfp,
        "CFP模块与accepted-paper数据分开建模，保存投稿截止、rebuttal、录用通知、终稿和举办日期的原始文本、规范化日期、来源URL、置信度和复核状态。日期冲突不直接覆盖，形成独立复核队列。",
    )
    set_para(
        p_collect_handoff,
        "采集Skill的质量门是来源入口可访问、目标论文数可解释、PDF文件有效、题名匹配和哈希去重完成、人工复核状态已记录，并且manifest能够重建本批次。其统计接口只生成论文规模和覆盖指标：N_p表示通过accepted门的去重论文数，N_r表示待复核记录数；N_r>0或存在下载错误时，流程不得进入最终统计。",
    )

    set_para(
        p_parse,
        "信息解析Skill将原始JSON/API记录、accepted PDF和GROBID header TEI转换为可计算的论文、作者、机构原始署名和作者角色事实。其职责是保留证据并恢复关系，不是用启发式猜测机构或国家。",
    )
    set_para(
        p_parse_modules,
        "SKILL.md将该Skill组织为原始论文数据解析、PDF/TEI元数据抽取、元数据清洗和作者角色事实抽取四个模块；每个模块均保留输入文件、输出文件、候选字段和复核原因。",
    )
    set_para(
        p_parse_raw,
        "原始论文数据解析模块统一生成paper_metadata.csv，提取题名、作者、作者顺序、年份、会议、DOI和原始机构文本。字段缺失保留为空值和异常状态，不在解析阶段擅自补充国家或机构。",
    )
    set_para(
        p_parse_pdf,
        "PDF/TEI抽取模块以GROBID header为初始结构，同时读取PDF前两页的文本、坐标、字号和链接上下文，生成题名、作者、机构、邮箱、摘要、关键词、ORCID及角色候选。GROBID、pdfplumber和pypdf的证据按字段合并，原始TEI和PDF证据始终保留。",
    )
    set_para(
        p_parse_layout,
        "通用解析器先完成标题、作者、机构、邮箱和角色版式分类，再由会议策略处理编号、符号脚注、连续机构块、IEEE水印、共同一作和跨页补充。会议策略是可插拔配置，不能替代通用证据；网页端仅在唯一匹配时补充PDF缺失字段，不能覆盖非空PDF值。",
    )
    set_para(
        p_parse_clean,
        "清洗模块遵循“先审计、后修复”，以单篇论文为修复单位检查作者顺序、重复作者、邮箱错位、机构碎片、虚假作者和角色标记异常。无法确定唯一归属的候选不自动合并，修复前后记录论文键、行数和决策。",
    )
    set_para(
        p_parse_role,
        "作者角色模块独立生成paper_author_roles.csv，至少保留第一作者和参与作者事实，并为通讯作者、共同一作和equal contribution保留显式字段。缺少可靠证据时保留false和needs_review=true，等待PDF frontmatter、HTML或其他正式来源复核。",
    )
    set_para(
        p_parse_output,
        "输出包括paper_metadata.csv、作者明细、TEI XML、PDF证据、候选字段、修复记录和review_queue.csv，并以paper_key、author_order和原始affiliation交接给机构规范化Skill。解析统计只反映事实覆盖，不直接生成机构排行榜：设A_p为论文p的去重作者集合，则author_coverage = |{p: A_p ≠ ∅}| / N_p；解析错误、无作者论文或未决关系必须进入质量门报告。",
    )

    set_para(
        p_aff,
        "机构规范化Skill把作者署名中的原始affiliation转换为可比较、可统计且可追溯的机构事实。它面向任意会议的作者—机构明细，保留主体机构、下属单位、地点、语言、置信度、ROR和审核证据，不能用机构字符串相似度替代实体身份判断。",
    )
    set_para(
        p_aff_input,
        "输入至少包含稳定record_id、paper_id、author、author_rank、affiliation_rank和原始affiliations，并尽量保留DOI、年份和来源。原始affiliation及原始输入行不可被替换；规范名称、ROR、国家和城市都是新增富化字段。",
    )
    set_para(
        p_aff_prepare,
        "处理顺序固定为：先保留稳定标识并提取明确的终端国家/城市证据，再生成完整、组成项、连续组成项和括号别名候选；prepare-only阶段不得查询institution_raw.csv，也不能由城市单独反推国家。院系、学院、实验室和研究中心保存在affiliation_subunits中，不能自动成为主体机构。",
    )
    set_para(
        p_aff_main,
        "随后运行AffilGood/ROR主识别。AffilGood负责机构主体、组织层级、地点、语言和置信度，ROR作为主要实体标识；结果按record_id合并回原始行。多个组织成分只有在身份和国家能够可靠对齐时才拆成分析事实，未对齐成分保留为残片并排除排名。",
    )
    set_para(
        p_aff_fill,
        "主识别完成后，经过审核的institution_raw.csv、别名、拼写修正和范围规则只用于补充空的规范名称、ROR、国家或城市字段，不能覆盖已有的AffilGood/ROR非空值。短缩写需要国家上下文，模糊匹配、邮箱域名、城市或本地ID不能单独制造跨数据集身份。",
    )
    set_para(
        p_aff_country,
        "国家字段优先复制affilgood_location_country，展示表不得从旧country列或原始文本再次猜测。设P为通过质量门的论文集合，I_p为论文p中可靠且去重的机构键集合，C_p为已确定国家集合，则机构和国家参与论文数分别为 N_i = |{p ∈ P | i ∈ I_p}|，N_c = |{p ∈ P | c ∈ C_p}|。同一论文内同一实体只计一次，多机构或多国家可以分别计入，因此实体参与数之和可以超过N_p。",
    )
    set_para(
        p_aff_quality,
        "该Skill输出完整作者—机构—国家事实表、institution_dim.csv、机构匹配报告和固定15列展示表；每条输入必须保留ok、skipped或error状态。显式无机构记录可标记为not_applicable_noninstitutional，未识别组织保留unknown_organization，不能伪造ROR。发布和机构统计前要求error、未决reference review和可处理的blank_country_actionable均为零；skipped记录必须计数并报告。机构统计使用institution_key，显示名只用于结果呈现。",
    )

    set_para(
        p_metric,
        "计量分析Skill位于标准化事实之后，负责按明确范围生成国家、机构、作者、趋势和合作分析，并编排质量审计、基准比较、报告和可视化。它不修改论文、作者或机构事实，所有结果都可以回溯到本次运行的输入快照。",
    )
    set_para(
        p_metric_input,
        "统一输入优先为author_affiliation_facts.csv，可结合institution_dim.csv、paper_author_roles.csv和会议年份。分析开始前必须在manifest中写明会议过滤、年份过滤、国家切片、趋势实体、合作模式和启用的能力集合；标准化事实表是所有下游统计的唯一共享输入。",
    )
    set_para(
        p_metric_country,
        "国家统计按每篇论文中每个可靠国家最多计一次，输出papers、authors、institutions、paper_share、author_share和avg_authors_per_paper；国家复合标签先按可靠身份拆分，无法对齐的残片不计入。",
    )
    set_para(
        p_metric_inst,
        "机构统计以institution_key为分组键，至少输出去重论文数papers、作者—论文记录数authors、first_author_papers、conferences和years_active，并保留paper_key明细以支持排名回溯。作者统计另行使用author_key和author_order，不能把作者行数当作论文产出。",
    )
    set_para(
        p_metric_trend,
        "趋势统计按一个主实体维度运行，默认计算每个国家、机构或作者每年的去重论文数、同比绝对变化和相对变化，并记录首次活跃年份、最近活跃年份、活跃年份数和峰值年份。范围过滤必须先于聚合，不能从全量边表反推子区间。",
    )
    set_para(
        p_metric_collab,
        "合作分析支持author、country和institution三种模式。对每篇论文先在论文内部去重节点，再生成无序组合；设E_p = {{i,j} | i,j ∈ I_p, i ≠ j}，则总边集合E = ∪_{p∈P} E_p，边权w_ij = Σ_{p∈P} 1({i,j} ⊆ I_p)。同一机构或国家在一篇论文内重复出现不增加边权，跨年份切片必须重新从事实表聚合。",
    )
    set_para(
        p_metric_benchmark,
        "基准比较只读取已经生成的同类summary文件，一次运行不得混合国家、机构和作者；默认以papers为公共指标，输出每个实体的各切片值、最佳切片、最大值、最小值和spread。",
    )
    set_para(
        p_metric_quality,
        "质量审计是质量门而不是修复器，分别检查标准化明细和分析产物，记录缺失字段、Unknown国家、低置信度身份、显示名与实体键不一致、异常覆盖变化和缺失输出。审计阶段不静默修改事实。",
    )
    set_para(
        p_metric_viz,
        "报告和可视化只消费统计产物，不回到原始数据重复计算。报告明确列出输入范围、实际生成章节和缺失章节；图表与合作网络按本次范围重新生成边表，并在manifest中记录图表、CSV和可视化参数。无机构署名或Independent Researcher不进入机构排名和机构合作网络。",
    )
    set_para(
        p_metric_close,
        "因此，计量分析Skill的输出是可复现的summary、by_year、edge、audit、report和visualization文件，而不是脱离事实表的手工排行榜。每次运行必须保存manifest、输入和输出路径、过滤条件、执行步骤、跳过原因和失败状态；任何质量门未通过时，只能输出诊断，不得发布最终统计。",
    )

    # Add a compact, executable pseudo-code block to the Skill design section.
    code_ref = p_skill_handoff
    code_caption = new_para_after(
        doc,
        code_ref,
        "算法 1  基于SKILL.md的会议元数据Skill执行与统计交接",
        "Caption",
        font_size=10,
        font="Times New Roman",
        east_asia=DISPLAY_EAST_ASIA,
        bold=True,
    )
    code_lines = [
        "Input: task_query Q = (conference, years, pdf_dir, run_options)",
        "1  read SKILL.md; validate scope, input fields, resources, and negative boundaries",
        "2  discover sources or accept the reviewed PDF directory; write source_manifest",
        "3  run the configured extraction stage; preserve raw evidence and review states",
        "4  hand off by stable paper_key/record_id to the next Skill; never join by row order",
        "5  run the Skill quality gate; if error/review/actionable-missing > 0, emit diagnostics",
        "6  write the full fact table, manifest, summary, and optional downstream artifacts",
        "Output: accepted artifacts, quality report, and auditable analysis handoff",
    ]
    last = code_caption
    for line in code_lines:
        last = new_para_after(doc, last, line, "摘要", font_size=9.2, font="Menlo", east_asia=BODY_EAST_ASIA)
        last.paragraph_format.left_indent = Inches(0.35)
        last.paragraph_format.space_after = Pt(0)

    # Caption the existing data-collection Skill illustration.
    figure_para = paragraph_with_drawing(doc, p_collect_h)
    new_para_after(
        doc,
        figure_para,
        "图 2  数据采集Skill的SKILL.md、任务计划与执行模块契约示意",
        "Caption",
        font_size=10,
        font="Times New Roman",
        east_asia=DISPLAY_EAST_ASIA,
        bold=False,
    )

    # Remove the old standalone 3.3 statistics block and the now-empty 4.2 wrapper.
    body = doc.element.body
    take_range(body, p_stats_h._p, p_exp._p)
    body.remove(p_exp_process._p)

    # Move 4.2.1/4.2.2/4.2.3 blocks into the method chapter, before chapter 4.
    pdf_block = take_range(body, p_pdf_h._p, p_meta_h._p)
    meta_block = take_range(body, p_meta_h._p, p_aff_method_h._p)
    aff_block = take_range(body, p_aff_method_h._p, p_application._p)
    method_blocks = pdf_block + meta_block + aff_block
    insert_at = list(body).index(p_exp._p)
    for element in reversed(method_blocks):
        body.insert(insert_at, element)

    # Promote the moved methods to 3.3/3.4/3.5 headings.
    for p, title in [
        (p_pdf_h, "论文数据采集 Skill 执行设计"),
        (p_meta_h, "元数据解析与作者—机构关系重建"),
        (p_aff_method_h, "机构规范化与实体链接"),
    ]:
        set_para(p, title, "Heading 3", font_size=10.5, font="Times New Roman", east_asia=DISPLAY_EAST_ASIA)
        remove_num_level(p, 1)

    # Align moved method prose with the conference-neutral contract.
    p_pdf_first = find_para(doc, starts="为构建元数据解析所需的论文全文数据集")
    set_para(
        p_pdf_first,
        "本节落实3.2.1数据采集Skill的执行设计。论文来源可以来自IACR、Springer、ACM Digital Library、IEEE Xplore、会议官网或用户提供的审核目录；这些来源是案例适配器，不是通用流程的前置条件。采集阶段只负责形成可追溯的论文清单和accepted PDF集合，具体流程如图3所示。",
    )
    p_pdf_final = find_para(doc, starts="最终形成按会议和年份组织的PDF数据集")
    set_para(
        p_pdf_final,
        "最终形成按会议和年份组织的PDF数据集，并生成包含论文题名、来源页面、PDF地址、本地路径、匹配状态、文件哈希和复核状态的paper_manifest。该manifest是进入GROBID的质量门，未通过审核的PDF不得直接进入后续统计。",
    )
    p_meta_first = find_para(doc, starts="我们以GROBID生成的TEI结构")
    set_para(
        p_meta_first,
        "本节落实3.2.2信息解析Skill的执行设计。以GROBID生成的TEI结构为初始结果，结合PDF前两页的文本、坐标和字号，提取题名、作者、机构、邮箱、ORCID及作者角色；GROBID提供结构和顺序，版面解析用于校验和补充。",
    )
    p_layout_intro = find_para(doc, starts="版式规则集")
    set_para(
        p_layout_intro,
        "版式规则集用于生成PDF侧的作者—机构关系候选。针对署名区域的组织形式，本文设置上标编号、作者信息块、横向矩阵、纵向堆叠、分组共享、全体共享以及脚注与跨页补充七类规则，具体方法见表2。",
    )
    p_layout_table_caption = find_para(doc, starts="表3 典型署名版式")
    set_para(p_layout_table_caption, "表2  典型署名版式的作者—机构关联规则")
    p_aff_first = find_para(doc, starts="GROBID提取的机构字段通常")
    set_para(
        p_aff_first,
        "本节落实3.2.3机构规范化Skill的执行设计。GROBID提取的机构字段保留论文中的原始署名，AffilGood负责字段解析，ROR负责规范实体链接，审核机构表只在主识别后补充空字段。原始affiliation、组成项和决策证据始终保留，处理流程如图4所示。",
    )
    p_aff_figure = Paragraph(p_aff_first._p.getnext(), p_aff_first._parent)
    scale_inline_drawing(p_aff_figure, 0.70)
    p_aff_candidate = find_para(doc, starts="在本文的运行配置中，候选检索")
    set_para(
        p_aff_candidate,
        "对于未能直接唯一匹配的署名，系统在已有候选范围内执行名称、国家和城市约束下的候选检索与重排；是否启用交叉编码器或本地LLM判别由运行配置决定，阈值、模型版本和候选数写入manifest，不把某一组实验参数写成所有会议的固定规则。模型只能选择已有候选或拒绝全部候选，不能生成新的机构名称或ROR标识。",
    )
    set_para(
        p_aff_llm,
        "候选阶段保存候选集合、得分、判别来源、接受或拒绝结果及其配置版本。记录未满足当次配置的接受条件时，保留原始机构署名和未匹配状态并进入复核；模型或阈值发生变化时，只重跑受影响记录，不能覆盖已有的确定性证据和审核事实。",
    )
    p_aff_ref = find_para(doc, starts="AffilGood处理完成后，本地机构词典")
    set_para(
        p_aff_ref,
        "对于ROR中尚无对应实体但已有审核证据的机构，可以使用项目内部机构标识作为本地审计引用；该标识不是跨数据集通用ID。未决记录保留原始署名和复核状态，不因模糊字符串相似而建立链接。",
    )

    # The old layout pseudo-code is now Algorithm 2 after Algorithm 1 above.
    algorithm_table = find_table_with_text(doc, "Algorithm 1")
    algorithm_table.cell(0, 0).text = "Algorithm 2  基于版式信息的元数据提取算法"
    algorithm_table.cell(1, 0).text = "\n".join(
        [
            "输入：论文PDF P，通用版式规则R，会议profile C",
            "输出：论文元数据M，作者—机构关系A，证据与复核状态Q",
            "1  运行GROBID header解析，并提取PDF前两页的文本块、坐标和字号",
            "2  清除页眉、版权和页码噪声，定位题名、作者、机构、邮箱及脚注区域",
            "3  融合TEI与版面证据，确定题名、作者列表和作者顺序",
            "4  分类署名版式，并依次应用通用规则R与可选会议profile C",
            "5  生成作者—机构候选，保留候选来源、符号、编号和空间邻接证据",
            "6  融合机构、邮箱、ORCID及作者角色；冲突项进入复核而不强制合并",
            "7  以paper_key和author_order校验关系完整性，记录修复前后状态",
            "8  返回M、A和Q，并将原始TEI与PDF证据一并交接",
        ]
    )
    for row_index, row in enumerate(algorithm_table.rows):
        prevent_row_split(row)
        for p in row.cells[0].paragraphs:
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.0
            for run in p.runs:
                set_fonts(
                    run,
                    "Times New Roman",
                    DISPLAY_EAST_ASIA if row_index == 0 else BODY_EAST_ASIA,
                    9.2 if row_index == 0 else 8.8,
                )
                if row_index == 0:
                    run.bold = True

    # Add an explicit reference to the new figure numbering and keep examples scoped.
    for p in doc.paragraphs:
        text = para_text(p)
        if text.startswith("PDF获取流程如图2所示"):
            set_para(p, text.replace("如图2所示", "如图3所示"))
        elif text.startswith("整体过程如图3所示"):
            set_para(p, text.replace("如图3所示", "如图4所示"))
        elif text.startswith("以2020—2025 年七个安全与密码学会议"):
            set_para(
                p,
                "以2020—2025年七个安全与密码学会议为案例开展验证：ASIACRYPT、CRYPTO、EUROCRYPT、CCS、IEEE Symposium on Security and Privacy（IEEE S&P）、Network and Distributed System Security Symposium（NDSS）及USENIX Security Symposium。该案例集合用于检验公共PDF-first链路和已配置适配器，不代表系统的支持边界。表3列出各年度各案例会议论文数。",
            )

    caption_map = {
        "图 2 会议论文PDF获取与数据集构建流程": "图 3 会议论文PDF获取与数据集构建流程",
        "图 3基于AffilGood的机构规范化流程": "图 4 基于AffilGood的机构规范化流程",
        "图 4 七大会议主要参与机构分布": "图 5 案例会议主要参与机构分布",
        "图 5 七大会议主要参与国家或地区分布": "图 6 案例会议主要参与国家或地区分布",
        "图 6  CCS 2025录用论文页面及作者—机构信息的DOM定位": "图 7  CCS 2025录用论文页面及作者—机构信息的DOM定位",
    }
    for p in doc.paragraphs:
        if para_text(p) in caption_map:
            set_para(p, caption_map[para_text(p)], "Caption", font_size=10, font="Times New Roman", east_asia=DISPLAY_EAST_ASIA)

    # The DOM illustration is Figure 7 after the moved method figures.
    for p in doc.paragraphs:
        if "如图6所示" in p.text:
            set_para(p, p.text.replace("如图6所示", "如图7所示"))
        elif "表2列出各年度各案例会议论文数" in p.text:
            set_para(p, p.text.replace("表2列出", "表3列出"))
        elif "七大会议" in p.text:
            set_para(p, p.text.replace("七大会议", "七个案例会议"))

    # Keep the chapter 4 title meaningful after moving its former process section.
    set_para(p_exp, "实验设置", "Heading 2", font_size=10.5, font="Times New Roman", east_asia=DISPLAY_EAST_ASIA)
    set_para(p_scope, "研究范围", "Heading 3", font_size=10.5, font="Times New Roman", east_asia=DISPLAY_EAST_ASIA)
    set_para(p_scope_table_caption, "表3  各年度案例会议论文数")

    # Refresh conclusion language so the new chapter organization is explicit.
    p_conclusion = find_para(doc, starts="本文面向学术会议论文元数据来源分散")
    set_para(
        p_conclusion,
        "本文面向学术会议论文元数据来源分散、作者—机构关系复杂及机构名称不统一等问题，提出了一种基于Skill.md统一契约的自动化处理方法。该方法将论文数据采集、PDF信息解析、作者—机构关系识别、机构名称规范化和统计结果生成组织为连续处理流程，并通过稳定文件契约衔接各阶段。",
    )
    p_conclusion2 = find_para(doc, starts="各处理环节以Skill形式")
    set_para(
        p_conclusion2,
        "各处理环节以Skill形式组织任务边界、处理程序、规则资源、质量门和统计口径，使会议入口、版式策略、机构别名和分析范围能够按运行参数配置。本文以2020—2025年七个会议为案例，共处理7079篇论文，形成35680条作者—机构关系记录，并据此完成论文规模、机构参与、国家分布和合作网络分析。案例结果用于验证公共链路，不将七个会议误作系统支持范围。",
    )

    # Keep headings, visuals, captions, and the 3.5 opening paragraph together.
    for p in doc.paragraphs:
        if p.text.startswith("算法 1"):
            p.paragraph_format.keep_with_next = True
    p_aff_method_h.paragraph_format.keep_with_next = True
    p_aff_method_h.paragraph_format.keep_together = True
    p_aff_first.paragraph_format.keep_together = True
    keep_layout_pairs(doc)
    for p in (p_skill_table_caption, p_layout_table_caption, p_scope_table_caption):
        p.paragraph_format.keep_with_next = True
    for table in doc.tables:
        if table.rows:
            repeat_table_header(table.rows[0])
        for row in table.rows:
            prevent_row_split(row)
    force_cjk_fonts(doc)

    doc.save(str(DST))
    print(DST)


if __name__ == "__main__":
    main()
