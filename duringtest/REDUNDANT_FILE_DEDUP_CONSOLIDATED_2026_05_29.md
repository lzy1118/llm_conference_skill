# 冗余文件清理总记录

## 1. 合并范围

本文件合并以下七份连续清理记录：

- `REDUNDANT_FILE_DEDUP_2026_05_29.md`
- `REDUNDANT_FILE_DEDUP_ROUND2_2026_05_29.md`
- `REDUNDANT_FILE_DEDUP_ROUND3_2026_05_29.md`
- `REDUNDANT_FILE_DEDUP_ROUND4_2026_05_29.md`
- `REDUNDANT_FILE_DEDUP_ROUND5_2026_05_29.md`
- `REDUNDANT_FILE_DEDUP_ROUND6_2026_05_29.md`
- `REDUNDANT_FILE_DEDUP_ROUND7_2026_05_29.md`

## 2. 清理主线

这七轮工作本质上是一条连续主线：

1. 删除美国机构历史子集文件
2. 删除中国机构历史专题切片
3. 清理旧 `data/` 抽取残留与 `*-check` 验证目录
4. 删除空目录壳并同步收口主文档
5. 删除单会议运行后残留的伪汇总副本
6. 清理 `resolution/` 中的空占位和无效缓存
7. 清理 `interim/` 与 `output/` 中剩余完全重复的空副本

## 3. 各轮摘要

### 3.1 第一轮：删除美国机构历史子集

删除：

- `generated-data/extraction/output/2025-2026三大密码会_美国机构.csv`
- `generated-data/extraction/output/2025-2026三大密码会_美国机构_audit.csv`
- `generated-data/extraction/output/2025-2026三大密码会_美国机构.xlsx`
- `data/reference/三大密码会_美国机构_2020-2026.csv`

结论：

- 仓库内已无名称包含“美国机构”的现存文件

### 3.2 第二轮：删除中国专题切片并检查机构 reference

删除：

- `generated-data/extraction/output/asiacrypt_2024_china_*`
- `data/reference/crypto_2025_china_institutions.csv`
- `data/reference/三大密码会_中国机构_*`

同时检查：

- `data/reference/institution_aliases.csv`
- `data/reference/institution_registry.csv`

结果：

- `institution_aliases.csv` 无重复行、无 alias 多 ID 冲突
- `institution_registry.csv` 无重复行、无重复 `institution_id`

### 3.3 第三轮：清理历史 `data/` 与验证目录内容

删除：

- `data/raw/` 和 `data/interim/` 中已被 `generated-data/extraction/` 覆盖的旧产物
- `generated-data/crypto-2022-check/normalized/` 内容
- `generated-data/usenix-security-2022-check/normalized/` 与 `analysis/` 内容

### 3.4 第四轮：删除空目录壳并收口文档

删除空目录：

- `data/interim/`
- `data/raw/`
- `data/output/`
- `generated-data/crypto-2022-check/`
- `generated-data/usenix-security-2022-check/`

同步更新：

- `README.md`
- `WORKFLOW.md`
- `conference-paper-extraction/references/affiliation_sources.md`

### 3.5 第五轮：删除伪汇总副本

删除：

- `generated-data/extraction/interim/affiliation_resolution_queue.csv`
- `generated-data/extraction/interim/author_affiliations_expanded.csv`
- `generated-data/extraction/interim/institution_classification_candidates.csv`
- `generated-data/extraction/output/2025-2026三大密码会_作者机构国家.*`
- `generated-data/extraction/output/四大安全顶会_作者机构国家.*`

原因：

- 这些文件在单会议执行后只是单会议副本，不是真正跨会议汇总

### 3.6 第六轮：清理空 resolution 占位

删除：

- `generated-data/extraction/resolution/crypto_2022/parsed_affiliations.jsonl`
- `generated-data/extraction/resolution/crypto_2022/resolved_author_affiliations.csv`

原因：

- 前者为 0 字节空文件
- 后者仅有表头

### 3.7 第七轮：清理空的逐会议复核队列副本

删除：

- `generated-data/extraction/interim/crypto_2020_affiliation_resolution_queue.csv`
- `generated-data/extraction/interim/usenix_security_2022_affiliation_resolution_queue.csv`
- `generated-data/extraction/interim/usenix_security_2023_affiliation_resolution_queue.csv`

原因：

- 三者内容完全相同，且都只有表头

## 4. 清理原则总结

本轮冗余文件清理遵循以下规则：

- 删除已被主链路 `generated-data/` 覆盖的旧产物
- 删除专题切片最终文件，避免误导其为主契约
- 删除空文件、空目录、只有表头的空副本
- 删除单会议运行后产生的伪汇总副本
- 对机构 reference 先做安全结构检查，不做激进内容删除

## 5. 当前结论

整理完成后：

- `data/` 只保留 `reference/`
- `generated-data/` 中不再保留历史 `*-check` 空壳与明显伪汇总副本
- 美国机构、中国机构专题切片不再与主线产物并存
- `interim/`、`output/`、`resolution/` 中的空占位和完全重复副本已基本清干净

## 6. 后续建议

- 新增清理记录时，直接追加到本文件，不再按 Round 继续拆文件
- 如需再次做 reference 去重，先做冲突审计，再决定是否删行
- 若未来恢复多会议正式汇总，应确保它们确实来自多会议输入，而不是单会议副本
