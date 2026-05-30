# 作者角色链路与覆盖接入实验记录

## 1. 合并范围

本文件合并以下三份阶段记录：

- `AUTHOR_ROLE_MINIMAL_PIPELINE_2026_05_29.md`
- `AUTHOR_ROLE_COVERAGE_INTEGRATION_2026_05_29.md`
- `AUTHOR_ROLE_OVERRIDE_SUPPORT_2026_05_29.md`

## 2. 主线目标

围绕作者角色模块，一共完成三步：

1. 建立最小作者角色事实表
2. 把角色状态接入 coverage ledger
3. 为通讯作者和共同一作增加人工 override 入口

## 3. 阶段一：最小作者角色链路

目标：把作者角色从统计脚本里拆出，生成独立 `paper_author_roles.csv`。

当前稳定支持：

- 第一作者
- 参与作者

保留待补字段：

- 通讯作者
- 共同一作 / equal contribution

新增内容：

- `conference-author-role-extraction/SKILL.md`
- `conference-author-role-extraction/references/author_role_schema.md`
- `conference-author-role-extraction/scripts/build_author_roles.py`

当前产物：

- `generated-data/author-roles/paper_author_roles.csv`
- `generated-data/author-roles/author_role_report.json`
- `generated-data/author-roles/author_role_report.md`

关键结果：

- input_rows: 7419
- role_rows: 5992
- papers: 1359
- first_author_rows: 1315
- participating_author_rows: 5992
- corresponding_author_rows: 0
- equal_contribution_rows: 0

解决的核心问题：

- 多机构作者在长表中重复，先按 `(paper_key, author_order, author_key)` 去重
- 第一作者逻辑从多个统计脚本中抽离出来
- 通讯作者不做无证据猜测

## 4. 阶段二：角色状态接入 coverage ledger

目标：让 coverage ledger 的 `role_status` 从硬编码推断改为读取角色事实表后计算。

修改脚本：

- `conference-analysis-automation/scripts/build_coverage_ledger.py`

默认读取：

- `generated-data/author-roles/paper_author_roles.csv`

当前 `role_status` 规则：

- `missing`
- `participant_only`
- `first_author_only`
- `corresponding_author_available`
- `complete_unverified`

关键结果：

- 当前已有角色覆盖的会议年份会显示 `first_author_only`
- 缺角色表的会议年份显示 `missing`
- backfill task 仍保留 `extract_author_roles`

解决的核心问题：

- 角色状态改为由事实表驱动
- 为后续通讯作者补齐预留状态升级接口

## 5. 阶段三：override 支持

目标：在不自动猜测通讯作者的前提下，为 `paper_author_roles.csv` 增加人工 gold set / override 入口。

修改脚本：

- `conference-author-role-extraction/scripts/build_author_roles.py`

新增参数：

- `--role-overrides <csv>`
- `--override-template-limit <n>`

新增模板：

- `generated-data/author-roles/author_role_overrides_template.csv`

关键结果：

- role_rows: 5992
- corresponding_author_rows: 0
- equal_contribution_rows: 0
- applied_override_rows: 0

解释：

- 当前还没有正式传入 `author_role_overrides.csv`
- 但模板和匹配入口已经具备

## 6. 方法对比结论

通用写法已统一收口到：`WRITING_NOTES.md` 中的“作者角色：证据驱动而不是猜测驱动”和“事实表优先于分散逻辑”。

### 6.1 直接在统计脚本里判断角色

优点：

- 简单
- 短期可用

缺点：

- 逻辑分散
- 多机构重复风险会在多个脚本中反复出现
- 不利于扩展通讯作者和共同一作

### 6.2 独立角色事实表

当前采用。

优点：

- 一人一论文一行
- 角色字段集中管理
- 可与 coverage、override、后续 PDF/HTML 解析器对接

缺点：

- 多一层产物
- 下游统计需要逐步切换消费方式

### 6.3 自动猜测通讯作者

当前不采用。

原因：

- 最后一作者不稳定
- 星号可能表示 equal contribution
- PDF 文本抽取可能丢标记

## 7. 后续实验建议

- 比较“直接从 `author_affiliation_facts.csv` 统计一作”和“从 `paper_author_roles.csv` 统计一作”的误差
- 用小规模人工 gold set 比较通讯作者候选策略：最后作者、PDF 标记、publisher HTML、人工 override
- 比较不同 override 粒度对下游统计收益和人工成本的影响
- 论文写作时，优先复用 `WRITING_NOTES.md` 中的“实验对比写法模板”和“消融实验模板”

## 8. 当前结论

作者角色主线已经从“统计脚本内隐逻辑”升级为：

- 独立角色事实表
- coverage ledger 状态接入
- 人工 override 入口

当前能力稳定支持第一作者和参与作者；通讯作者和共同一作仍应通过证据驱动方式逐步补齐。
