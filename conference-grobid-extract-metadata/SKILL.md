---
name: conference-grobid-extract-metadata
description: 使用本地 GROBID 从论文 PDF 批量生成 header TEI XML，并按会议或出版格式提取、修复和审计标题、作者顺序、机构、邮箱、年份及作者角色。用于人工批处理或自动采集流水线中的 PDF 入库、GROBID header 解析、会议策略选择、证据与候选保留、复核队列生成，以及向 conference-clean-paper-metadata 交接结构化 CSV/JSON。
---

# GROBID 论文头部元数据提取

从论文 PDF 批量生成 header 级 TEI XML，再提取论文的标题、作者（按顺序）、机构和年份等头部信息，自动清洗 GROBID 常见提取噪声。

## 代码结构

核心实现位于 `scripts/author_metadata/`，按职责维护：

- `pipeline.py`：批次编排和 GROBID 流程，不放字段清洗规则；
- `tei_parser.py`：只解析 GROBID TEI；
- `pdf_context.py`：只建立 pdfplumber/pypdf 页面与链接上下文；
- `metadata_repair.py`：只编排字段修复阶段并合并决策；
- `affiliation_linking.py`：作者—机构、邮箱和机构残片关系；
- `role_linking.py`：第一作者、共同一作和通讯作者证据；
- `paper_fields.py`：摘要仲裁及第一/参与机构等论文级派生字段；
- `author_validation.py`、`author_order.py`：作者候选校验和导出顺序；
- `layout_relations.py`：二维作者—机构关系；
- `extraction_trace.py`：证据、候选、决策和复核原因；
- `artifacts.py`、`exporter.py`：统一生成 JSON、作者 CSV、摘要 CSV 和指标。

会议专属规则继续放在 `scripts/*_strategy.py`，通过 `author_metadata/strategies/` 加载。
不要把会议模板规则重新塞回 `metadata_repair.py` 或 `pipeline.py`。

## 使用场景

- 用户有一批论文 PDF，需要批量生成结构化元数据
- 需要识别第一作者、通讯作者、共同作者
- 需要去除 GROBID 提取的噪声（IEEE 水印、脚注重复、机构名误识别等）
- 需要针对不同会议论文格式分别处理作者块、机构块、邮箱、脚注和版权信息

## 快速开始

```bash
# 处理默认目录 data/raw_data/（递归扫描所有子目录）
python scripts/extract_paper_metadata.py

# 处理指定目录
python scripts/extract_paper_metadata.py --input-dir data/raw_data/usenix_security_2020

# 或使用一键脚本
./run_author_dataset_pipeline.sh                              # 默认 data/raw_data/
./run_author_dataset_pipeline.sh data/raw_data/usenix_security_2020  # 指定子目录
```

使用 skill 时，先将包含本文件的目录记为 `<skill-dir>`，再从任意工作目录运行：

```bash
SKILL_DIR=/absolute/path/to/conference-grobid-extract-metadata
python3 "$SKILL_DIR/scripts/extract_paper_metadata.py" \
  --input-dir /absolute/path/to/pdfs \
  --output-dir /absolute/path/to/output \
  --conference ccs
```

`--conference` 应使用稳定的会议标识，例如 `ccs`、`ieee_s&p`、`ndss` 或
`usenix_security`。自动采集任务必须显式传入该参数，不要依赖批次目录名推断策略。

## 自动采集契约

1. 为每个会议和批次使用独立输入、输出目录；不要让两个任务写入同一个
   `author_metadata_dataset*`。
2. 使用固定的 `GROBID_LOCK_PATH` 共享同一 runtime 锁；需要时设置
   `GROBID_LOCK_TIMEOUT` 和 `GROBID_RUN_LOG_DIR`。同一个 GROBID home 不要并发运行。
3. 将命令非零退出视为批次失败。没有 PDF、没有生成 TEI 或 GROBID 子进程失败时，不得
   继续清洗、合并或统计。
4. 命令成功后读取每个数据集的 `extraction_metrics.json`，核对
   `papers_total == papers_processed + parse_errors`，并检查 `parse_errors`、
   `papers_without_authors` 和 `papers_requiring_review`。
5. 将解析错误或无作者记录视为阻断性质量错误；将 `review_queue.csv` 作为自动诊断输出。保留
   `evidence_json/` 和 `candidate_json/`，不得用空值或弱候选静默覆盖直接证据。
6. 自动核对 `paper_metadata.csv` 的字段、行数、论文数、作者顺序和机构覆盖情况。结构性质量检查
   通过后，交给 `$conference-affiliation-normalizer` 或下游统计。
7. 以批次目录作为幂等边界。重跑同一批次前先归档或明确替换该批次输出，不要把不同批次
   追加到同一个临时目录。

