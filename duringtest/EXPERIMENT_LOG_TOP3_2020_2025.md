# 三大密码会 2020-2025 accepted papers 补齐实验记录

## 1. 实验目标

目标是在现有 skills 做最小改动的前提下，补齐三大密码会 `ASIACRYPT / CRYPTO / EUROCRYPT` 在 `2020-2025` 的 accepted papers 抽取能力，并记录：

- 配置扩展过程
- 实际运行结果
- 遇到的问题
- 解决方案
- 不同方式的风险和错误率比较
- 后续可用于论文的消融实验思路

## 2. 当前实验设计

### 2.1 设计原则

本轮采用“最小改动”方案：

1. 仅补 `conference_registry.py`
2. 仅补 `iacr_top3_backend.py`
3. 不改 unified runner 接口
4. 不改下游标准化、统计、分析 skills

### 2.2 核心假设

对三大密码会 accepted papers 抓取而言，主要依赖 IACR JSON：

- `https://asiacrypt.iacr.org/<year>/json/papers.json`
- `https://crypto.iacr.org/<year>/json/papers.json`
- `https://eurocrypt.iacr.org/<year>/json/papers.json`

因此该任务本质上更接近：

- registry 扩展问题
- 年份 URL 有效性问题
- 实际抓取稳定性问题

而不是复杂的 affiliation 解析问题。

## 3. 已完成的改动

### 3.1 新增年份配置

已补齐以下 18 个 key：

- `asiacrypt_2020`
- `asiacrypt_2021`
- `asiacrypt_2022`
- `asiacrypt_2023`
- `asiacrypt_2024`
- `asiacrypt_2025`
- `crypto_2020`
- `crypto_2021`
- `crypto_2022`
- `crypto_2023`
- `crypto_2024`
- `crypto_2025`
- `eurocrypt_2020`
- `eurocrypt_2021`
- `eurocrypt_2022`
- `eurocrypt_2023`
- `eurocrypt_2024`
- `eurocrypt_2025`

### 3.2 修改文件

- `conference-paper-extraction/scripts/iacr_top3_backend.py`
- `conference-paper-extraction/scripts/conference_registry.py`
- `tests/test_conference_extraction_unified.py`

### 3.3 已完成验证

已通过：

- `python3 -m unittest tests.test_conference_extraction_unified -v`
- `python3 -m unittest tests.test_conference_extraction_backends -v`

## 4. 当前实验步骤记录

### 步骤 A：静态配置扩展

状态：已完成

内容：

1. 在 backend 中补 ConferenceConfig
2. 在 registry 中补 RegisteredConference
3. 更新 `top3_crypto` 分组

结果：

- `--list-conferences` 已能列出历史年份
- `top3_crypto` 已覆盖 2020-2025

### 步骤 B：dry run 验证

状态：待执行

目标：

验证 unified runner 在不联网情况下能否正确构造 18 个会议的执行计划。

计划命令：

```bash
python3 conference-paper-extraction/scripts/run_unified_pipeline.py \
  --group top3_crypto \
  --output-dir generated-data/extraction \
  --dry-run
```

### 步骤 C：实际抓取

状态：待执行

目标：

实际抓取 `2020-2025` 三大会 raw papers，并观察：

- 哪些年份 URL 正常
- 哪些年份抓取失败
- 是否有结构差异
- validation report 是否完整生成

计划命令：

```bash
python3 conference-paper-extraction/scripts/run_unified_pipeline.py \
  --group top3_crypto \
  --output-dir generated-data/extraction
```

## 5. 问题记录区

### 5.1 预期可能问题

1. 个别历史年份 JSON 路径不存在
2. 个别年份 JSON 结构字段变化
3. 历史年份 acceptedPapers 字段为空或不同名
4. 年份网页可访问但 JSON 返回异常
5. 抓取成功但 validation report 中 `papers_count = 0`

### 5.2 本轮重点观察指标

每个年份至少记录：

1. raw JSON 是否落盘
2. validation report 是否生成
3. `papers_count`
4. 是否出现 mismatch queue
5. 是否出现 `Unknown` / unresolved 明显异常偏高

## 6. 不同方式对比框架

论文中可把 accepted papers 补齐方式对比为三类：

### 6.1 方式一：仅补 registry + backend 配置

优点：

- 改动最小
- 不影响下游分析
- 最符合工程最小扰动原则

风险：

- 如果历史 URL 或 JSON 结构变动，仍需要逐年验证

预期错误率：

- 对 accepted papers 列表任务应最低
- 主要错误来自外部源失效，而非内部逻辑

### 6.2 方式二：引入 `family + year` 泛化入口

