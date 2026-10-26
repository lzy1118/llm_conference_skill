import unittest

from author_metadata.layout_classifier import classify_header_layout
from author_metadata.layout_relations import analyze_layout
from author_metadata.metadata_repair import repair_metadata
from author_metadata.pdf_context import PdfContext


def block(index, x, y, size, text, width=120, page=1):
    return {
        "block_id": f"pdf:p{page}:b{index}",
        "page": page,
        "bbox": [x, y, x + width, y + size],
        "x": x,
        "y": y,
        "font_size": size,
        "raw_text": text,
    }


def context(lines, blocks, title_lines=None, author_lines=None, affiliation_lines=None, email_lines=None):
    return PdfContext(
        first_page_text="\n".join(lines),
        first_page_lines=lines,
        page_lines={1: lines},
        title_lines=title_lines or [],
        author_lines=author_lines or [],
        affiliation_lines=affiliation_lines or [],
        email_lines=email_lines or [],
        preabstract_lines=lines,
        page_blocks={1: blocks},
        extractor_status={"pdfplumber": "ok", "pypdf": "ok"},
    )


class GeneralLayoutClassifierTest(unittest.TestCase):
    def test_classifies_multiple_independent_dimensions(self):
        lines = [
            "A General Extraction Framework:",
            "Evidence-Gated Metadata Repair",
            "Alice Smith1, Bob Jones2",
            "1 Example University, Paris, France",
            "2 Other Institute, London, UK",
            "{alice,bob}@example.org",
            "Alice Smith and Bob Jones contributed equally.",
        ]
        blocks = [
            block(0, 90, 740, 16, lines[0], 300),
            block(1, 90, 720, 16, lines[1], 300),
            block(2, 100, 690, 12, "Alice Smith1", 90),
            block(3, 240, 690, 12, "Bob Jones2", 90),
            block(4, 90, 665, 10, lines[3], 250),
            block(5, 90, 650, 10, lines[4], 250),
            block(6, 90, 635, 10, lines[5], 220),
        ]
        authors = [
            {"name": "Alice Smith", "affiliations": [], "email": ""},
            {"name": "Bob Jones", "affiliations": [], "email": ""},
        ]
        pdf_context = context(
            lines,
            blocks,
            title_lines=lines[:2],
            author_lines=[lines[2]],
            affiliation_lines=lines[3:5],
            email_lines=[lines[5]],
        )

        result = classify_header_layout(pdf_context, authors, analyze_layout(pdf_context, authors))

        self.assertEqual(result["dimensions"]["title"]["selected_type"], "multi_line_title")
        self.assertEqual(
            result["dimensions"]["author"]["selected_type"],
            "authors_with_numbered_affiliations",
        )
        self.assertEqual(
            result["dimensions"]["affiliation"]["selected_type"],
            "numbered_or_symbol_affiliation_list",
        )
        self.assertEqual(result["dimensions"]["email"]["selected_type"], "braced_shared_domain_emails")
        self.assertEqual(result["dimensions"]["role"]["selected_type"], "equal_contribution")

    def test_unknown_conference_receives_general_classification_and_repairs_cards(self):
        lines = [
            "A New Paper",
            "Alice Smith",
            "Example University",
            "Paris, France",
            "Bob Jones",
            "Other Research Institute",
            "London, UK",
        ]
        blocks = [
            block(0, 100, 700, 12, "Alice Smith"),
            block(1, 100, 688, 10, "Example University"),
            block(2, 100, 676, 10, "Paris, France"),
            block(3, 350, 700, 12, "Bob Jones"),
            block(4, 350, 688, 10, "Other Research Institute"),
            block(5, 350, 676, 10, "London, UK"),
        ]
        pdf_context = context(lines, blocks, title_lines=[lines[0]], author_lines=[lines[1], lines[4]])
        metadata = {
            "title": "A New Paper",
            "year": "2026",
            "abstract": "Abstract text.",
            "root": None,
            "authors": [
                {"name": "Alice Smith", "affiliations": [], "email": ""},
                {"name": "Bob Jones", "affiliations": [], "email": ""},
            ],
        }

        result = repair_metadata(metadata, pdf_context, conference_name="new_unknown_venue")
        classification = result["_extraction"]["candidates"]["layout_relations"]["classification"]

        self.assertTrue(classification["conference_independent"])
        self.assertEqual(classification["dimensions"]["author"]["selected_type"], "author_cards")
        self.assertEqual(
            [author["affiliations"] for author in result["authors"]],
            [["Example University Paris, France"], ["Other Research Institute London, UK"]],
        )

    def test_ambiguous_dimension_is_routed_to_review(self):
        pdf_context = context(["Unstructured heading text"], [], title_lines=[])
        result = classify_header_layout(pdf_context, [], {})

        self.assertTrue(any(
            item["code"] == "layout_dimension_unclassified"
            for item in result["review_reasons"]
        ))


if __name__ == "__main__":
    unittest.main()
