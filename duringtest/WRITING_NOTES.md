# 论文写作笔记

## 说明

本文件汇总 `duringtest/` 中多次重复出现的方法论总结、论文写作线索、实验对比框架与消融模板。

使用方式：

- 写论文时先从本文件挑选可复用表述
- 再回到对应实验记录补具体数字、命令、案例与边界条件

## 1. 系统设计主线

### 1.1 统一主链路

可复用表述：

- 系统从分散的案例脚本与目录散点，收口为统一 registry、统一 runner、统一输出根目录的主链路。
- 用户入口与内部后端解耦，外部只面向稳定会议 key / group 接口，内部可逐步替换具体抓取实现。
- 这种设计降低了历史兼容负担，也让后续质量审计、标准化、统计与回填自动化可以围绕稳定文件契约协作。

### 1.2 低耦合文件契约

可复用表述：

- 模块间优先通过稳定中间产物协作，而不是直接导入彼此内部逻辑。
- 抽取、标准化、coverage、CFP、author role、统计模块之间通过 CSV / JSON 契约对接，降低了模块替换成本。
- 低耦合设计让局部模块可以独立迭代，同时保持下游接口稳定。

### 1.3 控制面与执行面分离

可复用表述：

- coverage ledger 提供控制面，负责量化缺口、生成待补任务和暴露质量状态。
- backfill runner 提供执行面，负责把任务映射为命令、建立 dry-run 边界，并区分 local / network / manual 执行模式。
- 这种分层使“发现问题”和“执行修复”既可衔接又不混在同一层逻辑中。

## 2. 数据建模主线

### 2.1 source-of-truth 与 reference 边界

可复用表述：

- 论文事实层默认以原始源数据为准，例如 IACR raw 或 DBLP。
- 标准化 reference 更适合承担 alias 映射、canonical metadata 补充、country 保守兜底、规则缺口发现和人工复核支持，而不是直接改写作者身份或论文事实。
- 明确 source-of-truth 与 reference 的边界，可以减少历史案例污染未来年份默认逻辑的风险。

### 2.2 主契约从专题切片回归长表

可复用表述：

- 正式主契约应是作者-机构-国家长表，而不是某个国家子集切片。
- 国家切片是消费层视图，不应反向主导抽取层设计。
- 这一收口减少了 schema 分叉，也让下游国家、机构、作者统计可以共享同一事实表。

### 2.3 事实表优先于分散逻辑

可复用表述：

- 当某种语义会被多个下游模块重复消费时，更稳妥的做法是先建立独立事实表。
- 作者角色是典型例子：与其在多个统计脚本里重复判断一作和通讯作者，不如先生成 `paper_author_roles.csv`。
- 事实表化不仅减少逻辑漂移，也更利于后续引入新来源和人工 override。

## 3. 质量控制与误差分析主线

### 3.1 coverage 作为实验控制层

可复用表述：

- coverage ledger 不是纯工程清单，而是一层实验控制面板。
- 它把“缺 paper metadata、缺 affiliation、缺 CFP、缺 author role、缺官方对账”等问题统一转化为可量化状态。
- 这种控制层让错误不再只体现在失败日志，而能以结构化产物进入后续报告和补齐流程。

### 3.2 最终消费表不等于最佳审计输入

可复用表述：

- 面向用户消费的精简输出不一定适合作为审计输入，因为它可能丢失 `paper_id`、`title`、`classification_*` 等字段。
- 审计层更适合优先使用 expanded interim 表或 audit 表，以保证能和 raw 论文元数据稳定对齐。

### 3.3 expected count 对账

可复用表述：

- 如果没有 official expected paper count，对 raw paper coverage 的判断会与 affiliation 补齐问题混在一起。
- 引入 `expected_papers`、`paper_count_match_status` 与 `paper_count_delta`，可以把“没抓全论文”与“抓全后未补齐机构信息”分开表达。

## 4. 模块化方法主线

### 4.1 作者角色：证据驱动而不是猜测驱动

可复用表述：

- 第一作者可以保守地由作者顺序导出，但通讯作者与共同一作不应默认猜测。
- 对通讯作者这类高语义字段，应保留 `role_source`、`role_evidence`、`confidence`，并优先通过 override 或显式解析器填充。

### 4.2 CFP：template-first 而不是 crawler-first

