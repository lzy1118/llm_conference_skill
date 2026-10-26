---
name: conference-report-generation
description: Generate Markdown summary reports from existing conference analysis outputs such as country, institution, author, trend, and collaboration CSV files. Use when the user wants a readable report, executive summary, leaderboard digest, or a stitched narrative across multiple analytics artifacts.
license: MIT
compatibility: Requires Python 3.10+ and existing analysis CSV outputs produced by conference analytics skills.
metadata:
  author: llm-conference-skill
  version: "1.0"
allowed-tools: Bash(python3:*) Read Glob Grep
---

# 顶会报告生成

基于已有分析产物生成简洁、可审计的 Markdown 报告，而不是重新计算底层统计结果。

## 适用场景

- 用户希望得到可直接阅读的最终报告，而不仅仅是原始 CSV。
- 用户希望把国家、机构、作者、趋势、合作几个分析结果汇总到同一份文档中。
- 用户希望在已有分析之上增加一层可复用的报告生成能力。
- 用户希望为一次分析运行或一个会议切片生成对应报告。

## 设计原则

本 skill 应消费分析产物，而不是重新计算统计。

优先读取以下 skills 的输出：

- `conference-country-statistics`
- `conference-institution-statistics`
- `conference-author-statistics`
- `conference-trend-analysis`
- `conference-collaboration-analysis`

输入与章节建议见 [报告契约](references/report_contract.md)。

## 输入要求

接受一个分析目录根路径，目录下可包含以下任意子文件：

- `country/country_summary.csv`
- `institutions/institution_summary.csv`
- `authors/author_summary.csv`
- `trends/trend_summary.csv`
- `collaboration/collaboration_edges.csv`

至少应存在一种受支持的输入文件。

## 标准输出

输出到 `generated-data/reports/`：

1. `conference_report.md`
2. `conference_report.json`

## 工作流程

### 第 1 步：识别可用章节

检测当前分析目录下存在哪些分析产物，仅为存在的部分生成章节。

### 第 2 步：提炼稳定摘要层

对于每一类可用产物，提取头部行或最重要边，例如 top 5。

### 第 3 步：显式记录范围

报告中应始终写明：

- 输入分析目录
- 实际包含的章节
- 缺失的章节

### 第 4 步：同时输出人类与机器可读结果

生成一份 Markdown 报告，以及一份 JSON 元数据摘要，供自动化链继续消费。

## 示例命令

```bash
python3 scripts/generate_report.py \
  --analysis-dir generated-data/analysis \
  --output-dir generated-data/reports
```

## 常见问题

- 在报告层重新从 normalized 数据重算指标。
- 假设每个章节一定存在。
- 把不同分析运行的结果混到同一份报告中。
- 对缺失输入只跳过、不说明。
