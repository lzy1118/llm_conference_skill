import csv
import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]


def write_normalized_input(path: Path) -> None:
    rows = [
        {
            "row_key": "p1-0-mit",
            "paper_key": "p1",
            "conference": "CCS",
            "year": "2023",
            "title": "Paper One",
            "article_tag": "CCS-Paper One",
            "paper_id": "1",
            "name": "Alice",
            "author_key": "alice",
            "author_order": "0",
            "inst": "MIT",
            "institution_key": "mit",
            "country": "United States",
            "is_us_institution": "True",
            "classification_source": "rule",
            "classification_confidence": "1.0",
            "classification_reason": "test",
        },
        {
            "row_key": "p1-1-eth",
            "paper_key": "p1",
            "conference": "CCS",
            "year": "2023",
            "title": "Paper One",
            "article_tag": "CCS-Paper One",
            "paper_id": "1",
            "name": "Bob",
            "author_key": "bob",
            "author_order": "1",
            "inst": "ETH Zurich",
            "institution_key": "eth-zurich",
            "country": "Switzerland",
            "is_us_institution": "False",
            "classification_source": "rule",
            "classification_confidence": "1.0",
            "classification_reason": "test",
        },
        {
            "row_key": "p2-0-mit",
            "paper_key": "p2",
            "conference": "CCS",
            "year": "2024",
            "title": "Paper Two",
            "article_tag": "CCS-Paper Two",
            "paper_id": "2",
            "name": "Alice",
            "author_key": "alice",
            "author_order": "0",
            "inst": "MIT",
            "institution_key": "mit",
            "country": "United States",
            "is_us_institution": "True",
            "classification_source": "rule",
            "classification_confidence": "1.0",
            "classification_reason": "test",
        },
        {
            "row_key": "p2-1-stanford",
            "paper_key": "p2",
            "conference": "CCS",
            "year": "2024",
            "title": "Paper Two",
            "article_tag": "CCS-Paper Two",
            "paper_id": "2",
            "name": "Carol",
            "author_key": "carol",
            "author_order": "1",
            "inst": "Stanford University",
            "institution_key": "stanford",
            "country": "United States",
            "is_us_institution": "True",
            "classification_source": "rule",
            "classification_confidence": "1.0",
            "classification_reason": "test",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


class AnalysisSkillsTests(unittest.TestCase):
    def test_normalization_preserves_extraction_country_without_resplitting(self):
        with TemporaryDirectory() as directory:
            tmp = Path(directory)
            raw_input = tmp / "expanded.csv"
            output_dir = tmp / "normalized-out"
            rows = [
                {
                    "conference": "USENIX_SECURITY",
                    "year": "2022",
                    "paper_id": "p1",
                    "title": "Paper One",
                    "name": "Alice",
                    "article_tag": "tag-1",
                    "author_order": "0",
                    "inst": "Johns Hopkins University/Renmin University of China",
                    "country": "Multiple",
                    "is_us_institution": "False",
                    "classification_source": "rule",
                    "classification_confidence": "0.95",
                    "classification_reason": "multiple_countries",
                }
            ]
            with raw_input.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)

            result = subprocess.run(
                [
                    "python3",
                    "conference-dataset-normalization/scripts/normalize_dataset.py",
                    str(raw_input),
                    "--output-dir",
                    str(output_dir),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            normalized_path = output_dir / "normalized" / "author_affiliation_facts.csv"
            with normalized_path.open(encoding="utf-8", newline="") as handle:
                normalized_rows = list(csv.DictReader(handle))

            self.assertEqual(len(normalized_rows), 1)
            self.assertEqual(normalized_rows[0]["inst"], "Johns Hopkins University/Renmin University of China")
            self.assertEqual(normalized_rows[0]["country"], "Multiple")
            self.assertNotIn("is_us_institution", normalized_rows[0])

    def test_normalization_recovers_conference_and_title_from_article_tag(self):
        with TemporaryDirectory() as directory:
            tmp = Path(directory)
            raw_input = tmp / "author_affiliations.csv"
            output_dir = tmp / "normalized-out"
            rows = [
                {
                    "year": "2025",
                    "article_tag": "ASIACRYPT-Haystack ciphers",
                    "author_order": "0",
                    "name": "Alice",
                    "inst": "University of Luxembourg",
                    "country": "Luxembourg",
                },
                {
                    "year": "2025",
                    "article_tag": "ASIACRYPT-Haystack ciphers",
                    "author_order": "1",
                    "name": "Bob",
                    "inst": "University of Luxembourg",
                    "country": "Luxembourg",
                },
                {
                    "year": "2025",
                    "article_tag": "CRYPTO-Another paper",
                    "author_order": "0",
                    "name": "Carol",
                    "inst": "MIT",
                    "country": "United States",
                },
            ]
            with raw_input.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)

            result = subprocess.run(
                [
                    "python3",
                    "conference-dataset-normalization/scripts/normalize_dataset.py",
                    str(raw_input),
                    "--output-dir",
                    str(output_dir),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)

            with (output_dir / "normalized" / "paper_facts.csv").open(encoding="utf-8", newline="") as handle:
                paper_rows = list(csv.DictReader(handle))
            with (output_dir / "normalized" / "author_affiliation_facts.csv").open(encoding="utf-8", newline="") as handle:
                normalized_rows = list(csv.DictReader(handle))

            self.assertEqual(len(paper_rows), 2)
            self.assertEqual([row["conference"] for row in paper_rows], ["ASIACRYPT", "CRYPTO"])
            self.assertEqual([row["title"] for row in paper_rows], ["Haystack ciphers", "Another paper"])
            self.assertEqual(normalized_rows[0]["conference"], "ASIACRYPT")
            self.assertEqual(normalized_rows[0]["title"], "Haystack ciphers")

    def test_automation_pipeline_runs_from_normalized_input(self):
        with TemporaryDirectory() as directory:
            tmp = Path(directory)
            normalized_input = tmp / "author_affiliation_facts.csv"
            output_dir = tmp / "analysis"
            write_normalized_input(normalized_input)

            result = subprocess.run(
                [
                    "python3",
                    "conference-analysis-automation/scripts/run_analysis_pipeline.py",
                    "--normalized-input",
                    str(normalized_input),
                    "--output-dir",
                    str(output_dir),
                    "--conference",
                    "CCS",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((output_dir / "country" / "country_summary.csv").exists())
            self.assertTrue((output_dir / "institutions" / "institution_summary.csv").exists())
            self.assertTrue((output_dir / "authors" / "author_summary.csv").exists())
            self.assertTrue((output_dir / "trends" / "trend_summary.csv").exists())
            self.assertTrue((output_dir / "collaboration" / "collaboration_edges.csv").exists())
            self.assertTrue((output_dir / "audit" / "normalized" / "quality_audit.json").exists())
            self.assertTrue((output_dir / "audit" / "analysis" / "quality_audit.json").exists())
            self.assertTrue((output_dir / "reports" / "conference_report.md").exists())
            self.assertTrue((output_dir / "visualizations" / "visualization_manifest.json").exists())
            manifest = json.loads((output_dir / "automation_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["scope"]["conference"], "CCS")
            self.assertEqual(
                [step["step"] for step in manifest["steps"]],
                ["audit-normalized", "country", "institution", "author", "trend", "collaboration", "audit-analysis", "report", "visualization"],
            )

    def test_automation_pipeline_runs_trend_and_collaboration(self):
        with TemporaryDirectory() as directory:
            tmp = Path(directory)
            normalized_input = tmp / "author_affiliation_facts.csv"
            output_dir = tmp / "analysis"
            write_normalized_input(normalized_input)

            result = subprocess.run(
                [
                    "python3",
                    "conference-analysis-automation/scripts/run_analysis_pipeline.py",
                    "--normalized-input",
                    str(normalized_input),
                    "--output-dir",
                    str(output_dir),
                    "--conference",
                    "CCS",
                    "--run",
                    "trend",
                    "--run",
                    "collaboration",
                    "--trend-entity",
                    "country",
                    "--collaboration-mode",
                    "author",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((output_dir / "trends" / "trend_summary.csv").exists())
            self.assertTrue((output_dir / "collaboration" / "collaboration_edges.csv").exists())
            manifest = json.loads((output_dir / "automation_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["scope"]["trend_entity"], "country")
            self.assertEqual(manifest["scope"]["collaboration_mode"], "author")
            self.assertEqual([step["step"] for step in manifest["steps"]], ["trend", "collaboration"])

    def test_automation_pipeline_runs_audit_only(self):
        with TemporaryDirectory() as directory:
            tmp = Path(directory)
            normalized_input = tmp / "author_affiliation_facts.csv"
            output_dir = tmp / "analysis"
            write_normalized_input(normalized_input)

            result = subprocess.run(
                [
                    "python3",
                    "conference-analysis-automation/scripts/run_analysis_pipeline.py",
                    "--normalized-input",
                    str(normalized_input),
                    "--output-dir",
                    str(output_dir),
                    "--run",
                    "audit",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((output_dir / "audit" / "normalized" / "quality_audit.json").exists())
            self.assertTrue((output_dir / "audit" / "analysis" / "quality_audit.json").exists())
            manifest = json.loads((output_dir / "automation_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual([step["step"] for step in manifest["steps"]], ["audit-normalized", "audit-analysis"])

    def test_automation_pipeline_runs_report_after_analytics(self):
        with TemporaryDirectory() as directory:
            tmp = Path(directory)
            normalized_input = tmp / "author_affiliation_facts.csv"
            output_dir = tmp / "analysis"
            write_normalized_input(normalized_input)

            result = subprocess.run(
                [
                    "python3",
                    "conference-analysis-automation/scripts/run_analysis_pipeline.py",
                    "--normalized-input",
                    str(normalized_input),
                    "--output-dir",
                    str(output_dir),
                    "--run",
                    "country",
                    "--run",
                    "report",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((output_dir / "reports" / "conference_report.md").exists())
            manifest = json.loads((output_dir / "automation_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual([step["step"] for step in manifest["steps"]], ["country", "report"])

    def test_automation_pipeline_runs_visualization_after_analytics(self):
        with TemporaryDirectory() as directory:
            tmp = Path(directory)
            normalized_input = tmp / "author_affiliation_facts.csv"
            output_dir = tmp / "analysis"
            write_normalized_input(normalized_input)

            result = subprocess.run(
                [
                    "python3",
                    "conference-analysis-automation/scripts/run_analysis_pipeline.py",
                    "--normalized-input",
                    str(normalized_input),
                    "--output-dir",
                    str(output_dir),
                    "--run",
                    "country",
                    "--run",
                    "visualization",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((output_dir / "visualizations" / "country_top_papers.svg").exists())
            manifest = json.loads((output_dir / "automation_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual([step["step"] for step in manifest["steps"]], ["country", "visualization"])

    def test_trend_analysis_generates_year_deltas(self):
        with TemporaryDirectory() as directory:
            tmp = Path(directory)
            normalized_input = tmp / "author_affiliation_facts.csv"
            output_dir = tmp / "analysis"
            write_normalized_input(normalized_input)

            result = subprocess.run(
                [
                    "python3",
                    "conference-trend-analysis/scripts/trend_analysis.py",
                    "--input",
                    str(normalized_input),
                    "--output-dir",
                    str(output_dir),
                    "--entity",
                    "country",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            summary_path = output_dir / "trends" / "trend_summary.csv"
            self.assertTrue(summary_path.exists())
            with summary_path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            us_row = next(row for row in rows if row["entity_name"] == "United States")
            self.assertEqual(us_row["papers_peak"], "1")
            self.assertEqual(us_row["year_first"], "2023")

    def test_collaboration_analysis_generates_repeated_author_edges(self):
        with TemporaryDirectory() as directory:
            tmp = Path(directory)
            normalized_input = tmp / "author_affiliation_facts.csv"
            output_dir = tmp / "analysis"
            write_normalized_input(normalized_input)

            extra_rows = [
                {
                    "row_key": "p3-0-alice",
                    "paper_key": "p3",
                    "conference": "CCS",
                    "year": "2024",
                    "title": "Paper Three",
                    "article_tag": "CCS-Paper Three",
                    "paper_id": "3",
                    "name": "Alice",
                    "author_key": "alice",
                    "author_order": "0",
                    "inst": "MIT",
                    "institution_key": "mit",
                    "country": "United States",
                    "is_us_institution": "True",
                    "classification_source": "rule",
                    "classification_confidence": "1.0",
                    "classification_reason": "test",
                },
                {
                    "row_key": "p3-1-bob",
                    "paper_key": "p3",
                    "conference": "CCS",
                    "year": "2024",
                    "title": "Paper Three",
                    "article_tag": "CCS-Paper Three",
                    "paper_id": "3",
                    "name": "Bob",
                    "author_key": "bob",
                    "author_order": "1",
                    "inst": "ETH Zurich",
                    "institution_key": "eth-zurich",
                    "country": "Switzerland",
                    "is_us_institution": "False",
                    "classification_source": "rule",
                    "classification_confidence": "1.0",
                    "classification_reason": "test",
                },
            ]
            write_normalized_input(normalized_input)
            with normalized_input.open("a", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(extra_rows[0].keys()))
                writer.writerows(extra_rows)

            result = subprocess.run(
                [
                    "python3",
                    "conference-collaboration-analysis/scripts/collaboration_analysis.py",
                    "--input",
                    str(normalized_input),
                    "--output-dir",
                    str(output_dir),
                    "--mode",
                    "author",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            edges_path = output_dir / "collaboration" / "collaboration_edges.csv"
            self.assertTrue(edges_path.exists())
            with edges_path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            alice_bob = next(row for row in rows if row["left_key"] == "alice" and row["right_key"] == "bob")
            self.assertEqual(alice_bob["shared_papers"], "2")

    def test_report_generation_uses_existing_outputs(self):
        with TemporaryDirectory() as directory:
            tmp = Path(directory)
            normalized_input = tmp / "author_affiliation_facts.csv"
            analysis_dir = tmp / "analysis"
            report_dir = tmp / "reports"
            write_normalized_input(normalized_input)

            pipeline_result = subprocess.run(
                [
                    "python3",
                    "conference-analysis-automation/scripts/run_analysis_pipeline.py",
                    "--normalized-input",
                    str(normalized_input),
                    "--output-dir",
                    str(analysis_dir),
                    "--conference",
                    "CCS",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(pipeline_result.returncode, 0, pipeline_result.stderr)

            result = subprocess.run(
                [
                    "python3",
                    "conference-report-generation/scripts/generate_report.py",
                    "--analysis-dir",
                    str(analysis_dir),
                    "--output-dir",
                    str(report_dir),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((report_dir / "conference_report.md").exists())
            metadata = json.loads((report_dir / "conference_report.json").read_text(encoding="utf-8"))
            self.assertIn("country", metadata["included_sections"])
            self.assertIn("collaboration", metadata["included_sections"])

    def test_visualization_generation_uses_existing_outputs(self):
        with TemporaryDirectory() as directory:
            tmp = Path(directory)
            normalized_input = tmp / "author_affiliation_facts.csv"
            analysis_dir = tmp / "analysis"
            visualization_dir = tmp / "visualizations"
            write_normalized_input(normalized_input)

            pipeline_result = subprocess.run(
                [
                    "python3",
                    "conference-analysis-automation/scripts/run_analysis_pipeline.py",
                    "--normalized-input",
                    str(normalized_input),
                    "--output-dir",
                    str(analysis_dir),
                    "--conference",
                    "CCS",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(pipeline_result.returncode, 0, pipeline_result.stderr)

            result = subprocess.run(
                [
                    "python3",
                    "conference-visualization/scripts/generate_visualizations.py",
                    "--analysis-dir",
                    str(analysis_dir),
                    "--output-dir",
                    str(visualization_dir),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((visualization_dir / "country_top_papers.svg").exists())
            self.assertTrue((visualization_dir / "trend_entity_year.svg").exists())
            manifest = json.loads((visualization_dir / "visualization_manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["rendered_files"])

    def test_benchmark_comparison_builds_side_by_side_table(self):
        with TemporaryDirectory() as directory:
            tmp = Path(directory)
            left = tmp / "left.csv"
            right = tmp / "right.csv"
            output_dir = tmp / "comparison"
            left.write_text(
                "country,papers,authors\nUnited States,5,8\nSwitzerland,2,2\n",
                encoding="utf-8",
            )
            right.write_text(
                "country,papers,authors\nUnited States,7,10\nGermany,3,4\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    "python3",
                    "conference-benchmark-comparison/scripts/compare_benchmarks.py",
                    "--label",
                    "CCS2023",
                    "--summary",
                    str(left),
                    "--label",
                    "CCS2024",
                    "--summary",
                    str(right),
                    "--output-dir",
                    str(output_dir),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            comparison_path = output_dir / "benchmark_comparison.csv"
            self.assertTrue(comparison_path.exists())
            with comparison_path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            us_row = next(row for row in rows if row["entity"] == "United States")
            self.assertEqual(us_row["CCS2023"], "5")
            self.assertEqual(us_row["CCS2024"], "7")
            self.assertEqual(us_row["best_label"], "CCS2024")

    def test_quality_audit_reports_anomalies(self):
        with TemporaryDirectory() as directory:
            tmp = Path(directory)
            normalized_input = tmp / "author_affiliation_facts.csv"
            institution_dim = tmp / "institution_dim.csv"
            output_dir = tmp / "audit"
            rows = [
                {
                    "paper_key": "p1",
                    "conference": "CCS",
                    "year": "2024",
                    "name": "Alice",
                    "author_key": "",
                    "author_order": "0",
                    "inst": "Example University",
                    "institution_key": "example-u-1",
                    "country": "Unknown",
                    "classification_confidence": "0.4",
                },
                {
                    "paper_key": "p2",
                    "conference": "CCS",
                    "year": "2024",
                    "name": "Bob",
                    "author_key": "bob",
                    "author_order": "1",
                    "inst": "Example University",
                    "institution_key": "example-u-2",
                    "country": "United States",
                    "classification_confidence": "not-a-number",
                },
            ]
            with normalized_input.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)

            institution_rows = [
                {
                    "institution_key": "example-u-1",
                    "inst_display": "Example University",
                    "country": "Unknown",
                    "source_count": "1",
                    "needs_review": "True",
                },
                {
                    "institution_key": "example-u-2",
                    "inst_display": "Example University",
                    "country": "United States",
                    "source_count": "1",
                    "needs_review": "False",
                },
            ]
            with institution_dim.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(institution_rows[0].keys()))
                writer.writeheader()
                writer.writerows(institution_rows)

            result = subprocess.run(
                [
                    "python3",
                    "conference-quality-audit/scripts/quality_audit.py",
                    "--normalized-input",
                    str(normalized_input),
                    "--institution-dim",
                    str(institution_dim),
                    "--output-dir",
                    str(output_dir),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads((output_dir / "quality_audit.json").read_text(encoding="utf-8"))
            finding_codes = {finding["code"] for finding in payload["findings"]}
            self.assertIn("unknown_country", finding_codes)
            self.assertIn("missing_author_key", finding_codes)
            self.assertIn("low_classification_confidence", finding_codes)
            self.assertIn("invalid_classification_confidence", finding_codes)
            self.assertIn("duplicate_institution_display_names", finding_codes)


if __name__ == "__main__":
    unittest.main()
