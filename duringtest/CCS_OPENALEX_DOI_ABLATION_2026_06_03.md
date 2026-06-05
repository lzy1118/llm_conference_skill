# CCS OpenAlex DOI Ablation 2026-06-03

## 目的

验证 `CCS` 抽取中，`OpenAlex title search` 与 `OpenAlex DOI lookup` 两种入口对作者机构覆盖率的影响。

## 变更点

在 `conference-paper-extraction/scripts/security_real_backend.py` 中，把 `CCS` 的机构回补顺序从：

1. `OpenAlex title search`
2. `Semantic Scholar fallback`

调整为：

1. `OpenAlex DOI lookup`
2. `OpenAlex title search`
3. `Semantic Scholar fallback`

同时修复了“空 affiliation 旧缓存阻断重新联网”的问题：

- 旧行为：只要缓存文件里有列表，就直接复用
- 新行为：只有缓存里至少有一条非空 affiliation 才视为有效缓存

## 结果

### CCS 各年份覆盖率变化

| 年份 | 变更前 papers_with_author_rows | 变更后 papers_with_author_rows | 变更前 no_affiliation | 变更后 no_affiliation |
|------|-------------------------------:|-------------------------------:|----------------------:|----------------------:|
| 2020 | 133 | 147 | 15 | 1 |
| 2021 | 215 | 221 | 10 | 4 |
| 2022 | 89 | 279 | 198 | 8 |
| 2023 | 248 | 287 | 44 | 5 |
| 2024 | 0 | 404 | 413 | 9 |
| 2025 | 0 | 387 | 390 | 3 |

### 关键结论

1. `CCS 2024/2025` 的主要问题不是 DOI 无法解析，而是 `title search` 覆盖很差。
2. 对 `CCS 2022/2023`，`DOI lookup` 也显著优于 `title search`。
3. “空缓存阻断重试”会把旧失败结果长期固化，需要避免。

## 当前判断

- 对 `CCS 2020-2025`，`OpenAlex DOI lookup` 应作为默认主路径保留。
- `Semantic Scholar` 更适合作为剩余少量未命中论文的兜底，而不是主入口。
- 若后续仍要继续压缩 `no_affiliation_data`，优先检查剩余 DOI 是否在 OpenAlex 无 authorship，或作者映射是否存在个别变体未命中。
