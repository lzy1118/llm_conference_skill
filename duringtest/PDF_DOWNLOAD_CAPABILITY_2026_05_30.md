# 论文 PDF 下载能力实验记录

## 1. 目标

- 为统一抽取入口补充“只下载 PDF、不解析 PDF”的正式能力。
- 让 PDF 成为主流程中的可选稳定产物，方便后续人工复核、frontmatter 解析或角色补齐实验复用。

## 2. 新增接口

统一入口新增参数：

- `--download-pdfs`
- `--pdf-limit`

示例：

```bash
python3 conference-paper-extraction/scripts/run_unified_pipeline.py --conference usenix_security_2020 --output-dir generated-data/extraction --download-pdfs
python3 conference-paper-extraction/scripts/run_unified_pipeline.py --conference usenix_security_2020 --output-dir generated-data/extraction --download-pdfs --pdf-limit 5
```

## 3. 当前实现策略

### 3.1 安全会

- 先读取 raw paper metadata 中的 landing page `url`
- 如果不是 `.pdf` 直链，就抓 landing page HTML
- 再从页面中查找 `.pdf` 链接并下载

### 3.2 IACR 会议

- 只在 raw metadata 中已有 `.pdf` 直链时下载
- 当前不额外做页面级 PDF 链接探测

## 4. 输出契约

- PDF 目录：`generated-data/extraction/pdfs/<conference_key>/`
- 下载审计表：`generated-data/extraction/interim/<conference_key>_pdf_download_report.csv`
- 下载摘要：`generated-data/extraction/interim/<conference_key>_pdf_download_summary.json`

## 5. 已验证结果

### 5.1 USENIX Security 2020

- papers_seen: 159
- downloaded_pdfs: 157
- success rate: `98.74%`

失败项：

- `The 2020 Election: Remote Voting, Disinformation, and Audit.`
- `Digital Contact Tracing.`

二者都是 panel / discussion 页面，状态均为 `no_pdf_url`，不属于下载器错误。

### 5.2 USENIX Security 2022

- papers_seen: 256
- downloaded_pdfs: 256
- success rate: `100.00%`

### 5.3 USENIX Security 2023

- papers_seen: 422
- downloaded_pdfs: 422
- success rate: `100.00%`

### 5.4 USENIX Security 2025

- papers_seen: 439
- downloaded_pdfs: 437
- success rate: `99.54%`

剩余 2 条：

- 1 条 `download_error`：下载超时
- 1 条 `no_pdf_url`：落地页没有稳定 PDF 链接

### 5.5 NDSS 2025

- papers_seen: 211
- downloaded_pdfs: 211
- success rate: `100.00%`

### 5.6 IEEE S&P 2025

- papers_seen: 255
- downloaded_pdfs: 0
- 当前状态全部为 `no_pdf_url`

原因判断：

- 当前 raw metadata 只给出 DOI 页面
- 现有轻量实现没有继续穿透 IEEE 平台获取 PDF 直链

### 5.7 CCS 2025

- papers_seen: 390
- downloaded_pdfs: 0
- 当前状态全部为 `no_pdf_url`

原因判断：

- 当前 raw metadata 只给出 DOI 页面
- 现有轻量实现没有继续穿透 ACM 平台获取 PDF 直链

### 5.8 CRYPTO 2025

- papers_seen: 156
- downloaded_pdfs: 6
- success rate: `3.85%`

当前主要来源：

- `dblp_eprint_exact`

新增公开搜索增强：

- `arxiv_exact`
- `openreview_exact`

解释：

- IACR `papers.json` 本身不提供公开 PDF 直链。
- 当前增强版会按标题依次尝试：
  1. DBLP Search API
  2. arXiv API
  3. OpenReview 公共搜索 API
- 但只有在标题做归一化后精确匹配时才接受结果，避免把语义相近但不是同一篇论文的结果误收进来。
- 当前已验证的实际主要收益仍来自 DBLP 命中的 `IACR Cryptol. ePrint Arch.` 开放版本，并将 ePrint 页面 URL 转成 `.pdf` 下载。
- 因此当前能下载到的主要是“同时存在 ePrint 公开版本”的论文，而不是全部 accepted papers。

额外观察：

- 通过 DBLP 命中的 Springer DOI 落地页，通常可以读到 `citation_pdf_url` 这类 PDF 元信息。
- 但当前直接访问 `link.springer.com/content/pdf/...` 返回的是空响应或受限响应，不适合作为“公开可下载 PDF”来源接入主逻辑。
- OpenReview 公共搜索接口可访问，但更偏语义搜索，因此当前只把它作为“精确标题命中时的保守候选来源”。

### 5.9 ASIACRYPT 2025

- papers_seen: 143
- downloaded_pdfs: 5
- success rate: `3.50%`

说明：

