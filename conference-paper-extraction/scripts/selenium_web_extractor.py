from __future__ import annotations

import argparse
import csv
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.safari.options import Options as SafariOptions


DEFAULT_OUTPUT_DIR = Path("generated-data") / "extraction" / "selenium"


@dataclass(frozen=True)
class FieldSpec:
    name: str
    xpath: str


def parse_field_specs(values: list[str]) -> list[FieldSpec]:
    specs: list[FieldSpec] = []
    for value in values:
        if "=" not in value:
            raise ValueError(f"Field spec must be name=xpath: {value}")
        name, xpath = value.split("=", 1)
        name = name.strip()
        xpath = xpath.strip()
        if not name or not xpath:
            raise ValueError(f"Field spec must be name=xpath: {value}")
        specs.append(FieldSpec(name, xpath))
    return specs


def create_driver(browser: str) -> Any:
    if browser != "safari":
        raise ValueError(f"Unsupported browser: {browser}")
    options = SafariOptions()
    return webdriver.Safari(options=options)


def wait_for_page(driver: Any, seconds: float) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            state = driver.execute_script("return document.readyState")
        except Exception:
            state = None
        if state == "complete":
            return
        time.sleep(0.2)


def scroll_page(driver: Any, scroll_count: int, pause_seconds: float) -> None:
    for _ in range(max(scroll_count, 0)):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(max(pause_seconds, 0.0))


def normalize_text(value: str) -> str:
    return " ".join(value.split())


def element_payload(element: WebElement) -> dict[str, str]:
    text = normalize_text(element.text or "")
    href = (element.get_attribute("href") or "").strip()
    src = (element.get_attribute("src") or "").strip()
    content = (element.get_attribute("content") or "").strip()
    value = (element.get_attribute("value") or "").strip()
    html = (element.get_attribute("outerHTML") or "").strip()
    return {
        "text": text,
        "href": href,
        "src": src,
        "content": content,
        "value": value,
        "html": html,
    }


def extract_field_values(driver: Any, spec: FieldSpec) -> list[dict[str, str]]:
    elements = driver.find_elements(By.XPATH, spec.xpath)
    return [element_payload(element) for element in elements]


def login_if_configured(driver: Any, args: argparse.Namespace) -> None:
    login_url = (args.login_url or "").strip()
    if not login_url:
        return

    required = [args.username_xpath, args.password_xpath, args.submit_xpath, args.username_env, args.password_env]
    if not all(required):
        raise ValueError("Login flow requires --login-url, --username-xpath, --password-xpath, --submit-xpath, --username-env, and --password-env")

    username = os.environ.get(args.username_env, "").strip()
    password = os.environ.get(args.password_env, "").strip()
    if not username or not password:
        raise RuntimeError(
            f"Missing credentials in environment variables {args.username_env} / {args.password_env}"
        )

    driver.get(login_url)
    wait_for_page(driver, args.wait_seconds)

    username_field = driver.find_element(By.XPATH, args.username_xpath)
    password_field = driver.find_element(By.XPATH, args.password_xpath)
    submit_element = driver.find_element(By.XPATH, args.submit_xpath)

    username_field.clear()
    username_field.send_keys(username)
    password_field.clear()
    password_field.send_keys(password)
    try:
        submit_element.click()
    except Exception:
        password_field.send_keys(Keys.RETURN)
    wait_for_page(driver, args.wait_seconds)
    time.sleep(args.post_login_wait_seconds)


def collect_links(driver: Any, xpath: str, base_url: str) -> list[str]:
    links: list[str] = []
    for element in driver.find_elements(By.XPATH, xpath):
        href = (element.get_attribute("href") or "").strip()
        if not href:
            continue
        absolute = urljoin(base_url, href)
        if absolute not in links:
            links.append(absolute)
    return links


def visit_page(driver: Any, url: str, args: argparse.Namespace) -> None:
    driver.get(url)
    wait_for_page(driver, args.wait_seconds)
    scroll_page(driver, args.scroll_count, args.scroll_pause_seconds)


def run_extract(args: argparse.Namespace) -> dict[str, Any]:
    specs = parse_field_specs(args.field)
    driver = create_driver(args.browser)
    try:
        login_if_configured(driver, args)
        visit_page(driver, args.url, args)
        fields = {spec.name: extract_field_values(driver, spec) for spec in specs}
        payload = {
            "mode": "extract",
            "url": args.url,
            "browser": args.browser,
            "fields": fields,
        }
        return payload
    finally:
        driver.quit()


def run_crawl(args: argparse.Namespace) -> dict[str, Any]:
    detail_specs = parse_field_specs(args.field)
    if not args.level1_xpath or not args.level2_xpath:
        raise ValueError("crawl mode requires --level1-xpath and --level2-xpath")

    driver = create_driver(args.browser)
    try:
        login_if_configured(driver, args)
        visit_page(driver, args.url, args)
        level1_links = collect_links(driver, args.level1_xpath, args.url)
        rows: list[dict[str, Any]] = []
        for level1_url in level1_links[: args.level1_limit or None]:
            visit_page(driver, level1_url, args)
            level2_links = collect_links(driver, args.level2_xpath, level1_url)
            for detail_url in level2_links[: args.level2_limit or None]:
                visit_page(driver, detail_url, args)
                row: dict[str, Any] = {
                    "level1_url": level1_url,
                    "detail_url": detail_url,
                }
                for spec in detail_specs:
                    values = extract_field_values(driver, spec)
                    row[f"{spec.name}_count"] = len(values)
                    row[f"{spec.name}_texts"] = " | ".join(value["text"] for value in values if value["text"])
                    row[f"{spec.name}_hrefs"] = " | ".join(value["href"] for value in values if value["href"])
                rows.append(row)
        return {
            "mode": "crawl",
            "root_url": args.url,
            "browser": args.browser,
            "level1_count": len(level1_links),
            "rows": rows,
        }
    finally:
        driver.quit()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_rows_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generic Selenium extractor for public conference pages")
    parser.add_argument("mode", choices=("extract", "crawl"))
    parser.add_argument("--url", required=True, help="Target URL or crawl root URL")
    parser.add_argument("--browser", default="safari", choices=("safari",))
    parser.add_argument("--field", action="append", default=[], help="Field spec in name=xpath form. Repeatable.")
    parser.add_argument("--level1-xpath")
    parser.add_argument("--level2-xpath")
    parser.add_argument("--level1-limit", type=int, default=0)
    parser.add_argument("--level2-limit", type=int, default=0)
    parser.add_argument("--wait-seconds", type=float, default=8.0)
    parser.add_argument("--scroll-count", type=int, default=1)
    parser.add_argument("--scroll-pause-seconds", type=float, default=1.0)
    parser.add_argument("--login-url")
    parser.add_argument("--username-xpath")
    parser.add_argument("--password-xpath")
    parser.add_argument("--submit-xpath")
    parser.add_argument("--username-env")
    parser.add_argument("--password-env")
    parser.add_argument("--post-login-wait-seconds", type=float, default=3.0)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output-prefix", default="selenium_extract")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.mode == "extract":
        payload = run_extract(args)
        write_json(args.output_dir / f"{args.output_prefix}.json", payload)
    else:
        payload = run_crawl(args)
        write_json(args.output_dir / f"{args.output_prefix}.json", payload)
        write_rows_csv(args.output_dir / f"{args.output_prefix}.csv", payload["rows"])
    print(json.dumps({
        "mode": payload["mode"],
        "output_dir": str(args.output_dir),
        "output_prefix": args.output_prefix,
        "rows": len(payload.get("rows", [])),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
