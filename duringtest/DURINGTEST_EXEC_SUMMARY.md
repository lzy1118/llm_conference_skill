# duringtest 归纳总览

## 说明

本文件把 `duringtest/` 中的测试记录收口成一份执行摘要，方便快速回答三类问题：

- 这个目录主要记录了什么
- 哪些结论已经进入当前主线
- 如果后续要追溯细节，应该先看哪一类记录

当前目录只保留归纳文档，因此本文件已经吸收了原始记录中的关键问题、处理结论、指标结果与后续建议，目的是在不保留历史分散文件的前提下，尽量保住可复用信息。

## 一、目录整体可分为五条主线

### 1. 主链路与工程治理

这条线关注系统如何从分散脚本和散乱目录，收口为统一入口、统一契约、统一产物目录。

核心结论：

- 主抽取入口收口到 `conference-paper-extraction/scripts/run_unified_pipeline.py`
- 主结果目录收口到 `generated-data/`

工程治理侧的具体收口包括：

- 早期并行路径如 `Top3-data/`、`Security-data/`、根目录 `data/` 被弱化，主线统一转向 `generated-data/`
- raw / interim / output / resolution 的主路径含义被重新约束，减少“哪个才是正式结果”的歧义
- coverage 和 backfill 不再依赖人工看目录，而是有统一产物和状态字段

与旧口径清理直接相关的结论：

- 将标准化层国家推断改为只接收机构文本


### 2. 数据质量与会议级案例修复

这条线关注 source-of-truth、reference 接入边界、历史 schema 异构、单会议数据修补与国家归属质量。

核心结论：

- 默认 source of truth 仍以 `IACR raw / DBLP` 为主
- reference 的定位是 alias、canonical metadata、country fallback 和规则缺口补齐
- 三大密码会历史 schema 差异需要局部 parser 兼容，而不是重写统一入口
- `USENIX Security` 和 `CCS` 的关键问题更多出在具体来源与 fallback 策略，而不是主框架本身

数据侧的重要边界判断是：

- `IACR raw / DBLP` 负责论文事实层

三大密码会 `2020-2025` 的 accepted papers 补齐采用“最小改动”策略：

1. 仅补 `conference_registry.py`
2. 仅补 `iacr_top3_backend.py`
3. 不改 unified runner 接口
4. 不改下游标准化、统计、分析 skills

这条线的关键价值是把 Top3 的历史年份扩展理解为 registry / backend 配置问题，而不是重新设计整条 pipeline。

`USENIX Security 2020` 是最完整的单案例修复样板：

- 抽取层接入泛化规则
- 修复 `and` 错拆机构名
- 接入 `institution_aliases.csv` 与 `institution_registry.csv` 作为 exact alias / registry fallback
- 标准化层新增 `institution_id`、`canonical_institution_name`、`region`、`type`

该案例的关键指标变化：

- 方法 A 原始流程：`unresolved = 89 / 754 = 11.80%`
- 方法 B 增强泛化规则：`unresolved = 16 / 754 = 2.12%`
- 方法 C 泛化规则 + reference fallback：`unresolved = 6 / 754 = 0.80%`

标准化验证结果显示：

- `rows_with_reference_institution_id = 425`
- `rows_with_unknown_country = 0`

`USENIX Security 2022` 则更像端到端流程健康检查：

- `papers_count = 256`
- `papers_with_author_rows = 256`
- `expanded_author_rows = 1261`
- `classified_author_rows = 1245`
- `unresolved_country_rows = 16`
- 标准化后 `rows_with_unknown_country = 0`
- 国家、机构、作者统计脚本均跑通

`CCS OpenAlex DOI Ablation` 的关键实验结论是：

- `OpenAlex DOI lookup` 应该优先于 `title search`
- 空 affiliation 缓存不能阻断重新联网

各年份提升最明显的是：

- `CCS 2022`: `papers_with_author_rows 89 -> 279`
- `CCS 2024`: `0 -> 404`
- `CCS 2025`: `0 -> 387`

### 3. 覆盖率、回填与控制面

这条线关注如何把“哪里缺数据、哪里要补跑、哪里要人工处理”从经验判断变成可执行的控制面。

核心结论：

- coverage ledger 是当前数据主线的重要控制层
- 它统一暴露 paper metadata、affiliation、CFP、author role、官方论文数对账等缺口
- backfill runner 负责把 `backfill_tasks.csv` 转成可执行计划，并显式区分 dry-run、local、network、manual 边界

coverage ledger 阶段一的关键产物是：

- `conference_coverage_ledger.csv`
- `backfill_tasks.csv`
- `paper_completeness_audit.csv`
- `coverage_report.md`

当时阶段一结果：

- `registered_conference_years = 28`
- `missing_paper_metadata = 4`
- `affiliation_needs_work = 25`
- `cfp_missing = 28`
- `generated_backfill_tasks = 119`
- `audited_papers = 3917`
- `papers_needing_review = 1755`

paper completeness 审计方法比较中，重要方法判断是：

- 只靠最终输出 CSV 基本不适合作为论文级 audit 输入
- expanded interim CSV 更适合做 completeness audit
- needs_review 从 `3917` 降到 `1755`

阶段二增加了 official expected count 对账接口，新增：

- `expected_papers`
- `paper_count_match_status`
- `paper_count_delta`

同时生成 `expected_paper_counts_template.csv`，让系统能区分：

1. 论文列表本身是否抓全
2. 抓全后 affiliation / country / role 是否补齐

backfill runner 的核心推进是：

