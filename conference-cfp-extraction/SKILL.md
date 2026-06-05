---
name: conference-cfp-extraction
description: Extract, normalize, and audit conference CFP lifecycle metadata such as submission deadlines, rebuttal windows, notification dates, camera-ready deadlines, and conference dates.
license: MIT
compatibility: Requires Python 3.10+ and local access to this repository's conference registry and CSV inputs.
metadata:
  author: llm-conference-skill
  version: "0.1"
allowed-tools: Bash(python3:*) Read Glob Grep
---

# 顶会 CFP 与会议日期抽取

本 skill 负责会议征文与会议周期元数据，不直接承担论文作者机构抽取。它用于补齐以下信息：

- abstract deadline
- full paper deadline
- artifact deadline
- rebuttal start / end
- notification date
- camera-ready deadline
- conference start / end
- 官网、CFP 页、proceedings 页等来源 URL

## 当前阶段

当前实现已经升级为稳定主链路：

1. 从统一 conference registry 选择会议范围。
2. 自动预填会议版本元数据，例如官网、CFP 页、proceedings 页 URL。
3. 合并人工补充输入 `cfp_events_input.csv` 与 `conference_edition_input.csv`。
4. 规范化日期字段并生成 `conference_events.csv`。
5. 生成 `conference_edition_metadata.csv`、`cfp_review_queue.csv`、`cfp_coverage_summary.csv` 和 `cfp_validation_report.json`。

当前仍不默认联网抓取，避免把未验证页面内容误写入正式事实表；自动预填部分默认低置信度并标记 `needs_review=true`。

对 IACR 三大密码会，当前已支持可选联网自动抽取：

- 从官方 `json/metadata.json` 抓取 submission deadline、rebuttal、notification、camera-ready、conference dates
- 自动回写到 `conference_events.csv` 与 `conference_edition_metadata.csv`
- 官方 metadata 命中的行默认 `confidence=0.9`

对四大安全会，当前已支持可选 CFP 页面自动抽取：

- USENIX Security：多 review cycle 的 submission / rebuttal / notification / final paper dates
- NDSS：call-for-papers 页面中的 review cycle 日期与 conference dates
- IEEE S&P：`cfpapers.html` 中的多 deadline 日期
- ACM CCS：call-for-papers 页面中的 review cycle 日期

由于安全会历史网页结构跨年份差异更大，当前策略是：

- 能稳定命中的字段自动写入事实表
- 不能稳定命中的年份保留在 `cfp_review_queue.csv`
- 推荐优先把 `2024-2025` 作为自动抽取主范围

## 输出目录

默认输出到：

```text
generated-data/cfp/
  input_templates/
  output/
```

核心输出：

- `input_templates/cfp_events_template.csv`
- `input_templates/conference_edition_template.csv`
- `output/conference_events.csv`
- `output/conference_edition_metadata.csv`
- `output/cfp_review_queue.csv`
- `output/cfp_coverage_summary.csv`
- `output/cfp_validation_report.json`
- `output/cfp_report.md`

## 使用方式

生成模板：

```bash
python3 scripts/run_cfp_pipeline.py --output-dir generated-data/cfp
```

按会议组生成并自动预填 edition metadata：

```bash
python3 scripts/run_cfp_pipeline.py --group top7_2020_2025 --output-dir generated-data/cfp
```

为 IACR 三会自动抓取官方日期元数据：

```bash
python3 scripts/run_cfp_pipeline.py --group top3_crypto --fetch-iacr --output-dir generated-data/cfp
```

为四大安全会自动抓取 CFP 页面日期：

```bash
python3 scripts/run_cfp_pipeline.py --group top4_security --fetch-security --output-dir generated-data/cfp
```

同时为七大会生成当前最完整的主线结果：

```bash
python3 scripts/run_cfp_pipeline.py --group top7_2020_2025 --fetch-iacr --fetch-security --output-dir generated-data/cfp
```

使用已有事件输入：

```bash
python3 scripts/run_cfp_pipeline.py \
  --events-input generated-data/cfp/input/cfp_events_input.csv \
  --edition-input generated-data/cfp/input/conference_edition_input.csv \
  --output-dir generated-data/cfp
```

只跑单会议：

```bash
python3 scripts/run_cfp_pipeline.py --conference crypto_2025 --output-dir generated-data/cfp
```

## 设计原则

- CFP 元数据和论文 accepted data 分开建模。
- 日期必须保留原始文本和规范化结果。
- timezone 不确定时不要硬猜，标记 `needs_review=true`。
- source URL 必须保留，便于后续复核。
- 不同来源冲突时保留多行，不直接覆盖。
- edition metadata 默认由 registry URL pattern 预填，但必须通过 review queue 持续复核完善。
