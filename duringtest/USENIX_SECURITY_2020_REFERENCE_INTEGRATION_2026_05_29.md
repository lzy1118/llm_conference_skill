# USENIX Security 2020 Reference Integration - 2026-05-29

## 目标

- 完成 `USENIX Security 2020` 作者-机构-国家采集。
- 把 `conference-dataset-normalization/references/institution_aliases.csv` 与 `conference-dataset-normalization/references/institution_registry.csv` 真正接入现有流程，而不是只作为旁路参考。
- 记录不同方法下的 unresolved error rate 变化，并给出后续可复现实验与消融实验建议。

## 参考文件是否应使用

应该使用。

这两个文件的定位如下：

- `conference-dataset-normalization/references/institution_aliases.csv`
  - 作用：把机构别名映射到稳定 `institution_id`。
- `conference-dataset-normalization/references/institution_registry.csv`
  - 作用：通过 `institution_id` 提供 `canonical_name / country / region / type`。

它们最适合接入两个 skill / 流程：

- `conference-paper-extraction`
  - 用作精确别名命中的国家兜底，不替代网页抓取与规则分类，只在“机构名本身可精确映射”时生效。
- `conference-dataset-normalization`
  - 用作机构标准化来源，补 `institution_id`、canonical name、country、region、type。

## 本次接入内容

### 1. 抽取层接入标准化 reference

修改位置：

- `conference-paper-extraction/scripts/classification_common.py`
- `conference-paper-extraction/scripts/security_real_backend.py`

做了三件事：

- 扩充泛化国家规则，补齐高频未解析机构。
- 修复 `and` 拆分导致机构名被错误拆开的情况。
- 新增全局 reference registry fallback：
  - 读取 `conference-dataset-normalization/references/institution_aliases.csv`
  - 读取 `conference-dataset-normalization/references/institution_registry.csv`
  - 对 exact alias / canonical name 命中的机构，直接给出 `reference_registry` 来源的国家结果。

额外修复：

- 这两份 CSV 的表头带有 BOM 和引号，例如 `"alias"`，原始 `DictReader` 直接按 `alias` 读不到。
- 现在已在读取函数里做表头归一化兼容。

### 2. 标准化层接入 skill 内部 reference

修改位置：

- `conference-dataset-normalization/scripts/normalize_dataset.py`

新增输出：

- 在 `author_affiliation_facts.csv` 中新增：
  - `institution_id`
  - `canonical_institution_name`
- 在 `institution_dim.csv` 中新增：
  - `institution_id`
  - `canonical_name`
  - `country`
  - `region`
  - `type`
- 在 `normalization_report.json` 中新增：
  - `rows_with_reference_institution_id`

## 执行命令

初始采集：

```bash
python3 conference-paper-extraction/scripts/run_unified_pipeline.py --conference usenix_security_2020 --output-dir generated-data/extraction --fetch --fetch-affiliations
```

规则增强后重跑：

```bash
python3 conference-paper-extraction/scripts/run_unified_pipeline.py --conference usenix_security_2020 --output-dir generated-data/extraction --fetch-affiliations
```

接入全局 reference 后重跑：

```bash
python3 conference-paper-extraction/scripts/run_unified_pipeline.py --conference usenix_security_2020 --output-dir generated-data/extraction --fetch-affiliations
```

标准化验证：

```bash
python3 conference-dataset-normalization/scripts/normalize_dataset.py generated-data/extraction/output/usenix_security_2020_author_affiliations_audit.csv --output-dir generated-data/usenix-security-2020-check
```

## 不同方法错误率对比

统一以 `expanded_author_rows = 754` 为分母。

### 方法 A：原始流程

- classified rows: 665
- unresolved rows: 89
- unresolved rate: `89 / 754 = 11.80%`

特点：

- 能完成基础采集。
- 但大量机构名没有国家映射，尤其是企业名、缩写名、以及部分非英文高校名。

### 方法 B：仅增强泛化规则

- classified rows: 738
- unresolved rows: 16
- unresolved rate: `16 / 754 = 2.12%`

相对方法 A：

- unresolved 从 89 降到 16
- 绝对减少 73 条
- 相对减少约 `82.02%`

主要收益来源：

- 增加国家关键词规则。
- 增加美国高校 / 企业规则。
- 修复部分 `and` 误拆。

### 方法 C：泛化规则 + skill 内部 reference 精确别名兜底

- classified rows: 748
- unresolved rows: 6
- unresolved rate: `6 / 754 = 0.80%`

相对方法 B：

- unresolved 从 16 降到 6
- 绝对减少 10 条
- 相对减少约 `62.50%`

相对方法 A：

- unresolved 从 89 降到 6
- 绝对减少 83 条
- 相对减少约 `93.26%`

