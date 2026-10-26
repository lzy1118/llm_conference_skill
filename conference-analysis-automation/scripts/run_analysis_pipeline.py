from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


RUN_CHOICES = ("country", "institution", "author", "trend", "collaboration", "audit", "report", "visualization")
DEFAULT_OUTPUT_DIR = Path("generated-data") / "analysis"


def parse_args() -> argparse.Namespace:
    """解析端到端分析编排入口的命令行参数。"""
    parser = argparse.ArgumentParser(description="Run normalized conference analytics with low-coupling orchestration.")
    parser.add_argument("--normalized-input", help="Existing normalized author_affiliation_facts.csv path.")
    parser.add_argument("--affilgood-input", help="Full AffilGood CSV produced by the PDF-first conference pipeline.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Automation run output directory.")
    parser.add_argument("--conference")
    parser.add_argument("--year")
    parser.add_argument("--country")
    parser.add_argument("--run", action="append", choices=RUN_CHOICES, help="Metric families to run. Defaults to all.")
    parser.add_argument("--trend-entity", choices=("country", "institution", "author"), default="country", help="Entity dimension for trend analysis.")
    parser.add_argument("--collaboration-mode", choices=("author", "country", "institution"), default="author", help="Edge mode for collaboration analysis.")
    parser.add_argument("--fail-fast", action="store_true", help="Stop after the first downstream analytics failure.")
    return parser.parse_args()


def repo_root() -> Path:
    """返回仓库根目录，便于稳定调用其他子脚本。"""
    return Path(__file__).resolve().parents[2]


def ensure_directory(path: Path) -> None:
    """创建输出目录树；若已存在则直接复用。"""
    path.mkdir(parents=True, exist_ok=True)


def run_command(command: list[str], cwd: Path) -> tuple[int, str, str]:
    """执行子进程，并为清单记录返回码与标准输出信息。"""
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    return completed.returncode, completed.stdout, completed.stderr


def build_scope(args: argparse.Namespace) -> dict[str, object]:
    """构造写入自动化清单中的标准化筛选范围记录。"""
    return {
        "conference": args.conference or "all",
        "year": args.year or "all",
        "country": args.country or "all",
        "trend_entity": args.trend_entity,
        "collaboration_mode": args.collaboration_mode,
    }


def normalize_inputs_if_needed(args: argparse.Namespace, output_dir: Path, manifest: dict[str, object]) -> Path:
    """复用已有事实表，或从 PDF 主流程的 AffilGood 明细生成。"""
    if args.normalized_input:
        normalized_input = Path(args.normalized_input).resolve()
        if not normalized_input.exists():
            raise FileNotFoundError(f"Normalized input not found: {normalized_input}")
        manifest["normalization"] = {
            "executed": False,
            "normalized_input": str(normalized_input),
        }
        return normalized_input

    if args.affilgood_input:
        affilgood_input = Path(args.affilgood_input).resolve()
        if not affilgood_input.exists():
            raise FileNotFoundError(f"AffilGood input not found: {affilgood_input}")
        normalized_root = output_dir / "normalized"
        ensure_directory(normalized_root)
        command = [
            sys.executable,
            str(repo_root() / "conference-analysis-automation" / "scripts" / "prepare_affilgood_facts.py"),
            "--input", str(affilgood_input),
            "--output-dir", str(normalized_root),
        ]
        returncode, stdout, stderr = run_command(command, cwd=repo_root())
        normalized_input = normalized_root / "author_affiliation_facts.csv"
        manifest["normalization"] = {
            "executed": True,
            "mode": "affilgood_split_csv",
            "command": command,
            "source_input": str(affilgood_input),
            "normalized_input": str(normalized_input),
            "returncode": returncode,
            "stdout": stdout,
            "stderr": stderr,
        }
        if returncode != 0:
            raise RuntimeError("AffilGood analytics adaptation failed")
        return normalized_input

    raise ValueError("Provide --affilgood-input or --normalized-input")


