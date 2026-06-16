# duringtest 文件归类清单

## 说明

本文件把历史 `duringtest/` 文件的主要内容、关键结论、重要指标与论文可复用点收口成一张清单。
现在历史分散文件已经删除，因此这里不仅是导航，也承担“文件级内容摘录”的作用。

## 一、现存文件

| 文件 | 角色 | 作用 |
|---|---|---|
| `DURINGTEST_EXEC_SUMMARY.md` | 总览 | 按主线汇总 duringtest 全局内容 |
| `DURINGTEST_RECORD_MAP.md` | 清单 | 按历史文件来源重组内容与用途 |

## 二、原总入口与模板的内容收口

### 1. `ARCHIVE_ISSUES_AND_SOLUTIONS.md`

- 原角色：总归档入口
- 核心内容：把问题分为工程、数据、方法三类，提醒新增内容优先写入分类归档
- 现在如何保留：已并入 `DURINGTEST_EXEC_SUMMARY.md` 的结构总览

### 2. `DURINGTEST_INDEX.md`

- 原角色：目录索引
- 核心内容：说明哪些文件是总览、哪些是系统级记录、哪些是会议案例
- 现在如何保留：已被本文件的结构替代

### 3. `ARCHIVE_FUTURE_TEMPLATE.md`

- 原角色：后续问题记录模板
- 关键字段：
  - 日期 / 任务主题 / 会议年份 / 影响范围
  - 问题现象 / 复现条件 / 原因判断 / 解决对策
  - 操作步骤 / 结果 / 性能对比 / 论文价值 / 证据
- 现在如何保留：已提炼进 `DURINGTEST_EXEC_SUMMARY.md` 的“后续记录建议”

## 三、原分类归档的内容收口

### 1. 工程归档

来源：`ARCHIVE_ENGINEERING_ISSUES.md`

保留下来的核心内容：

- 主抽取入口统一到 `run_unified_pipeline.py`
- 主产物目录统一到 `generated-data/`
- 美国布尔字段与旧口径移除，主线只保留 `country`
- coverage / backfill 从人工目录判断升级为结构化自动化产物
- 模块接入优先走 CSV / JSON 文件契约，而不是内部直接耦合

### 2. 数据归档

来源：`ARCHIVE_DATA_ISSUES.md`

保留下来的核心内容：

- `IACR raw / DBLP` 与 reference 的边界
- Top3 历史 schema 异构需要局部 parser 修复
- expected paper count 对账的必要性
- `USENIX 2020` 作为高质量单案例
- `USENIX 2022` 作为端到端流程验证案例

### 3. 方法归档

来源：`ARCHIVE_METHOD_EXPERIMENTS.md`

保留下来的核心内容：

- coverage ledger 是实验控制层
- 作者角色应独立成事实表
- CFP 更适合 template-first
- backfill 更适合 dry-run + execute + network gate + dedupe
- 单会议案例应写成“基线 / 改法 / 对比 / 边界 / 消融”

### 4. 写作笔记

来源：`WRITING_NOTES.md`

保留下来的核心内容：

- 统一主链路、低耦合文件契约、控制面与执行面分离
- source-of-truth 与 reference 边界
- 长表主契约优先于国家专题切片
- 事实表优先于分散逻辑
- coverage、author role、CFP、backfill、PDF 的论文化表述
- 实验对比模板和消融模板

## 四、原系统级主线记录的内容收口

### 1. coverage 与对账

来源：`COVERAGE_LEDGER_AND_COUNT_RECONCILIATION_2026_05_29.md`

关键产物：

- `conference_coverage_ledger.csv`
- `backfill_tasks.csv`
- `paper_completeness_audit.csv`
- `coverage_report.md`
- `expected_paper_counts_template.csv`

关键指标：

- `registered_conference_years = 28`
- `missing_paper_metadata = 4`
- `affiliation_needs_work = 25`
- `generated_backfill_tasks = 119`
- `papers_needing_review = 1755`

关键判断：

- expanded interim 表比最终消费 CSV 更适合作为 completeness audit 输入
- expected count 可以把“没抓全论文”和“抓全后没补齐 affiliation”分开表达

论文可复用点：

- coverage 作为控制层
- expected count 对账作为误差分析层
- audit 输入表选择对误判率有决定性影响

### 2. backfill 与去重

来源：`BACKFILL_RUNNER_AND_DEDUP_2026_05_29.md`

关键产物：

- `generated-data/backfill/backfill_plan.json`
- `generated-data/backfill/backfill_plan.md`

关键结果：

- dry-run 阶段：`selected_tasks = 12`，`runnable_tasks = 4`
- execute 阶段：`selected_tasks = 10`，`duplicate_tasks = 8`，`executed_tasks = 2`

关键判断：

- 不应默认自动执行全部待补任务
- command-level dedupe 足够简单，也足够实用
- 更合理的是 `dry-run plan + 显式 execute`

论文可复用点：

- 控制面与执行面分离
- 安全边界先于自动化程度

### 3. 作者角色

来源：`AUTHOR_ROLE_PIPELINE_AND_COVERAGE_2026_05_29.md`

关键产物：

- `paper_author_roles.csv`
- `author_role_report.json`
- `author_role_report.md`
- `author_role_overrides_template.csv`

关键结果：

- 第一作者和参与作者稳定可用
- `corresponding_author_rows = 0`
- `equal_contribution_rows = 0`

关键判断：

- 通讯作者与共同一作不能默认猜
- 一人一论文一行的角色事实表优于在多个统计脚本里重复判断

