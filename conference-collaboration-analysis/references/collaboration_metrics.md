# 合作指标参考

## 默认边定义

对每篇论文，先收集指定模式下的去重节点集合，再生成无序两两组合。

机构或国家节点包含复合标签时，先按可靠身份拆分；未解析的组成项作为残片丢弃，
不生成复合字符串节点。

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
