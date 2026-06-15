from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


ROOT = Path("/Users/liziyu/llm_conference_skill")
REPORT_DIR = ROOT / "generated-data" / "reports"
FIGURE_DIR = REPORT_DIR / "figures"
SNAPSHOT_CSV = REPORT_DIR / "experiment_metrics" / "fullbatch_snapshot_evolution.csv"

FIG1_PATH = FIGURE_DIR / "figure1_framework.png"
FIG2_PATH = FIGURE_DIR / "figure2_workflow.png"
FIG3_PATH = FIGURE_DIR / "figure3_coverage_metrics.png"

FONT_SANS = "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/86ba2c91f017a3749571a82f2c6d890ac7ffb2fb.asset/AssetData/PingFang.ttc"
FONT_HEITI = "/Users/liziyu/Library/Fonts/黑体.ttf"


PALETTE = {
    "bg": "#FFFFFF",
    "text": "#1F2937",
    "muted": "#5B6472",
    "line": "#CBD5E1",
    "blue": "#4F86F7",
    "blue_soft": "#EAF2FF",
    "teal": "#14B8A6",
    "teal_soft": "#E8FCF8",
    "amber": "#F59E0B",
    "amber_soft": "#FFF6E5",
    "purple": "#8B5CF6",
    "purple_soft": "#F3EEFF",
    "rose": "#E85D75",
    "rose_soft": "#FFECEF",
    "slate_soft": "#F8FAFC",
}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_HEITI if bold else FONT_SANS
    return ImageFont.truetype(path, size=size)


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def new_canvas(width: int, height: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (width, height), hex_to_rgb(PALETTE["bg"]))
    draw = ImageDraw.Draw(image)
    return image, draw


def draw_centered_text(
    draw: ImageDraw.ImageDraw,
    box: tuple[float, float, float, float],
    text: str,
    size: int,
    fill: str,
    bold: bool = False,
    spacing: int = 6,
):
    x0, y0, x1, y1 = box
    fnt = font(size, bold=bold)
    bbox = draw.multiline_textbbox((0, 0), text, font=fnt, align="center", spacing=spacing)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = x0 + (x1 - x0 - tw) / 2
    ty = y0 + (y1 - y0 - th) / 2
    draw.multiline_text((tx, ty), text, font=fnt, fill=hex_to_rgb(fill), align="center", spacing=spacing)


def draw_left_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    size: int,
    fill: str,
    bold: bool = False,
    spacing: int = 4,
):
    draw.multiline_text(xy, text, font=font(size, bold=bold), fill=hex_to_rgb(fill), spacing=spacing)


def rounded_box(
    draw: ImageDraw.ImageDraw,
    box: tuple[float, float, float, float],
    fill: str,
    outline: str = "#CBD5E1",
    radius: int = 28,
    width: int = 3,
):
    draw.rounded_rectangle(box, radius=radius, fill=hex_to_rgb(fill), outline=hex_to_rgb(outline), width=width)


def arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[float, float],
    end: tuple[float, float],
    fill: str = "#94A3B8",
    width: int = 5,
    head_len: int = 20,
    head_w: int = 12,
):
    draw.line([start, end], fill=hex_to_rgb(fill), width=width)
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    angle = math.atan2(dy, dx)
    back_x = end[0] - head_len * math.cos(angle)
    back_y = end[1] - head_len * math.sin(angle)
    left = (
        back_x + head_w * math.sin(angle),
        back_y - head_w * math.cos(angle),
    )
    right = (
        back_x - head_w * math.sin(angle),
        back_y + head_w * math.cos(angle),
    )
    draw.polygon([end, left, right], fill=hex_to_rgb(fill))


def dashed_line(
    draw: ImageDraw.ImageDraw,
    start: tuple[float, float],
    end: tuple[float, float],
    fill: str = "#94A3B8",
    width: int = 3,
    dash: int = 14,
    gap: int = 10,
):
    x0, y0 = start
    x1, y1 = end
    total = math.dist(start, end)
    if total == 0:
        return
    ux = (x1 - x0) / total
    uy = (y1 - y0) / total
    pos = 0.0
    while pos < total:
        seg_end = min(pos + dash, total)
        sx = x0 + ux * pos
        sy = y0 + uy * pos
        ex = x0 + ux * seg_end
        ey = y0 + uy * seg_end
        draw.line([(sx, sy), (ex, ey)], fill=hex_to_rgb(fill), width=width)
        pos += dash + gap


