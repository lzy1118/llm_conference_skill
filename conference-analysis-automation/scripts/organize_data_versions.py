from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERATED_ROOT = ROOT / "generated-data"
DEFAULT_OUTPUT_ROOT = GENERATED_ROOT / "versioned_data"
EXPERIMENT_DIR = GENERATED_ROOT / "reports" / "experiment_metrics"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Organize generated artifacts into result/data/archive/log views")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args(argv)


def is_ignored(path: Path) -> bool:
    name = path.name
    return name.startswith(".~") or name in {".DS_Store", ".gitkeep"}


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def collect_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        if not path.exists():
            continue
        if path.is_file():
            if not is_ignored(path) and path not in seen:
                files.append(path)
                seen.add(path)
            continue
        for child in sorted(path.rglob("*")):
            if child.is_file() and not is_ignored(child) and child not in seen:
                files.append(child)
                seen.add(child)
    return files


def latest_and_historical_snapshots() -> tuple[list[Path], list[Path]]:
    index_rows = read_csv_rows(EXPERIMENT_DIR / "experiment_metrics_index.csv")
    latest_by_variant: dict[str, dict[str, str]] = {}
    for row in sorted(index_rows, key=lambda item: item.get("generated_at", "")):
        latest_by_variant[row.get("variant_id", "")] = row

    latest_ids = {row.get("snapshot_id", "") for row in latest_by_variant.values()}
    latest: list[Path] = []
    historical: list[Path] = []
    for path in sorted((EXPERIMENT_DIR / "snapshots").glob("*")):
        if not path.is_file():
            continue
        if path.stem in latest_ids:
            latest.append(path)
        else:
            historical.append(path)
    return latest, historical


def copy_bucket(files: list[Path], output_root: Path, bucket: str, manifest_rows: list[dict[str, str]]) -> None:
    bucket_root = output_root / bucket
    for source in files:
        relative = source.relative_to(GENERATED_ROOT)
        destination = bucket_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        manifest_rows.append(
            {
                "bucket": bucket,
                "source": str(source),
                "copied_to": str(destination),
            }
        )


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_readme(path: Path, title: str, notes: list[str]) -> None:
    lines = [f"# {title}", ""]
    lines.extend(f"- {note}" for note in notes)
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_index(path: Path, title: str, root: Path, sections: list[tuple[str, list[Path]]]) -> None:
    lines = [f"# {title}", ""]
    for section_title, items in sections:
        lines.append(f"## {section_title}")
        lines.append("")
        real_items = [item for item in items if item.exists() and item.is_file()]
        if not real_items:
            lines.append("- None")
            lines.append("")
            continue
        for item in real_items:
            lines.append(f"- `{item.relative_to(root)}`")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def list_markdown_and_docx(path: Path) -> list[Path]:
    return sorted(path.glob("*.md")) + sorted(path.glob("*.docx"))


