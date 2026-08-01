from __future__ import annotations

import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
NORMALIZATION_SCRIPTS = ROOT / "conference-dataset-normalization" / "scripts"
if str(NORMALIZATION_SCRIPTS) not in sys.path:
    sys.path.append(str(NORMALIZATION_SCRIPTS))

from normalize_dataset import build_normalized_tables, collect_input_rows  # noqa: E402


EXTRACTION_BY_CONFERENCE = ROOT / "generated-data" / "extraction" / "output" / "by_conference"
OUTPUT_ROOT = ROOT / "generated-data" / "ablation_experiments"
REPORT_ROOT = ROOT / "generated-data" / "reports" / "ablation_experiments"
PAPER_TABLES_DIR = ROOT / "generated-data" / "paper_tables"


@dataclass(frozen=True)
class VariantSpec:
    variant_id: str
    variant_label: str
    description: str
    apply_ordered_bundle_heuristic: bool
    apply_repairs: bool
    apply_split: bool
    apply_reference_resolution: bool
    apply_parent_collapse: bool
    apply_country_inference: bool


VARIANTS = [
    VariantSpec(
        variant_id="M0",
        variant_label="原始直接统计",
        description="关闭多机构拆分、规则映射、父机构归并与复杂修复，直接保留原始 affiliation 字符串。",
        apply_ordered_bundle_heuristic=False,
        apply_repairs=False,
        apply_split=False,
        apply_reference_resolution=False,
        apply_parent_collapse=False,
        apply_country_inference=False,
    ),
    VariantSpec(
        variant_id="M1",
        variant_label="基础文本清洗",
        description="仅启用文本规整与多机构拆分，不启用复杂修复、词典映射和父机构归并。",
        apply_ordered_bundle_heuristic=False,
        apply_repairs=False,
        apply_split=True,
        apply_reference_resolution=False,
        apply_parent_collapse=False,
        apply_country_inference=True,
    ),
    VariantSpec(
        variant_id="M2",
        variant_label="规则/词典映射",
        description="在 M1 基础上加入机构别名字典和国家规则映射，但关闭复杂多机构修复与父机构归并。",
        apply_ordered_bundle_heuristic=False,
        apply_repairs=False,
        apply_split=True,
        apply_reference_resolution=True,
        apply_parent_collapse=False,
        apply_country_inference=True,
    ),
    VariantSpec(
        variant_id="M3",
        variant_label="复杂解析消融",
        description="在 M2 基础上加入共享 bundle 启发式和修复逻辑，但关闭父机构归并。",
        apply_ordered_bundle_heuristic=True,
        apply_repairs=True,
        apply_split=True,
        apply_reference_resolution=True,
        apply_parent_collapse=False,
        apply_country_inference=True,
    ),
    VariantSpec(
        variant_id="M4",
        variant_label="完整自动化流程",
        description="启用共享 bundle 修复、词典映射、父机构归并和国家推断，作为完整方法组。",
        apply_ordered_bundle_heuristic=True,
        apply_repairs=True,
        apply_split=True,
        apply_reference_resolution=True,
        apply_parent_collapse=True,
        apply_country_inference=True,
    ),
]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def top_entities(path: Path, field: str, limit: int) -> list[str]:
    rows = read_csv_rows(path)
    return [row[field] for row in rows[:limit] if row.get(field)]


def jaccard(left: list[str], right: list[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return 1.0
    return len(left_set & right_set) / len(left_set | right_set)


def run_command(command: list[str]) -> None:
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(command)}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )


def stable_paper_success_count(author_paper_rows: list[dict[str, object]]) -> int:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in author_paper_rows:
        grouped.setdefault(str(row["paper_key"]), []).append(row)
    success = 0
    for rows in grouped.values():
        ok = True
        for row in rows:
            if int(row["resolved_affiliation_count"]) <= 0:
                ok = False
                break
            if str(row["first_country"]) in {"", "Unknown", "Multiple"}:
                ok = False
                break
            if "Multiple" in str(row.get("all_record_countries", "")):
                ok = False
                break
            if str(row["participating_country_scope"]) == "multiple_countries":
                ok = False
                break
        if ok:
            success += 1
    return success


def raw_input_paths() -> list[Path]:
    return sorted(EXTRACTION_BY_CONFERENCE.glob("*/author_affiliations_audit.csv"))


