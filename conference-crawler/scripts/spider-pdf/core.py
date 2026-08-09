#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# 七个会议共用的抓取核心。
# - 直接走 DBLP PDF 解析：CRYPTO / EUROCRYPT / ASIACRYPT / NDSS / USENIX Security
# - 需要 IEEE 浏览器辅助流程：IEEE S&P
# - 需要 ACM 浏览器辅助流程：CCS

import csv
import html
import json
import re
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import InvalidSessionIdException, NoSuchWindowException, TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


DBLP_API_HOST_FALLBACKS = ["dblp.org", "dblp.uni-trier.de", "dblp.dagstuhl.de"]
IEEE_SEARCH_PAGE = "https://ieeexplore.ieee.org/search/searchresult.jsp"
IEEE_SEARCH_API = "https://ieeexplore.ieee.org/rest/search"
IEEE_DOCUMENT_PAGE = "https://ieeexplore.ieee.org/document/{article_number}"
CHROME_PROFILE_COPY_IGNORE = shutil.ignore_patterns("Singleton*", "RunningChromeVersion")


@dataclass
class Paper:
    title: str = ""
    authors: str = ""
    venue: str = ""
    year: str = ""
    pages: str = ""
    doi: str = ""
    ee_url: str = ""
    dblp_url: str = ""
    pdf_url: str = ""
    pdf_path: str = ""
    status: str = ""


@dataclass
class BatchResult:
    url: str = ""
    venue: str = ""
    year: str = ""
    total: int = 0
    downloaded: int = 0
    missing_pdf_url: int = 0
    error: int = 0
    output_dir: str = ""
    output_csv: str = ""


@dataclass
class SPPaper:
    title: str = ""
    authors: str = ""
    year: str = ""
    pages: str = ""
    doi: str = ""
    ee_url: str = ""
    dblp_url: str = ""
    article_number: str = ""
    document_url: str = ""
    pdf_url: str = ""
    pdf_path: str = ""
    status: str = ""


@dataclass
class CCSPaper:
    title: str = ""
    authors: str = ""
    year: str = ""
    pages: str = ""
    doi: str = ""
    ee_url: str = ""
    dblp_url: str = ""
    document_url: str = ""
    pdf_url: str = ""
    pdf_path: str = ""
    status: str = ""


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]", "_", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:180] or "paper"


def is_workshop_title(title: str) -> bool:
    """Skip workshop records before any PDF resolution or browser request."""
    return bool(re.search(r"\bworkshop\b", html.unescape(title or ""), flags=re.IGNORECASE))


def title_match_key(name: str) -> str:
    name = html.unescape(name)
    name = re.sub(r"\\(?:mathbb|mathrm|mathbf|mathit|text|displaystyle)\s*", "", name)
    name = name.replace("$", "").replace("{", "").replace("}", "").replace("_", "")
    name = re.sub(r"[^a-zA-Z0-9]+", " ", name)
    return re.sub(r"\s+", " ", name).strip().lower()


def title_from_pdf_filename(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"^[a-zA-Z_&]+20\d{2}(?:[-_]\d+)?__+", "", stem)
    stem = re.sub(r"^[a-zA-Z_&]+20\d{2}(?:[-_]\d+)?[_-]*", "", stem)
    stem = re.sub(r"^\d+\s*[_-]+\s*", "", stem)
    stem = stem.replace("_", " ")
    return re.sub(r"\s+", " ", stem).strip()


def find_existing_flat_pdf(year_dir: Path, slug: str, title: str, index: int, widths: tuple[int, ...] = (2, 3)) -> Path | None:
    # 兼容历史产物：旧脚本把 PDF 直接放在 conference/year/ 下。
    if not year_dir.exists():
        return None
    safe_title = safe_filename(title)
    candidates: List[Path] = []
    for width in widths:
        number = f"{index:0{width}d}"
        candidates.extend(
            [
                year_dir / f"{number}_{safe_title}.pdf",
                year_dir / f"{slug}__{number}_{safe_title}.pdf",
                year_dir / f"{slug}_{number}_{safe_title}.pdf",
            ]
        )
    for candidate in candidates:
        if candidate.exists() and candidate.stat().st_size > 0:
            return candidate

    title_key = title_match_key(title)
    for candidate in year_dir.glob("*.pdf"):
        if candidate.stat().st_size <= 0:
            continue
        if title_match_key(title_from_pdf_filename(candidate.name)) == title_key:
            return candidate
    return None


def chrome_service(driver_path: str) -> Service:
    return Service(driver_path) if driver_path else Service()


def save_csv(rows: List[Any], output_path: Path) -> None:
    if not rows:
        return
    fieldnames = list(asdict(rows[0]).keys())
    with open(output_path, "w", newline="", encoding="utf-8-sig") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def save_summary(rows: List[BatchResult], output_path: Path) -> None:
    fieldnames = list(asdict(BatchResult()).keys())
    with open(output_path, "w", newline="", encoding="utf-8-sig") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def load_urls(urls_file: Path) -> List[str]:
    urls: List[str] = []
    with open(urls_file, encoding="utf-8") as file_obj:
        for line in file_obj:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            urls.append(line)
    return urls


def load_existing_statuses(csv_path: Path, keys: List[str]) -> dict[str, dict[str, str]]:
    # 复用历史结果，让重跑时只补未完成的论文。
    if not csv_path.exists():
        return {}
    with open(csv_path, encoding="utf-8-sig", newline="") as file_obj:
        rows = list(csv.DictReader(file_obj))
    existing: dict[str, dict[str, str]] = {}
    for row in rows:
        for key in keys:
            value = row.get(key) or ""
            if value:
                existing[value] = row
                break
    return existing