- 同一策略可迁移到 ASIACRYPT。
- 但成功仍主要依赖论文是否存在同标题的公开 ePrint 版本。

### 5.10 EUROCRYPT 2025

- papers_seen: 123
- downloaded_pdfs: 1
- success rate: `0.81%`

说明：

- 当前只有极少量论文命中可公开下载的 ePrint PDF。
- 这更像是开放版本覆盖不足，而不是统一入口失效。

### 5.11 三大密码会 2020-2025 全量覆盖表

汇总文件：

- `generated-data/extraction/interim/top3_crypto_pdf_coverage_summary.csv`

当前结果：

| conference_key | papers_seen | downloaded_pdfs | download_rate |
|---|---:|---:|---:|
| asiacrypt_2020 | 85 | 2 | 2.35% |
| asiacrypt_2021 | 95 | 0 | 0.00% |
| asiacrypt_2022 | 98 | 1 | 1.02% |
| asiacrypt_2023 | 106 | 6 | 5.66% |
| asiacrypt_2024 | 127 | 0 | 0.00% |
| asiacrypt_2025 | 143 | 5 | 3.50% |
| crypto_2020 | 85 | 4 | 4.71% |
| crypto_2021 | 103 | 2 | 1.94% |
| crypto_2022 | 99 | 0 | 0.00% |
| crypto_2023 | 124 | 0 | 0.00% |
| crypto_2024 | 143 | 0 | 0.00% |
| crypto_2025 | 156 | 6 | 3.85% |
| eurocrypt_2020 | 81 | 0 | 0.00% |
| eurocrypt_2021 | 78 | 2 | 2.56% |
| eurocrypt_2022 | 85 | 0 | 0.00% |
| eurocrypt_2023 | 108 | 2 | 1.85% |
| eurocrypt_2024 | 105 | 7 | 6.67% |
| eurocrypt_2025 | 123 | 1 | 0.81% |

观察：

- 三大密码会的当前覆盖率整体明显低于 USENIX / NDSS。
- 主要决定因素不是统一入口是否能下载，而是同标题公开版本是否存在并可公开访问。
- `EUROCRYPT 2024` 与 `ASIACRYPT 2023`、`CRYPTO 2020/2025` 是当前相对较高的几个年份，但也仍处于低覆盖状态。
- 因此对密码会而言，当前下载能力应被视为“公开版本补充层”，而不是“主 proceedings PDF 完整镜像能力”。

## 6. 方法对比

### 方法 A：只保留 landing page / DOI URL

优点：

- 实现简单
- 不涉及额外下载

缺点：

- 用户后续还要手动点进去找 PDF
- 不能形成稳定本地缓存

### 方法 B：先下载 PDF，不解析内容

当前采用。

优点：

- 对 USENIX、NDSS 这类页面结构明确的平台效果很好
- 对密码会，当前可通过 DBLP + ePrint fallback 获得一部分公开 PDF
- 可以先形成稳定 PDF 缓存
- 后续解析实验可以直接复用同一批输入

缺点：

- 不同出版平台需要额外适配 DOI -> PDF 路由
- 当前对 IEEE / ACM 平台支持不足
- 对密码会，公开 PDF 覆盖率会受 ePrint 开放版本可用性限制
- 对 Springer 这类出版页面，即使能读到 PDF 元信息，也未必意味着该 PDF 可作为公开下载源稳定获取

### 方法 C：下载 PDF 后直接做 frontmatter / 全文解析

当前未启用。

原因：

- 当前需求只要求下载，不要求解析
- 下载层和解析层分开更利于逐步验证错误来源

## 7. 当前结论

- PDF 下载能力已经进入统一主流程，可稳定支持“先缓存 PDF、后决定是否解析”的工作方式。
- 对 USENIX 和 NDSS，这一能力已经足够实用。
- 对密码会，这一能力已经从“完全没有 PDF 线索”提升到“可自动抓取一部分 ePrint 开放 PDF”。
- 对密码会，当前最佳公开来源仍是 ePrint；Springer DOI 页面更多适合作为“存在 PDF 元信息”的线索，而不是当前主下载源。
- 对密码会，当前公开搜索增强已经形成“DBLP/ePrint -> arXiv -> OpenReview”的保守回退链，但实际有效覆盖目前仍主要由 ePrint 决定。
- 对 IEEE S&P 和 CCS，当前主要缺的是平台 DOI 页面到 PDF 直链的适配，而不是统一入口本身缺失。

## 8. 后续可做实验

1. 补 IEEE / ACM DOI 页面到 PDF 直链的专门适配
2. 比较“只保留 landing page URL”和“落本地 PDF 缓存”对人工复核效率的提升
3. 在后续 PDF frontmatter 解析实验中，把这批已下载 PDF 作为固定输入集，独立评估解析错误率