每次生成年度作者元数据 CSV 后，按会议或出版格式执行自动完整性与一致性检查，覆盖作者姓名、
作者顺序、机构串、邮箱、第一作者、共同一作和通讯作者等字段。ACM、IEEE、USENIX、NDSS
和密码学会议分别使用对应的版式规则，不能只依赖总体行数或字段非空率。

如需在新项目里直接处理 PDF，可一并迁移当前目录下的 `grobid-runtime/`
（已过滤为运行所需的最小集合）。

脚本会自动按目录结构定位以下路径：

```python
conference-grobid-extract-metadata/
├── scripts/
└── ../data/
    ├── raw_data/
    │   └── usenix_security_2020/   ← 子目录也会被递归扫描
    ├── author_metadata_dataset/           ← 顶层 PDF 的产物
    │   ├── pdf_stage/
    │   ├── tei_header_xml/
    │   ├── metadata_json/
    │   ├── evidence_json/
    │   ├── candidate_json/
    │   ├── paper_index.csv
    │   ├── skipped_files.csv
    │   ├── review_queue.csv
    │   ├── extraction_metrics.json
    │   └── paper_metadata.csv
    └── author_metadata_dataset_usenix_security_2020/  ← 子目录产物自动隔离
        └── ...
```

**子目录隔离**：当输入目录包含子目录时，每个子目录的 PDF 会被分组处理，产物写入独立的输出目录（`author_metadata_dataset_{子目录名}/`），不会混在一起。

如果迁移后的项目目录不同，再按需调整脚本顶部的 `DATA_DIR` 推导逻辑即可。
也可以通过环境变量 `GROBID_METADATA_DATA_DIR=/path/to/data` 覆盖默认数据目录。

## 会议版式专属策略

不同会议的论文模板、出版平台和作者信息排版并不一致，提取和清洗方案必须随会议格式
变化。不要假设一套“从 GROBID XML 直接读取作者和机构”的规则适用于所有会议，也不要
把某个会议验证过的正则、作者块边界、机构传播规则直接套到另一个会议。会议差异通常体现在：

- 作者姓名、机构、邮箱是否分列，是否混在同一连续文本块里；
- 机构和作者的关联方式是上标编号、符号脚注、顺序邻近，还是全体共享；
- 版权声明、下载水印、会议页眉页脚是否靠近标题或作者块；
- 共同一作、通讯作者和 equal contribution 标记是否在首页脚注、末页说明或正文致谢；
- 同一会议跨年份是否更换模板、出版商或页面结构。

当前流水线采用：

1. 同一 PDF 先由 GROBID 生成结构化 header TEI 主结果；
2. 用 pdfplumber 校验姓名字符、摘要边界、首页文本块和页面位置；
3. 用 pypdf 补充 PDF 文档信息和链接/`mailto` 证据；
4. 按标题、作者、邮箱、机构、作者—机构关系、作者角色和摘要分别合并证据；
5. 只执行有直接证据的高置信自动修正，冲突或低置信候选保留在 `candidate_json/` 并进入 `review_queue.csv`。

PDF 首页字符/版式校验依赖 `pdfplumber`，链接与文档信息补证依赖 `pypdf`。自动流水线选用的
Python 3.11+ 环境必须安装两者；
若 `first_page_lines` 为空，应先检查运行时依赖或 PDF 文本层，不能把全 `false` 角色结果
解释为论文没有通讯作者或共同一作。

会议策略入口位于 `scripts/*_strategy.py`，通过
`scripts/author_metadata/strategies/` 适配到流水线。新增会议时，应先确认该会议
的版式特征，再决定是否需要单独 strategy；不要只复制通用清洗规则并假定字段
结构相同。

当前已知策略和主要差异：

