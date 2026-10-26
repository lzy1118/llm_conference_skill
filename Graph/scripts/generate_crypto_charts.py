#!/usr/bin/env python3
"""三大密码会数据分析图生成脚本"""

import argparse
import csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
from collections import defaultdict

# 设置中文字体
matplotlib.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

# 历史案例数据默认保留在 Graph/data，图表统一输出至当前可视化目录。
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / 'Graph' / 'data'
GRAPH_DIR = ROOT / 'generated-data' / 'visualizations'

def load_paper_counts(filename: str) -> dict:
    """加载论文数量统计"""
    counts = defaultdict(lambda: defaultdict(int))
    filepath = DATA_DIR / filename
    
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            conf = row['conference']
            year = int(row['year'])
            count = int(row['paper_count'])
            counts[conf][year] = count
    
    return counts

def load_author_data(filename: str) -> dict:
    """加载作者数据并统计论文数（按唯一论文去重）"""
    papers = defaultdict(lambda: defaultdict(set))
    filepath = DATA_DIR / filename
    
    # 会议名称标准化映射
    conf_mapping = {
        'CRYPTO': 'CRYPTO',
        'Eurocrypt': 'EUROCRYPT',
        'EUROCRYPT': 'EUROCRYPT',
        'ASIACRYPT': 'ASIACRYPT',
        'USENIX_SECURITY': 'USENIX_SECURITY',
        'NDSS': 'NDSS',
        'IEEE_S&P': 'IEEE_S&P',
        'CCS': 'CCS'
    }
    
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            year = int(row['year'])
            article_tag = row['article_tag']
            # 提取会议名称并标准化
            conf_raw = article_tag.split('-')[0]
            conf = conf_mapping.get(conf_raw, conf_raw)
            papers[conf][year].add(article_tag)
    
    # 转换为计数
    counts = defaultdict(lambda: defaultdict(int))
    for conf in papers:
        for year in papers[conf]:
            counts[conf][year] = len(papers[conf][year])
    
    return counts

def get_total_by_year(counts: dict) -> dict:
    """按年份汇总"""
    totals = defaultdict(int)
    for conf in counts:
        for year in counts[conf]:
            totals[year] += counts[conf][year]
    return totals

def plot_bar_chart(global_data: dict, china_data: dict, us_data: dict):
    """生成整合柱状图，显示三大会议的具体数量"""
    years = list(range(2020, 2026))
    conferences = ['CRYPTO', 'EUROCRYPT', 'ASIACRYPT']
    
    # 学术配色方案 - Nature/Science 期刊风格
    conf_colors = {
        'CRYPTO': '#2166AC',      # 深蓝色
        'EUROCRYPT': '#B2182B',   # 深红色
        'ASIACRYPT': '#4DAF4A'    # 深绿色
    }
    
    # 准备数据
    global_by_conf = {}
    china_by_conf = {}
    us_by_conf = {}
    
    for conf in conferences:
        global_by_conf[conf] = [global_data.get(conf, {}).get(y, 0) for y in years]
        china_by_conf[conf] = [china_data.get(conf, {}).get(y, 0) for y in years]
        us_by_conf[conf] = [us_data.get(conf, {}).get(y, 0) for y in years]
    
    # 创建图表
    fig, ax = plt.subplots(figsize=(16, 10))
    
    x = np.arange(len(years))
    width = 0.28  # 每组柱子的宽度
    
    # 三个区域的数据 - 使用深色调区分（顺序：中国、美国、全球）
    regions = [
        ('中国', china_by_conf, '#D62728'),
        ('美国', us_by_conf, '#1F77B4'),
        ('全球', global_by_conf, '#1B1B1B')
    ]
    
    # 绘制堆叠柱状图
    for region_idx, (region_name, data, region_color) in enumerate(regions):
        offset = (region_idx - 1) * width  # -width, 0, +width
        
        bottom = np.zeros(len(years))
        bars_list = []
        
        for conf in conferences:
            values = data[conf]
            bars = ax.bar(x + offset, values, width * 0.9, bottom=bottom, 
                         color=conf_colors[conf], alpha=0.85, 
                         edgecolor='#333333', linewidth=0.8)
            bars_list.append((bars, values))
            bottom += np.array(values)
        
        # 添加数值标签（每个会议的数量）
        for bars, values in bars_list:
            for i, (bar, val) in enumerate(zip(bars, values)):
                if val > 0:
                    # 在柱子内部显示数量
                    ax.text(bar.get_x() + bar.get_width()/2, 
                           bar.get_y() + bar.get_height()/2,
                           f'{int(val)}', ha='center', va='center', 
                           fontsize=12, fontweight='bold', color='white')
        
        # 添加总计标签（国家+换行+发文数量）
        totals = [sum(data[conf][i] for conf in conferences) for i in range(len(years))]
        for i, total in enumerate(totals):
            ax.text(x[i] + offset, total + 8, f'{region_name}\n{int(total)}', ha='center', va='bottom', 
                   fontsize=12, fontweight='bold', color=region_color)
    
    # 添加图例 - 学术论文格式
    from matplotlib.patches import Patch, FancyBboxPatch
    
    # 会议图例（颜色）
    conf_elements = [
        Patch(facecolor='#2166AC', alpha=0.85, label='CRYPTO'),
        Patch(facecolor='#B2182B', alpha=0.85, label='EUROCRYPT'),
        Patch(facecolor='#4DAF4A', alpha=0.85, label='ASIACRYPT')
    ]
    
    # 添加会议图例
    legend = ax.legend(handles=conf_elements, fontsize=13, loc='upper left', ncol=3, 
              frameon=True, fancybox=False, shadow=False,
              edgecolor='#000000', facecolor='white', framealpha=1.0,
              borderpad=1.0, labelspacing=0.6, handlelength=1.5, handleheight=1.0,
              title='Conference', title_fontsize=13)
    legend.get_frame().set_linewidth(1.0)
    
    ax.set_xlabel('年份', fontsize=14, fontweight='bold')
    ax.set_ylabel('论文数量', fontsize=14, fontweight='bold')
    ax.set_title('三大密码会（CRYPTO/EUROCRYPT/ASIACRYPT）每年发文数量对比\n全球 vs 中国 vs 美国 (2020-2025)', fontsize=18, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(years, fontsize=14)
    ax.tick_params(axis='y', labelsize=14)
    ax.grid(axis='y', alpha=0.4, linestyle='-', color='#CCCCCC')
    ax.set_ylim(0, 500)  # 设置y轴范围
    
    # 设置坐标轴样式
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_linewidth(1.5)
    ax.spines['bottom'].set_linewidth(1.5)
    ax.tick_params(width=1.5, length=6)
    
    plt.tight_layout()
    
    output_file = GRAPH_DIR / '三大密码会_发文数量_柱状图.png'
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"已生成: {output_file}")



