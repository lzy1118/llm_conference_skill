from __future__ import annotations

import csv
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


CORE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "spider-pdf" / "core.py"
SPEC = importlib.util.spec_from_file_location("conference_crawler_core_regressions", CORE_PATH)
core = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(core)


class FakeResponse:
    def __init__(self, content: bytes, content_type: str = "application/pdf", url: str = "https://example.test/paper"):
        self.content = content
        self.headers = {"Content-Type": content_type, "content-type": content_type}
        self.url = url

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def raise_for_status(self) -> None:
        return None


class FakeCookies:
    def set(self, *_args, **_kwargs) -> None:
        return None


class FakeSession:
    def __init__(self, response: FakeResponse):
        self.response = response
        self.headers = {}
        self.cookies = FakeCookies()

    def get(self, *_args, **_kwargs) -> FakeResponse:
        return self.response


class FakeBrowser:
    def execute_script(self, _script: str) -> str:
        return "test-agent"

    def get_cookies(self) -> list[dict[str, str]]:
        return []


def _download(core_module, backend: str, response: FakeResponse, target: Path, monkeypatch) -> bool:
    if backend == "dblp":
        crawler = core_module.DBLPPDFCrawler(sleep_seconds=0)
        paper = core_module.Paper(title="A paper", pdf_url=response.url)
        monkeypatch.setattr(crawler, "_get_pdf_or_html_response", lambda *_args, **_kwargs: response)
        crawler.download_pdf(paper, target.parent, 1)
        return paper.status == "downloaded"

    monkeypatch.setattr(core_module.requests, "Session", lambda: FakeSession(response))
    crawler_type = (
        core_module.SPIEEESeleniumCrawler
        if backend == "ieee"
        else core_module.ACMCCSSeleniumCrawler
    )
    crawler = object.__new__(crawler_type)
    crawler.timeout = 1
    crawler.browser = FakeBrowser()
    if backend == "ieee":
        return crawler.browser_download_pdf(response.url, target)
    crawler._with_browser_restart = lambda action: action()
    return crawler.download_pdf(response.url, target)


@pytest.mark.parametrize("backend", ["dblp", "ieee", "acm"])
def test_downloaders_reject_html_even_when_content_type_claims_pdf(tmp_path, monkeypatch, backend):
    response = FakeResponse(b"<html><body>login required</body></html>")
    target = tmp_path / f"{backend}.pdf"

    if backend == "dblp":
        with pytest.raises(ValueError, match="%PDF-"):
            _download(core, backend, response, target, monkeypatch)
    else:
        assert not _download(core, backend, response, target, monkeypatch)

    if backend == "dblp":
        assert not list(tmp_path.glob("*.pdf"))
    else:
        assert not target.exists()


@pytest.mark.parametrize("backend", ["dblp", "ieee", "acm"])
def test_downloaders_accept_pdf_signature_despite_generic_content_type(tmp_path, monkeypatch, backend):
    content = b"%PDF-1.7\nvalid fixture"
    response = FakeResponse(content, content_type="application/octet-stream")
    target = tmp_path / f"{backend}.pdf"

    assert _download(core, backend, response, target, monkeypatch)
    saved_path = tmp_path / "01_A paper.pdf" if backend == "dblp" else target
    assert saved_path.read_bytes() == content


def test_ieee_article_resolution_never_uses_a_nonmatching_doi():
    resolver = object.__new__(core.SPIEEEArticleResolver)
    resolver.crawler = SimpleNamespace(
        search=lambda **_kwargs: [
            core.IEEEPaper(title="Unrelated result", doi="10.9999/other", article_number="999")
        ]
    )

    assert resolver.find_article_number("10.1109/requested") == ""


def test_ieee_article_resolution_matches_normalized_doi():
    resolver = object.__new__(core.SPIEEEArticleResolver)
    resolver.crawler = SimpleNamespace(
        search=lambda **_kwargs: [
            core.IEEEPaper(
                title="Requested result",
                doi="https://doi.org/10.1109/REQUESTED.",
                article_number="123",
            )
        ]
    )

    assert resolver.find_article_number("10.1109/requested") == "123"


def test_dblp_html_fallback_excludes_non_inproceedings_entries(monkeypatch):
    html = """<html><body><ul>
      <li class="entry inproceedings"><span class="title">Accepted paper</span></li>
      <li class="entry proceedings"><span class="title">Proceedings, Part I</span></li>
      <li class="entry article"><span class="title">Journal article</span></li>
    </ul></body></html>"""
    crawler = core.DBLPPDFCrawler(sleep_seconds=0)
    monkeypatch.setattr(crawler, "_get_with_retry", lambda *_args, **_kwargs: SimpleNamespace(text=html))

    papers = crawler._fetch_papers_from_html("https://dblp.org/db/conf/crypto/crypto2024.html")

    assert [paper.title for paper in papers] == ["Accepted paper"]


