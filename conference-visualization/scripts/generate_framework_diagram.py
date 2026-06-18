from __future__ import annotations

import argparse
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont


CANVAS_W = 1800
CANVAS_H = 980
BG = "#FFFFFF"
TEXT = "#222222"
SUBTEXT = "#666666"
BORDER = "#2E2E2E"
BLUE = "#8E97A3"
GREEN = "#A3ABB4"
RED = "#7E8792"
ORANGE = "#969EA8"
GRAY = "#EEF2F6"
LIGHT = "#F8F8F8"
DASH = "#8C8C8C"
PALE_BLUE = "#F3F4F6"
PALE_GREEN = "#F5F5F5"
PALE_ORANGE = "#F1F2F4"


FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """加载本地可用的中文字体，必要时回退到 PIL 默认字体。"""
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


FONT_TITLE = load_font(28)
FONT_GROUP = load_font(24)
FONT_BOX = load_font(24)
FONT_BODY = load_font(19)
FONT_FOOTER = load_font(18)
FONT_SMALL = load_font(19)
FONT_BOX_SMALL = load_font(22)
FONT_BODY_SMALL = load_font(17)

ORIGINAL_TITLE_TEXT = "顶会数据治理与科研分析的技能化自动化工作流框架"
ORIGINAL_LEFT_GROUP_LABEL = "技能化工作流核心"
ORIGINAL_RIGHT_GROUP_LABEL = "学术证据与解析增强层"

ORIGINAL_CORE_BOXES = [
    (
        (800, 130, 1290, 255),
        BLUE,
        "多源论文与作者机构抽取",
        ["论文清单汇聚", "元数据、DOI 与全文证据补充", "作者机构线索缓存与整合"],
        None,
        FONT_BOX,
        FONT_BODY,
        7,
    ),
    (
        (800, 300, 1290, 425),
        GREEN,
        "数据清洗与标准化",
        ["抽取噪声清洗", "机构别名归并与机构库映射", "标准化论文事实与作者机构事实"],
        None,
        FONT_BOX,
        FONT_BODY,
        7,
    ),
    (
        (800, 470, 1290, 625),
        ORANGE,
        "统计分析与质量治理",
        ["国家、机构、作者、趋势与合作分析", "覆盖率审计与异常定位", "缺口清单生成与回填修正"],
        None,
        FONT_BOX,
        FONT_BODY,
        7,
    ),
    (
        (800, 675, 1290, 800),
        RED,
        "报告与论文图生成",
        ["汇总表、分析报告与论文配图", "图表数据表与附录材料", "统一成果输出"],
        None,
        FONT_BOX,
        FONT_BODY,
        7,
    ),
]

ORIGINAL_RIGHT_BOXES = [
    (
        (1415, 140, 1715, 250),
        PALE_BLUE,
        "结构化学术元数据",
        ["DBLP、IACR、会议官网", "IEEE Xplore、DOI 页面"],
        None,
        FONT_BOX_SMALL,
        FONT_BODY_SMALL,
        6,
    ),
    (
        (1415, 322, 1715, 442),
        PALE_GREEN,
        "作者机构补强证据",
        ["OpenAlex 与", "Semantic Scholar", "网页首部信息与 PDF 首页"],
        None,
        FONT_BOX_SMALL,
        FONT_BODY_SMALL,
        5,
    ),
    (
        (1415, 504, 1715, 624),
        PALE_ORANGE,
        "解析执行与缓存复用",
        ["页面解析与浏览器自动化", "缓存复用与结果回填"],
        None,
        FONT_BOX_SMALL,
        FONT_BODY_SMALL,
        6,
    ),
    (
        (1415, 676, 1715, 796),
        LIGHT,
        "统一产物出口",
        ["抽取、标准化与分析结果", "报告与可视化结果"],
        None,
        FONT_BOX_SMALL,
        FONT_BODY_SMALL,
        6,
    ),
]

PLAN_B_TITLE_TEXT = ""
PLAN_B_LEFT_GROUP_LABEL = "技能化治理与分析核心"
PLAN_B_RIGHT_GROUP_LABEL = "辅助证据与校正支撑层"

