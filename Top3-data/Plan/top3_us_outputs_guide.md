# 三大密码会数据产物说明（含历史美国机构兼容切片）

## 这份文档的用途

本文档说明本次三大密码会美国机构数据采集工作生成了哪些文件、每个文件夹负责什么、不同文件后缀代表什么含义，以及后续人工复核时应该看哪些文件。

这份文档最初围绕“美国机构”兼容切片编写。当前仓库的正式主契约已经升级为“作者-机构-国家”长表；文中 `*_美国机构.*` 与 `*_us_institutions.*` 应理解为历史兼容输出，而不是默认主输出。若 IACR 原始 JSON 中 `authors[]` 和 `affiliations[]` 数量不一致，则不强行把机构分配给作者，而是进入复核队列。

## 当前结果概览

- 三会论文总数：`441`
- 可直接展开的作者机构行：`363`
- 历史美国机构兼容切片中的作者行：`133`
- 作者数与机构数不一致、需复核的论文：`311`
- 尚未规则判定、需人工或 LLM 复核的机构候选：`149`

分会议结果：

- `ASIACRYPT 2025`: 论文 `143` 篇，历史美国机构兼容切片作者行 `32` 行，需复核论文 `106` 篇。
- `CRYPTO 2025`: 论文 `156` 篇，历史美国机构兼容切片作者行 `59` 行，需复核论文 `103` 篇。
- `EUROCRYPT 2026`: 论文 `142` 篇，历史美国机构兼容切片作者行 `42` 行，需复核论文 `102` 篇。

## 文件夹说明

### `Plan/`

保存规划和说明文档。

- `top3_us_institutions_workflow.md`: 原始工作流计划，说明目标、数据源、目录结构、判定规则和验证标准。
- `top3_us_outputs_guide.md`: 当前这份产物说明文档。

### `data/raw/`

保存从 IACR 获取的原始数据快照和抓取元数据。这里的文件用于保证后续可以复现同一次处理结果。

- `asiacrypt_2025_papers.json`: Asiacrypt 2025 的原始论文 JSON。
- `crypto_2025_papers.json`: Crypto 2025 的原始论文 JSON。
- `eurocrypt_2026_papers.json`: Eurocrypt 2026 的原始论文 JSON。
- `*_fetch_metadata.json`: 单个会议的抓取来源、文件大小、哈希等元数据。
- `fetch_metadata.json`: 三个会议抓取元数据的汇总。

### `data/interim/`

保存中间结果。这里的文件主要用于排查、复核和扩展规则，不建议直接作为最终交付表。

- `papers_normalized.csv`: 三会论文级规范化表，一行一篇论文，包含会议、年份、`paper_id`、标题、作者数、机构数等。
- `author_affiliations_expanded.csv`: 三会作者机构展开表，一行一个作者机构匹配结果。只包含作者数和机构数能一一对应的论文。
- `us_institution_candidates.csv`: 历史兼容候选表。当前主用候选文件应优先看泛化命名的 `institution_classification_candidates.csv`。
- `affiliation_resolution_queue.csv`: 复核队列。这里保存 `authors[]` 和 `affiliations[]` 数量不一致的论文，不能直接自动分配作者机构。
- `llm_resolution_input.jsonl`: 给 LLM 或人工复核使用的疑难机构输入。
- `llm_resolution_output.jsonl`: 当前保守复核结果。未确认的机构都保留为 `needs_manual_review = true`。
- `<conference>_author_affiliations_expanded.csv`: 单个会议版本的作者机构展开表。
- `<conference>_affiliation_resolution_queue.csv`: 单个会议版本的复核队列。

### `data/reference/`

保存参考格式和人工覆盖规则。

