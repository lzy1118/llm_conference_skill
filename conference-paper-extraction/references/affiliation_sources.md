# 机构来源参考

## 目标

为不同顶会或来源提供合适的机构归属抽取策略。

当前正式执行入口为 `scripts/run_unified_pipeline.py`。该入口会根据会议类型自动路由到 skill 内部 backend，而不是要求用户分别调用多个历史脚本。

## 常见来源类型

### IACR JSON

- 优先使用 IACR 公开 JSON 中的作者与论文结构。
- 如果缺少结构化机构信息，需要结合补充来源或后续复核。
- 在当前实现中，对应 `scripts/iacr_top3_backend.py`。
- 当作者数组与 affiliation 数组不对齐时，可通过统一入口的 `--resolve-mismatches` 触发内部补源候选阶段。

### DBLP

- 适合拿到会议论文元信息和作者列表。
- DBLP 往往不直接提供完整机构信息，因此需要与会议官网、OpenAlex、Springer、作者页面等组合使用。
- 在当前实现中，安全会由 `scripts/security_real_backend.py` 先抓取 DBLP 论文元信息，再结合会议页面或 API 补足 affiliations。

### 会议官网 / PDF Frontmatter

- 当结构化来源不足时，可优先尝试论文 frontmatter。
- frontmatter 适合处理作者与机构一一对应或有清晰标注的论文。
- 当前安全会 backend 已内置多种网页解析器，例如 USENIX meta 标签、NDSS 页面作者机构行、IEEE Xplore 元数据块。

### OpenReview / Semantic Scholar

- 适合 AI/ML 会议。
- 应注意同名作者、非标准机构名称和补全字段不稳定的问题。

## 策略建议

1. 优先结构化 API
2. 再尝试可解析网页或 PDF frontmatter
3. 最后进入人工复核队列

## 与统一入口的关系

- `top3_crypto` 分组默认走 IACR JSON 主路径
- `top4_security` 分组默认走 DBLP + 会议网页/API 补充路径
- 统一入口只负责选择会议与调度 backend，不直接内嵌具体页面解析细节
- IACR 路径目前还支持一个保守型后处理阶段：生成 mismatch 论文的候选来源与 resolution report，便于后续人工复核或自动 enrichment

## 输出要求

- 保留原始机构字符串
- 保留国家判定结果 `country`
- 保留来源 URL 或来源类型
- 保留置信度与判定原因
- 不要在抽取阶段过早做激进合并

## 中间产物命名

- 推荐主用 `interim/institution_classification_candidates.csv` 作为待复核候选清单
- 正式主输出应优先读取 `output/*_author_affiliations.csv` 或汇总版 `*_作者机构国家.csv`
