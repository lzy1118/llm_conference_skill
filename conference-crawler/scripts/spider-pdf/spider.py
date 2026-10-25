#!/usr/bin/env python3

# 共享抓取核心之上的轻量分发入口。
# 通过会议名同时决定 URL 子集和使用的抓取后端。
import os
import importlib.util
import csv
from pathlib import Path
import sys
import tempfile
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from core import DBLPPDFCrawler, parse_generic_toc_identity, parse_sp_ccs_toc_identity, run_ccs_batch, run_dblp_batch, run_sp_batch


CONFERENCE_CONFIG = {
    "asiacrypt": {"kind": "dblp", "summary": "summary_asiacrypt.csv"},
    "crypto": {"kind": "dblp", "summary": "summary_crypto.csv"},
    "eurocrypt": {"kind": "dblp", "summary": "summary_eurocrypt.csv"},
    "ndss": {"kind": "dblp", "summary": "summary_ndss.csv"},
    "usenix_security": {"kind": "dblp", "summary": "summary_usenix_security.csv", "output_venue": "usenix_security"},
    "ieee_s&p": {"kind": "sp", "summary": "summary_ieee_s&p.csv", "output_venue": "ieee_s&p"},
    "ccs": {"kind": "ccs", "summary": "summary_ccs.csv"},
    "www": {"kind": "ccs", "summary": "summary_www.csv"},
    "neurips": {"kind": "neurips", "summary": "summary_neurips.csv"},
    "icml": {"kind": "pmlr", "summary": "summary_icml.csv"},
}


def _load_source_discovery(base: Path):
    discovery_dir = base.parent / "source-discovery"
    discovery_file = discovery_dir / "discover.py"
    spec = importlib.util.spec_from_file_location("conference_source_discovery", discovery_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 source discovery: {discovery_file}")
    sys.path.insert(0, str(discovery_dir))
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        try:
            sys.path.remove(str(discovery_dir))
        except ValueError:
            pass
    return module


def _write_discovered_urls_file(records: list[dict[str, object]], conference: str) -> Path:
    temp_file = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        delete=False,
        prefix=f"{conference}_discovered_",
        suffix="_urls.txt",
    )
    with temp_file:
        for record in records:
            temp_file.write(f"{record['url']}\n")
    return Path(temp_file.name)


def _read_summary_counts(summary_path: Path) -> dict[str, int | None]:
    if not summary_path.exists():
        return {}
    with open(summary_path, encoding="utf-8-sig", newline="") as file_obj:
        rows = list(csv.DictReader(file_obj))
    counts: dict[str, int | None] = {}
    for row in rows:
        url = row.get("url", "")
        if not url:
            continue
        status = (row.get("validation_status") or "").strip().lower()
        raw_total = (row.get("total") or "").strip()
        raw_error = (row.get("error") or "").strip()
        if status == "failed":
            counts[url] = None
            continue
        try:
            total = int(raw_total)
            error_count = int(raw_error) if raw_error else 0
        except ValueError:
            counts[url] = None
            continue
        counts[url] = total if total >= 0 and error_count == 0 else None
    return counts


def _read_existing_summary_rows(summary_path: Path) -> dict[str, dict[str, str]]:
    if not summary_path.exists():
        return {}
    with open(summary_path, encoding="utf-8-sig", newline="") as file_obj:
        rows = list(csv.DictReader(file_obj))
    return {row.get("url", ""): row for row in rows if row.get("url")}


def _successful_existing_summary_row(existing_rows: dict[str, dict[str, str]], url: str) -> dict[str, str] | None:
    row = existing_rows.get(url)
    if not row:
        return None
    raw_total = (row.get("total") or "").strip()
    if not raw_total:
        return None
    try:
        total = int(raw_total)
        error = int((row.get("error") or "0").strip())
    except ValueError:
        return None
    if total >= 0 and error == 0 and (row.get("validation_status") or "validated").lower() != "failed":
        return row
    return None


def _read_urls(urls_file: Path) -> list[str]:
    urls: list[str] = []
    with open(urls_file, encoding="utf-8") as file_obj:
        for line in file_obj:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return urls


