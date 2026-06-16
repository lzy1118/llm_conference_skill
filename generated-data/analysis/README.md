# 分析结果目录

该目录用于统一保存国家、机构、作者、趋势、合作、审计等分析产物。

## 典型来源

- `conference-analysis-automation/scripts/run_analysis_pipeline.py`
- 以及各个独立分析脚本透过自动化层生成的子目录

在未显式传入 `--output-dir` 时，自动化分析脚本默认会把结果写到仓库根目录下的 `generated-data/analysis/`。

## 典型子目录

- `country/`
- `institutions/`
- `authors/`
- `trends/`
- `collaboration/`
- `audit/`
- `reports/`
- `visualizations/`

## 典型文件

- `automation_manifest.json`
- `automation_report.md`
- `country/country_summary.csv`
- `institutions/institution_summary.csv`
- `authors/author_summary.csv`
- `trends/trend_summary.csv`
- `collaboration/collaboration_edges.csv`
- `reports/conference_report.md`
- `visualizations/visualization_manifest.json`

## 当前状态

当前目录已经写入一套可直接复用的分析主产物，包括：

- 自动化运行记录：`automation_manifest.json`、`automation_report.md`
- 国家分析：`country/`
- 机构分析：`institutions/`
- 作者分析：`authors/`
- 趋势分析：`trends/`
- 合作分析：`collaboration/`
- 质量审计：`audit/`
- 分析层报告：`reports/`
- 分析层图表：`visualizations/`

此外，`artifact_index.csv` 与 `artifact_index.md` 已作为本目录的路径总索引存在。
后续新的分析主链路结果仍应统一保存在这里，并优先延续当前目录结构。
