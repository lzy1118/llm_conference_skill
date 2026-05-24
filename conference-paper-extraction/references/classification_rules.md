# 分类规则参考

## 目标

对机构字符串做可解释的国家判定，并额外保留兼容型美国机构标记、置信度与来源说明。

当前 skill 内部已经把“规则型分类骨架”收敛到共享 helper，具体会议族仍可保留各自的规则集合，以避免误伤不同学科或会议生态下的机构命名差异。

## 建议分层

### 第 1 层：精确别名匹配

- 适用于 MIT、Stanford、CMU、NIST 等稳定简称
- 置信度最高
- 应由人工维护的别名字典支撑

### 第 2 层：明确排除规则

- 通过国家名、城市名、机构特征词识别具体国家
- 如 `Zurich`、`Bochum`、`Tsinghua` 等
- 适合减少误报并避免把非美国机构错误吞进美国规则

### 第 2.5 层：国家关键词识别

- 在无法命中高置信度机构规则时，继续尝试识别具体国家
- 当前已覆盖美国、中国、加拿大、英国、瑞士、德国、日本、新加坡、韩国、印度、以色列等常见学术产出国家
- 无法可靠判断时保持 `Unknown`，避免硬猜

### 第 3 层：关键词规则

- 使用 `University of`, `UC`, `Carnegie Mellon`, `Georgia Tech` 等关键词
- 可覆盖大量美国高校与研究机构
- 置信度略低于精确匹配
- 安全会 backend 的关键词集合通常更宽，因为工业实验室、政府实验室和安全公司缩写更常出现
- 密码会 backend 的关键词集合可以更保守，以减少对国际机构简称的误判

### 回退：未解析

- 无法可靠判断时进入 `unresolved`
- 置信度设为 0.0
- 应进入复核或后续 enriched 流程
- 对 IACR mismatch 论文，当前 skill 内部已经支持单独的 resolution stage 来生成候选来源与待复核清单

## 输出建议

每条判定至少保留：

- `country`
- `is_us_institution`：兼容字段，不应替代 `country` 成为主分析字段
- `classification_source`
- `classification_confidence`
- `classification_reason`

## 常见问题

- 机构简称在不同国家重复出现
- 公司实验室与大学混合命名
- 同一机构存在多种拼写或语言形式
- 一个字符串中同时包含多个机构

## reference-first 规则

当用户提供人工整理的 reference 表，并要求统计结果优先贴齐 reference 时，建议显式采用 reference-first 规则层，而不是把所有特判混入默认国家分类层。

### 1. 先判断 reference 的真实语义

常见有两类：

- 机构所属国：一条机构字符串只应落到一个国家
- 论文参与国：同一条 affiliation 可能同时贡献多个国家参与信号

若 reference 更接近“论文参与国”口径，则不要强迫每条 affiliation 只能输出一个国家。

若 reference 同时包含作者名单信息，需要把“作者身份”与“机构/国家补充”拆开看待：

- 作者身份冲突时，优先保留 IACR raw / DBLP
- reference author list 只作为机构与国家的辅助补充来源
- 不要让 reference 直接改写与 source-of-truth 冲突的作者姓名或作者顺序

若引入作者级 override 文件，推荐把冲突记录单独输出，而不是强行合并进主抽取表。

### 2. 联合 affiliation 的推荐处理顺序

先保护，再拆分：

1. 保护不应拆开的固定机构名
2. 仅对可靠的 `;`、`/`、` & `、` and ` 连接结构做拆分
3. 对拆分后的片段分别分类
4. 若 reference 要求同一机构串同时贡献多个国家，可保留多条参与记录

不应拆开的典型场景：

- `Science and Technology`
- `Posts and Telecommunications`
- `Academy of Mathematics and System Science`
- `Beijing Institute of Mathematical Sciences and Application`
- 其他内部自带 `and`，但语义上仍是单一机构名的场景

### 3. 双参与国特判的使用边界

仅当满足以下条件时再引入双参与国特判：

- 用户明确要求按已有 reference 复刻统计口径
- reference 中稳定反复出现同一类解释模式
- 保留原始机构国家判定后，仍需要额外补一个参与国信号

推荐做法：

- 保留原始国家判定结果
- 额外写出一条同机构文本的新参与记录
- 在 `classification_reason` 中显式标记为 `reference_dual_participation_*`
- 若使用作者级 override，要求同时匹配会议、年份、论文标签、作者顺序和作者姓名，避免 reference 覆盖错误作者

不推荐做法：

- 直接把原始国家覆盖成另一个国家
- 只在最终聚合脚本里硬编码论文名，不回写审计层

### 4. reference-first 规则的沉淀方式

建议按优先级沉淀：

1. 通用国家别名规则
2. 拆分保护规则
3. 会议族局部特判
4. 极少数 reference 特殊案例

只有前 3 类适合泛化复用。第 4 类应尽量附带明确注释，说明：

- 来源 reference 文件
- 适用会议范围
- 适用年份范围
- 为什么不能用更通用规则表达

## 当前实现提示

- 共享判定骨架位于 `scripts/classification_common.py`
- 密码会与安全会 backend 都复用了同一判定骨架：override -> exact alias -> country / institution rules -> unresolved
- 安全会 backend 对 `A; B; C` 形式的多机构字符串会逐段判定：
  - 单国一致时保留该国家
  - 多国混合时标记为 `Multiple`
  - 无法可靠判断时保留 `Unknown`
- IACR 密码会 backend 在需要对齐论文级参与国 reference 时，可输出同一机构字符串的多条国家参与记录，而不是只保留单一国家。
