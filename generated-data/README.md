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
  generated-data/extraction/output/by_conference/*/author_affiliations.csv \
  --output-dir generated-data/normalized
```

当前推荐的抽取层目录约定：

```text
generated-data/extraction/
  raw/                 原始快照
  interim/by_conference/<conference_key>/
  output/by_conference/<conference_key>/
  output/summaries/<group>/
  pdfs/<conference_key>/
```

其中：

- 单会议正式输出统一放在 `output/by_conference/<conference_key>/`
- 多会议汇总统一放在 `output/summaries/<group>/`
- 单会议中间产物统一放在 `interim/by_conference/<conference_key>/`
- 会议级路径总索引见：`generated-data/extraction/artifact_index.csv` 与 `generated-data/extraction/artifact_index.md`
- 分析层路径总索引见：`generated-data/analysis/artifact_index.csv` 与 `generated-data/analysis/artifact_index.md`
- 七大会 `2020-2025` 完成度总表见：`generated-data/coverage/seven_conference_completion_2020_2025.csv` 与 `generated-data/coverage/seven_conference_completion_2020_2025.md`

### 3. 自动化分析

```bash
python3 conference-analysis-automation/scripts/run_analysis_pipeline.py \
  --normalized-input generated-data/normalized/author_affiliation_facts.csv \
  --output-dir generated-data/analysis
```

或者直接从会议选择开始：

```bash
python3 conference-analysis-automation/scripts/run_analysis_pipeline.py \
  --extract-group top4_security \
  --extract-fetch \
  --extract-fetch-affiliations \
  --output-dir generated-data/analysis
```

对于密码会，也可以让分析自动化直接触发 mismatch resolution：

```bash
python3 conference-analysis-automation/scripts/run_analysis_pipeline.py \
  --extract-group top3_crypto \
  --extract-fetch \
  --extract-resolve-mismatches \
  --extract-query-dblp-for-resolution \
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

- 新工作流应优先使用本目录，减少跨子项目目录查找成本。
- 历史目录应逐步收缩；新的主流程结果应集中保存在本目录。
- 当前 `generated-data/` 不保留仅美国切片文件；统一管理的主对象是通用的“作者-机构-国家”主输出及其下游产物。

## 当前默认落盘行为

以下主链路脚本在未显式传入 `--output-dir` 时，已经默认写入 `generated-data/`：

- `conference-paper-extraction/scripts/run_unified_pipeline.py` -> `generated-data/extraction`
- `conference-dataset-normalization/scripts/normalize_dataset.py` -> `generated-data/normalized`
- `conference-analysis-automation/scripts/run_analysis_pipeline.py` -> `generated-data/analysis`
- `conference-report-generation/scripts/generate_report.py` -> `generated-data/reports`
- `conference-visualization/scripts/generate_visualizations.py` -> `generated-data/visualizations`

因此现在可以把 `generated-data/` 视为仓库主工作流的统一数据出口。

## 当前正式目录

- `generated-data/extraction/`：统一采集主输出目录
- `generated-data/normalized/`：已写入标准化主产物
- `generated-data/analysis/`：已写入分析主产物
- `generated-data/reports/`：已写入汇总报告
- `generated-data/visualizations/`：已写入可视化产物

`generated-data/` 当前应被理解为仓库主工作流的通用结果目录，而不是历史美国切片文件的缓存区。

## 论文写作推荐入口

写论文时优先使用这些最新主线目录：

- 数据抽取：`generated-data/extraction/`
- 标准化事实表：`generated-data/normalized/author_affiliation_facts.csv`
- 作者聚合事实表：`generated-data/normalized/author_paper_affiliation_facts.csv`
- 论文级事实表：`generated-data/normalized/paper_facts.csv`
- 机构维表：`generated-data/normalized/institution_dim.csv`
- 统计分析：`generated-data/analysis/`
- 双口径作者单位统计：`generated-data/analysis/affiliation_scope/`
- 汇总报告：`generated-data/reports/`
- 图表：`generated-data/visualizations/`
- 覆盖率与完整性审计：`generated-data/coverage/`
