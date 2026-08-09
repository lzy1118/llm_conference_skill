# 可视化契约

## 稳定输入

| 类型 | 默认输入 | 主要指标 |
| --- | --- | --- |
| 国家排名 | `country/country_summary.csv` | `papers` |
| 机构排名 | `institutions/institution_summary.csv` | `papers` |
| 作者排名 | `authors/author_summary.csv`、`authors/first_author_summary.csv` | `papers` |
| 趋势 | `trends/trend_summary.csv` 及对应按年表 | 年度 `papers` |
| 合作 | `collaboration/collaboration_edges.csv`、`collaboration_summary.csv` | `shared_papers` |
| 排名明细 | 正式排名 workbook 的明细 sheet | 论文行 |

不得把临时抽取文件或未经标准化的 PDF 文本直接作为可视化事实源。

## 合作范围契约

精确范围必须在边聚合前应用于 normalized author-affiliation rows：

| 请求 | 聚合参数 |
| --- | --- |
| 某一年、全部会议 | `--year Y` |
| 某会议、某一年 | `--conference C --year Y` |
| 某会议、连续年份 | `--conference C --year-start A --year-end B` |
| 全部会议、连续年份 | `--year-start A --year-end B` |

边表至少包含：`mode`、`left_key`、`left_name`、`right_key`、`right_name`、`shared_papers`、`conference_count`、`year_first`、`year_last`。

摘要至少包含：`mode`、`paper_count`、`node_count`、`edge_count`、`repeated_edge_count`、`max_shared_papers`。

## 默认展示映射

- 国家、机构、作者排名：横向条形图或紧凑排名表。
- 趋势：按年份折线图。
- 合作：交互式网络 + 头部合作边表；静态报告可补头部边横向条形图。
- 第一作者排名：`rank | entity | affiliation | papers_count`。
- 参与作者排名：`rank | entity | primary_institution | papers_count`。
- 排名实体论文明细：`conference | title | first_author`。

`affiliation` 与 `primary_institution` 使用英文机构名。作者主要机构按其署名论文第一单位出现次数选择。

## 输出要求

- 只为实际存在且非空的输入生成可视化。
- 使用 ASCII 小写连字符文件名；正文实体名保留正式英文拼写。
- 输出或 manifest 记录输入路径、范围、生成文件、缺失或空 section、`top_n` 和阈值。
- 网络数据 JSON 记录节点的 `weighted_degree`、`degree` 与边的 `shared_papers`。
- 对话内 HTML fragment 遵守当前 `visualize` skill；项目归档优先保留 SVG、PNG 或经渲染的 standalone HTML。
- 数据质量修正必须发生在标准化或合作分析层，并在重新聚合后进入可视化。