def plot_line_chart(global_data: dict, china_data: dict, us_data: dict):
    """生成曲线图"""
    years = list(range(2020, 2026))
    
    # 按年份汇总
    global_totals = get_total_by_year(global_data)
    china_totals = get_total_by_year(china_data)
    us_totals = get_total_by_year(us_data)
    
    # 准备数据
    global_counts = [global_totals.get(y, 0) for y in years]
    china_counts = [china_totals.get(y, 0) for y in years]
    us_counts = [us_totals.get(y, 0) for y in years]
    
    # 创建曲线图
    fig, ax = plt.subplots(figsize=(14, 8))
    
    ax.plot(years, global_counts, 'o-', color='#2196F3', linewidth=2.5, markersize=8, label='全球')
    ax.plot(years, china_counts, 's-', color='#F44336', linewidth=2.5, markersize=8, label='中国')
    ax.plot(years, us_counts, '^-', color='#4CAF50', linewidth=2.5, markersize=8, label='美国')
    
    # 添加数值标签
    for i, (g, c, u) in enumerate(zip(global_counts, china_counts, us_counts)):
        ax.annotate(f'{g}', (years[i], g), textcoords="offset points", xytext=(0, 10), ha='center', fontsize=13)
        ax.annotate(f'{c}', (years[i], c), textcoords="offset points", xytext=(0, -15), ha='center', fontsize=13, color='#F44336')
        ax.annotate(f'{u}', (years[i], u), textcoords="offset points", xytext=(0, 10), ha='center', fontsize=13, color='#4CAF50')
    
    ax.set_xlabel('年份', fontsize=14)
    ax.set_ylabel('论文数量', fontsize=14)
    ax.set_title('三大密码会（CRYPTO/EUROCRYPT/ASIACRYPT）每年发文数量趋势\n中国 vs 美国 vs 全球 (2020-2025)', fontsize=14, fontweight='bold')
    ax.set_xticks(years)
    ax.set_xticklabels(years, fontsize=14)
    ax.legend(fontsize=13, loc='upper left')
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, max(global_counts) * 1.2)
    
    plt.tight_layout()
    output_file = GRAPH_DIR / '三大密码会_发文数量_曲线图.png'
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"已生成: {output_file}")

def plot_by_conference(global_data: dict, china_data: dict, us_data: dict):
    """按会议分组生成柱状图"""
    years = list(range(2020, 2026))
    conferences = ['CRYPTO', 'EUROCRYPT', 'ASIACRYPT']
    
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    
    for idx, conf in enumerate(conferences):
        ax = axes[idx]
        
        global_counts = [global_data.get(conf, {}).get(y, 0) for y in years]
        china_counts = [china_data.get(conf, {}).get(y, 0) for y in years]
        us_counts = [us_data.get(conf, {}).get(y, 0) for y in years]
        
        x = np.arange(len(years))
        width = 0.25
        
        ax.bar(x - width, china_counts, width, label='中国', color='#F44336', alpha=0.85)
        ax.bar(x, us_counts, width, label='美国', color='#2196F3', alpha=0.85)
        ax.bar(x + width, global_counts, width, label='全球', color='#4CAF50', alpha=0.85)
        
        ax.set_xlabel('年份', fontsize=14)
        ax.set_ylabel('论文数量', fontsize=14)
        ax.set_title(f'{conf}', fontsize=14, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(years, fontsize=14)
        ax.legend(fontsize=13)
        ax.grid(axis='y', alpha=0.3)
    
    fig.suptitle('三大密码会各会议每年发文数量对比 (2020-2025)', fontsize=14, fontweight='bold')
    plt.tight_layout()
    
    output_file = GRAPH_DIR / '三大密码会_各会议_柱状图.png'
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"已生成: {output_file}")

