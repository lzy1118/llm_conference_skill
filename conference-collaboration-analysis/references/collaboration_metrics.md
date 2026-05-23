# 合作指标参考

## 默认边定义

对每篇论文，先收集指定模式下的去重节点集合，再生成无序两两组合。

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