这个结果说明：

- 泛化规则负责覆盖“名字本身可推断国家”的大部分机构。
- 这组 skill 内部 reference 更适合作为 exact alias / registry fallback，解决 `DFINITY`、`Protocol Labs`、`State Key Laboratory ...` 这类规则不稳、但 registry 可精确命中的机构。

## 剩余未解析项

当前剩余 6 条 unresolved：

- `IDC`
- `The Tor Project`
- `Hengmuxing Technologies`
- `None`
- `Unaffiliated`
- `Unbound Tech`

处理建议：

- `None`、`Unaffiliated` 应保留 `Unknown`，不要强行猜测。
- `IDC` 歧义较强，不能直接假设等于 `IDC Herzliya`。
- `The Tor Project`、`Hengmuxing Technologies`、`Unbound Tech` 若需要进一步降低 unresolved，可放入人工 override，但建议先确认你希望采用“法律注册地”还是“主要研究地点”口径。

## 标准化验证结果

输出目录：

- `generated-data/usenix-security-2020-check/normalized/`

关键指标：

- input_rows: 748
- normalized_rows: 748
- paper_count: 158
- institution_count: 266
- rows_with_reference_institution_id: 425
- rows_with_unknown_country: 0

说明：

- 这表示在已进入 audit 输出的 748 行中，有 425 行已经成功挂上 `institution_id`。
- 这一步已经把这组 skill 内部 reference 从“仅供参考文件”变成“真实参与标准化输出的结构化来源”。

## 本轮解决的问题与方法

### 问题 1：USENIX 2020 未注册

方法：

- 在 registry 和 security backend 中补 `usenix_security_2020`。

### 问题 2：高频机构未解析

方法：

- 扩充 `classification_common.py` 的国家规则。
- 补企业、高校、研究机构的 exact / keyword 模式。

### 问题 3：机构名被 `and` 错拆

典型例子：

- `National Research Center of Parallel Computer Engineering and Technology`

方法：

- 在 `security_real_backend.py` 的 `split_affiliation_parts()` 中增加保护短语，避免把本来是单机构名的字符串拆成两段。

### 问题 4：reference CSV 表头异常

现象：

- 表头含 BOM 和引号，导致 `DictReader` 用 `alias` / `canonical_name` 直接取值失败。

方法：

- 在抽取层和标准化层都增加 `csv_row_get()` 兼容函数，先做表头规范化再取字段。

## 当前已知残余风险

- 仍有少量 mixed affiliation 的国家语义不够理想，例如一个字符串中混有多机构、多国家时，目前更多是“保守取已知结果”，而不是严格做论文级参与国展开。
- 一些品牌名虽然可映射到国家，但国家口径可能依赖你是按注册地还是研究团队所在地统计。
- `NYU Abu Dhabi`、`Yale-NUS` 这类跨品牌 / 海外校区语义，后续应单独做 richer alias / campus-level registry，而不是继续靠简单关键词。

## 后续可做的消融实验

通用写法模板已统一收口到：`WRITING_NOTES.md` 中的“单案例实验记录模板”“实验对比写法模板”“消融实验模板”。

建议至少做下面 5 组：

### Ablation 1：去掉全局 reference registry

做法：

- 禁用 `classification_common.py` 中的 `load_reference_registry_overrides()`。

观察：

- unresolved 是否从 6 回升到 16。
- 哪些机构必须依赖 exact alias registry 才能解。

### Ablation 2：去掉泛化规则扩充，只保留 reference registry

做法：

- 回退新增 keyword 规则，只保留 global alias / registry fallback。

观察：

- 企业名和高校名里，哪些必须依赖规则，哪些仅靠 registry 即可。
- 这可以区分“规则覆盖贡献”和“参考表覆盖贡献”。

### Ablation 3：恢复原始 `and` 拆分逻辑

做法：

- 去掉 `Parallel Computer Engineering and Technology` 等保护项。

观察：

- 是否重新出现机构名被拆坏，导致 country 回退为 `Unknown`。

### Ablation 4：关闭 `--fetch-affiliations`

做法：

- 只保留 DBLP raw paper metadata，不抓 USENIX 页面作者机构。

观察：

- `papers_with_author_rows`
- `expanded_author_rows`
- 最终可分类行数

这个消融能衡量 venue page affiliation 抓取对整体覆盖率的贡献。

### Ablation 5：只比较 exact alias 命中，不使用 canonical name 回退

做法：

- 在 reference loader 中只使用 `institution_aliases.csv`，不把 registry canonical name 也加入 exact match。

观察：

- 精确别名文件本身覆盖了多少。
- canonical name 补充带来了多少额外收益。

## 推荐后续动作

