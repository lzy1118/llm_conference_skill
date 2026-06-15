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

## 口径说明

- `normalization_report.json` 中的 `rows_missing_name` 与 `rows_missing_inst` 仅表示“已进入标准化作者机构事实表的行”里是否存在空作者名或空机构名。
- 这两个指标不能等同于“论文级作者机构缺失已经清零”。
- 论文级缺失应以 `generated-data/coverage/paper_completeness_audit.csv` 为准，重点关注：
  - `coverage_status = missing`：论文级没有作者机构行
  - `coverage_status = partial`：论文级仅部分 affiliation 覆盖
  - `coverage_status = complete_unverified`：论文级覆盖完整，但仍保留未人工复核语义
- 当前目录只保留现行主标准化结果；历史或旧口径标准化快照不应继续放在本目录下与当前结果并列。