def shadow_box(draw: ImageDraw.ImageDraw, box: tuple[float, float, float, float], fill: str, accent: str):
    x0, y0, x1, y1 = box
    draw.rounded_rectangle((x0 + 10, y0 + 12, x1 + 10, y1 + 12), radius=28, fill=(236, 241, 248))
    rounded_box(draw, box, fill=fill, outline=accent, radius=28, width=3)


def build_figure1() -> None:
    image, draw = new_canvas(2400, 1500)

    draw_left_text(draw, (120, 90), "图 1  基于 Skill 的顶会数据治理与分析自动化框架", 42, PALETTE["text"], bold=True)
    draw_left_text(
        draw,
        (120, 150),
        "从多源采集、标准化治理、质量增强到统计分析与结果表达的模块化组织方式",
        24,
        PALETTE["muted"],
    )

    top = (240, 260, 2160, 400)
    shadow_box(draw, top, PALETTE["purple_soft"], PALETTE["purple"])
    draw_centered_text(draw, top, "自动化编排层\n批量执行 | 任务调度 | 版本管理 | 归档与日志", 30, PALETTE["text"], bold=True)

    col_y0, col_y1 = 520, 1120
    col_w = 560
    gap = 80
    left = (160, col_y0, 160 + col_w, col_y1)
    mid = (160 + col_w + gap, col_y0, 160 + col_w * 2 + gap, col_y1)
    right = (160 + col_w * 2 + gap * 2, col_y0, 160 + col_w * 3 + gap * 2, col_y1)

    shadow_box(draw, left, PALETTE["blue_soft"], PALETTE["blue"])
    draw_centered_text(draw, (left[0], left[1] + 20, left[2], left[1] + 90), "输入与采集", 30, PALETTE["blue"], bold=True)
    sub_boxes_left = [
        ((left[0] + 36, left[1] + 120, left[2] - 36, left[1] + 240), "会议与年份配置\n七大会 2020—2025"),
        ((left[0] + 36, left[1] + 280, left[2] - 36, left[1] + 400), "多源论文获取\n官网 | OpenAlex | PDF | 历史补录"),
        ((left[0] + 36, left[1] + 440, left[2] - 36, left[1] + 560), "作者与机构提取\n作者名 | affiliation | 元数据"),
    ]
    for box, text in sub_boxes_left:
        rounded_box(draw, box, fill="#FFFFFF", outline=PALETTE["blue"])
        draw_centered_text(draw, box, text, 24, PALETTE["text"], bold=False)

    shadow_box(draw, mid, PALETTE["teal_soft"], PALETTE["teal"])
    draw_centered_text(draw, (mid[0], mid[1] + 20, mid[2], mid[1] + 90), "核心处理模块", 30, PALETTE["teal"], bold=True)
    sub_boxes_mid = [
        ((mid[0] + 36, mid[1] + 110, mid[2] - 36, mid[1] + 220), "标准化\n会议命名统一 | 机构清洗 | 字段对齐"),
        ((mid[0] + 36, mid[1] + 250, mid[2] - 36, mid[1] + 360), "质量增强\n去噪 | 国家识别 | 机构治理"),
        ((mid[0] + 36, mid[1] + 390, mid[2] - 36, mid[1] + 500), "覆盖审计\npaper-id 对齐 | 完整性判断"),
        ((mid[0] + 36, mid[1] + 530, mid[2] - 36, mid[1] + 640), "中间数据与事实表\n论文表 | 作者机构表 | 会议表"),
    ]
    for box, text in sub_boxes_mid:
        rounded_box(draw, box, fill="#FFFFFF", outline=PALETTE["teal"])
        draw_centered_text(draw, box, text, 24, PALETTE["text"])

    shadow_box(draw, right, PALETTE["amber_soft"], PALETTE["amber"])
    draw_centered_text(draw, (right[0], right[1] + 20, right[2], right[1] + 90), "分析输出模块", 30, PALETTE["amber"], bold=True)
    sub_boxes_right = [
        ((right[0] + 36, right[1] + 110, right[2] - 36, right[1] + 220), "统计分析\n国家 | 机构 | 作者 | 趋势 | 合作"),
        ((right[0] + 36, right[1] + 250, right[2] - 36, right[1] + 360), "角色与会议元数据\n第一作者 | 参与作者 | CFP"),
        ((right[0] + 36, right[1] + 390, right[2] - 36, right[1] + 500), "结果表达\n报告 | 图表 | 基准比较"),
        ((right[0] + 36, right[1] + 530, right[2] - 36, right[1] + 640), "版本化产物\n当前结果 | 底层数据 | 历史归档 | 运行日志"),
    ]
    for box, text in sub_boxes_right:
        rounded_box(draw, box, fill="#FFFFFF", outline=PALETTE["amber"])
        draw_centered_text(draw, box, text, 24, PALETTE["text"])

    arrow(draw, (left[2] + 10, 820), (mid[0] - 20, 820), fill=PALETTE["line"], width=7, head_len=24, head_w=14)
    arrow(draw, (mid[2] + 10, 820), (right[0] - 20, 820), fill=PALETTE["line"], width=7, head_len=24, head_w=14)
    arrow(draw, ((top[0] + top[2]) / 2, top[3] + 10), ((top[0] + top[2]) / 2, col_y0 - 20), fill=PALETTE["line"], width=7, head_len=24, head_w=14)

    footer = (220, 1220, 2180, 1380)
    rounded_box(draw, footer, fill=PALETTE["slate_soft"], outline=PALETTE["line"], radius=30, width=2)
    draw_centered_text(
        draw,
        footer,
        "质量增强型模块直接影响覆盖率、完整率与机构国家解析率；分析扩展型模块负责在统一事实表上生成科研分析结果。",
        25,
        PALETTE["muted"],
    )

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    image.save(FIG1_PATH, format="PNG")