PLAN_B_CORE_BOXES = [
    (
        (800, 120, 1290, 245),
        BLUE,
        "顶会数据获取与结构化抽取",
        ["会议清单、论文元数据与作者线索汇聚", "官网、DBLP、DOI 与全文证据接入", "形成可重跑的抽取底稿"],
        None,
        FONT_BOX,
        FONT_BODY,
        7,
    ),
    (
        (800, 285, 1290, 430),
        GREEN,
        "标准化治理与机构归并",
        ["机构库映射、别名归并与母体机构收口", "组合机构拆分、噪声清洗与国家补全", "作者-机构事实与论文事实统一落表"],
        None,
        FONT_BOX,
        FONT_BODY,
        7,
    ),
    (
        (800, 470, 1290, 635),
        ORANGE,
        "作者机构校正与质量闭环",
        ["shared bundle 重分配与历史回填", "Unknown / 残片 / 异常对齐问题定位", "规则修正后全量重刷与覆盖率校验"],
        None,
        FONT_BOX,
        FONT_BODY,
        7,
    ),
    (
        (800, 680, 1290, 815),
        RED,
        "统计分析与成果输出",
        ["国家、机构、作者与合作关系统计", "第一机构 / 参与机构双口径分析", "图表、表格、报告与论文配图生成"],
        None,
        FONT_BOX,
        FONT_BODY,
        7,
    ),
]

PLAN_B_RIGHT_BOXES = [
    (
        (1415, 130, 1715, 240),
        PALE_BLUE,
        "会议与论文证据",
        ["官网 accepted / program 页面", "DBLP、IACR、DOI 与 PDF"],
        None,
        FONT_BOX_SMALL,
        FONT_BODY_SMALL,
        6,
    ),
    (
        (1415, 312, 1715, 432),
        PALE_GREEN,
        "作者机构补全证据",
        ["OpenAlex、Semantic Scholar", "页面首部与首页机构信息"],
        None,
        FONT_BOX_SMALL,
        FONT_BODY_SMALL,
        6,
    ),
    (
        (1415, 504, 1715, 624),
        PALE_ORANGE,
        "缓存与规则复用",
        ["affiliation cache 与历史修正复用", "机构库、手写规则与回填记录"],
        None,
        FONT_BOX_SMALL,
        FONT_BODY_SMALL,
        6,
    ),
    (
        (1415, 696, 1715, 806),
        LIGHT,
        "正式产物层",
        ["抽取结果、归一化数据、分析表", "论文图表与展示结果"],
        None,
        FONT_BOX_SMALL,
        FONT_BODY_SMALL,
        6,
    ),
]


# Keep both layouts in one script so the published "original" figure stays stable
# while we can iterate on alternate paper-facing versions such as plan_b.
VARIANTS = {
    "original": {
        "title": ORIGINAL_TITLE_TEXT,
        "left_group_label": ORIGINAL_LEFT_GROUP_LABEL,
        "right_group_label": ORIGINAL_RIGHT_GROUP_LABEL,
        "core_boxes": ORIGINAL_CORE_BOXES,
        "right_boxes": ORIGINAL_RIGHT_BOXES,
        "quality_box": ((95, 730, 430, 820), "质量校验与人工复核", ["覆盖率、缺口、异常结果检查"]),
        "final_box": ((120, 870, 315, 940), "最终成果发布", []),
        "feedback_label": "未通过则回填重跑",
        "right_labels": ["证据接入", "证据补强", "解析支撑", None],
    },
    "plan_b": {
        "title": PLAN_B_TITLE_TEXT,
        "left_group_label": PLAN_B_LEFT_GROUP_LABEL,
        "right_group_label": PLAN_B_RIGHT_GROUP_LABEL,
        "core_boxes": PLAN_B_CORE_BOXES,
        "right_boxes": PLAN_B_RIGHT_BOXES,
        "quality_box": ((95, 735, 430, 835), "异常识别与人工复核", ["缺口、歧义与规则失配统一收口"]),
        "final_box": ((120, 875, 345, 950), "正式数据与论文产物发布", []),
        "feedback_label": "异常回流至治理环节",
        "right_labels": ["证据接入", "补全校核", "规则复用", None],
    },
}


