import unittest

from author_metadata.layout_relations import (
    analyze_layout,
    apply_layout_affiliations,
    reconcile_authors_from_layout,
)
from author_metadata.metadata_repair import (
    LAYOUT_CARD_CONFERENCES,
    _complete_layout_mapping,
    apply_author_roles,
    get_export_author_rank,
)
from author_metadata.pdf_context import PdfContext


def block(index, x, y, size, text, width=120):
    return {
        "block_id": f"pdf:p1:b{index}",
        "page": 1,
        "bbox": [x, y, x + width, y + size],
        "x": x,
        "y": y,
        "font_size": size,
        "raw_text": text,
    }


def context(blocks):
    return PdfContext("", [], {}, [], [], [], [], [], page_blocks={1: blocks})


class LayoutRelationsTest(unittest.TestCase):
    def setUp(self):
        self.blocks = [
            block(0, 100, 700, 12, "Alice Smith"),
            block(1, 100, 688, 10, "Example University"),
            block(2, 100, 676, 10, "Paris, France"),
            block(3, 350, 700, 12, "Bob Jones"),
            block(4, 350, 688, 10, "Example Research"),
            block(5, 350, 676, 10, "London, UK"),
            block(6, 50, 650, 11, "Abstract"),
        ]
        self.authors = [
            {"name": "Alice Smith", "affiliations": [], "email": ""},
            {"name": "Bob Jones", "affiliations": [], "email": ""},
        ]

    def test_ndss_enables_validated_author_card_layout(self):
        self.assertIn("ndss", LAYOUT_CARD_CONFERENCES)

    def test_ndss_requires_complete_author_card_mapping(self):
        complete = {
            "auto_eligible": True,
            "relations": [
                {
                    "author_index": 0,
                    "local_auto_eligible": True,
                    "email_raw": "alice@example.org",
                    "email_block_ids": ["pdf:p1:b2"],
                },
                {
                    "author_index": 1,
                    "local_auto_eligible": True,
                    "email_raw": "bob@example.org",
                    "email_block_ids": ["pdf:p1:b5"],
                },
            ],
        }
        partial = {
            "auto_eligible": True,
            "relations": [{"author_index": 0, "local_auto_eligible": True}],
        }

        self.assertTrue(_complete_layout_mapping(complete, 2, require_card_email=True))
        self.assertFalse(_complete_layout_mapping(partial, 2))

    def test_complete_author_card_mapping_does_not_require_email(self):
        complete = {
            "auto_eligible": True,
            "relations": [
                {"author_index": 0, "local_auto_eligible": True, "email_raw": ""},
                {"author_index": 1, "local_auto_eligible": True, "email_raw": ""},
            ],
        }
        self.assertTrue(_complete_layout_mapping(complete, 2))

    def test_exact_card_grid_fills_raw_affiliations(self):
        analysis = analyze_layout(context(self.blocks), self.authors)
        result, decisions, reviews = apply_layout_affiliations(self.authors, analysis)

        self.assertTrue(analysis["auto_eligible"])
        self.assertEqual(analysis["layout_type"], "author_card_grid")
        self.assertEqual(result[0]["affiliations"], ["Example University Paris, France"])
        self.assertEqual(result[1]["affiliations"], ["Example Research London, UK"])
        self.assertEqual(result[0]["affiliation_source"], "pdf_layout")
        self.assertEqual(len(decisions), 2)
        self.assertEqual(reviews, [])

    def test_author_count_mismatch_allows_only_locally_exact_relations(self):
        authors = self.authors + [{"name": "Missing Author", "affiliations": [], "email": ""}]
        analysis = analyze_layout(context(self.blocks), authors)
        result, decisions, reviews = apply_layout_affiliations(authors, analysis)

        self.assertFalse(analysis["auto_eligible"])
        self.assertEqual(result[0]["affiliations"], ["Example University Paris, France"])
        self.assertEqual(result[1]["affiliations"], ["Example Research London, UK"])
        self.assertEqual(result[2]["affiliations"], [])
        self.assertEqual(len(decisions), 2)
        self.assertEqual(reviews, [])

    def test_existing_conflicting_affiliation_is_reviewed_not_overwritten(self):
        authors = [dict(self.authors[0], affiliations=["Other University"]), self.authors[1]]
        analysis = analyze_layout(context(self.blocks), authors)
        result, _, reviews = apply_layout_affiliations(authors, analysis)

        self.assertEqual(result[0]["affiliations"], ["Other University"])
        self.assertTrue(any(item["code"] == "layout_affiliation_conflict" for item in reviews))

    def test_ieee_aligned_rows_replace_wrong_shared_tei_affiliation(self):
        blocks = [
            block(0, 50, 700, 12, "DanBoneh", width=70),
            block(1, 180, 700, 12, "EletteBoyle", width=80),
            block(2, 330, 700, 12, "HenryCorrigan-Gibbs", width=130),
            block(3, 50, 686, 12, "Stanford", width=70),
            block(4, 180, 686, 12, "IDCHerzliya", width=80),
            block(5, 330, 686, 12, "EPFLandMITCSAIL", width=130),
            block(6, 50, 650, 11, "Abstract"),
        ]
        authors = [
            {"name": "Dan Boneh", "affiliations": ["Ben-Gurion University"], "email": ""},
            {"name": "Elette Boyle", "affiliations": ["Ben-Gurion University"], "email": ""},
            {"name": "Henry Corrigan-Gibbs", "affiliations": ["Ben-Gurion University"], "email": ""},
        ]

        analysis = analyze_layout(context(blocks), authors)
        result, decisions, reviews = apply_layout_affiliations(
            authors,
            analysis,
            auto_fill_enabled=False,
            auto_accept_aligned_rows=True,
        )

        self.assertEqual(analysis["layout_type"], "aligned_author_affiliation_rows")
        self.assertEqual(
            [author["affiliations"] for author in result],
            [["Stanford"], ["IDC Herzliya"], ["EPFL and MIT CSAIL"]],
        )
        self.assertEqual(len(decisions), 3)
        self.assertEqual(reviews, [])

    def test_aligned_rows_do_not_override_when_conference_is_not_enabled(self):
        blocks = [
            block(0, 50, 700, 12, "Alice Smith", width=90),
            block(1, 250, 700, 12, "Bob Jones", width=90),
            block(2, 50, 686, 12, "Example University", width=90),
            block(3, 250, 686, 12, "Other Research", width=90),
            block(4, 50, 650, 11, "Abstract"),
        ]
        authors = [
            {"name": "Alice Smith", "affiliations": ["Shared University"], "email": ""},
            {"name": "Bob Jones", "affiliations": ["Shared University"], "email": ""},
        ]

        analysis = analyze_layout(context(blocks), authors)
        result, decisions, reviews = apply_layout_affiliations(
            authors,
            analysis,
            auto_fill_enabled=False,
        )

        self.assertEqual([author["affiliations"] for author in result], [["Shared University"], ["Shared University"]])
        self.assertEqual(decisions, [])
        self.assertTrue(any(item["code"] == "layout_affiliation_conflict" for item in reviews))

    def test_existing_extended_affiliation_is_not_reported_as_conflict(self):
        authors = [
            dict(self.authors[0], affiliations=["Example University, Faculty of Science, Paris, France"]),
            self.authors[1],
        ]
        analysis = analyze_layout(context(self.blocks), authors)
        _, _, reviews = apply_layout_affiliations(authors, analysis)

        self.assertFalse(any(
            item["code"] == "layout_affiliation_conflict" and item["author"] == "Alice Smith"
            for item in reviews
        ))

    def test_high_confidence_layout_replaces_clear_affiliation_fragment(self):
        authors = [dict(self.authors[0], affiliations=["University, China"])]
        analysis = analyze_layout(context(self.blocks[:3] + [self.blocks[6]]), authors)
        result, decisions, reviews = apply_layout_affiliations(authors, analysis)

        self.assertEqual(result[0]["affiliations"], ["Example University Paris, France"])
        self.assertEqual(decisions[0]["action"], "replace_fragmented_affiliation_from_pdf_layout")
        self.assertEqual(reviews, [])

    def test_complete_conflicting_affiliation_is_still_not_overwritten(self):
        authors = [dict(self.authors[0], affiliations=["Other University, Berlin, Germany"])]
        analysis = analyze_layout(context(self.blocks[:3] + [self.blocks[6]]), authors)
        result, decisions, reviews = apply_layout_affiliations(authors, analysis)

        self.assertEqual(result[0]["affiliations"], ["Other University, Berlin, Germany"])
        self.assertEqual(decisions, [])
        self.assertTrue(any(item["code"] == "layout_affiliation_conflict" for item in reviews))

    def test_fragment_replacement_must_preserve_stable_affiliation_prefix(self):
        authors = [dict(
            self.authors[0],
            affiliations=["Example University", "Department of, Paris, France"],
        )]
        analysis = analyze_layout(context(self.blocks[:3] + [self.blocks[6]]), authors)
        result, decisions, _ = apply_layout_affiliations(authors, analysis)

        self.assertEqual(result[0]["affiliations"], ["Example University Paris, France"])
        self.assertEqual(decisions[0]["action"], "replace_fragmented_affiliation_from_pdf_layout")

    def test_unvalidated_conference_does_not_auto_fill(self):
        analysis = analyze_layout(context(self.blocks), self.authors)
        result, decisions, reviews = apply_layout_affiliations(
            self.authors,
            analysis,
            auto_fill_enabled=False,
        )

        self.assertEqual(result[0]["affiliations"], [])
        self.assertEqual(decisions, [])
        self.assertTrue(any(item.get("reason") == "conference_not_validated" for item in reviews))

    def test_lower_font_affiliation_fragment_is_not_matched_as_author(self):
        blocks = [
            block(0, 100, 700, 12, "Alice Smith"),
            block(1, 100, 688, 10, "Example Research LLC"),
            block(2, 100, 676, 10, "Paris, France"),
            block(3, 50, 650, 11, "Abstract"),
        ]
        authors = [
            {"name": "Alice Smith", "affiliations": [], "email": ""},
            {"name": "Example Research LLC", "affiliations": [], "email": ""},
        ]

        analysis = analyze_layout(context(blocks), authors)
        result, decisions, _ = apply_layout_affiliations(authors, analysis)

        self.assertEqual(analysis["dominant_author_font_size"], 12.0)
        self.assertEqual(analysis["matched_author_count"], 1)
        self.assertEqual(result[0]["affiliations"], ["Example Research LLC Paris, France"])
        self.assertEqual(result[1]["affiliations"], [])
        self.assertEqual(len(decisions), 1)

    def test_email_first_multiline_card_is_joined(self):
        blocks = [
            block(0, 100, 700, 12, "Alice Smith"),
            block(1, 100, 688, 10, "alice@example.org"),
            block(2, 80, 676, 10, "Example Institute for"),
            block(3, 100, 664, 10, "Security Research"),
            block(4, 100, 652, 10, "Paris, France"),
            block(5, 50, 630, 11, "Abstract"),
        ]
        authors = [{"name": "Alice Smith", "affiliations": [], "email": "alice@example.org"}]

        analysis = analyze_layout(context(blocks), authors)
        result, decisions, _ = apply_layout_affiliations(authors, analysis)

        self.assertEqual(
            result[0]["affiliations"],
            ["Example Institute for Security Research Paris, France"],
        )
        self.assertEqual(decisions[0]["action"], "fill_from_pdf_layout")

    def test_multilingual_and_acronym_organization_names(self):
        blocks = [
            block(0, 100, 700, 12, "Alice Smith"),
            block(1, 100, 688, 10, "alice@example.org"),
            block(2, 80, 676, 10, "Universidade do Porto and"),
            block(3, 100, 664, 10, "INESC TEC"),
            block(4, 100, 652, 10, "Porto, Portugal"),
            block(5, 50, 630, 11, "Abstract"),
        ]
        authors = [{"name": "Alice Smith", "affiliations": [], "email": "alice@example.org"}]

        analysis = analyze_layout(context(blocks), authors)
        result, _, _ = apply_layout_affiliations(authors, analysis)

        self.assertEqual(
            result[0]["affiliations"],
            ["Universidade do Porto and INESC TEC Porto, Portugal"],
        )

    def test_first_affiliation_line_is_confirmed_by_org_continuation(self):
        blocks = [
            block(0, 100, 700, 12, "Alice Smith"),
            block(1, 100, 688, 10, "alice@example.org"),
            block(2, 100, 676, 10, "Purple Mountain"),
            block(3, 100, 664, 10, "Laboratories"),
            block(4, 100, 652, 10, "Nanjing, China"),
            block(5, 50, 630, 11, "Abstract"),
        ]
        authors = [{"name": "Alice Smith", "affiliations": [], "email": "alice@example.org"}]

        analysis = analyze_layout(context(blocks), authors)
        result, _, _ = apply_layout_affiliations(authors, analysis)

        self.assertEqual(result[0]["affiliations"], ["Purple Mountain Laboratories Nanjing, China"])

    def test_unknown_short_org_requires_local_location_and_email_support(self):
        blocks = [
            block(0, 100, 700, 12, "Alice Smith"),
            block(1, 100, 688, 10, "Five Rings"),
            block(2, 100, 676, 10, "New York, NY, USA"),
            block(3, 100, 664, 10, "alice@example.org"),
            block(4, 50, 640, 11, "Abstract"),
        ]
        authors = [{"name": "Alice Smith", "affiliations": [], "email": ""}]

        analysis = analyze_layout(context(blocks), authors)
        result, decisions, _ = apply_layout_affiliations(authors, analysis)

        self.assertEqual(result[0]["affiliations"], ["Five Rings New York, NY, USA"])
        self.assertEqual(decisions[0]["validation_evidence_ids"], [
            "pdf:p1:b2",
            "pdf:p1:b3",
        ])

    def test_unknown_short_org_without_email_is_not_auto_filled(self):
        blocks = [
            block(0, 100, 700, 12, "Alice Smith"),
            block(1, 100, 688, 10, "Five Rings"),
            block(2, 100, 676, 10, "New York, NY, USA"),
            block(3, 50, 650, 11, "Abstract"),
        ]
        authors = [{"name": "Alice Smith", "affiliations": [], "email": ""}]

        analysis = analyze_layout(context(blocks), authors)
        result, decisions, _ = apply_layout_affiliations(authors, analysis)

        self.assertEqual(result[0]["affiliations"], [])
        self.assertEqual(decisions, [])

    def test_grouped_author_card_assigns_shared_institution_in_same_column(self):
        blocks = [
            block(0, 100, 700, 12, "Alice Smith"),
            block(1, 100, 688, 12, "Bob Jones"),
            block(2, 100, 672, 10, "alice@example.org"),
            block(3, 100, 660, 10, "bob@example.org"),
            block(4, 100, 648, 10, "Example University"),
            block(5, 100, 636, 10, "Paris, France"),
            block(6, 50, 620, 11, "Abstract"),
        ]
        authors = [
            {"name": "Alice Smith", "affiliations": [], "email": ""},
            {"name": "Bob Jones", "affiliations": [], "email": ""},
        ]

        analysis = analyze_layout(context(blocks), authors)
        result, decisions, _ = apply_layout_affiliations(authors, analysis)

        self.assertEqual(result[0]["affiliations"], ["Example University Paris, France"])
        self.assertEqual(result[1]["affiliations"], ["Example University Paris, France"])
        self.assertTrue(all(item["action"] == "fill_from_pdf_layout" for item in decisions))

    def test_supported_page_author_list_replaces_false_org_author(self):
        blocks = [
            block(0, 100, 700, 12, "Alice Smith"),
            block(1, 100, 688, 10, "Example University"),
            block(2, 100, 676, 10, "Paris, France"),
            block(3, 350, 700, 12, "Bob Jones"),
            block(4, 350, 688, 10, "Example Research LLC"),
            block(5, 350, 676, 10, "London, UK"),
            block(6, 50, 650, 11, "Abstract"),
        ]
        authors = [
            {"name": "Alice Smith", "affiliations": [], "email": ""},
            {"name": "Example Research LLC", "affiliations": [], "email": ""},
        ]

        rebuilt, decisions, _, discovery = reconcile_authors_from_layout(context(blocks), authors)

        self.assertTrue(discovery["fully_supported"])
        self.assertEqual([author["name"] for author in rebuilt], ["Alice Smith", "Bob Jones"])
        self.assertEqual(decisions[0]["action"], "rebuild_author_list_from_pdf_layout")
        self.assertIn("Example Research LLC", decisions[0]["removed_names"])

    def test_supported_page_author_list_adds_missing_author(self):
        authors = [{
            "order": 0,
            "name": "Alice Smith",
            "affiliations": ["Example University"],
            "email": "alice@example.org",
        }]

        rebuilt, decisions, _, discovery = reconcile_authors_from_layout(
            context(self.blocks),
            authors,
        )

        self.assertTrue(discovery["fully_supported"])
        self.assertEqual([author["name"] for author in rebuilt], ["Alice Smith", "Bob Jones"])
        self.assertEqual(rebuilt[0]["affiliations"], ["Example University"])
        self.assertEqual(rebuilt[1]["affiliations"], [])
        self.assertEqual(rebuilt[1]["affiliation_source"], "empty")
        self.assertEqual(decisions[0]["old_names"], ["Alice Smith"])

    def test_rebuild_preserves_matched_fields_and_roles_follow_page_order(self):
        authors = [
            {
                "order": 0,
                "name": "Bob Jones",
                "affiliations": ["Example Research"],
                "email": "bob@example.org",
            },
            {
                "order": 1,
                "name": "Alice Smith",
                "affiliations": ["Example University"],
                "email": "alice@example.org",
            },
        ]

        rebuilt, _, _, _ = reconcile_authors_from_layout(context(self.blocks), authors)
        rebuilt = apply_author_roles(rebuilt, {
            "corresponding_names": {"bob jones"},
            "equal_contribution_names": set(),
            "equal_contribution": True,
        })

        self.assertEqual([author["name"] for author in rebuilt], ["Alice Smith", "Bob Jones"])
        self.assertEqual([author["order"] for author in rebuilt], [0, 1])
        self.assertEqual(rebuilt[0]["email"], "alice@example.org")
        self.assertEqual(rebuilt[1]["email"], "bob@example.org")
        self.assertEqual([author["first_author"] for author in rebuilt], [True, False])
        self.assertEqual([author["corresponding"] for author in rebuilt], [False, True])
        self.assertEqual([get_export_author_rank(author, rebuilt) for author in rebuilt], [0, 1])

    def test_page_author_list_is_not_rebuilt_when_a_candidate_lacks_support(self):
        blocks = [
            block(0, 100, 700, 12, "Alice Smith"),
            block(1, 100, 688, 10, "Example University"),
            block(2, 350, 700, 12, "Bob Jones"),
            block(3, 50, 650, 11, "Abstract"),
        ]
        authors = [{"name": "Alice Smith", "affiliations": [], "email": ""}]

        rebuilt, decisions, _, discovery = reconcile_authors_from_layout(context(blocks), authors)

        self.assertFalse(discovery["fully_supported"])
        self.assertEqual(rebuilt, authors)
        self.assertEqual(decisions, [])

    def test_author_reconciliation_can_be_disabled_for_unvalidated_conference(self):
        authors = [{"name": "Alice Smith", "affiliations": [], "email": ""}]

        rebuilt, decisions, _, discovery = reconcile_authors_from_layout(
            context(self.blocks),
            authors,
            enabled=False,
        )

        self.assertTrue(discovery["fully_supported"])
        self.assertEqual(rebuilt, authors)
        self.assertEqual(decisions, [])

    def test_supported_missing_author_can_be_added_when_existing_authors_match_page(self):
        blocks = [
            block(0, 100, 700, 12, "Alice Smith"),
            block(1, 350, 700, 12, "Bob Jones"),
            block(2, 350, 688, 10, "Example University"),
            block(3, 50, 650, 11, "Abstract"),
        ]
        authors = [{"name": "Alice Smith", "affiliations": [], "email": ""}]

        rebuilt, decisions, _, discovery = reconcile_authors_from_layout(context(blocks), authors)

        self.assertFalse(discovery["fully_supported"])
        self.assertEqual([author["name"] for author in rebuilt], ["Alice Smith", "Bob Jones"])
        self.assertEqual(decisions[0]["action"], "rebuild_author_list_from_pdf_layout")

    def test_lower_author_font_is_discovered_from_supported_header_cards(self):
        blocks = [
            block(0, 100, 700, 10.959, "Alice Smith"),
            block(1, 100, 688, 9.963, "Example University"),
            block(2, 350, 700, 10.959, "Bob Jones"),
            block(3, 350, 688, 9.963, "Example Research"),
            block(4, 50, 650, 11, "Abstract"),
        ]
        rebuilt, decisions, _, discovery = reconcile_authors_from_layout(
            context(blocks), [{"name": "Alice Smith"}, {"name": "Bob Jones"}]
        )
        self.assertEqual(discovery["dominant_font_size"], 11.0)
        self.assertTrue(discovery["fully_supported"])
        self.assertEqual([author["name"] for author in rebuilt], ["Alice Smith", "Bob Jones"])

    def test_exact_page_names_restore_initial_punctuation_without_affiliation_support(self):
        blocks = [
            block(0, 80, 700, 10.959, "Harry W. H. Wong"),
            block(1, 300, 700, 10.959, "Jack P. K. Ma"),
            block(2, 50, 650, 11, "Abstract"),
        ]
        authors = [{"name": "Harry W H Wong"}, {"name": "Jack P K Ma"}]

        rebuilt, decisions, _, discovery = reconcile_authors_from_layout(context(blocks), authors)

        self.assertFalse(discovery["fully_supported"])
        self.assertEqual(
            [author["name"] for author in rebuilt],
            ["Harry W. H. Wong", "Jack P. K. Ma"],
        )
        self.assertEqual(decisions[0]["action"], "rebuild_author_list_from_pdf_layout")

    def test_single_initial_and_full_surname_remains_a_person_candidate(self):
        blocks = [
            block(0, 100, 700, 11, "N. Asokan"),
            block(1, 100, 688, 10, "Example University"),
            block(2, 350, 700, 11, "Alice Smith"),
            block(3, 350, 688, 10, "Example Research"),
            block(4, 50, 650, 11, "Abstract"),
        ]
        authors = [{"name": "N Asokan"}, {"name": "Alice Smith"}]

        rebuilt, _, _, discovery = reconcile_authors_from_layout(context(blocks), authors)

        self.assertEqual(discovery["candidates"][0]["name"], "N. Asokan")
        self.assertEqual([author["name"] for author in rebuilt], ["N. Asokan", "Alice Smith"])

    def test_full_width_repeated_affiliation_row_is_not_a_middle_author_card(self):
        blocks = [
            block(0, 80, 700, 11, "Alice Smith", width=80),
            block(1, 260, 700, 11, "Bob Jones", width=80),
            block(2, 440, 700, 11, "Carol White", width=80),
            block(
                3,
                50,
                688,
                10,
                "Example University Example University Example University",
                width=500,
            ),
            block(4, 50, 650, 11, "Abstract"),
        ]
        authors = [
            {"name": "Alice Smith", "affiliations": [], "email": ""},
            {"name": "Bob Jones", "affiliations": [], "email": ""},
            {"name": "Carol White", "affiliations": [], "email": ""},
        ]

        analysis = analyze_layout(context(blocks), authors)

        self.assertEqual(analysis["relations"], [])

    def test_numbered_affiliation_note_is_added_only_to_owning_card(self):
        blocks = [
            block(0, 80, 700, 11, "Alice Smith", width=80),
            block(1, 80, 688, 10, "Example University", width=100),
            block(2, 300, 700, 11, "Bob Jones", width=80),
            block(3, 300, 688, 10, "Example Research", width=90),
            block(4, 390, 691, 6, "1", width=4),
            block(5, 50, 650, 11, "Abstract"),
            block(6, 50, 120, 6, "1", width=4),
            block(
                7,
                55,
                116,
                8,
                "Part of the work was done while affiliated with Other Polytechnic University.",
                width=250,
            ),
        ]
        authors = [
            {"name": "Alice Smith", "affiliations": [], "email": ""},
            {"name": "Bob Jones", "affiliations": [], "email": ""},
        ]

        analysis = analyze_layout(context(blocks), authors)
        result, decisions, reviews = apply_layout_affiliations(authors, analysis)

        self.assertEqual(result[0]["affiliations"], ["Example University"])
        self.assertEqual(
            result[1]["affiliations"],
            ["Example Research", "Other Polytechnic University"],
        )
        self.assertTrue(any(
            item["action"] == "fill_affiliation_note_from_pdf_layout"
            and item["author"] == "Bob Jones"
            for item in decisions
        ))
        self.assertEqual(reviews, [])


if __name__ == "__main__":
    unittest.main()
