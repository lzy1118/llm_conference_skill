from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


network = load_module(
    "generate_collaboration_network",
    ROOT / "conference-visualization" / "scripts" / "generate_collaboration_network.py",
)
collaboration = load_module(
    "collaboration_analysis",
    ROOT / "conference-collaboration-analysis" / "scripts" / "collaboration_analysis.py",
)


class CollaborationNetworkTest(unittest.TestCase):
    def test_year_range_filter_is_inclusive(self) -> None:
        rows = [
            {"conference": "CRYPTO", "year": "2020"},
            {"conference": "CRYPTO", "year": "2021"},
            {"conference": "CRYPTO", "year": "2022"},
            {"conference": "EUROCRYPT", "year": "2021"},
        ]
        filtered = collaboration.filter_rows(rows, "crypto", None, 2020, 2021)
        self.assertEqual([row["year"] for row in filtered], ["2020", "2021"])

    def test_collaboration_input_requires_paper_and_mode_columns(self) -> None:
        with self.assertRaisesRegex(ValueError, "paper_key"):
            collaboration.validate_input_rows([{"conference": "CRYPTO", "year": "2025"}], "institution")

    def test_dense_network_raises_the_render_floor(self) -> None:
        dense_edges = [[0, 1, 1, 1, "2025", "2025"] for _ in range(601)]
        dense_edges.append([0, 2, 2, 1, "2025", "2025"])
        self.assertEqual(network.choose_render_floor(dense_edges, 600), 2)

    def test_fragment_contains_filtered_network_and_no_document_wrapper(self) -> None:
        rows = [
            {
                "mode": "institution",
                "left_key": "a",
                "left_name": "Alpha University",
                "right_key": "b",
                "right_name": "Beta Lab",
                "shared_papers": "3",
                "conference_count": "2",
                "year_first": "2020",
                "year_last": "2021",
            },
            {
                "mode": "institution",
                "left_key": "a",
                "left_name": "Alpha University",
                "right_key": "c",
                "right_name": "Gamma Institute",
                "shared_papers": "1",
                "conference_count": "1",
                "year_first": "2021",
                "year_last": "2021",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            edge_path = Path(tmp) / "collaboration_edges.csv"
            with edge_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            nodes, edges, stats = network.build_network(network.read_csv(edge_path))
            fragment = network.render_fragment(
                network.DEFAULT_TEMPLATE.read_text(encoding="utf-8"),
                root_id="test-network",
                scope_label="CRYPTO 2020-2021 institution collaboration network",
                nodes=nodes,
                edges=edges,
                stats=stats,
                paper_count=4,
                minimum_threshold=1,
                default_threshold=2,
                top_edge_count=10,
            )

        self.assertEqual(stats["node_count"], 3)
        self.assertEqual(stats["edge_count"], 2)
        self.assertEqual(stats["repeated_edge_count"], 1)
        self.assertIn('data-threshold="2" aria-pressed="true"', fragment)
        self.assertIn("Alpha University", fragment)
        self.assertNotIn("<!doctype", fragment.casefold())
        self.assertNotIn("<html", fragment.casefold())
        self.assertNotIn("fetch(", fragment)
        self.assertNotIn("XMLHttpRequest", fragment)
        self.assertNotIn("/Users/", fragment)
        self.assertNotIn("__ROOT_ID__", fragment)


if __name__ == "__main__":
    unittest.main()
