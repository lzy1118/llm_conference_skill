# 趋势指标参考

## 默认对象-年份指标

默认使用去重后的 `(entity, paper_key, year)` 参与数量。

这样可以让趋势结果与大多数会议统计中的 headline 指标保持一致。

## 推荐输出列

`trend_by_entity_year.csv` 建议包含：

- `entity_type`
- `entity_key`
- `entity_name`
- `year`
- `papers`
- `previous_year_papers`
- `delta_papers`
- `delta_ratio`

`trend_summary.csv` 建议包含：

- `entity_type`
- `entity_key`
- `entity_name`
- `year_first`
- `year_last`
- `years_active`
- `papers_first`
- `papers_last`
- `papers_peak`
- `peak_year`
- `net_change`

## 报告检查清单

- 分析范围
- 对象类型
- 计数口径
- 增长最快的对象
- 下降最明显的对象
- 已知覆盖范围限制