| 会议/出版格式 | 版式特征与主要风险 | 提取/清洗重点 |
|---|---|---|
| CCS | ACM 风格作者块可能存在多列机构、邮箱与脚注符号；PDF 候选作者信息有时只有作者名，机构覆盖率低于 TEI | 结合 PDF 作者块修复作者、邮箱和角色；只有当 PDF 候选不损失已有机构覆盖率时才替换更丰富的 TEI 作者记录；清理 ACM/版权前缀和脚注标记 |
| IEEE S&P | IEEE 首页常带版权水印、下载信息、会议年份和复杂脚注；邮箱和机构可能分散在作者块与地址行 | 先过滤 IEEE 水印和会议信息，再从 PDF 上下文补邮箱/机构；标题清洗不能把会议前缀或水印当成标题；作者顺序以首页作者块和 TEI 交叉校验 |
| NDSS | 作者信息常见共享机构、上标/符号关联、邮箱脚注和会议模板文本；GROBID 可能把地址片段拆散 | 优先保留 TEI 作者顺序，使用 PDF 脚注和共享机构信息补齐映射；清洗符号、重复地址片段和模板噪声；对通讯作者和共同一作只在有明确标记时启发式标注 |
| USENIX Security | 作者区常以连续文本列出姓名、机构和邮箱，机构可能是全体作者共享的多行地址；版式跨年份变化明显 | 使用 USENIX 专属作者/机构块解析；只有共享机构版式证据成立时才传播；禁止从邮箱域名生成机构 |
| CRYPTO / EUROCRYPT / ASIACRYPT 等 LNCS/Springer 风格 | 作者、机构、邮箱常通过上标编号和 `\inst` 风格布局关联；Springer 信封字形在 PDF 文本中常提取为姓名后的 `(B)`；脚注和资助信息容易混入机构 | 使用共享 LNCS strategy 解析姓名后的 `(B)` 为通讯作者，支持一篇论文多个通讯作者；只在明确出现 equal-contribution 文本时标共同一作；机构拆分时保留主体，不把城市/国家当机构 |
| 未配置 strategy 的会议 | 版式未知，只有通用 TEI 与通用 PDF 修复可用 | 保留原始提取结果，标记低置信字段并安排人工抽查；不要把其他会议的规则直接套用 |

### PDF 首页版式分类

处理标题、作者、机构和邮箱前，先识别 PDF 首页实际版式，不能只根据会议名固定一种
parser。同一会议、同一年份中也可能出现不同作者块结构。当前版式分类包括：

- **标题区域 6 类**：标准单行标题、多行长标题、会议页眉后的标题、主标题与副标题、
  标题与作者行粘连、封面或特殊出版页后的标题。
- **作者区域 10 类**：单行连续作者、多行作者、作者卡片、横向列对齐矩阵、纵向堆叠、
  作者上标与集中机构列表、多个作者组分别共享机构、全体作者共享机构或邮箱、首页脚注
  或页侧信息、首页与后续页面分别出现作者信息。
- **机构区域 10 类**：单行完整机构、多行机构与地址、部门—主体机构层级、编号或符号
  机构列表、一名作者对应多个机构、全体作者共享机构、作者卡片或矩阵中的局部机构、
  首页脚注或页侧机构、被 PDF 文本层打散的机构、纯地址/城市/国家信息。
- **邮箱区域 8 类**：单作者完整邮箱、多个完整邮箱集中排列、花括号共享域名、局部邮箱与
  共享域名分离、作者卡片或矩阵中的邮箱、脚注或通讯作者邮箱、被换行或文本层打散的邮箱、
  公共邮箱或无法明确归属的邮箱。
- **作者角色 7 类**：第一作者、共同一作、一般共同贡献、通讯作者、多名通讯作者、同一脚注
  包含多个角色、没有明确角色说明。

一篇论文可以同时匹配一种作者排列方式、一种机构关联方式和一种特殊补充位置。版式规则
必须按字段使用：可靠 TEI 作者列表可以保留，而 PDF 版式只补机构或邮箱；只有 PDF 作者
集合、阅读顺序和局部关系全部闭合时，才允许重建作者列表。具体识别特征、处理规则与禁止
条件见 [PDF 首页版式规则](references/pdf-first-page-layout-rules.md)。

因此，提取和清洗方案应按以下顺序设计：

- **先按会议分组**：输入目录、文件名或 CLI 的会议参数应能稳定识别会议；
- **再识别版式**：抽样检查首页作者块、机构列数、上标/脚注符号、共享机构、版权文本和跨年份变化；
- **然后选择来源优先级**：通常是 TEI 结构化字段优先，PDF 上下文用于补缺和纠错；若某会议 PDF 首页比 TEI 更可靠，可以在该 strategy 中显式调整优先级；
- **最后做字段级合并**：作者名、作者顺序、机构、邮箱、标题和角色应分别判断，不能因为 PDF 作者名更完整就整体覆盖 TEI；
- **记录覆盖率变化**：如果 PDF 候选作者会丢失已有机构或邮箱信息，应拒绝整体替换，只合并更可信的缺失字段。
- **保留可审计痕迹**：新增或修改 strategy 时，应在代码或输出日志中能看出哪些字段来自 TEI、PDF 上下文、文件名回退或启发式推断。

常见决策边界：