可复用表述：

- 对历史 CFP 这种异构且时效性强的数据，直接把爬虫当主线风险较高。
- 更稳的路线是先固定 schema、模板、validation report，再逐步引入 crawler 与人工复核。

### 4.3 Backfill：执行安全边界先于自动化程度

可复用表述：

- 回填自动化不应以“一键执行全部任务”为目标，而应先建立 dry-run、network gate、task filtering 与 command dedupe。
- 在质量敏感的数据系统中，安全可控的执行边界往往比更高的自动化覆盖率更重要。

### 4.4 PDF：先下载、后解析

可复用表述：

- PDF 下载层和 PDF 解析层应分开设计，先建立稳定缓存，再单独评估 frontmatter 或全文解析质量。
- 对页面结构较稳定的会议平台，先把论文 PDF 落地为本地审计资产，通常比一开始直接做 PDF 内容解析更稳妥。
- 这种“download-first, parse-later”的策略有助于把下载错误与解析错误解耦。
- 对开放版本覆盖不完整的会议家族，可先通过 DBLP / ePrint 等公开来源补一部分 PDF，而不把“未下载到 PDF”直接等同于系统失败。
- 当引入标题搜索型公开来源时，应只接受归一化后的精确标题匹配，避免把语义相似但并非同一论文的结果误当作有效 PDF 来源。

### 4.5 凭据管理：只走环境变量

可复用表述：

- 任何需要登录态的外部平台接入都不应把账号密码写进仓库或脚本。
- 凭据应只通过环境变量注入，并且不落盘到日志、报告、缓存或中间产物。
- 这可以把“代码可复现性”和“凭据安全性”分离开来。

## 5. 实验对比写法模板

适合复用的结构：

1. 基线方法 A
2. 增强方法 B
3. 参考表 / 新模块 / 新规则介入后的方法 C
4. 用同一分母比较 error rate、unresolved rate、needs_review rate 或 coverage rate
5. 明确“减少了多少绝对值”和“相对减少百分比”
6. 解释收益分别来自哪里

建议句式：

- 与方法 A 相比，方法 B 将 unresolved 从 X 降到 Y，绝对减少 Z， 相对减少约 P%。
- 这一结果表明，泛化规则主要解决了……，而 reference exact match 主要解决了……。

## 6. 消融实验模板

常用消融维度：

- 去掉 reference fallback
- 去掉泛化规则扩充
- 去掉某个保护性解析逻辑
- 关闭网页 affiliation 抓取，仅保留 raw metadata
- 只保留 alias，不保留 canonical name
- 只 dry-run / 只 local execute / local+network execute

常用观察指标：

- unresolved rows
- resolved rate
- needs_review papers
- paper_count mismatch 数量
- top-k 排名是否变化
- `institution_id` 覆盖率
- 人工复核成本

## 7. 单案例实验记录模板

建议每个会议案例都保持以下结构：

1. 目标
2. 输入与参考源
3. 接入或修改内容
4. 执行命令
5. 方法 A / B / C 对比
6. 剩余未解决项
7. 标准化或下游统计结果
8. 残余风险
9. 可继续做的消融实验

## 8. 论文可复用主题线索

- 多源异构数据统一抽取
- source-of-truth 与人工 reference 的边界控制
- 作者-机构-国家长表作为稳定主契约
- 论文级参与国与机构所属国的语义区分
- 从案例脚本到统一 skill / pipeline 的演进
- 低耦合文件契约与可复现自动化
- coverage ledger 作为数据质量控制层
- evidence-driven author role construction
- template-first CFP extraction
- download-first PDF acquisition

## 9. 如何与现有记录联动

- Coverage / completeness / expected count：`COVERAGE_LEDGER_AND_COUNT_RECONCILIATION_2026_05_29.md`
- Author role / override：`AUTHOR_ROLE_PIPELINE_AND_COVERAGE_2026_05_29.md`
- CFP：`CFP_PIPELINE_AND_COVERAGE_2026_05_29.md`
- Backfill：`BACKFILL_RUNNER_AND_DEDUP_2026_05_29.md`
- PDF 下载能力：`PDF_DOWNLOAD_CAPABILITY_2026_05_30.md`
- 单会议高质量案例：`USENIX_SECURITY_2020_REFERENCE_INTEGRATION_2026_05_29.md`
