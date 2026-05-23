---
name: conference-visualization
description: Generate reusable charts and lightweight visual assets from existing conference analysis outputs such as country, institution, author, trend, and collaboration CSV files. Use when the user wants figures, dashboards, SVG charts, or visual summaries built from stable analysis artifacts instead of one-off plotting scripts.
license: MIT
compatibility: Requires Python 3.10+ and existing analysis CSV outputs. Designed to work without third-party plotting libraries by emitting SVG files.
metadata:
  author: llm-conference-skill
  version: "1.0"
allowed-tools: Bash(python3:*) Read Glob Grep
---

# 顶会可视化

基于已有分析产物生成可复用图表与轻量可视化资源，而不是把作图逻辑耦合到原始抽取流程或单次案例脚本中。

## 适用场景

- 用户希望根据国家、机构、作者、趋势或合作分析结果生成图表。
- 用户希望从一次 analysis run 中直接得到可复用的可视化产物。
- 用户希望生成适合查看、嵌入和版本管理的 SVG 图表。
- 用户希望使用一层通用可视化能力，而不是某个单独案例脚本。

## 设计原则

本 skill 消费 analysis outputs，而不是 normalized 原始明细。

它应读取其他分析 skill 产出的稳定 section 文件，并渲染一组清晰、轻量、可复用的图表。

这个 skill 参考了仓库中的 `Graph/` 案例目录，但不应继承其中的绝对路径、会议特定命名或单案例绑定逻辑。

输入输出规则见 [可视化契约](references/visualization_contract.md)。

## 输入要求

接受一个分析目录根路径，其中可包含以下任意子集：

- `country/country_summary.csv`
- `institutions/institution_summary.csv`
- `authors/author_summary.csv`
- `trends/trend_by_entity_year.csv`
- `collaboration/collaboration_edges.csv`

至少应存在一种受支持输入。

## 标准输出

输出到 `data/analysis/visualizations/`：

1. `visualization_manifest.json`
2. 零个或多个 SVG 文件，例如：
   - `country_top_papers.svg`
   - `institution_top_papers.svg`
   - `author_top_papers.svg`
   - `trend_entity_year.svg`
   - `collaboration_top_edges.svg`

## 工作流程

### 第 1 步：检测可用分析章节

只为当前真实存在的 section 生成图表。

### 第 2 步：使用稳定 headline 指标

优先使用：

- `papers` 作为排名类图表指标
- `shared_papers` 作为合作边图表指标
- `papers_peak` 仅用于文本摘要，不替代时序图

### 第 3 步：选择清晰图形形式

默认图表映射：

- 国家、机构、作者：横向条形图
- 趋势：按年份折线图
- 合作：头部合作边条形图

### 第 4 步：保持范围与来源可见

始终输出 manifest，记录：

- 输入分析目录
- 成功渲染的图表文件
- 跳过或缺失的章节
- 使用的 `top-n`

## 示例命令

```bash
python3 scripts/generate_visualizations.py \
  --analysis-dir data/analysis/automation \
  --output-dir data/analysis/visualizations
```

## 常见问题

- 在可视化层重新计算统计结果。
- 硬编码会议名称或本地绝对路径。
- 使用不能直观体现规模与排序的图表形式。
- 假设每次分析运行都包含所有 section。
