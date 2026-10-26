import hashlib
import importlib
import sys
from pathlib import Path

import requests


CRAWLER_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DISCOVERY_DIR = CRAWLER_ROOT / "scripts" / "source-discovery"
sys.path.insert(0, str(SOURCE_DISCOVERY_DIR))
deadlines = importlib.import_module("deadlines")


CFP_HTML = b"""<!doctype html>
<html><head><title>NeurIPS 2024 Call for Papers</title></head><body>
<p>Abstract submission deadline: May 15, 2024 AoE</p>
<p>Full paper submission deadline: May 22, 2024 at 11:59 PM AoE</p>
<tr><td>June 15, 2024</td><td>First notification</td></tr>
<p>Camera-ready deadline: July 1, 2024</p>
</body></html>"""


class FakeResponse:
    def __init__(self, content: bytes, url: str):
        self.content = content
        self.url = url

    def raise_for_status(self) -> None:
        return None


def test_extracts_labeled_deadlines_and_excludes_other_dates():
    title, rows = deadlines.extract_deadlines(CFP_HTML)

    assert title == "NeurIPS 2024 Call for Papers"
    assert [(row["deadline_type"], row["deadline_date"]) for row in rows] == [
        ("abstract_submission", "2024-05-15"),
        ("full_paper_submission", "2024-05-22"),
    ]
    assert all(row["deadline_timezone"] == "AoE" for row in rows)
    assert all("submission deadline" in row["evidence_text"].lower() for row in rows)


def test_parses_date_before_submission_label():
    _title, rows = deadlines.extract_deadlines(
        "<html><body><table><tr><td>13 Feb 2024</td><td>Submission deadline</td></tr></table></body></html>"
    )

    assert [(row["deadline_type"], row["deadline_date"]) for row in rows] == [
        ("submission", "2024-02-13")
    ]


def test_invalid_or_unlabeled_dates_are_not_reported_as_deadlines():
    _title, rows = deadlines.extract_deadlines(
        "<html><body><p>Camera-ready deadline: 2024-02-30</p><p>Notification: May 2, 2024</p></body></html>"
    )

    assert rows == []


def test_collection_retains_official_url_hash_and_evidence(monkeypatch):
    url = "https://neurips.cc/Conferences/2024/CallForPapers"
    monkeypatch.setattr(deadlines.requests, "get", lambda *_args, **_kwargs: FakeResponse(CFP_HTML, url))

    rows = deadlines.collect_deadlines(["NeurIPS"], [2024])

    assert len(rows) == 2
    assert {row["source_url"] for row in rows} == {url}
    assert {row["source_kind"] for row in rows} == {"configured_official_cfp"}
    assert {row["source_sha256"] for row in rows} == {hashlib.sha256(CFP_HTML).hexdigest()}
    assert all(row["status"] == "parsed" and row["evidence_text"] for row in rows)


def test_fetch_failure_and_unconfigured_source_are_explicit(monkeypatch):
    def fail(*_args, **_kwargs):
        raise requests.Timeout("offline fixture")

    monkeypatch.setattr(deadlines.requests, "get", fail)
    failed = deadlines.collect_deadlines(["icml"], [2024])
    unconfigured = deadlines.collect_deadlines(["www"], [2024])

    assert failed[0]["status"] == "fetch_failed"
    assert failed[0]["deadline_date"] == ""
    assert "offline fixture" in failed[0]["error"]
    assert unconfigured[0]["status"] == "no_configured_source"
    assert unconfigured[0]["deadline_date"] == ""


def test_source_page_changes_are_kept_as_separate_observations(tmp_path, monkeypatch):
    url = "https://neurips.cc/Conferences/2024/CallForPapers"
    versions = [
        b"<html><body><p>Submission deadline: May 20, 2024</p></body></html>",
        b"<html><body><p>Submission deadline: May 22, 2024</p></body></html>",
    ]
    monkeypatch.setattr(
        deadlines.requests,
        "get",
        lambda *_args, **_kwargs: FakeResponse(versions.pop(0), url),
    )
    output = tmp_path / "deadlines.csv"

    deadlines.save_deadline_observations(deadlines.collect_deadlines(["neurips"], [2024]), output)
    deadlines.save_deadline_observations(deadlines.collect_deadlines(["neurips"], [2024]), output)

    text = output.read_text(encoding="utf-8-sig")
    assert "2024-05-20" in text
    assert "2024-05-22" in text
    assert text.count("configured_official_cfp") == 2
