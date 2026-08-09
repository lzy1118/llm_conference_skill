#!/usr/bin/env python3
"""Migrate the reviewed 2026-08-01 security batch into the per-year contract."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path


CONFERENCES = {
    "CCS": "ccs",
    "IEEE_S&P": "ieee_s&p",
    "NDSS": "ndss",
    "USENIX_SECURITY": "usenix_security",
}
YEARS = tuple(str(year) for year in range(2020, 2026))


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scoped_rows(rows: list[dict[str, str]], conference: str, year: str) -> list[dict[str, str]]:
    return [
        row for row in rows
        if (row.get("conference") or "").strip().casefold() == conference.casefold()
        and (row.get("year") or "").strip() == year
    ]


def run(command: list[str], root: Path) -> None:
    print("$", " ".join(command))
    subprocess.run(command, cwd=root, check=True)


def remove_legacy_flat_outputs(generated: Path) -> int:
    removed = 0
    for slug in CONFERENCES.values():
        for year in YEARS:
            prefix = f"{slug}_{year}"
            paths = (
                generated / "extraction_raw" / f"{prefix}_raw作者机构拆分.csv",
                generated / "extraction_spilt" / f"{prefix}_作者机构拆分_output.csv",
                generated / "extraction_spilt" / f"{prefix}_institution_match_report.json",
                generated / "extraction_affilgood" / f"{prefix}_affilgood_pre_reference.csv",
                generated / "extraction_affilgood" / f"{prefix}_affilgood_作者机构拆分_output.csv",
                generated / "extraction_final" / f"{prefix}_final.csv",
            )
            for path in paths:
                if path.is_file():
                    path.unlink()
                    removed += 1
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()

    root = args.repo_root.resolve()
    generated = root / "generated-data"
    legacy = generated / "security_country_update_20260801"
    manifest_path = root / "conference-crawler/scripts/download/metadata/paper_manifest.csv"
    institution_table = generated / "institution_raw.csv"
    matcher = root / "conference-affiliation-normalizer/scripts/match_institution_reference_csv.py"
    final_generator = root / "conference-affiliation-normalizer/scripts/generate_final_view.py"

    manifest_fields, manifest_rows = read_csv(manifest_path)
    report: dict[str, object] = {
        "source_batch": str(legacy),
        "source_manifest": str(manifest_path),
        "source_manifest_sha256": sha256(manifest_path),
        "institution_table": str(institution_table),
        "institution_table_sha256": sha256(institution_table),
        "batches": [],
    }

    uppercase_ccs = generated / "full_output/CCS"
    lowercase_ccs = generated / "full_output/ccs"
    if uppercase_ccs.exists() and lowercase_ccs.exists():
        if not uppercase_ccs.samefile(lowercase_ccs):
            raise RuntimeError("Both full_output/CCS and full_output/ccs exist; refusing ambiguous migration")
        temporary_ccs = generated / "full_output/__ccs_case_migration__"
        uppercase_ccs.rename(temporary_ccs)
        temporary_ccs.rename(lowercase_ccs)
    elif uppercase_ccs.exists():
        uppercase_ccs.rename(lowercase_ccs)

    for display, slug in CONFERENCES.items():
        raw_fields, raw_rows = read_csv(legacy / "raw" / f"{display}_2020_2025_raw作者机构拆分.csv")
        split_fields, split_rows = read_csv(legacy / "prepared" / f"{display}_2020_2025_prepared.csv")
        pre_fields, pre_rows = read_csv(legacy / "affilgood" / f"{display}_2020_2025_enriched_pre_reference.csv")

        for year in YEARS:
            batch_manifest = scoped_rows(manifest_rows, slug, year)
            if not batch_manifest or any(row.get("status") != "accepted" for row in batch_manifest):
                raise RuntimeError(f"Manifest scope is not fully accepted: {slug}/{year}")

            dataset_root = generated / "full_output" / slug / year
            dataset = dataset_root / f"author_metadata_dataset_{year}"
            if not (dataset / "paper_metadata.csv").is_file():
                raise FileNotFoundError(f"Missing GROBID dataset: {dataset}")
            write_csv(dataset_root / "source_pdf_manifest.csv", manifest_fields, batch_manifest)

            year_raw = scoped_rows(raw_rows, display, year)
            year_split = scoped_rows(split_rows, display, year)
            year_pre = scoped_rows(pre_rows, display, year)
            raw_dir = generated / "extraction_raw" / slug / year
            split_dir = generated / "extraction_spilt" / slug / year
            affilgood_dir = generated / "extraction_affilgood" / slug / year
            final_dir = generated / "extraction_final" / slug / year
            raw_output = raw_dir / f"{slug}_{year}_raw作者机构拆分.csv"
            split_output = split_dir / f"{slug}_{year}_作者机构拆分_output.csv"
            pre_output = affilgood_dir / f"{slug}_{year}_affilgood_pre_reference.csv"
            affilgood_output = affilgood_dir / f"{slug}_{year}_affilgood_作者机构拆分_output.csv"
            match_report = split_dir / f"{slug}_{year}_institution_match_report.json"
            final_output = final_dir / f"{slug}_{year}_final.csv"

            write_csv(raw_output, raw_fields, year_raw)
            write_csv(split_output, split_fields, year_split)
            write_csv(pre_output, pre_fields, year_pre)
            run([
                args.python, str(matcher), "--input", str(pre_output), "--output", str(affilgood_output),
                "--institution-table", str(institution_table), "--report", str(match_report),
            ], root)
            match_metrics = json.loads(match_report.read_text(encoding="utf-8"))
            if match_metrics.get("review_required", 0):
                raise RuntimeError(
                    f"Institution automation left review rows for {slug}/{year}: "
                    f"{match_metrics['review_required']}"
                )
            if match_metrics.get("blank_country_actionable", 0):
                raise RuntimeError(
                    f"Institution automation left actionable blank countries for {slug}/{year}: "
                    f"{match_metrics['blank_country_actionable']}"
                )
            run([
                args.python, str(final_generator), "--input", str(affilgood_output),
                "--conference", display, "--year", year, "--output", str(final_output),
            ], root)

            _, final_rows = read_csv(final_output)
            paper_ids = {row.get("paper_id", "") for row in year_raw if row.get("paper_id")}
            if len(paper_ids) != len(batch_manifest):
                raise RuntimeError(
                    f"Paper count mismatch for {slug}/{year}: raw={len(paper_ids)}, manifest={len(batch_manifest)}"
                )
            batch_report = {
                "conference": slug,
                "year": year,
                "papers": len(paper_ids),
                "manifest_rows": len(batch_manifest),
                "raw_rows": len(year_raw),
                "split_rows": len(year_split),
                "affilgood_rows": len(year_pre),
                "final_rows": len(final_rows),
                "final_blank_orcid": sum(not row.get("orcid", "").strip() for row in final_rows),
                "final_blank_country": sum(not row.get("country", "").strip() for row in final_rows),
                "blank_country_not_applicable": match_metrics["blank_country_not_applicable"],
                "blank_country_actionable": match_metrics["blank_country_actionable"],
                "institution_review_required": match_metrics["review_required"],
                "institution_resolution_statuses": {
                    key: value for key, value in match_metrics.items()
                    if key in {
                        "affilgood_resolved", "matched", "resolved_reviewed_rule",
                        "resolved_unique_identity", "resolved_atomic_composite",
                        "not_applicable_noninstitutional", "unknown_organization",
                    }
                },
                "role_values": {
                    field: dict(Counter(row.get(field, "") for row in final_rows))
                    for field in ("co_first_author", "equal_contribution")
                },
            }
            report["batches"].append(batch_report)

    report["totals"] = {
        key: sum(int(batch[key]) for batch in report["batches"])
        for key in ("papers", "manifest_rows", "raw_rows", "split_rows", "affilgood_rows", "final_rows")
    }
    report["quality_totals"] = {
        key: sum(int(batch[key]) for batch in report["batches"])
        for key in (
            "final_blank_country", "blank_country_not_applicable",
            "blank_country_actionable", "institution_review_required",
        )
    }
    report["output_layout"] = "generated-data/<stage>/<conference>/<year>/<conference>_<year>_<artifact>"
    report["legacy_flat_files_removed"] = remove_legacy_flat_outputs(generated)
    report_path = generated / "migration_security_20260801_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Migration complete: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
