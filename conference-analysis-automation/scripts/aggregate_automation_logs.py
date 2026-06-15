from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


DEFAULT_OUTPUT_DIR = Path("generated-data") / "analysis" / "automation_logs"


def read_manifest(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def manifest_paths(inputs: list[Path]) -> list[Path]:
    paths: list[Path] = []
    for value in inputs:
        if value.is_dir():
            candidate = value / "automation_manifest.json"
            if candidate.exists():
                paths.append(candidate)
            paths.extend(sorted(value.glob("*/automation_manifest.json")))
        elif value.exists():
            paths.append(value)
    return sorted(set(paths))


def summarize_manifest(path: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    manifest = read_manifest(path)
    steps = manifest.get("steps", [])
    if not isinstance(steps, list):
        steps = []
    failures = [step for step in steps if isinstance(step, dict) and int(step.get("returncode", 0) or 0) != 0]
    scope = manifest.get("scope", {})
    if not isinstance(scope, dict):
        scope = {}
    run_id = path.parent.name
    row = {
        "run_id": run_id,
        "manifest_path": str(path),
        "generated_at": manifest.get("generated_at", ""),
        "conference": scope.get("conference", "all"),
        "year": scope.get("year", "all"),
        "country": scope.get("country", "all"),
        "requested_runs": " | ".join(str(item) for item in manifest.get("requested_runs", [])),
        "step_count": len(steps),
        "failed_steps": len(failures),
        "normalized_input": manifest.get("normalized_input", ""),
        "raw_inputs": " | ".join(str(item) for item in manifest.get("raw_inputs", [])),
    }
    step_rows = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue
        step_rows.append(
            {
                "run_id": run_id,
                "step_index": index,
                "step": step.get("step", ""),
                "returncode": step.get("returncode", ""),
                "status": "ok" if int(step.get("returncode", 0) or 0) == 0 else "failed",
                "stdout_chars": len(str(step.get("stdout", ""))),
                "stderr_chars": len(str(step.get("stderr", ""))),
            }
        )
    return row, step_rows


def write_markdown(path: Path, summary_rows: list[dict[str, object]], step_rows: list[dict[str, object]]) -> None:
    failed_runs = [row for row in summary_rows if int(row.get("failed_steps", 0) or 0) > 0]
    lines = [
        "# Automation Log Summary",
        "",
        "## Summary",
        "",
        f"- runs: {len(summary_rows)}",
        f"- failed_runs: {len(failed_runs)}",
        f"- step_rows: {len(step_rows)}",
        "",
        "## Runs",
        "",
        "| run_id | generated_at | requested_runs | step_count | failed_steps |",
        "|---|---|---|---:|---:|",
    ]
    for row in summary_rows:
        lines.append(
            f"| {row['run_id']} | {row['generated_at']} | {row['requested_runs']} | {row['step_count']} | {row['failed_steps']} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate automation manifests across analysis runs.")
    parser.add_argument("--input", action="append", type=Path, default=[Path("generated-data") / "analysis"])
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary_rows: list[dict[str, object]] = []
    step_rows: list[dict[str, object]] = []
    for path in manifest_paths(args.input):
        summary, steps = summarize_manifest(path)
        summary_rows.append(summary)
        step_rows.extend(steps)

    output_dir = args.output_dir
    write_csv(
        output_dir / "automation_run_summary.csv",
        [
            "run_id",
            "manifest_path",
            "generated_at",
            "conference",
            "year",
            "country",
            "requested_runs",
            "step_count",
            "failed_steps",
            "normalized_input",
            "raw_inputs",
        ],
        summary_rows,
    )
    write_csv(
        output_dir / "automation_step_summary.csv",
        ["run_id", "step_index", "step", "returncode", "status", "stdout_chars", "stderr_chars"],
        step_rows,
    )
    write_markdown(output_dir / "automation_log_summary.md", summary_rows, step_rows)


if __name__ == "__main__":
    main()
