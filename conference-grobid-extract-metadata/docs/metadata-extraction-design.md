# 高精度论文元数据提取设计

## 1. 目标与边界

本阶段的目标是从本地论文 PDF 中尽可能准确地恢复论文原始元数据，并保留每个字段的
来源、证据和不确定性。最终结果将作为 AffilGood 的输入。

需要提取：

- 标题、年份、DOI、摘要；
- 作者姓名、原始顺序；
- 作者邮箱；
- PDF 中出现的原始机构字符串；
- 作者与原始机构字符串之间的关系；
- 第一作者、共同一作、equal contribution、通讯作者；
- 每个字段的来源、置信度和证据位置。

本阶段明确不做：

- 机构别名合并或标准名称选择；
- ROR、GRID、Wikidata 等机构实体链接；
- 机构层级、国家和城市的规范化；
- 根据历史作者档案猜测 PDF 中没有出现的机构。

机构输出应尽量忠实于 PDF，例如保留 `Georgia Tech`、`Georgia Institute of
Technology` 各自的原始写法，交由 AffilGood 在下一阶段消歧。

## 2. 设计原则

1. **证据优先**：最终值必须能追溯到 TEI 节点、PDF 文本块、PDF 元数据、文件路径或
   明确的推断规则。
2. **候选无损**：任何清洗或会议策略都不能删除原候选；只能新增候选、降低候选分数或
   选择另一个候选。
3. **字段级仲裁**：标题、作者、机构、邮箱和角色分别选择，禁止因为一个字段更好而整组
   覆盖其他字段。
4. **关系与实体分离**：先识别作者、机构、邮箱和脚注实体，再建立作者到机构、邮箱和
   角色的关系。
5. **精准优先**：证据冲突时进入复核队列，不使用看似完整但无法验证的值。
6. **原文与显示值分离**：`raw_text` 保留 PDF 原文，`display_text` 只做 Unicode、空白、
   连字符和明显 OCR 字符修复，不做机构消歧。
7. **会议规则受限**：会议策略只能在检测到对应版式后启用，不能仅凭会议名强行套用。

## 3. 总体架构

```text
PDF
 ├─ GROBID header TEI（主结果）
 ├─ pdfplumber 文本 + token/block 坐标（姓名字符与页面位置校验）
 ├─ pypdf document info + Link/mailto annotations（补充链接证据）
 └─ 文件路径/年份提示
          │
          ▼
    Evidence Store（只追加）
          │
          ▼
    版式检测 + 多解析器候选
          │
          ▼
    Metadata Candidate Graph
          │
          ├─ 字段级打分与约束仲裁
          ├─ 作者—机构/邮箱/角色关系匹配
          └─ 一致性校验与置信度校准
          │
          ▼
 final metadata + evidence + review queue
          │
      ▼
       AffilGood
```

同一 PDF 的固定执行顺序为：

```text
GROBID 结构化主结果
    -> pdfplumber 姓名字符/页面位置校验
    -> pypdf 链接证据补充
    -> 按字段合并证据
    -> 高置信度自动修正
    -> 低置信度进入 review_queue
```

流水线拆成六个可独立评测的阶段：

1. `evidence_extraction`：提取 TEI、PDF 文本和二维坐标等原始证据；
2. `layout_detection`：识别首页作者区版式；
3. `candidate_generation`：运行适合该版式的解析器，生成多个候选；
4. `relation_linking`：构建作者—机构、作者—邮箱和作者—脚注关系；
5. `arbitration_validation`：字段级选择、约束校验、置信度校准；
6. `export_review`：输出兼容 CSV、详细 JSON 和复核队列。

## 4. Evidence Store

不能只保留当前最终 JSON。每条证据至少包含：

```json
{
  "evidence_id": "pdf_block:p1:b17",
  "paper_id": "002_iovalve_...",
  "source": "pdf_layout",
  "page": 1,
  "bbox": [72.1, 118.4, 241.8, 153.7],
  "raw_text": "Microsoft Research",
  "normalized_text": "Microsoft Research",
  "labels": ["affiliation_candidate"],
  "extractor": "pdfalto",
  "extractor_version": "..."
}
```

来源至少包括：