优点：

- 用户体验更好
- 减少显式 conference key 注册成本

风险：

- 需要改 CLI 和路由逻辑
- 更适合后续产品化，而不是当前最小改动

预期错误率：

- 不一定降低源数据错误率
- 但会增加入口层逻辑复杂度

### 6.3 方式三：完全动态探测历史年份

优点：

- 理论上自动化程度最高

风险：

- 需要额外网站发现逻辑
- 更容易受外部页面变化影响
- 更难控制失败边界

预期错误率：

- 在 accepted papers 场景下不一定优于静态注册
- 失败模式更复杂

### 6.4 当前判断

在本任务中：

- 方式一最适合当前阶段
- 方式二适合作为后续产品化扩展
- 方式三不适合当前最小改动目标

## 7. 可写成论文的消融实验建议

在本轮成功后，可以进一步设计以下消融：

### 7.1 registry 显式注册 vs 动态年份路由

比较：

- 实现复杂度
- 失败可解释性
- 历史年份覆盖效率
- 新年份扩展成本

### 7.2 仅 accepted papers 抓取 vs 完整作者机构国家抽取

比较：

- 运行时间
- 失败率
- 对外部源依赖程度
- 结果稳定性

### 7.3 仅 IACR JSON vs IACR JSON + DBLP 校验

比较：

- accepted papers 数量一致率
- 标题一致率
- 额外网络开销
- 限流风险

### 7.4 保留历史兼容层 vs 删除兼容层

比较：

- 仓库复杂度
- 文档复杂度
- 输出歧义程度
- 维护成本

## 8. 建议记录的性能指标

后续每轮实际运行建议至少记录：

1. 总会议数
2. 总年份数
3. 总耗时
4. 成功抓取年份数
5. 失败年份数
6. 单年份平均耗时
7. validation report 成功率
8. raw JSON 成功率

## 9. 后续补记区

### dry run 实际结果

已执行：

```bash
python3 conference-paper-extraction/scripts/run_unified_pipeline.py \
  --group top3_crypto \
  --output-dir generated-data/extraction \
  --dry-run
```

结果：

1. dry run 成功返回
2. `conference_keys` 共 18 个，覆盖 `ASIACRYPT / CRYPTO / EUROCRYPT` 的 `2020-2025`
3. 执行计划被正确聚合到单一 backend：`iacr_top3`
4. 说明 registry 扩展与 unified runner 路由已正常联通

当前结论：

- 静态配置补齐方案在入口层是有效的
- 当前剩余风险已经从“配置是否生效”转移到“真实历史 URL / JSON 是否逐年有效”

### 实际抓取结果

- 首次直接运行：失败

执行命令：

```bash
python3 conference-paper-extraction/scripts/run_unified_pipeline.py \
  --group top3_crypto \
  --output-dir generated-data/extraction
```

失败现象：

- `FileNotFoundError: generated-data/extraction/raw/asiacrypt_2020_papers.json`

原因判断：

1. 失败不是历史年份 URL 失效
2. 失败不是 JSON 结构变化
3. 失败原因是当前 backend 运行契约要求：
   - 若本地尚无 raw JSON，需先显式加 `--fetch`
4. 也就是说，这是一类“运行方式错误”，不是“数据源错误”

采用对策：

- 不修改主代码逻辑
- 直接按现有 runner 契约改用 `--fetch`

对论文写作的价值：

- 这是一个典型的“最小改动方案优先遵循现有接口，而不是为了单次实验修改默认行为”的案例
- 可写入工程实现中的运行契约设计与错误分类讨论

### 失败案例与修复

- 案例 1：直接运行未加 `--fetch`
  - 错误类型：运行方式错误
  - 表现：raw JSON 不存在导致 `FileNotFoundError`
  - 修复：改用 `--fetch`

### 不同方式的错误率/风险对比补充

在这一步可以形成一个很清晰的实验对照：

1. **方式 A：直接运行，不加 `--fetch`**
   - 预期成功率：对新年份补齐任务较低
   - 主要失败模式：本地 raw 不存在
   - 优点：若 raw 已存在，可避免重复联网

2. **方式 B：首次运行加 `--fetch`**
   - 预期成功率：更高
   - 主要失败模式：外部源 URL 无效、网络波动、历史 JSON 结构变化
   - 优点：符合首次补齐历史年份的正常路径

当前判断：

- 对“历史年份首次补齐”任务，应默认采用方式 B
- 对“重复复现实验”任务，可采用方式 A

- 第二次运行（加 `--fetch`）：成功跑完 18 个年份，但暴露出历史 JSON schema 差异

