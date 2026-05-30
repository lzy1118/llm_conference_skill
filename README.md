# 顶会作者机构国家数据采集项目

采集密码学和信息安全领域顶会中的作者、机构与国家归属数据，并支持国家、机构、作者等多维统计分析。

## 子项目

| 子项目 | 会议 | 结果 |
|--------|------|------|
| `conference-paper-extraction/` | 三大密码会、四大安全会、AI/ML 入口 | 统一采集主线 |
| `generated-data/` | 抽取、标准化、分析、报告、可视化产物 | 统一结果目录 |

当前主线以 `conference-paper-extraction/` 与 `generated-data/` 为准；`data/` 目录现仅保留机构 reference。

## Skills

仓库当前包含以下 Agent Skills：

| Skill | 作用 |
|------|------|
| `conference-paper-extraction/` | 从顶会来源抓取论文与作者机构数据 |
| `conference-dataset-normalization/` | 将抽取结果标准化为可复用分析数据集 |
| `conference-country-statistics/` | 生成国别统计、份额、趋势分析 |
| `conference-institution-statistics/` | 生成机构排名、参与度与跨年趋势 |
| `conference-author-statistics/` | 生成作者产出、首作者、合作网络统计 |

推荐使用顺序：`conference-paper-extraction` -> `conference-dataset-normalization` -> 各类统计分析 skill。

## 主统计口径

主口径是“作者-机构-国家”长表：每一条作者机构归属都保留原始机构文本、国家判定、来源、置信度与审计信息。

国家字段只使用 `country`；不再生成或消费额外的美国布尔标记。

## 统一生成数据目录

仓库根目录已新增 `generated-data/`，用于统一管理最终有用的生成数据文件。后续推荐把主要产物集中写到这里：

- `generated-data/extraction/`：统一采集输出
- `generated-data/normalized/`：标准化事实表与维表
- `generated-data/analysis/`：国家、机构、作者、趋势、合作、审计分析结果
- `generated-data/reports/`：报告
- `generated-data/visualizations/`：可视化
- `generated-data/manifests/`：运行记录

具体命令示例见 `generated-data/README.md`。

## 通用依赖

```bash
uv pip install openpyxl pypdf
```