- 作者顺序：优先使用会议模板中最稳定的顺序来源；如果 TEI 和 PDF 首页冲突，抽查原 PDF，不要自动排序或按姓名字母重排。
- 机构关联：只有存在上标、脚注、邻近块、共享机构说明或稳定模板时才传播机构；不要把同页任意组织名传播给全部作者。
- 邮箱归属：邮箱与作者一一对应、域名组邮箱、花括号邮箱和脚注邮箱需要分别处理；无法可靠映射时可保留论文级邮箱，但不要虚构作者级邮箱。
- 标题清洗：不同会议的页眉、版权、水印和 proceedings 前缀不同；标题规则应先排除该会议特有噪声，再做通用规范化。
- 作者角色：共同一作和通讯作者必须依赖明确文本或符号线索；没有证据时只保守标注第一位作者。

## 字段规则与保守边界

本节的编号映射完整性、机构逐行导出、15 列作者 CSV、末尾国家传播和 ORCID 规则，是
CCS、IEEE S&P、NDSS、USENIX Security 四大安全会议的强制公共契约，不得只在某一个
会议的定稿脚本中实现。会议 strategy 只负责各自版式的作者、机构、编号和脚注证据解析。

- **第一作者**：按最终确认的出版顺序标记第一位；共同一作只有明确姓名列表或明确 `first N authors`
  语义时才扩展第一作者集合。仅出现 `equal contribution` 而没有范围时不猜测，进入复核。
- **通讯作者**：必须有显式姓名、符号脚注、信封标记或可定位的 `corresponding author` 语义；邮箱存在
  只证明邮箱，不证明通讯身份。
- **第一机构**：取第一作者集合的作者—机构关系中按 PDF 阅读顺序的第一机构；共一时保留所有共一作者
  的机构，不把它们压成单一实体。
- **参与机构**：取所有已确认作者—机构关系的去重并集；未知、孤立或仅有地点的机构只保留候选，不进入
  参与机构集合。
- **作者—机构关系**：上标/编号一致、同一作者卡片、同列且有邮箱/地点支持为强证据；单纯线性相邻、同姓、
  机构多数票和“唯一机构传播”均不足以自动建立关系。邮箱域名只有满足下述同论文唯一回填规则时可用。
- **编号映射完整性**：先汇总整篇论文所有作者引用的机构编号。只有引用集合中的每一个编号都能映射到明确
  机构时，才采用 PDF 编号映射；缺少任意编号时，整个编号映射候选作废，不允许保留部分命中。
- **共享基础机构与符号例外**：这是所有会议通用的基础规则，不按会议名启用。只有 TEI 作者全部在首页
  摘要前作者区按原顺序唯一出现、至少一位作者无符号且至少一位作者带符号、存在明确无符号基础机构，
  并且作者引用的每个符号都完整且唯一地定义了机构时才写回。无符号作者只取基础机构；带符号作者只取
  对应符号机构，多符号机构逐项保留。符号若同时出现在 `corresponding author`、`equal contribution` 等
  角色说明中，不得作为机构符号；缺少基础机构、符号未定义或已有 TEI 机构冲突时整条机构候选作废。
  花括号邮箱组仅在目标作者组和邮箱数量完全相等、作者顺序完整且不与已有邮箱冲突时按顺序补空值。
- **全作者上标映射**：如果每位作者都带一个或多个上标，且作者引用的全部符号与首页机构定义一一闭合，
  则使用完整 PDF 映射替换错误或合并的 TEI 机构。一个作者的多个上标必须保留为多个独立机构值，并按
  `affiliation_rank=0,1,2...` 分行导出。支持 `{name@, other@mail.}example.edu` 共享域名邮箱写法，但每个
  邮箱局部名必须唯一匹配作者。
- **邮箱域名反推机构**：作为所有会议的保守回填，只填机构为空的作者。邮箱必须是非公共邮箱域名，并且
  同一论文中该组织域名已由直接证据唯一对应一个单一机构；多机构种子、公共邮箱、域名对应多个机构或
  目标作者姓名仍含版式符号/数字、仅靠外部常识猜测机构时都不回填。完整编号/符号映射始终优先。
- **分离坐标块的完整符号映射**：作者名、作者符号、机构符号和机构文本被 PDF 抽取为独立块时，按同一
  作者行的横向姓名末端位置关联作者符号，并按机构行内符号的横向位置切分和关联机构。只有全部真实作者
  和全部机构符号闭合时才允许替换重叠但错误的 TEI 机构；一个作者的多个符号仍逐条输出机构。页脚
  `affiliated with`、`was at ... during this work` 等明确机构说明单独补充到被点名作者，不能传播给同符号
  或相邻作者。连续角色脚注必须先按句号和脚注符号切分，防止下一条机构说明中的姓名被误标为通讯作者。