def rr(draw: ImageDraw.ImageDraw, xy: tuple[int, int, int, int], fill: str, outline: str = BORDER, width: int = 2, radius: int = 18):
    """绘制框架图中使用的圆角矩形模块。"""
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def dashed_rect(draw: ImageDraw.ImageDraw, xy: tuple[int, int, int, int], dash: int = 12, gap: int = 8, width: int = 2, outline: str = DASH):
    """绘制高层分组区域使用的虚线边框。"""
    x1, y1, x2, y2 = xy
    for x in range(x1, x2, dash + gap):
        draw.line((x, y1, min(x + dash, x2), y1), fill=outline, width=width)
        draw.line((x, y2, min(x + dash, x2), y2), fill=outline, width=width)
    for y in range(y1, y2, dash + gap):
        draw.line((x1, y, x1, min(y + dash, y2)), fill=outline, width=width)
        draw.line((x2, y, x2, min(y + dash, y2)), fill=outline, width=width)


def centered_text(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], lines: list[tuple[str, ImageFont.ImageFont, str]], line_gap: int = 8, x_padding: int = 16):
    """在图中模块内居中排布多行文本。"""
    x1, y1, x2, y2 = box
    heights = []
    for text, font, _ in lines:
        bbox = draw.textbbox((0, 0), text, font=font)
        heights.append(bbox[3] - bbox[1])
    total_h = sum(heights) + line_gap * (len(lines) - 1)
    cy = y1 + (y2 - y1 - total_h) / 2
    for (text, font, fill), h in zip(lines, heights):
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        available = max((x2 - x1) - 2 * x_padding, 10)
        tx = x1 + x_padding + max((available - tw) / 2, 0)
        draw.text((tx, cy), text, font=font, fill=fill)
        cy += h + line_gap


def arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], fill: str = BORDER, width: int = 3):
    """绘制两个流程阶段之间的实线方向连接。"""
    x1, y1 = start
    x2, y2 = end
    draw.line((x1, y1, x2, y2), fill=fill, width=width)
    if abs(x2 - x1) >= abs(y2 - y1):
        sign = 1 if x2 >= x1 else -1
        pts = [(x2, y2), (x2 - 16 * sign, y2 - 8), (x2 - 16 * sign, y2 + 8)]
    else:
        sign = 1 if y2 >= y1 else -1
        pts = [(x2, y2), (x2 - 8, y2 - 16 * sign), (x2 + 8, y2 - 16 * sign)]
    draw.polygon(pts, fill=fill)


def dashed_arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], fill: str = DASH, width: int = 2, dash: int = 10, gap: int = 7):
    """绘制辅助证据关系使用的虚线连接。"""
    x1, y1 = start
    x2, y2 = end
    if y1 == y2:
        step = dash + gap
        sign = 1 if x2 >= x1 else -1
        for x in range(x1, x2, sign * step):
            nx = x + sign * dash
            draw.line((x, y1, nx, y2), fill=fill, width=width)
    elif x1 == x2:
        step = dash + gap
        sign = 1 if y2 >= y1 else -1
        for y in range(y1, y2, sign * step):
            ny = y + sign * dash
            draw.line((x1, y, x2, ny), fill=fill, width=width)
    else:
        draw.line((x1, y1, x2, y2), fill=fill, width=width)
    arrow(draw, (x2 - (18 if x2 >= x1 else -18), y2), (x2, y2), fill=fill, width=width)