def build_buckets() -> dict[str, list[Path]]:
    latest_snapshots, historical_snapshots = latest_and_historical_snapshots()

    current_results = collect_files(
        [
            GENERATED_ROOT / "reports" / "README.md",
            GENERATED_ROOT / "reports" / "conference_report.json",
            GENERATED_ROOT / "reports" / "conference_report.md",
            GENERATED_ROOT / "reports" / "extraction_2020_2025_validation_status_2026_06_03.md",
            GENERATED_ROOT / "reports" / "masters_thesis_draft.docx",
            GENERATED_ROOT / "reports" / "masters_thesis_draft.md",
            GENERATED_ROOT / "reports" / "masters_thesis_draft_conference_detailed.docx",
            GENERATED_ROOT / "reports" / "masters_thesis_draft_with_conference_figures.docx",
            GENERATED_ROOT / "reports" / "masters_thesis_draft_with_figures.docx",
            GENERATED_ROOT / "reports" / "papers_missing_author_rows_2026_06_06.csv",
            GENERATED_ROOT / "reports" / "experiment_metrics" / "experiment_comparison.csv",
            GENERATED_ROOT / "reports" / "experiment_metrics" / "experiment_comparison.md",
            GENERATED_ROOT / "reports" / "experiment_metrics" / "experiment_metrics_index.csv",
            GENERATED_ROOT / "reports" / "experiment_metrics" / "normalized_layer_comparison.md",
            GENERATED_ROOT / "reports" / "experiment_metrics" / "coverage_audit_evolution.md",
            GENERATED_ROOT / "reports" / "experiment_metrics" / "fullbatch_version_comparison.md",
            GENERATED_ROOT / "reports" / "experiment_metrics" / "fullbatch_version_comparison_overall.csv",
            GENERATED_ROOT / "reports" / "experiment_metrics" / "fullbatch_version_comparison_by_conference.csv",
            GENERATED_ROOT / "reports" / "experiment_metrics" / "fullbatch_snapshot_evolution.csv",
            GENERATED_ROOT / "reports" / "experiment_metrics" / "thesis_experiment_tables.md",
            GENERATED_ROOT / "analysis" / "artifact_index.csv",
            GENERATED_ROOT / "analysis" / "artifact_index.md",
            GENERATED_ROOT / "analysis" / "authors",
            GENERATED_ROOT / "analysis" / "collaboration",
            GENERATED_ROOT / "analysis" / "country",
            GENERATED_ROOT / "analysis" / "institutions",
            GENERATED_ROOT / "analysis" / "reports",
            GENERATED_ROOT / "analysis" / "trends",
            GENERATED_ROOT / "analysis" / "visualizations",
            *latest_snapshots,
        ]
    )

    base_data = collect_files(
        [
            GENERATED_ROOT / "cfp" / "output",
            GENERATED_ROOT / "author-roles",
            GENERATED_ROOT / "coverage",
            GENERATED_ROOT / "normalized" / "README.md",
            GENERATED_ROOT / "normalized" / "author_affiliation_facts.csv",
            GENERATED_ROOT / "normalized" / "institution_dim.csv",
            GENERATED_ROOT / "normalized" / "paper_facts.csv",
            GENERATED_ROOT / "normalized" / "normalization_report.json",
            GENERATED_ROOT / "extraction" / "artifact_index.csv",
            GENERATED_ROOT / "extraction" / "artifact_index.md",
            GENERATED_ROOT / "extraction" / "output",
            GENERATED_ROOT / "backfill" / "backfill_plan.json",
            GENERATED_ROOT / "backfill" / "backfill_plan.md",
        ]
    )

    historical_archive = collect_files(
        [
            GENERATED_ROOT / "archive",
            GENERATED_ROOT / "reports" / "thesis_analysis",
            GENERATED_ROOT / "reports" / "experiment_metrics" / "documented_historical_observations.csv",
            GENERATED_ROOT / "reports" / "experiment_metrics" / "documented_historical_observations.md",
            GENERATED_ROOT / "normalized" / "normalized",
            *historical_snapshots,
        ]
    )

    run_logs = collect_files(
        [
            GENERATED_ROOT / "analysis" / "automation_logs",
            GENERATED_ROOT / "analysis" / "automation_manifest.json",
            GENERATED_ROOT / "analysis" / "automation_report.md",
            GENERATED_ROOT / "extraction" / "noise_cleaning_report.json",
            GENERATED_ROOT / "extraction" / "unified_run_manifest.json",
            GENERATED_ROOT / "reports" / "experiment_metrics" / "variant_registry_template.csv",
        ]
    )

    return {
        "current_results": current_results,
        "base_data": base_data,
        "historical_archive": historical_archive,
        "run_logs": run_logs,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_root = args.output_root
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    buckets = build_buckets()
    manifest_rows: list[dict[str, str]] = []
    for bucket, files in buckets.items():
        copy_bucket(files, output_root, bucket, manifest_rows)

    write_csv(output_root / "version_manifest.csv", manifest_rows, ["bucket", "source", "copied_to"])

    write_readme(
        output_root / "README.md",
        "Generated Data Views",
        [
            "current_results: current reports, analysis outputs, figures, and latest experiment snapshots.",
            "base_data: current CFP, extraction, coverage, author-role, normalized, and backfill data tables.",
            "historical_archive: historical outputs, archived runs, superseded snapshots, and legacy layouts.",
            "run_logs: manifests, automation logs, and process-oriented reporting files.",
        ],
    )
    write_readme(
        output_root / "current_results" / "README.md",
        "Current Results",
        [
            "Use this folder when you want the latest metrics, result tables, report drafts, analysis summaries, and current figures.",
        ],
    )
    write_readme(
        output_root / "base_data" / "README.md",
        "Base Data",
        [
            "Use this folder when you need source-like generated tables such as CFP outputs, extraction outputs, coverage tables, normalized facts, and author-role files.",
        ],
    )
    write_readme(
        output_root / "historical_archive" / "README.md",
        "Historical Archive",
        [
            "Use this folder for historical comparison and full backtracking. It includes archived process runs, legacy thesis-analysis outputs, superseded snapshots, and old layout copies.",
        ],
    )
    write_readme(
        output_root / "run_logs" / "README.md",
        "Run Logs",
        [
            "Use this folder for process traces: automation logs, manifests, noise-cleaning reports, and variant registry metadata.",
        ],
    )

    write_index(
        output_root / "current_results" / "INDEX.md",
        "Current Results Index",
        output_root / "current_results",
        [
            (
                "Core Reports",
                list_markdown_and_docx(output_root / "current_results" / "reports")
                + sorted((output_root / "current_results" / "reports" / "experiment_metrics").glob("*.md"))
                + sorted((output_root / "current_results" / "reports" / "experiment_metrics").glob("*.csv")),
            ),
            (
                "Latest Snapshots",
                sorted((output_root / "current_results" / "reports" / "experiment_metrics" / "snapshots").glob("*.json")),
            ),
            (
                "Analysis Summaries",
                sorted((output_root / "current_results" / "analysis" / "reports").glob("*"))
                + sorted((output_root / "current_results" / "analysis" / "authors").glob("*.md"))
                + sorted((output_root / "current_results" / "analysis" / "country").glob("*.md"))
                + sorted((output_root / "current_results" / "analysis" / "institutions").glob("*.md"))
                + sorted((output_root / "current_results" / "analysis" / "collaboration").glob("*.md"))
                + sorted((output_root / "current_results" / "analysis" / "trends").glob("*.md")),
            ),
        ],
    )
    write_index(
        output_root / "base_data" / "INDEX.md",
        "Base Data Index",
        output_root / "base_data",
        [
            ("CFP Outputs", sorted((output_root / "base_data" / "cfp" / "output").glob("*"))),
            ("Coverage Tables", sorted((output_root / "base_data" / "coverage").glob("*"))),
            ("Author Role Data", sorted((output_root / "base_data" / "author-roles").glob("*"))),
            ("Normalized Facts", sorted((output_root / "base_data" / "normalized").glob("*"))),
            ("Extraction Summaries", sorted((output_root / "base_data" / "extraction" / "output" / "summaries").rglob("*"))),
        ],
    )
    write_index(
        output_root / "historical_archive" / "INDEX.md",
        "Historical Archive Index",
        output_root / "historical_archive",
        [
            (
                "Superseded Snapshots",
                sorted((output_root / "historical_archive" / "reports" / "experiment_metrics" / "snapshots").glob("*.json")),
            ),
            (
                "Historical Comparisons",
                sorted((output_root / "historical_archive" / "reports" / "experiment_metrics").glob("documented_historical_observations.*")),
            ),
            (
                "Legacy Thesis Analysis",
                sorted((output_root / "historical_archive" / "reports" / "thesis_analysis").rglob("*")),
            ),
        ],
    )
    write_index(
        output_root / "run_logs" / "INDEX.md",
        "Run Logs Index",
        output_root / "run_logs",
        [
            ("Automation Logs", sorted((output_root / "run_logs" / "analysis" / "automation_logs").glob("*"))),
            ("Manifests", sorted((output_root / "run_logs" / "analysis").glob("*manifest*.json")) + sorted((output_root / "run_logs" / "extraction").glob("*manifest*.json"))),
            ("Process Reports", sorted((output_root / "run_logs" / "analysis").glob("*report.md")) + sorted((output_root / "run_logs" / "extraction").glob("*report*.json")) + sorted((output_root / "run_logs" / "reports" / "experiment_metrics").glob("*template*.csv"))),
        ],
    )

    summary = {"output_root": str(output_root)}
    summary.update({f"{bucket}_files": len(files) for bucket, files in buckets.items()})
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
