# 统一生成数据目录

该目录用于统一管理仓库内“最终有用的生成数据文件”。后续推荐把抽取、标准化、分析、报告、可视化等产物都写到这里，而不是分散落在 `data/`、`Security-data/data/`、`Top3-data/data/` 等多个位置。

## 推荐目录结构

```text
generated-data/
  extraction/      统一采集输出目录，供 conference-paper-extraction 使用
  normalized/      标准化后的共享事实表与维表
  analysis/        国家、机构、作者、趋势、合作、审计等分析结果
  reports/         汇总报告
  visualizations/  图表与 SVG 可视化
  manifests/       运行 manifest 与批处理记录
```

## 推荐用法

### 1. 统一采集

```bash
python3 conference-paper-extraction/scripts/run_unified_pipeline.py \
  --group all \
  --output-dir generated-data/extraction
```

### 2. 标准化

```bash
python3 conference-dataset-normalization/scripts/normalize_dataset.py \
  generated-data/extraction/output/*_author_affiliations.csv \
  --output-dir generated-data/normalized
```

### 3. 自动化分析

```bash
python3 conference-analysis-automation/scripts/run_analysis_pipeline.py \
  --normalized-input generated-data/normalized/author_affiliation_facts.csv \
  --output-dir generated-data/analysis
```

### 4. 报告与可视化

```bash
python3 conference-report-generation/scripts/generate_report.py \
  --analysis-dir generated-data/analysis \
  --output-dir generated-data/reports

python3 conference-visualization/scripts/generate_visualizations.py \
  --analysis-dir generated-data/analysis \
  --output-dir generated-data/visualizations
```

## 说明

- 现有脚本仍兼容旧的 `data/` 输出位置。
- 新工作流建议优先使用本目录，减少跨子项目目录查找成本。
- 如果需要保留历史产物，可以继续保存在旧目录；本目录面向后续统一管理。
- 当前 `generated-data/` 不保留仅美国切片文件；统一管理的主对象是通用的“作者-机构-国家”主输出及其下游产物。

## 当前默认落盘行为

以下主链路脚本在未显式传入 `--output-dir` 时，已经默认写入 `generated-data/`：

- `conference-paper-extraction/scripts/run_unified_pipeline.py` -> `generated-data/extraction`
- `Security-data/scripts/security_pipeline.py` -> `generated-data/extraction`
- `Top3-data/scripts/top3_pipeline.py` -> `generated-data/extraction`
- `conference-dataset-normalization/scripts/normalize_dataset.py` -> `generated-data/normalized`
- `conference-analysis-automation/scripts/run_analysis_pipeline.py` -> `generated-data/analysis`
- `conference-report-generation/scripts/generate_report.py` -> `generated-data/reports`
- `conference-visualization/scripts/generate_visualizations.py` -> `generated-data/visualizations`

因此现在可以把 `generated-data/` 视为仓库主工作流的统一数据出口。

## 当前归档情况

- `generated-data/extraction/`：已集中复制当前仓库中可见的历史采集层最终输出
- `generated-data/normalized/`：已写入标准化主产物
- `generated-data/analysis/`：已写入分析主产物
- `generated-data/reports/`：已写入汇总报告
- `generated-data/visualizations/`：已写入可视化产物

`generated-data/` 当前应被理解为仓库主工作流的通用结果目录，而不是历史美国切片文件的缓存区。
