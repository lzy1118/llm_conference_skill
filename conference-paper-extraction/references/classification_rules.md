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

## 当前实现提示

- 共享判定骨架位于 `scripts/classification_common.py`
- 密码会与安全会 backend 都复用了同一判定骨架：override -> exact alias -> country / institution rules -> unresolved
- 安全会 backend 对 `A; B; C` 形式的多机构字符串会逐段判定：
  - 单国一致时保留该国家
  - 多国混合时标记为 `Multiple`
  - 无法可靠判断时保留 `Unknown`
