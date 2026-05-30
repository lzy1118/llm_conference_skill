# CFP Schema

## `conference_events.csv`

会议生命周期事件表，每个事件一行。

| 字段 | 说明 |
|------|------|
| `conference_key` | registry 中的会议年份 key，例如 `crypto_2025` |
| `conference` | 会议名，例如 `CRYPTO` |
| `year` | 会议年份 |
| `event_type` | 事件类型 |
| `event_date` | 规范化日期，推荐 `YYYY-MM-DD` |
| `event_datetime` | 若有具体时间，使用 ISO-like 文本保留 |
| `timezone` | 原始或规范化时区 |
| `deadline_scope` | `abstract`、`full_paper`、`artifact`、`camera_ready` 等 |
| `source_text` | 原始文本证据 |
| `source_url` | 来源 URL |
| `source_kind` | `official_cfp`、`conference_site`、`proceedings`、`manual` 等 |
| `confidence` | 0 到 1 的置信度 |
| `needs_review` | 是否需要人工复核 |
| `notes` | 备注 |

推荐 `event_type`：

- `abstract_submission_deadline`
- `paper_submission_deadline`
- `artifact_submission_deadline`
- `rebuttal_start`
- `rebuttal_end`
- `notification`
- `camera_ready`
- `conference_start`
- `conference_end`

## `conference_edition_metadata.csv`

会议年份维表，每个会议年份一行。

| 字段 | 说明 |
|------|------|
| `conference_key` | registry key |
| `conference` | 会议名 |
| `year` | 年份 |
| `family` | 会议家族 |
| `location` | 举办地点 |
| `country` | 举办国家或地区 |
| `start_date` | 会议开始日期 |
| `end_date` | 会议结束日期 |
| `timezone` | 默认时区 |
| `website_url` | 会议官网 |
| `cfp_url` | CFP 页面 |
| `proceedings_url` | proceedings 页面 |
| `source_url` | 元数据来源 |
| `confidence` | 置信度 |
| `needs_review` | 是否需要人工复核 |
| `notes` | 备注 |

## 日期规范化原则

- 已知完整日期时写 `YYYY-MM-DD`。
- 只有月份或日期范围时保留 `source_text`，`event_date` 可为空并标记 `needs_review=true`。
- 时区不确定时不要推断，保留空或原始文本。
- 多来源冲突时保留多行，让审计阶段处理冲突。
