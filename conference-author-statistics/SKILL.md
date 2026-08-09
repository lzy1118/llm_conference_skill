---
name: conference-author-statistics
description: Generate author-level productivity, participation, collaboration, recurrence, and author-detail query results from normalized conference datasets. Use when the user asks for top authors, repeat contributors, an author's papers or collaborators, first-author papers, or author collaboration patterns.
license: MIT
metadata:
  author: llm-conference-skill
  version: "1.0"
allowed-tools: Bash(python3:*) Read Glob Grep
---

# 顶会作者统计

基于标准化后的顶会数据生成作者层面的产出、参与、合作与复现统计，同时显式说明作者身份归并假设。

## 适用场景

- 用户希望查看高产作者或重复投稿作者。
- 用户希望查看一作、末位作者等位置相关统计。
- 用户希望分析合作网络或共著关系。
- 用户希望比较作者在不同会议或不同年份中的活跃度。

## 输入要求

优先使用 `conference-dataset-normalization` 生成的 `author_affiliation_facts.csv`。

最低需要以下字段：

- `paper_key`
- `conference`
- `year`
- `name`
- `author_order`

推荐包含的标准化字段：

- `author_key`

如果不存在 `author_key`，应使用显示名生成保守的标准化 key，并在报告中明确说明其可能导致不同人被合并或同一人被拆分。

由 `conference-analysis-automation/scripts/prepare_affilgood_facts.py` 生成事实表时，会先将明显
的 OCR 插入空格、大小写差异和多余空格归并到同一 `author_key`，例如 `Xiaoyun Wang`、
`Xiaoyun WAng`、`Xiaoyun Wa Ng`。首字母姓名只有在机构或共同作者证据唯一匹配时才自动归并；候选冲突时自动保留为不同 key，不生成身份复核队列。

详细身份与计数建议见 [作者指标参考](references/author_metrics.md)。

## 标准输出

输出到 `data/analysis/authors/`：

1. `author_summary.csv`
2. `author_by_year.csv`
3. `first_author_summary.csv`
4. `coauthor_edges.csv`
5. `author_report.md`

## 核心指标

至少计算以下指标：

| 指标 | 定义 |
|------|------|
| `papers` | 每位作者的去重论文数 |
| `conferences` | 每位作者参与过的去重会议数 |
| `years_active` | 作者活跃的去重年份数 |
| `first_author_papers` | `author_order == 0` 时的去重论文数 |
| `coauthor_count` | 当前分析范围内的去重合作作者数 |

## 工作流程

### 作者明细查询

当用户查询某位作者的论文、合作者或一作论文时，运行
`scripts/query_author_details.py`，并遵循以下规则：

1. 从标准化的 `author_affiliation_facts.csv` 查询；优先按稳定的 `author_key` 精确匹配，否则按规范化后的完整显示名匹配。
2. 先应用用户指定的会议和年份过滤条件，再确定命中的论文范围。
3. 按 `paper_key` 对论文去重，保留标题、会议、年份和目标作者顺序。
4. 从命中论文的全部事实行重建合作者；按 `author_key` 去重，并统计每位合作者的去重合作论文数。
5. 仅把 `author_order == 0` 的论文列入一作论文，不根据姓名位置或领域惯例推断。
6. 若同一显示名对应多个 `author_key`，保留全部命中 key 并显式报告身份歧义；只有通过事实表
   的紧凑姓名规则确认的 OCR 变体才会在上游归并。
7. 在结果中说明：显示名匹配不等同于 ORCID 级身份消歧。

论文跨文件去重时，同时使用大小写、标点和空白不敏感的紧凑标题键，并要求会议、年份和有序
作者签名一致；因此标题中的多余或插入空格不会单独造成漏匹配。

脚本稳定输出：

- `author_papers.csv`
- `author_collaborators.csv`
- `author_first_author_papers.csv`
- `author_query_summary.json`

### 第 1 步：确定作者身份规则

作者统计对身份归并最敏感。优先顺序建议如下：

1. 使用标准化数据中的 `author_key`
2. 使用精确标准化后的全名
3. 仅在用户接受歧义时，使用“姓 + 名首字母”

如果数据跨越多年或跨多个会议家族，必须在报告中说明身份不确定性。

### 第 2 步：计算作者参与度

按作者聚合去重后的 `paper_key`。作者统计应与机构归属统计口径分开，不要混为一谈。

### 第 3 步：计算作者位置指标

如果作者顺序可靠，可增加：

- 一作论文数
- 作者位置中位数
- 末位作者论文数（前提是作者列表完整）

如果数据源无法保证作者顺序，跳过这类指标。

### 第 4 步：生成合作边

生成 `coauthor_edges.csv`，每一行对应一对无序作者组合，并包含 `shared_papers` 字段。

这样可以支持下游网络分析，同时不把本 skill 绑定到任何具体可视化工具。

### 第 5 步：识别重复贡献者

单独生成章节或表格，突出以下作者：

- 跨多个年份持续出现
- 跨多个会议出现
- 跨多个会议家族出现

## 推荐输出列

`author_summary.csv` 建议包含：

- `author_key`
- `author_name`
- `papers`
- `conferences`
- `years_active`
- `first_author_papers`
- `coauthor_count`
- `year_first`
- `year_last`

## 默认排序规则

如果用户没有指定其他方式，默认按以下顺序排序：

1. `papers` 降序
2. `first_author_papers` 降序
3. `conferences` 降序
4. `author_name` 升序

## 常见问题

- 把重名作者错误合并为同一个人。
- 因多机构归属导致同一作者在同一论文上被重复计数。
- 在不同领域中错误地根据作者顺序推断资历。
- 把作者产出和机构产出放在一个排行榜中混算。