def parse_generic_toc_identity(url: str) -> tuple[str, str, str, str]:
    # 通用 DBLP 分会场 slug 解析，例如 crypto2024-3。
    path = urlparse(url).path
    match = re.search(r"/db/conf/([^/]+)/([^/]+)\.html$", path)
    if not match:
        raise ValueError(f"无法解析 TOC 信息: {url}")
    venue = match.group(1)
    slug = match.group(2)
    slug_match = re.search(r"(\d{4})(?:-(\d+))?$", slug)
    if not slug_match:
        raise ValueError(f"无法从 slug 解析年份: {url}")
    return venue, slug_match.group(1), slug_match.group(2) or "", slug


def parse_sp_ccs_toc_identity(url: str) -> tuple[str, str, str]:
    # SP / CCS 使用单一年份 slug，例如 sp2024 / ccs2024。
    path = urlparse(url).path
    match = re.search(r"/db/conf/([^/]+)/([a-z]+)(\d{4})\.html$", path)
    if not match:
        raise ValueError(f"无法解析 TOC 信息: {url}")
    return match.group(1), match.group(3), match.group(2) + match.group(3)


def to_uni_trier_toc_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(netloc="dblp.uni-trier.de").geturl()


class DBLPPDFCrawler:
    def __init__(self, timeout: int = 30, sleep_seconds: float = 1.0, browser_session: "AttachedChromeCookieSession | None" = None):
        self.timeout = timeout
        self.sleep_seconds = sleep_seconds
        self.browser_session = browser_session
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
        )

    def _get_pdf_or_html_response(self, url: str, referer: str = "") -> requests.Response:
        if self.browser_session and ("springer.com" in url or "springernature.com" in url or "doi.org" in url):
            return self.browser_session.get(url, referer=referer, timeout=self.timeout)
        return self._get_with_retry(url, timeout=self.timeout)

    def _get_with_retry(self, url: str, max_attempts: int = 5, backoff_seconds: float | None = None, **kwargs) -> requests.Response:
        backoff_seconds = max(self.sleep_seconds, 2.0) if backoff_seconds is None else backoff_seconds
        last_error: requests.RequestException | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                response = self.session.get(url, **kwargs)
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_error = exc
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                retriable_status = status_code in {429, 500, 502, 503, 504}
                retriable_network = isinstance(exc, (requests.ConnectionError, requests.Timeout))
                if (not retriable_status and not retriable_network) or attempt == max_attempts:
                    raise
                sleep_seconds = backoff_seconds * attempt
                print(f"[重试] GET {url} status={status_code} attempt={attempt}/{max_attempts} sleep={sleep_seconds:.1f}s")
                time.sleep(sleep_seconds)
        raise RuntimeError(f"请求失败: {url}") from last_error

    @staticmethod
    def _toc_key_from_url(toc_url: str) -> str:
        parsed = urlparse(toc_url)
        path = parsed.path.strip("/")
        if not path.startswith("db/") or not path.endswith(".html"):
            raise ValueError(f"不支持的 DBLP TOC URL: {toc_url}")
        return f"{path[:-5]}.bht"

    @staticmethod
    def _api_candidates_from_toc_url(toc_url: str) -> List[str]:
        parsed = urlparse(toc_url)
        host = parsed.netloc or "dblp.org"
        ordered_hosts = [host] + [fallback for fallback in DBLP_API_HOST_FALLBACKS if fallback != host]
        return [f"https://{candidate_host}/search/publ/api" for candidate_host in ordered_hosts]

    @staticmethod
    def _normalize_authors(raw_authors: object) -> str:
        if isinstance(raw_authors, dict):
            raw_authors = raw_authors.get("author", [])
        if isinstance(raw_authors, dict):
            raw_authors = [raw_authors]
        authors: List[str] = []
        if isinstance(raw_authors, list):
            for item in raw_authors:
                if isinstance(item, dict):
                    authors.append(str(item.get("text", "")).strip())
                elif item:
                    authors.append(str(item).strip())
        return ", ".join(author for author in authors if author)

    def _fetch_papers_from_html(self, toc_url: str) -> List[Paper]:
        # 当 publ API 不稳定时，直接回退到 DBLP TOC HTML 页面解析。
        html_url = to_uni_trier_toc_url(toc_url)
        response = self._get_with_retry(html_url, timeout=self.timeout)
        soup = BeautifulSoup(response.text, "lxml")
        papers: List[Paper] = []
        year_match = re.search(r"(19|20)\d{2}", toc_url)
        year = year_match.group(0) if year_match else ""

        for entry in soup.select("li.entry"):
            title_node = entry.select_one("span.title")
            if title_node is None:
                continue

            author_nodes = entry.select('span[itemprop="author"]')
            authors = ", ".join(node.get_text(" ", strip=True) for node in author_nodes if node.get_text(" ", strip=True))

            doi = ""
            ee_url = ""
            for anchor in entry.select("nav.publ a[href]"):
                href = (anchor.get("href") or "").strip()
                if "doi.org/" in href and not doi:
                    ee_url = href
                    doi = href.split("doi.org/", 1)[1]
                    break

            dblp_url = ""
            for anchor in entry.select("nav.publ a[href]"):
                href = (anchor.get("href") or "").strip()
                if "/rec/" in href and href.endswith(".html"):
                    dblp_url = href
                    break

            pages = ""
            pages_node = entry.select_one("span[itemprop='pagination']")
            if pages_node is not None:
                pages = pages_node.get_text(" ", strip=True)

            papers.append(
                Paper(
                    title=title_node.get_text(" ", strip=True),
                    authors=authors,
                    venue="",
                    year=year,
                    pages=pages,
                    doi=doi,
                    ee_url=ee_url,
                    dblp_url=dblp_url,
                )
            )

        if not papers:
            raise RuntimeError(f"HTML 回退解析失败：{toc_url}")
        return papers

    def fetch_papers(self, toc_url: str) -> List[Paper]:
        # 通过 DBLP publ API 分页拉取完整 TOC，而不是直接抓 HTML。
        toc_key = self._toc_key_from_url(toc_url)
        papers: List[Paper] = []
        offset = 0
        page_size = 100
        api_candidates = self._api_candidates_from_toc_url(toc_url)
        api_timeout = min(self.timeout, 12)
        while True:
            params = {"q": f"toc:{toc_key}:", "h": page_size, "f": offset, "format": "json"}
            last_error: Exception | None = None
            response = None
            for api_url in api_candidates:
                try:
                    response = self._get_with_retry(
                        api_url,
                        params=params,
                        timeout=api_timeout,
                        max_attempts=2,
                        backoff_seconds=max(self.sleep_seconds, 1.0),
                    )
                    break
                except requests.RequestException as exc:
                    last_error = exc
                    print(f"[警告] DBLP API 失败 {api_url}: {exc}")
            if response is None:
                print(f"[警告] 所有 DBLP API 镜像都失败，回退到 HTML 解析：{toc_url}")
                return self._fetch_papers_from_html(toc_url)
            payload = response.json()
            hits_block = payload.get("result", {}).get("hits", {})
            hits = hits_block.get("hit", [])
            if isinstance(hits, dict):
                hits = [hits]
            if not hits:
                break
            for item in hits:
                info: Dict[str, object] = item.get("info", {})
                papers.append(
                    Paper(
                        title=str(info.get("title", "") or ""),
                        authors=self._normalize_authors(info.get("authors", {})),
                        venue=str(info.get("venue", "") or ""),
                        year=str(info.get("year", "") or ""),
                        pages=str(info.get("pages", "") or ""),
                        doi=str(info.get("doi", "") or ""),
                        ee_url=str(info.get("ee", "") or ""),
                        dblp_url=str(info.get("url", "") or ""),
                    )
                )
            total = int(str(hits_block.get("@total", len(papers))) or len(papers))
            offset += len(hits)
            if offset >= total:
                break
            time.sleep(self.sleep_seconds)
        return papers

    def resolve_pdf_url(self, paper: Paper) -> str:
        # 适用于 ee 页面直接暴露 PDF 元信息或链接的会议。
        if not paper.ee_url:
            return ""
        response = self._get_pdf_or_html_response(paper.ee_url)
        content_type = response.headers.get("Content-Type", "")
        if "pdf" in content_type.lower() or response.url.endswith(".pdf"):
            return response.url
        soup = BeautifulSoup(response.text, "lxml")
        access_tag = soup.find("meta", attrs={"name": "access"})
        if access_tag and str(access_tag.get("content", "")).strip().lower() == "no":
            raise PermissionError(f"访问受限，无法下载 PDF: {paper.ee_url}")
        tag = soup.find("meta", attrs={"name": "citation_pdf_url"})
        if tag and tag.get("content"):
            return str(tag["content"]).strip()
        for anchor in soup.find_all("a", href=True):
            href = str(anchor["href"]).strip()
            if ".pdf" in href.lower():
                return urljoin(response.url, href)
        for source in soup.find_all(src=True):
            src = str(source["src"]).strip()
            if ".pdf" in src.lower():
                return urljoin(response.url, src)
        return ""

    def download_pdf(self, paper: Paper, output_dir: Path, index: int) -> None:
        if not paper.pdf_url:
            paper.status = "missing_pdf_url"
            return
        filename = f"{index:02d}_{safe_filename(paper.title)}.pdf"
        target = output_dir / filename
        if target.exists() and target.stat().st_size > 0:
            paper.pdf_path = str(target)
            paper.status = "exists"
            return
        response = self._get_pdf_or_html_response(paper.pdf_url, referer=paper.ee_url)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        content = response.content
        if not content:
            raise ValueError(f"PDF 内容为空: {paper.pdf_url}")
        if "pdf" not in content_type.lower() and not content.lstrip().startswith(b"%PDF-"):
            html_prefix = content[:4096].decode("utf-8", errors="ignore").lower()
            if 'meta name="access" content="no"' in html_prefix or "meta name='access' content='no'" in html_prefix:
                raise PermissionError(f"访问受限，无法下载 PDF: {paper.pdf_url}")
            raise ValueError(f"返回内容不是 PDF: {paper.pdf_url}")
        with open(target, "wb") as file_obj:
            file_obj.write(content)
        paper.pdf_path = str(target)
        paper.status = "downloaded"


