# 可视化目录

该目录用于统一保存基于分析产物生成的 SVG 图表与可视化 manifest。

## 典型来源

- `conference-visualization/scripts/generate_visualizations.py`
- `conference-analysis-automation/scripts/run_analysis_pipeline.py` 在启用 `visualization` 时生成的图表输出

在未显式传入 `--output-dir` 时，可视化脚本默认会把结果写到仓库根目录下的 `generated-data/visualizations/`。

## 典型文件

- `visualization_manifest.json`
- `country_top_papers.svg`
- `institution_top_papers.svg`
- `author_top_papers.svg`
- `conference_papers.svg`
- `conference_authors.svg`
- `conference_rows.svg`
- `conference_unknown_rate.svg`
- `trend_entity_year.svg`
- `collaboration_top_edges.svg`

## 当前状态

当前目录已经写入可直接使用的 SVG 图表与 manifest，包括：

- `country_top_papers.svg`
- `institution_top_papers.svg`
- `author_top_papers.svg`
- `trend_entity_year.svg`
- `collaboration_top_edges.svg`
- `conference_papers.svg`
- `conference_authors.svg`
- `conference_rows.svg`
- `conference_unknown_rate.svg`
- `visualization_manifest.json`

后续新的图表产物仍应统一保存在这里，并保持 manifest 与实际文件同步。
