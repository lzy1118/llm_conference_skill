---
name: conference-visualization
description: Generate conference-analysis charts, ranked tables, paper-detail tables, and interactive collaboration networks from stable CSV or workbook outputs. Use when users request conference visualizations, a collaboration network for a specific year, one conference across a year range, ranked author or institution displays, or paper lists for a ranked entity.
---

# 顶会可视化

从稳定分析产物生成可复用图表和表格。不要在可视化层修补论文、作者或机构事实；发现名称、归属或去重问题时，先回到对应分析或标准化 skill 修正并重新生成输入。

读取 [可视化契约](references/visualization_contract.md) 确认字段、范围和输出规则。

## 选择入口

- 生成单个可视化或表格：直接读取对应 section 文件。
- 生成完整分析运行的图表包：运行 `scripts/generate_visualizations.py`。入口会自动识别当前 `analysis/<run>` 标准目录与旧版展示目录；当前目录缺少旧版覆盖率资料时，只生成实际可用的国家、机构、作者、趋势和会议规模图，不创建空的占位文件。
- 生成合作网络：先用 `conference-collaboration-analysis` 按请求范围重新聚合边，再运行 `scripts/generate_collaboration_network.py`。
- 仅在用户明确要求历史论文配图或复现实验产物时，才调用其他专项脚本；不要把专项脚本当成通用入口。

## 合作网络

### 解析范围

把用户请求转换为明确的 `mode + conference + year scope`：

- “2025 年合作网络”：使用 `--year 2025`，会议不设限。
- “CRYPTO 2020–2025 合作网络”：使用 `--conference CRYPTO --year-start 2020 --year-end 2025`。
- “某会议某一年”：同时使用 `--conference` 与 `--year`。
- 未说明实体层级时默认使用 `institution`；用户明确要求作者或国家合作时改用 `author` 或 `country`。

不要用已跨多年聚合的 `collaboration_edges.csv` 事后截取年份。它只保留 `year_first/year_last`，不能还原子区间内的准确共同论文数。必须从 `author_affiliation_facts.csv` 按范围重新聚合。

### 生成边表

```bash
python3 conference-collaboration-analysis/scripts/collaboration_analysis.py \
  --input <analysis-dir>/normalized/author_affiliation_facts.csv \
  --output-dir <temporary-analysis-dir> \
  --mode institution \
  --year 2025
```

```bash
python3 conference-collaboration-analysis/scripts/collaboration_analysis.py \
  --input <analysis-dir>/normalized/author_affiliation_facts.csv \
  --output-dir <temporary-analysis-dir> \
  --mode institution \
  --conference CRYPTO \
  --year-start 2020 \
  --year-end 2025
```

使用临时分析目录，避免覆盖现有全量 `collaboration/` 产物。

### 生成网络

```bash
python3 conference-visualization/scripts/generate_collaboration_network.py \
  --edges <temporary-analysis-dir>/collaboration/collaboration_edges.csv \
  --summary <temporary-analysis-dir>/collaboration/collaboration_summary.csv \
  --output <visualization-dir>/institution-collaboration-network.html \
  --data-output <visualization-dir>/institution-collaboration-network.json \
  --scope-label "CRYPTO 2020-2025 institution collaboration network"
```

输出为可直接嵌入对话的 HTML fragment。网络必须包含：

- 节点大小按加权合作强度；
- 边宽按 `shared_papers`；
- 默认阈值优先为 `shared_papers >= 2`，没有重复合作时回退为 `1`；
- 稀疏网络提供 `1+ / 2+ / 3+` 中真实可用的阈值；密集网络自动抬高最低阈值，使首层不超过 `--max-render-edges`；
- 头部合作边表；
- 节点点选后的最强合作摘要；
- 320px 与 736px 宽度下无整体横向溢出。

## 排名与论文明细

- 排名总览使用紧凑表格：`rank | entity | optional attribute | papers_count`。
- 第一作者榜在 `entity` 与 `papers_count` 之间使用英文列 `affiliation`。
- 参与作者榜在同一位置使用英文列 `primary_institution`。
- `primary_institution` 取该作者署名论文中出现次数最多的第一单位；并列时使用稳定、已记录的确定性规则。
- 用户追问某个排名实体对应论文时，使用 `conference | title | first_author` 三列表格；表格上方给出总数和按会议分布。
- 保留正式英文题目，不重复展示 `paper_id`、全体作者或未请求字段。
- 引用能完整覆盖明细行的精确 workbook sheet 和 range。

## 验证

每次生成后：

1. 核对范围、论文数、节点数、边数与合作分析 summary 一致。
2. 核对最强边与 `collaboration_edges.csv` 第一行一致。
3. 确认上游输入通过必需字段校验，且筛选后至少保留一行事实数据。
4. 检查 HTML 不包含文档外壳、`fetch`/XHR、未替换占位符或硬编码绝对路径。
5. 检查默认阈值、阈值切换、节点选择和头部边表。
6. 使用对话内可视化时，遵守当前 `visualize` skill 的 HTML、主题、响应式和最终指令规范。

## 输出约定

- 一个分析运行只使用一个可视化目录，建议命名为 `generated-data/visualizations/<analysis-run-name>`。
- 图表、对应 CSV 和 `visualization_manifest.json` 同目录保存；不要为同一数据重复创建临时脚本或多套平行输出目录。
- 入口根据输入中实际存在的 section 生成图表，并在 manifest 的 `sections` 和 `rendered_files` 中记录结果。

## 禁止事项

- 不要硬编码会议集合、年份范围或本机路径。
- 不要在可视化脚本中合并未经审核的机构别名。
- 不要用边的 `year_first/year_last` 猜测分年贡献。
- 不要默认运行历史专项脚本或生成与请求无关的整套图表。