- 如果目标是尽量接近 100% resolved，可新增一份人工 `institution_country_overrides.csv`，只处理 `IDC / The Tor Project / Hengmuxing Technologies / Unbound Tech` 这 4 个仍有业务歧义但可人工确认的机构。
- 如果目标是长期可复用，优先继续完善 `conference-dataset-normalization/references/`，不要把所有残余问题都写死在规则里。
- 如果后续要做机构排名或跨会议比较，建议直接使用标准化后的：
  - `generated-data/usenix-security-2020-check/normalized/author_affiliation_facts.csv`
  - `generated-data/usenix-security-2020-check/normalized/institution_dim.csv`

## 下游统计执行

### 执行命令

```bash
python3 conference-country-statistics/scripts/country_statistics.py --input generated-data/usenix-security-2020-check/normalized/author_affiliation_facts.csv --output-dir generated-data/usenix-security-2020-check/analysis/countries --conference USENIX_SECURITY --year 2020
python3 conference-institution-statistics/scripts/institution_statistics.py --input generated-data/usenix-security-2020-check/normalized/author_affiliation_facts.csv --output-dir generated-data/usenix-security-2020-check/analysis/institutions --conference USENIX_SECURITY --year 2020
python3 conference-author-statistics/scripts/author_statistics.py --input generated-data/usenix-security-2020-check/normalized/author_affiliation_facts.csv --output-dir generated-data/usenix-security-2020-check/analysis/authors --conference USENIX_SECURITY --year 2020
```

结果：全部成功。

### 产物位置

国家统计：

- `generated-data/usenix-security-2020-check/analysis/countries/country/country_summary.csv`
- `generated-data/usenix-security-2020-check/analysis/countries/country/country_by_conference.csv`
- `generated-data/usenix-security-2020-check/analysis/countries/country/country_by_year.csv`

机构统计：

- `generated-data/usenix-security-2020-check/analysis/institutions/institutions/institution_summary.csv`
- `generated-data/usenix-security-2020-check/analysis/institutions/institutions/institution_by_conference.csv`
- `generated-data/usenix-security-2020-check/analysis/institutions/institutions/institution_by_year.csv`

作者统计：

- `generated-data/usenix-security-2020-check/analysis/authors/authors/author_summary.csv`
- `generated-data/usenix-security-2020-check/analysis/authors/authors/author_by_year.csv`
- `generated-data/usenix-security-2020-check/analysis/authors/authors/first_author_summary.csv`
- `generated-data/usenix-security-2020-check/analysis/authors/authors/coauthor_edges.csv`

## 下游统计结果摘录

### 国家层

Top 5 国家（按 papers）：

1. United States: 111 papers, 415 author rows, 126 institutions
2. China: 25 papers, 116 author rows, 42 institutions
3. Germany: 24 papers, 65 author rows, 21 institutions
4. Switzerland: 12 papers, 23 author rows, 6 institutions
5. South Korea: 8 papers, 19 author rows, 10 institutions

观察：

- 美国占比最高，`paper_share = 0.702532`，但这仍然是“论文参与视角”，不是独占论文视角。
- 中国和德国在 2020 年 USENIX Security 中处于第二梯队，且中国作者行数明显高于德国，说明多作者团队贡献更集中。
- `Multiple` 仍存在，说明部分多国 affiliation 在抽取层被保守保留为跨国参与信号。

### 机构层

Top 5 机构（按 papers）：

1. University of Maryland: 7 papers
2. UC Berkeley: 6 papers
3. CISPA Helmholtz Center for Information Security: 5 papers
4. Purdue University: 5 papers
5. University of California, Irvine: 5 papers

观察：

- 头部机构以美国高校为主，但德国的 CISPA 已进入第一梯队。
- `EPFL` 也达到 5 papers，说明瑞士在顶尖安全研究上的集中度较高。
- 由于标准化层已经挂上 `institution_id`，后续跨年时更适合直接比较 canonical institution，而不是原始显示名。

### 作者层

Top 5 作者（按 papers）：

1. Zhiqiang Lin 0001: 5 papers
2. Michelle L. Mazurek: 4 papers
3. Raluca Ada Popa: 4 papers
4. Daniel Moghimi: 3 papers
5. Berk Sunar: 3 papers

一作特征示例：

- Daniel Moghimi 有 3 篇一作论文。
- Adam Oest 有 2 篇一作论文。
- Daniel Votipka 有 2 篇一作论文。

观察：

- 这里的作者身份仍是保守的 exact name normalization，不建议跨多年直接把它当作“真实去重学者 ID”。
- 如果后面要做跨年作者趋势，建议继续引入更稳定的 author disambiguation 规则或外部 author registry。

## 可以继续做的实验

