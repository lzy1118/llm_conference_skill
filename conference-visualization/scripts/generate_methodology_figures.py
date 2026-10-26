from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path("/Users/liziyu/llm_conference_skill")
OUT_DIR = ROOT / "generated-data" / "visualizations" / "current_showcase"

CN_FONT = "/System/Library/Fonts/STHeiti Medium.ttc"
EN_FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
EN_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

BLUE = (46, 116, 181)
DARK = (36, 52, 71)
MID = (91, 107, 122)
EDGE = (170, 183, 196)
LIGHT = (238, 243, 248)
LIGHTER = (247, 250, 253)
WHITE = (255, 255, 255)


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=size)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, use_font) -> str:
    lines = []
    for paragraph in text.split("\n"):
        buf = ""
        for ch in paragraph:
            test = buf + ch
            if draw.textbbox((0, 0), test, font=use_font)[2] <= max_width:
                buf = test
            else:
                if buf:
                    lines.append(buf)
                buf = ch
        lines.append(buf)
    return "\n".join(lines)


def centered_text(draw, box, text, use_font, fill, spacing=8):
    x1, y1, x2, y2 = box
    bbox = draw.multiline_textbbox((0, 0), text, font=use_font, spacing=spacing, align="center")
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = x1 + (x2 - x1 - tw) / 2
    y = y1 + (y2 - y1 - th) / 2
    draw.multiline_text((x, y), text, font=use_font, fill=fill, spacing=spacing, align="center")


def round_box(draw, box, title, body, fill_color, title_font, body_font, title_fill=DARK):
    draw.rounded_rectangle(box, radius=20, fill=fill_color, outline=EDGE, width=3)
    x1, y1, x2, y2 = box
    centered_text(draw, (x1 + 16, y1 + 18, x2 - 16, y1 + 88), title, title_font, title_fill, spacing=6)
    centered_text(draw, (x1 + 18, y1 + 88, x2 - 18, y2 - 18), body, body_font, MID, spacing=8)


