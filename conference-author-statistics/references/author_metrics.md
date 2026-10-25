# 作者指标参考

## 身份归并建议

始终优先使用最保守、最稳定的作者身份 key。

推荐顺序：

1. 使用标准化阶段生成的 `author_key`
2. 使用大小写标准化后的完整显示名
3. 仅在必要且已明确说明时，使用“姓 + 名首字母”

## 默认计数规则

### 每位作者的论文数

统计去重后的 `(author_key, paper_key)` 对。多机构事实行不会增加论文签名中的作者数；
跨来源论文签名按作者顺序和稳定 `author_key` 去重，缺少 key 时才回退到紧凑显示名。
不同的非空 `author_key` 不因显示名相同而自动合并。

### 每位作者参与的会议数

统计去重后的 `(author_key, conference)` 对。

### 活跃年份数

统计去重后的 `(author_key, year)` 对。

### 一作论文数

统计 `author_order == 0` 时的 `(author_key, paper_key)` 去重数量。

### 共著边

对每篇论文，生成其中不同作者 key 的无序两两组合。

`coauthor_edges.csv` 推荐列：

- `author_key_1`
- `author_name_1`
- `author_key_2`
- `author_name_2`
- `shared_papers`
- `conference_count`
- `year_first`
- `year_last`

## 报告检查清单

- 分析范围与过滤条件
- 作者身份归并假设
- 按论文数排序的头部作者
- 头部一作作者
- 跨年份或跨会议重复出现的作者
- 已知姓名标准化歧义
