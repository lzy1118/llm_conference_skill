---
name: conference-collaboration-analysis
description: Generate coauthorship and cross-entity collaboration summaries from normalized conference datasets. Use when the user asks for collaboration networks, coauthor pairs, cross-country collaboration, institution collaboration, or reusable network edge tables for conference analysis.
---

# 顶会合作分析

生成可复用的合作边表与简洁合作摘要，同时避免把网络分析逻辑耦合进排行或趋势技能中。

## 适用场景

- 用户希望分析共著网络。
- 用户希望查看跨国合作数量。
- 用户希望生成机构之间的合作表。
- 用户需要边列表供下游图分析或可视化使用。

## 设计原则

本 skill 应输出平铺的边表和简明摘要。

默认不要依赖图分析库。输出应保持轻量，让下游工具自行选择网络可视化或中心性分析方案。

默认边定义见 [合作指标参考](references/collaboration_metrics.md)。

## 支持的合作模式

1. `author`：作者之间的无序共著对
2. `country`：每篇论文中的无序国家对
3. `institution`：每篇论文中的无序机构对

## 输入要求

优先使用 `data/analysis/normalized/author_affiliation_facts.csv`。

必需字段按模式而定：

- 作者模式：`paper_key`、`author_key` 或 `name`
- 国家模式：`paper_key`、`country`
- 机构模式：`paper_key`、`institution_key`、`inst`

推荐公共字段：

- `conference`
- `year`

## 标准输出

输出到 `data/analysis/collaboration/`：

1. `collaboration_edges.csv`
2. `collaboration_summary.csv`
3. `collaboration_report.md`

## 工作流程

### 第 1 步：选择边模式

每次运行只使用一种主模式。

### 第 2 步：在论文内部先去重

在每个 `paper_key` 内，先消除重复节点，再生成边。

这一步对多机构归属与重复作者行尤其重要。

机构或国家字段出现复合标签时，先拆分有可靠身份的组成项并分别生成节点；无法
确认的组成项作为残片丢弃，不保留整个复合标签节点。

### 第 3 步：生成无序边对

对每篇论文，枚举所有不同节点之间的无序组合，并累加 `shared_papers`。

### 第 4 步：补充时间覆盖信息

至少跟踪：

- `conference_count`
- `year_first`
- `year_last`

按年份范围分析时，必须在生成边之前使用 `--year-start`/`--year-end` 过滤明细行；不要从全量边表的 `year_first`/`year_last` 反推子区间贡献。

### 第 5 步：报告合作集中度

至少总结：

- `shared_papers` 最高的合作边
- 节点数量
- 边数量
- 单篇合作与重复合作的差异

## 示例命令

```bash
python3 scripts/collaboration_analysis.py \
  --input data/analysis/normalized/author_affiliation_facts.csv \
  --output-dir data/analysis \
  --mode author
```

```bash
python3 scripts/collaboration_analysis.py \
  --input data/analysis/normalized/author_affiliation_facts.csv \
  --output-dir data/analysis \
  --mode country \
  --conference CCS
```

```bash
python3 scripts/collaboration_analysis.py \
  --input data/analysis/normalized/author_affiliation_facts.csv \
  --output-dir data/analysis \
  --mode institution \
  --conference CRYPTO \
  --year-start 2020 \
  --year-end 2025
```

## 常见问题

- 错把自环算作合作边。
- 把镜像边重复计数。
- 用未标准化的机构显示名直接构造机构边。
- 把一篇多人论文误当成多次独立重复合作。