- **通用封闭作者卡片规则**：作者字号不得使用固定会议阈值；先用 GROBID 作者名在 PDF 首页摘要前块中
  精确锚定主字号，再按同字号、姓名形状和下方机构块发现漏提作者。只有所有已有有效作者均精确匹配、
  新候选均有唯一邻近机构、阅读顺序（先纵向后横向）闭合且无重叠歧义时，才跨会议自动重建作者列表，
  不以邮箱存在作为必要条件。机构块右上方的数字上标只能映射到其所属作者卡；若页脚出现
  `while affiliated with`、`during this work` 等明确说明，只把对应机构追加到该作者，绝不传播给全体作者。
- **机构逐行导出**：作者有多条机构时，每条机构独立输出一行，`affiliation_rank` 按该作者机构顺序从
  `0` 连续编号；无机构作者仍输出一行，机构和国家留空。作者级字段在这些机构行中必须保持一致。
- **国家与 ORCID**：`country` 只从机构原文末尾明确出现的国家或地区名提取，不按邮箱域名或机构知识库
  推测。同一作者有多条机构、前面机构均无国家且仅最后一条机构末尾有明确国家时，将该国家填写到该作者
  的全部机构行；若前面已有不同国家则不传播。`orcid` 只接受作者 TEI/PDF 中明确出现且能唯一归属的
  ORCID，统一输出为 `https://orcid.org/...`。
- **作者 CSV 契约**：列顺序固定为 `paper_id,year,conference,title,author,author_rank,affiliation_rank,`
  `affiliations,emails,first_author,co_first_author,corresponding,equal_contribution,country,orcid`。
- **原始机构文本**：保留 PDF 中的完整字符串和地点；只去除明确邮箱、URL、脚注符号和由坐标确认的完整
  作者 span，不按逗号、`of/for` 或地点词过度拆分或标准化。
- **摘要**：GROBID `profileDesc/abstract` 为主；pdfplumber 以 `Abstract` 到 `Keywords/Introduction` 的版面
  边界校验并在 GROBID 缺失时提供候选；两者冲突时保留 GROBID 并进入复核。摘要单独输出为
  `conference_year_paper_abstract.csv`，列固定为 `conference,year,title,abstract`。
- **证据单调性**：后续阶段不得把已有直接非空机构、邮箱、作者或摘要静默改为空；候选覆盖下降、作者数冲突、
  角色范围不明和提取器不可用都必须写入复核队列。

通用策略补充：

- **TEI 等长尾部机构节点按序映射**：若 header 中先出现 `N` 个有姓名但无机构的作者节点，
  随后恰好出现 `N` 个无姓名、无邮箱且各自含明确机构的作者节点，可按原始节点顺序一一映射；
  该规则跨会议生效，但必须满足 `N/N` 全覆盖，数量不等、任一尾节点为空或夹杂人物信息时整条候选作废，
  不允许部分写回。
- **作者姓名只做证据支持的标点恢复**：不得用全局正则把连续首字母与姓氏拼接，也不得删除 TEI 已保留的
  姓名分词边界。只有 PDF 首页与 TEI 的作者数量、顺序及规范化姓名逐项一致时，才可用 PDF 原文恢复
  `W. H.`、`P. K.` 等首字母标点；同人数但任一姓名不一致时不自动改名。
- **跨列全宽机构块不是单人卡片**：机构文本块若横跨两个或更多互相分离的作者列，即使其几何中心落在
  中间作者下方，也不得作为该作者的局部机构关系。重复机构被 pdfplumber 合并为全宽行时，只能在共享机构、
  完整编号映射或 TEI 等长尾节点映射等闭合证据成立后关联，不能依据中心点邻近传播。
