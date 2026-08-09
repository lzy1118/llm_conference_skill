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

## 可选输出：详细排名工作簿

当用户请求同时给出会议范围、年份或年份范围，并出现“详细排名”“详细工作簿”“Top10 及逐篇明细”或同义表达时，生成详细 Excel 工作簿，而不是只生成国家切片 CSV。会议范围可以是任意单个会议、会议集合（例如“四大会”）、集合中的某一个会议或自定义会议列表；会议名称匹配不区分大小写。

以下表达均属于可触发形式（会议名和年份按请求替换）：

- `生成 Asiacrypt 2025 中国大陆详细排名`
- `生成 ASIACRYPT 2020-2025 详细排名`
- `生成四大会 2025 详细排名`
- `生成四大会中的某一个会议 2024 年 Top10 及逐篇明细`
- `生成任意会议 2021 至 2023 年的详细排名工作簿`

如果请求中明确写出“中国大陆”“中国机构”或其他国家/地区，则按该范围过滤；未指定国家/地区时，按请求的默认数据范围统计。详细工作簿应包含论文清单，以及机构和作者的排名与逐篇明细。是否生成方法说明页，应按用户当前请求决定，不设固定规则。论文表按国家/地区、会议和年份范围动态命名（例如 `China_Papers_2025` 或 `Papers_ASIACRYPT_2020_2025`）；核心数据工作表包括：

1. `Papers_<scope>_<year_or_range>`
2. `First_Unit_Top10`
3. `First_Unit_Details`
4. `Participating_Unit_Top10`
5. `Participating_Unit_Details`
6. `First_Author_Top10`
7. `First_Author_Details`
8. `Participating_Author_Top10`
9. `Participating_Author_Details`

其中 `Details` 工作表必须保留排名实体对应的逐篇论文信息；复合机构或国家标签可解析时按组成项拆分并分别统计，无法解析的组成部分作为残片丢弃。中国大陆范围是可选国家规则，不替代全球统计口径。

若用户只说 `中国机构清单`、`中国机构排名` 或指定 `--country China`，仍生成标准国家切片 CSV；只有在同时明确会议范围、年份（或年份范围）和详细排名/逐篇明细意图时，才生成上述多工作表 XLSX。

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

中国机构清单是一个可选国家切片。使用 `--country China` 后，输出仅保留中国归属机构，仍按去重论文数排序，并保留作者数、一作论文数、会议覆盖数和年份覆盖数：

```bash
python3 conference-institution-statistics/scripts/institution_statistics.py \
  --input <analysis-dir>/normalized/author_affiliation_facts.csv \
  --output-dir <analysis-dir>/china-institutions \
  --country China \
  [--year 2025]
```

该切片应同时保留完整的 `institution_summary.csv`、`institution_by_conference.csv`、`institution_by_year.csv` 和 `institution_report.md`，作为中国机构的具体清单；复合机构或国家标签按可解析组成项拆分，无法解析的组成部分按残片丢弃。

### 第 2 步：验证机构标准化质量

在排名前检查：

- 多个显示名是否指向同一个 `institution_key`
- 同一个显示名是否被拆成多个 key
- 是否存在 `unknown` 之类未解析机构
- `Independent Researcher` 是无机构作者的统一占位，不进入机构排名

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
