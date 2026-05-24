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

## 当前状态

当前仓库已提交的历史产物中，尚未发现可直接归档到本目录的现成分析结果文件。
后续分析主链路运行后的结果应统一保存在这里。
