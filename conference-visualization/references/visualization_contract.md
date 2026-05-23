# 可视化契约

## 目标

把已有顶会分析输出转换为轻量、可复用的可视化产物。

## 支持输入

- `country/country_summary.csv`
- `institutions/institution_summary.csv`
- `authors/author_summary.csv`
- `trends/trend_by_entity_year.csv`
- `collaboration/collaboration_edges.csv`

## 默认图表映射

- 国家 summary -> 头部论文数条形图
- 机构 summary -> 头部论文数条形图
- 作者 summary -> 头部论文数条形图
- 趋势表 -> 多序列折线图
- 合作边表 -> 头部合作边条形图

## 输出规则

- 优先使用 SVG，便于移植与版本对比。
- 只有当 section 存在且非空时才生成对应图表。
- manifest 中应显式记录跳过或缺失的 section。

## Manifest 建议字段

- `analysis_dir`
- `rendered_files`
- `missing_sections`
- `empty_sections`
- `top_n`
