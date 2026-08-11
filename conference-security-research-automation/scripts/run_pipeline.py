#!/usr/bin/env python3
"""Run the conference PDF-to-analysis data pipeline."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


REFERENCE_FIELDS = (
    "affilgood_ror_ids", "affilgood_institutions", "affilgood_location_country",
    "affilgood_location_city", "affilgood_standard_institutions",
    "affilgood_standardization_source",
)
REQUIRED_DATASET_ENTRIES = (
    "metadata_json", "evidence_json", "candidate_json", "pdf_stage", "tei_header_xml",
    "paper_index.csv", "paper_metadata.csv", "conference_year_paper_abstract.csv",
    "review_queue.csv", "skipped_files.csv", "extraction_metrics.json",
)
CONFERENCE_ALIASES = {
    "asiacrypt": "ASIACRYPT",
    "asia_crypt": "ASIACRYPT",
    "crypto": "CRYPTO",
    "eurocrypt": "EUROCRYPT",
    "euro_crypt": "EUROCRYPT",
    "ccs": "CCS",
    "ndss": "NDSS",
    "ieee_s_p": "IEEE_S&P",
    "ieee_sp": "IEEE_S&P",
    "sp": "IEEE_S&P",
    "usenix_security": "USENIX_SECURITY",
    "usenix": "USENIX_SECURITY",
}

CONFERENCE_SLUGS = {
    "ASIACRYPT": "asiacrypt",
    "CRYPTO": "crypto",
    "EUROCRYPT": "eurocrypt",
    "CCS": "ccs",
    "NDSS": "ndss",
    "IEEE_S&P": "ieee_s&p",
    "USENIX_SECURITY": "usenix_security",
}


SECURITY_CONFERENCES = {"CCS", "NDSS", "IEEE_S&P", "USENIX_SECURITY"}


def normalized_conference_key(value: str) -> str:
    """Return a stable filesystem-safe key for a conference label."""
    key = re.sub(r"[^\w]+", "_", value.strip().casefold(), flags=re.UNICODE)
    return re.sub(r"_+", "_", key).strip("_")


def canonical_conference(value: str) -> str:
    key = normalized_conference_key(value)
    if not key:
        raise ValueError("conference must contain at least one letter or number")
    return CONFERENCE_ALIASES.get(key, key.upper())


def conference_slug(value: str) -> str:
    conference = canonical_conference(value)
    return CONFERENCE_SLUGS.get(conference, conference.casefold())


# Backward-compatible name for callers importing the old helper.
canonical_security_conference = canonical_conference


def find_repo_root(requested: Path | None = None) -> Path:
    candidates = [
        requested,
        Path(os.environ["LLM_CONFERENCE_SKILL_ROOT"]) if os.environ.get("LLM_CONFERENCE_SKILL_ROOT") else None,
        Path.cwd(),
        Path(__file__).resolve().parents[2],
        Path.home() / "llm_conference_skill",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        root = candidate.expanduser().resolve()
        if (root / "conference-grobid-extract-metadata/scripts/extract_paper_metadata.py").is_file() and (
            root / "conference-affiliation-normalizer/scripts/run_affilgood.py"
        ).is_file():
            return root
    raise RuntimeError("Cannot locate llm_conference_skill; pass --repo-root or set LLM_CONFERENCE_SKILL_ROOT")


def run(command: list[str], dry_run: bool, root: Path) -> None:
    print("$", " ".join(map(str, command)))
    if not dry_run:
        subprocess.run(command, cwd=root, check=True)


def choose_python(requested: str | None, root: Path) -> str:
    candidates = [requested] if requested else []
    candidates.extend([
        str(root / ".venv/bin/python"),
        str(root / "conference-affiliation-normalizer/affilgood-runtime/.venv/bin/python"),
        str(root / "conference-crawler/scripts/download/.venv/bin/python"),
        sys.executable,
    ])
    for candidate in candidates:
        if not candidate or not Path(candidate).exists():
            continue
        check = subprocess.run(
            [
                candidate,
                "-c",
                "import sys, pdfplumber, pypdf, bs4; raise SystemExit(sys.version_info < (3, 11))",
            ],
            capture_output=True,
        )
        if check.returncode == 0:
            return candidate
    raise RuntimeError(
        "Python 3.11+ with pdfplumber and pypdf is required; pass --python /path/to/python"
    )


def write_unresolved(source: Path, output: Path) -> int:
    with source.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = []
        for row in reader:
            status = (row.get("institution_reference_status") or "").strip()
            institution = (
                row.get("affilgood_standard_institutions")
                or row.get("affilgood_institutions")
                or ""
            ).strip()
            country = (row.get("affilgood_location_country") or "").strip()
            review_status = status in {"unmatched", "ambiguous", "conflict"}
            if review_status or not institution or not country:
                rows.append(row)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    return len(rows)


def affilgood_fields(payload: dict) -> dict[str, str]:
    countries: list[str] = []
    cities: list[str] = []
    institutions: list[str] = []
    standards: list[str] = []
    ror_ids: list[str] = []
    for output in payload.get("outputs") or []:
        location = output.get("location") or {}
        if location.get("country"):
            countries.append(str(location["country"]))
        if location.get("city"):
            cities.append(str(location["city"]))
        for institution in output.get("institutions") or []:
            name = institution.get("raw") or institution.get("name")
            standard = institution.get("name")
            identifier = institution.get("id") or {}
            if name:
                institutions.append(str(name))
            if standard:
                standards.append(str(standard))
            if identifier.get("ror_id"):
                ror_ids.append(str(identifier["ror_id"]))
    dedupe = lambda values: ";".join(dict.fromkeys(value for value in values if value))
    return {
        "affilgood_ror_ids": dedupe(ror_ids),
        "affilgood_institutions": dedupe(institutions),
        "affilgood_location_country": dedupe(countries),
        "affilgood_location_city": dedupe(cities),
        "affilgood_standard_institutions": dedupe(standards),
        "affilgood_standardization_source": "affilgood" if countries or institutions else "",
    }


def merge_affilgood(reference_csv: Path, normalized_jsonl: Path | None, output: Path) -> None:
    normalized: dict[str, dict[str, str]] = {}
    if normalized_jsonl and normalized_jsonl.exists():
        with normalized_jsonl.open(encoding="utf-8") as handle:
            for line in handle:
                item = json.loads(line)
                if item.get("status") == "ok":
                    normalized[str(item.get("record_id", ""))] = affilgood_fields(item.get("affilgood") or {})
    with reference_csv.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = []
        for row in reader:
            values = normalized.get(row.get("record_id", ""), {})
            for field in REFERENCE_FIELDS:
                if not (row.get(field) or "").strip() and values.get(field):
                    row[field] = values[field]
            if not (row.get("country") or "").strip() and (row.get("affilgood_location_country") or "").strip():
                row["country"] = row["affilgood_location_country"]
                row["country_source"] = row.get("country_source") or "affilgood"
                row["country_confidence"] = row.get("country_confidence") or "model"
            rows.append(row)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def verify_dataset(dataset: Path, *, allow_missing_authors: bool = False) -> dict:
    missing = [name for name in REQUIRED_DATASET_ENTRIES if not (dataset / name).exists()]
    if missing:
        raise RuntimeError(f"GROBID dataset is incomplete at {dataset}; missing: {', '.join(missing)}")
    with (dataset / "extraction_metrics.json").open(encoding="utf-8") as handle:
        metrics = json.load(handle)
    total = int(metrics.get("papers_total", 0))
    processed = int(metrics.get("papers_processed", 0))
    parse_errors = int(metrics.get("parse_errors", 0))
    if total != processed + parse_errors:
        raise RuntimeError("GROBID metrics are inconsistent: papers_total != papers_processed + parse_errors")
    if parse_errors or (int(metrics.get("papers_without_authors", 0)) and not allow_missing_authors):
        raise RuntimeError("GROBID quality gate failed; inspect extraction_metrics.json")
    return metrics


def validate_pdf_manifest(manifest: Path, pdf_dir: Path, conference: str, year: str) -> int:
    """Validate the reviewed crawler manifest before GROBID reads any PDFs."""
    if not manifest.is_file():
        raise FileNotFoundError(f"PDF manifest not found: {manifest}")
    if not pdf_dir.is_dir():
        raise FileNotFoundError(f"PDF directory not found: {pdf_dir}")

    expected_conference = conference_slug(conference)
    accepted: list[dict[str, str]] = []
    with manifest.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            row_conference = (row.get("conference") or "").strip()
            if not row_conference or conference_slug(row_conference) != expected_conference:
                continue
            if (row.get("year") or "").strip() != str(year):
                continue
            if (row.get("status") or "").strip() == "accepted":
                accepted.append(row)

    if not accepted:
        raise RuntimeError(f"PDF manifest has no accepted rows for {conference}/{year}")

    expected_names: set[str] = set()
    for row in accepted:
        name = (row.get("new_filename") or "").strip()
        digest = (row.get("sha256") or "").strip().lower()
        if not name or len(digest) != 64:
            raise RuntimeError(f"Invalid accepted manifest row: {row}")
        path = pdf_dir / name
        if not path.is_file():
            raise RuntimeError(f"Manifest PDF is missing: {path}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest:
            raise RuntimeError(f"PDF SHA-256 mismatch: {path} (manifest {digest}, actual {actual})")
        expected_names.add(name)

    actual_names = {path.name for path in pdf_dir.glob("*.pdf")}
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        extra = sorted(actual_names - expected_names)
        raise RuntimeError(f"PDF directory does not match manifest; missing={missing[:3]}, extra={extra[:3]}")
    return len(accepted)


def verify_final(path: Path) -> int:
    expected = [
        "paper_id", "year", "conference", "title", "author", "author_rank",
        "affiliation_rank", "affiliations", "emails", "first_author",
        "co_first_author", "corresponding", "equal_contribution", "country", "orcid",
    ]
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if list(reader.fieldnames or []) != expected:
            raise RuntimeError(f"final display CSV does not have the required 15 columns: {path}")
        return sum(1 for _ in reader)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conference")
    parser.add_argument("--year")
    parser.add_argument(
        "--batch",
        action="append",
        metavar="CONFERENCE:YEAR",
        help=(
            "Process multiple conference/year batches while loading AffilGood once. "
            "Repeat this option for each batch."
        ),
    )
    parser.add_argument("--repo-root", type=Path, help="llm_conference_skill repository root.")
    parser.add_argument("--pdf-dir", type=Path)
    parser.add_argument(
        "--pdf-manifest",
        type=Path,
        help="Reviewed crawler metadata/paper_manifest.csv; validates accepted PDF names and SHA-256.",
    )
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--python", help="Python 3.11+ interpreter for AffilGood.")
    parser.add_argument("--institution-table", type=Path, help="Reviewed institution_raw.csv override.")
    parser.add_argument(
        "--reuse-extraction",
        action="store_true",
        help="Reuse an existing PDF extraction dataset and continue with affiliation normalization.",
    )
    parser.add_argument("--skip-analysis", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--prepare-affilgood", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--finish-after-affilgood", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def csv_row_count(path: Path) -> int:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def parse_batch_spec(spec: str) -> tuple[str, str]:
    conference_text, separator, year = spec.rpartition(":")
    if not separator or not conference_text.strip() or not year.isdigit():
        raise ValueError(f"invalid batch {spec!r}; expected CONFERENCE:YEAR")
    return canonical_conference(conference_text), year


def append_common_args(command: list[str], args: argparse.Namespace, *, include_manifest: bool) -> None:
    if args.output_root:
        command.extend(["--output-root", str(args.output_root)])
    if args.python:
        command.extend(["--python", args.python])
    if args.institution_table:
        command.extend(["--institution-table", str(args.institution_table)])
    if include_manifest and args.pdf_manifest:
        command.extend(["--pdf-manifest", str(args.pdf_manifest)])
    if args.reuse_extraction:
        command.append("--reuse-extraction")
    if args.skip_analysis:
        command.append("--skip-analysis")
    if args.dry_run:
        command.append("--dry-run")


def run_batches(args: argparse.Namespace) -> int:
    if args.conference or args.year:
        raise ValueError("use either --batch or --conference/--year, not both")
    if args.pdf_dir:
        raise ValueError("--pdf-dir cannot be shared by multiple --batch values")
    if args.prepare_affilgood or args.finish_after_affilgood:
        raise ValueError("internal stage options cannot be combined with --batch")

    root = find_repo_root(args.repo_root)
    python = choose_python(args.python, root)
    output_root = (args.output_root or root / "generated-data").expanduser().resolve()
    batches = [parse_batch_spec(spec) for spec in args.batch]
    script = Path(__file__).resolve()

    for conference, year in batches:
        command = [python, str(script), "--repo-root", str(root), "--conference", conference,
                   "--year", year, "--prepare-affilgood"]
        append_common_args(command, args, include_manifest=True)
        run(command, args.dry_run, root)

    jobs: list[tuple[Path, Path]] = []
    for conference, year in batches:
        slug = conference_slug(conference)
        prefix = f"{slug}_{year}"
        directory = output_root / "extraction_affilgood" / slug / year
        unresolved = directory / f"{prefix}_affilgood_unresolved.csv"
        normalized = directory / f"{prefix}_affilgood_unresolved.jsonl"
        if args.dry_run or csv_row_count(unresolved):
            jobs.append((unresolved, normalized))

    if jobs:
        command = [python, str(root / "conference-affiliation-normalizer/scripts/run_affilgood.py"),
                   "--input-format", "csv", "--affiliation-field", "affiliations",
                   "--id-field", "record_id", "--output-format", "normalized",
                   "--no-institution-table"]
        for source, destination in jobs:
            command.extend(["--job", str(source), str(destination)])
        run(command, args.dry_run, root)

    for conference, year in batches:
        command = [python, str(script), "--repo-root", str(root), "--conference", conference,
                   "--year", year, "--finish-after-affilgood"]
        append_common_args(command, args, include_manifest=False)
        run(command, args.dry_run, root)
    return 0


def main() -> int:
    args = parse_args()
    if args.batch:
        return run_batches(args)
    if not args.conference or not args.year:
        raise ValueError("--conference and --year are required unless --batch is used")
    if args.prepare_affilgood and args.finish_after_affilgood:
        raise ValueError("preparation and finishing stages are mutually exclusive")
    root = find_repo_root(args.repo_root)
    grobid = root / "conference-grobid-extract-metadata" / "scripts"
    affil = root / "conference-affiliation-normalizer" / "scripts"
    output_root = (args.output_root or root / "generated-data").expanduser().resolve()
    python = choose_python(args.python, root)
    conference = canonical_conference(args.conference)
    slug = conference_slug(conference)
    prefix = f"{slug}_{args.year}"
    crawler_download = root / "conference-crawler" / "scripts" / "download"
    curated_pdf_dir = crawler_download / "curated" / slug / args.year / "accepted"
    pdf_dir = args.pdf_dir or (
        curated_pdf_dir if curated_pdf_dir.is_dir() else output_root / "pdf" / slug / args.year
    )
    pdf_manifest = args.pdf_manifest
    default_manifest = crawler_download / "metadata" / "paper_manifest.csv"
    if (
        not pdf_manifest
        and not args.reuse_extraction
        and pdf_dir.resolve() == curated_pdf_dir.resolve()
        and default_manifest.is_file()
    ):
        pdf_manifest = default_manifest
    dataset_root = output_root / "full_output" / slug / args.year
    dataset = dataset_root / f"author_metadata_dataset_{args.year}"
    raw_dir = output_root / "extraction_raw" / slug / args.year
    split_dir = output_root / "extraction_spilt" / slug / args.year
    affilgood_dir = output_root / "extraction_affilgood" / slug / args.year
    final_dir = output_root / "extraction_final" / slug / args.year
    raw = raw_dir / f"{prefix}_raw作者机构拆分.csv"
    split = split_dir / f"{prefix}_作者机构拆分_output.csv"
    institution_report = split_dir / f"{prefix}_institution_match_report.json"
    unresolved = affilgood_dir / f"{prefix}_affilgood_unresolved.csv"
    normalized = affilgood_dir / f"{prefix}_affilgood_unresolved.jsonl"
    affilgood_pre_reference = affilgood_dir / f"{prefix}_affilgood_pre_reference.csv"
    affilgood_csv = affilgood_dir / f"{prefix}_affilgood_作者机构拆分_output.csv"
    final_csv = final_dir / f"{prefix}_final.csv"
    requested_table = args.institution_table.expanduser().resolve() if args.institution_table else None
    generated_table = output_root / "institution_raw.csv"
    bundled_table = root / "conference-affiliation-normalizer" / "references" / "institution_raw.csv"
    institution_table = requested_table or (generated_table if generated_table.is_file() else bundled_table)
    if not args.dry_run and not institution_table.is_file():
        raise FileNotFoundError(f"institution_raw.csv not found: {institution_table}")
    if pdf_manifest and not args.dry_run:
        manifest_count = validate_pdf_manifest(
            pdf_manifest.expanduser().resolve(), pdf_dir.expanduser().resolve(), conference, args.year
        )
        dataset_root.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pdf_manifest.expanduser().resolve(), dataset_root / "source_pdf_manifest.csv")
        print(f"Reviewed PDF manifest verified: {manifest_count} PDFs; copied to {dataset_root / 'source_pdf_manifest.csv'}")

    if not args.finish_after_affilgood and not args.reuse_extraction:
        run([python, str(grobid / "extract_paper_metadata.py"), "--input-dir", str(pdf_dir),
             "--output-dir", str(dataset_root), "--dataset-name", dataset.name,
             "--conference", slug, "--year", args.year], args.dry_run, root)
        if not args.dry_run:
            verify_dataset(dataset, allow_missing_authors=True)
        # Official-web reconciliation is an optional registered enhancement.
        # Every other conference retains the GROBID PDF record as its primary
        # source and continues through the conference-neutral common stages.
        if conference in SECURITY_CONFERENCES:
            run([
                python,
                str(grobid / "reconcile_security_official_metadata.py"),
                "--dataset-dir", str(dataset),
                "--conference", slug,
                "--year", args.year,
                "--apply",
            ], args.dry_run, root)
        run([
            python,
            str(grobid / "enrich_pdf_author_roles.py"),
            "--dataset-dir", str(dataset),
            "--conference", slug,
            "--apply",
        ], args.dry_run, root)
        if not args.dry_run:
            verify_dataset(dataset)
    elif not args.finish_after_affilgood and not args.dry_run:
        verify_dataset(dataset)

    if not args.finish_after_affilgood:
        run([python, str(grobid / "split_affiliations_raw.py"), "--input", str(dataset / "paper_metadata.csv"),
             "--output", str(raw)], args.dry_run, root)
        run([python, str(affil / "match_institution_reference_csv.py"), "--input", str(raw),
             "--output", str(split), "--institution-table", str(institution_table),
             "--report", str(institution_report), "--prepare-only"], args.dry_run, root)
        unresolved_count = None if args.dry_run else write_unresolved(split, unresolved)
        if args.prepare_affilgood:
            return 0
    else:
        unresolved_count = None if args.dry_run else csv_row_count(unresolved)
        if unresolved_count and not normalized.is_file():
            raise FileNotFoundError(f"AffilGood output not found: {normalized}")

    if not args.finish_after_affilgood and (args.dry_run or unresolved_count):
        run([python, str(affil / "run_affilgood.py"), "--job", str(unresolved), str(normalized),
             "--input-format", "csv", "--affiliation-field", "affiliations",
             "--id-field", "record_id", "--output-format", "normalized",
             "--no-institution-table"], args.dry_run, root)
    if not args.dry_run:
        merge_affilgood(split, normalized if unresolved_count else None, affilgood_pre_reference)
    run([python, str(affil / "match_institution_reference_csv.py"),
         "--input", str(affilgood_pre_reference), "--output", str(affilgood_csv),
         "--institution-table", str(institution_table), "--report", str(institution_report)],
        args.dry_run, root)
    if not args.dry_run:
        with institution_report.open(encoding="utf-8") as handle:
            match_report = json.load(handle)
        print(f"Institution reference table: {match_report['institution_table']}")
        if match_report.get("review_required", 0):
            raise RuntimeError(
                f"Institution automation left {match_report['review_required']} rows requiring review; "
                f"inspect {institution_report}"
            )
        if match_report.get("blank_country_actionable", 0):
            raise RuntimeError(
                f"Institution automation left {match_report['blank_country_actionable']} actionable blank countries; "
                f"inspect {institution_report}"
            )
        for warning in match_report.get("warnings", []):
            print(f"WARNING: {warning}")
    run([python, str(affil / "generate_final_view.py"), "--input", str(affilgood_csv),
         "--conference", slug, "--year", args.year, "--output", str(final_csv)], args.dry_run, root)
    if not args.dry_run:
        rows = verify_final(final_csv)
        print(f"Final display table verified: {final_csv} ({rows} rows)")

    analysis = root / "conference-analysis-automation/scripts/run_analysis_pipeline.py"
    if not args.skip_analysis and analysis.exists():
        run([python, str(analysis), "--affilgood-input", str(affilgood_csv), "--output-dir",
             str(output_root / "analysis" / slug / args.year)], args.dry_run, root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