def write_normalized_variant(variant: VariantSpec, raw_inputs: list[Path]) -> Path:
    variant_root = OUTPUT_ROOT / variant.variant_id
    normalized_dir = variant_root / "normalized"
    normalized_dir.mkdir(parents=True, exist_ok=True)

    rows, input_files = collect_input_rows(
        raw_inputs,
        apply_ordered_bundle_heuristic=variant.apply_ordered_bundle_heuristic,
        apply_repairs=variant.apply_repairs,
    )
    author_rows, author_paper_rollups, paper_facts, institution_dim, report = build_normalized_tables(
        rows,
        apply_split=variant.apply_split,
        apply_reference_resolution=variant.apply_reference_resolution,
        apply_parent_collapse=variant.apply_parent_collapse,
        apply_country_inference=variant.apply_country_inference,
    )
    report["variant_id"] = variant.variant_id
    report["variant_label"] = variant.variant_label
    report["variant_description"] = variant.description
    report["input_files"] = input_files

    from analytics_common import write_csv_rows, write_json  # noqa: E402

    write_csv_rows(
        normalized_dir / "author_affiliation_facts.csv",
        author_rows,
        [
            "row_key",
            "paper_key",
            "conference",
            "year",
            "title",
            "article_tag",
            "paper_id",
            "name",
            "author_key",
            "author_order",
            "inst",
            "institution_key",
            "institution_id",
            "canonical_institution_name",
            "country",
            "classification_source",
            "classification_confidence",
            "classification_reason",
        ],
    )
    write_csv_rows(
        normalized_dir / "author_paper_affiliation_facts.csv",
        author_paper_rollups,
        [
            "author_paper_key",
            "paper_key",
            "conference",
            "year",
            "title",
            "article_tag",
            "paper_id",
            "name",
            "author_key",
            "author_order",
            "affiliation_record_count",
            "affiliation_institution_count",
            "resolved_affiliation_count",
            "has_multi_affiliation",
            "first_inst",
            "first_institution_key",
            "first_institution_id",
            "first_canonical_institution_name",
            "first_country",
            "first_classification_source",
            "first_classification_confidence",
            "first_classification_reason",
            "participating_insts",
            "participating_institution_keys",
            "participating_institution_ids",
            "participating_canonical_institution_names",
            "participating_inst_countries",
            "participating_countries",
            "participating_country_count",
            "participating_country_scope",
            "all_record_countries",
        ],
    )
    write_csv_rows(
        normalized_dir / "paper_facts.csv",
        paper_facts,
        ["paper_key", "conference", "year", "title", "article_tag", "paper_id", "author_count"],
    )
    write_csv_rows(
        normalized_dir / "institution_dim.csv",
        institution_dim,
        ["institution_key", "inst_display", "institution_id", "canonical_name", "country", "region", "type", "source_count", "needs_review"],
    )
    write_json(normalized_dir / "normalization_report.json", report)
    return normalized_dir / "author_affiliation_facts.csv"


def run_analysis_for_variant(variant: VariantSpec, normalized_input: Path) -> Path:
    analysis_root = OUTPUT_ROOT / variant.variant_id / "analysis"
    analysis_root.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            sys.executable,
            str(ROOT / "conference-country-statistics" / "scripts" / "country_statistics.py"),
            "--input",
            str(normalized_input),
            "--output-dir",
            str(analysis_root),
        ]
    )
    run_command(
        [
            sys.executable,
            str(ROOT / "conference-institution-statistics" / "scripts" / "institution_statistics.py"),
            "--input",
            str(normalized_input),
            "--output-dir",
            str(analysis_root),
        ]
    )
    run_command(
        [
            sys.executable,
            str(ROOT / "conference-collaboration-analysis" / "scripts" / "collaboration_analysis.py"),
            "--input",
            str(normalized_input),
            "--output-dir",
            str(analysis_root),
            "--mode",
            "author",
        ]
    )
    return analysis_root