论文可复用点：

- evidence-driven author role construction
- facts first, heuristics second

### 4. CFP

来源：`CFP_PIPELINE_AND_COVERAGE_2026_05_29.md`

关键产物：

- `cfp_events_template.csv`
- `conference_edition_template.csv`
- `conference_events.csv`
- `conference_edition_metadata.csv`
- `cfp_validation_report.json`

关键结果：

- 当前仍是 template-first 阶段
- `event_rows = 0`
- `edition_rows = 0`
- 但 `cfp_status` 已能进入 coverage ledger

关键判断：

- 直接 crawler-first 风险太高
- 应先建立 gold set 和 review-friendly 的结构化出口

论文可复用点：

- template-first CFP extraction
- 异构历史网页数据的渐进式结构化

### 5. PDF 下载

来源：`PDF_DOWNLOAD_CAPABILITY_2026_05_30.md`

关键接口：

- `--download-pdfs`
- `--pdf-limit`

关键结果：

- `USENIX 2020`: `98.74%`
- `USENIX 2022`: `100%`
- `USENIX 2023`: `100%`
- `USENIX 2025`: `99.54%`
- `NDSS 2025`: `100%`
- `IEEE S&P 2025`: `0%`
- `CCS 2025`: `0%`
- Top3 密码会整体覆盖很低，定位应是“公开版本补充层”

关键判断：

- download-first, parse-later
- 对不同会议家族，公开 PDF 可得性差异极大

论文可复用点：

- 下载层与解析层解耦
- 开放版本覆盖率本身可作为局限性讨论

### 6. 旧口径清理

来源：`REMOVE_IS_US_INSTITUTION_2026_05_29.md`

关键动作：

- 删除美国布尔字段、旧输出列、`--us-only`、旧辅助脚本
- coverage 与文档层同步收口到 `country`

关键判断：

- 国家专题切片不应反向主导抽取层契约

论文可复用点：

- 从专题切片回归通用长表契约
- 简化 schema 可降低维护成本和口径分裂

### 7. 冗余文件清理

来源：`REDUNDANT_FILE_DEDUP_CONSOLIDATED_2026_05_29.md`

关键动作：

- 删除美国 / 中国专题切片
- 清理旧 `data/` 抽取残留
- 删除 `*-check` 空壳
- 删除伪汇总副本、空 resolution 占位、只有表头的队列副本

关键判断：

- 清理对象优先级应是：空文件、空目录、伪汇总、副本、旧专题切片

论文可复用点：

- 主线数据出口治理
- 结果目录语义清晰化

## 五、原会议与数据案例记录的内容收口

### 1. Top3 2020-2025

来源：`EXPERIMENT_LOG_TOP3_2020_2025.md`

关键内容：

- 补齐 `ASIACRYPT / CRYPTO / EUROCRYPT` 的 `2020-2025` conference keys
- 采用最小改动策略，不改 unified runner 和下游接口
- 把问题定义为 registry / backend 扩展，而不是重写主线

论文可复用点：

- minimal perturbation strategy
- 历史年份扩展的工程风险控制

### 2. USENIX Security 2020

来源：`USENIX_SECURITY_2020_REFERENCE_INTEGRATION_2026_05_29.md`

关键结果：

- unresolved 从 `11.80%` 降到 `0.80%`
- `rows_with_reference_institution_id = 425`
- `rows_with_unknown_country = 0`

关键判断：

- 泛化规则解决大头
- reference fallback 解决 exact alias / registry 类问题
- `None`、`Unaffiliated`、强歧义机构应保守留 `Unknown`

论文可复用点：

- 规则增强与 reference fallback 的分工
- 单会议案例的多方法对比写法

### 3. USENIX Security 2022

来源：`USENIX_SECURITY_2022_FLOW_CHECK_2026_05_29.md`

关键结果：

- 抽取、标准化、国家/机构/作者统计全链路通过
- `papers_count = 256`
- `rows_with_unknown_country = 0`

关键判断：

- 新口径在移除旧美国布尔字段后仍可端到端运行

论文可复用点：

- 兼容性验证
- 主线改造后的健康检查

### 4. CCS OpenAlex DOI Ablation

来源：`CCS_OPENALEX_DOI_ABLATION_2026_06_03.md`

关键结果：

- `CCS 2024`: `papers_with_author_rows 0 -> 404`
- `CCS 2025`: `0 -> 387`
- `CCS 2022`: `89 -> 279`

关键判断：

- DOI lookup 明显优于 title search
- 空缓存不能阻断后续重试

论文可复用点：

- 数据源入口消融
- 缓存策略本身会显著影响覆盖率

## 六、推荐阅读路径

### 快速了解目录

1. `DURINGTEST_EXEC_SUMMARY.md`
2. `DURINGTEST_RECORD_MAP.md`

### 快速了解主线形成过程

1. 先看 `DURINGTEST_EXEC_SUMMARY.md` 的五条主线
2. 再看本文件第三、四、五部分的详细摘录

### 快速提取论文素材

1. 本文件第三、四、五部分中的“论文可复用点”
2. 再回看 `DURINGTEST_EXEC_SUMMARY.md` 的方法论归纳

## 七、后续维护建议

- 新增记录时，优先判断是否能并入现有主题归档
- 只有实验对象独立、研究价值明确时，再保留单独文件
- `DURINGTEST_EXEC_SUMMARY.md` 负责主题收口
- `DURINGTEST_RECORD_MAP.md` 负责文件导航