### 实验 1：剩余 6 条 unresolved 的人工 override 收尾

目的：

- 评估从 `0.80% unresolved` 到接近 `0% unresolved` 的边际收益是否值得。

做法：

- 在 `generated-data/extraction/reference/institution_country_overrides.csv` 中仅加入人工确认过的机构。

建议对比：

- 加 override 前后的国家排名是否变化。
- 机构数和作者数是否只发生极小变化。

### 实验 2：国家排名对“Multiple”口径的敏感性

目的：

- 检查多国 affiliation 保守折叠为 `Multiple` 是否影响国家排名解释。

做法：

- 复制一份实验分支，把 `Multiple` 行展开到多个国家参与视角。

观察：

- 中国、美国、瑞士、新加坡等国家的 `papers` 和 `authors` 是否变化。

### 实验 3：只用 raw rule，不用 reference registry 的下游排名差异

目的：

- 评估这组标准化 reference 对最终统计结果的影响，不只是对 unresolved 数量的影响。

做法：

- 用方法 B 的结果重新做标准化和下游统计。

观察：

- Top 10 国家是否稳定。
- Top 20 机构是否有明显换位。
- `institution_id` 覆盖率下降多少。

## PDF 下载能力补充

### 新增目标

- 在不解析 PDF 内容的前提下，为统一抽取入口补充“下载论文 PDF”能力。
- 让 PDF 成为正式主流程可选产物，而不是只停留在后续 frontmatter / 复核设想里。

### 新增接口

统一入口新增参数：

- `--download-pdfs`
- `--pdf-limit`

适用方式：

```bash
python3 conference-paper-extraction/scripts/run_unified_pipeline.py --conference usenix_security_2020 --output-dir generated-data/extraction --download-pdfs
python3 conference-paper-extraction/scripts/run_unified_pipeline.py --conference usenix_security_2020 --output-dir generated-data/extraction --download-pdfs --pdf-limit 5
```

### 当前实现方式

安全会：

- 从 raw paper metadata 中读取落地页 `url`
- 若 `url` 不是 `.pdf` 直链，则先抓 landing page
- 再在页面里查找 `.pdf` 链接并下载

IACR 会议：

- 仅在 raw metadata 中出现 `.pdf` 直链时下载
- 当前不额外做页面级 PDF 探测

### 输出位置

- PDF 文件目录：`generated-data/extraction/pdfs/<conference_key>/`
- 下载审计表：`generated-data/extraction/interim/<conference_key>_pdf_download_report.csv`
- 下载摘要：`generated-data/extraction/interim/<conference_key>_pdf_download_summary.json`

### USENIX Security 2020 全量下载结果

执行命令：

```bash
python3 conference-paper-extraction/scripts/run_unified_pipeline.py --conference usenix_security_2020 --output-dir generated-data/extraction --download-pdfs
```

结果：

- papers_seen: 159
- downloaded_pdfs: 157
- 下载成功率：`157 / 159 = 98.74%`

产物：

- PDF 目录：`generated-data/extraction/pdfs/usenix_security_2020/`
- 审计表：`generated-data/extraction/interim/usenix_security_2020_pdf_download_report.csv`

### 失败项分析

当前未下载成功的 2 条并不是技术失败，而是落地页本身没有论文 PDF：

1. `The 2020 Election: Remote Voting, Disinformation, and Audit.`
2. `Digital Contact Tracing.`

两者状态均为：

- `status = no_pdf_url`

解释：

- 这两条是 panel / discussion 类页面，不是常规论文页面。
- 因此没有稳定论文 PDF 可下载，当前保守记为 `no_pdf_url` 是合理行为。

### 方法对比与边界

#### 方法 A：只记录 landing page URL

优点：

- 实现最简单

缺点：

- 用户后续仍需手工点页面找 PDF
- 不能形成稳定本地 PDF 缓存

#### 方法 B：landing page -> PDF link -> 下载

当前采用。

优点：

- 对 USENIX 类会议页面非常有效
- 不需要解析 PDF 内容
- 能直接形成可复用 PDF 缓存与审计表

缺点：

- 依赖页面 HTML 中存在可识别 `.pdf` 链接
- 对不同出版平台需要各自适配

#### 方法 C：解析 PDF 内容后再做结构化抽取

当前未启用。

原因：

- 目前需求只要求下载，不要求解析
- PDF 内容解析应单独评估 frontmatter 提取质量和错误率

### 后续可做的实验

1. 对 `top4_security` 其他会议年份评估 PDF 下载覆盖率
2. 比较“只保存 landing page URL”和“直接落本地 PDF”对后续人工复核效率的提升
3. 在后续 frontmatter 解析实验中，以这批已下载 PDF 作为固定输入集，单独评估 PDF 解析错误率
