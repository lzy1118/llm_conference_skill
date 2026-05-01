import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.top3_us_pipeline import (
    ConferenceConfig,
    build_article_tag,
    classify_affiliation,
    expand_author_rows,
    filter_us_rows,
    load_institution_overrides,
)


class Top3UsPipelineTests(unittest.TestCase):
    def test_build_article_tag_uses_title_not_paper_id(self):
        config = ConferenceConfig(
            key="eurocrypt_2026",
            conference="EUROCRYPT",
            year=2026,
            url="https://eurocrypt.iacr.org/2026/json/papers.json",
        )

        tag = build_article_tag(
            config,
            {
                "paperId": 13,
                "title": "Two-Server Private Information Retrieval in Sublinear Time and Quasilinear Space",
            },
        )

        self.assertEqual(
            tag,
            "EUROCRYPT-Two-Server Private Information Retrieval in Sublinear Time and Quasilinear Space",
        )

    def test_filter_us_rows_keeps_only_us_affiliations(self):
        config = ConferenceConfig(
            key="eurocrypt_2026",
            conference="EUROCRYPT",
            year=2026,
            url="https://eurocrypt.iacr.org/2026/json/papers.json",
        )
        papers = [
            {
                "paperId": 13,
                "title": "Two-Server Private Information Retrieval in Sublinear Time and Quasilinear Space",
                "authors": ["Alexandra Henzinger", "Seyoon Ragavan"],
                "affiliations": ["MIT", "ETH Zurich"],
            }
        ]

        rows, issues = expand_author_rows(config, papers)
        us_rows = filter_us_rows(rows)

        self.assertEqual(issues, [])
        self.assertEqual(len(us_rows), 1)
        self.assertEqual(us_rows[0]["name"], "Alexandra Henzinger")
        self.assertEqual(us_rows[0]["inst"], "MIT")
        self.assertEqual(us_rows[0]["author_order"], 0)

    def test_mismatched_affiliations_are_not_silently_assigned(self):
        config = ConferenceConfig(
            key="eurocrypt_2026",
            conference="EUROCRYPT",
            year=2026,
            url="https://eurocrypt.iacr.org/2026/json/papers.json",
        )
        papers = [
            {
                "paperId": 2,
                "title": "Group Key Progression: Strong Security for Shared Persistent Data",
                "authors": ["Matilda Backendal", "David Balbas", "Miro Haller"],
                "affiliations": ["USI, Lugano", "ETH Zurich", "UC San Diego"],
            },
            {
                "paperId": 99,
                "title": "Ambiguous Paper",
                "authors": ["Alice", "Bob"],
                "affiliations": ["MIT"],
            },
        ]

        rows, issues = expand_author_rows(config, papers)
        us_rows = filter_us_rows(rows)

        self.assertEqual(len(us_rows), 1)
        self.assertEqual(us_rows[0]["name"], "Miro Haller")
        self.assertEqual(issues[0]["issue"], "author_affiliation_count_mismatch")
        self.assertEqual(issues[0]["paper_id"], "99")

    def test_affiliation_classifier_handles_common_us_and_non_us_names(self):
        self.assertTrue(classify_affiliation("UC San Diego").is_us)
        self.assertTrue(classify_affiliation("MIT").is_us)
        self.assertTrue(classify_affiliation("NIST").is_us)
        self.assertTrue(classify_affiliation("Brown University").is_us)
        self.assertTrue(classify_affiliation("Johns Hopkins University & NTT").is_us)
        self.assertTrue(classify_affiliation("UIUC and NTT Research").is_us)
        self.assertTrue(classify_affiliation("UMD").is_us)
        self.assertTrue(classify_affiliation("Yale").is_us)
        self.assertFalse(classify_affiliation("ETH Zurich").is_us)
        self.assertFalse(classify_affiliation("ETH Zürich").is_us)
        self.assertFalse(classify_affiliation("IBM Research Europe").is_us)
        self.assertFalse(classify_affiliation("Ruhr University Bochum").is_us)

    def test_affiliation_overrides_take_precedence(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "institution_country_overrides.csv"
            path.write_text(
                "inst,is_us_institution,reason\nExample Lab,true,manual_review\n",
                encoding="utf-8",
            )

            overrides = load_institution_overrides(path)
            result = classify_affiliation("Example Lab", overrides)

            self.assertTrue(result.is_us)
            self.assertEqual(result.source, "override")


if __name__ == "__main__":
    unittest.main()
