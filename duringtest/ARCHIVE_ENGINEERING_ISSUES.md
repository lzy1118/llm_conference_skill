# 工程问题归档

## 说明

本文件归档测试期间偏工程系统侧的问题：主链路收口、目录与产物治理、接口稳定性、执行安全边界、历史兼容清理。

## 1. 主链路与目录收口

核心问题：

- 早期存在 `Top3-data/`、`Security-data/`、根目录 `data/` 等多条并行路径
- raw / interim / output / resolution 散落，主输出难以判断

处理结论：

- 主抽取入口统一为 `conference-paper-extraction/scripts/run_unified_pipeline.py`
- 主产物目录统一到 `generated-data/`

相关记录：

- `ARCHIVE_ISSUES_AND_SOLUTIONS.md`
- `REDUNDANT_FILE_DEDUP_CONSOLIDATED_2026_05_29.md`

## 2. 美国布尔字段与旧口径移除

核心问题：

- 旧流程同时保留 `country` 与美国布尔字段，导致 schema 漂移和口径重复

处理结论：

- 当前主线只保留 `country`
- 美国统计改为下游切片，而不是抽取层主契约

相关记录：

- `REMOVE_IS_US_INSTITUTION_2026_05_29.md`

## 3. 冗余文件、空目录、伪汇总副本清理

核心问题：

- 历史专题切片、空占位、单会议伪汇总、副本文件混杂在主工作区

处理结论：

- 已完成多轮安全清理
- 当前 `data/` 已不再承担机构 reference 主存储职责
- `generated-data/` 中伪汇总、副本、空壳已大幅收缩

相关记录：

- `REDUNDANT_FILE_DEDUP_CONSOLIDATED_2026_05_29.md`

## 4. Coverage / Backfill 自动化接口设计

核心问题：

- coverage 之前依赖人工看目录
- backfill task 之前是静态表，无法稳定执行

处理结论：

- 已建立 coverage ledger、paper completeness audit、backfill task 生成
- 已建立 backfill runner，区分 local / network / manual，并默认 dry-run
- 已加入 command-level 去重，避免全局任务重复执行

相关记录：

- `COVERAGE_LEDGER_AND_COUNT_RECONCILIATION_2026_05_29.md`
- `BACKFILL_RUNNER_AND_DEDUP_2026_05_29.md`

## 5. 低耦合集成原则

当前稳定原则：

- 新模块尽量通过 CSV / JSON 文件契约接入，而不是互相直接导入内部逻辑
- 覆盖率、CFP、作者角色、标准化尽量靠稳定中间产物协作

这条原则已经在以下主线中反复验证：

- coverage ledger 接 CFP 输出
- coverage ledger 接 author roles 输出
- 标准化层接 `conference-dataset-normalization/references/`

## 6. 当前工程侧建议

- 后续新增系统级记录优先追加到 consolidated 文档，而不是再按 round 拆文件
- 若再做清理，继续优先删除“空文件 / 伪汇总 / 单会议副本”，避免误伤正式产物
- 新的自动化能力优先走文件契约，保持低耦合
