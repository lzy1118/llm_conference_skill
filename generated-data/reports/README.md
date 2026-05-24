# 报告目录

该目录用于统一保存基于分析产物生成的 Markdown / JSON 报告。

## 典型来源

- `conference-report-generation/scripts/generate_report.py`
- `conference-analysis-automation/scripts/run_analysis_pipeline.py` 在启用 `report` 时生成的报告输出

在未显式传入 `--output-dir` 时，报告脚本默认会把结果写到仓库根目录下的 `generated-data/reports/`。

## 典型文件

- `conference_report.md`
- `conference_report.json`

## 当前状态

当前仓库已提交的历史产物中，尚未发现可直接归档到本目录的现成报告文件。
后续报告产物应统一保存在这里。
