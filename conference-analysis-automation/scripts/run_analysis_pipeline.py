from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


RUN_CHOICES = ("country", "institution", "author", "trend", "collaboration", "audit", "report", "visualization")
DEFAULT_OUTPUT_DIR = Path("generated-data") / "analysis"
DEFAULT_EXTRACTION_OUTPUT_DIR = Path("generated-data") / "extraction"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run normalized conference analytics with low-coupling orchestration.")
    parser.add_argument("--raw-input", action="append", default=[], help="Raw row-level CSV input. Repeat for multiple files.")
    parser.add_argument("--normalized-input", help="Existing normalized author_affiliation_facts.csv path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Automation run output directory.")
    parser.add_argument("--extract-conference", action="append", default=[], help="Conference key to extract before normalization. Repeatable.")
    parser.add_argument("--extract-group", action="append", default=[], help="Conference group to extract before normalization. Repeatable.")
    parser.add_argument("--extraction-output-dir", default=str(DEFAULT_EXTRACTION_OUTPUT_DIR), help="Extraction output directory when running unified extraction.")
    parser.add_argument("--extract-fetch", action="store_true", help="Fetch raw metadata during unified extraction stage.")
    parser.add_argument("--extract-fetch-affiliations", action="store_true", help="Fetch security venue affiliations during unified extraction stage.")
    parser.add_argument("--extract-resolve-mismatches", action="store_true", help="Run crypto mismatch resolution during unified extraction stage.")
    parser.add_argument("--extract-query-dblp-for-resolution", action="store_true", help="Allow DBLP lookup during crypto mismatch resolution.")
    parser.add_argument(
        "--skip-extract-noise-cleaning",
        action="store_true",
        help="Skip extraction-layer noise cleaning after unified extraction.",
    )
    parser.add_argument("--conference")
    parser.add_argument("--year")
    parser.add_argument("--country")
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
        "trend_entity": args.trend_entity,
        "collaboration_mode": args.collaboration_mode,
    }


def run_unified_extraction_if_needed(args: argparse.Namespace, manifest: dict[str, object]) -> list[Path]:
    if not args.extract_conference and not args.extract_group:
        manifest["extraction"] = {"executed": False}
        return []

    extraction_output_dir = Path(args.extraction_output_dir).resolve()
    dry_run_command = [
        sys.executable,
        str(repo_root() / "conference-paper-extraction" / "scripts" / "run_unified_pipeline.py"),
        "--output-dir",
        str(extraction_output_dir),
        "--dry-run",
    ]
    for conference in args.extract_conference:
        dry_run_command.extend(["--conference", conference])
    for group in args.extract_group:
        dry_run_command.extend(["--group", group])
    if args.extract_fetch:
        dry_run_command.append("--fetch")
    if args.extract_fetch_affiliations:
        dry_run_command.append("--fetch-affiliations")
    if args.extract_resolve_mismatches:
        dry_run_command.append("--resolve-mismatches")
    if args.extract_query_dblp_for_resolution:
        dry_run_command.append("--query-dblp-for-resolution")

    dry_returncode, dry_stdout, dry_stderr = run_command(dry_run_command, cwd=repo_root())
    if dry_returncode != 0:
        manifest["extraction"] = {
            "executed": False,
            "dry_run_command": dry_run_command,
            "returncode": dry_returncode,
            "stdout": dry_stdout,
            "stderr": dry_stderr,
        }
        raise RuntimeError("Unified extraction dry-run failed")

    dry_payload = json.loads(dry_stdout)
    selected_keys = dry_payload.get("conference_keys", [])

    extraction_command = [part for part in dry_run_command if part != "--dry-run"]
    returncode, stdout, stderr = run_command(extraction_command, cwd=repo_root())
    manifest["extraction"] = {
        "executed": True,
        "command": extraction_command,
        "conference_keys": selected_keys,
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "output_dir": str(extraction_output_dir),
    }
    if returncode != 0:
        raise RuntimeError("Unified extraction failed")

    raw_inputs: list[Path] = []
    missing_outputs: list[str] = []
    for conference_key in selected_keys:
        candidate = extraction_output_dir / "output" / "by_conference" / conference_key / "author_affiliations_audit.csv"
        if candidate.exists():
            raw_inputs.append(candidate)
        else:
            missing_outputs.append(conference_key)
    manifest["extraction"]["raw_inputs"] = [str(path) for path in raw_inputs]
    manifest["extraction"]["missing_outputs"] = missing_outputs
    return raw_inputs


def run_extraction_noise_cleaning_if_needed(args: argparse.Namespace, manifest: dict[str, object]) -> None:
    extraction = manifest.get("extraction", {})
    if not extraction.get("executed"):
        manifest["extraction_noise_cleaning"] = {"executed": False, "reason": "extraction_not_run"}
        return
    if args.skip_extract_noise_cleaning:
        manifest["extraction_noise_cleaning"] = {"executed": False, "reason": "skipped_by_flag"}
        return

    extraction_output_dir = Path(str(extraction.get("output_dir", DEFAULT_EXTRACTION_OUTPUT_DIR))).resolve()
    command = [
        sys.executable,
        str(repo_root() / "conference-paper-extraction" / "scripts" / "clean_extraction_noise.py"),
        "--output-dir",
        str(extraction_output_dir),
    ]
    for conference_key in extraction.get("conference_keys", []):
        command.extend(["--conference", str(conference_key)])

    returncode, stdout, stderr = run_command(command, cwd=repo_root())
    manifest["extraction_noise_cleaning"] = {
        "executed": True,
        "command": command,
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "output_dir": str(extraction_output_dir),
    }
    if returncode != 0:
        raise RuntimeError("Extraction noise cleaning failed")


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

    extracted_inputs = run_unified_extraction_if_needed(args, manifest)
    if extracted_inputs:
        run_extraction_noise_cleaning_if_needed(args, manifest)
    if extracted_inputs:
        raw_inputs = [str(path.resolve()) for path in extracted_inputs]
    else:
        raw_inputs = [str(Path(value).resolve()) for value in args.raw_input]

    if not raw_inputs:
        raise ValueError("Provide either --normalized-input, at least one --raw-input, or extraction selection flags")

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
        "## Extraction",
        "",
    ])

    extraction = manifest.get("extraction", {})
    if extraction.get("executed"):
        lines.extend([
            f"- executed: True",
            f"- extraction_output_dir: {extraction.get('output_dir', '')}",
            f"- extracted_conference_keys: {', '.join(extraction.get('conference_keys', [])) or 'none'}",
            f"- extracted_raw_inputs: {', '.join(extraction.get('raw_inputs', [])) or 'none'}",
            f"- missing_outputs: {', '.join(extraction.get('missing_outputs', [])) or 'none'}",
            "",
        ])
    else:
        lines.extend([
            "- executed: False",
            "",
        ])

    lines.extend([
        "## Extraction Noise Cleaning",
        "",
    ])
    extraction_noise_cleaning = manifest.get("extraction_noise_cleaning", {})
    if extraction_noise_cleaning.get("executed"):
        lines.extend([
            f"- executed: True",
            f"- extraction_output_dir: {extraction_noise_cleaning.get('output_dir', '')}",
            f"- returncode: {extraction_noise_cleaning.get('returncode', '')}",
            "",
        ])
    else:
        lines.extend([
            f"- executed: False",
            f"- reason: {extraction_noise_cleaning.get('reason', 'not_applicable')}",
            "",
        ])

    lines.extend([
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
