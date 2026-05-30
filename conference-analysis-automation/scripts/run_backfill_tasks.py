from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASK_FILE = ROOT / "generated-data" / "coverage" / "backfill_tasks.csv"
DEFAULT_OUTPUT_DIR = ROOT / "generated-data" / "backfill"
DEFAULT_EXTRACTION_DIR = ROOT / "generated-data" / "extraction"
DEFAULT_CFP_DIR = ROOT / "generated-data" / "cfp"
DEFAULT_AUTHOR_ROLES_DIR = ROOT / "generated-data" / "author-roles"
DEFAULT_NORMALIZED_INPUT = ROOT / "generated-data" / "normalized" / "author_affiliation_facts.csv"


def read_tasks(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def command_for_task(task: dict[str, str], args: argparse.Namespace) -> tuple[list[str], str]:
    task_type = task.get("task_type", "")
    conference_key = task.get("conference_key", "")
    if task_type == "fetch_papers":
        return (
            [
                sys.executable,
                str(ROOT / "conference-paper-extraction" / "scripts" / "run_unified_pipeline.py"),
                "--conference",
                conference_key,
                "--output-dir",
                str(args.extraction_dir),
                "--fetch",
            ],
            "network",
        )
    if task_type == "fetch_affiliations":
        return (
            [
                sys.executable,
                str(ROOT / "conference-paper-extraction" / "scripts" / "run_unified_pipeline.py"),
                "--conference",
                conference_key,
                "--output-dir",
                str(args.extraction_dir),
                "--fetch-affiliations",
                "--resolve-mismatches",
            ],
            "network",
        )
    if task_type == "extract_cfp":
        return (
            [
                sys.executable,
                str(ROOT / "conference-cfp-extraction" / "scripts" / "run_cfp_pipeline.py"),
                "--output-dir",
                str(args.cfp_dir),
            ],
            "local",
        )
    if task_type == "extract_author_roles":
        command = [
            sys.executable,
            str(ROOT / "conference-author-role-extraction" / "scripts" / "build_author_roles.py"),
            "--input",
            str(args.normalized_input),
            "--output-dir",
            str(args.author_roles_dir),
        ]
        if args.role_overrides:
            command.extend(["--role-overrides", str(args.role_overrides)])
        return command, "local"
    if task_type in {"add_expected_paper_count", "verify_paper_count", "normalize_country"}:
        return [], "manual"
    return [], "unsupported"


def filter_tasks(tasks: list[dict[str, str]], args: argparse.Namespace) -> list[dict[str, str]]:
    filtered = tasks
    if args.task_type:
        allowed = set(args.task_type)
        filtered = [task for task in filtered if task.get("task_type") in allowed]
    if args.priority:
        allowed = set(args.priority)
        filtered = [task for task in filtered if task.get("priority") in allowed]
    if args.conference:
        allowed = set(args.conference)
        filtered = [task for task in filtered if task.get("conference_key") in allowed]
    if args.limit is not None:
        filtered = filtered[: args.limit]
    return filtered


def build_plan(tasks: list[dict[str, str]], args: argparse.Namespace) -> list[dict[str, object]]:
    plan: list[dict[str, object]] = []
    seen_commands: dict[tuple[str, ...], str] = {}
    for task in tasks:
        command, execution_kind = command_for_task(task, args)
        runnable = bool(command) and execution_kind == "local" or (bool(command) and execution_kind == "network" and args.allow_network)
        duplicate_of = ""
        command_key = tuple(str(part) for part in command)
        if command_key and args.dedupe_commands:
            duplicate_of = seen_commands.get(command_key, "")
            if duplicate_of:
                runnable = False
                execution_kind = "duplicate"
            else:
                seen_commands[command_key] = task.get("task_id", "")
        plan.append(
            {
                "task_id": task.get("task_id", ""),
                "conference_key": task.get("conference_key", ""),
                "task_type": task.get("task_type", ""),
                "priority": task.get("priority", ""),
                "reason": task.get("reason", ""),
                "execution_kind": execution_kind,
                "runnable": runnable,
                "duplicate_of": duplicate_of,
                "command": command,
            }
        )
    return plan


def execute_plan(plan: list[dict[str, object]], args: argparse.Namespace) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for step in plan:
        command = step.get("command", [])
        runnable = bool(step.get("runnable"))
        result: dict[str, object] = {**step, "executed": False, "returncode": None}
        if args.execute and runnable and command:
            completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
            result.update(
                {
                    "executed": True,
                    "returncode": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                }
            )
            if completed.returncode != 0 and args.fail_fast:
                results.append(result)
                break
        results.append(result)
    return results


def write_report(path: Path, payload: dict[str, object]) -> None:
    plan = payload["plan"]
    results = payload["results"]
    lines = [
        "# Backfill Task Plan",
        "",
        "## Summary",
        "",
        f"- selected_tasks: {len(plan)}",
        f"- execute: {payload['execute']}",
        f"- allow_network: {payload['allow_network']}",
        f"- runnable_tasks: {sum(1 for step in plan if step['runnable'])}",
        f"- duplicate_tasks: {sum(1 for step in plan if step.get('execution_kind') == 'duplicate')}",
        f"- executed_tasks: {sum(1 for step in results if step['executed'])}",
        "",
        "## First Tasks",
        "",
    ]
    for step in plan[:20]:
        command = " ".join(str(part) for part in step["command"]) if step["command"] else "manual"
        duplicate_note = f" duplicate_of={step['duplicate_of']}" if step.get("duplicate_of") else ""
        lines.append(f"- {step['task_id']} [{step['execution_kind']}]{duplicate_note}: {command}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan or execute generated conference backfill tasks.")
    parser.add_argument("--task-file", type=Path, default=DEFAULT_TASK_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--extraction-dir", type=Path, default=DEFAULT_EXTRACTION_DIR)
    parser.add_argument("--cfp-dir", type=Path, default=DEFAULT_CFP_DIR)
    parser.add_argument("--author-roles-dir", type=Path, default=DEFAULT_AUTHOR_ROLES_DIR)
    parser.add_argument("--normalized-input", type=Path, default=DEFAULT_NORMALIZED_INPUT)
    parser.add_argument("--role-overrides", type=Path)
    parser.add_argument("--task-type", action="append")
    parser.add_argument("--priority", action="append")
    parser.add_argument("--conference", action="append")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--no-dedupe-commands", dest="dedupe_commands", action="store_false", help="Keep duplicate commands in the runnable plan")
    parser.set_defaults(dedupe_commands=True)
    parser.add_argument("--execute", action="store_true", help="Execute runnable local tasks. Default is dry-run plan only.")
    parser.add_argument("--allow-network", action="store_true", help="Allow network-dependent extraction tasks to run when --execute is set.")
    parser.add_argument("--fail-fast", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tasks = filter_tasks(read_tasks(args.task_file.resolve()), args)
    plan = build_plan(tasks, args)
    results = execute_plan(plan, args)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "task_file": str(args.task_file.resolve()),
        "execute": args.execute,
        "allow_network": args.allow_network,
        "plan": plan,
        "results": results,
    }
    output_dir = args.output_dir.resolve()
    write_json(output_dir / "backfill_plan.json", payload)
    write_report(output_dir / "backfill_plan.md", payload)


if __name__ == "__main__":
    main()
