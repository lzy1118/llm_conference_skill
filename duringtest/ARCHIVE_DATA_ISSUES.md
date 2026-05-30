# 数据问题归档

## 说明

本文件归档测试期间偏数据侧的问题：源数据异构、reference 使用边界、论文数对账、国家与机构映射质量、单会议案例修复。

## 1. source-of-truth 与 reference 的边界

核心问题：

- 容易把 `reference` 验证材料误写成默认业务规则
- 可能让历史案例污染未来年份的默认逻辑

处理结论：

- 默认 source of truth 仍是 `IACR raw / DBLP`
- 标准化 reference 主要用于 alias 映射、canonical metadata 补充、country fallback、规则缺口发现

相关记录：

- `USENIX_SECURITY_2020_REFERENCE_INTEGRATION_2026_05_29.md`
- `ARCHIVE_ISSUES_AND_SOLUTIONS.md`

## 2. 三大密码会 2020 历史 schema 异构

核心问题：

- `ASIACRYPT 2020`、`EUROCRYPT 2020` 存在历史 JSON schema 差异
- raw JSON 抓到后不代表能顺利展开作者-机构行

处理结论：

- 对 `iacr_top3_backend.py` 做局部 parser 兼容修复
- 不改 unified runner 与下游接口

主要收益：

- `expanded_author_rows`、`classified_author_rows` 明显提升
- mismatch issue 数量下降

相关记录：

- `EXPERIMENT_LOG_TOP3_2020_2025.md`

## 3. 论文数 completeness 与 expected count 对账

核心问题：

- 没有 official expected paper count 时，无法区分“paper list 没抓全”和“后续机构解析不完整”

处理结论：

- 已建立 `expected_papers / paper_count_match_status / paper_count_delta` 字段
- 当前仍需后续逐项填充官方计数来源

相关记录：

- `COVERAGE_LEDGER_AND_COUNT_RECONCILIATION_2026_05_29.md`

## 4. 单会议案例：USENIX Security 2020

核心问题：

- 初始 unresolved 比例较高
- 当时机构 reference 虽已存在，但未真正接入抽取与标准化链路

处理结论：

- 抽取层接入泛化规则 + `conference-dataset-normalization/references/` 标准化 reference fallback
- 标准化层补 `institution_id / canonical_name / region / type`

结果：

- unresolved rate 从 11.80% 降到 0.80%
- 标准化后大量行成功挂上 `institution_id`

相关记录：

- `USENIX_SECURITY_2020_REFERENCE_INTEGRATION_2026_05_29.md`

## 5. 单会议案例：USENIX Security 2022

核心问题：

- 需要验证当前统一流程在移除旧口径后是否仍可端到端执行

处理结论：

- 抽取、标准化、国家/机构/作者统计链路均可顺利跑通

相关记录：

- `USENIX_SECURITY_2022_FLOW_CHECK_2026_05_29.md`

## 6. 当前数据侧建议

- 后续优先继续完善 `conference-dataset-normalization/references/`，不要把所有机构问题写死到规则中
- 新会议案例优先记录“基线错误率 / 方法对比 / 消融建议”三部分
- 对 `Unknown` 或歧义机构保持保守，不要用不稳定品牌名强行猜国家