- **先识别作者块版式，再决定解析器**：同一会议也可能同时存在“作者集中列出后统一列机构”“逐作者卡片”“上标编号映射”“符号脚注映射”“共享机构块”等格式。不要只按会议名固定一种 parser；应先在 PDF 首页 pre-abstract 区域检测姓名、邮箱、机构、地点、上标和脚注的排列形态，再选择对应解析策略。
- **逐作者卡片要同时支持两种顺序**：ACM/CCS 等模板里常见 `作者 -> 邮箱 -> 机构/地点`，也常见 `作者 -> 机构/地点 -> 邮箱`。解析时应以“下一个可信作者名”作为当前卡片边界，邮箱和机构顺序不能写死；地点行应合并到当前机构，`for/of/and` 结尾的机构行应继续拼接下一行。
- **多列/右上角机构要防止被线性化打散**：PDF 文本抽取会把视觉上的左列、右列、上方机构块压成一串行文本，右上角机构尤其容易和相邻作者错位。遇到 ACM 多列作者区时，应优先按局部卡片邻近关系重建作者-邮箱-机构，不要用一个全局 stage machine 从“作者阶段”一次性切到“机构阶段”。
- **parser 选择要看信息覆盖率**：如果某个候选 parser 能识别更多作者，但明显丢失大部分机构或邮箱，不应整体覆盖 TEI；可以只合并缺失字段。反过来，如果 PDF 卡片 parser 同时恢复了作者数、顺序、邮箱和机构覆盖率，则可在该会议 strategy 中优先使用。
- **机构/人名判断要保守**：短机构和缩写机构（如 `CSAIL, MIT`、`TU Crete`、`Aarno Labs`）不应被误判成人名；含 `University`、`Institute`、`Center/Centre`、`Lab/Labs`、`Security`、`Research`、已知高校/研究机构缩写或公司词的行，应优先作为机构候选。全大写缩写加地名/机构词的两词短语通常不是作者。
- **未知短机构需要组合证据**：对于 `Technion`、`Dragos`、`Five Rings` 这类无法仅凭词典确认的短字符串，只有已确认作者名、同列短机构、紧邻地点和同卡片邮箱同时成立时才自动接收；缺少地点或邮箱时只保留候选。
- **作者列表重建要验证主字号和完整支持**：先用现有 TEI 作者精确锚定首页主作者字号；只有所有已有有效作者均精确匹配、每个页面人名候选都有同列机构支持、姓名不重复且至少有两位作者时，才可按页面阅读顺序重建作者列表。邮箱缺失不阻断闭合卡片映射；重建后必须重新计算 `order`、第一作者、共同一作、通讯作者和导出 rank。
- **机构清洗不能过度拆分**：`CSAIL, MIT`、`CISPA Helmholtz Center for Information Security`、`IBM Research Europe / ETH Zurich` 这类字符串应作为一个作者机构候选保留。只有存在明确分隔符、编号映射或多个独立机构线索时才拆分；不要因为逗号、`for`、`of` 或地点词就把单一机构拆成多个残片。
- **残片必须在提取阶段处理**：`University, China`、`Science and, Technology`、`Republic of, Korea` 等不是可交给 AffilGood 的完整原始机构。只有固定语法相邻片段可直接重组；否则必须由高置信 PDF 卡片关系替换或进入复核。
- **地点行只补充，不替代机构**：城市、州、省、国家行应追加到最近的机构行，例如 `Bergische Universität Wuppertal` + `Wuppertal, Germany`，但不要把纯地点当成独立机构；如果没有可归属机构，则保留为低置信候选或待人工核对。
- **官网差异不等于提取错误**：官网元数据只用于对照。若 PDF 首页作者卡片、机构原文和空间关系确认没有截取或错位，应保留 PDF 机构，并标记为实际出版版本的机构调整；不要为了与官网一致而覆盖 PDF 原文。
- **PDF 国家优先于官网 DOM 国家**：国家是独立于机构关系的字段级 PDF 直接证据。首次官网对账时，应从对账前的 PDF 导出结果按作者和 `affiliation_rank` 持久化为 `pdf_countries`；重跑时使用最早的 `before_official_web_*` 备份恢复，已有非空 `pdf_countries` 不得覆盖。官网可以替换作者机构关系，但导出时必须先保留 PDF 国家：PDF 只有一个非空国家时传播到该作者全部机构行；PDF 有多个国家时按原 `affiliation_rank` 使用；只有对应 PDF 国家为空时，才允许使用官网 DOM 机构末尾的国家补值。该规则对 CCS、IEEE S&P、NDSS 和 USENIX Security 全部生效。
 - **脚注角色识别要解析语义而不只看符号**：NDSS 等模板常把作者行写成 `作者 †∗`、`作者 ¶`，但脚注正文可能是 `The first two authors made equal contribution` 或 `X is the corresponding author`。遇到 `first two/three/four/five/N authors`、`made equal contribution`、`contributed equally`、`co-first authors` 时，应将角色映射到前 N 位作者或明确提到的作者；遇到 `corresponding author(s)` 时，应同时支持符号映射和显式姓名映射。不要只因为作者行有 `*` 就标共同一作，也不要只依赖邮箱图标；必须结合脚注文本确认角色含义。
 - **同一脚注行可能包含多个角色说明**：PDF 文本抽取可能把 `∗The first two authors made equal contribution.¶Zhikun Zhang is the corresponding author.` 合并到一行。解析时应按脚注符号或角色关键词切分，而不是把整行当成单一脚注；共同一作和通讯作者应分别落到不同作者字段。
- **会议专属规则优先放在 strategy 中**：ACM 作者卡片、IEEE 符号脚注、USENIX 共享机构、LNCS 编号机构等都应放在对应会议策略里。全局清洗只放高度通用、低风险的噪声过滤和字段规范化，避免一个会议的强假设污染其他会议。