def main() -> int:
    raw_inputs = raw_input_paths()
    if not raw_inputs:
        raise FileNotFoundError(f"No author_affiliations_audit.csv files found under {EXTRACTION_BY_CONFERENCE}")

    official_total_papers = int(json.loads((PAPER_TABLES_DIR / "coverage_manifest.json").read_text(encoding="utf-8"))["overall"]["total_papers"])

    variant_outputs: dict[str, dict[str, Path]] = {}
    for variant in VARIANTS:
        normalized_input = write_normalized_variant(variant, raw_inputs)
        analysis_root = run_analysis_for_variant(variant, normalized_input)
        variant_outputs[variant.variant_id] = {
            "normalized_input": normalized_input,
            "normalized_dir": normalized_input.parent,
            "analysis_root": analysis_root,
        }

    m4_country_top10 = top_entities(variant_outputs["M4"]["analysis_root"] / "country" / "country_summary.csv", "country", 10)
    m4_inst_top20 = top_entities(
        variant_outputs["M4"]["analysis_root"] / "institutions" / "institution_summary.csv",
        "institution_name",
        20,
    )

    summary_rows: list[dict[str, object]] = []
    for variant in VARIANTS:
        normalized_dir = variant_outputs[variant.variant_id]["normalized_dir"]
        analysis_root = variant_outputs[variant.variant_id]["analysis_root"]
        report = json.loads((normalized_dir / "normalization_report.json").read_text(encoding="utf-8"))
        author_paper_rows = read_csv_rows(normalized_dir / "author_paper_affiliation_facts.csv")
        collaboration_summary = read_csv_rows(analysis_root / "collaboration" / "collaboration_summary.csv")[0]
        country_top10 = top_entities(analysis_root / "country" / "country_summary.csv", "country", 10)
        inst_top20 = top_entities(analysis_root / "institutions" / "institution_summary.csv", "institution_name", 20)

        stable_papers = stable_paper_success_count(author_paper_rows)
        normalized_papers = int(report["paper_count"])
        summary_rows.append(
            {
                "variant_id": variant.variant_id,
                "variant_label": variant.variant_label,
                "description": variant.description,
                "official_papers": official_total_papers,
                "normalized_papers": normalized_papers,
                "stable_modeled_papers": stable_papers,
                "stable_modeling_rate": round(stable_papers / official_total_papers, 6),
                "institution_entities": int(report["institution_count"]),
                "institution_compression_rate": round(1 - (int(report["institution_count"]) / max(int(report["input_rows"]), 1)), 6),
                "author_affiliation_rows": int(report["normalized_rows"]),
                "multi_affiliation_author_rows": int(report["multi_affiliation_author_rows"]),
                "unknown_country_rows": int(report["rows_with_unknown_country"]),
                "top10_country_jaccard_vs_m4": round(jaccard(country_top10, m4_country_top10), 6),
                "top20_institution_jaccard_vs_m4": round(jaccard(inst_top20, m4_inst_top20), 6),
                "author_nodes": int(collaboration_summary["node_count"]),
                "collaboration_edges": int(collaboration_summary["edge_count"]),
            }
        )

    fieldnames = list(summary_rows[0].keys())
    write_csv(REPORT_ROOT / "ablation_experiment_summary.csv", summary_rows, fieldnames)

    def pct(value: float) -> str:
        return f"{value:.2%}"

    lines = [
        "# Ablation Experiment Summary",
        "",
        "## Variant Definitions",
        "",
    ]
    for row in summary_rows:
        lines.append(f"- {row['variant_id']} {row['variant_label']}: {row['description']}")
    lines.extend(
        [
            "",
            "## Result Table",
            "",
            "| Variant | Stable Modeled Papers | Stable Modeling Rate | Institution Entities | Multi-Affiliation Author Rows | Unknown Country Rows | Top-20 Institution Jaccard | Author Nodes | Collaboration Edges |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in summary_rows:
        lines.append(
            "| "
            f"{row['variant_id']} {row['variant_label']} | "
            f"{row['stable_modeled_papers']} | "
            f"{pct(float(row['stable_modeling_rate']))} | "
            f"{row['institution_entities']} | "
            f"{row['multi_affiliation_author_rows']} | "
            f"{row['unknown_country_rows']} | "
            f"{pct(float(row['top20_institution_jaccard_vs_m4']))} | "
            f"{row['author_nodes']} | "
            f"{row['collaboration_edges']} |"
        )

    write_text(REPORT_ROOT / "ablation_experiment_report.md", "\n".join(lines) + "\n")
    print(str(REPORT_ROOT / "ablation_experiment_summary.csv"))
    print(str(REPORT_ROOT / "ablation_experiment_report.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
