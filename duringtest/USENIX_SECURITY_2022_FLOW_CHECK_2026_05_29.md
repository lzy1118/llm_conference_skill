# USENIX Security 2022 Flow Check - 2026-05-29

## 目标

验证当前移除旧美国布尔字段后的流程，是否还能正常完成 USENIX Security 2022 数据收集、标准化和下游统计。

## 新增参考数据

用户补充了两个机构参考文件，现已收口到 `conference-dataset-normalization` skill 内部：

- `conference-dataset-normalization/references/institution_aliases.csv`
- `conference-dataset-normalization/references/institution_registry.csv`

初步检查：

- `institution_aliases.csv` 字段为 `alias,institution_id`，可用于把机构别名映射到稳定机构 ID。
- `institution_registry.csv` 字段为 `institution_id,canonical_name,country,region,type`，可用于补充 canonical name、国家、地区和机构类型。
- 当前记录所述检查发生在接入前；后续这些文件已经被接入 `conference-dataset-normalization` 的机构标准化阶段。

## 执行命令

先验证统一入口路由：

```bash
python3 conference-paper-extraction/scripts/run_unified_pipeline.py --conference usenix_security_2022 --output-dir generated-data/extraction --dry-run
```

结果：路由到 `security_real` backend，命令计划正确。

执行真实抽取并从 DBLP 拉取 raw metadata：

```bash
python3 conference-paper-extraction/scripts/run_unified_pipeline.py --conference usenix_security_2022 --output-dir generated-data/extraction --fetch
```

结果：成功。

随后补跑完整采集命令，显式启用 venue affiliation 获取参数：

```bash
python3 conference-paper-extraction/scripts/run_unified_pipeline.py --conference usenix_security_2022 --output-dir generated-data/extraction --fetch --fetch-affiliations
```

结果：成功。由于本地已有 affiliation cache，本次指标与前一次一致；在全新目录或全新机器上，正式采集建议使用这个完整命令。

关键指标：

- papers_count: 256
- papers_with_author_rows: 256
- expanded_author_rows: 1261
- classified_author_rows: 1245
- resolved_country_rows: 1245
- unresolved_country_rows: 16
- no_affiliation_issues: 0

执行标准化：

```bash
python3 conference-dataset-normalization/scripts/normalize_dataset.py generated-data/extraction/output/usenix_security_2022_author_affiliations_audit.csv --output-dir generated-data/usenix-security-2022-check
```

结果：成功。

标准化指标：

- input_rows: 1245
- normalized_rows: 1245
- paper_count: 256
- institution_count: 332
- duplicate_row_keys_skipped: 0
- rows_missing_name: 0
- rows_missing_inst: 0
- rows_with_unknown_country: 0

执行下游统计：

```bash
python3 conference-country-statistics/scripts/country_statistics.py --input generated-data/usenix-security-2022-check/normalized/author_affiliation_facts.csv --output-dir generated-data/usenix-security-2022-check/analysis/countries --conference USENIX_SECURITY --year 2022
python3 conference-institution-statistics/scripts/institution_statistics.py --input generated-data/usenix-security-2022-check/normalized/author_affiliation_facts.csv --output-dir generated-data/usenix-security-2022-check/analysis/institutions --conference USENIX_SECURITY --year 2022
python3 conference-author-statistics/scripts/author_statistics.py --input generated-data/usenix-security-2022-check/normalized/author_affiliation_facts.csv --output-dir generated-data/usenix-security-2022-check/analysis/authors --conference USENIX_SECURITY --year 2022
```

结果：全部成功。

## 产物

抽取产物：

- `generated-data/extraction/raw/usenix_security_2022_papers.json`
- `generated-data/extraction/interim/usenix_security_2022_author_affiliations_expanded.csv`
- `generated-data/extraction/interim/usenix_security_2022_institution_classification_candidates.csv`
- `generated-data/extraction/output/usenix_security_2022_author_affiliations.csv`
- `generated-data/extraction/output/usenix_security_2022_author_affiliations_audit.csv`
- `generated-data/extraction/output/usenix_security_2022_validation_report.json`

标准化产物：

- `generated-data/usenix-security-2022-check/normalized/author_affiliation_facts.csv`
- `generated-data/usenix-security-2022-check/normalized/paper_facts.csv`
- `generated-data/usenix-security-2022-check/normalized/institution_dim.csv`
- `generated-data/usenix-security-2022-check/normalized/normalization_report.json`

统计产物：

- `generated-data/usenix-security-2022-check/analysis/countries/country/`
- `generated-data/usenix-security-2022-check/analysis/institutions/institutions/`
- `generated-data/usenix-security-2022-check/analysis/authors/authors/`

## 结论

USENIX Security 2022 的当前流程可以正常执行，从原始论文元数据获取到标准化事实表，再到国家、机构、作者统计均通过。

## 后续建议

- 继续完善 `conference-dataset-normalization/references/` 下的 alias / registry，生成更稳定的 `institution_key` 和 canonical display name。
- 对 `unresolved_country_rows` 和低置信机构候选做人工复核，必要时补充 alias 或 registry。
- 如果要做正式报告，建议使用独立输出目录，避免与历史生成产物混放。
