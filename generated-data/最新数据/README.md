# 最新数据（七大会统一入口）

本目录是当前已核实数据的统一入口，核实日期为 **2026-08-01**。

## 当前完整批次

- 数据年份：**2020–2025**
- 三大密码会：`ASIACRYPT`、`CRYPTO`、`EUROCRYPT`
- 四大安全会：`CCS`、`IEEE_S&P`、`NDSS`、`USENIX_SECURITY`
- 统一层级：`会议类别/会议/年份/paper_metadata.csv`
- `generated-data/latest` 是本目录的英文别名。

这里的“最新”指仓库中七个会议均已齐备、可统一比较的最新完整批次。截至核实日，仓库内没有 2026 年论文元数据 CSV，因此没有把不完整的 2026 年数据混入该入口。

## 数据来源

- 三大密码会链接到 `outputs/crypto_2020_2025_author_affiliations/by_conference_year/`。
- 四大安全会链接到 `generated-data/full_output/<conference>/<year>/author_metadata_dataset_<year>/paper_metadata.csv`。
- 三大密码会的跨会议合并 CSV 和 XLSX 位于 `三大密码会/全部年份/`。

本目录中的数据文件均为符号链接，不产生重复副本。源数据更新后，文件内容会同步更新；若增加年份或会议，请在仓库根目录运行：

```bash
sh scripts/refresh_latest_data_links.sh
```

## 口径说明

每行表示一条作者—机构归属记录，同一篇论文通常对应多行。论文数应按 `paper_id` 去重统计，不能直接使用 CSV 行数。
