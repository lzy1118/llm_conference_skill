# 安全顶会作者机构国家数据采集 - 历史进度交接文档

> 说明：这份文档记录的是旧 `Security-data/` 阶段的交接状态。
> 当前仓库正式主契约已经切换为“作者-机构-国家”长表。
> 文中涉及的“美国机构”表述应理解为当时保留的兼容切片目标，而不是当前默认主输出。

## 当前目标

采集 USENIX Security 2025、NDSS 2025、IEEE S&P 2025、ACM CCS 2025 四大安全顶会中的作者、机构与国家归属数据，并在需要时兼容导出历史美国机构切片。

## 已完成

1. **项目结构** — `Security-data/` 目录已创建，包含 `data/`、`scripts/`、`tests/`、`Plan/`
2. **旧兼容 Pipeline 脚本** — `scripts/security_us_pipeline.py` 在当时已实现完整流程：
   - DBLP XML 抓取论文数据
   - USENIX Security: `citation_author_institution` meta 标签抓取 affiliations
   - NDSS: `Author (Institution)` 格式解析
   - IEEE S&P: IEEE Xplore JSON metadata 解析
   - ACM CCS: Semantic Scholar API fallback（ACM DL 封禁请求）
   - 机构归属分类规则（当时仍保留美国机构兼容切片逻辑）
   - 输出 Excel/CSV 主表和审计表
3. **Raw 论文数据** — `data/raw/` 下四会议 JSON 全部抓取完成：
   - `usenix_security_2025_papers.json`: 439 篇
   - `ndss_2025_papers.json`: 211 篇
   - `ieee_sp_2025_papers.json`: 255 篇
   - `ccs_2025_papers.json`: 390 篇
   - 合计 1295 篇
4. **Affiliation 缓存** — `data/resolution/affiliation_cache/` 已缓存 513 条（主要是 NDSS 80 条 + 部分其他会议）

## 未完成

1. **Affiliation 抓取未完成** — USENIX (0/439)、IEEE S&P (0/255)、CCS (0/390) 尚未缓存；NDSS 只完成 80/211
2. **Pipeline 未跑完** — 上次运行被中断，需要重新执行
3. **复核队列处理** — 无 affiliation 数据的论文需要进入复核队列
4. **enriched 输出** — 尚未生成最终合并结果
5. **override 文件** — `data/reference/institution_country_overrides.csv` 尚未创建
6. **README** — 尚未编写

## 继续执行命令

```bash
# 历史兼容命令（旧 Security-data 流程）
cd /Users/liziyu/llm_conference_us/Security-data
/Users/liziyu/llm_conference_us/.venv/bin/python3 scripts/security_us_pipeline.py \
  --conference usenix_security_2025 ndss_2025 ieee_sp_2025 ccs_2025 \
  --output-dir data \
  --fetch-affiliations

# 当前正式主入口应优先使用统一入口
python3 conference-paper-extraction/scripts/run_unified_pipeline.py \
  --group top4_security \
  --output-dir data \
  --fetch-affiliations
```

## 关键注意事项

1. **请求限流** — 脚本已有 0.3 秒延迟，但 DBLP 和 Semantic Scholar 可能限流更严。如果遇到 429 错误，等几秒重试
2. **CCS 数据源** — ACM DL 封禁 HTTP 请求，CCS affiliations 使用 Semantic Scholar API，可能不完整
3. **缓存机制** — 已抓取的 affiliation 存在 `data/resolution/affiliation_cache/`，重跑会自动复用
4. **输出格式** — 当前正式主表应优先包含 `name`, `year`, `article_tag`, `author_order`, `inst`, `country`；若需要兼容历史美国机构切片，可额外导出旧格式子集
5. **article_tag 格式** — `USENIX_SECURITY-<title>`、`NDSS-<title>`、`IEEE_S&P-<title>`、`CCS-<title>`

## 文件位置

- 主脚本（历史兼容）: `Security-data/scripts/security_us_pipeline.py`
- Raw 数据: `Security-data/data/raw/*.json`
- Affiliation 缓存: `Security-data/data/resolution/affiliation_cache/`
- 输出目录: `Security-data/data/output/`
- 中间结果: `Security-data/data/interim/`
