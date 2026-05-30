# Backfill runner 与去重执行实验记录

## 1. 合并范围

本文件合并以下两份阶段记录：

- `BACKFILL_TASK_RUNNER_2026_05_29.md`
- `BACKFILL_DEDUP_EXECUTION_2026_05_29.md`

## 2. 主线目标

围绕 backfill 自动化，一共完成两步：

1. 把 `backfill_tasks.csv` 变成可执行计划
2. 解决重复命令并验证 local task 安全执行

## 3. 阶段一：backfill task runner

目标：让 `generated-data/coverage/backfill_tasks.csv` 从静态清单推进到执行计划层。

新增脚本：

- `conference-analysis-automation/scripts/run_backfill_tasks.py`

默认输入：

- `generated-data/coverage/backfill_tasks.csv`

默认输出：

- `generated-data/backfill/backfill_plan.json`
- `generated-data/backfill/backfill_plan.md`

当前计划能力：

- 读取 backfill task
- 过滤 task type / priority / conference / limit
- 映射到命令
- 默认 dry-run
- 默认不执行 network 任务

关键结果：

- selected_tasks: 12
- execute: False
- allow_network: False
- runnable_tasks: 4
- executed_tasks: 0

## 4. 阶段二：命令去重与本地执行

目标：解决全局任务被按会议年份重复生成的问题，并验证可安全执行 local backfill 任务。

修改内容：

- 默认按完整 command 去重
- 重复任务标记为 `execution_kind=duplicate`
- 重复任务不执行
- 可通过 `--no-dedupe-commands` 关闭去重

关键结果：

- selected_tasks: 10
- execute: True
- allow_network: False
- runnable_tasks: 2
- duplicate_tasks: 8
- executed_tasks: 2

实际执行的 local 任务：

1. `extract_author_roles`
2. `extract_cfp`

执行后结果：

- 作者角色任务成功重跑
- CFP 任务成功重跑
- 由于当前没有 author role override 和 CFP 实际输入，统计结果无实质变化，这符合预期

## 5. 当前任务映射规则

- `fetch_papers` -> unified extraction runner + `--fetch`，network
- `fetch_affiliations` -> unified extraction runner + affiliation / mismatch flags，network
- `extract_cfp` -> CFP pipeline，local
- `extract_author_roles` -> author role builder，local
- `add_expected_paper_count` -> manual
- `verify_paper_count` -> manual
- `migrate_legacy_contract` -> manual
- `normalize_country` -> manual

## 6. 方法对比结论

通用写法已统一收口到：`WRITING_NOTES.md` 中的“Backfill：执行安全边界先于自动化程度”和“控制面与执行面分离”。

### 6.1 人工逐项执行

优点：

- 风险低

缺点：

- 不可复现
- 容易漏任务

### 6.2 直接自动执行全部任务

优点：

- 自动化高

缺点：

- 网络任务风险高
- 失败难定位

### 6.3 dry-run plan + 显式 execute

当前采用。

优点：

- 可先审阅命令
- 能清晰区分 local / network / manual
- 安全边界明确

### 6.4 不去重执行重复命令

风险：

- 重复覆盖输出
- 浪费运行时间

### 6.5 command-level 去重

当前采用。

优点：

- 实现简单
- 对全局任务有效

限制：

- 无法识别“不同命令但语义相同”的重复

## 7. 后续实验建议

- 比较只 dry-run、只执行 local、执行 local+network 的 coverage 改善量与失败率
- 比较 high priority、high+medium、全部任务三种执行范围
- 比较不去重、command-level 去重、task-type 去重三种策略的运行时间与产物变化次数
- 论文写作时，优先复用 `WRITING_NOTES.md` 中的“实验对比写法模板”和“消融实验模板”

## 8. 当前结论

backfill 主线已经从“人工阅读任务表”推进到：

- 可复现执行计划
- local/network/manual 分类
- 安全 dry-run 边界
- command-level 去重
- local task 实际执行验证
