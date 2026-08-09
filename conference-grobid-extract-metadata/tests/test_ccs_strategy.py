import unittest
from unittest.mock import patch

import ccs_strategy


class CcsAuthorCandidateSafetyTest(unittest.TestCase):
    def test_organization_fragments_are_not_person_names(self):
        for text in (
            "Information Engineering",
            "Singapore Management",
            "Nanyang Technological",
            "Brave Software",
            "Zoom Video Communications",
            "Privacy (MPI-SP)",
            "United Kingdom",
        ):
            with self.subTest(text=text):
                self.assertFalse(ccs_strategy._looks_like_person_name(text))

    def test_person_name_allows_lowercase_family_name_particle(self):
        self.assertTrue(
            ccs_strategy._looks_like_person_name("Cyprien Delpech de Saint Guilhem")
        )

    def test_title_candidate_cannot_trigger_author_rebuild(self):
        authors = [{
            "order": 0,
            "name": "Michele Orrù",
            "email": "m@orru.net",
            "affiliations": ["CNRS"],
        }]
        pdf_authors = [
            {
                "name": "Revisiting Keyed-Verification Anonymous Credentials",
                "email": "",
                "affiliations": ["CNRS"],
            },
            {
                "name": "Michele Orrù",
                "email": "m@orru.net",
                "affiliations": ["CNRS"],
            },
        ]

        with patch.object(ccs_strategy, "_parse_acm_numbered_author_blocks", return_value=pdf_authors):
            result = ccs_strategy.refine_authors(
                authors,
                title="Revisiting Keyed-Verification Anonymous Credentials",
                pdf_lines=["header"],
            )

        self.assertEqual([author["name"] for author in result], ["Michele Orrù"])

    def test_joins_clear_university_affiliation_fragments(self):
        self.assertEqual(
            ccs_strategy._join_split_university_chunks([
                "Singapore Management",
                "University, Singapore",
            ]),
            ["Singapore Management University, Singapore"],
        )

    def test_candidate_arbitration_prefers_complete_affiliation_for_same_authors(self):
        existing = [{"name": "Biming Zhou"}]
        short = [{"name": "Biming Zhou", "email": "b@example.org", "affiliations": ["University, Shanghai, China"]}]
        complete = [{"name": "Biming Zhou", "email": "b@example.org", "affiliations": [
            "College of Computer Science and Artificial Intelligence, Fudan",
            "University, Shanghai, China",
        ]}]

        selected = ccs_strategy._select_pdf_author_candidate([short, complete], existing)

        self.assertEqual(selected[0]["affiliations"], [
            "College of Computer Science and Artificial Intelligence, Fudan University, Shanghai, China",
        ])

    def test_repairs_internal_breaks_and_duplicate_location(self):
        self.assertEqual(
            ccs_strategy._repair_affiliation_text(
                "East China Normal, University, Shenzhen, Shenzhen, China"
            ),
            "East China Normal University, Shenzhen, China",
        )
        self.assertEqual(
            ccs_strategy._repair_affiliation_text("CryptoLab, Republic of, Korea"),
            "CryptoLab, Republic of Korea",
        )

    def test_joins_country_only_affiliation_chunk(self):
        self.assertEqual(
            ccs_strategy._join_split_university_chunks([
                "Georgia Institute of Technology",
                "USA",
            ]),
            ["Georgia Institute of Technology, USA"],
        )

    def test_does_not_rebuild_with_much_shorter_affiliations_at_same_coverage(self):
        existing = [
            {"name": "Alice Smith", "affiliations": ["College of Computer Science, Example University, Paris, France"]},
            {"name": "Bob Jones", "affiliations": ["Example Research Laboratory, London, UK"]},
        ]
        candidate = [
            {"name": "Alice Smith", "affiliations": ["University, France"]},
            {"name": "Bob Jones", "affiliations": ["Laboratory, UK"]},
        ]

        self.assertFalse(ccs_strategy._should_rebuild_from_pdf(candidate, existing))


if __name__ == "__main__":
    unittest.main()
