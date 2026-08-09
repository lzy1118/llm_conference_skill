import unittest
from types import SimpleNamespace

from author_metadata.config import clean_text
from author_metadata.metadata_repair import (
    _clean_ccs_publication_location_noise,
    assign_aligned_orphan_affiliations,
    clean_post_strategy_author_artifacts,
    dedupe_authors_with_pdf_evidence,
    extract_author_emails,
    merge_orphan_affiliation_chunks,
    protect_reliable_author_list,
    repair_metadata,
)
from author_metadata.pdf_context import PdfContext
from author_metadata.extraction_trace import (
    build_candidates,
    preserve_nonempty_author_fields,
    validate_metadata,
)


class TextCleaningTest(unittest.TestCase):
    def test_removes_unpaired_surrogates_without_losing_unicode(self):
        self.assertEqual(clean_text("Université \udc00 北京"), "Université 北京")

    def test_removes_pdf_control_characters(self):
        self.assertEqual(clean_text("\x00 Tommaso\uffff Gagliardoni\x7f"), "Tommaso Gagliardoni")


class AlignedOrphanAffiliationTest(unittest.TestCase):
    def test_assigns_exact_contiguous_affiliation_tail_by_author_order(self):
        authors = [
            {"name": "Alice Smith", "affiliations": [], "affiliation_source": "empty", "_source_index": 0},
            {"name": "Bob Jones", "affiliations": [], "affiliation_source": "empty", "_source_index": 1},
        ]
        raw = [
            {"name": "Alice Smith", "email": "", "affiliations": []},
            {"name": "Bob Jones", "email": "", "affiliations": []},
            {"name": "", "email": "", "affiliations": ["Example University"]},
            {"name": "", "email": "", "affiliations": ["Example Research"]},
        ]

        result = assign_aligned_orphan_affiliations(authors, raw)

        self.assertEqual(result[0]["affiliations"], ["Example University"])
        self.assertEqual(result[1]["affiliations"], ["Example Research"])

    def test_ndss_uses_exact_contiguous_affiliation_tail(self):
        metadata = {
            "title": "Paper",
            "year": "2024",
            "abstract": "Abstract text",
            "root": None,
            "authors": [
                {"name": "Alice Smith", "email": "", "affiliations": []},
                {"name": "Bob Jones", "email": "", "affiliations": []},
                {"name": "", "email": "", "affiliations": ["Example University, Hong Kong"]},
                {"name": "", "email": "", "affiliations": ["Example University, Hong Kong"]},
            ],
        }
        pdf_context = PdfContext(
            "", ["Alice Smith", "Bob Jones"], {}, [], [], [], [],
            ["Alice Smith", "Bob Jones"],
        )

        result = repair_metadata(metadata, pdf_context, conference_name="ndss")

        self.assertEqual(
            [author["affiliations"] for author in result["authors"]],
            [["Example University, Hong Kong"], ["Example University, Hong Kong"]],
        )

    def test_recovers_unknown_lncs_organization_with_numbered_pdf_evidence(self):
        authors = [{
            "name": "Christian Matt",
            "affiliations": [],
            "affiliation_source": "empty",
            "_source_index": 0,
        }]
        raw = [
            {"name": "Christian Matt", "email": "", "affiliations": []},
            {"name": "Concordium", "email": "", "affiliations": []},
            {"name": "", "email": "", "affiliations": ["Zurich, Switzerland"]},
        ]
        context = SimpleNamespace(
            preabstract_lines=["1 Concordium, Zurich, Switzerland"],
            first_page_lines=[],
        )

        result = merge_orphan_affiliation_chunks(authors, raw, pdf_context=context)

        self.assertEqual(
            result[0]["affiliations"],
            ["Concordium, Zurich, Switzerland"],
        )
        self.assertEqual(
            result[0]["affiliation_source"],
            "orphan_affiliation_pdf_evidence",
        )

    def test_does_not_recover_unknown_fragment_without_exact_pdf_evidence(self):
        authors = [{
            "name": "Alice Smith",
            "affiliations": [],
            "affiliation_source": "empty",
            "_source_index": 0,
        }]
        raw = [
            {"name": "Alice Smith", "email": "", "affiliations": []},
            {"name": "Unknown", "email": "", "affiliations": []},
            {"name": "", "email": "", "affiliations": ["Zurich, Switzerland"]},
        ]
        context = SimpleNamespace(
            preabstract_lines=["1 Different Company, Zurich, Switzerland"],
            first_page_lines=[],
        )

        result = merge_orphan_affiliation_chunks(authors, raw, pdf_context=context)

        self.assertEqual(result[0]["affiliations"], [])

    def test_removes_ccs_location_noise_from_mainland_china_address(self):
        self.assertEqual(
            _clean_ccs_publication_location_noise(
                "Cryptography Technology Zhengzhou, Henan Taipei, China Taiwan"
            ),
            "Cryptography Technology Zhengzhou, Henan, China",
        )