def box_svg(x1: int, y1: int, x2: int, y2: int, fill: str, title: str, body: list[str], footer: str | None = None, stroke: str = BORDER, text_fill: str = TEXT, footer_fill: str = SUBTEXT, title_size: int = 24, body_size: int = 19) -> str:
    """构造单个框架模块的 SVG 片段。"""
    parts = [
        f'<rect x="{x1}" y="{y1}" width="{x2-x1}" height="{y2-y1}" rx="18" ry="18" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
    ]
    cy = y1 + 26
    parts.append(f'<text x="{(x1+x2)/2}" y="{cy}" font-size="{title_size}" text-anchor="middle" fill="{text_fill}" font-weight="600">{escape(title)}</text>')
    cy += 34
    for line in body:
        parts.append(f'<text x="{(x1+x2)/2}" y="{cy}" font-size="{body_size}" text-anchor="middle" fill="{text_fill}">{escape(line)}</text>')
        cy += 28
    if footer:
        parts.append(f'<text x="{(x1+x2)/2}" y="{y2-18}" font-size="17" text-anchor="middle" fill="{footer_fill}">{escape(footer)}</text>')
    return "\n".join(parts)


def dashed_group_svg(x1: int, y1: int, x2: int, y2: int, label: str) -> str:
    """构造带标签虚线分组框的 SVG 片段。"""
    return "\n".join(
        [
            f'<rect x="{x1}" y="{y1}" width="{x2-x1}" height="{y2-y1}" fill="none" stroke="{DASH}" stroke-width="2" stroke-dasharray="10,8"/>',
            f'<text x="{(x1+x2)/2}" y="{y1-10}" font-size="24" text-anchor="middle" fill="{TEXT}" font-weight="600">{escape(label)}</text>',
        ]
    )