def build_figure2() -> None:
    image, draw = new_canvas(2400, 1400)

    draw_left_text(draw, (120, 90), "图 2  顶会数据自动化处理流程", 42, PALETTE["text"], bold=True)
    draw_left_text(
        draw,
        (120, 150),
        "展示从论文获取到质量审计、统计输出和版本归档的主处理链路，以及发现问题后的回流修复路径",
        24,
        PALETTE["muted"],
    )

    boxes = [
        ("1 会议与年份配置", "确定会议范围\n年份范围与运行批次", PALETTE["blue"], PALETTE["blue_soft"]),
        ("2 论文与作者获取", "从官网、开放平台和 PDF 页面\n提取原始记录", PALETTE["purple"], PALETTE["purple_soft"]),
        ("3 标准化整理", "统一会议命名\n作者字段与机构文本", PALETTE["teal"], PALETTE["teal_soft"]),
        ("4 质量增强", "去噪、国家识别\n机构治理与补源回填", PALETTE["amber"], PALETTE["amber_soft"]),
        ("5 覆盖审计", "论文级完整性判断\npaper-id 对齐修复", PALETTE["rose"], PALETTE["rose_soft"]),
        ("6 分析与归档", "统计分析、图表报告生成\n版本化结果输出", PALETTE["blue"], PALETTE["blue_soft"]),
    ]

    xs = [90, 460, 830, 1200, 1570, 1940]
    y = 420
    w = 300
    h = 220
    for idx, (title, body, accent, fill) in enumerate(boxes):
        box = (xs[idx], y, xs[idx] + w, y + h)
        shadow_box(draw, box, fill, accent)
        draw_centered_text(draw, (box[0] + 18, box[1] + 18, box[2] - 18, box[1] + 88), title, 25, accent, bold=True)
        draw_centered_text(draw, (box[0] + 22, box[1] + 96, box[2] - 22, box[3] - 18), body, 21, PALETTE["text"])
        if idx < len(boxes) - 1:
            arrow(draw, (box[2] + 14, y + h / 2), (xs[idx + 1] - 18, y + h / 2), fill="#94A3B8", width=6, head_len=20, head_w=12)

    note_box = (430, 780, 1970, 980)
    rounded_box(draw, note_box, fill=PALETTE["slate_soft"], outline=PALETTE["line"], radius=28, width=2)
    draw_centered_text(
        draw,
        note_box,
        "审计发现缺失、错配或未知机构后，系统不会直接放大统计口径，\n而是回流至补源、规则治理和机构库修正阶段，再重新进入标准化与覆盖审计。",
        25,
        PALETTE["muted"],
        spacing=8,
    )

    dashed_line(draw, (1720, 640), (1720, 760), fill="#94A3B8", width=4)
    dashed_line(draw, (1720, 760), (980, 760), fill="#94A3B8", width=4)
    arrow(draw, (980, 760), (980, 650), fill="#94A3B8", width=4, head_len=18, head_w=10)

    label = (800, 1080, 1600, 1260)
    rounded_box(draw, label, fill="#FFFFFF", outline=PALETTE["line"], radius=24, width=2)
    draw_centered_text(draw, label, "主链路输出\n论文表 | 作者机构表 | 会议元数据表 | 对比报告", 26, PALETTE["text"], bold=False)

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    image.save(FIG2_PATH, format="PNG")


