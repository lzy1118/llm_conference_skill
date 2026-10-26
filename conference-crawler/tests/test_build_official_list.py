from __future__ import annotations

import csv
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DISCOVERY_DIR = ROOT / "scripts" / "source-discovery"
SPIDER_DIR = ROOT / "scripts" / "spider-pdf"
sys.path[:0] = [str(SOURCE_DISCOVERY_DIR), str(SPIDER_DIR)]

import build_official_list  # noqa: E402
from core import DBLPPDFCrawler  # noqa: E402


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def test_dblp_fetch_skips_non_paper_entry_types(monkeypatch):
    payload = {
        "result": {
            "hits": {
                "@total": 2,
                "hit": [
                    {"info": {"type": "Conference and Workshop Papers", "title": "A paper"}},
                    {"info": {"type": "Editorship", "title": "Proceedings, Part I"}},
                ],
            }
        }
    }
    crawler = DBLPPDFCrawler(sleep_seconds=0)
    monkeypatch.setattr(crawler, "_get_with_retry", lambda *_args, **_kwargs: FakeResponse(payload))

    papers = crawler.fetch_papers("https://dblp.org/db/conf/asiacrypt/2020.html")

    assert [paper.title for paper in papers] == ["A paper"]


def test_official_list_filters_containers_and_deduplicates(tmp_path, monkeypatch):
    records = [{
        "conference": "crypto",
        "year": 2024,
        "source": "dblp",
        "backend": "dblp",
        "url": "https://dblp.org/db/conf/crypto/crypto2024.html",
        "paper_count": "",
        "status": "success",
        "discovered_time": "2026-01-01T00:00:00+00:00",
        "validation_status": "discovered",
    }]
    papers = [
        SimpleNamespace(title="Accepted Paper", doi="10.1234/paper"),
        SimpleNamespace(title="Duplicate record", doi="https://doi.org/10.1234/paper"),
        SimpleNamespace(title="Unique Without DOI", doi=""),
        SimpleNamespace(title="unique without doi", doi=""),
        SimpleNamespace(
            title=(
                "Advances in Cryptology - CRYPTO 2024 - Proceedings, Part I"
            ),
            doi="10.1234/volume",
        ),
    ]

    monkeypatch.setattr(build_official_list, "discover_proceedings_urls", lambda *_args: records)

    class StubCrawler:
        def __init__(self, **_kwargs):
            pass

        def fetch_papers(self, _url):
            return papers

    monkeypatch.setattr(build_official_list, "DBLPPDFCrawler", StubCrawler)
    manifest_path = tmp_path / "source_manifest.csv"

    rows = build_official_list.build_official_rows("crypto", [2024], manifest_path)

    assert [row["title"] for row in rows] == ["Accepted Paper", "Unique Without DOI"]
    with manifest_path.open(encoding="utf-8", newline="") as handle:
        manifest = list(csv.DictReader(handle))
    assert manifest[0]["paper_count"] == "2"
