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

当前实现是最小稳定闭环：

1. 从统一 conference registry 生成 CFP 待填模板。
2. 接收人工整理或后续爬虫生成的 `cfp_events_input.csv`。
3. 规范化日期字段并生成 `conference_events.csv`。
4. 生成 `conference_edition_metadata.csv` 和 `cfp_validation_report.json`。

当前不默认联网抓取，避免把未验证页面内容误写入正式事实表。

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
- `output/cfp_validation_report.json`
- `output/cfp_report.md`

## 使用方式

生成模板：

```bash
python3 scripts/run_cfp_pipeline.py --output-dir generated-data/cfp
```

使用已有事件输入：

```bash
python3 scripts/run_cfp_pipeline.py \
  --events-input generated-data/cfp/input/cfp_events_input.csv \
  --edition-input generated-data/cfp/input/conference_edition_input.csv \
  --output-dir generated-data/cfp
```

## 设计原则

- CFP 元数据和论文 accepted data 分开建模。
- 日期必须保留原始文本和规范化结果。
- timezone 不确定时不要硬猜，标记 `needs_review=true`。
- source URL 必须保留，便于后续复核。
- 不同来源冲突时保留多行，不直接覆盖。
