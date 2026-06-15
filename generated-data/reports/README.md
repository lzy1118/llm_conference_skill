# 报告目录

该目录用于统一保存基于分析产物生成的 Markdown / JSON 报告。

## 典型来源

- `conference-report-generation/scripts/generate_report.py`
- `conference-analysis-automation/scripts/run_analysis_pipeline.py` 在启用 `report` 时生成的报告输出

在未显式传入 `--output-dir` 时，报告脚本默认会把结果写到仓库根目录下的 `generated-data/reports/`。

## 典型文件

- `conference_report.md`
- `conference_report.json`
- `extraction_2020_2025_validation_status_2026_06_03.md`
- `papers_missing_author_rows_2026_06_06.csv`
- `data_generation_status_2026_06_06.md`

## 当前状态

当前目录已用于集中保存状态报告、实验对比报告、论文草稿与辅助说明文件。
后续新的报告产物仍应统一保存在这里，并尽量在说明中明确其统计口径与适用范围。

## 说明

- 本目录中的校验与状态报告应明确区分：
  - 行级字段完整性：例如标准化事实表中是否存在空作者名、空机构名
  - 论文级覆盖完整性：例如论文是否缺少作者机构行、是否仅有部分 affiliation 覆盖
- 作者角色报告当前应视为“非全量能力报告”，不能直接当作七大会 2020—2025 全量主结果引用。
