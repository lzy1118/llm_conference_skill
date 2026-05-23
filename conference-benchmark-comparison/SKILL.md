---
name: conference-benchmark-comparison
description: Compare existing conference analytics outputs across conferences, years, or analysis runs. Use when the user wants leaderboard comparisons, cross-conference benchmarking, side-by-side rankings, or standardized comparison tables built from prior analysis results.
license: MIT
compatibility: Requires Python 3.10+ and existing summary CSV outputs from conference analytics skills.
metadata:
  author: llm-conference-skill
  version: "1.0"
allowed-tools: Bash(python3:*) Read Glob Grep
---

# 顶会基准对比

基于已有分析产物生成并排对比表，用于跨会议、跨年份或跨分析运行的基准比较，而不是重新回到底层事实表做统计。

## 适用场景

- 用户希望比较多个会议之间的表现。
- 用户希望比较不同年份或不同分析运行的结果。
- 用户希望生成国家、机构或作者层面的基准对比表。
- 用户希望避免手工在表格中做多份 summary 的横向拼接。

## 设计原则

本 skill 应消费 summary 输出，而不是 normalized 事实表。

优先读取多个已生成的排行榜型 summary 文件，并把它们组合成一张窄而清晰的对比表。

输入输出契约见 [比较契约](references/comparison_contract.md)。

## 输入要求

接受重复成对出现的参数：

- `--label <name>`
- `--summary <csv path>`

每份 summary 文件应代表一个可比较切片，例如某个会议某年的国家排名。

支持的 summary 类型：

- 国家 summary
- 机构 summary
- 作者 summary

## 标准输出

输出到 `data/analysis/comparisons/`：

1. `benchmark_comparison.csv`
2. `benchmark_report.md`

## 工作流程

### 第 1 步：保持对比对象同质

一次运行只比较同一种实体类型。不要在同一张表里混合国家与机构，或机构与作者。

### 第 2 步：选择公共指标

默认优先使用 `papers` 列作为对比指标。

### 第 3 步：统一对比表面

输出应为“每个实体一行、每个 label 一列”的宽表形式。

### 第 4 步：补充基础差异指标

至少计算：

- 最佳 label
- 最大值
- 最小值
- spread（最大值减最小值）

## 示例命令

```bash
python3 scripts/compare_benchmarks.py \
  --label CCS2023 --summary data/ccs2023/country/country_summary.csv \
  --label CCS2024 --summary data/ccs2024/country/country_summary.csv \
  --output-dir data/analysis/comparisons
```

## 常见问题

- 在一个输出里混用了不同实体类型。
- 比较了过滤条件不同的排名却没有说明。
- 假设每个 label 都包含完全相同的实体集合。