def analytics_commands(normalized_input: Path, output_dir: Path, args: argparse.Namespace, requested_runs: list[str]) -> list[tuple[str, list[str]]]:
    """按所选统计类别组装下游分析命令。"""
    root = repo_root()
    shared_flags: list[str] = ["--input", str(normalized_input), "--output-dir", str(output_dir)]
    if args.conference:
        shared_flags.extend(["--conference", args.conference])
    if args.year:
        shared_flags.extend(["--year", str(args.year)])

    commands: list[tuple[str, list[str]]] = []
    if "country" in requested_runs:
        commands.append(
            (
                "country",
                [
                    sys.executable,
                    str(root / "conference-country-statistics" / "scripts" / "country_statistics.py"),
                    *shared_flags,
                ],
            )
        )
    if "institution" in requested_runs:
        institution_command = [
            sys.executable,
            str(root / "conference-institution-statistics" / "scripts" / "institution_statistics.py"),
            *shared_flags,
        ]
        if args.country:
            institution_command.extend(["--country", args.country])
        commands.append(("institution", institution_command))
    if "author" in requested_runs:
        commands.append(
            (
                "author",
                [
                    sys.executable,
                    str(root / "conference-author-statistics" / "scripts" / "author_statistics.py"),
                    *shared_flags,
                ],
            )
        )
    if "trend" in requested_runs:
        trend_command = [
            sys.executable,
            str(root / "conference-trend-analysis" / "scripts" / "trend_analysis.py"),
            *shared_flags,
            "--entity",
            args.trend_entity,
        ]
        commands.append(("trend", trend_command))
    if "collaboration" in requested_runs:
        collaboration_command = [
            sys.executable,
            str(root / "conference-collaboration-analysis" / "scripts" / "collaboration_analysis.py"),
            *shared_flags,
            "--mode",
            args.collaboration_mode,
        ]
        commands.append(("collaboration", collaboration_command))
    if "country" in requested_runs or "institution" in requested_runs:
        author_paper_input = normalized_input.parent / "author_paper_affiliation_facts.csv"
        required_scope_fields = {
            "paper_key", "author_paper_key", "first_inst", "first_country",
            "participating_insts", "participating_countries",
        }
        available_scope_fields: set[str] = set()
        if author_paper_input.exists():
            with author_paper_input.open(encoding="utf-8", newline="") as handle:
                available_scope_fields = set(csv.DictReader(handle).fieldnames or [])
        if required_scope_fields.issubset(available_scope_fields):
            dual_scope_command = [
                sys.executable,
                str(root / "conference-analysis-automation" / "scripts" / "generate_affiliation_scope_statistics.py"),
                "--input",
                str(author_paper_input),
                "--output-dir",
                str(output_dir),
            ]
            if args.conference:
                dual_scope_command.extend(["--conference", args.conference])
            if args.year:
                dual_scope_command.extend(["--year", str(args.year)])
            commands.append(("affiliation-scope", dual_scope_command))
    return commands


def audit_commands(normalized_input: Path, output_dir: Path, requested_runs: list[str]) -> list[tuple[str, list[str]]]:
    """构造面向归一化数据与分析产物的质量审计命令。"""
    if "audit" not in requested_runs:
        return []

    root = repo_root()
    normalized_parent = normalized_input.parent
    institution_dim = normalized_parent / "institution_dim.csv"
    audit_normalized_command = [
        sys.executable,
        str(root / "conference-quality-audit" / "scripts" / "quality_audit.py"),
        "--normalized-input",
        str(normalized_input),
        "--output-dir",
        str(output_dir / "audit" / "normalized"),
    ]
    if institution_dim.exists():
        audit_normalized_command.extend(["--institution-dim", str(institution_dim)])

    audit_analysis_command = [
        sys.executable,
        str(root / "conference-quality-audit" / "scripts" / "quality_audit.py"),
        "--analysis-dir",
        str(output_dir),
        "--output-dir",
        str(output_dir / "audit" / "analysis"),
    ]
    return [
        ("audit-normalized", audit_normalized_command),
        ("audit-analysis", audit_analysis_command),
    ]


