# Author Role Schema

## `paper_author_roles.csv`

每篇论文每位作者一行。

| 字段 | 说明 |
|------|------|
| `paper_key` | 标准化论文 key；如果没有则由会议、年份、paper_id/title 派生 |
| `conference` | 会议名 |
| `year` | 年份 |
| `paper_id` | 来源论文 ID |
| `title` | 论文标题 |
| `author_key` | 标准化作者 key；如果没有则由作者名派生 |
| `author_name` | 作者展示名 |
| `author_order` | 作者顺序，从 0 开始 |
| `is_first_author` | 是否第一作者 |
| `is_participating_author` | 是否参与作者 |
| `is_corresponding_author` | 是否通讯作者 |
| `is_equal_contribution` | 是否共同一作或 equal contribution |
| `role_source` | 角色来源，例如 `author_order`、`pdf_frontmatter`、`manual` |
| `role_evidence` | 原始证据文本 |
| `confidence` | 0 到 1 |
| `needs_review` | 是否需要复核 |

## 当前最小规则

- `is_first_author=true` 当且仅当 `author_order == 0`。
- `is_participating_author=true` 当作者在输入行中出现。
- `is_corresponding_author=false`，等待后续来源补齐。
- `is_equal_contribution=false`，等待后续来源补齐。
- 多机构行按 `(paper_key, author_order, author_key)` 去重，避免一个作者多个机构导致重复角色行。

## `author_role_overrides.csv`

人工验证覆盖表，用于补充通讯作者和共同一作。

最低匹配字段：

- `paper_key`
- `author_key`
- `author_order`

可覆盖字段：

- `is_corresponding_author`
- `is_equal_contribution`
- `role_source`
- `role_evidence`
- `confidence`
- `needs_review`

建议 `role_source` 使用：

- `manual`
- `pdf_frontmatter`
- `publisher_html`
- `openreview_metadata`

不要写入未经验证的猜测结果。
