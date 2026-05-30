# Remove Legacy US Boolean Cleanup - 2026-05-29

## 目标

彻底移除旧美国布尔字段及其派生旧口径，不再在抽取、标准化、统计、自动化、文档或当前生成产物中保留美国布尔标记。

## 本轮修改

- 删除抽取层美国布尔分类字段。
- 删除旧美国布尔输出列。
- 删除美国行过滤与字段剥离等过渡逻辑。
- 删除旧的美国分类辅助脚本。
- 删除分析自动化和机构统计中的 `--us-only` 参数。
- 将标准化层国家推断函数改为只接收机构文本。
- 删除 coverage ledger 对旧美国作者行统计和旧美国子集口径的识别逻辑。
- 删除含旧字段的旧生成产物，避免旧 schema 继续混入当前结果。
- 更新 README、WORKFLOW、各 skill 文档和 schema 文档，统一写成只使用 `country`。

## 验证

执行语法检查：

```bash
python3 -m py_compile conference-paper-extraction/scripts/classification_common.py conference-paper-extraction/scripts/iacr_top3_backend.py conference-paper-extraction/scripts/security_real_backend.py conference-dataset-normalization/scripts/analytics_common.py conference-dataset-normalization/scripts/normalize_dataset.py conference-analysis-automation/scripts/build_coverage_ledger.py conference-analysis-automation/scripts/run_analysis_pipeline.py conference-institution-statistics/scripts/institution_statistics.py
```

结果：通过，无输出。

执行 coverage ledger 重建：

```bash
python3 conference-analysis-automation/scripts/build_coverage_ledger.py --output-dir generated-data/coverage --cfp-dir generated-data/cfp/output --author-roles-dir generated-data/author-roles --expected-counts generated-data/coverage/expected_paper_counts_template.csv
```

结果：通过，无输出。

执行全仓库残留扫描：

```bash
/usr/bin/grep -RIl -E '<legacy-us-boolean-patterns>' .
```

结果：无输出，说明当前工作区文本中没有这些残留标记。

## 注意

曾尝试给 coverage ledger 传入 `--extraction-dir`，但当前脚本不支持该参数；已改用脚本现有参数重跑成功。

## 后续

- 若需要恢复被删除的旧生成结果，应使用当前无旧美国布尔字段的脚本重新运行 pipeline。
- 后续消融实验应比较 `country` 单字段契约与旧双字段契约在错误率和维护成本上的差异，但旧双字段不再进入主线代码。