def line_svg(start: tuple[int, int], end: tuple[int, int], dashed: bool = False, label: str | None = None) -> str:
    """构造可选虚线样式与标签的直线 SVG 连接。"""
    x1, y1 = start
    x2, y2 = end
    style = 'stroke-dasharray="10,8"' if dashed else ""
    head = "arrowHeadDashed" if dashed else "arrowHead"
    label_svg = ""
    if label:
        label_svg = f'<text x="{(x1+x2)/2}" y="{(y1+y2)/2 - 8}" font-size="18" text-anchor="middle" fill="{SUBTEXT}">{escape(label)}</text>'
    return "\n".join(
        [
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{DASH if dashed else BORDER}" stroke-width="{2 if dashed else 3}" {style} marker-end="url(#{head})"/>',
            label_svg,
        ]
    )


def draw_png(output_png: Path, variant: str) -> None:
    """将选定版本的框架图栅格化输出为 PNG。"""
    cfg = VARIANTS[variant]
    title_text = cfg["title"]
    left_group_label = cfg["left_group_label"]
    right_group_label = cfg["right_group_label"]
    core_boxes = cfg["core_boxes"]
    right_boxes = cfg["right_boxes"]
    quality_box = cfg["quality_box"]
    final_box = cfg["final_box"]
    feedback_label = cfg["feedback_label"]
    right_labels = cfg["right_labels"]

    img = Image.new("RGB", (CANVAS_W, CANVAS_H), BG)
    draw = ImageDraw.Draw(img)

    if title_text:
        bbox = draw.textbbox((0, 0), title_text, font=FONT_TITLE)
        tw = bbox[2] - bbox[0]
        draw.text(((CANVAS_W - tw) / 2, 20), title_text, font=FONT_TITLE, fill=TEXT)

    rr(draw, (40, 165, 190, 235), "#FFFFFF")
    centered_text(draw, (40, 165, 190, 235), [("用户输入", FONT_BOX, TEXT)])

    rr(draw, (230, 155, 470, 245), "#FFFFFF")
    centered_text(draw, (230, 155, 470, 245), [("任务理解与流程编排", FONT_BOX, TEXT), ("拆解分析目标与执行顺序", FONT_SMALL, SUBTEXT)])

    rr(draw, (515, 140, 720, 260), "#F7F9FC")
    centered_text(draw, (515, 140, 720, 260), [("自动化治理中枢", FONT_BOX, TEXT), ("任务调度 / 重跑 / 回填", FONT_SMALL, SUBTEXT), ("校验 / 版本整理", FONT_SMALL, SUBTEXT)])

    dashed_rect(draw, (760, 100, 1330, 840))
    draw.text((930, 76), left_group_label, font=FONT_GROUP, fill=TEXT)

    dashed_rect(draw, (1390, 100, 1735, 840))
    draw.text((1452, 76), right_group_label, font=FONT_GROUP, fill=TEXT)

    # A small downward shift keeps the dashed group labels visually separated
    # from the top row of boxes in both variants.
    shifted_core_boxes = [((x1, y1 + 10, x2, y2 + 10), color, title, body, footer, title_font, body_font, gap) for (x1, y1, x2, y2), color, title, body, footer, title_font, body_font, gap in core_boxes]
    shifted_right_boxes = [((x1, y1 + 10, x2, y2 + 10), fill, title, body, footer, title_font, body_font, gap) for (x1, y1, x2, y2), fill, title, body, footer, title_font, body_font, gap in right_boxes]

    for box, color, title, body, footer, title_font, body_font, gap in shifted_core_boxes:
        rr(draw, box, fill=color)
        lines = [(title, title_font, "#FFFFFF"), *[(line, body_font, "#FFFFFF") for line in body]]
        if footer:
            lines.append((footer, FONT_FOOTER, "#EAF1F8"))
        centered_text(draw, box, lines, line_gap=gap, x_padding=18)

    for box, fill, title, body, footer, title_font, body_font, gap in shifted_right_boxes:
        rr(draw, box, fill=fill)
        centered_text(draw, box, [(title, title_font, TEXT), *[(line, body_font, TEXT) for line in body]], line_gap=gap, x_padding=20)

    quality_xy, quality_title, quality_body = quality_box
    rr(draw, quality_xy, "#FFFFFF")
    centered_text(draw, quality_xy, [(quality_title, FONT_BOX, TEXT), *[(line, FONT_SMALL, SUBTEXT) for line in quality_body]])

    final_xy, final_title, final_body = final_box
    rr(draw, final_xy, "#FFFFFF")
    centered_text(draw, final_xy, [(final_title, FONT_BOX, TEXT), *[(line, FONT_SMALL, SUBTEXT) for line in final_body]])

    arrow(draw, (190, 200), (230, 200))
    arrow(draw, (470, 200), (515, 200))
    arrow(draw, (720, 200), (800, 210))
    arrow(draw, (1045, 265), (1045, 310))
    arrow(draw, (1045, 435), (1045, 480))
    arrow(draw, (1045, 635), (1045, 685))
    arrow(draw, (1290, 200), (1415, 200))
    arrow(draw, (1290, 382), (1415, 382))
    arrow(draw, (1290, 564), (1415, 564))
    arrow(draw, (1290, 745), (1415, 745))
    arrow(draw, (800, 755), (430, 785))
    arrow(draw, (220, quality_xy[3]), (220, final_xy[1]))
    dashed_arrow(draw, (430, 775), (800, 380))
    label_positions = [(1322, 192), (1322, 389), (1322, 571)]
    for (x, y), label in zip(label_positions, right_labels[:3]):
        if label:
            draw.text((x, y), label, font=FONT_SMALL, fill=SUBTEXT)
    draw.text((575, 535), feedback_label, font=FONT_SMALL, fill=SUBTEXT)

    img.save(output_png)


def build_svg(variant: str) -> str:
    """组装选定版本的 SVG 框架图内容。"""
    cfg = VARIANTS[variant]
    title_text = cfg["title"]
    left_group_label = cfg["left_group_label"]
    right_group_label = cfg["right_group_label"]
    core_boxes = cfg["core_boxes"]
    right_boxes = cfg["right_boxes"]
    quality_box = cfg["quality_box"]
    final_box = cfg["final_box"]
    feedback_label = cfg["feedback_label"]
    right_labels = cfg["right_labels"]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" viewBox="0 0 {CANVAS_W} {CANVAS_H}">',
        "<defs>",
        f'<marker id="arrowHead" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto"><path d="M0,0 L12,6 L0,12 z" fill="{BORDER}"/></marker>',
        f'<marker id="arrowHeadDashed" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto"><path d="M0,0 L12,6 L0,12 z" fill="{DASH}"/></marker>',
        "</defs>",
        f'<rect width="{CANVAS_W}" height="{CANVAS_H}" fill="{BG}"/>',
        dashed_group_svg(760, 100, 1330, 840, left_group_label),
        dashed_group_svg(1390, 100, 1735, 840, right_group_label),
        box_svg(40, 165, 190, 235, "#FFFFFF", "用户输入", []),
        box_svg(230, 155, 470, 245, "#FFFFFF", "任务理解与流程编排", ["拆解分析目标与执行顺序"]),
        box_svg(515, 140, 720, 260, "#F7F9FC", "自动化治理中枢", ["任务调度 / 重跑 / 回填", "校验 / 版本整理"]),
    ]
    if title_text:
        title_x = CANVAS_W / 2
        parts.insert(
            5,
            f'<text x="{title_x}" y="46" font-size="28" text-anchor="middle" fill="{TEXT}" font-weight="700">{escape(title_text)}</text>',
        )
    shifted_core_boxes = [((x1, y1 + 10, x2, y2 + 10), color, title, body, footer, title_font, body_font, gap) for (x1, y1, x2, y2), color, title, body, footer, title_font, body_font, gap in core_boxes]
    shifted_right_boxes = [((x1, y1 + 10, x2, y2 + 10), fill, title, body, footer, title_font, body_font, gap) for (x1, y1, x2, y2), fill, title, body, footer, title_font, body_font, gap in right_boxes]
    for box, color, title, body, footer, title_font, body_font, gap in shifted_core_boxes:
        parts.append(box_svg(*box, fill=color, title=title, body=body, footer=footer, stroke=BORDER, text_fill="#FFFFFF", footer_fill="#EAF1F8", title_size=24, body_size=19))
    for box, fill, title, body, footer, title_font, body_font, gap in shifted_right_boxes:
        parts.append(box_svg(*box, fill=fill, title=title, body=body, footer=footer, stroke=BORDER, title_size=22, body_size=17))
    quality_xy, quality_title, quality_body = quality_box
    final_xy, final_title, final_body = final_box
    parts.extend(
        [
            box_svg(*quality_xy, "#FFFFFF", quality_title, quality_body),
            box_svg(*final_xy, "#FFFFFF", final_title, final_body),
            line_svg((190, 200), (230, 200)),
            line_svg((470, 200), (515, 200)),
            line_svg((720, 200), (800, 210)),
            line_svg((1045, 265), (1045, 310)),
            line_svg((1045, 435), (1045, 480)),
            line_svg((1045, 635), (1045, 685)),
            line_svg((1290, 200), (1415, 200), label=right_labels[0]),
            line_svg((1290, 382), (1415, 382), label=right_labels[1]),
            line_svg((1290, 564), (1415, 564), label=right_labels[2]),
            line_svg((1290, 745), (1415, 745)),
            line_svg((800, 755), (430, 785)),
            line_svg((220, quality_xy[3]), (220, final_xy[1])),
            f'<line x1="430" y1="775" x2="800" y2="380" stroke="{DASH}" stroke-width="2" stroke-dasharray="10,8" marker-end="url(#arrowHeadDashed)"/>',
            f'<text x="610" y="535" font-size="18" text-anchor="middle" fill="{SUBTEXT}">{escape(feedback_label)}</text>',
        ]
    )
    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    """按指定布局版本生成 SVG 和 PNG 两种框架图。"""
    parser = argparse.ArgumentParser(description="Generate a paper-style framework diagram for the skills workflow.")
    parser.add_argument("--output-dir", required=True, help="Directory to place SVG and PNG outputs")
    parser.add_argument("--basename", default="技能化自动化工作流_框架图", help="Output file basename")
    parser.add_argument("--variant", choices=sorted(VARIANTS.keys()), default="original", help="Diagram variant")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    svg_path = output_dir / f"{args.basename}.svg"
    png_path = output_dir / f"{args.basename}.png"

    svg_path.write_text(build_svg(args.variant), encoding="utf-8")
    draw_png(png_path, args.variant)


if __name__ == "__main__":
    main()
