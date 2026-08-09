#!/usr/bin/env python3
"""Run one PDF-first metadata pipeline for the seven conference cases."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType


CONFERENCE_ALIASES = {
    "asiacrypt": ("crypto", "asiacrypt"),
    "asia_crypt": ("crypto", "asiacrypt"),
    "crypto": ("crypto", "crypto"),
    "eurocrypt": ("crypto", "eurocrypt"),
    "euro_crypt": ("crypto", "eurocrypt"),
    "ccs": ("security", "CCS"),
    "ndss": ("security", "NDSS"),
    "ieee_s&p": ("security", "IEEE_S&P"),
    "ieee_sp": ("security", "IEEE_S&P"),
    "sp": ("security", "IEEE_S&P"),
    "usenix_security": ("security", "USENIX_SECURITY"),
    "usenix": ("security", "USENIX_SECURITY"),
}


def normalized_key(value: str) -> str:
    return value.strip().casefold().replace("-", "_").replace(" ", "_")


def canonical_conference(value: str) -> tuple[str, str]:
    result = CONFERENCE_ALIASES.get(normalized_key(value))
    if not result:
        supported = "ASIACRYPT, CRYPTO, EUROCRYPT, CCS, IEEE S&P, NDSS, USENIX Security"
        raise ValueError(f"unsupported conference {value!r}; expected one of: {supported}")
    return result


def load_security_runner(repo_root: Path) -> ModuleType:
    path = repo_root / "conference-security-research-automation/scripts/run_pipeline.py"
    spec = importlib.util.spec_from_file_location("conference_security_pipeline", path)
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot load existing security pipeline: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conference", required=True)
    parser.add_argument("--year", required=True)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--pdf-dir", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--python")
    parser.add_argument("--institution-table", type=Path)
    parser.add_argument("--reuse-extraction", action="store_true")
    parser.add_argument("--skip-analysis", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def append_path(command: list[str], option: str, value: Path | None) -> None:
    if value is not None:
        command.extend([option, str(value.expanduser().resolve())])


def run_security(args: argparse.Namespace, root: Path, python: str, conference: str) -> int:
    script = root / "conference-security-research-automation/scripts/run_pipeline.py"
    command = [
        python, str(script), "--repo-root", str(root), "--conference", conference,
        "--year", args.year, "--python", python,
    ]
    append_path(command, "--pdf-dir", args.pdf_dir)
    append_path(command, "--output-root", args.output_root)
    append_path(command, "--institution-table", args.institution_table)
    if args.reuse_extraction:
        command.append("--reuse-extraction")
    if args.skip_analysis:
        command.append("--skip-analysis")
    if args.dry_run:
        command.append("--dry-run")
    return subprocess.run(command, cwd=root, check=False).returncode


def run_crypto(
    args: argparse.Namespace,
    root: Path,
    python: str,
    conference: str,
    shared: ModuleType,
) -> int:
    grobid = root / "conference-grobid-extract-metadata/scripts"
    affil = root / "conference-affiliation-normalizer/scripts"
    output_root = (args.output_root or root / "generated-data").expanduser().resolve()
    pdf_dir = (args.pdf_dir or output_root / "pdf" / conference / args.year).expanduser().resolve()
    dataset_root = output_root / "full_output" / conference / args.year
    dataset = dataset_root / f"author_metadata_dataset_{args.year}"
    prefix = f"{conference}_{args.year}"
    raw_dir = output_root / "extraction_raw" / conference / args.year
    split_dir = output_root / "extraction_spilt" / conference / args.year
    affilgood_dir = output_root / "extraction_affilgood" / conference / args.year
    primary_dir = output_root / "primary_institution" / conference / args.year
    final_dir = output_root / "extraction_final" / conference / args.year
    raw = raw_dir / f"{prefix}_raw作者机构拆分.csv"
    split = split_dir / f"{prefix}_作者机构拆分_output.csv"
    institution_report = split_dir / f"{prefix}_institution_match_report.json"
    unresolved = affilgood_dir / f"{prefix}_affilgood_unresolved.csv"
    normalized = affilgood_dir / f"{prefix}_affilgood_unresolved.jsonl"
    pre_reference = affilgood_dir / f"{prefix}_affilgood_pre_reference.csv"
    affilgood_csv = affilgood_dir / f"{prefix}_affilgood_作者机构拆分_output.csv"
    primary_csv = primary_dir / f"{prefix}_主体机构.csv"
    final_csv = final_dir / f"{prefix}_final.csv"
    requested_table = args.institution_table.expanduser().resolve() if args.institution_table else None
    generated_table = output_root / "institution_raw.csv"
    bundled_table = root / "conference-affiliation-normalizer/references/institution_raw.csv"
    institution_table = requested_table or (generated_table if generated_table.is_file() else bundled_table)
    if not args.dry_run and not institution_table.is_file():
        raise FileNotFoundError(f"institution_raw.csv not found: {institution_table}")

    if not args.reuse_extraction:
        shared.run([
            python, str(grobid / "extract_paper_metadata.py"), "--input-dir", str(pdf_dir),
            "--output-dir", str(dataset_root), "--dataset-name", dataset.name,
            "--conference", conference, "--year", args.year,
        ], args.dry_run, root)
        if not args.dry_run:
            shared.verify_dataset(dataset, allow_missing_authors=True)
        shared.run([
            python, str(grobid / "enrich_pdf_author_roles.py"), "--dataset-dir", str(dataset),
            "--conference", conference, "--pdf-dir", str(pdf_dir), "--apply",
        ], args.dry_run, root)
        if not args.dry_run:
            shared.verify_dataset(dataset)
    elif not args.dry_run:
        shared.verify_dataset(dataset)

    shared.run([python, str(grobid / "split_affiliations_raw.py"), "--input",
                str(dataset / "paper_metadata.csv"), "--output", str(raw)], args.dry_run, root)
    shared.run([python, str(affil / "match_institution_reference_csv.py"), "--input", str(raw),
                "--output", str(split), "--institution-table", str(institution_table),
                "--report", str(institution_report), "--prepare-only"], args.dry_run, root)
    unresolved_count = None if args.dry_run else shared.write_unresolved(split, unresolved)
    if args.dry_run or unresolved_count:
        shared.run([python, str(affil / "run_affilgood.py"), "--input", str(unresolved),
                    "--input-format", "csv", "--affiliation-field", "affiliations",
                    "--id-field", "record_id", "--output", str(normalized),
                    "--output-format", "normalized", "--no-institution-table"], args.dry_run, root)
    if not args.dry_run:
        shared.merge_affilgood(split, normalized if unresolved_count else None, pre_reference)
    shared.run([python, str(affil / "match_institution_reference_csv.py"), "--input",
                str(pre_reference), "--output", str(affilgood_csv), "--institution-table",
                str(institution_table), "--report", str(institution_report)], args.dry_run, root)
    if not args.dry_run:
        match_report = json.loads(institution_report.read_text(encoding="utf-8"))
        if match_report.get("review_required", 0) or match_report.get("blank_country_actionable", 0):
            raise RuntimeError(
                "Institution automation quality gate failed: "
                f"review_required={match_report.get('review_required', 0)}, "
                f"blank_country_actionable={match_report.get('blank_country_actionable', 0)}; "
                f"inspect {institution_report}"
            )
    shared.run([python, str(affil / "extract_crypto_primary_institutions.py"), "--input",
                str(affilgood_csv), "--output", str(primary_csv), "--institution-table",
                str(institution_table)], args.dry_run, root)
    shared.run([python, str(affil / "generate_final_view.py"), "--input", str(primary_csv),
                "--conference", conference, "--year", args.year, "--output", str(final_csv)],
               args.dry_run, root)
    if not args.dry_run:
        rows = shared.verify_final(final_csv)
        print(f"Final display table verified: {final_csv} ({rows} rows)")
    analysis = root / "conference-analysis-automation/scripts/run_analysis_pipeline.py"
    if not args.skip_analysis and analysis.exists():
        shared.run([python, str(analysis), "--affilgood-input", str(primary_csv), "--output-dir",
                    str(output_root / "analysis" / conference / args.year)], args.dry_run, root)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    family, conference = canonical_conference(args.conference)
    bootstrap_root = args.repo_root.expanduser().resolve() if args.repo_root else Path(__file__).resolve().parents[2]
    shared = load_security_runner(bootstrap_root)
    root = shared.find_repo_root(args.repo_root)
    python = shared.choose_python(args.python, root)
    if family == "security":
        return run_security(args, root, python, conference)
    return run_crypto(args, root, python, conference, shared)


if __name__ == "__main__":
    raise SystemExit(main())
