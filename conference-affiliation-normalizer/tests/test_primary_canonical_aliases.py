from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from extract_crypto_primary_institutions import enrich_row, load_reviewed_aliases  # noqa: E402
import match_institution_reference_csv as reference_matcher  # noqa: E402


class PrimaryCanonicalAliasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.aliases = load_reviewed_aliases(SKILL_DIR / "references" / "personal-rules.json")
        cls.countries = {"China"}

    def test_shanghai_qi_zhi_overrides_registry_spelling(self) -> None:
        row = {
            "affiliations": "Shanghai Qi Zhi Institute, Shanghai, China",
            "affiliation_institution_candidate": "Shanghai Qi Zhi Institute",
            "affilgood_institutions": "Shanghai Qi Zhi Institute",
            "affilgood_standard_institutions": "Shanghai Qu Zhi Institute",
            "affilgood_ror_ids": "https://ror.org/01n14yn69",
            "affilgood_location_country": "China",
            "affilgood_location_city": "Shanghai",
        }

        result = enrich_row(row, {"rows": [], "index": {}}, self.aliases, self.countries)

        self.assertEqual(result["primary_institution"], "Shanghai Qi Zhi Institute")
        self.assertEqual(result["primary_ror_id"], "https://ror.org/01n14yn69")
        self.assertIn("shanghai-qi-zhi-reviewed-aliases", result["primary_institution_source"])

    def test_zhongguancun_lab_uses_fixed_display_name(self) -> None:
        table = {
            "rows": [
                {
                    "conference_id": "INST1699",
                    "conference_final_id": "INST1699",
                    "observed_name": "Zhongguancun Lab",
                    "standard_name": "Zhongguancun Lab",
                    "country": "China",
                    "city": "Beijing",
                }
            ],
            "index": {},
        }
        row = {
            "affiliations": "Zhongguancun Lab, Beijing, China",
            "affiliation_institution_candidate": "Zhongguancun Lab",
            "affilgood_institutions": "Zhongguancun Lab",
            "affilgood_standard_institutions": "Zhongguancun Lab",
            "affilgood_location_country": "China",
            "institution_reference_id": "INST1699",
        }

        result = enrich_row(row, table, self.aliases, self.countries)

        self.assertEqual(result["primary_institution"], "Zhongguancun Laboratory")
        self.assertEqual(result["primary_institution_id"], "INST1699")
        self.assertIn(
            "zhongguancun-laboratory-reviewed-aliases",
            result["primary_institution_source"],
        )

    def test_post_matcher_automatically_resolves_review_and_blank_country_classes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.csv"
            table = root / "institution_raw.csv"
            output = root / "output.csv"
            report = root / "report.json"
            input_fields = [
                "paper_id", "year", "conference", "author", "author_rank",
                "affiliation_rank", "affiliations",
            ]
            with source.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=input_fields)
                writer.writeheader()
                writer.writerows([
                    {"paper_id": "p1", "year": "2025", "conference": "CCS", "author": "A", "author_rank": "0", "affiliation_rank": "0", "affiliations": "Independent Researcher"},
                    {"paper_id": "p2", "year": "2025", "conference": "CCS", "author": "B", "author_rank": "0", "affiliation_rank": "0", "affiliations": "CMU, IC3"},
                    {"paper_id": "p3", "year": "2025", "conference": "CCS", "author": "C", "author_rank": "0", "affiliation_rank": "0", "affiliations": "Alpha University, Beta University, France"},
                    {"paper_id": "p4", "year": "2025", "conference": "CCS", "author": "D", "author_rank": "0", "affiliation_rank": "0", "affiliations": "Gamma University, France"},
                ])
            table_fields = [
                "affilgood_ror_ids", "conference_id", "affilgood_institutions",
                "affilgood_location_country", "affilgood_location_city", "conference_final_id",
                "affilgood_standard_institutions", "affilgood_standardization_source", "notes",
            ]
            with table.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=table_fields)
                writer.writeheader()
                writer.writerows([
                    {"conference_id": "I1", "conference_final_id": "I1", "affilgood_institutions": "Alpha University", "affilgood_standard_institutions": "Alpha University", "affilgood_location_country": "France"},
                    {"conference_id": "I2", "conference_final_id": "I2", "affilgood_institutions": "Beta University", "affilgood_standard_institutions": "Beta University", "affilgood_location_country": "France"},
                    {"conference_id": "I3", "conference_final_id": "I3", "affilgood_institutions": "Gamma University", "affilgood_standard_institutions": "Gamma University", "affilgood_location_country": "United States"},
                ])

            reference_matcher.match_csv(source, output, table, report)

            with output.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            metrics = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(
                [row["institution_reference_status"] for row in rows],
                [
                    "not_applicable_noninstitutional",
                    "resolved_reviewed_rule",
                    "resolved_atomic_composite",
                    "resolved_unique_identity",
                ],
            )
            self.assertTrue(rows[2]["institution_reference_id"].startswith("ATOMIC:"))
            self.assertTrue(all(not row["institution_reference_review"] for row in rows))
            self.assertEqual(metrics["review_required"], 0)
            self.assertEqual(metrics["blank_country_not_applicable"], 1)
            self.assertEqual(metrics["blank_country_actionable"], 0)

    def test_post_matcher_corrects_ror_from_explicit_city_name_family(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.csv"
            table = root / "institution_raw.csv"
            output = root / "output.csv"
            input_fields = [
                "paper_id", "year", "conference", "author", "author_rank",
                "affiliation_rank", "affiliations", "affilgood_ror_ids",
                "affilgood_institutions", "affilgood_location_country",
                "affilgood_location_city", "affilgood_standard_institutions",
            ]
            with source.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=input_fields)
                writer.writeheader()
                writer.writerows([
                    {
                        "paper_id": "p1", "year": "2025", "conference": "CCS",
                        "author": "A", "author_rank": "0", "affiliation_rank": "0",
                        "affiliations": "Northbridge University, Lakeside, USA",
                        "affilgood_ror_ids": "https://ror.org/wrong",
                        "affilgood_institutions": "Northbridge University in Metro",
                        "affilgood_standard_institutions": "Northbridge University in Metro",
                        "affilgood_location_country": "United States",
                        "affilgood_location_city": "Metro",
                    },
                    {
                        "paper_id": "p2", "year": "2025", "conference": "CCS",
                        "author": "B", "author_rank": "0", "affiliation_rank": "0",
                        "affiliations": "Northbridge University, USA",
                        "affilgood_ror_ids": "https://ror.org/wrong",
                        "affilgood_institutions": "Northbridge University in Metro",
                        "affilgood_standard_institutions": "Northbridge University in Metro",
                        "affilgood_location_country": "United States",
                        "affilgood_location_city": "Metro",
                    },
                ])
            table_fields = [
                "affilgood_ror_ids", "conference_id", "affilgood_institutions",
                "affilgood_location_country", "affilgood_location_city", "conference_final_id",
                "affilgood_standard_institutions", "affilgood_standardization_source", "notes",
            ]
            with table.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=table_fields)
                writer.writeheader()
                writer.writerows([
                    {"affilgood_ror_ids": "https://ror.org/wrong", "conference_id": "I1", "conference_final_id": "I1", "affilgood_institutions": "Northbridge University in Metro", "affilgood_standard_institutions": "Northbridge University in Metro", "affilgood_location_country": "United States", "affilgood_location_city": "Metro"},
                    {"affilgood_ror_ids": "https://ror.org/right", "conference_id": "I2", "conference_final_id": "I2", "affilgood_institutions": "Northbridge University Lakeside", "affilgood_standard_institutions": "Northbridge University Lakeside", "affilgood_location_country": "United States", "affilgood_location_city": "Lakeside"},
                ])

            reference_matcher.match_csv(source, output, table)

            with output.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["institution_reference_status"], "resolved_explicit_location_conflict")
            self.assertEqual(rows[0]["affilgood_ror_ids"], "https://ror.org/right")
            self.assertEqual(rows[0]["affilgood_standard_institutions"], "Northbridge University Lakeside")
            self.assertEqual(rows[0]["institution_reference_match_method"], "explicit_city_name_family")
            self.assertEqual(rows[1]["institution_reference_status"], "affilgood_resolved")
            self.assertEqual(rows[1]["affilgood_ror_ids"], "https://ror.org/wrong")


if __name__ == "__main__":
    unittest.main()
