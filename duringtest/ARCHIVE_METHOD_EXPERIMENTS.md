# 方法与实验设计归档

## 说明

本文件归档测试期间偏方法论与实验设计的问题：coverage 评估、作者角色设计、CFP 建模、消融实验方向、论文写作可复用线索。

## 1. Coverage 作为实验控制层

核心方法结论：

- coverage ledger 不只是工程辅助工具，也是一层实验控制面板
- 它能把“缺 paper metadata / 缺 affiliation / 缺 CFP / 缺 author role / 需要官方对账”统一量化出来

相关记录：

- `COVERAGE_LEDGER_AND_COUNT_RECONCILIATION_2026_05_29.md`

## 2. 作者角色模块化

核心方法结论：

- 作者角色应独立成事实表，而不是散落在作者统计或机构统计脚本里
- 通讯作者和共同一作必须证据驱动，不能默认猜测

相关记录：

- `AUTHOR_ROLE_PIPELINE_AND_COVERAGE_2026_05_29.md`

适合延伸的消融：

- 直接从长表统计一作 vs 从角色事实表统计一作
- 通讯作者候选策略对比：最后作者、PDF 标记、HTML metadata、人工 override

## 3. CFP 采用 template-first 路径

核心方法结论：

- CFP 不宜一开始就把网络爬虫当主线
- 更稳的路线是先固定 schema、模板、validation report，再引入 crawler

相关记录：

- `CFP_PIPELINE_AND_COVERAGE_2026_05_29.md`

适合延伸的消融：

- 官方 CFP 页、重要日期页、聚合站、proceedings 页的覆盖率对比
- 正则解析、日期解析库、LLM 结构化、规则+人工复核的准确率对比

## 4. Backfill 作为安全实验执行层

核心方法结论：

- 不应直接自动执行所有待补任务
- 更适合采用 dry-run plan + 显式 execute + network gate + command dedupe 的分层执行设计

相关记录：

- `BACKFILL_RUNNER_AND_DEDUP_2026_05_29.md`

适合延伸的消融：

- 只 dry-run / 只执行 local / 执行 local+network
- command-level 去重 / task-type 去重 / 不去重

## 5. 单会议案例方法模板

当前较成熟的案例模板已经体现在：

- `USENIX_SECURITY_2020_REFERENCE_INTEGRATION_2026_05_29.md`

建议后续案例继续保留这些部分：

- 基线结果
- 方法 A / B / C 对比
- unresolved 或 error rate 变化
- 剩余边界
- 可直接复用的消融实验设计

## 6. 论文写作可复用主题

这些共性主题已统一收口到：

- `WRITING_NOTES.md`

## 7. 当前方法侧建议

- 后续新增实验记录优先写明：基线、改法、对比、误差、边界、消融
- 同一主题多次推进时直接追加 consolidated 文档，避免 round 文件重新膨胀
- 需要写论文时，优先先读 `WRITING_NOTES.md`，再回到对应案例补数字和边界条件
