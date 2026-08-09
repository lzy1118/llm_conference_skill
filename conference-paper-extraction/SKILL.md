---
name: conference-paper-extraction
description: Build four-security-conference paper metadata CSV files from raw papers.json files, with optional affiliation text enrichment and no country/classification output.
license: MIT
compatibility: Requires Python 3.10+, beautifulsoup4
metadata:
  author: llm-conference-skill
  version: "2.0"
allowed-tools: Bash(python3:*) Read Glob Grep
---

# 安全会论文元数据生成

当前脚本目录已清理为四大安全会 metadata 工作流。主目标是从已有 raw JSON 生成每个会议的 `paper_metadata.csv`，并尽量补充作者机构文本。

## 当前保留脚本

| 脚本 | 作用 |
|---|---|
| `build_paper_metadata_with_affiliations.py` | 主入口：生成四会 `paper_metadata.csv` |
| `security_real_backend.py` | 安全会官网/DBLP/ACM/IEEE 机构补源函数库 |
| `backend_common.py` | CSV/Excel 等通用写入工具 |
| `api_runtime.py` | 低速率 API 请求工具 |
| `classification_common.py` | 旧 backend 仍引用的通用文本规范化/规则模块 |

## 输入

```text
generated-data/extraction/raw/by_conference/*/papers.json
```

## 输出

```text
generated-data/ccs_full_output/paper_metadata.csv
generated-data/ieee_sp_full_output/paper_metadata.csv
generated-data/ndss_full_output/paper_metadata.csv
generated-data/usenix_security_full_output/paper_metadata.csv
```

表头固定为：

```csv
year,conference,title,author,author_rank,affiliations
```

## 运行

```bash
python3 conference-paper-extraction/scripts/build_paper_metadata_with_affiliations.py \
  --generated-data-dir generated-data
```

如只希望使用官网列表和本地缓存，不访问 DOI/OpenAlex/Semantic Scholar 等慢速兜底源：

```bash
python3 conference-paper-extraction/scripts/build_paper_metadata_with_affiliations.py \
  --generated-data-dir generated-data \
  --no-network
```

## 当前口径

- 只补充 `affiliations` 文本。
- 不生成国家字段。
- 不生成 `classification_source`、`classification_confidence`、`classification_reason`。
- 不生成作者机构国家长表、PDF manifest、validation report。
- IEEE S&P 生成时优先用官方标题修正 DBLP raw title，并从官方页面拆分 `Name (Affiliation)` 样式的作者机构。
