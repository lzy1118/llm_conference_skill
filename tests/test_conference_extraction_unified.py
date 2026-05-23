import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]


class UnifiedConferenceExtractionTests(unittest.TestCase):
    def test_dry_run_group_builds_two_backend_steps(self):
        with TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    "python3",
                    "conference-paper-extraction/scripts/run_unified_pipeline.py",
                    "--group",
                    "top3_crypto",
                    "--group",
                    "top4_security",
                    "--output-dir",
                    directory,
                    "--dry-run",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("asiacrypt_2025", payload["conference_keys"])
            self.assertIn("usenix_security_2022", payload["conference_keys"])
            self.assertEqual([step["backend"] for step in payload["plan"]], ["iacr_top3", "security_real"])

    def test_dry_run_security_fetch_affiliations_only_hits_security_backend(self):
        with TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    "python3",
                    "conference-paper-extraction/scripts/run_unified_pipeline.py",
                    "--conference",
                    "crypto_2025",
                    "--conference",
                    "usenix_security_2022",
                    "--output-dir",
                    directory,
                    "--fetch-affiliations",
                    "--dry-run",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            commands = {step["backend"]: step["command"] for step in payload["plan"]}
            self.assertNotIn("--fetch-affiliations", commands["iacr_top3"])
            self.assertIn("--fetch-affiliations", commands["security_real"])

    def test_dry_run_resolution_flags_only_hit_iacr_backend(self):
        with TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    "python3",
                    "conference-paper-extraction/scripts/run_unified_pipeline.py",
                    "--conference",
                    "crypto_2025",
                    "--conference",
                    "usenix_security_2022",
                    "--output-dir",
                    directory,
                    "--resolve-mismatches",
                    "--query-dblp-for-resolution",
                    "--dry-run",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            commands = {step["backend"]: step["command"] for step in payload["plan"]}
            self.assertIn("--resolve-mismatches", commands["iacr_top3"])
            self.assertIn("--query-dblp-for-resolution", commands["iacr_top3"])
            self.assertNotIn("--resolve-mismatches", commands["security_real"])
            self.assertNotIn("--query-dblp-for-resolution", commands["security_real"])

    def test_list_conferences_includes_groups_and_backends(self):
        result = subprocess.run(
            [
                "python3",
                "conference-paper-extraction/scripts/run_unified_pipeline.py",
                "--list-conferences",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("top3_crypto", result.stdout)
        self.assertIn("top4_security", result.stdout)
        self.assertIn("backend=security_real", result.stdout)

    def test_unified_runner_smoke_test_with_local_fixture_data(self):
        with TemporaryDirectory() as directory:
            tmp = Path(directory)
            raw_dir = tmp / "raw"
            cache_dir = tmp / "resolution" / "affiliation_cache"
            raw_dir.mkdir(parents=True, exist_ok=True)
            cache_dir.mkdir(parents=True, exist_ok=True)

            (raw_dir / "crypto_2025_papers.json").write_text(
                json.dumps(
                    {
                        "acceptedPapers": [
                            {
                                "paperId": "crypto-p1",
                                "title": "Crypto Paper",
                                "authors": ["Alice Crypto"],
                                "affiliations": ["MIT"],
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (raw_dir / "usenix_security_2022_papers.json").write_text(
                json.dumps(
                    [
                        {
                            "paperId": "conf/uss/2022/p1",
                            "title": "Security Paper",
                            "authors": ["Alice Security", "Bob Security"],
                            "url": "https://example.com/security-paper",
                        }
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (cache_dir / "conf_uss_2022_p1_affiliations.json").write_text(
                json.dumps(
                    [
                        {"name": "Alice Security", "affiliations": ["Stanford University"]},
                        {"name": "Bob Security", "affiliations": ["University of Toronto"]},
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    "python3",
                    "conference-paper-extraction/scripts/run_unified_pipeline.py",
                    "--conference",
                    "crypto_2025",
                    "--conference",
                    "usenix_security_2022",
                    "--output-dir",
                    str(tmp),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((tmp / "interim" / "institution_classification_candidates.csv").exists())
            self.assertTrue((tmp / "output" / "crypto_2025_author_affiliations.csv").exists())
            self.assertTrue((tmp / "output" / "usenix_security_2022_author_affiliations.csv").exists())
            self.assertTrue((tmp / "output" / "crypto_2025_us_institutions.csv").exists())
            self.assertTrue((tmp / "output" / "usenix_security_2022_us_institutions.csv").exists())
            self.assertTrue((tmp / "output" / "2025-2026三大密码会_作者机构国家.csv").exists())
            self.assertTrue((tmp / "output" / "四大安全顶会_作者机构国家.csv").exists())
            self.assertTrue((tmp / "output" / "2025-2026三大密码会_美国机构.csv").exists())
            self.assertTrue((tmp / "output" / "四大安全顶会_美国机构.csv").exists())
            manifest = json.loads((tmp / "unified_run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["conference_keys"], ["crypto_2025", "usenix_security_2022"])
            self.assertEqual([step["returncode"] for step in manifest["steps"]], [0, 0])
            combined_report = json.loads((tmp / "output" / "validation_report.json").read_text(encoding="utf-8"))
            self.assertIn("classified_author_rows", combined_report)
            self.assertIn("resolved_country_rows", combined_report)
            self.assertIn("unresolved_country_rows", combined_report)

    def test_legacy_conference_pipeline_forwards_to_unified_runner(self):
        result = subprocess.run(
            [
                "python3",
                "conference-paper-extraction/scripts/conference_pipeline.py",
                "--conference",
                "crypto_2025",
                "usenix_security_2022",
                "--dry-run",
                "--output-dir",
                "data",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["conference_keys"], ["crypto_2025", "usenix_security_2022"])