def _parse_neurips_identity(url: str) -> tuple[str, str, str]:
    match = re.search(r"/paper_files/paper/(\d{4})/?$", urlparse(url).path)
    if not match:
        raise ValueError(f"无法解析 NeurIPS TOC 信息: {url}")
    year = match.group(1)
    return "neurips", year, f"neurips{year}"


def _parse_pmlr_identity(url: str) -> tuple[str, str, str]:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    title_text = soup.title.get_text(" ", strip=True) if soup.title else ""
    year_match = re.search(r"\b(19|20)\d{2}\b", title_text)
    year = year_match.group(0) if year_match else ""
    slug = urlparse(url).path.strip("/").replace("/", "_") or "pmlr"
    return "icml", year, slug


def _count_neurips_papers(url: str) -> int:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    seen: set[str] = set()
    skip_terms = ("workshop", "demo", "companion")
    for anchor in soup.select('a[href*="-Abstract-Conference.html"]'):
        href = urljoin(url, anchor.get("href") or "")
        text = anchor.get_text(" ", strip=True)
        haystack = f"{text} {href}".lower()
        if any(term in haystack for term in skip_terms):
            continue
        seen.add(href)
    return len(seen)


def _count_pmlr_papers(url: str) -> int:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    seen: set[str] = set()
    skip_terms = ("workshop", "demo", "companion")
    for paper in soup.select("div.paper"):
        title_node = paper.select_one("p.title")
        if title_node is None:
            continue
        title = title_node.get_text(" ", strip=True)
        haystack = paper.get_text(" ", strip=True).lower()
        if any(term in haystack for term in skip_terms):
            continue
        link = paper.select_one('a[href$=".html"]')
        key = urljoin(url, link.get("href")) if link and link.get("href") else title
        seen.add(key)
    return len(seen)


def _save_metadata_only_summary(urls_file: Path, output_root: Path, summary_csv: str, years: set[str] | None, kind: str) -> dict[str, int | None]:
    crawler = DBLPPDFCrawler(sleep_seconds=0.0)
    urls = _read_urls(urls_file)
    pmlr_identities: dict[str, tuple[str, str, str]] = {}
    pmlr_identity_errors: dict[str, Exception] = {}
    if years:
        if kind == "dblp":
            urls = [url for url in urls if parse_generic_toc_identity(url)[1] in years]
        elif kind == "ccs":
            urls = [url for url in urls if parse_sp_ccs_toc_identity(url)[1] in years]
        elif kind == "neurips":
            urls = [url for url in urls if _parse_neurips_identity(url)[1] in years]
        elif kind == "pmlr":
            filtered_urls = []
            for url in urls:
                try:
                    identity = _parse_pmlr_identity(url)
                except Exception as exc:
                    # Keep this URL so its failure is written to the summary without stopping the batch.
                    pmlr_identity_errors[url] = exc
                    filtered_urls.append(url)
                else:
                    pmlr_identities[url] = identity
                    if identity[1] in years:
                        filtered_urls.append(url)
            urls = filtered_urls
    output_root.mkdir(parents=True, exist_ok=True)
    summary_path = output_root / summary_csv
    existing_rows = _read_existing_summary_rows(summary_path)
    fieldnames = ["url", "venue", "year", "total", "previous_total", "downloaded", "missing_pdf_url", "error", "validation_status", "output_dir", "output_csv"]
    counts: dict[str, int | None] = {}
    with open(summary_path, "w", newline="", encoding="utf-8-sig") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        for toc_index, url in enumerate(urls, start=1):
            venue = ""
            year = ""
            slug = urlparse(url).path.strip("/").replace("/", "_") or url
            try:
                if url in pmlr_identity_errors:
                    raise pmlr_identity_errors[url]
                if kind == "dblp":
                    venue, year, _part, slug = parse_generic_toc_identity(url)
                elif kind == "ccs":
                    venue, year, slug = parse_sp_ccs_toc_identity(url)
                elif kind == "neurips":
                    venue, year, slug = _parse_neurips_identity(url)
                elif kind == "pmlr":
                    venue, year, slug = pmlr_identities.get(url) or _parse_pmlr_identity(url)
                else:
                    raise ValueError(f"不支持 metadata-only backend: {kind}")
                print(f"[CRAWLER] metadata-only TOC {toc_index}/{len(urls)} {slug}")
                if kind in {"dblp", "ccs"}:
                    total = len(crawler.fetch_papers(url))
                elif kind == "neurips":
                    total = _count_neurips_papers(url)
                elif kind == "pmlr":
                    total = _count_pmlr_papers(url)
                else:
                    raise ValueError(f"不支持 metadata-only backend: {kind}")
                error = 0
                validation_status = "validated"
                previous_total = ""
            except Exception as exc:
                print(f"[CRAWLER] metadata-only failed url={url} error={exc}")
                existing_row = _successful_existing_summary_row(existing_rows, url)
                if existing_row:
                    previous_total = existing_row.get("total", "")
                else:
                    previous_total = (existing_rows.get(url) or {}).get("previous_total", "")
                total = ""
                error = 1
                validation_status = "failed"
            counts[url] = total if error == 0 else None
            writer.writerow(
                {
                    "url": url,
                    "venue": venue,
                    "year": year,
                    "total": total,
                    "previous_total": previous_total,
                    "downloaded": 0,
                    "missing_pdf_url": 0,
                    "error": error,
                    "validation_status": validation_status,
                    "output_dir": "",
                    "output_csv": "",
                }
            )
    return counts


