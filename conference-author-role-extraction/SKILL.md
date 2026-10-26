---
name: conference-author-role-extraction
description: Build paper-author role facts such as first author, participating author, corresponding author placeholders, and equal-contribution placeholders from normalized conference author rows.
license: MIT
compatibility: Requires Python 3.10+ and normalized author affiliation CSV inputs.
metadata:
  author: llm-conference-skill
  version: "0.1"
allowed-tools: Bash(python3:*) Read Glob Grep
---

# 顶会作者角色抽取

本 skill 负责把作者角色从统计逻辑中拆出来，形成独立 `paper_author_roles.csv`。当前最小实现只从现有作者顺序中稳定生成：

- 第一作者：`author_order == 0`
- 参与作者：出现在论文作者列表中的作者

当前不自动推断：

- 通讯作者
- 共同一作
- equal contribution

这些字段会保留为显式列，默认 `false` 且 `needs_review=true`，等待后续 PDF frontmatter / HTML / OpenReview 元数据解析补齐。

## 输入

优先输入标准化事实表：

- `generated-data/analysis/normalized_run/normalized/author_affiliation_facts.csv`
- 或任意包含 `conference/year/paper_id/title/name/author_order` 的 CSV

## 输出

默认输出：

```text
generated-data/author-roles/
  paper_author_roles.csv
  author_role_report.json
  author_role_report.md
```

## 使用方式

```bash
python3 scripts/build_author_roles.py \
  --input generated-data/analysis/normalized_run/normalized/author_affiliation_facts.csv \
  --output-dir generated-data/author-roles
```

使用人工验证的角色覆盖表：

```bash
python3 scripts/build_author_roles.py \
  --input generated-data/normalized/author_affiliation_facts.csv \
  --role-overrides generated-data/author-roles/author_role_overrides.csv \
  --output-dir generated-data/author-roles
```

每次运行都会生成 `author_role_overrides_template.csv`，可复制为 `author_role_overrides.csv` 后只填写已人工确认的通讯作者或共同一作。

## 设计原则

- 角色事实表一人一论文一行，不因多机构归属重复。
- 第一作者只使用确定性的 `author_order == 0`。
- 通讯作者和共同一作不猜测，保留空位和复核标记。
- 后续统计脚本应消费 `paper_author_roles.csv`，而不是在每个统计模块重复判断作者角色。
