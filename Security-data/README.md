# 四大安全顶会作者机构国家数据采集

采集 USENIX Security、NDSS、IEEE S&P、ACM CCS 等安全顶会中的作者、机构与国家归属数据，并输出可复用的“作者-机构-国家”长表。历史美国机构切片仍兼容保留，但不再是主输出。

## 统计口径

主口径是“作者-机构-国家”长表：每条作者机构记录保留 `inst`、`country`、来源、置信度与审计字段。

`is_us_institution` 与 `*_美国机构.*` / `*_us_institutions.*` 文件仅作兼容已有美国机构统计链路的附加切片，不是默认主入口。

## 当前结果

| 会议 | 论文数 | 已展开作者行 | 已解析国家作者行 | 缺 affiliation |
|------|--------|-------------|------------------|---------------|
| USENIX Security 2025 | 439 | 2365 | 2365 中的已解析子集 | 4 |
| NDSS 2025 | 211 | 1145 | 1145 中的已解析子集 | 1 |
| IEEE S&P 2025 | 255 | 1166 | 1166 中的已解析子集 | 7 |
| ACM CCS 2025 | 314 (主会议) | 1695 | 1695 中的已解析子集 | 2 |
| **合计** | **1219** | **6371** | **按各会议 validation report 统计** | **14** |

## 快速开始

```bash
cd Security-data

# 安装依赖（如未安装）
uv pip install openpyxl

# 历史兼容入口：旧 Security-data pipeline
/Users/liziyu/llm_conference_us/.venv/bin/python3 scripts/security_us_pipeline.py \
  --conference usenix_security_2025 ndss_2025 ieee_sp_2025 ccs_2025 \
  --output-dir data --fetch

# 中性入口：转发到统一采集主线
python3 scripts/security_pipeline.py \
  --conference usenix_security_2025 ndss_2025 ieee_sp_2025 ccs_2025 \
  --output-dir data --fetch-affiliations

# 仅用缓存数据生成输出（不联网）
python3 scripts/security_pipeline.py \
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
    security_pipeline.py      中性入口，转发到统一主线
    security_us_pipeline.py   旧兼容 pipeline 脚本
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
| `data/output/四大安全顶会_作者机构国家.csv` | 正式主 CSV 输出 |
| `data/output/四大安全顶会_作者机构国家.xlsx` | 正式主 Excel 输出 |
| `data/output/四大安全顶会_美国机构.csv` | 历史兼容美国机构切片 |
| `data/output/四大安全顶会_美国机构.xlsx` | 历史兼容美国机构切片 |
| `data/output/四大安全顶会_美国机构_audit.csv` | 历史兼容美国机构切片审计表 |

主表字段：`name`, `year`, `article_tag`, `author_order`, `inst`, `country`

## override 规则

在 `data/reference/institution_country_overrides.csv` 中添加：

```csv
inst,country,is_us_institution,reason
Example Lab,United States,true,manual_review
```

## 测试

```bash
/Users/liziyu/llm_conference_us/.venv/bin/python3 -m unittest discover -s tests -v
```