def _log_source_records(records: list[dict[str, object]]) -> None:
    print(f"[SOURCE_DISCOVERY] found proceedings: {len(records)}")
    for record in records:
        print(
            "[SOURCE_DISCOVERY] "
            f"conference={record['conference']} "
            f"year={record['year']} "
            f"source={record['source']} "
            f"backend={record['backend']} "
            f"url={record['url']}"
        )


def _discover_urls_or_fallback(base: Path, conference: str, years: set[str] | None, output_root: Path, urls_file: Path) -> tuple[Path, Path | None]:
    if not years:
        print(f"[SOURCE_DISCOVERY] no --years supplied; loading manual URL file: {urls_file}")
        return urls_file, None

    try:
        discovery = _load_source_discovery(base)
        records = discovery.discover_proceedings_urls(conference, sorted(years))
        if not records:
            raise RuntimeError("source discovery returned no URLs")
        manifest_path = output_root / "metadata" / "source_manifest.csv"
        discovery.save_source_manifest(records, manifest_path)
        _log_source_records(records)
        discovered_urls_file = _write_discovered_urls_file(records, conference)
        print(f"[SOURCE_DISCOVERY] using discovered URL file: {discovered_urls_file}")
        print(f"[SOURCE_DISCOVERY] source manifest: {manifest_path}")
        return discovered_urls_file, discovered_urls_file
    except Exception as exc:
        print(f"[SOURCE_DISCOVERY] discovery failed; loading manual URL file: {urls_file}; error={exc}")
        return urls_file, None


