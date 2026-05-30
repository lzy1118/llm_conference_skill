# CFP 链路与覆盖接入实验记录

## 1. 合并范围

本文件合并以下两份阶段记录：

- `CFP_EXTRACTION_MINIMAL_PIPELINE_2026_05_29.md`
- `CFP_COVERAGE_INTEGRATION_2026_05_29.md`

## 2. 主线目标

围绕 CFP 元数据，一共完成两步：

1. 建立最小 CFP 抽取链路
2. 把 CFP 状态接入 coverage ledger

## 3. 阶段一：最小 CFP 抽取链路

目标：把会议征文、截稿日期、通知日期、会议日期等生命周期信息从“文档缺口”变成可执行模块。

第一阶段重点：

- 独立 skill 边界
- 稳定 schema
- 待填模板
- 规范化脚本
- validation report

新增内容：

- `conference-cfp-extraction/SKILL.md`
- `conference-cfp-extraction/references/cfp_schema.md`
- `conference-cfp-extraction/scripts/run_cfp_pipeline.py`

当前产物：

- `generated-data/cfp/input_templates/cfp_events_template.csv`
- `generated-data/cfp/input_templates/conference_edition_template.csv`
- `generated-data/cfp/output/conference_events.csv`
- `generated-data/cfp/output/conference_edition_metadata.csv`
- `generated-data/cfp/output/cfp_validation_report.json`
- `generated-data/cfp/output/cfp_report.md`

关键结果：

- registered_conference_years: 28
- event_rows: 0
- edition_rows: 0
- missing_event_conference_years: 28
- missing_edition_conference_years: 28

解释：

- 当前是 template-first 阶段
- 事实表为空是预期结果
- 关键收益是 CFP 缺口已经可以被量化表达

## 4. 阶段二：CFP 状态接入 coverage ledger

目标：让 `conference_coverage_ledger.csv` 中的 `cfp_status` 不再是硬编码 `missing`，而是读取 CFP 输出后计算得到。

修改脚本：

- `conference-analysis-automation/scripts/build_coverage_ledger.py`

默认读取：

- `generated-data/cfp/output/conference_events.csv`
- `generated-data/cfp/output/conference_edition_metadata.csv`

当前 `cfp_status` 规则：

- `missing`
- `needs_review`
- `complete_unverified`
- `partial`

关键结果：

- cfp_missing: 28
- generated_backfill_tasks: 147

解释：

- 当前所有会议年份仍是 `missing`
- 但这是由 CFP 产物驱动计算的 `missing`，不再是硬编码占位

## 5. 方法对比结论

通用写法已统一收口到：`WRITING_NOTES.md` 中的“CFP：template-first 而不是 crawler-first”。

### 5.1 直接爬官网 CFP

优点：

- 自动化程度高

缺点：

- 历史页面不稳定
- 日期文本复杂
- 时区与主会/子会识别容易出错

### 5.2 人工填模板 + 脚本规范化

第一阶段采用。

优点：

- 可控
- 可追溯
- 适合先建立 gold set

缺点：

- 人工成本高

### 5.3 爬虫抽取 + 人工复核

适合作为第二阶段。

优点：

- 在自动化与质量之间折中

缺点：

- 需要 review queue 和冲突解决逻辑

## 6. 后续实验建议

- 比较官方 CFP、重要日期页、聚合站、proceedings 页的覆盖率与准确率
- 比较正则解析、日期解析库、LLM 结构化、规则+人工复核的准确率
- 比较不同 `cfp_status` 阈值对 coverage 与 backfill task 数量的影响
- 论文写作时，优先复用 `WRITING_NOTES.md` 中的“实验对比写法模板”和“消融实验模板”

## 7. 当前结论

CFP 主线已经从“没有独立模块”推进到：

- 独立 CFP skill
- 稳定输入模板与输出 schema
- coverage ledger 状态接入

真实历史 CFP 数据仍需后续填充，但接口与质量报告层已经稳定。
