# 作者单位自动复核流程交接文档

## 当前任务背景

目标是接手“作者单位自动复核独立工作流”，处理 `data/interim/affiliation_resolution_queue.csv` 中作者数和机构数不一致的论文，通过 Springer、DBLP、IACR ePrint、PDF 首页或正式出版页面确认 `author -> affiliation` 映射，尽量减少人工核查。

> 说明：这份文档描述的是旧 `Top3-data/` 阶段围绕美国机构兼容 enriched 输出的独立复核链路。
> 当前仓库正式主契约已经是“作者-机构-国家”长表；文中 `*_美国机构.*`、`resolved_us_rows` 与 `merge_candidates_us_rows.csv` 应理解为旧兼容子流程，而不是当前默认主输出。

这个流程独立于原始采集流程。不要修改 `Plan/source-affiliation-resolution_77bbfeaa.plan.md`，也不要直接覆盖 `data/output/2025-2026三大密码会_美国机构.csv`。

## 当前完成状态

已经实现的文件：

1. `scripts/resolve_affiliations_from_sources.py`
   主复核脚本，负责读取复核队列、生成候选来源、查询 ePrint/DBLP、下载 PDF、抽取前两页文本、解析作者机构、输出复核结果。

2. `scripts/extract_pdf_frontmatter.py`
   辅助脚本，用于从 PDF 或 HTML 文件抽取前置信息文本。

3. `scripts/merge_resolved_us_rows.py`
   历史 compatibility-only 辅助脚本，用于把复核得到的历史美国机构兼容作者行合并到 enriched 输出。

4. `tests/test_affiliation_resolution.py`
   独立复核流程测试。

已经解决的问题：

1. `python3 scripts/resolve_affiliations_from_sources.py` 直接运行时导入失败的问题已修复。

2. ePrint 对弱请求头返回 403 的问题已定位并修复。脚本现在使用浏览器式请求头。

3. `pypdf` 和 `pdfplumber` 对部分 ePrint PDF 抽不到文本的问题已定位。脚本现在优先使用系统 `pdftotext` 抽取前两页文本。

4. 已证明真实来源链路可以跑通。样本 `EUROCRYPT_2026_13` 能从 ePrint 下载 PDF，抽取文本，并基于“来源确认标题和作者，IACR JSON 只有一个机构”规则生成 2 条可接受的历史兼容作者行。

样本结果位置：

1. `data/resolution/debug_known/resolved_author_affiliations.csv`

该文件目前包含：

1. `Alexandra Henzinger`, `MIT`
2. `Seyoon Ragavan`, `MIT`

来源是 `https://eprint.iacr.org/2025/2008`。

## 当前不可信或半成品状态

顶层 `data/resolution/` 当前不是完整全量结果。

原因是全量命令曾经被中断。当前状态如下：

1. `data/interim/affiliation_resolution_queue.csv`
   全量输入，可信。共有 `311` 条复核任务。

2. `data/resolution/resolution_report.json`
   不可信。它仍是一次 10 条样本运行留下的报告，显示 `tasks = 10`。

3. `data/resolution/source_candidates.csv`
   不可信。当前只有 `46` 行，是样本运行残留。

4. `data/resolution/resolved_author_affiliations.csv`
   不可信。当前顶层文件为 0 行。

5. `data/resolution/unresolved_after_source_lookup.csv`
   不可信。当前只有 10 行，是样本运行残留。

6. `data/resolution/downloaded_pdfs/`
   半成品缓存。中断前已经下载了约 `82` 个 PDF，可复用。

7. `data/resolution/extracted_text/`
   半成品缓存。中断前已经抽取了约 `84` 个文本文件，可复用。

下一位 LLM 不应该直接相信顶层 `resolution_report.json`，需要先重新生成全量结果。

## 关键技术思路

当前最可行的自动接受规则不是“必须解析出 PDF 中每个上标脚注”，而是分两层：

1. 若来源页面或 PDF 文本严格确认标题和作者列表，并且 IACR JSON 中该论文只有一个 affiliation，则可以把这个唯一 affiliation 映射给所有作者。

2. 若 IACR JSON 中有多个 affiliation，则需要从 PDF 首页或正式页面中解析明确的作者机构对应关系。解析失败时继续留在 unresolved 队列。

这样可以先自动消化大量单机构 mismatch，同时避免多机构论文错配。

相关函数：

1. `parse_confirmed_single_affiliation(...)`
   处理“来源确认标题作者，加 IACR 单一机构”的情况。

2. `parse_frontmatter_text(...)`
   处理文本中形如 `Author: Institution` 的显式映射。

3. `accept_resolved_mapping(...)`
   严格接受门槛。需要 `title_match = true`、`authors_match = true`、`confidence >= 0.9`。这份旧文档中的自动接受示例额外要求机构判定为美国机构，是因为它服务于历史兼容切片。

4. `source_to_pdf_url(...)`
   把 `https://eprint.iacr.org/YYYY/NNNN` 转成 PDF 链接。

5. `extract_frontmatter_from_pdf(...)`
   当前优先调用 `pdftotext`。

## 建议下一步

第一步，先不要跑 311 条全量。先跑一个可控子集，确认非零结果稳定。

建议新建一个包含 20 到 30 条的 queue。若继续验证旧兼容切片，可优先选择 `affiliations_count = 1` 且 affiliation 明显是美国机构的行；若迁回当前主链路，则应优先选择单机构且国家归属清晰的行。

可用命令：

