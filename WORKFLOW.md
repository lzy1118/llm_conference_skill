# 顶会作者机构国家数据采集工作流

## 概述

从学术会议论文中采集作者、机构与国家归属信息，输出可复用的“作者-机构-国家”长表，并按论文级参与国语义支撑国家统计。

## 适用场景

- 密码学会议（IACR 系列：Asiacrypt, Crypto, Eurocrypt）
- 安全顶会（USENIX Security, NDSS, IEEE S&P, ACM CCS）
- 其他有结构化论文数据的学术会议

## 工作流总览

```
1. 数据源调研 → 2. 论文数据抓取 → 3. Affiliation 抓取 → 4. 国家与机构归属分类 → 5. 输出生成 → 6. 复核完善
```

## 详细步骤

### 第一步：数据源调研

确定论文数据和 affiliation 数据来源：

| 数据类型 | 推荐来源 | 备选来源 |
|---------|---------|---------|
| 论文列表 | DBLP XML | 会议官网、ACM/IEEE DL |
| Author affiliations | 会议官网 meta 标签 | OpenAlex、Semantic Scholar、PDF |

**各会议数据源：**

| 会议 | 论文来源 | Affiliation 来源 |
|------|---------|-----------------|
| IACR 系列 | IACR JSON API | IACR JSON 自带 |
| USENIX Security | DBLP XML | 官网 `citation_author_institution` meta |
| NDSS | DBLP XML | 官网 `Author (Institution)` 格式 |
| IEEE S&P | DBLP XML | IEEE Xplore JSON metadata |
| ACM CCS | DBLP XML | OpenAlex API（ACM DL 封禁） |

### 第二步：论文数据抓取

**DBLP XML 格式：**
```
https://dblp.org/db/conf/{venue_key}/{venue_key}{year}.xml
```

**IACR JSON 格式：**
```
https://{conference}.iacr.org/{year}/json/papers.json
```

**抓取脚本：**
```python
# DBLP XML 解析
import xml.etree.ElementTree as ET
root = ET.fromstring(xml_data)
for article in root.findall('.//inproceedings'):
    title = article.find('title').text
    authors = [au.text for au in article.findall('.//author')]
    url = article.find('ee').text if article.find('ee') is not None else ''
```

**输出：** `generated-data/extraction/raw/{conference}_{year}_papers.json`

### 第三步：Affiliation 抓取

**按会议类型选择策略：**

#### USENIX Security
```python
# 从官网 meta 标签获取
html = fetch_text(paper_url)
authors = re.findall(r'<meta\s+name="citation_author"\s+content="([^"]+)"', html)
institutions = re.findall(r'<meta\s+name="citation_author_institution"\s+content="([^"]+)"', html)
```

#### NDSS
```python
# 从官网解析 "Author (Institution)" 格式
h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', text, re.DOTALL)
after_h1 = text[h1_match.end():h1_match.end()+3000]
pattern = r'([A-Z][a-zA-Z\-\']+(?:\s+[A-Z][a-zA-Z\-\']+)+)\s*\(([^)]+)\)'
```

#### IEEE S&P
```python
# 从 IEEE Xplore JSON metadata 获取
match = re.search(r'xplGlobal\.document\.metadata\s*=\s*(\{.*?\});', html, re.DOTALL)
data = json.loads(match.group(1))
for author in data.get('authors', []):
    name = author.get('name', '')
    affiliations = author.get('affiliation', [])
```

#### ACM CCS
```python
# 从 OpenAlex API 获取（ACM DL 封禁）
result = subprocess.run(['curl', '-sL', f'https://api.openalex.org/works/doi:{doi}'], ...)
for authorship in data.get('authorships', []):
    name = authorship.get('author', {}).get('display_name', '')
    institutions = [i.get('display_name', '') for i in authorship.get('institutions', [])]
```

#### IACR 系列
```python
# 直接从 JSON 获取
papers = json_data.get('acceptedPapers', [])
for paper in papers:
    authors = paper.get('authors', [])
    affiliations = paper.get('affiliations', [])
```

**缓存机制：**
```python
cache_file = cache_dir / f"{paper_id.replace('/', '_')}_affiliations.json"
if cache_file.exists():
    return json.loads(cache_file.read_text())
# ... 抓取逻辑 ...
cache_file.write_text(json.dumps(affiliations, ensure_ascii=False, indent=2))
```

**限流：** 每次请求间隔 0.3-1.5 秒

### 第四步：国家与机构归属分类

**分类规则（三级）：**

```python
# 第一级：精确匹配
EXACT_ALIASES = {'mit', 'nist', 'sri', 'uc san diego', 'uc berkeley', ...}

# 第二级：高置信规则匹配
COUNTRY_PATTERN_RULES = [
    ('United States', [r'\bmassachusetts institute of technology\b', r'\bcarnegie mellon university\b', ...]),
    ('China', [r'\btsinghua\b', r'\bpeking\b', ...]),
    ('Germany', [r'\bcispa\b', r'\brwth aachen university\b', ...]),
]

# Override 文件（人工覆盖）
# generated-data/extraction/reference/institution_country_overrides.csv
# inst,country,reason
# Example Lab,United States,manual_review
```