def report_commands(output_dir: Path, requested_runs: list[str]) -> list[tuple[str, list[str]]]:
    """在请求报告阶段时，构造报告生成命令。"""
    if "report" not in requested_runs:
        return []

    root = repo_root()
    return [
        (
            "report",
            [
                sys.executable,
                str(root / "conference-report-generation" / "scripts" / "generate_report.py"),
                "--analysis-dir",
                str(output_dir),
                "--output-dir",
                str(output_dir / "reports"),
            ],
        )
    ]


def visualization_commands(output_dir: Path, requested_runs: list[str]) -> list[tuple[str, list[str]]]:
    """构造面向论文图表产出的可视化命令。"""
    if "visualization" not in requested_runs:
        return []

    root = repo_root()
    return [
        (
            "visualization",
            [
                sys.executable,
                str(root / "conference-visualization" / "scripts" / "generate_visualizations.py"),
                "--analysis-dir",
                str(output_dir),
                "--output-dir",
                str(output_dir / "visualizations"),
            ],
        )
    ]


def execute_steps(step_commands: list[tuple[str, list[str]]], args: argparse.Namespace, manifest: dict[str, object]) -> bool:
    """Run commands in order, returning false when fail-fast should stop."""
    for step_name, command in step_commands:
        returncode, stdout, stderr = run_command(command, cwd=repo_root())
        step_record = {
            "step": step_name,
            "command": command,
            "returncode": returncode,
            "stdout": stdout,
            "stderr": stderr,
        }
        manifest["steps"].append(step_record)
        if returncode != 0 and args.fail_fast:
            return False
    return True


def run_analytics(normalized_input: Path, output_dir: Path, args: argparse.Namespace, manifest: dict[str, object]) -> None:
    """按既定顺序执行审计、分析、报告与可视化流程。"""
    requested_runs = args.run or list(RUN_CHOICES)
    manifest["requested_runs"] = requested_runs
    manifest["steps"] = []

    phases = (
        audit_commands(normalized_input, output_dir, requested_runs)[:1],
        analytics_commands(normalized_input, output_dir, args, requested_runs),
        audit_commands(normalized_input, output_dir, requested_runs)[1:],
        report_commands(output_dir, requested_runs),
        visualization_commands(output_dir, requested_runs),
    )
    for phase_commands in phases:
        if not execute_steps(phase_commands, args, manifest):
            return


def write_manifest(output_dir: Path, manifest: dict[str, object]) -> Path:
    """保存机器可读的自动化运行清单。"""
    path = output_dir / "automation_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def write_report(output_dir: Path, manifest: dict[str, object]) -> Path:
    """写出便于人工查看的轻量运行摘要。"""
    report_path = output_dir / "automation_report.md"
    lines = [
        "# Conference Analysis Automation Report",
        "",
        "## Scope",
        "",
    ]
    for key, value in manifest["scope"].items():
        lines.append(f"- {key}: {value}")

    lines.extend([
        "",
        "## Inputs",
        "",
        f"- normalized_input: {manifest['normalized_input']}",
        "## Steps",
        "",
    ])

    for step in manifest.get("steps", []):
        status = "ok" if step["returncode"] == 0 else "failed"
        lines.append(f"- {step['step']}: {status}")

    failures = [step for step in manifest.get("steps", []) if step["returncode"] != 0]
    lines.extend([
        "",
        "## Result",
        "",
        f"- failed_steps: {len(failures)}",
        f"- requested_runs: {', '.join(manifest.get('requested_runs', []))}",
    ])

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main() -> int:
    """统筹可选的抽取、归一化、分析与摘要输出流程。"""
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    ensure_directory(output_dir)

    manifest: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": build_scope(args),
    }

    normalized_input = normalize_inputs_if_needed(args, output_dir, manifest)
    manifest["normalized_input"] = str(normalized_input)

    run_analytics(normalized_input, output_dir, args, manifest)
    write_manifest(output_dir, manifest)
    write_report(output_dir, manifest)
    return int(any(step["returncode"] != 0 for step in manifest["steps"]))


if __name__ == "__main__":
    raise SystemExit(main())
