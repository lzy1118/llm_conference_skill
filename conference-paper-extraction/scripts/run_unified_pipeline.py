# 把不同会议的数据抽取脚本统一调度起来，例如密码学三大顶会和安全会议，用户只需要指定会议或会议组，它会自动判断应该调用哪个后端脚本
# 总控
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from conference_registry import CONFERENCES, GROUPS, expand_selection, group_by_backend, list_backend_keys


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = Path("generated-data") / "extraction"
BACKEND_SCRIPTS = {
    "iacr_top3": ROOT / "conference-paper-extraction" / "scripts" / "iacr_top3_backend.py",
    "security_real": ROOT / "conference-paper-extraction" / "scripts" / "security_real_backend.py",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unified conference extraction runner for crypto and security venues"
    )
    parser.add_argument(
        "--conference",
        action="append",
        default=[],
        help="Conference key to run. Repeatable.",
    )
    parser.add_argument(
        "--group",
        action="append",
        default=[],
        help="Conference group to run. Repeatable.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--fetch", action="store_true", help="Fetch raw paper metadata first")
    parser.add_argument(
        "--fetch-affiliations",
        action="store_true",
        help="Fetch venue-specific affiliations when supported by backend",
    )
    parser.add_argument(
        "--resolve-mismatches",
        action="store_true",
        help="Run mismatch-resolution stage when supported by backend",
    )
    parser.add_argument(
        "--query-dblp-for-resolution",
        action="store_true",
        help="Allow online DBLP lookup during mismatch resolution when supported",
    )
    parser.add_argument(
        "--download-pdfs",
        action="store_true",
        help="Download paper PDFs when backend can resolve PDF URLs",
    )
    parser.add_argument(
        "--pdf-limit",
        type=int,
        default=0,
        help="Limit PDF downloads per conference; 0 means no limit",
    )
    parser.add_argument("--list-conferences", action="store_true")
    parser.add_argument("--list-backends", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print backend execution plan without running pipelines",
    )
    return parser.parse_args(argv)


def build_plan(
    conference_keys: list[str],
    output_dir: Path,
    fetch: bool,
    fetch_affiliations: bool,
    resolve_mismatches: bool,
    query_dblp_for_resolution: bool,
    download_pdfs: bool,
    pdf_limit: int,
) -> list[dict[str, object]]:
    grouped = group_by_backend(conference_keys)
    plan: list[dict[str, object]] = []
    for backend, keys in grouped.items():
        script_path = BACKEND_SCRIPTS[backend]
        command = [
            "python3",
            str(script_path),
            "--output-dir",
            str(output_dir),
            "--conference",
            *keys,
        ]
        if fetch:
            command.append("--fetch")
        if fetch_affiliations and backend == "security_real":
            command.append("--fetch-affiliations")
        if resolve_mismatches and backend == "iacr_top3":
            command.append("--resolve-mismatches")
        if query_dblp_for_resolution and backend == "iacr_top3":
            command.append("--query-dblp-for-resolution")
        if download_pdfs:
            command.append("--download-pdfs")
            if pdf_limit > 0:
                command.extend(["--pdf-limit", str(pdf_limit)])
        plan.append(
            {
                "backend": backend,
                "script": str(script_path),
                "conference_keys": keys,
                "command": command,
            }
        )
    return plan


def print_registry() -> None:
    print("Conference groups:")
    for key, group in GROUPS.items():
        print(f"  {key}: {group.description}")
    print("\nConferences:")
    for key, conference in CONFERENCES.items():
        print(
            f"  {key}: {conference.conference} {conference.year} "
            f"[{conference.family}, backend={conference.backend}]"
        )


def run_plan(plan: list[dict[str, object]]) -> int:
    manifest_path = None
    run_steps = []
    for step in plan:
        command = step["command"]
        output_dir = Path(command[command.index("--output-dir") + 1])
        manifest_path = output_dir / "unified_run_manifest.json"
        result = subprocess.run(command, cwd=ROOT, text=True, check=False)
        run_steps.append(
            {
                "backend": step["backend"],
                "script": step["script"],
                "conference_keys": step["conference_keys"],
                "command": command,
                "returncode": result.returncode,
            }
        )
        if result.returncode != 0:
            if manifest_path is not None:
                write_manifest(manifest_path, plan, run_steps)
            return result.returncode
    if manifest_path is not None:
        write_manifest(manifest_path, plan, run_steps)
    return 0


def write_manifest(path: Path, plan: list[dict[str, object]], run_steps: list[dict[str, object]]) -> None:
    conference_keys: list[str] = []
    for step in plan:
        conference_keys.extend(step["conference_keys"])
    payload = {
        "conference_keys": conference_keys,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "steps": run_steps,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.list_conferences:
        print_registry()
        return 0

    if args.list_backends:
        for backend in list_backend_keys():
            print(backend)
        return 0

    default_groups = ["all"] if not args.conference and not args.group else []
    selected = expand_selection(args.conference, args.group or default_groups)
    plan = build_plan(
        selected,
        args.output_dir,
        args.fetch,
        args.fetch_affiliations,
        args.resolve_mismatches,
        args.query_dblp_for_resolution,
        args.download_pdfs,
        args.pdf_limit,
    )

    if args.dry_run:
        print(json.dumps({"conference_keys": selected, "plan": plan}, ensure_ascii=False, indent=2))
        return 0

    return run_plan(plan)


if __name__ == "__main__":
    raise SystemExit(main())