**分类函数：**
```python
def classify_affiliation(affiliation, overrides=None):
    lower = affiliation.casefold()
    if overrides and lower in overrides:
        return overrides[lower]
    if lower in EXACT_ALIASES:
        return {'country': 'United States', 'source': 'rule', 'confidence': 1.0}
    country = detect_country(lower)
    if country:
        return {
            'country': country,
            'source': 'rule',
            'confidence': 0.95,
        }
    return {'country': 'Unknown', 'source': 'unresolved', 'confidence': 0.0}
```

三大密码会国家统计默认应按论文级参与国语义处理。中国口径仅包括中国大陆机构；美国口径与其他国家口径一致，均按论文参与机构信号统计。除 2025 年验证案例外，其他年份若出现作者身份或基础事实冲突，应优先以 IACR raw / DBLP 为准。

### 第五步：输出生成

**主表字段（正式主契约）：**
- `name`: 作者姓名
- `year`: 年份
- `article_tag`: `{会议简称}-{论文标题}`
- `author_order`: 作者顺序（0-indexed）
- `inst`: 机构名称
- `country`: 国家归属

**输出格式：**
```python
# Excel
from openpyxl import Workbook
wb = Workbook()
ws = wb.active
ws.title = '英文版'
ws.append(['name', 'year', 'article_tag', 'author_order', 'inst', 'country'])

# CSV
fields = ['name', 'year', 'article_tag', 'author_order', 'inst', 'country']
```

当前主流程不再默认导出 `*_us_institutions.*`；若确有历史对照需要，应通过独立旧材料或额外脚本处理，而不应把它视为正式主输出。

**审计表（额外字段）：**
- `conference`: 会议名称
- `paper_id`: 论文 ID
- `title`: 论文标题
- `classification_source`: 分类来源（rule/override/source_pdf）
- `classification_confidence`: 置信度
- `classification_reason`: 分类原因

### 第六步：复核完善

**复核队列处理：**

1. **作者数与机构数不匹配**（密码会常见）
   - 从 PDF frontmatter 解析 author-affiliation 映射
   - 解析模式：
     - 编号模式：`Author1^1, Author2^2` + `1. Institution1, 2. Institution2`
     - 内联模式：`Author (Institution)`
     - 连续模式：作者后紧跟机构

2. **无 affiliation 数据**（安全顶会常见）
   - 尝试多个数据源：官网 → OpenAlex → Semantic Scholar → DBLP
   - 仍无数据则保留人工复核

**名称模糊匹配：**
```python
# 支持缩写匹配（Kostas/Konstantinos）
key_parts = key.split()
aa_parts = aa_name.split()
if (len(key_parts) >= 2 and len(aa_parts) >= 2 and
    key_parts[-1] == aa_parts[-1] and
    key_parts[0][0] == aa_parts[0][0]):
    # 匹配成功
```

## 目录结构

```text
conference-paper-extraction/
  scripts/           统一入口与 backend
  references/        采集规则说明

generated-data/
  extraction/
    raw/             原始数据快照
    interim/         中间结果
    output/          最终输出
    resolution/      复核缓存
  normalized/        标准化事实表与维表
  analysis/          下游分析结果

data/
  reference/         机构主 reference
```

## 关键注意事项

1. **请求限流**：所有 API 请求加延迟（0.3-1.5 秒），避免被封
2. **缓存机制**：所有抓取结果缓存到本地，重跑时自动复用
3. **断点续跑**：支持 `--start`/`--limit` 分批处理，`--checkpoint-every` 定期保存
4. **不覆盖原数据**：enriched 输出单独生成，不覆盖基础输出
5. **审计追溯**：保留所有中间结果和判定来源

## 常用命令

```bash
# 安装依赖
uv pip install openpyxl pypdf

# 运行统一抽取 pipeline
python3 conference-paper-extraction/scripts/run_unified_pipeline.py --group all --output-dir generated-data/extraction

# 抽取指定会议并抓取原始论文元数据
python3 conference-paper-extraction/scripts/run_unified_pipeline.py --conference crypto_2022 --output-dir generated-data/extraction --fetch

# 安全会额外抓取 affiliations
python3 conference-paper-extraction/scripts/run_unified_pipeline.py --conference usenix_security_2022 --output-dir generated-data/extraction --fetch --fetch-affiliations

# 运行复核（密码会）
python3 conference-paper-extraction/scripts/run_unified_pipeline.py \
  --conference crypto_2022 \
  --output-dir generated-data/extraction \
  --resolve-mismatches

# 如需更深入的补源阶段，可使用内部 resolution 产物
python3 conference-paper-extraction/scripts/resolve_affiliations_from_sources.py \
  --queue generated-data/extraction/interim/affiliation_resolution_queue.csv \
  --output-dir generated-data/extraction/resolution --query-dblp --checkpoint-every 50

# 合并 enriched 输出（密码会）
python3 conference-paper-extraction/scripts/merge_resolved_rows.py

# 运行测试
python3 -m unittest discover -s tests -v
```