class AttachedChromeCookieSession:
    def __init__(self, driver_path: str, debugger_address: str, timeout: int = 30):
        self.timeout = timeout
        self.debugger_address = debugger_address
        options = Options()
        options.debugger_address = debugger_address
        self.browser = webdriver.Chrome(service=chrome_service(driver_path), options=options)

    def _build_requests_session(self, referer: str = "", accept: str = "") -> requests.Session:
        session = requests.Session()
        user_agent = self.browser.execute_script("return navigator.userAgent")
        headers = {"User-Agent": user_agent}
        if referer:
            headers["Referer"] = referer
        if accept:
            headers["Accept"] = accept
        session.headers.update(headers)
        for cookie in self.browser.get_cookies():
            session.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain"), path=cookie.get("path", "/"))
        return session

    def get(self, url: str, referer: str = "", timeout: int = 30) -> requests.Response:
        session = self._build_requests_session(referer=referer, accept="application/pdf,application/octet-stream;q=0.9,text/html;q=0.8,*/*;q=0.7")
        response = session.get(url, timeout=max(timeout, self.timeout), allow_redirects=True)
        response.raise_for_status()
        return response

    def close(self) -> None:
        # 这里连接的是用户手动启动的浏览器，不主动关闭整个 Chrome。
        return


@dataclass
class IEEEPaper:
    title: str = ""
    publication_title: str = ""
    publication_date: str = ""
    doi: str = ""
    article_number: str = ""
    list_abstract: str = ""
    full_abstract: str = ""
    document_url: str = ""