class AuthorEmailExtractionTest(unittest.TestCase):
    def test_maps_plain_email_to_unique_author(self):
        context = PdfContext(
            first_page_text="",
            first_page_lines=["Guyue Liu", "guyue@pku.edu.cn"],
            page_lines={},
            title_lines=[],
            author_lines=[],
            affiliation_lines=[],
            email_lines=["guyue@pku.edu.cn"],
            preabstract_lines=[],
        )

        result = extract_author_emails(context, ["Yuejie Wang", "Guyue Liu"])

        self.assertEqual(result, {"guyue liu": "guyue@pku.edu.cn"})


class PostStrategyAuthorArtifactTest(unittest.TestCase):
    def test_removes_organization_author_and_cleans_person_suffix(self):
        authors = [
            {"order": 0, "name": "Palo Alto Networks", "affiliations": []},
            {"order": 1, "name": "Antoon Purnal Imec-Cosic", "affiliations": []},
        ]

        result, decisions = clean_post_strategy_author_artifacts(authors)

        self.assertEqual([author["name"] for author in result], ["Antoon Purnal"])
        self.assertEqual(
            {item["action"] for item in decisions},
            {"remove_organization_author", "clean_author_name_artifact"},
        )

    def test_splits_leading_comma_author_group_and_removes_year(self):
        authors = [
            {"order": 0, "name": ", Hong Hu , Hangfan Zhang", "affiliations": []},
            {"order": 1, "name": "Kovila P L 2020 Coopamootoo", "affiliations": []},
        ]

        result, _ = clean_post_strategy_author_artifacts(authors)

        self.assertEqual(
            [author["name"] for author in result],
            ["Hong Hu", "Hangfan Zhang", "Kovila P L Coopamootoo"],
        )

    def test_removes_split_university_acronym_artifact(self):
        authors = [
            {"order": 0, "name": "Antoon Purnal", "affiliations": []},
            {"order": 1, "name": "K ULeuven", "affiliations": []},
        ]

        result, decisions = clean_post_strategy_author_artifacts(authors)

        self.assertEqual([author["name"] for author in result], ["Antoon Purnal"])
        self.assertEqual(decisions[0]["action"], "remove_organization_author")

    def test_rejects_parser_rebuild_that_loses_most_clean_authors(self):
        baseline = [
            {"order": index, "name": name, "affiliations": []}
            for index, name in enumerate([
                "Julia Len", "Melissa Chase", "Esha Ghosh",
                "Daniel Jost", "Balachandar Kesavan", "Antonio Marcedone",
            ])
        ]
        proposed = [
            {"order": 0, "name": "Julia Len", "affiliations": []},
            {"order": 1, "name": "Daniel Jost", "affiliations": []},
            {"order": 2, "name": "Zoom Video Communications", "affiliations": []},
        ]

        result, decisions, reviews = protect_reliable_author_list(
            baseline, proposed, "conference_strategy"
        )

        self.assertEqual([author["name"] for author in result], [a["name"] for a in baseline])
        self.assertEqual(decisions[0]["action"], "reject_author_list_rebuild")
        self.assertEqual(reviews[0]["code"], "author_list_rebuild_rejected")

    def test_dedupes_only_beyond_exact_pdf_name_line_count(self):
        authors = [
            {"order": 0, "name": "Qi Li"},
            {"order": 1, "name": "Qi Li"},
            {"order": 2, "name": "Jingyi Wang"},
            {"order": 3, "name": "Jingyi Wang"},
            {"order": 4, "name": "Jingyi Wang"},
        ]
        pdf_context = SimpleNamespace(
            preabstract_lines=["Qi Li", "Qi Li*", "Jingyi Wang∗"],
            first_page_lines=[],
        )

        result, decisions = dedupe_authors_with_pdf_evidence(authors, pdf_context)

        self.assertEqual(
            [author["name"] for author in result],
            ["Qi Li", "Qi Li", "Jingyi Wang"],
        )
        self.assertEqual(decisions[0]["removed_count"], 2)


