# 比较契约

## 目标

把多个已有排行榜型 CSV 输出拼接成一张并排基准比较表。

## 支持输入

- `country_summary.csv`
- `institution_summary.csv`
- `author_summary.csv`

## 默认指标行为

- 默认优先使用 `papers` 作为对比指标。
- 如果文件中没有 `papers`，应由调用方提供兼容文件，或显式调整流程设计。

## 输出列建议

- `entity`
- 每个对比 label 各一列
- `best_label`
- `max_value`
- `min_value`
- `spread`

## 失败处理

- 如果 `--label` 与 `--summary` 不成对，应直接失败。
- 如果不存在公共 `papers` 指标，应直接失败。
