import csv
import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.resolve_affiliations_from_sources import (
    SourceCandidate,
    accept_resolved_mapping,
    build_resolution_id,
    parse_confirmed_single_affiliation,
    parse_frontmatter_text,
    parse_dblp_hits,
    rank_source_candidates,
    read_resolution_queue,
    source_to_pdf_url,
    query_eprint_search_candidates,
    write_resolution_outputs,
)


class AffiliationResolutionTests(unittest.TestCase):
    def test_read_resolution_queue_generates_stable_resolution_id(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "queue.csv"
            path.write_text(
                "conference,year,paper_id,title,issue,authors_count,affiliations_count,authors,affiliations\n"
                "CRYPTO,2025,442,Breaking X,author_affiliation_count_mismatch,2,1,Alice | Bob,MIT\n",
                encoding="utf-8",
            )

            tasks = read_resolution_queue(path)

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].resolution_id, "CRYPTO_2025_442")
        self.assertEqual(tasks[0].authors, ["Alice", "Bob"])
        self.assertEqual(tasks[0].affiliations, ["MIT"])

    def test_build_resolution_id_is_filename_safe(self):
        self.assertEqual(build_resolution_id("ASIACRYPT", "2025", "12/3"), "ASIACRYPT_2025_12_3")

    def test_rank_source_candidates_prefers_strict_title_and_author_match(self):
        candidates = [
            SourceCandidate(
                resolution_id="CRYPTO_2025_1",
                source_type="web",
                url="https://example.com/near",
                title="A Near Title",
                authors=["Alice"],
                doi="",
                score=0.0,
                retrieved_at="2026-04-29T00:00:00+00:00",
            ),
            SourceCandidate(
                resolution_id="CRYPTO_2025_1",
                source_type="springer",
                url="https://link.springer.com/chapter/10.1007/example",
                title="Exact Paper Title",
                authors=["Alice", "Bob"],
                doi="10.1007/example",
                score=0.0,
                retrieved_at="2026-04-29T00:00:00+00:00",
            ),
        ]

        ranked = rank_source_candidates("Exact Paper Title", ["Alice", "Bob"], candidates)

        self.assertEqual(ranked[0].source_type, "springer")
        self.assertGreaterEqual(ranked[0].score, 0.98)

    def test_parse_dblp_hits_creates_eprint_candidate(self):
        payload = {
            "result": {
                "hits": {
                    "hit": [
                        {
                            "info": {
                                "title": "Exact Paper Title.",
                                "authors": {
                                    "author": [
                                        {"text": "Alice Example"},
                                        {"text": "Bob Researcher"},
                                    ]
                                },
                                "ee": "https://eprint.iacr.org/2025/2008",
                                "url": "https://dblp.org/rec/journals/iacr/Example25",
                            }
                        }
                    ]
                }
            }
        }

        candidates = parse_dblp_hits("CRYPTO_2025_1", payload, "2026-04-29T00:00:00+00:00")

        self.assertEqual(candidates[0].source_type, "eprint")
        self.assertEqual(candidates[0].url, "https://eprint.iacr.org/2025/2008")
        self.assertEqual(candidates[0].authors, ["Alice Example", "Bob Researcher"])

    def test_source_to_pdf_url_converts_eprint_page_to_pdf(self):
        self.assertEqual(
            source_to_pdf_url("https://eprint.iacr.org/2025/2008"),
            "https://eprint.iacr.org/2025/2008.pdf",
        )

    def test_parse_frontmatter_text_extracts_author_affiliations(self):
        text = """
        Exact Paper Title
        Authors: Alice Example; Bob Researcher
        Affiliations:
        Alice Example: Massachusetts Institute of Technology
        Bob Researcher: ETH Zurich
        """

        parsed = parse_frontmatter_text("Exact Paper Title", ["Alice Example", "Bob Researcher"], text)

        self.assertTrue(parsed["title_match"])
        self.assertTrue(parsed["authors_match"])
        self.assertFalse(parsed["needs_manual_review"])
        self.assertEqual(parsed["author_affiliations"][0]["author"], "Alice Example")
        self.assertEqual(
            parsed["author_affiliations"][0]["affiliations"],
            ["Massachusetts Institute of Technology"],
        )

    def test_parse_confirmed_single_affiliation_maps_all_authors(self):
        text = "Two-Server Private Information Retrieval in Sublinear Time and Quasilinear Space Alexandra Henzinger Seyoon Ragavan"

        parsed = parse_confirmed_single_affiliation(
            "Two-Server Private Information Retrieval in Sublinear Time and Quasilinear Space",
            ["Alexandra Henzinger", "Seyoon Ragavan"],
            ["MIT"],
            text,
        )

        self.assertFalse(parsed["needs_manual_review"])
        self.assertEqual(len(parsed["author_affiliations"]), 2)
        self.assertEqual(parsed["author_affiliations"][1]["affiliations"], ["MIT"])

    def test_accept_resolved_mapping_requires_source_evidence_and_high_confidence(self):
        parsed = {
            "title_match": True,
            "authors_match": True,
            "needs_manual_review": False,
            "author_affiliations": [
                {
                    "author": "Alice Example",
                    "affiliations": ["Massachusetts Institute of Technology"],
                    "evidence_text": "Alice Example: Massachusetts Institute of Technology",
                    "confidence": 0.95,
                }
            ],
        }

        accepted = accept_resolved_mapping(
            resolution_id="CRYPTO_2025_1",
            conference="CRYPTO",
            year=2025,
            paper_id="1",
            title="Exact Paper Title",
            article_tag="CRYPTO-Exact Paper Title",
            source_url="https://link.springer.com/chapter/10.1007/example",
            title_score=0.99,
            parsed=parsed,
        )

        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]["name"], "Alice Example")
        self.assertEqual(accepted[0]["inst"], "Massachusetts Institute of Technology")
        self.assertEqual(accepted[0]["article_tag"], "CRYPTO-Exact Paper Title")

    def test_write_resolution_outputs_uses_expected_files(self):
        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            resolved = [
                {
                    "resolution_id": "CRYPTO_2025_1",
                    "conference": "CRYPTO",
                    "year": 2025,
                    "paper_id": "1",
                    "title": "Exact Paper Title",
                    "name": "Alice Example",
                    "author_order": 0,
                    "inst": "Massachusetts Institute of Technology",
                    "source_url": "https://example.com",
                    "evidence_text": "Alice Example: Massachusetts Institute of Technology",
                    "confidence": 0.95,
                    "classification_source": "source_pdf",
                    "classification_confidence": 0.95,
                    "classification_reason": "source_evidence",
                    "article_tag": "CRYPTO-Exact Paper Title",
                }
            ]
            unresolved = []
            parsed = [{"resolution_id": "CRYPTO_2025_1", "needs_manual_review": False}]

            write_resolution_outputs(output_dir, resolved, unresolved, parsed)

            merge_path = output_dir / "merge_candidates_us_rows.csv"
            self.assertTrue(merge_path.exists())
            with merge_path.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["name"], "Alice Example")
            report = json.loads((output_dir / "resolution_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["resolved_us_rows"], 1)

    def test_cli_runs_from_workspace_root(self):
        with TemporaryDirectory() as directory:
            queue = Path(directory) / "queue.csv"
            output = Path(directory) / "resolution"
            queue.write_text(
                "conference,year,paper_id,title,issue,authors_count,affiliations_count,authors,affiliations\n"
                "CRYPTO,2025,442,Breaking X,author_affiliation_count_mismatch,2,1,Alice | Bob,MIT\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    "python3",
                    "scripts/resolve_affiliations_from_sources.py",
                    "--queue",
                    str(queue),
                    "--output-dir",
                    str(output),
                ],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
