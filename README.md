# 美国机构数据采集项目

采集密码学和信息安全领域顶会中美国机构作者发表情况。

## 子项目

| 子项目 | 会议 | 结果 |
|--------|------|------|
| `Top3-data/` | Asiacrypt 2025, Crypto 2025, Eurocrypt 2026 | 182 行 |
| `Security-data/` | USENIX Security 2025, NDSS 2025, IEEE S&P 2025, CCS 2025 | 1497 行 |

详细说明见各子项目 README。

## 统计口径

按"美国机构"判定：只要作者 affiliation 为美国机构即计入，不按国籍推断。

## 通用依赖

```bash
uv pip install openpyxl pypdf
```