class IEEEXploreCrawler:
    def __init__(self, timeout: int = 25, sleep_seconds: float = 1.0):
        self.timeout = timeout
        self.sleep_seconds = sleep_seconds
        self.session = requests.Session()
        self.base_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
        }

    def _search_referer(self, keyword: str) -> str:
        return f"{IEEE_SEARCH_PAGE}?newsearch=true&queryText={quote_plus(keyword)}"

    @staticmethod
    def _clean_html_text(text: Any) -> str:
        if text is None:
            return ""
        if isinstance(text, list):
            text = " ".join(str(x) for x in text)
        return BeautifulSoup(str(text), "lxml").get_text(" ", strip=True)

    def _init_cookie(self, keyword: str) -> None:
        params = {"newsearch": "true", "queryText": keyword}
        headers = {**self.base_headers, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
        try:
            response = self.session.get(IEEE_SEARCH_PAGE, params=params, headers=headers, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"[警告] 初始化搜索页 cookie 失败：{exc}")

    def search(self, keyword: str, pages: int = 1, rows_per_page: int = 25, year_range: str = "") -> List[IEEEPaper]:
        # 供 SP 使用，把 DOI 映射到 IEEE article number。
        self._init_cookie(keyword)
        results: List[IEEEPaper] = []
        headers = {
            **self.base_headers,
            "Accept": "application/json,text/plain,*/*",
            "Content-Type": "application/json",
            "Origin": "https://ieeexplore.ieee.org",
            "Referer": self._search_referer(keyword),
        }
        for page in range(1, pages + 1):
            payload: Dict[str, Any] = {"newsearch": True, "queryText": keyword, "pageNumber": page, "rowsPerPage": rows_per_page}
            if year_range:
                payload["publicationYear"] = year_range
            print(f"[搜索] keyword={keyword!r}, page={page}, rows={rows_per_page}")
            try:
                response = self.session.post(IEEE_SEARCH_API, json=payload, headers=headers, timeout=self.timeout)
                response.raise_for_status()
            except requests.RequestException as exc:
                print(f"[错误] 搜索接口请求失败：{exc}")
                break
            try:
                data = response.json()
            except json.JSONDecodeError:
                print("[错误] 搜索接口没有返回 JSON，可能被拦截。")
                break
            records = data.get("records", [])
            if not records:
                break
            for item in records:
                article_number = str(item.get("articleNumber", "") or "")
                results.append(
                    IEEEPaper(
                        title=self._clean_html_text(item.get("articleTitle", "")),
                        publication_title=self._clean_html_text(item.get("publicationTitle", "")),
                        publication_date=str(item.get("publicationDate", "") or ""),
                        doi=str(item.get("doi", "") or ""),
                        article_number=article_number,
                        list_abstract=self._clean_html_text(item.get("abstract", "")),
                        document_url=IEEE_DOCUMENT_PAGE.format(article_number=article_number) if article_number else "",
                    )
                )
            time.sleep(self.sleep_seconds)
        return results


class SPIEEESeleniumCrawler:
    def __init__(self, driver_path: str, timeout: int = 30, sleep_seconds: float = 5.0, user_data_dir: str = "", profile_directory: str = ""):
        self.timeout = timeout
        self.sleep_seconds = sleep_seconds
        self.download_dir: str | None = None
        self.temp_user_data_dir: str | None = None
        options = Options()
        options.page_load_strategy = "eager"
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1440,1200")
        if user_data_dir:
            source_dir = Path(user_data_dir)
            temp_dir = Path(tempfile.mkdtemp(prefix="selenium_chrome_profile_"))
            if source_dir.exists():
                shutil.copytree(
                    source_dir,
                    temp_dir,
                    dirs_exist_ok=True,
                    ignore=CHROME_PROFILE_COPY_IGNORE,
                )
                for name in ["SingletonCookie", "SingletonLock", "SingletonSocket"]:
                    (temp_dir / name).unlink(missing_ok=True)
            self.temp_user_data_dir = str(temp_dir)
            options.add_argument(f"--user-data-dir={self.temp_user_data_dir}")
        if profile_directory:
            options.add_argument(f"--profile-directory={profile_directory}")
        service = chrome_service(driver_path)
        self.browser = webdriver.Chrome(service=service, options=options)
        self.browser.set_page_load_timeout(min(self.timeout, 20))
        self.wait = WebDriverWait(self.browser, self.timeout)

    def set_download_dir(self, download_dir: str) -> None:
        self.download_dir = download_dir
        self.browser.execute_cdp_cmd("Page.setDownloadBehavior", {"behavior": "allow", "downloadPath": download_dir})

    def close(self) -> None:
        self.browser.quit()
        if self.temp_user_data_dir:
            shutil.rmtree(self.temp_user_data_dir, ignore_errors=True)

    def _extract_metadata_from_document_page(self, article_number: str) -> Dict[str, object]:
        self.browser.get(IEEE_DOCUMENT_PAGE.format(article_number=article_number))
        time.sleep(8)
        metadata_json = self.browser.execute_script("""
            if (window.xplGlobal && window.xplGlobal.document && window.xplGlobal.document.metadata) {
                return JSON.stringify(window.xplGlobal.document.metadata);
            }
            return "";
        """)
        if metadata_json:
            try:
                return json.loads(metadata_json)
            except json.JSONDecodeError:
                pass
        source = self.browser.page_source
        match = re.search(r"xplGlobal\.document\.metadata\s*=\s*(\{.*?\});", source, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                return {}
        return {}

    def _dismiss_cookie_banner(self) -> None:
        selectors = ["button.osano-cm-accept-all", "button.osano-cm-dialog__close", "button[aria-label='Accept']", "button[mode='primary']"]
        for selector in selectors:
            try:
                elements = self.browser.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    if element.is_displayed() and element.is_enabled():
                        self.browser.execute_script("arguments[0].click();", element)
                        time.sleep(2)
                        return
            except Exception:
                continue

    def _extract_stamp_link_from_page(self, article_number: str) -> str:
        source = self.browser.page_source
        patterns = [
            rf"https://ieeexplore\.ieee\.org/stamp/stamp\.jsp\?tp=&arnumber={article_number}",
            rf"/stamp/stamp\.jsp\?tp=&arnumber={article_number}",
            rf"https://ieeexplore\.ieee\.org/stampPDF/getPDF\.jsp\?tp=&arnumber={article_number}",
            rf"/stampPDF/getPDF\.jsp\?tp=&arnumber={article_number}",
        ]
        for pattern in patterns:
            match = re.search(pattern, source)
            if match:
                link = match.group(0)
                return link if link.startswith("http") else f"https://ieeexplore.ieee.org{link}"
        return ""

    def resolve_pdf_url(self, article_number: str) -> str:
        metadata = self._extract_metadata_from_document_page(article_number)
        self._dismiss_cookie_banner()
        candidates = []
        for key in ["pdfPath", "pdfUrl", "pdf_link", "documentLink"]:
            value = metadata.get(key)
            if isinstance(value, str) and value:
                candidates.append(value)
        stamp_link = self._extract_stamp_link_from_page(article_number)
        if stamp_link:
            candidates.append(stamp_link)
        candidates.extend([
            f"https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber={article_number}",
            f"https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={article_number}",
        ])
        normalized = []
        for candidate in candidates:
            if candidate.startswith("http"):
                normalized.append(candidate)
            elif candidate.startswith("/"):
                normalized.append(f"https://ieeexplore.ieee.org{candidate}")
        return normalized[0] if normalized else ""

    @staticmethod
    def _extract_iframe_src_from_html(html: str) -> str:
        match = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if not match:
            return ""
        src = match.group(1)
        if src.startswith("//"):
            return f"https:{src}"
        if src.startswith("/"):
            return f"https://ieeexplore.ieee.org{src}"
        return src

    def browser_download_pdf(self, pdf_url: str, target: Path) -> bool:
        # 先拿浏览器会话 cookie，再用 requests 下载，稳定性更高。
        target.unlink(missing_ok=True)
        session = requests.Session()
        user_agent = self.browser.execute_script("return navigator.userAgent")
        session.headers.update({"User-Agent": user_agent, "Referer": "https://ieeexplore.ieee.org/"})
        for cookie in self.browser.get_cookies():
            session.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain"), path=cookie.get("path", "/"))
        response = session.get(pdf_url, timeout=max(self.timeout, 60), allow_redirects=True)
        response.raise_for_status()
        ctype = (response.headers.get("content-type") or "").lower()
        if "pdf" in ctype:
            target.write_bytes(response.content)
            return target.exists() and target.stat().st_size > 0
        iframe_src = self._extract_iframe_src_from_html(response.text)
        if not iframe_src:
            return False
        pdf_response = session.get(iframe_src, timeout=max(self.timeout, 60), allow_redirects=True)
        pdf_response.raise_for_status()
        if "pdf" not in (pdf_response.headers.get("content-type") or "").lower():
            return False
        target.write_bytes(pdf_response.content)
        return target.exists() and target.stat().st_size > 0


class SPIEEEArticleResolver:
    def __init__(self, sleep_seconds: float = 5.0):
        self.crawler = IEEEXploreCrawler(sleep_seconds=sleep_seconds)

    def find_article_number(self, doi: str) -> str:
        results = self.crawler.search(keyword=f'"DOI":{doi}', pages=1, rows_per_page=5)
        for result in results:
            if result.doi == doi and result.article_number:
                return result.article_number
        for result in results:
            if result.article_number:
                return result.article_number
        return ""


class ACMCCSSeleniumCrawler:
    def __init__(self, driver_path: str, timeout: int = 40, sleep_seconds: float = 8.0, user_data_dir: str = ""):
        self.driver_path = driver_path
        self.timeout = timeout
        self.sleep_seconds = sleep_seconds
        self.user_data_dir = user_data_dir
        self.temp_user_data_dir: str | None = None
        self.browser = self._launch_browser()

    def _build_options(self) -> Options:
        if self.temp_user_data_dir:
            shutil.rmtree(self.temp_user_data_dir, ignore_errors=True)
            self.temp_user_data_dir = None
        options = Options()
        options.page_load_strategy = "eager"
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1440,1200")
        if self.user_data_dir:
            source_dir = Path(self.user_data_dir)
            temp_dir = Path(tempfile.mkdtemp(prefix="selenium_ccs_profile_"))
            if source_dir.exists():
                shutil.copytree(
                    source_dir,
                    temp_dir,
                    dirs_exist_ok=True,
                    ignore=CHROME_PROFILE_COPY_IGNORE,
                )
                for name in ["SingletonCookie", "SingletonLock", "SingletonSocket"]:
                    (temp_dir / name).unlink(missing_ok=True)
            self.temp_user_data_dir = str(temp_dir)
            options.add_argument(f"--user-data-dir={self.temp_user_data_dir}")
        return options

    def _launch_browser(self):
        browser = webdriver.Chrome(service=chrome_service(self.driver_path), options=self._build_options())
        browser.set_page_load_timeout(min(self.timeout, 25))
        return browser

    def _reopen_browser(self) -> None:
        try:
            self.browser.quit()
        except Exception:
            pass
        self.browser = self._launch_browser()

    def _with_browser_restart(self, action):
        # CCS 页面可能把浏览器标签页或会话打掉，这里自动重建并重试一次。
        try:
            return action()
        except (InvalidSessionIdException, NoSuchWindowException) as exc:
            print(f"[警告] 浏览器会话失效，正在重建: {exc}")
            self._reopen_browser()
            return action()
        except WebDriverException as exc:
            message = str(exc).lower()
            if "target window already closed" in message or "web view not found" in message or "invalid session id" in message:
                print(f"[警告] 浏览器窗口关闭，正在重建: {exc}")
                self._reopen_browser()
                return action()
            raise

    def close(self) -> None:
        try:
            self.browser.quit()
        except Exception:
            pass
        if self.temp_user_data_dir:
            shutil.rmtree(self.temp_user_data_dir, ignore_errors=True)

    @staticmethod
    def _extract_pdf_url(html: str, page_url: str, doi: str) -> str:
        patterns = [
            rf"https://dl\.acm\.org/doi/pdf/{re.escape(doi)}",
            rf"/doi/pdf/{re.escape(doi)}",
            rf"https://dl\.acm\.org/doi/pdf/10\.1145/[0-9.]+",
            rf"/doi/pdf/10\.1145/[0-9.]+",
        ]
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                value = match.group(0)
                return value if value.startswith("http") else f"https://dl.acm.org{value}"
        page_doi_match = re.search(r"https://dl\.acm\.org/doi/(10\.1145/[0-9.]+)", page_url)
        if page_doi_match:
            return f"https://dl.acm.org/doi/pdf/{page_doi_match.group(1)}"
        return ""

    def resolve_pdf_url(self, paper: CCSPaper) -> str:
        # 用真实浏览器访问 ACM DOI 页面，处理 Cloudflare/JS 挑战。
        if not paper.doi:
            return ""

        def do_resolve() -> str:
            candidates = [f"https://dl.acm.org/doi/{paper.doi}"]
            if paper.ee_url:
                candidates.append(paper.ee_url)
            for url in candidates:
                try:
                    self.browser.get(url)
                except Exception:
                    pass
                time.sleep(max(self.sleep_seconds, 6.0))
                page_url = self.browser.current_url
                html = self.browser.page_source
                if "Just a moment" in html or "challenge" in page_url:
                    time.sleep(max(self.sleep_seconds, 6.0))
                    html = self.browser.page_source
                pdf_url = self._extract_pdf_url(html, page_url, paper.doi)
                if pdf_url:
                    paper.document_url = page_url
                    return pdf_url
            return ""

        return self._with_browser_restart(do_resolve)

    def download_pdf(self, pdf_url: str, target: Path) -> bool:
        def do_download() -> bool:
            target.unlink(missing_ok=True)
            session = requests.Session()
            user_agent = self.browser.execute_script("return navigator.userAgent")
            session.headers.update({"User-Agent": user_agent, "Referer": "https://dl.acm.org/"})
            for cookie in self.browser.get_cookies():
                session.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain"), path=cookie.get("path", "/"))
            response = session.get(pdf_url, timeout=max(self.timeout, 60), allow_redirects=True)
            response.raise_for_status()
            if "pdf" not in (response.headers.get("content-type") or "").lower():
                return False
            target.write_bytes(response.content)
            return target.exists() and target.stat().st_size > 0

        return self._with_browser_restart(do_download)


def run_dblp_batch(urls_file: Path, output_root: Path, summary_csv: str, sleep: float = 2.0, toc_sleep: float = 8.0, years: set[str] | None = None, force: bool = False, debugger_address: str = "", driver_path: str = "", output_venue: str = "") -> None:
    # 面向 DBLP 友好型会议的批量入口。
    browser_session = AttachedChromeCookieSession(driver_path=driver_path, debugger_address=debugger_address) if debugger_address else None
    crawler = DBLPPDFCrawler(sleep_seconds=sleep, browser_session=browser_session)
    urls = load_urls(urls_file)
    if years:
        urls = [url for url in urls if parse_generic_toc_identity(url)[1] in years]
    output_root.mkdir(parents=True, exist_ok=True)
    summary_rows: List[BatchResult] = []
    try:
        print(f"[信息] 待处理 TOC 页面数: {len(urls)}")
        for toc_index, url in enumerate(urls, start=1):
            venue, year, part, slug = parse_generic_toc_identity(url)
            target_venue = output_venue or venue
            year_dir = output_root / target_venue / year
            target_dir = year_dir / slug
            pdf_dir = target_dir / "pdfs"
            csv_path = target_dir / f"{slug}_results.csv"
            if force and target_dir.exists():
                shutil.rmtree(target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            pdf_dir.mkdir(parents=True, exist_ok=True)
            existing_statuses = load_existing_statuses(csv_path, ["ee_url", "title"])
            print(f"[TOC] {toc_index}/{len(urls)} {slug}")
            try:
                papers = crawler.fetch_papers(url)
            except Exception as exc:
                print(f"[错误] 跳过 {slug}: {exc}")
                summary_rows.append(BatchResult(url=url, venue=target_venue, year=year, total=0, downloaded=0, missing_pdf_url=0, error=1, output_dir=str(pdf_dir), output_csv=str(csv_path)))
                continue
            for paper_index, paper in enumerate(papers, start=1):
                if is_workshop_title(paper.title):
                    paper.status = "skipped_workshop"
                    print(f"[跳过Workshop] {slug} {paper_index}/{len(papers)} {paper.title}")
                    continue
                existing = existing_statuses.get(paper.ee_url) or existing_statuses.get(paper.title)
                target = pdf_dir / f"{paper_index:02d}_{safe_filename(paper.title)}.pdf"
                if target.exists() and target.stat().st_size > 0:
                    paper.pdf_path = str(target)
                    paper.status = "exists"
                    print(f"[跳过PDF] {slug} {paper_index}/{len(papers)} {paper.title}")
                    continue
                flat_pdf = None if force else find_existing_flat_pdf(year_dir, slug, paper.title, paper_index)
                if flat_pdf:
                    paper.pdf_url = existing.get("pdf_url", "") if existing else ""
                    paper.pdf_path = str(flat_pdf)
                    paper.status = "exists"
                    print(f"[复用旧PDF] {slug} {paper_index}/{len(papers)} {paper.title}")
                    continue
                if existing and existing.get("status") in {"downloaded", "exists", "missing_pdf_url"}:
                    paper.pdf_url = existing.get("pdf_url", "") or ""
                    paper.pdf_path = existing.get("pdf_path", "") or ""
                    paper.status = existing.get("status", "") or ""
                    print(f"[跳过] {slug} {paper_index}/{len(papers)} {paper.title}")
                    continue
                print(f"[处理] {slug} {paper_index}/{len(papers)} {paper.title}")
                try:
                    paper.pdf_url = crawler.resolve_pdf_url(paper)
                    crawler.download_pdf(paper, output_dir=pdf_dir, index=paper_index)
                except Exception as exc:
                    paper.status = f"error: {exc}"
                time.sleep(sleep)
            save_csv(papers, csv_path)
            downloaded = sum(1 for paper in papers if paper.status in {"downloaded", "exists"})
            missing_pdf_url = sum(1 for paper in papers if paper.status == "missing_pdf_url")
            errors = sum(1 for paper in papers if paper.status.startswith("error:"))
            summary_rows.append(BatchResult(url=url, venue=target_venue, year=year, total=len(papers), downloaded=downloaded, missing_pdf_url=missing_pdf_url, error=errors, output_dir=str(pdf_dir), output_csv=str(csv_path)))
            print(f"[完成] {slug} downloaded={downloaded} missing_pdf_url={missing_pdf_url} error={errors}")
            if toc_index < len(urls):
                print(f"[休眠] TOC 间隔 {toc_sleep} 秒")
                time.sleep(toc_sleep)
    finally:
        if browser_session:
            browser_session.close()
    save_summary(summary_rows, output_root / summary_csv)


def run_sp_batch(urls_file: Path, output_root: Path, summary_csv: str, driver_path: str, user_data_dir: str = "", profile_directory: str = "", start_year: int = 0, start_index: int = 0, sleep: float = 5.0, toc_sleep: float = 15.0, output_venue: str = "") -> None:
    # SP 需要 IEEE 搜索接口和浏览器辅助下载 PDF。
    urls = load_urls(urls_file)
    if start_year > 0:
        urls = [url for url in urls if int(parse_sp_ccs_toc_identity(url)[1]) >= start_year]
    output_root.mkdir(parents=True, exist_ok=True)
    dblp_crawler = DBLPPDFCrawler(sleep_seconds=sleep)
    resolver = SPIEEEArticleResolver(sleep_seconds=sleep)
    ieee_crawler = SPIEEESeleniumCrawler(driver_path=driver_path, sleep_seconds=sleep, user_data_dir=user_data_dir, profile_directory=profile_directory)
    summary_rows: List[BatchResult] = []
    try:
        for toc_index, url in enumerate(urls, start=1):
            venue, year, slug = parse_sp_ccs_toc_identity(url)
            target_venue = output_venue or venue
            year_dir = output_root / target_venue / year
            target_dir = year_dir / slug
            pdf_dir = target_dir / "pdfs"
            csv_path = target_dir / f"{slug}_results.csv"
            target_dir.mkdir(parents=True, exist_ok=True)
            pdf_dir.mkdir(parents=True, exist_ok=True)
            ieee_crawler.set_download_dir(str(pdf_dir))
            existing_statuses = load_existing_statuses(csv_path, ["doi", "title"])
            print(f"[TOC] {toc_index}/{len(urls)} {slug}")
            dblp_papers = dblp_crawler.fetch_papers(url)
            papers: List[SPPaper] = []
            toc_start_index = start_index if start_index > 0 and start_year > 0 and int(year) == start_year else 1
            for index, dblp_paper in enumerate(dblp_papers, start=1):
                if index < toc_start_index:
                    continue
                paper = SPPaper(title=dblp_paper.title, authors=dblp_paper.authors, year=dblp_paper.year, pages=dblp_paper.pages, doi=dblp_paper.doi, ee_url=dblp_paper.ee_url, dblp_url=dblp_paper.dblp_url)
                papers.append(paper)
                if is_workshop_title(paper.title):
                    paper.status = "skipped_workshop"
                    print(f"[跳过Workshop] {slug} {index}/{len(dblp_papers)} {paper.title}")
                    save_csv(papers, csv_path)
                    continue
                target = pdf_dir / f"{index:03d}_{safe_filename(paper.title)}.pdf"
                if target.exists() and target.stat().st_size > 0:
                    paper.pdf_path = str(target)
                    paper.status = "exists"
                    print(f"[跳过PDF] {slug} {index}/{len(dblp_papers)} {paper.title}")
                    save_csv(papers, csv_path)
                    continue
                flat_pdf = find_existing_flat_pdf(year_dir, slug, paper.title, index)
                if flat_pdf:
                    paper.pdf_path = str(flat_pdf)
                    paper.status = "exists"
                    print(f"[复用旧PDF] {slug} {index}/{len(dblp_papers)} {paper.title}")
                    save_csv(papers, csv_path)
                    continue
                existing = existing_statuses.get(paper.doi) or existing_statuses.get(paper.title)
                if existing and existing.get("status") in {"downloaded", "exists", "missing_doi", "missing_article_number", "missing_pdf_url"}:
                    paper.article_number = existing.get("article_number", "") or ""
                    paper.document_url = existing.get("document_url", "") or ""
                    paper.pdf_url = existing.get("pdf_url", "") or ""
                    paper.pdf_path = existing.get("pdf_path", "") or ""
                    paper.status = existing.get("status", "") or ""
                    print(f"[跳过] {slug} {index}/{len(dblp_papers)} {paper.title}")
                    save_csv(papers, csv_path)
                    continue
                print(f"[处理] {slug} {index}/{len(dblp_papers)} {paper.title}")
                try:
                    if not paper.doi:
                        paper.status = "missing_doi"
                    else:
                        paper.article_number = resolver.find_article_number(paper.doi)
                        if paper.article_number:
                            paper.document_url = IEEE_DOCUMENT_PAGE.format(article_number=paper.article_number)
                        paper.pdf_url = ieee_crawler.resolve_pdf_url(paper.article_number) if paper.article_number else ""
                        if paper.pdf_url and ieee_crawler.browser_download_pdf(paper.pdf_url, target):
                            paper.pdf_path = str(target)
                            paper.status = "downloaded"
                        elif paper.pdf_url:
                            paper.status = f"browser_download_failed: {paper.pdf_url}"
                        else:
                            paper.status = "missing_pdf_url"
                except Exception as exc:
                    paper.status = f"error: {exc}"
                save_csv(papers, csv_path)
                time.sleep(sleep)
            save_csv(papers, csv_path)
            downloaded = sum(1 for paper in papers if paper.status in {"downloaded", "exists"})
            missing_pdf_url = sum(1 for paper in papers if paper.status == "missing_pdf_url")
            errors = sum(1 for paper in papers if paper.status.startswith("error:"))
            summary_rows.append(BatchResult(url=url, venue=target_venue, year=year, total=len(papers), downloaded=downloaded, missing_pdf_url=missing_pdf_url, error=errors, output_dir=str(pdf_dir), output_csv=str(csv_path)))
            save_summary(summary_rows, output_root / summary_csv)
            print(f"[完成] {slug} downloaded={downloaded} missing_pdf_url={missing_pdf_url} error={errors}")
            if toc_index < len(urls):
                print(f"[休眠] TOC 间隔 {toc_sleep} 秒")
                time.sleep(toc_sleep)
    finally:
        ieee_crawler.close()
    save_summary(summary_rows, output_root / summary_csv)


def run_ccs_batch(urls_file: Path, output_root: Path, summary_csv: str, driver_path: str, user_data_dir: str = "", sleep: float = 8.0, toc_sleep: float = 20.0, years: set[str] | None = None) -> None:
    # CCS 需要 ACM 浏览器辅助下载 PDF。
    urls = load_urls(urls_file)
    if years:
        urls = [url for url in urls if parse_sp_ccs_toc_identity(url)[1] in years]
    output_root.mkdir(parents=True, exist_ok=True)
    dblp_crawler = DBLPPDFCrawler(sleep_seconds=sleep)
    ccs_crawler = ACMCCSSeleniumCrawler(driver_path=driver_path, sleep_seconds=sleep, user_data_dir=user_data_dir)
    summary_rows: List[BatchResult] = []
    try:
        for toc_index, url in enumerate(urls, start=1):
            venue, year, slug = parse_sp_ccs_toc_identity(url)
            year_dir = output_root / venue / year
            target_dir = year_dir / slug
            pdf_dir = target_dir / "pdfs"
            csv_path = target_dir / f"{slug}_results.csv"
            target_dir.mkdir(parents=True, exist_ok=True)
            pdf_dir.mkdir(parents=True, exist_ok=True)
            existing_statuses = load_existing_statuses(csv_path, ["doi", "ee_url", "title"])
            print(f"[TOC] {toc_index}/{len(urls)} {slug}")
            dblp_papers = dblp_crawler.fetch_papers(url)
            papers: List[CCSPaper] = []
            for index, dblp_paper in enumerate(dblp_papers, start=1):
                paper = CCSPaper(title=dblp_paper.title, authors=dblp_paper.authors, year=dblp_paper.year, pages=dblp_paper.pages, doi=dblp_paper.doi, ee_url=dblp_paper.ee_url, dblp_url=dblp_paper.dblp_url)
                papers.append(paper)
                if is_workshop_title(paper.title):
                    paper.status = "skipped_workshop"
                    print(f"[跳过Workshop] {slug} {index}/{len(dblp_papers)} {paper.title}")
                    save_csv(papers, csv_path)
                    continue
                target = pdf_dir / f"{index:03d}_{safe_filename(paper.title)}.pdf"
                if target.exists() and target.stat().st_size > 0:
                    paper.pdf_path = str(target)
                    paper.status = "exists"
                    print(f"[跳过PDF] {slug} {index}/{len(dblp_papers)} {paper.title}")
                    save_csv(papers, csv_path)
                    continue
                flat_pdf = find_existing_flat_pdf(year_dir, slug, paper.title, index)
                if flat_pdf:
                    paper.pdf_path = str(flat_pdf)
                    paper.status = "exists"
                    print(f"[复用旧PDF] {slug} {index}/{len(dblp_papers)} {paper.title}")
                    save_csv(papers, csv_path)
                    continue
                existing = existing_statuses.get(paper.doi) or existing_statuses.get(paper.ee_url) or existing_statuses.get(paper.title)
                if existing and existing.get("status") in {"downloaded", "exists", "missing_pdf_url"}:
                    paper.document_url = existing.get("document_url", "") or ""
                    paper.pdf_url = existing.get("pdf_url", "") or ""
                    paper.pdf_path = existing.get("pdf_path", "") or ""
                    paper.status = existing.get("status", "") or ""
                    print(f"[跳过] {slug} {index}/{len(dblp_papers)} {paper.title}")
                    save_csv(papers, csv_path)
                    continue
                print(f"[处理] {slug} {index}/{len(dblp_papers)} {paper.title}")
                try:
                    paper.pdf_url = ccs_crawler.resolve_pdf_url(paper)
                    if paper.pdf_url and ccs_crawler.download_pdf(paper.pdf_url, target):
                        paper.pdf_path = str(target)
                        paper.status = "downloaded"
                    else:
                        paper.status = "missing_pdf_url"
                except Exception as exc:
                    paper.status = f"error: {exc}"
                save_csv(papers, csv_path)
                time.sleep(sleep)
            save_csv(papers, csv_path)
            downloaded = sum(1 for paper in papers if paper.status in {"downloaded", "exists"})
            missing_pdf_url = sum(1 for paper in papers if paper.status == "missing_pdf_url")
            errors = sum(1 for paper in papers if paper.status.startswith("error:"))
            summary_rows.append(BatchResult(url=url, venue=venue, year=year, total=len(papers), downloaded=downloaded, missing_pdf_url=missing_pdf_url, error=errors, output_dir=str(pdf_dir), output_csv=str(csv_path)))
            save_summary(summary_rows, output_root / summary_csv)
            print(f"[完成] {slug} downloaded={downloaded} missing_pdf_url={missing_pdf_url} error={errors}")
            if toc_index < len(urls):
                print(f"[休眠] TOC 间隔 {toc_sleep} 秒")
                time.sleep(toc_sleep)
    finally:
        ccs_crawler.close()
    save_summary(summary_rows, output_root / summary_csv)
