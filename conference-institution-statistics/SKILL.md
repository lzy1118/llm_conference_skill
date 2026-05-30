---
name: conference-institution-statistics
description: Generate institution-level rankings, participation tables, and trend summaries from normalized conference datasets. Use when the user asks for top institutions, institution shares, conference participation by institution, or cross-year institutional comparisons.
license: MIT
compatibility: Requires Python 3.10+ and normalized conference data with stable institution keys.
metadata:
  author: llm-conference-skill
  version: "1.0"
allowed-tools: Bash(python3:*) Read Glob Grep
---

# 顶会机构统计

基于稳定的机构标准化结果，生成机构层面的参与指标、排名和趋势视图。

## 适用场景

- 用户希望查看一个或多个会议中的头部机构。
- 用户希望查看机构按年份的变化趋势。
- 用户需要按国家、会议、年份或机构类型切片查看机构排名；美国机构只应视为其中一种可选国家切片。
- 用户需要能追溯到标准化明细行的机构排名结果。

## 输入要求

优先使用：

- `author_affiliation_facts.csv`
- `institution_dim.csv`

如果输入还停留在抽取层，应优先选择 `conference-paper-extraction` 的主输出：

- `output/*_author_affiliations.csv`
- 汇总版 `*_作者机构国家.csv`

再经 `conference-dataset-normalization` 生成 `author_affiliation_facts.csv` 与 `institution_dim.csv`。

最低需要以下字段：

- `paper_key`
- `conference`
- `year`
- `institution_key`
- 机构展示字段，如 `inst`

可选但很有用的字段：

- `country`
- `classification_confidence`

## 标准输出

输出到 `data/analysis/institutions/`：

1. `institution_summary.csv`
2. `institution_by_conference.csv`
3. `institution_by_year.csv`
4. `institution_report.md`

指标定义详见 [机构排名参考](references/institution_rankings.md)。

## 核心指标

至少计算以下指标：

| 指标 | 定义 |
|------|------|
| `papers` | 至少有一位作者来自该机构的去重论文数 |
| `authors` | 归属于该机构的作者-论文记录数 |
| `first_author_papers` | 该机构出现在一作位置的去重论文数 |
| `conferences` | 该机构出现过的去重会议数 |
| `years_active` | 该机构出现过的去重年份数 |

分组时必须使用标准化后的 `institution_key`，同时保留便于阅读的机构显示名。

## 工作流程

### 第 1 步：明确机构范围

从以下范围中选择一种：

- 全部机构
- 仅某个国家切片
- 某一国家的机构
- 某一会议家族中的机构

默认应把“全球机构长表”视为主输入，把国家过滤视为后续切片条件，而不是主输入文件类型。

如果组合了多个范围条件，必须在报告中明确写出。

### 第 2 步：验证机构标准化质量

在排名前检查：

- 多个显示名是否指向同一个 `institution_key`
- 同一个显示名是否被拆成多个 key
- 是否存在 `unknown` 之类未解析机构

如果标准化质量较弱，应先运行 `conference-dataset-normalization`。

### 第 3 步：聚合排名

默认把去重论文参与数作为 headline 指标，同时保留作者记录数，因为这能反映不同维度的规模。

### 第 4 步：补充趋势视图

如果包含多个年份，应进一步计算同比变化和多年度参与概览。

### 第 5 步：保持可审计性

对于任一头部机构，用户应能回溯到支撑该结果的 `paper_key` 明细行。

## 推荐输出列

`institution_summary.csv` 建议包含：

- `institution_key`
- `institution_name`
- `country`
- `papers`
- `authors`
- `first_author_papers`
- `conferences`
- `years_active`
- `paper_share`

## 默认排序规则

如果用户没有指定排序方式，默认按以下顺序排序：

1. `papers` 降序
2. `authors` 降序
3. `first_author_papers` 降序
4. `institution_name` 升序

## 常见问题

- 仅按原始机构归属行数做排名。
- 没有确认粒度就把校区或变体机构拆开计算。
- 把高校、公司、研究院混在一起却未加说明。
- 没有区分全球排名与具体国家切片排名。