def _seed_previous_dblp_output(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    url = "https://dblp.org/db/conf/crypto/crypto2024-1.html"
    urls_file = tmp_path / "urls.txt"
    urls_file.write_text(f"{url}\n", encoding="utf-8")
    output_root = tmp_path / "download"
    target_dir = output_root / "crypto" / "2024" / "crypto2024-1"
    pdf_dir = target_dir / "pdfs"
    pdf_dir.mkdir(parents=True)
    existing_pdf = pdf_dir / "01_Previous paper.pdf"
    existing_pdf.write_bytes(b"previous PDF")
    existing_csv = target_dir / "crypto2024-1_results.csv"
    existing_csv.write_text("previous metadata\n", encoding="utf-8")
    return urls_file, output_root, existing_pdf, existing_csv


class SuccessfulCrawler:
    def __init__(self, **_kwargs):
        pass

    def fetch_papers(self, _url: str):
        return [core.Paper(title="Replacement paper", ee_url="https://example.test/replacement")]

    def resolve_pdf_url(self, paper):
        return "https://example.test/replacement.pdf"

    def download_pdf(self, paper, output_dir: Path, index: int):
        target = output_dir / f"{index:02d}_{core.safe_filename(paper.title)}.pdf"
        target.write_bytes(b"replacement PDF")
        paper.pdf_path = str(target)
        paper.status = "downloaded"


def test_force_fetch_failure_preserves_previous_successful_directory(tmp_path, monkeypatch):
    urls_file, output_root, existing_pdf, existing_csv = _seed_previous_dblp_output(tmp_path)

    class FailingCrawler:
        def __init__(self, **_kwargs):
            pass

        def fetch_papers(self, _url: str):
            raise RuntimeError("temporary DBLP outage")

    monkeypatch.setattr(core, "DBLPPDFCrawler", FailingCrawler)

    core.run_dblp_batch(urls_file, output_root, "summary.csv", sleep=0, toc_sleep=0, force=True)

    assert existing_pdf.read_bytes() == b"previous PDF"
    assert existing_csv.read_text(encoding="utf-8") == "previous metadata\n"


def test_force_download_failure_preserves_previous_successful_directory(tmp_path, monkeypatch):
    urls_file, output_root, existing_pdf, existing_csv = _seed_previous_dblp_output(tmp_path)

    class FailingDownloadCrawler(SuccessfulCrawler):
        def download_pdf(self, *_args, **_kwargs):
            raise RuntimeError("temporary PDF outage")

    monkeypatch.setattr(core, "DBLPPDFCrawler", FailingDownloadCrawler)

    core.run_dblp_batch(urls_file, output_root, "summary.csv", sleep=0, toc_sleep=0, force=True)

    assert existing_pdf.read_bytes() == b"previous PDF"
    assert existing_csv.read_text(encoding="utf-8") == "previous metadata\n"
    assert not list((output_root / "crypto" / "2024").glob(".crypto2024-1.stage-*"))


def test_force_empty_fetch_preserves_previous_successful_directory(tmp_path, monkeypatch):
    urls_file, output_root, existing_pdf, existing_csv = _seed_previous_dblp_output(tmp_path)

    class EmptyCrawler:
        def __init__(self, **_kwargs):
            pass

        def fetch_papers(self, _url: str):
            return []

    monkeypatch.setattr(core, "DBLPPDFCrawler", EmptyCrawler)

    core.run_dblp_batch(urls_file, output_root, "summary.csv", sleep=0, toc_sleep=0, force=True)

    assert existing_pdf.read_bytes() == b"previous PDF"
    assert existing_csv.read_text(encoding="utf-8") == "previous metadata\n"
    assert not list((output_root / "crypto" / "2024").glob(".crypto2024-1.stage-*"))


def test_force_success_commits_final_pdf_paths(tmp_path, monkeypatch):
    urls_file, output_root, _existing_pdf, _existing_csv = _seed_previous_dblp_output(tmp_path)
    monkeypatch.setattr(core, "DBLPPDFCrawler", SuccessfulCrawler)

    core.run_dblp_batch(urls_file, output_root, "summary.csv", sleep=0, toc_sleep=0, force=True)

    target_dir = output_root / "crypto" / "2024" / "crypto2024-1"
    output_pdf = target_dir / "pdfs" / "01_Replacement paper.pdf"
    with (target_dir / "crypto2024-1_results.csv").open(encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert output_pdf.read_bytes() == b"replacement PDF"
    assert row["pdf_path"] == str(output_pdf)


def test_force_csv_write_failure_preserves_previous_successful_directory(tmp_path, monkeypatch):
    urls_file, output_root, existing_pdf, existing_csv = _seed_previous_dblp_output(tmp_path)
    monkeypatch.setattr(core, "DBLPPDFCrawler", SuccessfulCrawler)

    original_save_csv = core.save_csv

    def fail_staged_csv(rows, output_path):
        if ".stage-" in str(output_path):
            raise OSError("disk full")
        return original_save_csv(rows, output_path)

    monkeypatch.setattr(core, "save_csv", fail_staged_csv)

    with pytest.raises(OSError, match="disk full"):
        core.run_dblp_batch(urls_file, output_root, "summary.csv", sleep=0, toc_sleep=0, force=True)

    assert existing_pdf.read_bytes() == b"previous PDF"
    assert existing_csv.read_text(encoding="utf-8") == "previous metadata\n"
