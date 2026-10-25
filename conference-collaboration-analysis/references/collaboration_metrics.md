# 合作指标参考

## 默认边定义

对每篇论文，先收集指定模式下的去重节点集合，再生成无序两两组合。

作者节点优先按 `author_key` 区分。不同显式 key 不因同名而合并；缺少 key 的行只有在同一论文中能唯一匹配一个显式 key 时才归并。跨来源论文签名按作者顺序和稳定身份去重，多机构事实行不增加签名中的作者数。

机构或国家节点包含复合标签时，按可靠身份拆分。无法解析的国家组成项归入 `Unknown`，无法解析的机构组成项不生成节点；不得将复合字符串直接作为节点。

## 推荐边表字段

- `mode`
- `left_key`
- `left_name`
- `right_key`
- `right_name`
- `shared_papers`
- `conference_count`
- `year_first`
- `year_last`

## 推荐摘要字段

- `mode`
- `paper_count`
- `node_count`
- `edge_count`
- `repeated_edge_count`
- `max_shared_papers`

## 报告检查清单

- 分析范围
- 边模式
- 去重规则
- 重复合作最强的边
- 已知数据质量限制
