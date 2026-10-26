from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_final_view.py"
SPEC = importlib.util.spec_from_file_location("generate_final_view", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(module)


class GenerateFinalViewTests(unittest.TestCase):
    def test_preserves_role_fields_and_allows_blank_orcid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.csv"
            output = root / "final.csv"
            fields = [
                "paper_id", "year", "conference", "title", "author", "author_rank",
                "affiliation_rank", "affiliations", "emails", "first_author",
                "co_first_author", "corresponding", "equal_contribution", "country",
                "orcid", "affilgood_location_country",
            ]
            source_row = {
                "paper_id": "p1", "year": "2025", "conference": "crypto",
                "title": "Fixture", "author": "A. Author", "author_rank": "0",
                "affiliation_rank": "0", "affiliations": "Example University",
                "emails": "author@example.edu", "first_author": "true",
                "co_first_author": "true", "corresponding": "false",
                "equal_contribution": "true", "country": "Legacy Country",
                "orcid": "", "affilgood_location_country": "United States",
            }
            explicit_corresponding = {
                **source_row,
                "author": "B. Author",
                "author_rank": "1",
                "affiliation_rank": "1",
                "emails": "",
                "first_author": "false",
                "co_first_author": "false",
                "corresponding": "true",
                "equal_contribution": "false",
            }
            unspecified_corresponding = {
                **source_row,
                "author": "C. Author",
                "author_rank": "2",
                "affiliation_rank": "2",
                "emails": "",
                "first_author": "false",
                "co_first_author": "false",
                "corresponding": "",
                "equal_contribution": "false",
            }
            with source.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows([source_row, explicit_corresponding, unspecified_corresponding])

            module.generate(source, output, "crypto", "2025")

            with output.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
            self.assertEqual(tuple(reader.fieldnames or ()), module.DISPLAY_FIELDS)
            self.assertEqual(rows[0]["emails"], source_row["emails"])
            self.assertEqual(rows[0]["co_first_author"], source_row["co_first_author"])
            self.assertEqual(rows[0]["corresponding"], "false")
            self.assertEqual(rows[0]["equal_contribution"], source_row["equal_contribution"])
            self.assertEqual(rows[0]["orcid"], "")
            self.assertEqual(rows[0]["country"], "United States")
            self.assertEqual(rows[1]["corresponding"], "true")
            self.assertEqual(rows[2]["corresponding"], "")


if __name__ == "__main__":
    unittest.main()