def plot_proportion_chart(global_data: dict, china_data: dict, us_data: dict):
    """生成占比趋势图"""
    years = list(range(2020, 2026))
    
    # 按年份汇总
    global_totals = get_total_by_year(global_data)
    china_totals = get_total_by_year(china_data)
    us_totals = get_total_by_year(us_data)
    
    # 计算占比
    china_ratio = [china_totals.get(y, 0) / global_totals.get(y, 1) * 100 for y in years]
    us_ratio = [us_totals.get(y, 0) / global_totals.get(y, 1) * 100 for y in years]
    
    # 创建占比图
    fig, ax = plt.subplots(figsize=(14, 8))
    
    ax.plot(years, china_ratio, 's-', color='#F44336', linewidth=2.5, markersize=8, label='中国占比')
    ax.plot(years, us_ratio, '^-', color='#4CAF50', linewidth=2.5, markersize=8, label='美国占比')
    
    # 添加数值标签
    for i, (c, u) in enumerate(zip(china_ratio, us_ratio)):
        ax.annotate(f'{c:.1f}%', (years[i], c), textcoords="offset points", xytext=(0, 10), ha='center', fontsize=13, color='#F44336')
        ax.annotate(f'{u:.1f}%', (years[i], u), textcoords="offset points", xytext=(0, -15), ha='center', fontsize=13, color='#4CAF50')
    
    ax.set_xlabel('年份', fontsize=14)
    ax.set_ylabel('占比 (%)', fontsize=14)
    ax.set_title('三大密码会中国和美国论文占比趋势 (2020-2025)', fontsize=14, fontweight='bold')
    ax.set_xticks(years)
    ax.set_xticklabels(years, fontsize=14)
    ax.legend(fontsize=13, loc='upper left')
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, max(max(china_ratio), max(us_ratio)) * 1.3)
    
    plt.tight_layout()
    output_file = GRAPH_DIR / '三大密码会_占比趋势_曲线图.png'
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"已生成: {output_file}")

def main():
    global DATA_DIR, GRAPH_DIR
    parser = argparse.ArgumentParser(description='生成三大密码会中美全球论文统计图表')
    parser.add_argument('--data-dir', type=Path, default=DATA_DIR, help='包含三份历史 CSV 的目录')
    parser.add_argument('--output-dir', type=Path, default=GRAPH_DIR, help='PNG 图表输出目录')
    args = parser.parse_args()
    DATA_DIR = args.data_dir
    GRAPH_DIR = args.output_dir
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)

    print("=== 加载数据 ===\n")
    
    # 加载全球数据
    global_data = load_paper_counts('三大密码会_全球_20-25.csv')
    print("全球数据:")
    for conf in ['CRYPTO', 'EUROCRYPT', 'ASIACRYPT']:
        counts = [global_data.get(conf, {}).get(y, 0) for y in range(2020, 2026)]
        print(f"  {conf}: {counts}")
    
    # 加载中国数据
    china_data = load_author_data('三大密码会_中国机构_20-25.csv')
    print("\n中国数据:")
    for conf in ['CRYPTO', 'EUROCRYPT', 'ASIACRYPT']:
        counts = [china_data.get(conf, {}).get(y, 0) for y in range(2020, 2026)]
        print(f"  {conf}: {counts}")
    
    # 加载美国数据
    us_data = load_author_data('三大密码会_美国机构_20-25.csv')
    print("\n美国数据:")
    for conf in ['CRYPTO', 'EUROCRYPT', 'ASIACRYPT']:
        counts = [us_data.get(conf, {}).get(y, 0) for y in range(2020, 2026)]
        print(f"  {conf}: {counts}")
    
    print("\n=== 生成图表 ===\n")
    
    # 生成柱状图
    plot_bar_chart(global_data, china_data, us_data)
    
    # 生成曲线图
    plot_line_chart(global_data, china_data, us_data)
    
    # 按会议分组柱状图
    plot_by_conference(global_data, china_data, us_data)
    
    # 生成占比趋势图
    plot_proportion_chart(global_data, china_data, us_data)
    
    print("\n=== 完成 ===")
    print(f"\n所有图表已保存到: {GRAPH_DIR}")

if __name__ == '__main__':
    main()
