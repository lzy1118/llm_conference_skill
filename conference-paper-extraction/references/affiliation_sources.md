# 机构来源参考

当前脚本目录只保留四大安全会 metadata 输出链路：

```bash
python3 conference-paper-extraction/scripts/build_paper_metadata_with_affiliations.py \
  --generated-data-dir generated-data
```

输入：

- `generated-data/extraction/raw/by_conference/*/papers.json`

输出：

- `generated-data/ccs_full_output/paper_metadata.csv`
- `generated-data/ieee_sp_full_output/paper_metadata.csv`
- `generated-data/ndss_full_output/paper_metadata.csv`
- `generated-data/usenix_security_full_output/paper_metadata.csv`

输出字段固定为：

```text
year,conference,title,author,author_rank,affiliations
```

## 来源优先级

1. raw `papers.json` 中已有的作者与机构字段
2. 会议官网可解析的作者机构文本
3. 已存在的本地 affiliation cache
4. 可选网络补源，仅用于机构文本，不生成 country 或 classification 字段

## 当前不再生成

- 作者机构国家长表
- country 字段
- classification_source / classification_confidence / classification_reason
- institution classification candidates
- validation report
- PDF manifest / PDF 下载报告
