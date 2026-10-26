"""
从 GROBID TEI XML 文件中提取文献元数据：
- 标题、年份
- 作者（按顺序，含机构）
- 自动过滤 GROBID 提取噪声（IEEE 水印、脚注重复、机构名误识别为作者等）

输出：
- data/paper_metadata.csv  每行一个作者
"""

import argparse
import os
from pathlib import Path
import re

from author_metadata.config import DATA_DIR, build_dataset_paths, slugify_filename
from author_metadata.pipeline import (
    dataset_name_for_group,
    load_conference_strategy,
    run_pipeline,
    scan_pdf_groups,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="从论文 PDF 批量提取头部元数据（标题、作者、机构、年份、摘要）"
    )
    parser.add_argument(
        "--input-dir",
        default=str(DATA_DIR / "raw_data"),
        help=f"PDF 输入目录（默认: {DATA_DIR / 'raw_data'}），支持递归扫描子目录",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DATA_DIR),
        help=f"输出根目录（默认: {DATA_DIR}），产物写入其下的 author_metadata_dataset/",
    )
    parser.add_argument(
        "--conference",
        default="",
        help="稳定的会议标识（如 ccs、ieee_s&p、ndss、usenix_security）；默认使用输入目录名",
    )
    parser.add_argument(
        "--dataset-name",
        default="",
        help="单个 PDF 分组的显式数据集目录名；自动流水线可用 author_metadata_dataset_<year>",
    )
    parser.add_argument(
        "--year",
        default="",
        help="已知出版年份；显式传入时作为该批次的权威出版年份",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    explicit_year = args.year.strip()
    if explicit_year and not re.fullmatch(r"(?:19|20)\d{2}", explicit_year):
        raise RuntimeError("--year 必须是四位年份。")
    raw_dir = os.path.abspath(args.input_dir)
    output_dir = os.path.abspath(args.output_dir)
    conference_name = args.conference.strip() or os.path.basename(raw_dir.rstrip(os.sep))
    strategy = load_conference_strategy(conference_name)

    groups = scan_pdf_groups(raw_dir)
    if not groups:
        raise RuntimeError("未找到可处理的 PDF，已停止以避免覆盖现有输出。")
    if args.dataset_name and len(groups) != 1:
        raise RuntimeError("--dataset-name 只能用于仅包含一个 PDF 分组的输入目录。")

    print(f"发现 {sum(len(items) for items in groups.values())} 个 PDF，分属 {len(groups)} 个目录：")
    for key, pdfs in sorted(groups.items()):
        print(f"  {key}/ ({len(pdfs)} 个 PDF)")
    print()

    for group_key, pdf_list in sorted(groups.items()):
        dataset_name, label, inferred_year = dataset_name_for_group(group_key)
        year_hint = explicit_year or inferred_year
        if args.dataset_name:
            dataset_name = args.dataset_name.strip()
            if not dataset_name or Path(dataset_name).name != dataset_name:
                raise RuntimeError("--dataset-name 必须是不含路径分隔符的目录名。")
        paths = build_dataset_paths(raw_dir, output_dir, dataset_name)
        print(f"{'─' * 50}")
        print(f"▶ 处理目录: {group_key}/ → {dataset_name}/")
        print(f"{'─' * 50}")
        run_pipeline(
            pdf_list,
            paths,
            label=label,
            conference_name=conference_name,
            year_hint=year_hint,
            strategy=strategy,
            slugify_filename=slugify_filename,
            year_is_authoritative=bool(explicit_year),
        )
        print()


if __name__ == "__main__":
    main()