- `grobid_tei`：TEI 节点及其 XPath；
- `pdf_layout`：首页/第二页文本块、token 坐标、字号和字体；
- `pdf_text`：不带坐标的文本回退；
- `pdf_document_info`：PDF Title、Author、CreationDate；
- `filename`：会议和年份提示；
- `rule`：规则推断及使用的证据 ID；
- `layout_model`：模型标签、关系分数和模型版本。

所有后续候选都引用 `evidence_id`，不能只保存 `affiliation_source=ccs_pdf` 这种粒度过粗的
标签。

## 5. 版式检测与候选解析器

先分类版式，再运行一个或多个解析器：

| 版式 | 主要线索 | 解析器 |
|---|---|---|
| 上标编号映射 | 作者名后数字，机构行以相同数字开头 | `numbered_reference` |
| 逐作者卡片 | 姓名、机构、地点、邮箱形成局部垂直块 | `author_card` |
| 多列矩阵 | 同一水平带有多个姓名，机构位于其下 | `column_matrix` |
| 集中作者+集中机构 | 作者集中在前，机构集中在后 | `grouped_blocks` |
| 共享机构 | 多作者，只有一个明确机构块 | `shared_affiliation` |
| 符号脚注 | `*`, `†`, `‡`, `✉` 与脚注文本对应 | `symbol_footnote` |
| TEI 稳定 | TEI 作者、机构、邮箱覆盖完整且无冲突 | `tei_direct` |

版式检测应基于二维特征，不应只使用 PDF 的线性文本顺序。解析器可以并行产生候选，
后续按字段仲裁，而不是采用“第一个解析成功即停止”。

当 PDF 文本层为空、乱码率高或视觉页存在文字但 token 数过少时，才触发 OCR/视觉模型
回退。OCR 结果必须保留为独立来源，不能覆盖原文本层。

## 6. Metadata Candidate Graph

每篇论文构建一个候选图：

- 节点：`TITLE`、`AUTHOR`、`AFFILIATION_RAW`、`EMAIL`、`MARKER`、`ROLE_NOTE`、
  `ABSTRACT`、`DOI`、`YEAR`；
- 边：`SAME_AS`、`AUTHORED_BY_ORDER`、`AFFILIATED_WITH`、`HAS_EMAIL`、
  `MARKED_BY`、`ROLE_OF`；
- 边特征：同上标、同列、水平/垂直距离、阅读顺序距离、邮箱域邻近、TEI 父子关系、
  解析器一致性。

作者—机构关系采用受约束二分图匹配：

- 上标完全一致是强证据；
- 同一作者卡片或同一列是强证据；
- 仅线性相邻是弱证据；
- “唯一机构传播给全部作者”只有在共享机构版式成立时允许；
- 一个作者允许多个机构，一个机构允许多个作者；
- 无可靠关系时保留论文级机构候选，但不虚构作者级关系。

## 7. 字段级规则

### 7.1 标题

候选来源优先考虑 TEI、首页最大字号块、PDF Title 和文件名。候选需通过：

- 位于首页摘要前；
- 不包含会议页眉、版权、ISBN 或 proceedings 固定文本；
- 与作者块和摘要块空间分离；
- 多来源一致时提高置信度。

禁止用标题清洗规则改变有意义的标点、数学符号或副标题结构。

### 7.2 作者与顺序

- 原始顺序由二维阅读顺序、上标组和 TEI 顺序共同确定；
- 对逐作者卡片先统计 11.2--13.5pt 区间内的人名候选字号，只使用出现次数最多的主作者字号；
- 只有首页每个候选作者都在同列距离窗口内得到邮箱或机构支持、候选姓名不重复且至少有
  两位作者时，才允许用页面顺序重建作者列表；重建后重新计算角色和导出 rank；
- 机构名、标题残片、地点、邮箱片段不得成为最终作者；
- 缩写名和完整名只建立 `SAME_AS` 候选，不立即删除其中一个；
- 作者数量或顺序在 TEI 与 PDF 间冲突时，整篇进入关系复核，不按字母重排；
- `author_rank_raw` 始终保存 PDF 顺序，共同一作不改变原始顺序。

### 7.3 原始机构字符串