会议策略的修改应至少用该会议的真实样本验证以下情况：单作者、多作者、多机构、
共享机构、邮箱缺失、脚注标记、共同一作、通讯作者、版权水印、标题前缀和跨年份
版式变化。验证样本应覆盖目标会议的不同年份；如果发现某一年模板明显不同，应拆分
年份分支或增加格式检测，而不是扩大通用正则。验证通过后再将策略用于整批数据。

## 输入

论文 PDF 文件，放在 `data/raw_data/` 下。支持递归扫描子目录，子目录中的 PDF 会被自动发现并按目录分组处理，每组产物写入独立的输出目录。

可通过 CLI 参数指定输入/输出目录：

```bash
python scripts/extract_paper_metadata.py \
    --input-dir data/raw_data/usenix_security_2020 \
    --output-dir data
```

- `--input-dir`：PDF 输入目录（默认 `data/raw_data/`），递归扫描
- `--output-dir`：输出根目录（默认 `data/`），产物写入其下的 `author_metadata_dataset/`
- `--conference`：显式会议标识；自动采集必须传入，交互运行省略时回退为输入目录名

## 输出

### 数据集目录

- `data/author_metadata_dataset/pdf_stage/`
- `data/author_metadata_dataset/tei_header_xml/`
- `data/author_metadata_dataset/metadata_json/`
- `data/author_metadata_dataset/evidence_json/`（TEI/PDF 原始证据）
- `data/author_metadata_dataset/candidate_json/`（候选值、选择与拒绝原因）
- `data/author_metadata_dataset/paper_index.csv`
- `data/author_metadata_dataset/skipped_files.csv`
- `data/author_metadata_dataset/review_queue.csv`（字段冲突和低置信候选）
- `data/author_metadata_dataset/extraction_metrics.json`（批次质量指标）
- `data/author_metadata_dataset/conference_year_paper_abstract.csv`（每篇论文一行的摘要表）

`metadata_json/` 和 `paper_metadata.csv` 的原有主字段保持兼容。详细 JSON 新增
`_extraction`，记录证据、候选、字段恢复决策和复核原因。后处理不得静默把有直接证据的
非空机构或邮箱变为空；弱来源、错位作者或冲突候选应保留在候选文件并进入复核队列。

PDF 证据还包含首页文本 block 的 `bbox` 和 `font_size`。当前二维关系层可识别逐作者卡片/
网格版式，并通过主作者字号和局部邮箱/机构支持重建高置信作者列表。对最终作者与页面 block
的局部精确关系可自动补空机构；已有机构与二维候选冲突时只写入 `review_queue.csv`，不覆盖
或追加。自动重建和补全是全会议通用规则，但只有现有作者精确锚定、候选机构关系完整闭合且无歧义时
才执行；否则只保留二维候选。

生成上述年度产物后，应向使用者明确说明需要人工核对的 CSV 路径，例如：
`data/asiacrypt_full_output/author_metadata_dataset_2025/paper_metadata.csv`。

### CSV（每行一个作者）

| 列 | 说明 |
|---|---|
| `title` | 论文标题 |
| `author` | 作者姓名 |
| `author_rank` | 导出作者顺序；共同一作都记为 `0`，其余作者顺延 |
| `affiliation_rank` | 同一作者的机构顺序，从 `0` 开始；多机构作者按机构逐行输出 |
| `affiliations` | 当前行对应的单个机构，不把多个机构合并在一行 |
| `emails` | 作者邮箱 |
| `first_author` | 是否属于第一作者集合；共同一作也为 `true` |
| `co_first_author` | 是否共同一作（启发式判断） |
| `corresponding` | 是否通讯作者（启发式判断） |
| `equal_contribution` | 是否 equal contribution（启发式判断） |

### JSON（每篇论文一个文件）

```json
{
  "title": "...",
  "year": "2022",
  "abstract": "...",
  "first_authors": ["..."],
  "co_first_authors": [],
  "corresponding_authors": ["..."],
  "first_affiliation": "...",
  "first_affiliations": ["..."],
  "participating_affiliations": ["..."],
  "author_affiliation_relations": [],
  "authors": [
    {
      "order": 0,
      "name": "...",
      "email": "...",
      "affiliations": ["..."],
      "affiliation_source": "author_node",
      "first_author": true,
      "co_first_author": false,
      "corresponding": true,
      "equal_contribution": false
    }
  ]
}
```

作者角色字段当前采用保守启发式规则：