执行命令：

```bash
python3 conference-paper-extraction/scripts/run_unified_pipeline.py \
  --group top3_crypto \
  --output-dir generated-data/extraction \
  --fetch
```

整体结果：

1. 18 个年份全部成功抓到 raw JSON
2. 合计 `papers_count = 1944`
3. 合计 `expanded_author_rows = 12101`
4. 合计 `classified_author_rows = 11497`
5. 合计 `unresolved_country_rows = 604`
6. 合计 `affiliation_mismatch_issues = 1165`

### 关键异常观察

#### 异常 1：ASIACRYPT 2020

- `papers_count = 85`
- `expanded_author_rows = 0`
- `affiliation_mismatch_issues = 85`

检查 raw JSON 发现：

- `authors` 是单个字符串，用 `;` 分隔
- `affiliations` 也是单个字符串，用 `;` 分隔

说明：

- 不是没有 accepted papers
- 不是 URL 无效
- 而是历史 JSON 使用“分号拼接字符串”而不是数组

#### 异常 2：EUROCRYPT 2020

- `papers_count = 81`
- `expanded_author_rows = 0`
- `affiliation_mismatch_issues = 0`

检查 raw JSON 发现：

- 使用的是 `author` 字段
- 使用的是 `institution` 字段
- 不是 `authors` / `affiliations` 数组结构

说明：

- 这是另一类历史 schema 变体
- 问题同样不在数据源缺失，而在 parser 兼容范围不足

进一步验证后发现：

- 仅补 `author` / `institution` 字段还不够
- `institution` 字段多数为空字符串
- 实际机构信息被编码在 `author` 文本的括号中，例如 `Name (Institution)`
- 多作者之间继续使用 `;` 拼接

因此 `EUROCRYPT 2020` 属于更复杂的历史 schema：

1. 字段名变体：`author` / `institution`
2. 内容编码变体：作者与机构混排在同一字符串中

### 当前新结论

对三大密码会历史年份，失败类型至少要区分三类：

1. **入口运行方式错误**
   - 例如首次没加 `--fetch`
2. **数据源层失败**
   - 例如 URL 不存在、网络失败、返回非 JSON
3. **历史 schema 变体失败**
   - 例如 2020 年字段结构不同，但数据本身存在

当前实验已证明：

- 2020-2025 补齐任务的主要剩余难点不是 conference registry
- 而是少量早期年份的 IACR JSON 字段兼容问题
- 而且这种兼容问题会表现为多种不同变体，不能假设 2020 年只需一种 parser 修复

### 对论文可写性的价值

这一发现非常适合写入：

- 历史数据异构性分析
- 数据清洗与 schema 统一章节
- 失败模式分类讨论

### 最终全量复跑结果（完成 parser 修复后）

在补充分号字符串 schema 与 inline `Name (Institution)` schema 兼容后，再次执行：

```bash
python3 conference-paper-extraction/scripts/run_unified_pipeline.py \
  --group top3_crypto \
  --output-dir generated-data/extraction
```

最终汇总结果：

1. `papers_count = 1944`
2. `expanded_author_rows = 12827`
3. `classified_author_rows = 12147`
4. `resolved_country_rows = 12147`
5. `unresolved_country_rows = 680`
6. `affiliation_mismatch_issues = 1089`
7. `unresolved_affiliation_candidates = 321`

### 修复前后总量变化

初次全量运行（仅加 `--fetch`、未做 2020 schema 修复）与修复后的对比：

- `expanded_author_rows`：`12101 -> 12827`，增加 `726`
- `classified_author_rows`：`11497 -> 12147`，增加 `650`
- `affiliation_mismatch_issues`：`1165 -> 1089`，减少 `76`

这说明少量面向历史 schema 的 parser 修复具有明确增益。

### 失败案例与修复

- 案例 1：直接运行未加 `--fetch`
  - 错误类型：运行方式错误
  - 表现：raw JSON 不存在导致 `FileNotFoundError`
  - 修复：改用 `--fetch`

- 案例 2：`ASIACRYPT 2020` 分号字符串 schema
  - 错误类型：历史 schema 变体
  - 表现：`papers_count > 0`，但 `expanded_author_rows = 0`
  - 修复：兼容 `authors` / `affiliations` 的分号字符串解析
  - 修复后效果：
    - `papers_count = 85`
    - `expanded_author_rows = 433`
    - `classified_author_rows = 416`
    - `affiliation_mismatch_issues = 6`

