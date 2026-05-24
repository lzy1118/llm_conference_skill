# 顶会作者机构国家数据采集项目

采集密码学和信息安全领域顶会中的作者、机构与国家归属数据，并支持国家、机构、作者等多维统计分析。

## 子项目

| 子项目 | 会议 | 结果 |
|--------|------|------|
| `Top3-data/` | Asiacrypt 2025, Crypto 2025, Eurocrypt 2026 | 377 行 |
| `Security-data/` | USENIX Security 2025, NDSS 2025, IEEE S&P 2025, CCS 2025 | 1575 行 |

详细说明见各子项目 README。

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

`is_us_institution` 与 `*_us_institutions.*` 仍然保留，但仅作兼容已有美国机构统计链路的附加切片，不再是仓库主叙事或默认主输出。

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
