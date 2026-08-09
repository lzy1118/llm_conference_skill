from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_pipeline.py"
SPEC = importlib.util.spec_from_file_location("security_research_run_pipeline", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(module)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class RunPipelineTests(unittest.TestCase):
    def test_default_python_has_pdf_evidence_dependencies(self) -> None:
        selected = module.choose_python(None, SCRIPT.parents[2])
        completed = subprocess.run(
            [selected, "-c", "import pdfplumber, pypdf, bs4"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_seven_conferences_are_accepted(self) -> None:
        self.assertEqual(module.canonical_conference("ASIACRYPT"), "ASIACRYPT")
        self.assertEqual(module.canonical_conference("CRYPTO"), "CRYPTO")
        self.assertEqual(module.canonical_conference("EUROCRYPT"), "EUROCRYPT")
        self.assertEqual(module.canonical_conference("CCS"), "CCS")
        self.assertEqual(module.canonical_conference("IEEE S&P"), "IEEE_S&P")
        self.assertEqual(module.canonical_conference("NDSS"), "NDSS")
        self.assertEqual(module.canonical_conference("USENIX Security"), "USENIX_SECURITY")
        with self.assertRaises(ValueError):
            module.canonical_conference("UNKNOWN")
        self.assertEqual(module.conference_slug("CRYPTO"), "crypto")
        self.assertEqual(module.conference_slug("IEEE S&P"), "ieee_s&p")

    def test_dry_run_orders_pdf_web_roles_and_downstream_stages(self) -> None:
        completed = subprocess.run([
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(SCRIPT.parents[2]),
            "--conference",
            "CCS",
            "--year",
            "2025",
            "--python",
            sys.executable,
            "--dry-run",
            "--skip-analysis",
        ], capture_output=True, text=True)

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        extraction = completed.stdout.index("extract_paper_metadata.py")
        official = completed.stdout.index("reconcile_security_official_metadata.py")
        roles = completed.stdout.index("enrich_pdf_author_roles.py")
        self.assertLess(extraction, official)
        self.assertLess(official, roles)
        self.assertIn("split_affiliations_raw.py", completed.stdout)
        self.assertIn("extraction_final/ccs/2025/ccs_2025_final.csv", completed.stdout)
        self.assertNotIn("--official-authoritative", completed.stdout)
        self.assertNotIn("--require-complete-affiliations", completed.stdout)
        self.assertNotIn("--require-all-papers-matched", completed.stdout)

    def test_lncs_dry_run_uses_common_pipeline_without_security_web_reconciliation(self) -> None:
        completed = subprocess.run([
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(SCRIPT.parents[2]),
            "--conference",
            "CRYPTO",
            "--year",
            "2025",
            "--python",
            sys.executable,
            "--dry-run",
            "--skip-analysis",
        ], capture_output=True, text=True)

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("extract_paper_metadata.py", completed.stdout)
        self.assertIn("--conference crypto", completed.stdout)
        self.assertIn("conference-crawler/scripts/download/curated/crypto/2025/accepted", completed.stdout)
        self.assertIn("enrich_pdf_author_roles.py", completed.stdout)
        self.assertIn("split_affiliations_raw.py", completed.stdout)
        self.assertIn("extraction_final/crypto/2025/crypto_2025_final.csv", completed.stdout)
        self.assertNotIn("reconcile_security_official_metadata.py", completed.stdout)

    def test_batch_dry_run_shares_one_affilgood_invocation(self) -> None:
        completed = subprocess.run([
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(SCRIPT.parents[2]),
            "--batch",
            "CRYPTO:2024",
            "--batch",
            "EUROCRYPT:2025",
            "--python",
            sys.executable,
            "--dry-run",
            "--skip-analysis",
        ], capture_output=True, text=True)

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        affilgood_commands = [
            line for line in completed.stdout.splitlines()
            if "conference-affiliation-normalizer/scripts/run_affilgood.py" in line
        ]
        self.assertEqual(len(affilgood_commands), 1)
        self.assertIn("crypto_2024_affilgood_unresolved.csv", affilgood_commands[0])
        self.assertIn("eurocrypt_2025_affilgood_unresolved.csv", affilgood_commands[0])
        self.assertEqual(affilgood_commands[0].count("--job"), 2)
        self.assertEqual(completed.stdout.count("--prepare-affilgood"), 2)
        self.assertEqual(completed.stdout.count("--finish-after-affilgood"), 2)

    def test_affilgood_fields_reads_nested_normalized_payload(self) -> None:
        values = module.affilgood_fields({"outputs": [{
            "location": {"country": "United States", "city": "Boston"},
            "institutions": [{"name": "Example University", "id": {"ror_id": "https://ror.org/example"}}],
        }]})
        self.assertEqual(values["affilgood_location_country"], "United States")
        self.assertEqual(values["affilgood_ror_ids"], "https://ror.org/example")

    def test_validate_pdf_manifest_checks_names_and_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_dir = root / "accepted"
            pdf_dir.mkdir()
            pdf = pdf_dir / "CRYPTO_2025_p0001.pdf"
            pdf.write_bytes(b"pdf-fixture")
            digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
            manifest = root / "paper_manifest.csv"
            write_csv(manifest, ["conference", "year", "status", "new_filename", "sha256"], [{
                "conference": "crypto", "year": "2025", "status": "accepted",
                "new_filename": pdf.name, "sha256": digest,
            }])
            self.assertEqual(module.validate_pdf_manifest(manifest, pdf_dir, "CRYPTO", "2025"), 1)
            pdf.write_bytes(b"changed")
            with self.assertRaises(RuntimeError):
                module.validate_pdf_manifest(manifest, pdf_dir, "CRYPTO", "2025")

    def test_unresolved_and_merge_fill_only_blank_reference_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "reference.csv"
            unresolved = root / "unresolved.csv"
            normalized = root / "normalized.jsonl"
            output = root / "merged.csv"
            fields = ["record_id", "affiliations", *module.REFERENCE_FIELDS]
            write_csv(source, fields, [
                {"record_id": "known", "affiliations": "Known", "affilgood_location_country": "China", "affilgood_institutions": "Reviewed"},
                {"record_id": "missing", "affiliations": "Unknown"},
            ])
            self.assertEqual(module.write_unresolved(source, unresolved), 1)
            with unresolved.open(encoding="utf-8-sig", newline="") as handle:
                self.assertEqual([row["record_id"] for row in csv.DictReader(handle)], ["missing"])
            payload = {"record_id": "missing", "status": "ok", "affilgood": {"outputs": [{
                "location": {"country": "United States"},
                "institutions": [{"name": "Detected", "id": {"ror_id": "ror-x"}}],
            }]}}
            normalized.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            module.merge_affilgood(source, normalized, output)
            with output.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["affilgood_location_country"], "China")
            self.assertEqual(rows[0]["affilgood_institutions"], "Reviewed")
            self.assertEqual(rows[1]["affilgood_location_country"], "United States")

    def test_explicit_country_does_not_skip_unmatched_institution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "reference.csv"
            unresolved = root / "unresolved.csv"
            fields = [
                "record_id", "affiliations", "country", "country_source",
                "institution_reference_status", *module.REFERENCE_FIELDS,
            ]
            write_csv(source, fields, [{
                "record_id": "row-alpha",
                "affiliations": "Unknown Organization, Region Alpha",
                "country": "Region Alpha",
                "country_source": "pdf_explicit",
                "affilgood_location_country": "Region Alpha",
                "institution_reference_status": "unmatched",
            }])

            self.assertEqual(module.write_unresolved(source, unresolved), 1)

    def test_verify_dataset_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp)
            for name in module.REQUIRED_DATASET_ENTRIES:
                path = dataset / name
                if "." in name:
                    path.write_text("", encoding="utf-8")
                else:
                    path.mkdir()
            (dataset / "extraction_metrics.json").write_text(json.dumps({
                "papers_total": 2, "papers_processed": 2, "parse_errors": 0,
                "papers_without_authors": 0,
            }), encoding="utf-8")
            self.assertEqual(module.verify_dataset(dataset)["papers_total"], 2)

            metrics = json.loads((dataset / "extraction_metrics.json").read_text(encoding="utf-8"))
            metrics["papers_without_authors"] = 1
            (dataset / "extraction_metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
            self.assertEqual(module.verify_dataset(dataset, allow_missing_authors=True)["papers_total"], 2)
            with self.assertRaises(RuntimeError):
                module.verify_dataset(dataset)

    @unittest.skipUnless(
        os.environ.get("RUN_AFFILGOOD_INTEGRATION") == "1",
        "set RUN_AFFILGOOD_INTEGRATION=1 when AffilGood models are installed",
    )
    def test_resume_pipeline_smoke_with_exact_reference_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp)
            dataset = output_root / "full_output" / "ccs" / "2025" / "author_metadata_dataset_2025"
            dataset.mkdir(parents=True)
            for name in module.REQUIRED_DATASET_ENTRIES:
                path = dataset / name
                if "." not in name:
                    path.mkdir()
            write_csv(dataset / "paper_metadata.csv", [
                "paper_id", "year", "conference", "title", "author", "author_rank",
                "affiliations", "emails", "first_author", "co_first_author",
                "corresponding", "equal_contribution",
            ], [{
                "paper_id": "p1", "year": "2025", "conference": "CCS", "title": "Fixture",
                "author": "A. Author", "author_rank": "0", "affiliations": "Aalto University",
                "first_author": "true", "corresponding": "false", "equal_contribution": "false",
            }])
            write_csv(dataset / "paper_index.csv", ["paper_id"], [{"paper_id": "p1"}])
            write_csv(dataset / "skipped_files.csv", ["filename"], [])
            write_csv(
                dataset / "conference_year_paper_abstract.csv",
                ["conference", "year", "title", "abstract"],
                [{"conference": "CCS", "year": "2025", "title": "Fixture", "abstract": "Abstract."}],
            )
            write_csv(
                dataset / "review_queue.csv",
                ["paper_id", "source_file", "code", "field", "author", "stage", "details"],
                [],
            )
            (dataset / "extraction_metrics.json").write_text(json.dumps({
                "papers_total": 1, "papers_processed": 1, "parse_errors": 0,
                "papers_without_authors": 0,
            }), encoding="utf-8")

            completed = subprocess.run([
                sys.executable, str(SCRIPT), "--conference", "CCS", "--year", "2025",
                "--output-root", str(output_root), "--python", sys.executable,
                "--reuse-extraction", "--skip-analysis",
            ], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            final_csv = output_root / "extraction_final" / "ccs" / "2025" / "ccs_2025_final.csv"
            with final_csv.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["country"], "Finland")
            self.assertEqual(list(rows[0]), [
                "paper_id", "year", "conference", "title", "author", "author_rank",
                "affiliation_rank", "affiliations", "emails", "first_author",
                "co_first_author", "corresponding", "equal_contribution", "country", "orcid",
            ])


if __name__ == "__main__":
    unittest.main()