- 保存作者块中完整机构短语，包括部门、实验室、学校、公司及原始地点信息；
- 只清除邮箱、URL、脚注符号和已由坐标确认的完整作者 span；
- 不按单个作者姓名 token 全局删除文本；
- 不要求机构必须含 `University/Institute/Lab`，短名称如 `Meta`、`Google`、
  `DPella AB`、`Serai DEX` 也应保留；
- 对词典未知的短机构，只有“已确认作者 + 同列短机构 + 紧邻地点 + 同卡片邮箱”四项
  几何证据同时成立时才自动接收，并保存地点和邮箱 block 作为验证证据；
- 纯地点可保留为低置信 `location_candidate`，但不能替代机构；
- 不在本阶段拆解或合并机构实体，分号仅表示 PDF 中确认存在多个独立机构。

### 7.4 邮箱

- 明确位于作者卡片内或由同一上标关联时，输出作者级邮箱；
- 花括号邮箱先展开，再通过本地部分、作者顺序和卡片关系匹配；
- 只凭域名不能生成作者邮箱；
- 无法可靠归属时保存为论文级邮箱候选，不强行分配；
- 邮箱域只能作为机构关系的辅助证据，不能在此阶段生成机构名称。

### 7.5 作者角色

- `corresponding` 需要明确姓名、符号、信封或脚注语义证据；有邮箱不等于通讯作者；
- `co_first_author` 和 `equal_contribution` 需要明确 `contributed equally`、`co-first` 或
  等价文本；
- 支持 `first two/three/N authors` 和脚注中显式姓名列表；
- 保存 `role_evidence_ids`；无证据时输出 `false`，不能猜测。

邮箱不是通讯作者证据。只有显式姓名、符号/信封和脚注语义的作者映射才能设置
`corresponding=true`。仅出现 `equal contribution`、`contributed equally` 或 `co-first` 而没有
姓名列表或 `first N authors` 范围时，保持共同一作字段为 `false` 并加入复核队列。

### 7.6 年份、DOI、摘要

- 年份优先级：明确出版日期 > proceedings 文本 > 目录年份 > 文件名；
- DOI 必须通过 DOI 格式和校验位附近上下文检查，避免把参考文献 DOI 当论文 DOI；
- 摘要必须由摘要标题/TEI 节点和版面边界确定，遇到 Introduction、CCS Concepts、
  Keywords 或版权块停止；
- 脚注、作者说明和关键词不得拼入摘要。

## 8. 仲裁、置信度和失败检测

每个字段候选分别计算特征，不使用一个论文级总分替代字段置信度。推荐特征：

- 来源可靠性；
- 多解析器一致性；
- TEI 与 PDF 一致性；
- 版面区域合理性；
- 结构约束是否满足；
- 候选之间的分数间隔；
- 是否经过 OCR 或弱推断。

置信度必须在人工标注验证集上校准。输出三档：

- `accepted`：满足自动接收精度目标；
- `review`：有合理候选但冲突或分数接近；
- `unresolved`：证据不足，不输出推断值。

建议以自动接收集的字段 precision 不低于 99% 为初始目标，再根据复核成本调整阈值。
不能直接把模型 softmax 当作可信概率。

必须实现以下失败检测：

- PDF 首页存在机构词/邮箱，但最终机构或邮箱覆盖为零；
- TEI 中字段非空，最终结果却为空，且没有明确拒绝原因；
- 最终作者数与高置信 PDF 作者候选数不一致；
- 作者名包含机构词、标题长片段、地点或邮箱；
- 同一作者获得空间上互斥的机构；
- 标题、作者或摘要跨过版面区域边界；
- 候选替换导致机构或邮箱覆盖下降。

最后一条是硬性单调约束：若新候选不能证明原候选错误，不允许把非空字段变为空。

## 9. 模型使用策略

规则继续负责高精度结构：DOI、邮箱、上标、显式脚注、固定模板边界和一致性约束。

模型只补规则难以覆盖的部分：

