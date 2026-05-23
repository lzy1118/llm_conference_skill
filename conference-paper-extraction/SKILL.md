---
name: conference-paper-extraction
description: Extract author affiliation data from top academic conferences (crypto, security, AI/ML). Use when analyzing conference papers, tracking institutional publications, or building research output reports. Supports IACR, DBLP, IEEE Xplore, ACM DL, and Semantic Scholar data sources.
license: MIT
compatibility: Requires Python 3.10+, openpyxl, pypdf
metadata:
  author: llm-conference-skill
  version: "1.0"
allowed-tools: Bash(python3:*) Read Glob Grep
---

# 顶会论文抽取

从密码学、安全、AI/ML 等顶会中抽取作者与机构归属数据，尤其适合生成后续机构统计、国家统计与研究产出报告所需的基础数据。

当前推荐通过统一入口运行三大密码会与四大安全会采集。该入口位于 skill 内部，用统一 registry 选择会议，再按后端能力路由到 skill 内部的真实采集实现。

`scripts/run_unified_pipeline.py` 是正式主入口。`scripts/conference_pipeline.py` 仅保留为兼容转发层，避免旧命令立即失效，但不再承载独立实现。

## 支持的会议类型

| 类型 | 会议 | 数据来源 |
|------|------|----------|
| IACR 密码学 | Asiacrypt, Crypto, Eurocrypt | IACR JSON API |
| 安全 | USENIX Security, NDSS, IEEE S&P, ACM CCS | DBLP + 会议元数据 API |
| AI/ML | NeurIPS, ICML, ICLR | OpenReview + Semantic Scholar |

## 快速开始

```bash
# 安装依赖
uv pip install openpyxl pypdf

# 查看统一 registry 中的会议与分组
python3 scripts/run_unified_pipeline.py --list-conferences

# 运行三大密码会
python3 scripts/run_unified_pipeline.py --group top3_crypto --output-dir data

# 运行四大安全会，并抓取站点 affiliation
python3 scripts/run_unified_pipeline.py --group top4_security --output-dir data --fetch-affiliations

# 同时运行指定密码会与安全会
python3 scripts/run_unified_pipeline.py --conference crypto_2025 --conference usenix_security_2022 --output-dir data

# 查看执行计划但不实际运行
python3 scripts/run_unified_pipeline.py --group top3_crypto --dry-run --output-dir data

# 对 IACR mismatch 论文生成内部补源候选
python3 scripts/run_unified_pipeline.py --conference crypto_2025 --output-dir data --resolve-mismatches

# 如需在 IACR mismatch 阶段额外查询 DBLP
python3 scripts/run_unified_pipeline.py --conference crypto_2025 --output-dir data --resolve-mismatches --query-dblp-for-resolution
```

## 当前统一入口覆盖范围

| 分组 | 覆盖会议 | 当前后端 |
|------|----------|----------|
| `top3_crypto` | Asiacrypt / Crypto / Eurocrypt | `scripts/iacr_top3_backend.py` |
| `top4_security` | USENIX Security / NDSS / IEEE S&P / CCS | `scripts/security_real_backend.py` |

这一步已经把用户入口和两类真实后端都统一到 `conference-paper-extraction/` 内部。后续还可以继续做规则去重和共享模块抽象，但当前已经不再依赖外部目录脚本作为正式执行入口。

每次实际运行结束后，统一入口会在 `output-dir` 根目录写出 `unified_run_manifest.json`，用于记录：

- 选择了哪些会议
- 路由到了哪些 backend
- 实际执行了哪些命令
- 每一步的返回码

当对 IACR 会议启用 `--resolve-mismatches` 时，还会在 `output-dir/resolution/<conference_key>/` 下写出内部 resolution 阶段产物。

## 核心流程

### 第 1 步：选择会议范围

统一入口通过内置 registry 管理会议，不要求用户手工维护单独的 `conference_config.json`。常见方式如下：

```bash
# 查看所有内置会议与分组
python3 scripts/run_unified_pipeline.py --list-conferences

# 运行所有已注册会议
python3 scripts/run_unified_pipeline.py --group all --output-dir data
```

### 第 2 步：抓取论文数据

**IACR JSON：**

```python
import urllib.request, json
url = f"https://{conference}.iacr.org/{year}/json/papers.json"
data = json.loads(urllib.request.urlopen(url).read())
papers = data.get("acceptedPapers", [])
```

**DBLP XML：**

```python
import xml.etree.ElementTree as ET
url = f"https://dblp.org/db/conf/{venue_key}/{venue_key}{year}.xml"
root = ET.parse(urllib.request.urlopen(url)).getroot()
for article in root.findall(".//inproceedings"):
    title = article.find("title").text
    authors = [a.text for a in article.findall(".//author")]
```

### 第 3 步：抽取机构归属

不同会议可采用不同策略，详见 [机构来源参考](references/affiliation_sources.md)。

### 第 4 步：识别国家与机构归属

当前采集层会同时生成：

- `country`
- `is_us_institution`（可选兼容标记）

其中：

- `country` 是正式主字段，用于后续国家统计、机构统计与泛化分析。
- `is_us_institution` 只是从 `country` 派生出来的兼容标记，保留它是为了兼容已有美国机构统计链路，而不是让采集层继续以美国机构为主视角。

分类流程采用“可解释国家判定 + 多机构保守聚合 + 未解析回退”的策略：

