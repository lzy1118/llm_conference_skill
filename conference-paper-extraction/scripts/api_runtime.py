from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
APICONFIG_PATH = ROOT / "apiconfig.md"
MIN_REQUEST_INTERVAL_SECONDS = 1.6
MAX_RETRIES = 3

_LAST_REQUEST_AT: dict[str, float] = {}


def _read_legacy_value(name: str) -> str:
    if not APICONFIG_PATH.exists():
        return ""
    text = APICONFIG_PATH.read_text(encoding="utf-8", errors="replace")
    match = re.search(rf"^{re.escape(name)}\s*=\s*\"([^\"]+)\"", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def semantic_scholar_api_key() -> str:
    import os

    for env_name in ("SEMANTIC_SCHOLAR_API_KEY", "S2_API_KEY"):
        value = os.environ.get(env_name, "").strip()
        if value:
            return value
    return _read_legacy_value("S2_API_KEY")


def semantic_scholar_headers() -> dict[str, str]:
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json,*/*;q=0.8"}
    api_key = semantic_scholar_api_key()
    if api_key:
        headers["x-api-key"] = api_key
    return headers


def openalex_headers() -> dict[str, str]:
    import os

    email = os.environ.get("OPENALEX_MAILTO", "").strip()
    user_agent = f"mailto:{email}" if email else "mailto:test@example.com"
    return {"User-Agent": user_agent, "Accept": "application/json,*/*;q=0.8"}


def rate_limited_urlopen(
    service_name: str,
    request: urllib.request.Request,
    *,
    timeout: int = 45,
    max_retries: int = MAX_RETRIES,
    min_interval_seconds: float = MIN_REQUEST_INTERVAL_SECONDS,
) -> Any:
    for attempt in range(max_retries):
        now = time.time()
        last = _LAST_REQUEST_AT.get(service_name, 0.0)
        wait_seconds = min_interval_seconds - (now - last)
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        _LAST_REQUEST_AT[service_name] = time.time()
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code in {429, 500, 502, 503, 504} and attempt + 1 < max_retries:
                time.sleep(min_interval_seconds * (attempt + 1) * 2)
                continue
            raise
        except urllib.error.URLError:
            if attempt + 1 < max_retries:
                time.sleep(min_interval_seconds * (attempt + 1) * 2)
                continue
            raise


def fetch_json_with_rate_limit(
    service_name: str,
    url: str,
    headers: dict[str, str] | None = None,
    *,
    timeout: int = 45,
    max_retries: int = MAX_RETRIES,
) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0", "Accept": "application/json,*/*;q=0.8"})
    with rate_limited_urlopen(
        service_name,
        request,
        timeout=timeout,
        max_retries=max_retries,
    ) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))