- `reference_schema.json`: 从 `2020-2024三大密码会.xlsx` 的 `英文版` sheet 解析出的表头和样例。当前正式主表应优先保留 `name`, `year`, `article_tag`, `author_order`, `inst`, `country`，同时在需要时兼容导出旧字段子集。
- `institution_country_overrides.csv`: 人工覆盖规则。后续如果确认某个机构应计入或排除，可以在这里写入，再重跑脚本。

### `data/output/`

保存最终输出和校验报告。通常优先看这个目录。

- `2025-2026三大密码会_作者机构国家.xlsx/.csv`: 当前正式主输出。
- `2025-2026三大密码会_美国机构.xlsx/.csv`: 历史美国机构兼容切片。
- `2025-2026三大密码会_美国机构_audit.csv`: 历史美国机构兼容切片审计表。
- `validation_report.json`: 三会合并校验报告，记录论文总数、输出行数、复核队列规模等。
- `<conference>_us_institutions.xlsx`: 单个会议的最终 Excel。
- `<conference>_us_institutions.csv`: 单个会议的最终 CSV。
- `<conference>_us_institutions_audit.csv`: 单个会议的审计表。
- `<conference>_validation_report.json`: 单个会议的校验报告。

### `scripts/`

保存处理脚本。

- `top3_us_pipeline.py`: 历史旧主流水线脚本，属于 compatibility-only 入口。当前正式抽取主入口应优先看统一入口与泛化 backend。

常用命令：

```bash
# 历史兼容命令
python3 scripts/top3_us_pipeline.py --conference all --output-dir data

# 中性入口：转发到 unified runner
python3 scripts/top3_pipeline.py --conference all --output-dir data
```

### `tests/`

保存自动化测试。

- `test_top3_us_pipeline.py`: 历史旧流水线测试。当前主链路测试应优先看 unified / backend / analysis tests。

常用命令：

```bash
python3 -m unittest tests.test_top3_us_pipeline -v
```

## 后缀含义

### `.xlsx`

Excel 工作簿，适合人工打开、检查和继续整理。本项目最终交付优先看 `.xlsx`。

### `.csv`

逗号分隔文本表格，适合脚本处理、版本对比和导入数据库。最终主表和审计表都同时保存了 `.csv`。

### `.json`

结构化 JSON 文件。本项目里主要用于原始 IACR 数据、抓取元数据、参考 schema 和校验报告。

### `.jsonl`

JSON Lines 文件，一行一个 JSON 对象。适合存放 LLM 批处理输入输出，也适合逐行追加和复核。

### `.py`

Python 脚本或测试文件。`scripts/` 下是生产处理脚本，`tests/` 下是测试代码。

### `.md`

Markdown 文档，用于保存计划、说明和工作流记录。

## 主表与审计表的区别

主表只保留参考 Excel 英文版要求的字段：

- `name`
- `year`
- `article_tag`
- `author_order`
- `inst`

审计表保留更多追溯字段：

- `conference`
- `year`
- `paper_id`
- `title`
- `name`
- `article_tag`
- `author_order`
- `inst`
- `classification_source`
- `classification_confidence`
- `classification_reason`

如果只是要延续 `2020-2024三大密码会.xlsx` 的旧格式，可查看历史兼容主表。如果要做当前泛化分析，应优先使用“作者-机构-国家”主输出与对应审计表。

## 后续复核建议

优先复核 `data/interim/affiliation_resolution_queue.csv`。这个文件里的论文占多数，因为 IACR JSON 经常只给论文级机构列表，而不是作者级机构列表。只有确认作者和机构对应关系后，才建议通过 `data/reference/institution_country_overrides.csv` 或额外人工补表进入最终主表。

其次复核 `data/interim/llm_resolution_input.jsonl`。这里是规则未能判定的机构字符串，确认后可以写入 override，再运行：

```bash
# 历史兼容重跑命令
python3 scripts/top3_us_pipeline.py --conference all --output-dir data

# 当前主链路优先重跑中性入口或 unified runner
python3 scripts/top3_pipeline.py --conference all --output-dir data
```