def _update_manifest_after_crawl(base: Path, output_root: Path, summary_csv: str) -> None:
    manifest_path = output_root / "metadata" / "source_manifest.csv"
    summary_path = output_root / summary_csv
    counts = _read_summary_counts(summary_path)
    if not counts:
        return
    discovery = _load_source_discovery(base)
    discovery.update_source_manifest_counts(manifest_path, counts)
    print(f"[CRAWLER] validated source records: {len(counts)}")


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: spider.py <conference> [args...]")
        print("可选 conference: asiacrypt crypto eurocrypt ndss usenix_security ieee_s&p ccs www neurips icml")
        raise SystemExit(1)

    conference = sys.argv[1]
    config = CONFERENCE_CONFIG.get(conference)
    if config is None:
        print(f"不支持的 conference: {conference}")
        print("可选 conference: asiacrypt crypto eurocrypt ndss usenix_security ieee_s&p ccs www neurips icml")
        raise SystemExit(1)

    base = Path(__file__).resolve().parent
    # `urls.txt` 是人工查看用的总列表；旁边的按会议 URL 文件
    # 让统一入口可以保持与具体会议解耦。
    urls_file = base / f"{conference}_urls.txt"
    output_root = Path(
        os.environ.get("CONFERENCE_DOWNLOAD_DIR", base.parent / "download")
    ).expanduser().resolve()
    extra_args = sys.argv[2:]
    default_driver_path = os.environ.get("CHROMEDRIVER_PATH", "")
    default_user_data_dir = os.environ.get("SELENIUM_USER_DATA_DIR", str(base.parent / "selenium_chrome_profile_fresh"))

    if config["kind"] == "dblp":
        sleep = 2.0
        toc_sleep = 8.0
        years: set[str] | None = None
        force = False
        metadata_only = False
        debugger_address = ""
        driver_path = default_driver_path
        index = 0
        while index < len(extra_args):
            arg = extra_args[index]
            if arg == "--sleep":
                sleep = float(extra_args[index + 1])
                index += 2
            elif arg == "--toc-sleep":
                toc_sleep = float(extra_args[index + 1])
                index += 2
            elif arg == "--years":
                years = {item.strip() for item in extra_args[index + 1].split(",") if item.strip()}
                index += 2
            elif arg == "--force":
                force = True
                index += 1
            elif arg == "--metadata-only":
                metadata_only = True
                index += 1
            elif arg == "--debugger-address":
                debugger_address = extra_args[index + 1]
                index += 2
            elif arg == "--driver-path":
                driver_path = extra_args[index + 1]
                index += 2
            else:
                raise SystemExit(f"不支持的参数: {arg}")
        batch_urls_file, temporary_urls_file = _discover_urls_or_fallback(base, conference, years, output_root, urls_file)
        try:
            print(f"[CRAWLER] backend={config['kind']} conference={conference} years={','.join(sorted(years or [])) or 'all'}")
            if metadata_only:
                print("[DOWNLOAD] mode=metadata-only no PDFs will be downloaded")
                counts = _save_metadata_only_summary(batch_urls_file, output_root, config["summary"], years, config["kind"])
                discovery = _load_source_discovery(base)
                discovery.update_source_manifest_counts(output_root / "metadata" / "source_manifest.csv", counts)
                print(f"[CRAWLER] validated source records: {len(counts)}")
            else:
                print("[DOWNLOAD] mode=normal existing PDFs will be reused when present")
                run_dblp_batch(urls_file=batch_urls_file, output_root=output_root, summary_csv=config["summary"], sleep=sleep, toc_sleep=toc_sleep, years=years, force=force, debugger_address=debugger_address, driver_path=driver_path, output_venue=str(config.get("output_venue", "")))
                _update_manifest_after_crawl(base, output_root, config["summary"])
        finally:
            if temporary_urls_file:
                temporary_urls_file.unlink(missing_ok=True)
        return

    if config["kind"] in {"neurips", "pmlr"}:
        years: set[str] | None = None
        metadata_only = False
        index = 0
        while index < len(extra_args):
            arg = extra_args[index]
            if arg == "--years":
                years = {item.strip() for item in extra_args[index + 1].split(",") if item.strip()}
                index += 2
            elif arg == "--metadata-only":
                metadata_only = True
                index += 1
            else:
                raise SystemExit(f"不支持的参数: {arg}")
        if not metadata_only:
            raise SystemExit(f"{conference} 当前只支持 --metadata-only 集成验证")
        batch_urls_file, temporary_urls_file = _discover_urls_or_fallback(base, conference, years, output_root, urls_file)
        try:
            print(f"[CRAWLER] backend={config['kind']} conference={conference} years={','.join(sorted(years or [])) or 'all'}")
            print("[DOWNLOAD] mode=metadata-only no PDFs will be downloaded")
            counts = _save_metadata_only_summary(batch_urls_file, output_root, config["summary"], years, config["kind"])
            discovery = _load_source_discovery(base)
            discovery.update_source_manifest_counts(output_root / "metadata" / "source_manifest.csv", counts)
            print(f"[CRAWLER] validated source records: {len(counts)}")
        finally:
            if temporary_urls_file:
                temporary_urls_file.unlink(missing_ok=True)
        return

    if config["kind"] == "sp":
        # SP 是这组会议里唯一走 IEEE 的会议。
        driver_path = default_driver_path
        user_data_dir = default_user_data_dir
        profile_directory = ""
        start_year = 0
        start_index = 0
        sleep = 5.0
        toc_sleep = 15.0
        index = 0
        while index < len(extra_args):
            arg = extra_args[index]
            if arg == "--start-year":
                start_year = int(extra_args[index + 1])
                index += 2
            elif arg == "--start-index":
                start_index = int(extra_args[index + 1])
                index += 2
            elif arg == "--sleep":
                sleep = float(extra_args[index + 1])
                index += 2
            elif arg == "--toc-sleep":
                toc_sleep = float(extra_args[index + 1])
                index += 2
            elif arg == "--driver-path":
                driver_path = extra_args[index + 1]
                index += 2
            elif arg == "--user-data-dir":
                user_data_dir = extra_args[index + 1]
                index += 2
            elif arg == "--profile-directory":
                profile_directory = extra_args[index + 1]
                index += 2
            else:
                raise SystemExit(f"不支持的参数: {arg}")
        run_sp_batch(
            urls_file=urls_file,
            output_root=output_root,
            summary_csv=config["summary"],
            driver_path=driver_path,
            user_data_dir=user_data_dir,
            profile_directory=profile_directory,
            start_year=start_year,
            start_index=start_index,
            sleep=sleep,
            toc_sleep=toc_sleep,
            output_venue=str(config.get("output_venue", "")),
        )
        return

    if config["kind"] == "ccs":
        # CCS 走 ACM，并使用 ACM 浏览器流程。
        driver_path = default_driver_path
        user_data_dir = default_user_data_dir
        sleep = 8.0
        toc_sleep = 20.0
        years: set[str] | None = None
        metadata_only = False
        index = 0
        while index < len(extra_args):
            arg = extra_args[index]
            if arg == "--years":
                years = {item.strip() for item in extra_args[index + 1].split(",") if item.strip()}
                index += 2
            elif arg == "--sleep":
                sleep = float(extra_args[index + 1])
                index += 2
            elif arg == "--toc-sleep":
                toc_sleep = float(extra_args[index + 1])
                index += 2
            elif arg == "--metadata-only":
                metadata_only = True
                index += 1
            elif arg == "--driver-path":
                driver_path = extra_args[index + 1]
                index += 2
            elif arg == "--user-data-dir":
                user_data_dir = extra_args[index + 1]
                index += 2
            else:
                raise SystemExit(f"不支持的参数: {arg}")
        batch_urls_file, temporary_urls_file = _discover_urls_or_fallback(base, conference, years, output_root, urls_file)
        try:
            print(f"[CRAWLER] backend={config['kind']} conference={conference} years={','.join(sorted(years or [])) or 'all'}")
            if metadata_only:
                print("[DOWNLOAD] mode=metadata-only no PDFs will be downloaded")
                counts = _save_metadata_only_summary(batch_urls_file, output_root, config["summary"], years, config["kind"])
                discovery = _load_source_discovery(base)
                discovery.update_source_manifest_counts(output_root / "metadata" / "source_manifest.csv", counts)
                print(f"[CRAWLER] validated source records: {len(counts)}")
            else:
                print("[DOWNLOAD] mode=normal existing PDFs will be reused when present")
                run_ccs_batch(
                    urls_file=batch_urls_file,
                    output_root=output_root,
                    summary_csv=config["summary"],
                    driver_path=driver_path,
                    user_data_dir=user_data_dir,
                    sleep=sleep,
                    toc_sleep=toc_sleep,
                    years=years,
                )
                _update_manifest_after_crawl(base, output_root, config["summary"])
        finally:
            if temporary_urls_file:
                temporary_urls_file.unlink(missing_ok=True)
        return


if __name__ == "__main__":
    main()
