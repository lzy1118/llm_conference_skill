---
name: conference-dataset-normalization
description: Normalize extracted conference paper, affiliation, and audit rows into stable analysis-ready datasets. Use when the user has raw or semi-structured top-conference outputs and needs reusable long tables, fact tables, dimension tables, deduplication, or a clean handoff into country, institution, or author statistics.
license: MIT
compatibility: Requires Python 3.10+ and local access to extracted conference CSV or Excel files.
metadata:
  author: llm-conference-skill
  version: "1.0"
allowed-tools: Bash(python3:*) Read Glob Grep
---

# 顶会数据标准化

在做任何统计前，先把抽取结果整理为稳定、可复用的中间数据集。本 skill 是 `conference-paper-extraction` 与下游统计 skills 之间的桥梁。

## 适用场景

- 用户已经有论文级或作者机构级的抽取结果。
- 不同会议来源的数据需要映射到统一模式。
- 机构、作者、国家统计出现口径不一致。
- 用户希望得到可反复复用的分析中间层 CSV。

## 输入要求

优先使用仓库中已存在的行级表。当前最推荐的上游来源是 `conference-paper-extraction` 的主输出：

- `output/*_author_affiliations.csv`
- 汇总版 `*_作者机构国家.csv`

这些文件已经把主契约固定为“作者-机构-国家”长表。输入字段尽量包含以下约定列：

| 字段 | 是否必需 | 说明 |
|------|----------|------|
| `name` | 是 | 作者姓名 |
| `year` | 是 | 发表年份 |
| `article_tag` | 是 | 稳定论文标签 |
| `author_order` | 是 | 从 0 开始的作者顺序 |
| `inst` | 是 | 机构或归属字符串 |

若存在以下审计字段，也应尽量保留：

| 字段 | 说明 |
|------|------|
| `conference` | 会议简称或代码 |
| `paper_id` | 数据源内部论文 ID |
| `title` | 论文标题 |
| `classification_source` | 如 `rule`、`override`、`source_pdf` |
| `classification_confidence` | 数值型置信度 |
| `classification_reason` | 匹配或判定原因 |
| `country` | 可选的国家映射结果 |
| `is_us_institution` | 来自现有流程的兼容布尔值，仅用于旧美国机构切片链路 |

目标数据契约见 [标准化参考](references/normalization_reference.md)。

## 输出

在统一生成数据目录下生成三张可复用表，例如 `generated-data/normalized/`：

1. `paper_facts.csv`
2. `author_affiliation_facts.csv`
3. `institution_dim.csv`

这些表应保持字段明确、结构稳定、含义可复用。下游 skills 应能直接消费，而不需要重新解析会议源文件。

## 工作流程

### 第 1 步：定位候选输入文件

优先搜索可能的输入文件：

- `**/*.csv`
- `**/*.xlsx`
- `**/*output*.*`
- `**/*audit*.*`
- `Top3-data/data/`
- `Security-data/data/`

如果存在多个文件，优先选择结构化的行级导出结果，而不是重新解析原始 HTML 或 PDF。

当同时看到 `*_author_affiliations.csv` 与 `*_us_institutions.csv` 时，应优先选择前者作为标准化输入，因为它保留了完整国家视角，而不仅是美国机构切片。

### 第 2 步：统一列名

把列名标准化为小写 snake case，并把常见变体映射到统一字段：

| 变体 | 统一字段 |
|------|----------|
| `author`, `author_name` | `name` |
| `institution`, `affiliation` | `inst` |
| `venue`, `conf` | `conference` |
| `paper_title` | `title` |
| `position` | `author_order` |

不要静默丢弃未知列。如果这些列可能对后续排错有帮助，应保留在审计副本中。

### 第 3 步：标准化文本字段

只做确定性的清洗：

- 去除首尾空白
- 合并连续空格
- 在可行时保留原始大小写展示
- 单独生成标准化 key，例如 `author_key`、`institution_key`、`paper_key`

默认不要做模糊合并。只有当精确标准化仍留下明显重复，且用户明确需要合并时才考虑。

### 第 4 步：生成稳定 key

推荐 key 方案：

- `paper_key = conference + year + normalized title`
- `author_key = normalized author name`
- `institution_key = normalized institution text`
- `row_key = paper_key + author_order + institution_key`

如果 `paper_id` 可靠，应单独保留；不要用数据源特定 ID 替代跨来源稳定的 `paper_key`。

### 第 5 步：区分事实表与维表

生成：

1. `paper_facts.csv`：每篇论文一行
2. `author_affiliation_facts.csv`：每条作者-机构记录一行
3. `institution_dim.csv`：每个标准化机构一行

这样可以减少重复计算，也能让国家、机构、作者统计保持低耦合。

### 第 6 步：输出数据质量摘要

始终输出简短的 `normalization_report.md` 或 `normalization_report.json`，至少覆盖：

- 使用了哪些输入文件
- 标准化前后的行数
- 缺失必需字段的情况
- 重复 `row_key` 数量
- 未解析机构或国家数量
- 映射或丢弃了哪些列

## 校验项

在交给下游统计前，至少检查：

1. `author_order` 为非负数值
2. 每一行都有非空 `paper_key`
3. 除非数据源本身不完整，否则 `name` 和 `inst` 不应缺失
4. 重复记录是可解释的，并被有意保留或确定性去重
5. `conference` 与 `year` 与源文件一致

如果上游采用了论文级参与国 reference-first 口径，需要额外检查：

6. 同一 `paper_key + author_order + inst` 出现多行、但 `country` 不同的情况是否来自合法的多参与国展开
7. 不要因为看起来像“重复机构行”就把 reference-first 展开的多国参与记录错误去重

## 交接契约

下游 skills 应能只依赖 `author_affiliation_facts.csv` 和维表来计算指标，而不必重新打开原始会议源文件。

换言之，标准化层负责把抽取层的“作者-机构-国家”主输出收束成稳定事实表；下游分析层不应再回退到任何美国子集导出文件。

这个 skill 应优先用于以下分析前：

- `conference-country-statistics`
- `conference-institution-statistics`
- `conference-author-statistics`

## 常见问题

- 把论文级计数和作者级计数混在一张表里。
- 错误去重，删掉了有效的多机构归属记录。
- 用显示名而不是标准化 key 做 join。
- 丢失了之后解释统计变化所需的来源字段。