def read_snapshot_rows() -> list[dict[str, str]]:
    with SNAPSHOT_CSV.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_figure3() -> None:
    rows = read_snapshot_rows()
    labels = ["早期快照 1", "早期快照 2", "当前快照"]
    author_counts = [int(r["papers_with_author_rows"]) for r in rows]
    aff_counts = [int(r["papers_with_full_affiliation_coverage"]) for r in rows]
    complete_counts = [int(r["papers_complete_unverified"]) for r in rows]
    any_rates = [float(r["paper_any_author_row_rate"]) for r in rows]
    full_rates = [float(r["paper_full_affiliation_coverage_rate"]) for r in rows]
    complete_rates = [float(r["paper_complete_unverified_rate"]) for r in rows]

    image, draw = new_canvas(2400, 1600)
    draw_left_text(draw, (120, 90), "图 3  不同版本快照下论文级覆盖审计指标变化", 42, PALETTE["text"], bold=True)
    draw_left_text(
        draw,
        (120, 150),
        "上半部分展示论文数量变化，下半部分展示对应覆盖率变化。可以看出当前快照主要提升来自覆盖审计与对齐修复。",
        24,
        PALETTE["muted"],
    )

    panel1 = (120, 260, 2280, 860)
    panel2 = (120, 930, 2280, 1480)
    rounded_box(draw, panel1, fill="#FFFFFF", outline=PALETTE["line"], radius=26, width=2)
    rounded_box(draw, panel2, fill="#FFFFFF", outline=PALETTE["line"], radius=26, width=2)
    draw_left_text(draw, (170, 290), "（a）论文数对比", 28, PALETTE["text"], bold=True)
    draw_left_text(draw, (170, 960), "（b）覆盖率对比", 28, PALETTE["text"], bold=True)

    # legends
    legend_items = [
        (PALETTE["blue"], "有作者行论文数"),
        (PALETTE["teal"], "完整 affiliation 覆盖论文数"),
        (PALETTE["rose"], "完整论文数"),
    ]
    lx = 1480
    for color, text in legend_items:
        draw.rounded_rectangle((lx, 292, lx + 34, 326), radius=6, fill=hex_to_rgb(color))
        draw_left_text(draw, (lx + 48, 289), text, 22, PALETTE["muted"])
        lx += 300

    legend2 = [
        (PALETTE["blue"], "作者信息获取率"),
        (PALETTE["teal"], "完整 affiliation 覆盖率"),
        (PALETTE["rose"], "论文完整率"),
    ]
    lx = 1410
    for color, text in legend2:
        draw.line((lx, 976, lx + 38, 976), fill=hex_to_rgb(color), width=6)
        draw.ellipse((lx + 12, 962, lx + 26, 976), fill=hex_to_rgb(color))
        draw_left_text(draw, (lx + 48, 958), text, 22, PALETTE["muted"])
        lx += 290

    # panel 1 axes and bars
    axis_x0, axis_y0, axis_x1, axis_y1 = 240, 380, 2200, 780
    draw.line((axis_x0, axis_y0, axis_x0, axis_y1), fill=hex_to_rgb(PALETTE["line"]), width=3)
    draw.line((axis_x0, axis_y1, axis_x1, axis_y1), fill=hex_to_rgb(PALETTE["line"]), width=3)
    max_count = 7600
    ticks = [0, 2000, 4000, 6000, 7600]
    for tick in ticks:
        y = axis_y1 - (tick / max_count) * (axis_y1 - axis_y0)
        draw.line((axis_x0 - 8, y, axis_x1, y), fill=hex_to_rgb("#EEF2F7"), width=2)
        draw_left_text(draw, (150, y - 12), f"{tick}", 20, PALETTE["muted"])

    centers = [620, 1220, 1820]
    bar_w = 90
    offsets = [-120, 0, 120]
    series = [
        (author_counts, PALETTE["blue"]),
        (aff_counts, PALETTE["teal"]),
        (complete_counts, PALETTE["rose"]),
    ]
    for cx, label in zip(centers, labels):
        draw_left_text(draw, (cx - 70, 796), label, 22, PALETTE["text"], bold=True)
    for values, color in series:
        for cx, off, value in zip(centers, offsets * 0 + offsets, values):
            pass
    for si, (values, color) in enumerate(series):
        off = offsets[si]
        for cx, value in zip(centers, values):
            x0 = cx + off - bar_w / 2
            x1 = cx + off + bar_w / 2
            y = axis_y1 - (value / max_count) * (axis_y1 - axis_y0)
            rounded_box(draw, (x0, y, x1, axis_y1), fill=color, outline=color, radius=18, width=1)
            draw_centered_text(draw, (x0 - 20, y - 44, x1 + 20, y - 4), str(value), 20, PALETTE["text"], bold=True)

    # panel 2 axes and lines
    axis2_x0, axis2_y0, axis2_x1, axis2_y1 = 240, 1030, 2200, 1390
    draw.line((axis2_x0, axis2_y0, axis2_x0, axis2_y1), fill=hex_to_rgb(PALETTE["line"]), width=3)
    draw.line((axis2_x0, axis2_y1, axis2_x1, axis2_y1), fill=hex_to_rgb(PALETTE["line"]), width=3)
    rate_ticks = [0.70, 0.75, 0.80, 0.85, 1.00]
    min_rate = 0.68
    max_rate = 1.0
    for tick in rate_ticks:
        y = axis2_y1 - ((tick - min_rate) / (max_rate - min_rate)) * (axis2_y1 - axis2_y0)
        draw.line((axis2_x0 - 8, y, axis2_x1, y), fill=hex_to_rgb("#EEF2F7"), width=2)
        draw_left_text(draw, (148, y - 12), f"{tick*100:.0f}%", 20, PALETTE["muted"])
    for cx, label in zip(centers, labels):
        draw_left_text(draw, (cx - 70, 1408), label, 22, PALETTE["text"], bold=True)

    def rate_to_xy(values: Iterable[float]) -> list[tuple[float, float]]:
        points = []
        for cx, rate in zip(centers, values):
            y = axis2_y1 - ((rate - min_rate) / (max_rate - min_rate)) * (axis2_y1 - axis2_y0)
            points.append((cx, y))
        return points

    line_series = [
        (rate_to_xy(any_rates), PALETTE["blue"]),
        (rate_to_xy(full_rates), PALETTE["teal"]),
        (rate_to_xy(complete_rates), PALETTE["rose"]),
    ]
    for points, color in line_series:
        draw.line(points, fill=hex_to_rgb(color), width=6)
        for (x, y), rate in zip(points, [p for p in (any_rates if color == PALETTE["blue"] else full_rates if color == PALETTE["teal"] else complete_rates)]):
            draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill=hex_to_rgb(color))
            draw_centered_text(draw, (x - 52, y - 52, x + 52, y - 20), f"{rate*100:.2f}%", 18, PALETTE["text"], bold=True)

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    image.save(FIG3_PATH, format="PNG")


def main() -> None:
    build_figure1()
    build_figure2()
    build_figure3()
    print(FIG1_PATH)
    print(FIG2_PATH)
    print(FIG3_PATH)


if __name__ == "__main__":
    main()