- 从静态任务表进入执行计划层
- 默认 dry-run
- 默认不执行 network
- 支持 `local / network / manual` 分类
- 加入 command-level 去重

两阶段的代表性结果：

- 阶段一：`selected_tasks = 12`，`runnable_tasks = 4`，`executed_tasks = 0`
- 阶段二：`selected_tasks = 10`，`duplicate_tasks = 8`，`executed_tasks = 2`

实际安全验证通过的 local 任务：

1. `extract_author_roles`
2. `extract_cfp`

### 4. 扩展能力模块

这条线关注主链路之外，但已经形成独立模块边界的能力。

核心结论：

- 作者角色被独立成事实表与独立 skill，当前稳定支持第一作者和参与作者
- CFP 采用 template-first 路径，先固定 schema、模板、validation，再考虑更自动化的抓取
- PDF 下载已经进入统一入口，但当前定位仍是“下载能力”而不是“PDF 解析主线”

作者角色模块完成了三步：

1. 建立最小角色事实表
2. 把角色状态接入 coverage ledger
3. 为通讯作者与共同一作预留 override 入口

当前作者角色侧的稳定能力：

- 第一作者
- 参与作者

保守不自动猜测的字段：

- 通讯作者
- equal contribution

阶段性结果曾记录为：

- `input_rows = 7419`
- `role_rows = 5992`
- `papers = 1359`
- `first_author_rows = 1315`
- `corresponding_author_rows = 0`
- `equal_contribution_rows = 0`

CFP 模块的阶段判断非常明确：

- 第一阶段不是抓满历史 CFP
- 而是先固定 skill 边界、schema、模板、validation report

当前 CFP 侧产物包括：

- `cfp_events_template.csv`
- `conference_edition_template.csv`
- `conference_events.csv`
- `conference_edition_metadata.csv`
- `cfp_validation_report.json`
- `cfp_report.md`

模板阶段的典型结果：

- `registered_conference_years = 28`
- `event_rows = 0`
- `edition_rows = 0`
- `missing_event_conference_years = 28`

PDF 下载能力的定位是“download-first, parse-later”。

对安全会，下载能力已经比较稳定：

- `USENIX Security 2020`: `157 / 159 = 98.74%`
- `USENIX Security 2022`: `256 / 256 = 100%`
- `USENIX Security 2023`: `422 / 422 = 100%`
- `USENIX Security 2025`: `437 / 439 = 99.54%`
- `NDSS 2025`: `211 / 211 = 100%`

对 `IEEE S&P 2025` 与 `CCS 2025`，当前轻量实现仍几乎抓不到 PDF，主要原因不是统一入口失效，而是平台落地页没有稳定公开 PDF 直链。

对三大密码会，当前能力更像“公开版本补充层”，不是 proceedings 完整镜像：

- `asiacrypt_2025`: `5 / 143 = 3.50%`
- `crypto_2025`: `6 / 156 = 3.85%`
- `eurocrypt_2025`: `1 / 123 = 0.81%`

### 5. 论文写作与方法论沉淀

这条线关注如何把工程和实验工作转成论文中的系统设计、方法选择和实验表达。

核心结论：

- 已经沉淀出统一主链路、低耦合文件契约、控制面与执行面分离等可复用写作表述
- `duringtest/` 里的很多实验记录适合作为论文中的案例、消融、设计动机和边界条件来源

当前已经沉淀出的论文主线主要包括：

- 统一主链路
- 低耦合文件契约
- 控制面与执行面分离
- source-of-truth 与 reference 的边界
- 专题切片回归长表主契约
- 事实表优先于分散逻辑
- coverage 作为实验控制层
- evidence-driven author role construction
- template-first CFP extraction
- download-first PDF acquisition

常用写作模板也已经在原记录中稳定下来，例如：

1. 基线方法 A
2. 增强方法 B
3. 参考表 / 新模块 / 新规则介入后的方法 C
4. 用同一分母比较 unresolved、needs_review、coverage 或 error rate
5. 同时写清绝对减少量与相对减少比例

适合作为论文方法或实验章节的主题包括：

- 多源异构数据统一抽取
- 作者-机构-国家长表作为稳定主契约
- coverage ledger 作为数据质量控制层
- author role 的证据驱动构造
- CFP template-first 路径
- backfill 的安全执行边界


## 三、目前最值得优先保留的有效结论

如果只关心“哪些结论已经进入当前项目主线”，优先关注这些：

1. 主输出目录统一为 `generated-data/`
2. 主数据口径统一为“作者-机构-国家”长表，只保留 `country`
3. coverage ledger 已成为主控制面
4. backfill、author role、CFP 已形成相对独立的模块边界
5. 单会议问题优先通过局部 backend / fallback / reference 修复，而不是推翻统一主链路



## 五、后续记录建议

如果后续仍然在 `duringtest/` 补记录，建议继续保持“先归纳、再沉淀”的方式。推荐模板是：

1. 目标
2. 影响范围
3. 问题现象
4. 复现条件
5. 原因判断
6. 解决对策
7. 执行步骤
8. 结果
9. 边界与残余风险
10. 对论文写作的价值

如果是同一主题连续推进，优先继续并入现有归纳文档，而不是重新拆出 round 文件。

## 六、建议把 duringtest 理解成什么

更准确地说，`duringtest/` 不是普通临时文件夹，而是：

- 主线能力形成过程的实验档案
- 关键设计取舍与问题修复记录
- 论文写作与实验复现的素材库

如果后续还要继续收口，可以把新记录优先并入现有主题归档，而不是继续增加大量平行单文件。
