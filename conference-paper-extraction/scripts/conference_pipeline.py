"""Legacy compatibility wrapper for the unified extraction runner."""

from __future__ import annotations

import argparse

from run_unified_pipeline import main as run_unified_main


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compatibility entrypoint for conference extraction"
    )
    parser.add_argument(
        "--conference",
        nargs="+",
        default=["all"],
        help="Conference keys to process, or 'all'",
    )
    parser.add_argument("--output-dir", default="data")
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--fetch-affiliations", action="store_true")
    parser.add_argument("--resolve-mismatches", action="store_true")
    parser.add_argument("--query-dblp-for-resolution", action="store_true")
    parser.add_argument("--list-conferences", action="store_true")
    parser.add_argument("--list-backends", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def build_forward_argv(args: argparse.Namespace) -> list[str]:
    forwarded: list[str] = ["--output-dir", args.output_dir]
    if args.list_conferences:
        forwarded.append("--list-conferences")
    if args.list_backends:
        forwarded.append("--list-backends")
    if args.fetch:
        forwarded.append("--fetch")
    if args.fetch_affiliations:
        forwarded.append("--fetch-affiliations")
    if args.resolve_mismatches:
        forwarded.append("--resolve-mismatches")
    if args.query_dblp_for_resolution:
        forwarded.append("--query-dblp-for-resolution")
    if args.dry_run:
        forwarded.append("--dry-run")

    for conference in args.conference:
        if conference == "all":
            forwarded.extend(["--group", "all"])
        else:
            forwarded.extend(["--conference", conference])
    return forwarded


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run_unified_main(build_forward_argv(args))


if __name__ == "__main__":
    raise SystemExit(main())
