import unittest
from unittest.mock import patch

from author_metadata.pdf_context import (
    PdfContext,
    _extract_pypdf_supplement,
    _merge_line_fragments,
    extract_abstract_from_pdf_context,
)


class PdfBlockMergeTest(unittest.TestCase):
    def test_pypdf_supplement_failure_does_not_abort_pdf_processing(self):
        class BrokenReader:
            @property
            def metadata(self):
                raise RuntimeError("missing AES backend")

        with patch("author_metadata.pdf_context.PdfReader", return_value=BrokenReader()):
            links, metadata, status, page_lines = _extract_pypdf_supplement("encrypted.pdf")

        self.assertEqual(links, [])
        self.assertEqual(metadata, {})
        self.assertEqual(status, "error:RuntimeError")
        self.assertEqual(page_lines, {})

    def test_merges_adjacent_word_fragments_but_keeps_columns_separate(self):
        blocks = [
            {"block_id": "a", "page": 1, "bbox": [100, 600, 135, 610], "x": 100, "y": 600, "font_size": 10, "raw_text": "Songfeng"},
            {"block_id": "b", "page": 1, "bbox": [140, 600, 150, 610], "x": 140, "y": 600, "font_size": 10, "raw_text": "Lu"},
            {"block_id": "c", "page": 1, "bbox": [300, 600, 335, 610], "x": 300, "y": 600, "font_size": 10, "raw_text": "Other"},
        ]

        merged = _merge_line_fragments(blocks)

        self.assertEqual([item["raw_text"] for item in merged], ["Songfeng Lu", "Other"])

    def test_does_not_merge_compact_affiliation_lines_across_columns(self):
        blocks = [
            {"block_id": "a", "page": 1, "bbox": [100, 600, 245, 610], "x": 100, "y": 600, "font_size": 10, "raw_text": "University of Electronic Science"},
            {"block_id": "b", "page": 1, "bbox": [252, 600, 420, 610], "x": 252, "y": 600, "font_size": 10, "raw_text": "Southern University of Science"},
        ]

        merged = _merge_line_fragments(blocks)

        self.assertEqual(len(merged), 2)

    def test_extracts_abstract_until_keywords(self):
        context = PdfContext(
            "", [], {
                1: [
                    "Paper title",
                    "Abstract—This paper studies metadata extraction.",
                    "It keeps field-level evidence.",
                    "Keywords: PDF, metadata",
                    "1 Introduction",
                ],
            }, [], [], [], [], [],
        )

        self.assertEqual(
            extract_abstract_from_pdf_context(context),
            "This paper studies metadata extraction. It keeps field-level evidence.",
        )


if __name__ == "__main__":
    unittest.main()