- 案例 3：`EUROCRYPT 2020` author-inline-institution schema
  - 错误类型：历史 schema 变体
  - 表现：`author` 字段存在但 `institution` 为空，导致全量 mismatch
  - 修复：从 `author` 文本中解析 `Name (Institution)` 结构
  - 修复前效果：
    - `papers_count = 81`
    - `expanded_author_rows = 0`
    - `classified_author_rows = 0`
  - 修复后效果：
    - `papers_count = 81`
    - `expanded_author_rows = 294`
    - `classified_author_rows = 231`
    - `affiliation_mismatch_issues = 2`

### 论文写作可直接引用的结论

- 对 accepted papers 历史补齐任务，最小改动方案的主要风险不是入口配置，而是早期 JSON schema 的异构性。
- 在三大密码会历史数据中，同一会议族不同年份可能采用不同编码方式，必须把“字段名兼容”和“内容编码兼容”分开处理。
- 因此，历史数据实验不应只报告抓取成功率，还应报告 schema 兼容成功率与 parser 修复收益。
- 在本实验中，补两类 2020 schema 兼容后，总 `classified_author_rows` 提升了 `650` 行，说明历史兼容 parser 对可分析结果规模有实质影响。

## 10. 当前可直接写入论文的对比数字

### 10.1 运行方式错误 vs 正确运行方式

- 不加 `--fetch`：首次运行直接失败，无法进入真实抓取阶段
- 加 `--fetch`：18 个年份全部成功落盘 raw JSON

这说明对“首次历史补齐”任务，`--fetch` 是必要运行条件。

### 10.2 schema 修复前后对比

#### ASIACRYPT 2020

- 修复前：
  - `expanded_author_rows = 0`
  - `classified_author_rows = 0`
  - `affiliation_mismatch_issues = 85`
- 修复后：
  - `expanded_author_rows = 433`
  - `classified_author_rows = 416`
  - `affiliation_mismatch_issues = 6`

#### EUROCRYPT 2020

- 修复前：
  - `expanded_author_rows = 0`
  - `classified_author_rows = 0`
  - `affiliation_mismatch_issues = 0`
- 修复后：
  - `expanded_author_rows = 294`
  - `classified_author_rows = 231`
  - `affiliation_mismatch_issues = 2`

### 10.3 对比解释

这个结果非常适合作为“parser 兼容策略有效性”的证据：

1. 仅补 conference registry 不能解决历史 schema 问题
2. 仅成功抓到 raw JSON 也不代表能成功展开作者机构行
3. 少量面向历史变体的 parser 修复，能显著降低 2020 年份的结构性失败率

### 10.4 从结果角度看“不同方式的错误率”

可把本轮实验中的错误/失败近似分成三层：

1. **入口层错误**
   - 代表：未加 `--fetch`
   - 后果：无法进入真实抓取阶段
   - 性质：人为使用错误，可通过运行规范完全避免

2. **数据源层错误**
   - 本轮未观察到大规模 URL 失效
   - 说明 2020-2025 IACR JSON 主体上是可获得的

3. **schema 兼容层错误**
   - 这是本轮的主导失败类型
   - 代表：`ASIACRYPT 2020` 与 `EUROCRYPT 2020`
   - 后果：raw 抓到但作者/机构行无法有效展开

因此在本任务下：

- **主要错误率贡献来自 schema 兼容层，而不是数据源可用性层**

这个结论非常适合写进论文实验讨论。

## 11. 后续可做的消融实验补充

在当前实验成功后，可以进一步做三类消融：

### 11.1 不同 parser 兼容层的增量收益

逐步比较：

1. 只支持标准数组 schema
2. 标准数组 schema + 分号字符串 schema
3. 标准数组 schema + 分号字符串 schema + inline `Name (Institution)` schema

比较指标：

- `expanded_author_rows`
- `classified_author_rows`
- `affiliation_mismatch_issues`
- `unresolved_country_rows`

### 11.2 “只抓 accepted papers”与“继续做作者机构国家抽取”的收益/代价对比

比较：

- raw 抓取成功率
- 作者展开成功率
- 国家识别成功率
- 实现复杂度

### 11.3 历史年份与新年份的异构性对比

可比较：

- 2020-2021
- 2022-2023
- 2024-2025

观察历史 schema 变体是否明显集中在早期年份。

### 11.4 parser 兼容策略的收益消融

建议明确做三组实验：

1. 不做历史 schema 修复
2. 只加分号字符串修复
3. 再加 inline `Name (Institution)` 修复

输出比较：

- `expanded_author_rows`
- `classified_author_rows`
- `affiliation_mismatch_issues`
- 每个年份的异常论文比例

这会非常像一组标准、清晰且容易写进论文的消融实验。
