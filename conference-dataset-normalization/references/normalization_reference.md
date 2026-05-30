# 标准化参考

## 目标

把来自不同顶会来源的抽取结果整理为稳定、可复用、适合分析的中间数据层。

## 目标输出表

### `paper_facts.csv`

每篇论文一行，建议包含：

- `paper_key`
- `conference`
- `year`
- `title`
- `article_tag`
- `paper_id`
- `author_count`

### `author_affiliation_facts.csv`

每条作者-机构记录一行，建议包含：

- `row_key`
- `paper_key`
- `conference`
- `year`
- `title`
- `article_tag`
- `paper_id`
- `name`
- `author_key`
- `author_order`
- `inst`
- `institution_key`
- `country`
- `classification_source`
- `classification_confidence`
- `classification_reason`

### `institution_dim.csv`

每个标准化机构一行，建议包含：

- `institution_key`
- `inst_display`
- `country`
- `source_count`
- `needs_review`

## 标准化原则

- 优先确定性清洗，而不是模糊合并。
- 同时保留展示字段和标准化 key。
- 只要对后续解释有帮助，就尽量保留来源字段。
- 下游统计应只消费这些标准化表，而不再回到原始源数据。

## 数据质量报告建议

至少应包含：

- 输入文件列表
- 原始行数与标准化行数
- 去重跳过数量
- 缺失作者或机构数量
- 未解析国家数量
- 字段映射说明