```python
def classify_affiliation(affiliation: str) -> dict:
    lower = affiliation.casefold().strip()

    # 第 1 层：精确别名匹配（可命中美国机构，也可命中其他高频稳定简称）
    if lower in US_EXACT_ALIASES:
        return {"country": "United States", "is_us": True, "source": "rule", "confidence": 1.0}

    # 第 2 层：国家关键词识别（例如 China, Canada, Switzerland）
    country = detect_country(lower)
    if country:
        return {"country": country, "is_us": country == "United States", "source": "rule", "confidence": 0.95}

    # 第 3 层：无法可靠判断时保守保留 Unknown，进入复核队列
    return {"country": "Unknown", "is_us": False, "source": "unresolved", "confidence": 0.0}
```

这个示例强调的是“先做国家判定，再从国家派生兼容布尔值”，而不是让 `is_us_institution` 主导分类流程。

完整规则见 [分类规则参考](references/classification_rules.md)。

### 第 5 步：生成输出

当前正式主输出是“作者-机构-国家”长表，不再把美国机构导出视为唯一主产物。

**主输出：**

- `output/<conference_key>_author_affiliations.csv`
- `output/<conference_key>_author_affiliations_audit.csv`
- `output/<conference_key>_author_affiliations.xlsx`
- 多会议汇总时：
  - 安全会：`output/四大安全顶会_作者机构国家.csv`
  - 密码会：`output/2025-2026三大密码会_作者机构国家.csv`

兼容输出仍会保留美国机构子集：

- `*_us_institutions.csv`
- `*_us_institutions_audit.csv`
- `*_us_institutions.xlsx`

中间候选主文件也改为泛化命名：

- `interim/institution_classification_candidates.csv`

旧文件名 `interim/us_institution_candidates.csv` 仍保留，作为兼容别名。

**基础输出字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 作者姓名 |
| `year` | integer | 发表年份 |
| `article_tag` | string | `{CONFERENCE}-{Title}` |
| `author_order` | integer | 从 0 开始的作者顺序 |
| `inst` | string | 机构归属文本 |
| `country` | string | 机构所属国家，无法可靠判断时为 `Unknown` |
| `is_us_institution` | boolean | 兼容字段，仅用于保留旧美国机构切片链路 |

**审计字段（附加）：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `conference` | string | 会议代码 |
| `paper_id` | string | 源数据论文 ID |
| `title` | string | 论文标题 |
| `country` | string | 国家判定结果 |
| `classification_source` | string | rule/override/source_pdf |
| `classification_confidence` | float | 0.0-1.0 |
| `classification_reason` | string | 判定原因 |

### 第 6 步：复核与补充

处理不匹配与未解析归属：

```bash
# 统一入口运行后，优先检查中间产物
data/interim/affiliation_resolution_queue.csv
data/interim/institution_classification_candidates.csv

# 对安全会，可在需要时启用站点机构抓取
python3 scripts/run_unified_pipeline.py --group top4_security --output-dir data --fetch-affiliations

# 对密码会，未解析机构会保守保留在待复核结果中
data/interim/llm_resolution_input.jsonl

# 对 IACR mismatch 论文，可生成内部补源候选与 resolution report
python3 scripts/run_unified_pipeline.py --conference crypto_2025 --output-dir data --resolve-mismatches
```

启用后，常见产物包括：

- `resolution/<conference_key>/source_candidates.csv`
- `resolution/<conference_key>/search_results.csv`
- `resolution/<conference_key>/unresolved_after_source_lookup.csv`
- `resolution/<conference_key>/resolution_report.json`

当前这一步仍然是保守型 resolution stage：优先生成候选来源、保留待复核上下文，并为后续更强的 frontmatter/PDF 自动接受逻辑预留接口。

## 报告字段说明

validation report 中优先关注以下泛化字段：

- `papers_count`
- `papers_with_author_rows`
- `papers_without_affiliation_data`
- `expanded_author_rows`
- `classified_author_rows`
- `resolved_country_rows`
- `unresolved_country_rows`

其中：

- `resolved_country_rows` 与 `classified_author_rows` 当前等价
- `unresolved_country_rows` 表示仍保留为 `Unknown` 的作者-机构行数
- `us_author_rows` 仅是兼容字段，用于旧美国机构统计链路；新的自动化与统计入口应优先使用 `resolved_country_rows` / `unresolved_country_rows`

## 目录结构

```text
conference-data/
  scripts/           流水线脚本
  data/
    raw/             原始数据快照
    interim/         中间结果
    reference/       覆盖规则与模式文件
    output/          最终 CSV/Excel 输出
    resolution/      复核缓存
  tests/             单元测试
```

## 关键设计模式

1. **缓存**：所有 API 响应本地缓存，重跑可复用
2. **限流**：请求间隔 0.3-1.5 秒，避免被封
3. **断点续跑**：支持 `--start` / `--limit` 批处理
4. **审计追踪**：保留所有中间结果与来源字段
5. **覆盖机制**：使用 `institution_country_overrides.csv` 做人工修正

## 泛化原则

- 正式主契约是作者、机构、国家三者的稳定长表。
- 美国统计只是消费层的一种切片，不应反向主导抽取层设计。
- 对中国机构、欧洲机构、跨国机构等应保持同样的判定与审计结构。
- 无法可靠判断时保持 `Unknown`，不要因为后续想做美国统计或中国统计就硬猜。

## 常见问题

- **作者数与机构数不匹配**：进入 PDF / 来源复核流程
- **API 被限制**：使用备选来源，如 OpenAlex
- **作者名存在变体**：必要时用姓 + 名首字母做辅助匹配