- `first_author`：第 0 位作者默认为 `true`；若识别为共同一作，则这些作者也记为 `true`
- `corresponding`：只接受显式姓名、符号/信封脚注或明确 `corresponding author` 语义；有邮箱不等于通讯作者
- `co_first_author` / `equal_contribution`：只接受明确姓名列表或 `first two/three/N authors` 范围；只有关键词而无范围时保持 `false` 并进入复核

作者列表经官网或人工修复后，可只回放 PDF 角色识别，不重跑 GROBID：

```bash
python3 scripts/enrich_pdf_author_roles.py \
  --dataset-dir /path/to/author_metadata_dataset_2021 \
  --conference ccs
```

默认只生成 dry-run 报告；核对后增加 `--apply`。该脚本只重算角色字段和角色审计证据，
不修改作者、顺序、机构、邮箱、标题、年份或摘要，应用前会备份 CSV 和 JSON 产物。

人工复核发现明确的作者、机构或对应关系错误时，应把预期旧状态、修正值和 PDF 证据写入
审核清单，再通过保护性脚本应用；不要直接手改派生 CSV。脚本会在标题或作者序列已变化时
拒绝写入，并为原始 JSON/CSV 建立备份：

```bash
python3 scripts/apply_reviewed_metadata_corrections.py \
  --dataset-dir /path/to/author_metadata_dataset_2024 \
  --corrections /path/to/reviewed_metadata_corrections.json
```

应用后重新执行官网对照和 PDF 角色回放，以统一重建 `paper_metadata.csv`、摘要表、证据文件
和 `review_queue.csv`。审核清单本身应随年度数据集保留，作为人工修正的可追溯依据。

四大安全会议（CCS、IEEE S&P、NDSS、USENIX Security）的自动化顺序固定为：PDF 主提取
→ 官网 DOM 作者机构对照 → PDF 作者角色回放。默认保守模式只补空机构并保留冲突；当任务明确要求
以官网为准且不保留作者机构人工复核时，运行：

```bash
python3 scripts/reconcile_security_official_metadata.py \
  --dataset-dir /path/to/author_metadata_dataset_2025 \
  --conference IEEE_S&P --year 2025 \
  --official-authoritative \
  --require-all-papers-matched \
  --require-complete-affiliations \
  --apply
```

权威模式只有在标题精确、紧凑精确、唯一长标题包含、唯一高分模糊匹配或完整作者序列唯一命中时
才可重建作者列表，并保留已有邮箱、ORCID 和角色字段。官网 DOM 缓存写入
`official_web_evidence/`；正式写入前必须满足全部本地论文已命中且每位作者至少一个机构，否则中止。
官网页面若只列作者而缺机构，只能使用 PDF 首页完整符号机构行等直接证据补齐，不能把
`Equal Contribution`、`Corresponding Author` 等角色说明当作机构。官网作者机构权威模式不负责
解决共同一作或通讯作者范围，角色仍由 PDF 明确脚注证据决定。

## 最小清洗规则

脚本只自动移除能够被明确识别为版式噪声的内容；以下规则不得扩展为全局“看起来像”的删除：

| 噪声类型 | 示例 | 处理方式 |
|----------|------|----------|
| 机构名误识别为作者 | `Fondazione Bruno Kessler` | 仅在机构证据或会议策略明确确认时移除，否则进入复核 |
| 脚注缩写重复作者 | `D Zou`（已存在 `Deqing Zou`） | 仅在 PDF 作者区支持完整姓名且缩写未单独出现时去重 |
| IEEE Xplore 水印 | `Authorized licensed use limited...` | 关键词过滤 |
| 会议信息混入 | `ICSE '22 An Image-inspired...` | 关键词过滤 |
| 地址行中的邮箱残留 | `Queen's University {jiayuan.zhou1...` | 花括号内容清洗 |
| 无意义 region | `yuan` | 仅在 TEI 地址字段明确标为 region 且不属于机构原文时过滤 |
| URL 混入机构 | `https://...` | 协议前缀过滤 |
| 脚注标记 | `• D Zou` → `D Zou` | 正则清洗 |

这些清洗规则只是通用底线。会议 strategy 可以增加专属噪声过滤和字段修复，但应避免
把某个会议的强假设放进全局清洗。例如 IEEE 水印过滤可以全局保守处理，而 ACM 作者块、
USENIX 共享机构、LNCS 上标机构映射等规则应留在对应会议 strategy 中。

## 年份提取优先级

1. `monogr/imprint/date[@type='published']/@when`
2. `biblStruct/note` 中的 submission 年份（如 `received 3 Sept. 2020`）
3. PDF 文件名中的年份（如 `Bhat et al_2018_Var-CNN.pdf`）

## 详细参考

- [GROBID TEI XML 结构参考](references/REFERENCE.md)
- [PDF 首页版式规则](references/pdf-first-page-layout-rules.md)
