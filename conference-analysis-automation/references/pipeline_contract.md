# 流水线契约

## 目标

让顶会分析技能通过文件与命令行参数低耦合协作，而不是通过直接函数导入耦合在一起。

## 核心共享契约

自动化层应把 `normalized/author_affiliation_facts.csv` 视为最主要的共享事实表。

如果输入仍停留在抽取层，则应优先从 `conference-paper-extraction` 的 `output/*_author_affiliations.csv` 或汇总版 `*_作者机构国家.csv` 进入标准化；不要把历史 `*_us_institutions.csv` 视为默认主入口。

最低应包含以下字段：

- `paper_key`
- `conference`
- `year`
- `name`
- `author_key`
- `author_order`
- `inst`
- `institution_key`
- `country`

其中 `country` 是正式主字段。

推荐保留的附加字段：

- `title`
- `paper_id`
- `classification_source`
- `classification_confidence`
- `classification_reason`

## 执行契约

自动化 skill 应独立调用每个下游脚本。

推荐脚本接口如下：

- 标准化：`python3 conference-dataset-normalization/scripts/normalize_dataset.py <inputs...> --output-dir <dir>`
- 国家统计：`python3 conference-country-statistics/scripts/country_statistics.py --input <csv> --output-dir <dir> [--conference X] [--year Y]`
- 机构统计：`python3 conference-institution-statistics/scripts/institution_statistics.py --input <csv> --output-dir <dir> [--conference X] [--year Y] [--country X]`
- 作者统计：`python3 conference-author-statistics/scripts/author_statistics.py --input <csv> --output-dir <dir> [--conference X] [--year Y]`
- 趋势分析：`python3 conference-trend-analysis/scripts/trend_analysis.py --input <csv> --output-dir <dir> --entity <country|institution|author> [--conference X] [--year Y]`
- 合作分析：`python3 conference-collaboration-analysis/scripts/collaboration_analysis.py --input <csv> --output-dir <dir> --mode <author|country|institution> [--conference X] [--year Y]`
- 标准化审计：`python3 conference-quality-audit/scripts/quality_audit.py --normalized-input <csv> [--institution-dim <csv>] --output-dir <dir>`
- 分析产物审计：`python3 conference-quality-audit/scripts/quality_audit.py --analysis-dir <dir> --output-dir <dir>`
- 报告生成：`python3 conference-report-generation/scripts/generate_report.py --analysis-dir <dir> --output-dir <dir>`
- 可视化生成：`python3 conference-visualization/scripts/generate_visualizations.py --analysis-dir <dir> --output-dir <dir>`

## 输出契约

每次自动化运行的目录应至少包含：

- 一个 manifest 文件，记录此次运行做了什么
- 一份 markdown 报告，概述此次自动化运行
- 如执行了标准化，则包含标准化目录
- 每个启用的分析能力各自的输出子目录

## 失败处理

- 如果标准化失败，应立即停止流程并报告错误。
- 如果某个下游步骤失败，应记录失败，并在未启用 fail-fast 时继续运行其余独立步骤。
- 不要静默替换 manifest 中已记录的输入文件。
