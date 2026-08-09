---
name: conference-country-statistics
description: Generate country-level statistics and country or region paper-detail queries from normalized conference author-affiliation datasets. Use when the user needs country counts, shares, trends, rankings, comparisons, or the papers, authors, and institutions associated with a selected country or region.
license: MIT
metadata:
  author: llm-conference-skill
  version: "1.0"
allowed-tools: Bash(python3:*) Read Glob Grep
---

# 顶会国别统计

基于标准化后的顶会作者-机构数据，生成国家层面的参与统计指标。

## 适用场景

- 用户需要国家排名、占比或趋势分析。
- 用户希望比较不同会议或不同年份的国家表现。
- 已经有机构层数据，需要进一步汇总到国家层。
- 用户希望得到可复现的国家统计结果，而不是手工在表格里计数。

## 输入要求

优先使用 `conference-dataset-normalization` 生成的 `data/analysis/normalized/author_affiliation_facts.csv`。

如果当前还处在抽取层与标准化层之间，也可以先使用 `conference-paper-extraction` 的主输出：

- `output/*_author_affiliations.csv`
- 汇总版 `*_作者机构国家.csv`

再通过 `conference-dataset-normalization` 统一映射成 `author_affiliation_facts.csv` 后进入本 skill。

最低需要以下字段：

- `paper_key`
- `conference`
- `year`
- `author_key` 或 `name`
- `institution_key` 或 `inst`
- `country`

如果 `country` 缺失，应先通过机构维表或仓库中的覆盖规则文件补全，再进行统计。


## 核心指标

生成国家汇总表时，至少包含以下明确命名的指标：

| 指标 | 定义 |
|------|------|
| `papers` | 该国至少有一位作者参与的去重论文数 |
| `authors` | 归属于该国的作者-论文记录数 |
| `institutions` | 映射到该国的去重机构数 |
| `paper_share` | 当前分析范围内 `papers / total papers` |
| `author_share` | 当前分析范围内 `authors / total authors` |
| `avg_authors_per_paper` | `authors / papers` |

必须明确说明国家归属规则。如果一篇论文包含多个国家的作者，则在参与视角下，每个国家都可以对该论文计数一次。

详细聚合规则见 [国家指标参考](references/country_metrics.md)。

## 工作流程

### 国家或地区论文明细查询

当用户查询某个国家或地区关联的论文、作者和机构时，运行
`scripts/query_country_papers.py`，并遵循以下规则：

1. 从标准化的 `author_affiliation_facts.csv` 查询，按规范化后的国家组成项匹配；复合国家先按可靠身份拆分。
2. 先应用用户指定的会议和年份过滤条件，再筛选目标国家或地区的事实行。
3. 按 `paper_key` 对论文去重，并从每篇命中论文的全部事实行重建完整、有序的作者列表。
4. 单独输出与目标国家或地区关联的作者和机构，并在作者明细中保留作者对应的机构；不要把论文的全部作者都归入目标国家或地区。
5. 按 `institution_key` 去重机构；显示名称优先使用 `canonical_institution_name`，缺失时再使用 `inst`。
6. 保留国际合作背景，并区分“论文被该国家或地区参与”和“作者或机构归属于该国家或地区”。
7. 在摘要中报告输入事实行数、过滤后事实行数、命中事实行数和去重论文数。

脚本稳定输出：

- `country_papers.csv`
- `country_authors.csv`
- `country_institutions.csv`
- `country_query_summary.json`

### 第 1 步：定义分析范围

在开始统计前，先明确分析切片：

- 单一会议与单一年份
- 同一会议跨多年
- 某一类会议家族，例如密码学或安全
- 仓库中所有可用会议

把所选范围写入最终报告。

### 第 2 步：检查国家映射质量

重点检查：

1. `country` 缺失的行
2. 同一个标准化机构被映射到多个国家
3. 仅格式不同的国家名，例如 `USA` 与 `United States`

在汇总前统一国家展示名称。

### 第 3 步：汇总国家指标

至少在 `data/analysis/country/` 下输出：

1. `country_summary.csv`
2. `country_by_conference.csv`
3. `country_by_year.csv`
4. `country_report.md`

即使用户请求范围较窄，也应保持这些稳定文件名，仅通过行过滤体现范围差异。

### 第 4 步：说明计数口径

每份输出报告都应说明每个指标对应的计数基础：

- 去重论文数
- 作者-机构记录数
- 去重机构数

这样可以避免顶会统计里最常见的口径混淆。

### 第 5 步：识别异常点

标记以下情况：

- 多重机构归属行异常偏多的国家
- 国家映射置信度很低的国家
- 可能由数据源变化导致的年份突增或突降

## 推荐输出列

`country_summary.csv` 建议包含：

- `country`
- `papers`
- `authors`
- `institutions`
- `paper_share`
- `author_share`
- `avg_authors_per_paper`
- `conference_count`
- `year_min`
- `year_max`

## 默认口径

如果用户没有指定计数规则，默认采用：

1. 国家论文参与度按“每篇论文在每个出现国家计一次”计算
2. 作者参与度按作者-论文记录计数
3. 机构数量按标准化后的去重机构计数

### 复合机构与国家标签

如果机构或国家字段包含多个组成项（例如 `Institution A | Institution B` 或
`China | Germany`），先按分隔符拆分。组成项有可靠标准化身份或能与输入中的
已知单项标签对齐时，分别计入展示、排名和明细；无法确认的组成项视为残片并
丢弃，不能把整个复合标签作为一个国家或机构统计。每篇论文在每个已确认国家
中最多计数一次。

## 常见问题

- 把作者行误当作跨年去重后的真实作者人数。
- 直接用原始机构字符串充当国家标识。
- 因重复机构归属导致同一国家内同一论文被重复计数。
- 在一个排名里混用了不同年份范围的会议总量。
