---
name: conference-trend-analysis
description: Generate year-over-year and multi-year trend summaries from normalized conference datasets for countries, institutions, or authors. Use when the user asks for trends, deltas, growth, declines, moving summaries, or temporal comparisons across conference analytics outputs.
license: MIT
compatibility: Requires Python 3.10+ and normalized conference data with conference and year fields.
metadata:
  author: llm-conference-skill
  version: "1.0"
allowed-tools: Bash(python3:*) Read Glob Grep
---

# 顶会趋势分析

分析顶会参与情况如何随时间变化，同时避免把时间序列逻辑硬塞进每一个排行 skill 中。

## 适用场景

- 用户希望查看同比变化。
- 用户希望识别上升或下降中的国家、机构或作者。
- 用户希望得到跨多年的参与趋势概览。
- 用户希望在多个统计视角之上复用同一套时间分析层。

## 设计原则

这是一个横切时间维度的分析层。

它应直接读取标准化事实表并输出趋势结果，而不是把趋势逻辑嵌入国家、机构或作者排行榜中，除非用户明确要求这样做。

默认定义见 [趋势指标参考](references/trend_metrics.md)。

机构或国家字段出现复合标签时，先按可靠身份拆分组成项并分别计算年度论文数；
无法确认的组成项作为残片丢弃，不把复合字符串作为趋势对象。

## 输入要求

优先使用 `data/analysis/normalized/author_affiliation_facts.csv`。

必需字段：

- `paper_key`
- `conference`
- `year`
- 按分析对象至少有以下字段之一：
  - `country`
  - `institution_key`
  - `author_key`

推荐展示字段：

- `inst`
- `name`

## 标准输出

输出到 `data/analysis/trends/`：

1. `trend_summary.csv`
2. `trend_by_entity_year.csv`
3. `trend_report.md`

## 工作流程

### 第 1 步：选择分析对象

一次运行只选择一个主维度：

1. 国家
2. 机构
3. 作者

### 第 2 步：确定计数口径

默认按“每个对象每年参与的去重论文数”统计。

如果用户希望按作者行或机构行强度统计，必须在报告中明确写出。

### 第 3 步：计算年度增减

对每个对象和每个年份，至少计算：

- 当年论文数
- 上一年论文数
- 绝对增减值
- 若上一年非零，则计算相对变化比率

### 第 4 步：提炼多年度模式

至少报告：

- 首次活跃年份
- 最近活跃年份
- 活跃年份数
- 峰值年份
- 峰值论文数
- 从首次到最后观测年份的净变化

### 第 5 步：说明风险点

标记可能由以下原因造成的异常跳变：

- 数据源覆盖变化
- 标准化策略变化
- 会议范围变化

## 示例命令

```bash
python3 scripts/trend_analysis.py \
  --input data/analysis/normalized/author_affiliation_facts.csv \
  --output-dir data/analysis \
  --entity country
```

```bash
python3 scripts/trend_analysis.py \
  --input data/analysis/normalized/author_affiliation_facts.csv \
  --output-dir data/analysis \
  --entity institution \
  --conference CCS
```

## 常见问题

- 比较了不同会议子集的年份结果。
- 没有区分论文数与作者行数口径。
- 只展示增长率而不展示基础绝对量。
- 隐藏了缺失年份或不规则数据覆盖。
