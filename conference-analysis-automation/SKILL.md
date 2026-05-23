---
name: conference-analysis-automation
description: Run end-to-end or partial automation for conference extraction handoff, dataset normalization, quality audit, report generation, visualization, and downstream country, institution, author, trend, and collaboration analysis. Use when the user wants reproducible batch analysis, one-command statistics generation, or a stable orchestration layer across conference analytics skills.
license: MIT
compatibility: Requires Python 3.10+ and local access to this repository's conference skills and CSV inputs.
metadata:
  author: llm-conference-skill
  version: "1.0"
allowed-tools: Bash(python3:*) Read Glob Grep
---

# 顶会分析自动化

在保持低耦合的前提下，把标准化数据与下游统计、审计、报告、可视化能力串联为可复现的一条分析流水线。

## 适用场景

- 用户希望用一条命令生成质量审计、报告、可视化、国家、机构、作者、趋势或合作分析结果。
- 用户希望针对一个或多个顶会数据集运行可复现的分析流程。
- 用户希望在不破坏统一输入契约的前提下，反复变换过滤条件重跑分析。
- 多个统计 skill 需要协同运行，但不希望改写各自内部逻辑。

## 设计原则

这是一个编排层，而不是领域分析 skill 的替代品。

它与其他 skill 的交互应尽量通过：

- 稳定输入文件
- 命令行接口
- 稳定输出目录
- manifest 与 markdown 报告

不要在自动化层直接导入下游统计函数。优先通过 subprocess 调用现有脚本，只要它们的文件契约稳定，各 skill 就可以独立演进。

交接规则见 [流水线契约](references/pipeline_contract.md)。

## 支持的入口模式

### 模式 1：从原始行级 CSV 开始

先运行 `conference-dataset-normalization`，再把结果扇出到各个下游分析 skill。

输入通常是一份或多份行级 CSV，字段可以映射到标准化阶段定义的统一模式。

如果这些原始行级 CSV 来自 `conference-paper-extraction`，应优先使用其主输出：

- `output/*_author_affiliations.csv`
- 汇总版 `*_作者机构国家.csv`

不要优先把 `*_us_institutions.csv` 当成自动化总入口输入，因为那只是美国子集兼容导出。

### 模式 2：从已有标准化数据开始

如果 `author_affiliation_facts.csv` 已存在，可跳过标准化，直接运行所需分析。

这是重复出报告时的优先模式，因为它减少重复计算，也能保持不同运行之间的可比性。

## 标准输出

将所有自动化结果写入一个专门的运行目录，例如 `data/analysis/automation/`：

1. `automation_manifest.json`
2. `automation_report.md`
3. 下游子目录，例如 `normalized/`、`audit/`、`country/`、`institutions/`、`authors/`、`trends/`、`collaboration/`、`reports/`、`visualizations/`

## 工作流程

### 第 1 步：解析输入

从以下两种输入中二选一：

1. 需要先标准化的原始 CSV
2. 已有标准化作者-机构事实表

如果二者同时提供，只有在用户明确要求跳过标准化时，才把标准化输入视为优先来源。

### 第 2 步：定义分析范围

应显式记录分析切片：

- 会议过滤条件
- 年份过滤条件
- 机构统计所需的国家过滤条件（如有）
- 是否只保留美国机构（兼容切片条件，不是主输入契约）
- 趋势分析对象（如启用）
- 合作分析模式（如启用）
- 需要运行的能力集合：审计、报告、可视化、国家、机构、作者、趋势、合作

### 第 3 步：按需运行标准化

如果从原始输入开始，则调用：

`conference-dataset-normalization/scripts/normalize_dataset.py`

随后把生成的 `normalized/author_affiliation_facts.csv` 作为后续分析唯一共享的事实表。

自动化层应默认围绕“作者-机构-国家”长表组织流程，而不是围绕美国机构子集组织流程。

### 第 4 步：按需运行审计

如果启用了质量审计，则拆成两个独立步骤运行：

- 先对标准化数据做审计
- 再在分析完成后对分析产物做审计

### 第 5 步：独立运行统计技能

分别调用以下脚本：

- `conference-country-statistics/scripts/country_statistics.py`
- `conference-institution-statistics/scripts/institution_statistics.py`
- `conference-author-statistics/scripts/author_statistics.py`
- `conference-trend-analysis/scripts/trend_analysis.py`
- `conference-collaboration-analysis/scripts/collaboration_analysis.py`

不要在自动化层中混合它们的内部假设。自动化层只负责透传过滤条件并记录执行步骤。

### 第 6 步：按需生成报告

如果启用了报告生成，则在分析和分析后审计之后运行，使报告反映最终可用分析结果。

### 第 7 步：按需生成可视化

如果启用了可视化，则在报告生成之后运行，使图表与报告基于同一批分析产物。

### 第 8 步：输出运行元数据

manifest 中应始终记录：

- 用户传入参数
- 实际使用的文件路径
- 分析过滤条件
- 执行过的步骤
- 生成的输出路径
- 跳过或失败的步骤

## 示例命令

```bash
python3 scripts/run_analysis_pipeline.py \
  --raw-input data/interim/conference_rows.csv \
  --output-dir data/analysis/automation
```

```bash
python3 scripts/run_analysis_pipeline.py \
  --normalized-input data/analysis/normalized/author_affiliation_facts.csv \
  --output-dir data/analysis/automation \
  --conference CCS \
  --year 2024 \
  --run audit --run country --run institution --run author --run trend --run collaboration --run report --run visualization \
  --trend-entity country \
  --collaboration-mode author
```

```bash
python3 scripts/run_analysis_pipeline.py \
  --normalized-input data/analysis/normalized/author_affiliation_facts.csv \
  --output-dir data/analysis/automation \
  --run institution \
  --country "United States" \
  --us-only
```

## 默认行为

如果用户没有指定 `--run`，默认运行以下全部能力：

1. 国家统计
2. 机构统计
3. 作者统计
4. 趋势分析
5. 合作分析
6. 质量审计
7. 报告生成
8. 可视化生成

如果用户没有指定过滤条件，则默认在标准化输入的全部行上运行。

## 常见问题

- 为每个小切片都重复运行标准化。
- 没有检查字段契约就把原始抽取结果直接当成分析输入。
- 每次运行都输出到风格不一致的临时目录中。
- 在最终报告里没有明确说明使用了哪些过滤条件。
- 在自动化层直接耦合下游 skill 的内部函数。
