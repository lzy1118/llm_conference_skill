from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_pipeline.py"
SPEC = importlib.util.spec_from_file_location("conference_research_run_pipeline", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(module)


class UnifiedRunPipelineTests(unittest.TestCase):
    def test_accepts_all_seven_conferences_and_aliases(self) -> None:
        expected = {
            "ASIACRYPT": ("crypto", "asiacrypt"),
            "CRYPTO": ("crypto", "crypto"),
            "EUROCRYPT": ("crypto", "eurocrypt"),
            "CCS": ("security", "CCS"),
            "IEEE S&P": ("security", "IEEE_S&P"),
            "NDSS": ("security", "NDSS"),
            "USENIX Security": ("security", "USENIX_SECURITY"),
        }
        for value, result in expected.items():
            self.assertEqual(module.canonical_conference(value), result)

    def test_crypto_dry_run_uses_lncs_pdf_chain_and_crypto_primary_stage(self) -> None:
        completed = subprocess.run([
            sys.executable, str(SCRIPT), "--repo-root", str(SCRIPT.parents[2]),
            "--conference", "CRYPTO", "--year", "2025", "--python", sys.executable,
            "--dry-run", "--skip-analysis",
        ], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("extract_paper_metadata.py", completed.stdout)
        self.assertIn("--conference crypto", completed.stdout)
        self.assertIn("enrich_pdf_author_roles.py", completed.stdout)
        self.assertIn("extract_crypto_primary_institutions.py", completed.stdout)
        self.assertNotIn("reconcile_security_official_metadata.py", completed.stdout)

    def test_security_dry_run_delegates_to_existing_pipeline(self) -> None:
        completed = subprocess.run([
            sys.executable, str(SCRIPT), "--repo-root", str(SCRIPT.parents[2]),
            "--conference", "IEEE S&P", "--year", "2025", "--python", sys.executable,
            "--dry-run", "--skip-analysis",
        ], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("reconcile_security_official_metadata.py", completed.stdout)
        self.assertIn("--conference IEEE_S&P", completed.stdout)


if __name__ == "__main__":
    unittest.main()
