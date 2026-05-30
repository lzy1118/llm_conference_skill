# Coverage ledger 与官方论文数对账实验记录

## 1. 合并范围

本文件合并以下两份连续记录：

- `COVERAGE_LEDGER_EXPERIMENT_2026_05_29.md`
- `EXPECTED_PAPER_COUNT_RECONCILIATION_2026_05_29.md`

## 2. 主线目标

围绕 coverage 自动化，一共完成两步：

1. 建立统一 coverage ledger 与 backfill task 产物
2. 在 ledger 中加入官方 expected paper count 对账能力

## 3. 阶段一：coverage ledger 自动化

目标：把“历史数据是否齐全”从人工判断改成可执行、可复现的覆盖率产物。

重点覆盖：

- 哪些会议年份缺 raw papers
- 哪些会议年份缺 author affiliation 输出
- 哪些结果仍是旧口径产物
- 哪些论文缺机构、缺国家或缺作者角色
- 后续应该生成哪些 backfill task

新增脚本：

- `conference-analysis-automation/scripts/build_coverage_ledger.py`

生成产物：

- `generated-data/coverage/conference_coverage_ledger.csv`
- `generated-data/coverage/backfill_tasks.csv`
- `generated-data/coverage/paper_completeness_audit.csv`
- `generated-data/coverage/coverage_report.md`

当前结果：

- registered_conference_years: 28
- missing_paper_metadata: 4
- affiliation_needs_work: 25
- cfp_missing: 28
- generated_backfill_tasks: 119
- audited_papers: 3917
- papers_needing_review: 1755

关键收益：

- 从目录散点判断变成 ledger 判断
- 能发现旧口径 validation report 残留
- 论文级 completeness audit 已从“全量误判”修正到可用状态

### 3.1 paper completeness 审计方法对比

方法 A：只用最终输出 CSV 匹配

- 字段少，缺 `paper_id/title`
- 误判率约 100%
- 不适合做论文级 completeness audit

方法 B：优先用 expanded interim CSV 匹配

- 保留 `paper_id/title/classification_*`
- `papers_needing_review` 从 3917 降到 1755
- 粗略误判减少 2162 篇
- 当前最适合作为 coverage audit 输入

方法 C：加入 source-level official count 校验

- 当时尚未实现
- 这一能力在阶段二补上

## 4. 阶段二：expected paper count 对账

目标：在 coverage ledger 中补入官方论文数对账能力，用于区分：

1. 论文列表本身是否抓全
2. 抓全后作者机构、国家、角色等下游信息是否补全

新增输入：

- `--expected-counts generated-data/coverage/expected_paper_counts.csv`

新增输出：

- `generated-data/coverage/expected_paper_counts_template.csv`

新增 ledger 字段：

- `expected_papers`
- `paper_count_match_status`
- `paper_count_delta`

状态定义：

- `missing_expected_count`
- `matches_expected`
- `count_mismatch`

当前结果：

- registered_conference_years: 28
- missing_expected_paper_counts: 28
- paper_count_mismatches: 0
- generated_backfill_tasks: 147

解释：

- 当前还没有正式填写 expected count
- 但模板和对账字段已经接入
- backfill task 已能自动生成 `add_expected_paper_count` 与 `verify_paper_count`

## 5. 方法对比结论

通用写法与消融框架已统一收口到：`WRITING_NOTES.md`。

### 5.1 不做 expected count 对账

优点：

- 实现简单

缺点：

- 无法判断 raw papers 是否完整
- 容易把 paper metadata 缺失误认为 affiliation 解析缺失

### 5.2 手工在报告里记录官方数量

优点：

- 快速

缺点：

- 无法被脚本消费
- 无法自动生成 backfill task

### 5.3 CSV 驱动 expected count 对账

当前采用。

优点：

- 可被 coverage ledger 消费
- 可追加 source URL 与 notes
- 可自动生成 mismatch 任务

缺点：

- 需要人工或后续 crawler 填官方来源
- 不同官方来源可能存在口径差异

## 6. 后续实验建议

- 比较 IACR 页面、DBLP、Springer/ACM/IEEE proceedings、会议官网 accepted list 的 expected count 一致率
- 当出现 `count_mismatch` 时，比较 raw 抓取失败、schema 过滤、workshop/demo 混入、DBLP 与官网口径差异等不同归因策略
- 比较 expected count 缺失时不同 task priority 方案对 backfill 效率的影响
- 论文写作时，优先套用 `WRITING_NOTES.md` 中的“质量控制与误差分析主线”与“实验对比写法模板”

## 7. 当前结论

coverage 主线已经从“人工看目录”推进到：

- 统一 ledger 产物
- 论文级 completeness audit
- 自动 backfill task 生成
- official expected count 对账接口

后续只要继续填充 `expected_paper_counts.csv`，coverage 系统就能把“抓没抓到论文”和“抓到后下游补没补齐”分开表达。
