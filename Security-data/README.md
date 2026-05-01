# 四大安全顶会美国机构数据采集

采集 USENIX Security 2025、NDSS 2025、IEEE S&P 2025、ACM CCS 2025 四大安全顶会中美国机构作者发表情况，输出与 `2020-2024三大密码会.xlsx` 英文版格式对齐的长表。

## 统计口径

按"美国机构"判定：只要作者 affiliation 为美国机构即计入，不按国籍推断。

## 当前结果

| 会议 | 论文数 | 已展开作者行 | 美国机构作者行 | 缺 affiliation |
|------|--------|-------------|--------------|---------------|
| USENIX Security 2025 | 439 | 2365 | 495 | 4 |
| NDSS 2025 | 211 | 1145 | 263 | 1 |
| IEEE S&P 2025 | 255 | 1166 | 401 | 7 |
| ACM CCS 2025 | 390 | 1695 | 442 | 2 |
| **合计** | **1295** | **6371** | **1601** | **14** |

## 快速开始

```bash
cd Security-data

# 安装依赖（如未安装）
uv pip install openpyxl

# 从 DBLP 抓取论文数据
/Users/liziyu/llm_conference_us/.venv/bin/python3 scripts/security_us_pipeline.py \
  --conference usenix_security_2025 ndss_2025 ieee_sp_2025 ccs_2025 \
  --output-dir data --fetch

# 抓取 affiliations 并生成输出
/Users/liziyu/llm_conference_us/.venv/bin/python3 scripts/security_us_pipeline.py \
  --conference usenix_security_2025 ndss_2025 ieee_sp_2025 ccs_2025 \
  --output-dir data --fetch-affiliations

# 仅用缓存数据生成输出（不联网）
/Users/liziyu/llm_conference_us/.venv/bin/python3 scripts/security_us_pipeline.py \
  --conference usenix_security_2025 ndss_2025 ieee_sp_2025 ccs_2025 \
  --output-dir data
```

## 数据来源

| 会议 | 论文来源 | Affiliation 来源 |
|------|---------|-----------------|
| USENIX Security | DBLP XML | USENIX 网站 `citation_author_institution` meta 标签 |
| NDSS | DBLP XML | NDSS 网站 `Author (Institution)` 格式 |
| IEEE S&P | DBLP XML | IEEE Xplore JSON metadata（部分页面需 JS 渲染） |
| ACM CCS | DBLP XML | ACM DL 封禁请求，Semantic Scholar API 受限 |

## 目录结构

```
Security-data/
  Plan/              规划文档
  scripts/
    security_us_pipeline.py   主 pipeline 脚本
  data/
    raw/             DBLP 论文 JSON 快照
    interim/         中间结果（规范化表、复核队列）
    reference/       override 规则
    output/          最终 Excel/CSV 输出
    resolution/      affiliation 缓存
  tests/             测试
```

## 输出文件

| 文件 | 说明 |
|------|------|
| `data/output/四大安全顶会_美国机构.xlsx` | 最终 Excel 主表 |
| `data/output/四大安全顶会_美国机构.csv` | CSV 主表 |
| `data/output/四大安全顶会_美国机构_audit.csv` | 审计表（含 conference、paper_id、判定来源） |

主表字段：`name`, `year`, `article_tag`, `author_order`, `inst`

## override 规则

在 `data/reference/institution_country_overrides.csv` 中添加：

```csv
inst,is_us_institution,reason
Example Lab,true,manual_review
```

## 测试

```bash
/Users/liziyu/llm_conference_us/.venv/bin/python3 -m unittest discover -s tests -v
```
