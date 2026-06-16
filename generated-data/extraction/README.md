# 统一采集输出目录

该目录用于集中查看采集阶段的最终有用产物。

## 子目录说明

- `raw/`：原始抓取快照
- `interim/`：按会议组织的中间产物
- `output/`：按会议与按分组组织的正式输出
- `reference/`：抽取阶段使用的 reference 文件
- `resolution/`：复核与补齐缓存

## 当前策略

- 新运行默认推荐直接写到 `generated-data/extraction/`。
- 当前 canonical 批次为七大会 `2020-2025` 完整抽取结果。
- 当前目录不保留 `*_us_institutions.*` 或 `*美国机构*` 这类仅美国切片文件，避免与主输出混淆。

## 当前状态

当前目录已经包含主抽取链路的核心管理文件与目录结构，包括：

- `unified_run_manifest.json`
- `noise_cleaning_report.json`
- `artifact_index.csv`
- `artifact_index.md`
- `raw/by_conference/`
- `interim/by_conference/`
- `interim/summaries/`
- `output/by_conference/`
- `output/summaries/`
- `resolution/affiliation_cache/`

后续新的抽取批次应继续沿用这套目录组织方式，并以 `output/` 下内容作为正式抽取出口。

## 注意

- `output/` 目录应优先承载当前主流程输出，而不是旧目录镜像。
- 如果后续需要更严格的版本管理，可以再细分为 `crypto/`、`security/`、`merged/` 等子目录。