def arrow(draw, start, end, fill=EDGE, width=4, head=16):
    draw.line([start, end], fill=fill, width=width)
    x1, y1 = start
    x2, y2 = end
    if abs(x2 - x1) >= abs(y2 - y1):
        if x2 >= x1:
            pts = [(x2, y2), (x2 - head, y2 - head // 2), (x2 - head, y2 + head // 2)]
        else:
            pts = [(x2, y2), (x2 + head, y2 - head // 2), (x2 + head, y2 + head // 2)]
    else:
        if y2 >= y1:
            pts = [(x2, y2), (x2 - head // 2, y2 - head), (x2 + head // 2, y2 - head)]
        else:
            pts = [(x2, y2), (x2 - head // 2, y2 + head), (x2 + head // 2, y2 + head)]
    draw.polygon(pts, fill=fill)


def canvas(title_cn: str, title_en: str, size=(3000, 1600)):
    image = Image.new("RGB", size, WHITE)
    draw = ImageDraw.Draw(image)
    title_font = font(EN_BOLD, 76)
    subtitle_font = font(EN_FONT, 34)
    title_cn_font = font(CN_FONT, 48)
    centered_text(draw, (100, 70, size[0] - 100, 180), title_cn, title_cn_font, DARK, spacing=4)
    centered_text(draw, (100, 175, size[0] - 100, 245), title_en, subtitle_font, BLUE, spacing=4)
    return image, draw


def draw_framework_evolution():
    image, draw = canvas(
        "从局部数据处理到统一治理框架的方法收敛过程",
        "Methodological convergence from fragmented handling to a unified governance framework",
    )
    title_font = font(CN_FONT, 40)
    body_font = font(CN_FONT, 28)

    boxes = [
        ((170, 540, 710, 1000), "阶段一\n局部整理", "面向单一会议或单一年份\n进行数据收集与人工修补", LIGHTER),
        ((850, 540, 1390, 1000), "阶段二\n问题暴露", "来源差异、机构歧义与\n统计漂移反复出现", (248, 251, 254)),
        ((1530, 540, 2070, 1000), "阶段三\n统一建模", "将论文、作者、机构与国家\n压缩到统一关系结构", LIGHT),
        ((2210, 540, 2750, 1000), "阶段四\n稳定分析", "在覆盖审计约束下形成\n可复现的跨会议分析结果", (233, 242, 251)),
    ]
    for box, title, body, fill_color in boxes:
        round_box(draw, box, title, body, fill_color, title_font, body_font)

    for i in range(3):
        arrow(draw, (boxes[i][0][2] + 20, 770), (boxes[i + 1][0][0] - 20, 770), fill=EDGE, width=6, head=24)

    note_title = font(CN_FONT, 34)
    note_body = font(CN_FONT, 24)
    notes = [
        ((330, 1130, 910, 1420), "驱动因素", "多源异构数据、历史页面差异、\n作者机构多重表达"),
        ((1210, 1130, 1790, 1420), "核心抽象", "统一数据模型 + 实体解析策略 +\n覆盖率评估机制"),
        ((2090, 1130, 2670, 1420), "输出能力", "国家、机构、作者、合作网络\n与时间趋势分析"),
    ]
    for box, title, body in notes:
        round_box(draw, box, title, body, (250, 252, 254), note_title, note_body)

    arrow(draw, (620, 1130), (440, 1015), fill=EDGE, width=5, head=20)
    arrow(draw, (1500, 1130), (1800, 1015), fill=EDGE, width=5, head=20)
    arrow(draw, (2380, 1130), (2480, 1015), fill=EDGE, width=5, head=20)

    path = OUT_DIR / "第三章_框架收敛过程图.png"
    image.save(path, quality=95)


def draw_result_pipeline():
    image, draw = canvas(
        "实验结果的生成链路与可信性来源",
        "How heterogeneous evidence is transformed into auditable analytical results",
    )
    title_font = font(CN_FONT, 38)
    body_font = font(CN_FONT, 26)

    upper_boxes = [
        ((130, 510, 670, 900), "多源原始材料", "会议页面\n开放学术数据库\n历史归档与文献页面", LIGHTER),
        ((810, 510, 1350, 900), "信息收集与对齐", "论文清单承接\n作者字段汇聚\n机构证据补强", LIGHT),
        ((1490, 510, 2030, 900), "实体解析与标准化", "作者—机构关系构建\n机构归并\n国家映射校正", LIGHT),
        ((2170, 510, 2710, 900), "覆盖审计与收口", "成功/失败分层\n问题记录回流\n统计口径统一", (233, 242, 251)),
    ]
    for box, title, body, fill_color in upper_boxes:
        round_box(draw, box, title, body, fill_color, title_font, body_font)

    for i in range(3):
        arrow(draw, (upper_boxes[i][0][2] + 20, 705), (upper_boxes[i + 1][0][0] - 20, 705), fill=EDGE, width=6, head=24)

    lower_title = font(CN_FONT, 32)
    lower_body = font(CN_FONT, 23)
    lower_boxes = [
        ((400, 1110, 940, 1370), "可信性来源一", "多源交叉验证\n缓解单一来源缺失与异常"),
        ((1230, 1110, 1770, 1370), "可信性来源二", "统一实体模型\n保证跨会议比较尺度一致"),
        ((2060, 1110, 2600, 1370), "可信性来源三", "覆盖率与审计边界\n明确结果适用范围"),
    ]
    for box, title, body in lower_boxes:
        round_box(draw, box, title, body, (250, 252, 254), lower_title, lower_body)

    arrow(draw, (1080, 905), (670, 1110), fill=EDGE, width=5, head=20)
    arrow(draw, (1760, 905), (1500, 1110), fill=EDGE, width=5, head=20)
    arrow(draw, (2440, 905), (2330, 1110), fill=EDGE, width=5, head=20)

    side_box = (2730, 510, 2920, 1370)
    round_box(
        draw,
        side_box,
        "分析输出",
        "国家格局\n机构分布\n作者合作\n年度趋势",
        (245, 249, 253),
        font(CN_FONT, 34),
        font(CN_FONT, 24),
        title_fill=BLUE,
    )
    arrow(draw, (2710, 705), (2730, 705), fill=EDGE, width=6, head=22)

    path = OUT_DIR / "第三章_结果生成链路图.png"
    image.save(path, quality=95)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    draw_framework_evolution()
    draw_result_pipeline()


if __name__ == "__main__":
    main()