1. 使用 LayoutLMv3 或同类二维文档模型识别首页实体；
2. 增加关系分类头预测作者—机构、作者—邮箱和标记—脚注关系；
3. 使用现有 2025 官网数据作为作者和原始机构的弱监督起点；
4. 对规则/模型冲突、机构为空和作者数异常的论文优先人工标注；
5. 通过主动学习逐轮增加困难版式，不随机平均标注全部论文。

训练/验证/测试必须按论文划分，并按会议和年份设置跨模板测试，不能把同一篇论文的作者行
拆到不同数据集。评测时既报告全部样本，也单独报告自动接收样本的 precision/coverage。

## 10. 输出设计

保持现有 `paper_metadata.csv` 兼容，同时新增：

```text
author_metadata_dataset_YYYY/
├── evidence_json/          # 原始证据，只追加
├── candidate_json/         # 所有字段和关系候选
├── metadata_json/          # 最终详细结果
├── review_queue.csv        # 需要人工检查的论文/字段
├── conference_year_paper_abstract.csv  # conference,year,title,abstract
├── extraction_metrics.json
└── paper_metadata.csv      # 兼容下游的作者行格式
```

最终 JSON 中每个字段采用统一包装结构：

```json
{
  "value": "Microsoft Research",
  "raw_value": "Microsoft Research",
  "status": "accepted",
  "confidence": 0.997,
  "source": "pdf_layout",
  "evidence_ids": ["pdf_block:p1:b17"],
  "extractor": "author_card_v2",
  "rejected_candidates": []
}
```

机构数组中的每项还需携带与作者的关系证据。传给 AffilGood 的是 `raw_value` 或仅做最小
字符清洗的 `value`，不是本阶段生成的标准机构名。

## 11. 评测指标

最小评测集合：

- 论文标题 exact/normalized exact accuracy；
- 作者集合 precision、recall、F1；
- 作者顺序完全正确率和 Kendall tau；
- 原始机构字符串 exact/soft match；
- 作者—机构关系 precision、recall、F1；
- 邮箱提取和作者—邮箱关系 F1；
- 通讯作者、共同一作 precision、recall、F1；
- 摘要边界 exact/character F1；
- 自动接收 precision 与 coverage 曲线；
- `review` 队列命中真实错误的比例。

机构字符串的 soft match 只用于评测，可忽略大小写、Unicode 兼容字符、连续空白和末尾标点；
不得用 AffilGood 的标准化结果反向替代原始提取结果。

官网数据只作为对照源，不是强制覆盖 PDF 的真值。当 PDF 首页原文、作者卡片位置和
作者—机构关系均确认无截取或错位，而官网机构不同，应保留 PDF 的原始机构，并将差异
标记为 `publication_affiliation_adjustment`，表示投稿/官网登记到实际出版版本之间发生了
作者机构调整。只有 PDF 证据本身残缺、错位或解析不确定时，才继续作为提取问题复核。

## 12. CCS 2025 验收样本

以下本地 PDF 应成为固定回归集：

- `002_IOValve...pdf`：逐作者卡片/机构缺失；
- `179_The OCH...pdf`：多作者多机构关联；
- `187_Evaluating the Robustness...pdf`：长作者列表和公司机构；
- `191_Lite-PoT...pdf`：缩写姓名、多个机构与邮箱；
- `220_Accuracy for Differentially Private Quotients...pdf`：短公司名 `DPella AB`；
- `229_WireTap...pdf`：姓名变体和 TEI 机构错位；
- `017_DPImageBench...pdf`、`129_Split Unlearning.pdf`、`186_Riddle Me This...pdf`：
  标题片段/机构误识别为作者。

每个会议还应覆盖：单作者、共享机构、上标编号、多列作者、邮箱缺失、共同一作、通讯作者、
PDF 文本层异常和跨年份模板变化。

## 13. 实施顺序

### Phase 1：无损与可审计

- 引入 Evidence Store 和字段候选结构；
- 将整组覆盖改为字段级合并；
- 增加覆盖单调约束、拒绝原因和 review queue；
- 修正短机构名和作者 token 过度清洗问题；
- 建立 CCS 2025 回归集。

这一阶段不需要训练模型，应先解决已确认的 TEI 非空但最终为空问题。

### Phase 2：二维关系解析