class PreserveNonemptyFieldsTest(unittest.TestCase):
    def test_restores_direct_tei_affiliation_and_email(self):
        baseline = [{
            "name": "Alice Smith",
            "affiliations": ["DPella AB"],
            "email": "alice@example.org",
            "affiliation_source": "author_node",
        }]
        proposed = [{
            "name": "Alice Smith",
            "affiliations": [],
            "email": "",
            "affiliation_source": "author_node",
        }]

        result, decisions, reviews = preserve_nonempty_author_fields(
            baseline, proposed, "conference_strategy"
        )

        self.assertEqual(result[0]["affiliations"], ["DPella AB"])
        self.assertEqual(result[0]["email"], "alice@example.org")
        self.assertEqual([item["action"] for item in decisions], [
            "restore_nonempty_field",
            "restore_nonempty_field",
        ])
        self.assertEqual(reviews, [])

    def test_does_not_restore_weak_shared_affiliation(self):
        baseline = [{
            "name": "Alice Smith",
            "affiliations": ["Microsoft Research"],
            "email": "",
            "affiliation_source": "shared_pdf",
        }]
        proposed = [{
            "name": "Alice Smith",
            "affiliations": [],
            "email": "",
            "affiliation_source": "shared_pdf",
        }]

        result, decisions, reviews = preserve_nonempty_author_fields(
            baseline, proposed, "conference_strategy"
        )

        self.assertEqual(result[0]["affiliations"], [])
        self.assertEqual(decisions[0]["action"], "reject_restore")
        self.assertIn("weak_source:shared_pdf", decisions[0]["reason"])
        self.assertEqual(reviews[0]["code"], "nonempty_field_dropped_with_reason")

    def test_does_not_restore_affiliation_containing_another_author(self):
        baseline = [
            {
                "name": "Daniel Genkin",
                "affiliations": ["Stephan van Schaik van Schaik, LLC"],
                "email": "",
                "affiliation_source": "author_node",
            },
            {
                "name": "Stephan van Schaik",
                "affiliations": ["van Schaik, LLC"],
                "email": "",
                "affiliation_source": "author_node",
            },
        ]
        proposed = [
            {"name": "Daniel Genkin", "affiliations": [], "email": ""},
            {"name": "Stephan van Schaik", "affiliations": ["van Schaik, LLC"], "email": ""},
        ]

        result, decisions, _ = preserve_nonempty_author_fields(
            baseline, proposed, "conference_strategy"
        )

        self.assertEqual(result[0]["affiliations"], [])
        self.assertIn("contains_other_author:Stephan van Schaik", decisions[0]["reason"])

    def test_ignores_punctuation_only_affiliation_difference(self):
        baseline = [{
            "name": "Alice Smith",
            "affiliations": ["Example University Sweden USA"],
            "email": "",
            "affiliation_source": "author_node",
        }]
        proposed = [{
            "name": "Alice Smith",
            "affiliations": ["Example University, Sweden, USA"],
            "email": "",
            "affiliation_source": "author_node",
        }]

        _, _, reviews = preserve_nonempty_author_fields(baseline, proposed, "conference_strategy")

        self.assertEqual(reviews, [])

    def test_accepts_direct_lncs_numbered_affiliation_over_tei_fragment(self):
        baseline = [{
            "name": "Chao Li",
            "affiliations": ["Engineering, Chinese Academy of Sciences, Beijing, China"],
            "email": "",
            "affiliation_source": "orphan_affiliation",
        }]
        proposed = [{
            "name": "Chao Li",
            "affiliations": [
                "College of Liberal Arts and Science, National University of Defense Technology, Changsha, China"
            ],
            "email": "",
            "affiliation_source": "lncs_pdf_numbered",
        }]

        result, decisions, reviews = preserve_nonempty_author_fields(
            baseline, proposed, "conference_strategy"
        )

        self.assertEqual(result, proposed)
        self.assertEqual(decisions[0]["action"], "replace_nonempty_field_from_direct_pdf")
        self.assertEqual(reviews, [])


class TraceValidationTest(unittest.TestCase):
    def test_candidates_keep_raw_and_selected_authors(self):
        raw = {"title": "Raw", "year": "2025", "authors": [{"name": "A B"}]}
        selected = {"title": "Selected", "year": "2025", "authors": [{"name": "A Bee"}]}
        candidates = build_candidates(raw, selected)
        self.assertEqual(candidates["authors"]["grobid_tei"][0]["name"], "A B")
        self.assertEqual(candidates["authors"]["selected"][0]["name"], "A Bee")

    def test_validation_flags_author_count_change(self):
        raw = {"title": "Paper", "authors": [{"name": "A B"}, {"name": "C D"}]}
        selected = {"title": "Paper", "authors": [{"name": "A B"}]}
        issues = validate_metadata(raw, selected)
        self.assertIn("author_count_changed", {item["code"] for item in issues})

    def test_validation_ignores_affiliation_only_tei_nodes(self):
        raw = {
            "title": "Paper",
            "authors": [
                {"name": "A B"},
                {"name": "", "affiliations": ["Example University"]},
            ],
        }
        selected = {"title": "Paper", "authors": [{"name": "A B"}]}
        issues = validate_metadata(raw, selected)
        self.assertNotIn("author_count_changed", {item["code"] for item in issues})

    def test_validation_accepts_closed_pdf_layout_author_rebuild(self):
        raw = {"title": "Paper", "authors": [{"name": "A B"}]}
        selected = {"title": "Paper", "authors": [{"name": "A B"}, {"name": "C D"}]}
        decisions = [{"action": "rebuild_author_list_from_pdf_layout"}]
        issues = validate_metadata(raw, selected, decisions=decisions)
        self.assertNotIn("author_count_changed", {item["code"] for item in issues})


if __name__ == "__main__":
    unittest.main()
