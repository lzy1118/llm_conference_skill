---
name: conference-quality-audit
description: Audit normalized conference datasets and downstream analysis outputs for missing values, unresolved entities, weak identity assumptions, suspicious coverage changes, and incomplete analysis artifacts. Use when the user wants quality checks before or after running conference statistics and automation pipelines.
license: MIT
compatibility: Requires Python 3.10+ and either normalized conference CSV data or an existing analysis output directory.
metadata:
  author: llm-conference-skill
  version: "1.0"
allowed-tools: Bash(python3:*) Read Glob Grep
---

# 顶会质量审计

对标准化后的顶会数据和下游分析产物进行质量检查，识别最常见的数据风险点，同时不在审计阶段直接修复数据。

## 适用场景

- 用户希望在正式分析前验证标准化数据质量。
- 用户希望确认自动化运行是否产出了完整分析文件。
- 用户怀疑存在国家未解析、机构标准化不稳定或作者身份归并风险。
- 用户希望得到可机器消费的异常报告供后续复核。

## 设计原则

这是一个质量门，而不是修复器。

它负责发现问题、记录问题、汇总问题，而不是静默修正问题。修复和审计应分离，以便用户决定是回到标准化阶段重跑，还是带着这些风险继续分析。

详细检查项见 [审计契约](references/audit_contract.md)。

## 支持的入口模式

### 模式 1：标准化数据审计

审计一份 `author_affiliation_facts.csv`，并可选结合对应的 `institution_dim.csv`。

### 模式 2：分析目录审计

审计一个完整分析目录中是否存在预期产物，例如 `country/`、`institutions/`、`authors/`、`trends/`、`collaboration/`。

## 标准输出

输出到 `data/analysis/audit/`：

1. `quality_audit.json`
2. `quality_audit.md`

## 工作流程

### 第 1 步：审计标准化明细行

重点检查：

- `paper_key`、`conference`、`year`、`name`、`inst` 是否缺失
- `country == Unknown` 的行
- `author_key` 缺失或过弱的行
- `classification_confidence` 过低或非数值
- 同一机构显示名对应多个标准化 key
- 是否仍残留明显噪声机构名，例如 `Independent Researcher`、`None`、`Privacy`

### 第 2 步：审计机构维表

如果 `institution_dim.csv` 存在，检查：

- `needs_review == True` 的行
- `country == Unknown` 的机构
- 重复的机构显示名

### 第 3 步：审计分析产物

如果提供了分析目录，则检查：

- 预期文件是否缺失
- 汇总 CSV 是否为空
- markdown 报告是否缺失

### 第 4 步：输出可操作问题

同时生成 JSON 与 Markdown，其中应优先列出最严重的问题项。

## 示例命令

```bash
python3 scripts/quality_audit.py \
  --normalized-input data/analysis/normalized/author_affiliation_facts.csv \
  --institution-dim data/analysis/normalized/institution_dim.csv \
  --output-dir data/analysis/audit
```

```bash
python3 scripts/quality_audit.py \
  --analysis-dir data/analysis/automation \
  --output-dir data/analysis/audit
```

## 常见问题

- 把审计警告直接等同于流程失败，而不结合上下文判断。
- 没有明确说明哪些检查因为文件缺失而被跳过。
- 在审计步骤里混入自动修复逻辑。