- 保存 PDF token/block 坐标；
- 实现版式检测和候选图；
- 将现有 numbered/card/matrix/grouped parser 改为可并行候选生成器；
- 使用受约束关系匹配代替整组作者重建。

### Phase 3：版面模型回退

- 标注困难样本；
- 训练实体识别和关系链接模型；
- 校准字段置信度；
- 模型只在规则覆盖不足或冲突时参与仲裁。

### Phase 4：跨会议验证

- 按 CCS、IEEE S&P、NDSS、USENIX 和 LNCS 分层评测；
- 增加跨年份模板漂移检测；
- 达到自动接收精度目标后再批量重跑全部 7052 篇 PDF。

## 14. 文献依据

- Tkaczyk et al. (2015), CERMINE: modular scientific-document metadata extraction with
  textual and geometric features. DOI: `10.1007/s10032-015-0249-8`.
- Xu et al. (2020), LayoutLM: joint text and 2D-layout representation. DOI:
  `10.1145/3394486.3403172`.
- Xu et al. (2021), LayoutLMv2: multimodal and spatial-aware document understanding.
  ACL 2021.
- Jaume et al. (2019), FUNSD: entity labeling and linking for document understanding.
  DOI: `10.1109/ICDARW.2019.10029`.
- Subramanian et al. (2021), S2AND: author-name disambiguation benchmark and model.
  DOI: `10.1109/JCDL52503.2021.00029`.

S2AND 只用于姓名候选匹配思路，不用于机构消歧；AffilGood 不属于本设计的执行阶段。

## 15. 当前实施状态

已完成 Phase 1 和 Phase 2 的高精度子集：

- 保存 TEI、PDF 文本以及首页 block 的 bbox、字号和原文；
- 保存原始候选、最终候选、选择/拒绝原因和 review queue；
- 对直接 TEI/PDF 证据执行非空字段防丢失约束；
- 拒绝恢复共享传播、邮箱推断等弱来源，以及包含其他作者姓名的错位机构；
- 检测 `author_card_grid` 版式；
- 使用作者 block、紧邻机构 block、地点 continuation 和列中心距离构建关系；
- 使用主作者字号和局部机构/邮箱支持发现页面作者；仅在全部页面作者都有支持时重建列表，
  以纠正漏作者、伪作者、重复作者和截断姓名；
- 最终作者与页面 block 局部精确匹配且关系置信度足够时可补原始机构；其他作者损坏不会
  阻止这个局部高置信关系，但冲突字段仍不覆盖；
- 词典未知短机构必须额外满足同卡片地点和邮箱双重验证；
- 明确残片（如 `University, China`、`Science and, Technology`、`Republic of, Korea`）
  不作为完整机构接受；优先由同卡片高置信二维候选替换，或仅在相邻片段满足固定语法时重组；
- 多个 CCS parser 并行产生候选；作者集合相同时优先选择残片更少、机构信息更完整的候选，
  但候选总信息量明显低于基线时不得整体覆盖；
- TEI 若严格呈现 N 个连续作者节点后跟 N 个匿名机构节点，可按顺序一一映射；数量或结构
  不完全一致时禁止使用该规则；
- CCS 不使用 `shared_pdf`、孤儿机构拼接、邮箱域推断、同姓传播或共识传播抢占空机构；
  这些弱候选可进入复核，但最终自动值优先来自 TEI 直接字段、CCS 卡片解析和二维关系；
- 当前自动补全只对已用官网数据验证的 CCS 启用；其他会议只产出候选和复核原因；
- 高置信二维候选与已有机构冲突时只进入复核，不覆盖或追加；
- 批次指标记录字段恢复数、二维机构补全数和作者列表重建数。

本轮已补充：pdfplumber 主文本/坐标校验、pypdf 链接与文档信息证据、摘要边界提取与独立摘要 CSV；
通用层取消邮箱域机构推断、同姓机构复制、机构多数票传播、无 PDF 编号证据的孤儿机构拼接，并将
无范围 equal-contribution 文本送入复核。

仍需按会议样本验证：编号上标、集中机构、复杂多列矩阵等版式的二维关系解析，以及 Phase 3
版面模型训练。没有验证的会议只生成候选和复核原因，不自动覆盖 TEI 直接字段。
