import csv
import importlib
import sys

import requests
from pathlib import Path


CRAWLER_ROOT = Path(__file__).resolve().parents[1]
SPIDER_DIR = CRAWLER_ROOT / "scripts" / "spider-pdf"
SOURCE_DISCOVERY_DIR = CRAWLER_ROOT / "scripts" / "source-discovery"
sys.path[:0] = [str(SPIDER_DIR), str(SOURCE_DISCOVERY_DIR)]
discover = importlib.import_module("discover")
spider = importlib.import_module("spider")

URL = "https://dblp.org/db/conf/crypto/crypto2024-1.html"


def _source_record() -> dict[str, object]:
    return {
        "conference": "crypto",
        "year": 2024,
        "source": "dblp",
        "backend": "dblp",
        "url": URL,
        "paper_count": "",
        "status": "success",
        "discovered_time": "test",
        "validation_status": "discovered",
    }


def _write_summary(path: Path, total: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file_obj:
        writer = csv.DictWriter(
            file_obj,
            fieldnames=["url", "venue", "year", "total", "downloaded", "missing_pdf_url", "error", "output_dir", "output_csv"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "url": URL,
                "venue": "crypto",
                "year": "2024",
                "total": total,
                "downloaded": 0,
                "missing_pdf_url": 0,
                "error": 0,
            }
        )


def _seed_validated_state(tmp_path: Path, total: int = 42) -> tuple[Path, Path, Path]:
    output_root = tmp_path / "download"
    summary_path = output_root / "summary.csv"
    manifest_path = tmp_path / "source_manifest.csv"
    _write_summary(summary_path, total)
    discover.save_source_manifest([_source_record()], manifest_path)
    discover.update_source_manifest_counts(manifest_path, {URL: total})
    return output_root, summary_path, manifest_path


def _patch_fetch(monkeypatch, result: list[object] | Exception) -> None:
    class FakeCrawler:
        def __init__(self, sleep_seconds: float = 0.0):
            pass

        def fetch_papers(self, url: str) -> list[object]:
            if isinstance(result, Exception):
                raise result
            return result

    monkeypatch.setattr(spider, "DBLPPDFCrawler", FakeCrawler)


def _run_validation(tmp_path: Path, output_root: Path, manifest_path: Path) -> dict[str, int | None]:
    urls_path = tmp_path / "urls.txt"
    urls_path.write_text(f"{URL}\n", encoding="utf-8")
    discover.save_source_manifest([_source_record()], manifest_path)
    counts = spider._save_metadata_only_summary(
        urls_path,
        output_root,
        "summary.csv",
        {"2024"},
        "dblp",
    )
    discover.update_source_manifest_counts(manifest_path, counts)
    return counts


def _read_row(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8-sig", newline="") as file_obj:
        return next(csv.DictReader(file_obj))


def test_failed_fetch_marks_previous_count_stale_and_manifest_failed(tmp_path, monkeypatch):
    output_root, summary_path, manifest_path = _seed_validated_state(tmp_path)
    _patch_fetch(monkeypatch, RuntimeError("offline test failure"))

    counts = _run_validation(tmp_path, output_root, manifest_path)

    summary = _read_row(summary_path)
    manifest = _read_row(manifest_path)
    assert counts == {URL: None}
    assert summary["total"] == ""
    assert summary["previous_total"] == "42"
    assert summary["error"] == "1"
    assert summary["validation_status"] == "failed"
    assert manifest["paper_count"] == ""
    assert manifest["previous_paper_count"] == "42"
    assert manifest["validation_status"] == "failed"


def test_successful_retry_replaces_stale_count(tmp_path, monkeypatch):
    output_root, summary_path, manifest_path = _seed_validated_state(tmp_path)
    _patch_fetch(monkeypatch, RuntimeError("offline test failure"))
    _run_validation(tmp_path, output_root, manifest_path)

    _patch_fetch(monkeypatch, [object(), object()])
    counts = _run_validation(tmp_path, output_root, manifest_path)

    summary = _read_row(summary_path)
    manifest = _read_row(manifest_path)
    assert counts == {URL: 2}
    assert summary["total"] == "2"
    assert summary["previous_total"] == ""
    assert summary["error"] == "0"
    assert summary["validation_status"] == "validated"
    assert manifest["paper_count"] == "2"
    assert manifest["previous_paper_count"] == ""
    assert manifest["validation_status"] == "validated"


def test_valid_zero_count_replaces_previous_positive_count(tmp_path, monkeypatch):
    output_root, summary_path, manifest_path = _seed_validated_state(tmp_path)
    _patch_fetch(monkeypatch, [])

    counts = _run_validation(tmp_path, output_root, manifest_path)

    summary = _read_row(summary_path)
    manifest = _read_row(manifest_path)
    assert counts == {URL: 0}
    assert summary["total"] == "0"
    assert summary["previous_total"] == ""
    assert summary["error"] == "0"
    assert summary["validation_status"] == "validated"
    assert manifest["paper_count"] == "0"
    assert manifest["previous_paper_count"] == ""
    assert manifest["validation_status"] == "validated"


def test_summary_counts_distinguish_unavailable_malformed_and_legacy_errors(tmp_path):
    summary_path = tmp_path / "summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8-sig") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=["url", "total", "error"])
        writer.writeheader()
        writer.writerows([
            {"url": "zero", "total": "0", "error": "0"},
            {"url": "legacy-error", "total": "12", "error": "1"},
            {"url": "blank", "total": "", "error": "0"},
            {"url": "malformed", "total": "not-a-count", "error": "0"},
            {"url": "missing", "error": "0"},
        ])

    assert spider._read_summary_counts(summary_path) == {
        "zero": 0,
        "legacy-error": None,
        "blank": None,
        "malformed": None,
        "missing": None,
    }
    assert spider._successful_existing_summary_row(
        {"blank": {"url": "blank", "total": "", "error": "0"}}, "blank"
    ) is None


def test_pmlr_identity_failure_during_year_filter_does_not_abort_batch(tmp_path, monkeypatch):
    bad_url = "https://proceedings.mlr.press/v999/bad.html"
    good_url = "https://proceedings.mlr.press/v200/good.html"
    urls_path = tmp_path / "pmlr_urls.txt"
    urls_path.write_text(f"{bad_url}\n{good_url}\n", encoding="utf-8")

    def parse_identity(url):
        if url == bad_url:
            raise requests.Timeout("identity lookup timed out")
        return "icml", "2024", "good"

    monkeypatch.setattr(spider, "_parse_pmlr_identity", parse_identity)
    monkeypatch.setattr(spider, "_count_pmlr_papers", lambda _url: 9)

    counts = spider._save_metadata_only_summary(
        urls_path,
        tmp_path / "download",
        "summary.csv",
        {"2024"},
        "pmlr",
    )

    rows = {
        row["url"]: row
        for row in csv.DictReader((tmp_path / "download" / "summary.csv").open(encoding="utf-8-sig", newline=""))
    }
    assert counts == {bad_url: None, good_url: 9}
    assert rows[bad_url]["validation_status"] == "failed"
    assert rows[bad_url]["total"] == ""
    assert rows[bad_url]["year"] == ""
    assert rows[good_url]["validation_status"] == "validated"
    assert rows[good_url]["total"] == "9"
