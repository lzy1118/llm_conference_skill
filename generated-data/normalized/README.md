# 标准化数据目录

该目录用于统一保存标准化阶段的共享事实表与维表。

## 典型来源

- `conference-dataset-normalization/scripts/normalize_dataset.py`

在未显式传入 `--output-dir` 时，标准化脚本默认会把结果写到仓库根目录下的 `generated-data/normalized/`。

## 典型文件

- `author_affiliation_facts.csv`
- `paper_facts.csv`
- `institution_dim.csv`
- `normalization_report.json`

## 作用

- 作为国家、机构、作者、趋势、合作分析的共享输入层
- 作为后续自动化分析的标准事实表目录
- 避免下游分析重复回读抽取层原始输出

## 当前状态

当前目录已写入主标准化产物，包括：

- `author_affiliation_facts.csv`
- `paper_facts.csv`
- `institution_dim.csv`
- `normalization_report.json`

后续新的标准化主链路结果仍应优先集中保存在这里。
