# 报告契约

## 目标

把已有分析 CSV 输出转换为结构清晰、易读的分析报告，同时不改变底层指标含义。

## 支持输入

可接受以下任意子集：

- `country/country_summary.csv`
- `institutions/institution_summary.csv`
- `authors/author_summary.csv`
- `trends/trend_summary.csv`
- `collaboration/collaboration_edges.csv`

## 建议章节

- 总览
- 已包含与缺失章节
- 头部国家
- 头部机构
- 头部作者
- 趋势亮点
- 合作亮点

## JSON 元数据建议字段

- `analysis_dir`
- `included_sections`
- `missing_sections`
- `section_counts`

## 失败处理

- 只有在所有受支持输入都不存在时才失败。
- 如果仅缺少部分章节，则生成部分报告，并在报告中显式说明。
