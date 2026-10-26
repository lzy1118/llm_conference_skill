# 项目框架图

本文档基于当前仓库主线代码整理，重点反映“统一抽取 -> 标准化 -> 分析 -> 报告/可视化 -> 自动化治理”的实际结构。

## 1. 总体框架图

```mermaid
flowchart LR
    A["外部数据源<br/>IACR JSON / DBLP XML / 官网 / IEEE / OpenAlex / PDF"] --> B["conference-paper-extraction<br/>统一论文与作者机构抽取"]
    B --> B1["后端 1: iacr_top3_backend<br/>密码三大会议"]
    B --> B2["后端 2: security_real_backend<br/>安全四大会议"]
    B1 --> C["generated-data/extraction<br/>raw / interim / output / pdfs / manifest"]
    B2 --> C

    C --> D["clean_extraction_noise.py<br/>抽取层清洗"]
    D --> E["conference-dataset-normalization<br/>normalize_dataset.py"]
    E --> F["generated-data/normalized<br/>author_affiliation_facts.csv<br/>paper_facts.csv<br/>institution_dim.csv"]

    F --> G["conference-analysis-automation<br/>run_analysis_pipeline.py"]
    G --> H1["国家统计<br/>conference-country-statistics"]
    G --> H2["机构统计<br/>conference-institution-statistics"]
    G --> H3["作者统计<br/>conference-author-statistics"]
    G --> H4["趋势分析<br/>conference-trend-analysis"]
    G --> H5["合作分析<br/>conference-collaboration-analysis"]
    G --> H6["质量审计<br/>conference-quality-audit"]

    H1 --> I["generated-data/analysis"]
    H2 --> I
    H3 --> I
    H4 --> I
    H5 --> I
    H6 --> I

    I --> J1["conference-report-generation<br/>Markdown/JSON 报告"]
    I --> J2["conference-visualization<br/>SVG 图表"]
    J1 --> K["generated-data/reports"]
    J2 --> L["generated-data/visualizations"]

    F --> M["conference-author-role-extraction<br/>作者角色补充事实表"]
    M --> N["generated-data/author-roles"]

    I --> O["conference-analysis-automation 辅助脚本<br/>版本整理 / 覆盖率 / 回填任务 / 产物校验"]
    N --> O
    C --> O
```

## 2. 模块分层图

```mermaid
flowchart TB
    subgraph S1["数据采集层"]
        A1["conference-paper-extraction"]
        A2["conference-cfp-extraction"]
    end

    subgraph S2["数据标准化层"]
        B1["conference-dataset-normalization"]
        B2["统一机构别名与机构注册表<br/>institution_aliases.csv / institution_registry.csv"]
    end

    subgraph S3["分析计算层"]
        C1["conference-country-statistics"]
        C2["conference-institution-statistics"]
        C3["conference-author-statistics"]
        C4["conference-trend-analysis"]
        C5["conference-collaboration-analysis"]
        C6["conference-benchmark-comparison"]
        C7["conference-quality-audit"]
    end

    subgraph S4["结果表达层"]
        D1["conference-report-generation"]
        D2["conference-visualization"]
    end

    subgraph S5["自动化治理层"]
        E1["conference-analysis-automation"]
        E2["coverage / backfill / artifact verify / version organize"]
    end

    subgraph S6["扩展事实层"]
        F1["conference-author-role-extraction"]
    end

    A1 --> B1
    A2 --> E1
    B2 --> B1
    B1 --> C1
    B1 --> C2
    B1 --> C3
    B1 --> C4
    B1 --> C5
    B1 --> C6
    B1 --> C7
    B1 --> F1
    C1 --> D1
    C2 --> D1
    C3 --> D1
    C4 --> D1
    C5 --> D1
    C7 --> D1
    C1 --> D2
    C2 --> D2
    C3 --> D2
    C4 --> D2
    C5 --> D2
    A1 --> E1
    B1 --> E1
    C1 --> E1
    C2 --> E1
    C3 --> E1
    C4 --> E1
    C5 --> E1
    C7 --> E1
    F1 --> E1
```

## 3. 当前仓库的核心主线

当前最明确、耦合最稳定的主线是：

1. `conference-paper-extraction/scripts/run_unified_pipeline.py`
2. `conference-paper-extraction/scripts/clean_extraction_noise.py`
3. `conference-dataset-normalization/scripts/normalize_dataset.py`
4. `conference-analysis-automation/scripts/run_analysis_pipeline.py`
5. `conference-report-generation/scripts/generate_report.py`
6. `conference-visualization/scripts/generate_visualizations.py`

对应统一产物出口：

- `generated-data/extraction/`
- `generated-data/normalized/`
- `generated-data/analysis/`
- `generated-data/reports/`
- `generated-data/visualizations/`

## 4. 目录视角简图

```text
llm_conference_skill/
├── conference-paper-extraction/        统一抽取主入口
├── conference-dataset-normalization/   标准化
├── conference-analysis-automation/     主流程编排与治理
├── conference-country-statistics/      国家统计
├── conference-institution-statistics/  机构统计
├── conference-author-statistics/       作者统计
├── conference-trend-analysis/          趋势分析
├── conference-collaboration-analysis/  合作分析
├── conference-quality-audit/           质量审计
├── conference-report-generation/       报告生成
├── conference-visualization/           可视化生成
├── conference-author-role-extraction/  作者角色补充
├── conference-cfp-extraction/          CFP 信息抽取
├── conference-benchmark-comparison/    横向对比分析
└── generated-data/                     统一结果目录
```

## 5. 一句话理解

这个项目本质上是一个围绕“顶会论文作者-机构-国家事实表”构建的数据工程仓库：上游负责多源抽取，中游负责规范化建模，下游负责统计分析、质量审计、报告生成与可视化输出，而 `conference-analysis-automation` 充当总调度与治理中枢。
