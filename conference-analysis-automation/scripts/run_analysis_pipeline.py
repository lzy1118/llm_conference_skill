from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


RUN_CHOICES = ("country", "institution", "author", "trend", "collaboration", "audit", "report", "visualization")
DEFAULT_OUTPUT_DIR = Path("generated-data") / "analysis"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run normalized conference analytics with low-coupling orchestration.")
    parser.add_argument("--raw-input", action="append", default=[], help="Raw row-level CSV input. Repeat for multiple files.")
    parser.add_argument("--normalized-input", help="Existing normalized author_affiliation_facts.csv path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Automation run output directory.")
    parser.add_argument("--conference")
    parser.add_argument("--year")
    parser.add_argument("--country")
    parser.add_argument("--us-only", action="store_true")
    parser.add_argument("--run", action="append", choices=RUN_CHOICES, help="Metric families to run. Defaults to all.")
    parser.add_argument("--trend-entity", choices=("country", "institution", "author"), default="country", help="Entity dimension for trend analysis.")
    parser.add_argument("--collaboration-mode", choices=("author", "country", "institution"), default="author", help="Edge mode for collaboration analysis.")
    parser.add_argument("--fail-fast", action="store_true", help="Stop after the first downstream analytics failure.")
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def run_command(command: list[str], cwd: Path) -> tuple[int, str, str]:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    return completed.returncode, completed.stdout, completed.stderr


def build_scope(args: argparse.Namespace) -> dict[str, object]:
    return {
        "conference": args.conference or "all",
        "year": args.year or "all",
        "country": args.country or "all",
        "us_only": args.us_only,
        "trend_entity": args.trend_entity,
        "collaboration_mode": args.collaboration_mode,
    }


def normalize_inputs_if_needed(args: argparse.Namespace, output_dir: Path, manifest: dict[str, object]) -> Path:
    if args.normalized_input:
        normalized_input = Path(args.normalized_input).resolve()
        if not normalized_input.exists():
            raise FileNotFoundError(f"Normalized input not found: {normalized_input}")
        manifest["normalization"] = {
            "executed": False,
            "normalized_input": str(normalized_input),
        }
        return normalized_input

    if not args.raw_input:
        raise ValueError("Provide either --normalized-input or at least one --raw-input")

    raw_inputs = [str(Path(value).resolve()) for value in args.raw_input]
    normalized_root = output_dir / "normalized_run"
    ensure_directory(normalized_root)

    command = [
        sys.executable,
        str(repo_root() / "conference-dataset-normalization" / "scripts" / "normalize_dataset.py"),
        *raw_inputs,
        "--output-dir",
        str(normalized_root),
    ]
    returncode, stdout, stderr = run_command(command, cwd=repo_root())
    normalized_input = normalized_root / "normalized" / "author_affiliation_facts.csv"
    manifest["normalization"] = {
        "executed": True,
        "command": command,
        "raw_inputs": raw_inputs,
        "returncode": returncode,
        "normalized_input": str(normalized_input),
        "stdout": stdout,
        "stderr": stderr,
    }
    if returncode != 0:
        raise RuntimeError("Normalization failed")
    return normalized_input


def analytics_commands(normalized_input: Path, output_dir: Path, args: argparse.Namespace, requested_runs: list[str]) -> list[tuple[str, list[str]]]:
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
        if args.us_only:
            institution_command.append("--us-only")
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
    return commands


def audit_commands(normalized_input: Path, output_dir: Path, requested_runs: list[str]) -> list[tuple[str, list[str]]]:
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


def execute_steps(step_commands: list[tuple[str, list[str]]], args: argparse.Namespace, manifest: dict[str, object]) -> None:
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
            raise RuntimeError(f"{step_name} analytics failed")


def run_analytics(normalized_input: Path, output_dir: Path, args: argparse.Namespace, manifest: dict[str, object]) -> None:
    requested_runs = args.run or list(RUN_CHOICES)
    manifest["requested_runs"] = requested_runs
    manifest["steps"] = []

    execute_steps(audit_commands(normalized_input, output_dir, requested_runs)[:1], args, manifest)
    execute_steps(analytics_commands(normalized_input, output_dir, args, requested_runs), args, manifest)
    execute_steps(audit_commands(normalized_input, output_dir, requested_runs)[1:], args, manifest)
    execute_steps(report_commands(output_dir, requested_runs), args, manifest)
    execute_steps(visualization_commands(output_dir, requested_runs), args, manifest)


def write_manifest(output_dir: Path, manifest: dict[str, object]) -> Path:
    path = output_dir / "automation_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def write_report(output_dir: Path, manifest: dict[str, object]) -> Path:
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
        f"- raw_inputs: {', '.join(manifest.get('raw_inputs', [])) or 'none'}",
        "",
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


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    ensure_directory(output_dir)

    manifest: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": build_scope(args),
        "raw_inputs": [str(Path(value).resolve()) for value in args.raw_input],
    }

    normalized_input = normalize_inputs_if_needed(args, output_dir, manifest)
    manifest["normalized_input"] = str(normalized_input)

    run_analytics(normalized_input, output_dir, args, manifest)
    write_manifest(output_dir, manifest)
    write_report(output_dir, manifest)


if __name__ == "__main__":
    main()