```bash
python3 - <<'PY'
import csv
from pathlib import Path

src = Path('data/interim/affiliation_resolution_queue.csv')
out = Path('data/resolution/single_affiliation_us_like_queue.csv')
keywords = [
    'MIT', 'Stanford', 'UC ', 'University of California', 'UT Austin',
    'Johns Hopkins', 'Purdue', 'Rice', 'Yale', 'Cornell',
    'Carnegie Mellon', 'Princeton', 'Columbia', 'NYU', 'NIST'
]

rows = []
for row in csv.DictReader(src.open(encoding='utf-8')):
    aff = row['affiliations']
    if int(row['affiliations_count']) == 1 and any(k.lower() in aff.lower() for k in keywords):
        rows.append(row)
    if len(rows) >= 30:
        break

with out.open('w', encoding='utf-8', newline='') as handle:
    writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

print(out, len(rows))
PY
```

然后运行：

```bash
python3 scripts/resolve_affiliations_from_sources.py \
  --queue data/resolution/single_affiliation_us_like_queue.csv \
  --output-dir data/resolution/single_affiliation_trial \
  --query-dblp
```

预期结果：

1. `resolved_us_rows` 应该大于 0。
2. `single_affiliation_trial/downloaded_pdfs/` 应该出现 PDF。
3. `single_affiliation_trial/extracted_text/` 应该出现非空 txt。
4. `single_affiliation_trial/resolved_author_affiliations.csv` 应该有可接受行。

第二步，修复全量运行过慢的问题。

当前全量 `--query-dblp` 会逐条联网，并且可能被慢请求拖住。建议下一位 LLM 增加以下能力：

1. 增加 `--start` 和 `--limit` 参数，按批次跑。

2. 每处理一条就把当前结果追加或周期性 checkpoint 到磁盘，而不是最后一次性写出。

3. ePrint 搜索结果和 PDF 下载结果建立缓存。已有缓存时不要重新联网。

4. 对 `download_binary` 和 `fetch_text` 增加更短超时和失败原因记录。

5. 对同一个标题的 ePrint 搜索页保存到 `data/resolution/source_pages/`，便于重跑。

第三步，全量批处理。

建议分批运行，例如每批 25 条：

```bash
python3 scripts/resolve_affiliations_from_sources.py \
  --queue data/interim/affiliation_resolution_queue.csv \
  --output-dir data/resolution_batch_000 \
  --query-dblp \
  --start 0 \
  --limit 25
```

当前脚本还没有 `--start` 参数，需要先补。

第四步，合并批次结果。

等批次跑完后，再合并所有批次的：

1. `resolved_author_affiliations.csv`
2. `merge_candidates_us_rows.csv`
3. `unresolved_after_source_lookup.csv`
4. `source_candidates.csv`
5. `parsed_affiliations.jsonl`

最后再运行：

```bash
python3 scripts/merge_resolved_us_rows.py \
  --base data/output/2025-2026三大密码会_美国机构.csv \
  --candidates data/resolution/merge_candidates_us_rows.csv \
  --output-csv data/output/2025-2026三大密码会_美国机构_enriched.csv \
  --output-xlsx data/output/2025-2026三大密码会_美国机构_enriched.xlsx
```

上面的命令仅适用于历史美国机构兼容 enriched 流程。当前正式主链路若要回写复核结果，应优先面向泛化主输出而不是继续扩展 `*_美国机构.*` 文件族。

## 需要特别注意的坑

1. 不要再把“搜索入口”当成真实来源。
   `https://eprint.iacr.org/search?q=...` 只是搜索页，只有解析到 `https://eprint.iacr.org/YYYY/NNNN` 才算真实来源。

2. `best_source_score` 和自动接受的 `title_score` 不是一回事。
   接受门槛应使用目标标题和候选标题的直接相似度，不要用综合排序分数。这个问题已经修过一次。

3. PDF 下载 403 时先检查请求头。
   ePrint PDF 用完整浏览器式 headers 可以访问。

4. PDF 文本抽取优先使用 `pdftotext`。
   `pypdf` 和 `pdfplumber` 对已有样本返回过空文本。

5. 顶层 `data/resolution/` 目前混有样本运行和中断残留。
   正式全量前建议先备份或清空顶层结果文件，但可以保留 `downloaded_pdfs/` 和 `extracted_text/` 作为缓存。

6. 多机构论文不要自动套用单机构规则。
   只有 `affiliations_count = 1` 时，才可以用“来源确认标题作者，加 IACR 唯一机构”的自动接受规则。

7. 不要覆盖原始主表。
   只生成 enriched 文件。

## 当前推荐接手目标

下一位 LLM 的第一目标不是直接全量跑完，而是先让 `single_affiliation_trial` 稳定产生非零行，并确认字段和证据完整。

成功标准：

1. `resolved_us_rows > 0`
2. 每条 resolved 行都有 `source_url`
3. 每条 resolved 行都有 `evidence_text`
4. `merge_candidates_us_rows.csv` 字段为 `name`, `year`, `article_tag`, `author_order`, `inst`
5. `unresolved_after_source_lookup.csv` 保留所有没过门槛的论文

完成上述后，再补批处理和 checkpoint，全量处理 311 条。

## 验证命令

基础测试：

```bash
python3 -m unittest tests.test_affiliation_resolution tests.test_top3_us_pipeline -v
```

检查 PDF 抽取工具：

```bash
command -v pdftotext
```

检查样本结果：

```bash
python3 - <<'PY'
import csv
from pathlib import Path

path = Path('data/resolution/debug_known/resolved_author_affiliations.csv')
rows = list(csv.DictReader(path.open(encoding='utf-8')))
print(len(rows))
for row in rows:
    print(row['resolution_id'], row['name'], row['inst'], row['source_url'])
PY
```
