from __future__ import annotations

import argparse
import html
import json
import mimetypes
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend_common import conference_interim_dir, conference_output_dir, conference_pdf_dir, conference_raw_dir, summary_interim_dir, summary_output_dir, write_csv, write_workbook
from api_runtime import fetch_json_with_rate_limit, openalex_headers, semantic_scholar_headers
from classification_common import classify_with_patterns, load_override_rows, normalize_space


BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass(frozen=True)
class ConferenceConfig:
    key: str
    conference: str
    year: int
    dblp_key: str
    venue_tag: str


CONFERENCES = {
    "usenix_security_2020": ConferenceConfig("usenix_security_2020", "USENIX_SECURITY", 2020, "uss", "USENIX_SECURITY"),
    "usenix_security_2021": ConferenceConfig("usenix_security_2021", "USENIX_SECURITY", 2021, "uss", "USENIX_SECURITY"),
    "usenix_security_2022": ConferenceConfig("usenix_security_2022", "USENIX_SECURITY", 2022, "uss", "USENIX_SECURITY"),
    "usenix_security_2023": ConferenceConfig("usenix_security_2023", "USENIX_SECURITY", 2023, "uss", "USENIX_SECURITY"),
    "usenix_security_2024": ConferenceConfig("usenix_security_2024", "USENIX_SECURITY", 2024, "uss", "USENIX_SECURITY"),
    "usenix_security_2025": ConferenceConfig("usenix_security_2025", "USENIX_SECURITY", 2025, "uss", "USENIX_SECURITY"),
    "ndss_2020": ConferenceConfig("ndss_2020", "NDSS", 2020, "ndss", "NDSS"),
    "ndss_2021": ConferenceConfig("ndss_2021", "NDSS", 2021, "ndss", "NDSS"),
    "ndss_2022": ConferenceConfig("ndss_2022", "NDSS", 2022, "ndss", "NDSS"),
    "ndss_2023": ConferenceConfig("ndss_2023", "NDSS", 2023, "ndss", "NDSS"),
    "ndss_2024": ConferenceConfig("ndss_2024", "NDSS", 2024, "ndss", "NDSS"),
    "ndss_2025": ConferenceConfig("ndss_2025", "NDSS", 2025, "ndss", "NDSS"),
    "ieee_sp_2020": ConferenceConfig("ieee_sp_2020", "IEEE_S&P", 2020, "sp", "IEEE_S&P"),
    "ieee_sp_2021": ConferenceConfig("ieee_sp_2021", "IEEE_S&P", 2021, "sp", "IEEE_S&P"),
    "ieee_sp_2022": ConferenceConfig("ieee_sp_2022", "IEEE_S&P", 2022, "sp", "IEEE_S&P"),
    "ieee_sp_2023": ConferenceConfig("ieee_sp_2023", "IEEE_S&P", 2023, "sp", "IEEE_S&P"),
    "ieee_sp_2024": ConferenceConfig("ieee_sp_2024", "IEEE_S&P", 2024, "sp", "IEEE_S&P"),
    "ieee_sp_2025": ConferenceConfig("ieee_sp_2025", "IEEE_S&P", 2025, "sp", "IEEE_S&P"),
    "ieee_sp_2026": ConferenceConfig("ieee_sp_2026", "IEEE_S&P", 2026, "sp", "IEEE_S&P"),
    "ccs_2020": ConferenceConfig("ccs_2020", "CCS", 2020, "ccs", "CCS"),
    "ccs_2021": ConferenceConfig("ccs_2021", "CCS", 2021, "ccs", "CCS"),
    "ccs_2022": ConferenceConfig("ccs_2022", "CCS", 2022, "ccs", "CCS"),
    "ccs_2023": ConferenceConfig("ccs_2023", "CCS", 2023, "ccs", "CCS"),
    "ccs_2024": ConferenceConfig("ccs_2024", "CCS", 2024, "ccs", "CCS"),
    "ccs_2025": ConferenceConfig("ccs_2025", "CCS", 2025, "ccs", "CCS"),
    "ccs_2026": ConferenceConfig("ccs_2026", "CCS", 2026, "ccs", "CCS"),
    "ndss_2026": ConferenceConfig("ndss_2026", "NDSS", 2026, "ndss", "NDSS"),
    "usenix_security_2026": ConferenceConfig("usenix_security_2026", "USENIX_SECURITY", 2026, "uss", "USENIX_SECURITY"),
}

US_EXACT_ALIASES = {
    "mit", "nist", "sri", "uc san diego", "uc berkeley", "uc irvine",
    "uc davis", "uc santa barbara", "uc santa cruz", "uc los angeles", "ucla",
    "ut austin", "uiuc", "umd", "nyu", "yale", "duke", "cmu", "usc",
    "gatech", "georgia tech",
}

US_KEYWORD_PATTERNS = [
    r"\bmassachusetts institute of technology\b", r"\bcarnegie mellon university\b",
    r"\bstanford university\b", r"\bprinceton university\b", r"\bcornell university\b",
    r"\bcornell tech\b", r"\bbrown university\b", r"\bduke university\b",
    r"\byale university\b", r"\byale\b", r"\bcolumbia university\b",
    r"\bnew york university\b", r"\bnyu\b", r"\bboston university\b",
    r"\bjohns hopkins university\b", r"\bjhu\b", r"\buniversity of california\b",
    r"\buniversity of washington\b", r"\buniversity of wisconsin\b", r"\buw-madison\b",
    r"\buniversity of maryland\b", r"\bumd\b", r"\buniversity of pennsylvania\b",
    r"\buniversity of michigan\b", r"\buniversity of texas\b", r"\but austin\b",
    r"\buniversity of illinois\b", r"\buiuc\b", r"\burbana-champaign\b",
    r"\bgeorgia tech\b", r"\bgeorgia institute of technology\b", r"\bcity college of new york\b",
    r"\bcuny\b", r"\bnorth carolina state university\b", r"\bnortheastern university\b",
    r"\bpurdue university\b", r"\brice university\b", r"\bstony brook university\b",
    r"\btexas a&m university\b", r"\bunc chapel hill\b", r"\buniversity of connecticut\b",
    r"\bwashington state university\b", r"\bgoogle\b", r"\bmeta\b", r"\bmicrosoft\b",
    r"\bibm research\b", r"\bintel\b", r"\bcloudflare\b", r"\bvisa research\b",
    r"\bamazon\b", r"\baws\b", r"\bapple\b", r"\bnational institute of standards and technology\b",
    r"\bsandia national lab\b", r"\bsandia national laboratories\b", r"\boak ridge national lab\b",
    r"\bargon national lab\b", r"\blawrence livermore\b", r"\blos alamos\b",
    r"\buniversity of north carolina\b", r"\buniversity of virginia\b", r"\buniversity of florida\b",
    r"\buniversity of colorado\b", r"\buniversity of arizona\b", r"\buniversity of southern california\b",
    r"\busc\b", r"\bucla\b", r"\bucsd\b", r"\bucsb\b", r"\bohio state university\b",
    r"\bpenn state\b", r"\bvirginia tech\b", r"\brutgers\b", r"\buc berkeley\b", r"\bucb\b",
    r"\buniversity of massachusetts\b", r"\bumass\b", r"\buniversity of minnesota\b",
    r"\buniversity of iowa\b", r"\buniversity of utah\b", r"\buniversity of oregon\b",
    r"\boregon state university\b", r"\buniversity of notre dame\b", r"\bnorthwestern university\b",
    r"\bemory university\b", r"\bgeorge mason university\b", r"\bgeorge washington university\b",
    r"\bamerican university\b", r"\bwayne state university\b", r"\bcase western\b",
    r"\buniversity of cincinnati\b", r"\buniversity of kansas\b", r"\buniversity of kentucky\b",
    r"\buniversity of tennessee\b", r"\buniversity of alabama\b", r"\buniversity of oklahoma\b",
    r"\buniversity of nebraska\b", r"\buniversity of south carolina\b", r"\buniversity of hawaii\b",
    r"\buniversity of delaware\b", r"\buniversity of maryland baltimore\b", r"\bstanford\b",
    r"\bmit\b", r"\bcaltech\b", r"\bharvard\b", r"\byale\b", r"\bprinceton\b",
    r"\bcolumbia\b", r"\bupenn\b", r"\bcornell\b", r"\bucsf\b", r"\buw\b", r"\bgmu\b",
    r"\bpurdue\b", r"\bnortheastern\b", r"\barizona state university\b", r"\basu\b",
    r"\buniversity of illinois chicago\b", r"\buic\b", r"\buniversity of texas at dallas\b",
    r"\butd\b", r"\buniversity of texas at san antonio\b", r"\butsa\b", r"\bsmu\b",
    r"\bsouthern methodist\b", r"\bdrexel university\b", r"\bstevens institute\b",
    r"\bworcester polytechnic\b", r"\bwpi\b", r"\brensselaer\b", r"\brpi\b", r"\buc davis\b",
    r"\buc irvine\b", r"\buc santa cruz\b", r"\bsuny\b", r"\bdisney research\b",
    r"\bqualcomm\b", r"\bnvidia\b", r"\bboeing\b", r"\bford\b", r"\bge research\b",
    r"\bsri international\b", r"\bbattelle\b", r"\bida\b", r"\bmitre\b", r"\brand\b",
    r"\bnasa\b", r"\bnoaa\b", r"\bnational security agency\b", r"\bnsa\b",
    r"\bdefense advanced research\b", r"\bdarpa\b", r"\barmy research lab\b",
    r"\bnaval research\b", r"\bair force research\b",
]

NON_US_KEYWORD_PATTERNS = [
    r"\beth zurich\b", r"\beth z.rich\b", r"\busi, lugano\b", r"\buniversity of luxembourg\b",
    r"\bruhr university bochum\b", r"\bkings? college london\b", r"\broyal holloway\b",
    r"\buniversity of auckland\b", r"\btechnical university of denmark\b", r"\bibm research europe\b",
    r"\buniversity of cambridge\b", r"\buniversity of oxford\b", r"\bimperial college\b",
    r"\bucl\b", r"\buniversity college london\b", r"\binria\b", r"\bcnrs\b",
    r"\buniversity of melbourne\b", r"\buniversity of sydney\b", r"\bnanyang technological\b",
    r"\bnational university of singapore\b", r"\btsinghua\b", r"\bpeking\b", r"\bfudan\b",
    r"\buniversity of tokyo\b", r"\bkyoto\b", r"\btechnische universit\b", r"\bludwig maximilian\b",
    r"\bmax planck\b", r"\buniversity of edinburgh\b", r"\buniversity of manchester\b",
    r"\buniversity of birmingham\b", r"\buniversity of bristol\b", r"\buniversity of glasgow\b",
    r"\bkarlsruhe institute\b", r"\buniversity of stuttgart\b", r"\bdarmstadt\b", r"\braadboud\b",
    r"\beindhoven\b", r"\bdelft\b", r"\buniversity of oslo\b", r"\bkth\b", r"\bchalmers\b",
    r"\buniversity of helsinki\b", r"\baalto\b", r"\buniversity of waterloo\b", r"\buniversity of toronto\b",
    r"\bmcgill\b", r"\buniversity of british columbia\b", r"\bepfl\b", r"\buniversity of bern\b",
    r"\buniversity of zurich\b", r"\buniversity of geneva\b", r"\buniversit.t basel\b", r"\bweizmann\b",
    r"\btechnion\b", r"\btel aviv\b", r"\bhebrew university\b", r"\bbar ilan\b",
    r"\bmonash\b", r"\buniversity of queensland\b", r"\buniversity of adelaide\b",
    r"\buniversity of new south wales\b", r"\bvrije universiteit\b", r"\buniversiteit leiden\b",
    r"\buniversiteit utrecht\b", r"\buniversiteit amsterdam\b", r"\buniversity of buenos aires\b",
    r"\buniversity of s£o paulo\b", r"\buniversity of cape town\b", r"\bnational chiao tung\b",
    r"\bnational tsing hua\b", r"\bnational taiwan\b", r"\buniversity of hong kong\b",
    r"\bhong kong university\b", r"\bchinese university of hong kong\b", r"\bcity university of hong kong\b",
    r"\buniversity of macau\b", r"\bseoul national\b", r"\bkaist\b", r"\bkorea university\b", r"\byonsei\b",
    r"\biisc\b", r"\biit bombay\b", r"\biit delhi\b", r"\biit madras\b", r"\bsoochow\b",
    r"\buniversity of science and technology of china\b", r"\buniversity of electronic science\b",
    r"\bxidian\b", r"\bbeihang\b", r"\bzhejiang\b", r"\bshanghai jiao\b", r"\bnanjing\b",
    r"\bwuhan\b", r"\bhuazhong\b", r"\bsun yat-sen\b", r"\bharbin institute\b", r"\btongji\b",
    r"\brenmin\b", r"\bbeijing institute\b", r"\bnational institute of informatics\b", r"\bsamsung\b",
    r"\bhuawei\b", r"\balibaba\b", r"\btencent\b", r"\bbaidu\b", r"\byandex\b",
    r"\bvodafone\b", r"\bdeutsche telekom\b", r"\bsony\b", r"\bntt\b", r"\bkddi\b",
    r"\bsoftbank\b", r"\brickitt\b", r"\bline corporation\b", r"\bnec corporation\b",
    r"\bfujitsu\b", r"\bhitachi\b", r"\bpanasonic\b", r"\bsharp\b", r"\btoshiba\b", r"\bcanon\b",
    r"\bolympus\b", r"\bkomatsu\b", r"\bdenso\b", r"\bmazda\b", r"\bhonda\b", r"\btoyota\b",
    r"\bnissan\b", r"\bsubaru\b", r"\bsuzuki\b", r"\bmitsubishi\b", r"\bsumitomo\b",
    r"\bmizuho\b", r"\bnomura\b", r"\bnintendo\b", r"\bcapcom\b", r"\bkonami\b", r"\bseg a\b",
    r"\bsquare enix\b", r"\bbandai\b", r"\bfrom software\b",
]

AUTHOR_NOTE_PATTERN = re.compile(
    r"\b(corresponding author|author to whom correspondence|equal contribution|shared first author|present address)\b",
    re.IGNORECASE,
)


def build_article_tag(config: ConferenceConfig, title: str) -> str:
    return f"{config.venue_tag}-{normalize_space(title)}"


@dataclass(frozen=True)
class AffiliationClassification:
    country: str
    source: str
    confidence: float
    reason: str


def clean_author_name(value: str) -> str:
    text = normalize_space(html.unescape(str(value)))
    text = re.sub(r"\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+\d{4}$", "", text)
    text = re.sub(r"\s*[\*\u2020\u2021\u00a7]+\s*$", "", text)
    text = re.sub(r"\s*\([^)]*\)$", lambda match: "" if AUTHOR_NOTE_PATTERN.search(match.group(0)) else match.group(0), text)
    return normalize_space(text.strip(" ,;"))


def classify_affiliation(
    affiliation: str,
    overrides: dict[str, AffiliationClassification] | None = None,
) -> AffiliationClassification:
    normalized = normalize_space(affiliation)
    if overrides and normalized.casefold() in overrides:
        return overrides[normalized.casefold()]
    parts = split_affiliation_parts(affiliation)
    if len(parts) > 1:
        results = [classify_single_affiliation(part, overrides) for part in parts]
        countries = {result.country for result in results if result.country != "Unknown"}
        if countries == {"China", "Hong Kong"}:
            lower = normalized.casefold()
            if "shenzhen" in lower:
                return AffiliationClassification("China", "rule", 0.95, "hong_kong_shenzhen_consensus")
            if "hong kong" in lower:
                return AffiliationClassification("Hong Kong", "rule", 0.95, "hong_kong_consensus")
        if len(countries) > 1:
            return AffiliationClassification(
                "Multiple",
                "rule",
                min((result.confidence for result in results if result.country != "Unknown"), default=0.7),
                "multiple_countries",
            )
        if len(countries) == 1:
            country = next(iter(countries))
            return AffiliationClassification(
                country,
                "rule",
                min((result.confidence for result in results if result.country != "Unknown"), default=0.7),
                "multi_affiliation_consensus",
            )
        return results[-1]
    return classify_single_affiliation(affiliation, overrides)


def split_affiliation_parts(affiliation: str) -> list[str]:
    normalized = normalize_space(affiliation)
    if ", and " in normalized:
        parts = [part.strip(" ,") for part in re.split(r",\s+and\s+", normalized) if part.strip(" ,")]
        if len(parts) > 1:
            return parts
    if ";" in normalized:
        return [part.strip() for part in normalized.split(";") if part.strip()]
    if "/" in normalized:
        return [part.strip() for part in normalized.split("/") if part.strip()]
    if " & " in normalized:
        parts = [part.strip() for part in normalized.split(" & ") if part.strip()]
        if len(parts) > 1:
            classified_countries = {
                classify_single_affiliation(part, overrides=None).country
                for part in parts
                if classify_single_affiliation(part, overrides=None).country != "Unknown"
            }
            if len(classified_countries) > 1:
                return parts
            if re.search(r"\b(University|Institute|Labs|Lab|Research|College|Technologies|Technology|Center|Centre|Group|School)\b.*&.*\b(University|Institute|Labs|Lab|Research|College|Technologies|Technology|Center|Centre|Group|School)\b", normalized):
                return parts
    if " and " in normalized:
        if re.search(
            r"\b(Science and Technology|Posts and Telecommunications|Economics and Technology|Research and Technology|Information and Communications Technology|Polytechnic Institute and State University|Parallel Computer Engineering and Technology|Mathematical Engineering and Advanced Computing)\b",
            normalized,
            re.IGNORECASE,
        ):
            return [normalized]
        parts = [part.strip() for part in normalized.split(" and ") if part.strip()]
        if len(parts) > 1:
            classified_countries = {
                classify_single_affiliation(part, overrides=None).country
                for part in parts
                if classify_single_affiliation(part, overrides=None).country != "Unknown"
            }
            if len(classified_countries) > 1:
                return parts
            if re.search(r"\b(University|Institute|Labs|Lab|Research|College|Technologies|Technology|Center|Centre|Group|School)\b.*\band\b.*\b(University|Institute|Labs|Lab|Research|College|Technologies|Technology|Center|Centre|Group|School)\b", normalized):
                return parts
    return [normalized]


def classify_single_affiliation(
    affiliation: str,
    overrides: dict[str, AffiliationClassification] | None = None,
) -> AffiliationClassification:
    return classify_with_patterns(
        affiliation,
        overrides=overrides,
        exact_aliases=US_EXACT_ALIASES,
        non_us_patterns=NON_US_KEYWORD_PATTERNS,
        us_patterns=US_KEYWORD_PATTERNS,
        classification_factory=AffiliationClassification,
    )


def load_institution_overrides(path: Path) -> dict[str, AffiliationClassification]:
    return load_override_rows(path, AffiliationClassification)


def parse_usenix_affiliations_html(html_text: str) -> list[dict[str, Any]]:
    def split_author_group(names_text: str) -> list[str]:
        normalized_names = html.unescape(names_text)
        normalized_names = re.sub(r"\s+", " ", normalized_names).strip(" ,;")
        normalized_names = re.sub(r",\s+and\s+", ", ", normalized_names)
        normalized_names = re.sub(r"\s+and\s+", ", ", normalized_names)
        return [name for name in (clean_author_name(part) for part in normalized_names.split(",")) if name]

    authors = re.findall(r'<meta\s+name="citation_author"\s+content="([^"]+)"', html_text)
    institutions = re.findall(r'<meta\s+name="citation_author_institution"\s+content="([^"]+)"', html_text)
    meta_rows = []
    for index, author in enumerate(authors):
        inst = institutions[index] if index < len(institutions) else ""
        clean_author = clean_author_name(author)
        clean_inst = normalize_space(html.unescape(inst).rstrip(";"))
        meta_rows.append({"name": clean_author, "affiliations": [clean_inst] if clean_inst else []})

    author_block_rows = []
    author_block_match = re.search(
        r'<div class="field field-name-field-paper-people-text.*?<p>(.*?)</p>',
        html_text,
        re.DOTALL,
    )
    if author_block_match:
        author_block = author_block_match.group(1)
        for names_text, institution_text in re.findall(r'([^<]+?),\s*<em>(.*?)</em>', author_block, re.DOTALL):
            institution = normalize_space(html.unescape(re.sub(r"<[^>]+>", " ", institution_text)).rstrip(";"))
            for name in split_author_group(names_text):
                author_block_rows.append({"name": name, "affiliations": [institution] if institution else []})

    if not meta_rows:
        return author_block_rows
    if not author_block_rows:
        return meta_rows

    merged = {row["name"]: {"name": row["name"], "affiliations": list(row.get("affiliations", []))} for row in meta_rows if row.get("name")}
    for row in author_block_rows:
        name = row.get("name", "")
        if not name:
            continue
        if name not in merged:
            merged[name] = {"name": name, "affiliations": list(row.get("affiliations", []))}
            continue
        if not merged[name].get("affiliations") and row.get("affiliations"):
            merged[name]["affiliations"] = list(row["affiliations"])
    return list(merged.values())


def parse_ndss_affiliations_html(html: str) -> list[dict[str, Any]]:
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)

    paper_data_match = re.search(r'<div class="paper-data">(.*?)</div>\s*<div class="paper-buttons">', text, re.DOTALL | re.IGNORECASE)
    if paper_data_match:
        paper_data = paper_data_match.group(1)
        paragraphs = re.findall(r"<p>(.*?)</p>", paper_data, re.DOTALL | re.IGNORECASE)
        for paragraph in paragraphs:
            clean = normalize_space(re.sub(r"<[^>]+>", " ", paragraph))
            if "(" not in clean or ")" not in clean:
                continue
            result = []
            for match in re.finditer(r"([^,]+?)\s*\(([^)]+)\)", clean):
                name = clean_author_name(match.group(1))
                inst = normalize_space(match.group(2))
                if len(name.split()) < 2 or len(inst) <= 3 or inst.startswith("http") or inst[0].isdigit():
                    continue
                result.append({"name": name, "affiliations": [inst]})
            if result:
                return result

    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.DOTALL | re.IGNORECASE)
    if not h1_match:
        return []
    after_h1 = text[h1_match.end():h1_match.end() + 3000]
    after_h1_clean = re.sub(r"<[^>]+>", " ", after_h1)
    after_h1_clean = re.sub(r"\s+", " ", after_h1_clean).strip()
    result = []
    pattern = r"([A-Z][a-zA-ZÀ-ÿ\-']+(?:\s+(?:van|de|di|da|von|le|la|el)\s+)?(?:\s+[A-Z][a-zA-ZÀ-ÿ\-']+(?:\s+\d{4})?)+)\s*\(([^)]+)\)"
    for match in re.finditer(pattern, after_h1_clean):
        name = clean_author_name(match.group(1))
        inst = match.group(2).strip()
        if len(inst) > 3 and not inst.startswith("http") and not inst[0].isdigit():
            result.append({"name": name, "affiliations": [inst]})
    return result


def parse_ieee_affiliations_html(html: str) -> list[dict[str, Any]]:
    match = re.search(r'xplGlobal\.document\.metadata\s*=\s*(\{.*?\});', html, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    result = []
    for author in data.get("authors", []):
        name = clean_author_name(author.get("name", ""))
        affiliations = author.get("affiliation", [])
        if name:
            result.append({"name": name, "affiliations": affiliations})
    return result


def fetch_text(url: str, timeout: int = 20) -> str:
    request = urllib.request.Request(url, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def slug_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalize_space(value).casefold()).strip("-")


def safe_pdf_stem(paper: dict[str, Any]) -> str:
    paper_id = normalize_space(str(paper.get("paperId", ""))).replace("/", "_")
    if paper_id:
        return paper_id
    title = slug_text(str(paper.get("title", "")))
    return title or "paper"


def extract_pdf_links_from_html(base_url: str, html_text: str) -> list[str]:
    links: list[str] = []
    for href in re.findall(r'href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\']', html_text, re.IGNORECASE):
        absolute = urllib.parse.urljoin(base_url, html.unescape(href))
        if absolute not in links:
            links.append(absolute)
    return links


def extract_public_pdf_candidates(base_url: str, html_text: str) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []

    def add(url: str, strategy: str) -> None:
        absolute = urllib.parse.urljoin(base_url, html.unescape(url.strip()))
        if absolute and all(existing[0] != absolute for existing in candidates):
            candidates.append((absolute, strategy))

    for pattern in [
        r'<meta[^>]+name="citation_pdf_url"[^>]+content="([^"]+)"',
        r'<meta[^>]+property="citation_pdf_url"[^>]+content="([^"]+)"',
        r'<meta[^>]+name="wkhealth_pdf_url"[^>]+content="([^"]+)"',
    ]:
        for match in re.findall(pattern, html_text, re.IGNORECASE):
            add(match, "meta_pdf_url")

    for href in re.findall(r'href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\']', html_text, re.IGNORECASE):
        add(href, "href_pdf")

    for pattern in [
        r'pdfUrl["\']?\s*[:=]\s*["\']([^"\']+)',
        r'epdf["\']?\s*[:=]\s*["\']([^"\']+)',
        r'data-pdf-url=["\']([^"\']+)["\']',
    ]:
        for match in re.findall(pattern, html_text, re.IGNORECASE):
            add(match, "script_pdf_hint")
    return candidates


def resolve_pdf_url(config: ConferenceConfig, paper: dict[str, Any]) -> tuple[str, str]:
    url = normalize_space(str(paper.get("url", "")))
    if not url:
        return "", ""
    if url.lower().endswith(".pdf"):
        return url, "raw_pdf_url"
    try:
        page_html = fetch_text(url, timeout=20)
    except Exception:
        return "", ""
    candidates = extract_public_pdf_candidates(url, page_html)
    if not candidates:
        return "", ""
    if config.conference == "USENIX_SECURITY":
        for link, strategy in candidates:
            if "files/conference" in link or "/presentation/" in link or "usenixsecurity" in link:
                return link, strategy
    return candidates[0]


def download_pdf(url: str, output_path: Path, referer: str = "", timeout: int = 60) -> tuple[bool, str, int]:
    headers = dict(BROWSER_HEADERS)
    headers["Accept"] = "application/pdf,*/*;q=0.8"
    if referer:
        headers["Referer"] = referer
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        content = response.read()
        final_url = response.geturl()
    is_pdf = "pdf" in content_type.casefold() or final_url.lower().endswith(".pdf")
    if not is_pdf:
        return False, content_type, len(content)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(content)
    return True, content_type, len(content)


def download_pdfs_for_conference(
    config: ConferenceConfig,
    papers: list[dict[str, Any]],
    output_dir: Path,
    pdf_limit: int = 0,
) -> dict[str, Any]:
    pdf_dir = conference_pdf_dir(output_dir, config.key)
    report_rows: list[dict[str, Any]] = []
    downloaded = 0
    papers_seen = 0
    for index, paper in enumerate(papers):
        if pdf_limit > 0 and papers_seen >= pdf_limit:
            break
        papers_seen += 1
        paper_id = normalize_space(str(paper.get("paperId", "")))
        title = normalize_space(str(paper.get("title", "")))
        source_url = normalize_space(str(paper.get("url", "")))
        pdf_url, resolution_strategy = resolve_pdf_url(config, paper)
        row = {
            "conference": config.conference,
            "year": config.year,
            "paper_id": paper_id,
            "title": title,
            "source_url": source_url,
            "pdf_url": pdf_url,
            "resolution_strategy": resolution_strategy,
            "status": "pending",
            "content_type": "",
            "bytes": 0,
            "path": "",
            "error": "",
        }
        if not pdf_url:
            row["status"] = "no_pdf_url"
            report_rows.append(row)
            continue
        output_path = pdf_dir / f"{safe_pdf_stem(paper)}.pdf"
        try:
            ok, content_type, byte_count = download_pdf(pdf_url, output_path, referer=source_url)
            row["content_type"] = content_type
            row["bytes"] = byte_count
            if ok:
                row["status"] = "downloaded"
                row["path"] = str(output_path)
                downloaded += 1
            else:
                row["status"] = "non_pdf_response"
        except Exception as exc:
            row["status"] = "download_error"
            row["error"] = str(exc)
        report_rows.append(row)
    report_path = output_dir / "interim" / f"{config.key}_pdf_download_report.csv"
    write_csv(
        report_path,
        report_rows,
        ["conference", "year", "paper_id", "title", "source_url", "pdf_url", "resolution_strategy", "status", "content_type", "bytes", "path", "error"],
    )
    summary = {
        "conference": config.conference,
        "year": config.year,
        "papers_seen": papers_seen,
        "downloaded_pdfs": downloaded,
        "report_path": str(report_path),
        "pdf_dir": str(pdf_dir),
    }
    (output_dir / "interim" / f"{config.key}_pdf_download_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def fetch_dblp_papers(config: ConferenceConfig) -> list[dict[str, Any]]:
    url = f"https://dblp.org/db/conf/{config.dblp_key}/{config.dblp_key}{config.year}.xml"
    request = urllib.request.Request(url, headers={"User-Agent": BROWSER_HEADERS["User-Agent"]})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            xml_data = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"DBLP fetch failed for {config.key}: {exc}", file=sys.stderr)
        return []

    root = ET.fromstring(xml_data)
    papers = []
    for article in root.findall(".//inproceedings") + root.findall(".//article"):
        title_el = article.find("title")
        title = normalize_space(title_el.text) if title_el is not None and title_el.text else ""
        if not title:
            continue
        authors = []
        for author in article.findall(".//author"):
            if author.text:
                cleaned = clean_author_name(author.text)
                if cleaned:
                    authors.append(cleaned)
        ee = article.find("ee")
        url = ee.text.strip() if ee is not None and ee.text else ""
        paper_id = article.get("key", "")
        papers.append({
            "paperId": paper_id,
            "title": title,
            "authors": authors,
            "url": url,
        })
    return papers


def fetch_usenix_affiliations(paper_url: str) -> list[dict[str, Any]]:
    try:
        html = fetch_text(paper_url, timeout=15)
    except Exception:
        return []
    return parse_usenix_affiliations_html(html)


def fetch_ndss_affiliations(paper_url: str) -> list[dict[str, Any]]:
    try:
        html = fetch_text(paper_url, timeout=15)
    except Exception:
        return []
    return parse_ndss_affiliations_html(html)


def fetch_ieee_affiliations(paper_url: str) -> list[dict[str, Any]]:
    try:
        html = fetch_text(paper_url, timeout=15)
    except Exception:
        return []
    return parse_ieee_affiliations_html(html)


def fetch_semantic_scholar_affiliations(title: str, authors: list[str]) -> list[dict[str, Any]]:
    query = urllib.parse.quote_plus(title[:100])
    url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={query}&limit=1&fields=title,authors"
    try:
        data = fetch_json_with_rate_limit(
            "semantic_scholar",
            url,
            headers=semantic_scholar_headers(),
            timeout=20,
        )
    except Exception:
        return []
    papers = data.get("data", [])
    if not papers:
        return []
    result = []
    for author in papers[0].get("authors", []):
        name = author.get("name", "")
        affiliations = [author.get("affiliations", [""])[0]] if author.get("affiliations") else []
        if name:
            result.append({"name": name, "affiliations": affiliations})
    return result


def normalized_title_key(title: str) -> str:
    title = re.sub(r"<[^>]+>", " ", title)
    return normalize_space(title).casefold().rstrip(".")


def normalize_person_name(value: str) -> list[str]:
    text = clean_author_name(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"<[^>]+>", " ", text)
    text = normalize_space(text)
    if "," in text:
        parts = [part.strip() for part in text.split(",") if part.strip()]
        if len(parts) >= 2:
            text = f"{' '.join(parts[1:])} {parts[0]}"
    text = re.sub(r"[^A-Za-z0-9 ]+", " ", text)
    return [part.casefold() for part in text.split() if part]


def names_match(left: str, right: str) -> bool:
    left_parts = normalize_person_name(left)
    right_parts = normalize_person_name(right)
    if not left_parts or not right_parts:
        return False
    if left_parts == right_parts:
        return True
    if left_parts[0] == right_parts[0]:
        left_tail = "".join(left_parts[1:])
        right_tail = "".join(right_parts[1:])
        if left_tail and left_tail == right_tail:
            return True
    if left_parts[-1] != right_parts[-1]:
        return False
    if left_parts[0][0] != right_parts[0][0]:
        return False
    return True


def map_author_name(input_authors: list[str], candidate_name: str) -> str:
    for name in input_authors:
        if names_match(name, candidate_name):
            return name
    return ""


def normalized_person_key(value: str) -> str:
    return " ".join(normalize_person_name(value))


def build_affiliation_map(author_affiliations: list[dict[str, Any]]) -> tuple[dict[str, list[str]], list[tuple[str, list[str]]]]:
    aff_map: dict[str, list[str]] = {}
    aff_name_pairs: list[tuple[str, list[str]]] = []
    for item in author_affiliations:
        source_name = normalize_space(str(item.get("name", "")))
        affiliations = item.get("affiliations", [])
        if not source_name:
            continue
        aff_name_pairs.append((source_name, affiliations))
        aff_map[normalized_person_key(source_name)] = affiliations
    return aff_map, aff_name_pairs


def match_author_affiliations(
    authors: list[str],
    aff_map: dict[str, list[str]],
    aff_name_pairs: list[tuple[str, list[str]]],
) -> list[list[str]]:
    matched_affiliations: list[list[str]] = []
    for author in authors:
        key = normalized_person_key(author)
        if key in aff_map:
            matched_affiliations.append(aff_map[key])
            continue
        matched = False
        for aff_name, affs in aff_name_pairs:
            aff_key = normalized_person_key(aff_name)
            if not aff_key:
                continue
            if names_match(author, aff_name):
                matched_affiliations.append(affs)
                matched = True
                break
            if aff_key in key or key in aff_key:
                matched_affiliations.append(affs)
                matched = True
                break
            key_parts = key.split()
            aff_parts = aff_key.split()
            if (
                len(key_parts) >= 2
                and len(aff_parts) >= 2
                and key_parts[-1] == aff_parts[-1]
                and key_parts[0][0] == aff_parts[0][0]
            ):
                matched_affiliations.append(affs)
                matched = True
                break
        if not matched:
            matched_affiliations.append([])
    return matched_affiliations


def fill_shared_affiliation_gaps(matched_affiliations: list[list[str]]) -> list[list[str]]:
    known_affiliations = [
        "; ".join(affs)
        for affs in matched_affiliations
        if affs and "; ".join(affs).strip()
    ]
    unique_known_affiliations = sorted(set(known_affiliations))
    if len(unique_known_affiliations) != 1:
        return matched_affiliations
    shared_affiliations = next((affs for affs in matched_affiliations if affs), [])
    if not shared_affiliations:
        return matched_affiliations
    return [affs if affs else list(shared_affiliations) for affs in matched_affiliations]


def extract_doi_from_url(url: str) -> str:
    value = normalize_space(url)
    if not value:
        return ""
    value = value.rstrip("/")
    if "doi.org/" not in value:
        return ""
    doi = value.split("doi.org/", 1)[1].strip()
    return doi


def map_openalex_authorships(authorships: list[dict[str, Any]], authors: list[str]) -> list[dict[str, Any]]:
    mapped_rows: list[dict[str, Any]] = []
    matched = 0
    for authorship in authorships:
        author_info = authorship.get("author", {})
        candidate_names = [
            normalize_space(str(author_info.get("display_name", ""))),
            normalize_space(str(authorship.get("raw_author_name", ""))),
        ]
        mapped_name = ""
        for candidate_name in candidate_names:
            if not candidate_name:
                continue
            mapped_name = map_author_name(authors, candidate_name)
            if mapped_name:
                break
        if not mapped_name:
            continue

        affiliations: list[str] = []
        for institution in authorship.get("institutions", []):
            inst_name = normalize_space(str(institution.get("display_name", "")))
            if inst_name and inst_name not in affiliations:
                affiliations.append(inst_name)
        for raw_aff in authorship.get("raw_affiliation_strings", []):
            raw_name = normalize_space(str(raw_aff))
            if raw_name and raw_name not in affiliations:
                affiliations.append(raw_name)
        mapped_rows.append({"name": mapped_name, "affiliations": affiliations})
        if affiliations:
            matched += 1
    if matched > 0:
        return mapped_rows
    return []


def has_resolved_affiliations(rows: list[dict[str, Any]]) -> bool:
    for row in rows:
        affiliations = row.get("affiliations", [])
        if any(normalize_space(str(value)) for value in affiliations):
            return True
    return False


def cache_has_full_author_coverage(rows: list[dict[str, Any]], authors: list[str]) -> bool:
    if not rows:
        return False
    aff_map, aff_name_pairs = build_affiliation_map(rows)
    matched_affiliations = match_author_affiliations(authors, aff_map, aff_name_pairs)
    return bool(authors) and all(bool(affs) for affs in matched_affiliations)


def fetch_openalex_affiliations_by_doi(doi: str, authors: list[str], year: int | None = None) -> list[dict[str, Any]]:
    normalized_doi = normalize_space(doi)
    if not normalized_doi:
        return []
    url = f"https://api.openalex.org/works/doi:{urllib.parse.quote(normalized_doi, safe='')}"
    try:
        payload = fetch_json_with_rate_limit(
            "openalex",
            url,
            headers=openalex_headers(),
            timeout=20,
        )
    except Exception:
        return []

    publication_year = payload.get("publication_year")
    if year is not None and publication_year is not None and int(publication_year) != int(year):
        return []
    return map_openalex_authorships(payload.get("authorships", []), authors)


def fetch_openalex_affiliations(title: str, authors: list[str], year: int | None = None) -> list[dict[str, Any]]:
    query = urllib.parse.quote(title)
    url = f"https://api.openalex.org/works?search={query}&per-page=5"
    try:
        payload = fetch_json_with_rate_limit(
            "openalex",
            url,
            headers=openalex_headers(),
            timeout=20,
        )
    except Exception:
        return []

    for result in payload.get("results", []):
        display_name = normalize_space(str(result.get("display_name", "")))
        publication_year = result.get("publication_year")
        if normalized_title_key(display_name) != normalized_title_key(title):
            continue
        if year is not None and publication_year is not None and int(publication_year) != int(year):
            continue
        mapped_rows = map_openalex_authorships(result.get("authorships", []), authors)
        if mapped_rows:
            return mapped_rows
    return []


def resolve_openalex_fallback(url: str, title: str, authors: list[str], year: int | None = None) -> list[dict[str, Any]]:
    doi = extract_doi_from_url(url)
    if doi:
        affiliations = fetch_openalex_affiliations_by_doi(doi, authors, year)
        if has_resolved_affiliations(affiliations):
            return affiliations
    affiliations = fetch_openalex_affiliations(title, authors, year)
    if has_resolved_affiliations(affiliations):
        return affiliations
    return []


def resolve_affiliations_for_paper(
    config: ConferenceConfig,
    paper: dict[str, Any],
    cache_dir: Path,
    fetch_from_network: bool = False,
) -> list[dict[str, Any]]:
    import time

    cache_file = cache_dir / f"{paper['paperId'].replace('/', '_')}_affiliations.json"
    authors = paper.get("authors", [])
    if cache_file.exists():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        if has_resolved_affiliations(cached) and (cache_has_full_author_coverage(cached, authors) or not fetch_from_network):
            return cached
    if not fetch_from_network:
        return []

    affiliations = []
    url = paper.get("url", "")
    title = paper.get("title", "")
    time.sleep(0.3)
    if config.conference == "USENIX_SECURITY" and url:
        affiliations = fetch_usenix_affiliations(url)
        if not has_resolved_affiliations(affiliations):
            affiliations = resolve_openalex_fallback(url, title, authors, config.year)
    elif config.conference == "NDSS" and url:
        affiliations = fetch_ndss_affiliations(url)
        if not has_resolved_affiliations(affiliations):
            affiliations = resolve_openalex_fallback(url, title, authors, config.year)
    elif config.conference == "IEEE_S&P" and url and "doi.org" in url:
        affiliations = fetch_ieee_affiliations(url)
        if not has_resolved_affiliations(affiliations):
            affiliations = resolve_openalex_fallback(url, title, authors, config.year)
    elif config.conference == "CCS" and url:
        doi = extract_doi_from_url(url)
        if doi:
            affiliations = fetch_openalex_affiliations_by_doi(doi, authors, config.year)
        if not affiliations:
            affiliations = fetch_openalex_affiliations(title, authors, config.year)
        if not affiliations:
            affiliations = fetch_semantic_scholar_affiliations(title, authors)

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(affiliations, ensure_ascii=False, indent=2), encoding="utf-8")
    return affiliations


def expand_author_rows(
    config: ConferenceConfig,
    papers: list[dict[str, Any]],
    overrides: dict[str, AffiliationClassification] | None = None,
    cache_dir: Path | None = None,
    fetch_from_network: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    for paper in papers:
        title = normalize_space(paper.get("title", ""))
        authors = [normalize_space(author) for author in paper.get("authors", [])]
        paper_id = paper.get("paperId", "")
        article_tag = build_article_tag(config, title)
        author_affiliations = resolve_affiliations_for_paper(config, paper, cache_dir, fetch_from_network) if cache_dir else []

        if author_affiliations:
            aff_map, aff_name_pairs = build_affiliation_map(author_affiliations)
            matched_affiliations = match_author_affiliations(authors, aff_map, aff_name_pairs)
            original_match_flags = [bool(affs) for affs in matched_affiliations]
            fallback_match_flags = [False] * len(authors)
            shared_fill_flags = [False] * len(authors)

            if any(not affs for affs in matched_affiliations):
                openalex_affiliations = resolve_openalex_fallback(
                    paper.get("url", ""),
                    title,
                    authors,
                    config.year,
                )
                if openalex_affiliations:
                    fallback_map, fallback_name_pairs = build_affiliation_map(openalex_affiliations)
                    fallback_matches = match_author_affiliations(authors, fallback_map, fallback_name_pairs)
                    fallback_match_flags = [bool(affs) for affs in fallback_matches]
                    matched_affiliations = [
                        primary if primary else fallback
                        for primary, fallback in zip(matched_affiliations, fallback_matches)
                    ]

            if any(not affs for affs in matched_affiliations):
                before_shared_fill = [bool(affs) for affs in matched_affiliations]
                matched_affiliations = fill_shared_affiliation_gaps(matched_affiliations)
                shared_fill_flags = [
                    (not before) and bool(after)
                    for before, after in zip(before_shared_fill, matched_affiliations)
                ]

            matched_count = sum(1 for affs in matched_affiliations if affs)
            if matched_count > 0:
                unmatched_authors: list[str] = []
                for order, (author, affs) in enumerate(zip(authors, matched_affiliations)):
                    if not affs:
                        unmatched_authors.append(author)
                        rows.append({
                            "conference": config.conference,
                            "year": config.year,
                            "paper_id": paper_id,
                            "title": title,
                            "name": author,
                            "article_tag": article_tag,
                            "author_order": order,
                            "inst": "",
                            "country": "Unknown",
                            "classification_source": "author_affiliation_unmatched",
                            "classification_confidence": 0.0,
                            "classification_reason": "author_not_matched_in_source_affiliations",
                        })
                        continue
                    inst = "; ".join(affs)
                    classification = classify_affiliation(inst, overrides)
                    classification_source = classification.source
                    classification_confidence = classification.confidence
                    classification_reason = classification.reason
                    if shared_fill_flags[order]:
                        classification_source = "paper_shared_affiliation_backfill"
                        classification_confidence = min(classification.confidence, 0.7)
                        classification_reason = "paper_level_single_affiliation_consensus"
                    elif (not original_match_flags[order]) and fallback_match_flags[order]:
                        classification_source = "openalex_partial_gap_fill"
                        classification_confidence = min(classification.confidence, 0.8)
                        classification_reason = "openalex_partial_author_gap_fill"
                    rows.append({
                        "conference": config.conference,
                        "year": config.year,
                        "paper_id": paper_id,
                        "title": title,
                        "name": author,
                        "article_tag": article_tag,
                        "author_order": order,
                        "inst": inst,
                        "country": classification.country,
                        "classification_source": classification_source,
                        "classification_confidence": classification_confidence,
                        "classification_reason": classification_reason,
                    })
                if unmatched_authors:
                    issues.append({
                        "conference": config.conference,
                        "year": str(config.year),
                        "paper_id": paper_id,
                        "title": title,
                        "issue": "partial_author_affiliation_coverage",
                        "authors_count": str(len(authors)),
                        "affiliations_count": str(len(author_affiliations)),
                        "authors": " | ".join(unmatched_authors),
                        "affiliations": " | ".join(
                            f"{item.get('name', '').strip()}: {'; '.join(item.get('affiliations', []))}".strip(": ")
                            for item in author_affiliations
                        ),
                    })
                continue

            issues.append({
                "conference": config.conference,
                "year": str(config.year),
                "paper_id": paper_id,
                "title": title,
                "issue": "author_affiliation_match_failed",
                "authors_count": str(len(authors)),
                "affiliations_count": str(len(author_affiliations)),
                "authors": " | ".join(authors),
                "affiliations": " | ".join(
                    f"{item.get('name', '').strip()}: {'; '.join(item.get('affiliations', []))}".strip(": ")
                    for item in author_affiliations
                ),
            })
            continue

        issues.append({
            "conference": config.conference,
            "year": str(config.year),
            "paper_id": paper_id,
            "title": title,
            "issue": "no_affiliation_data",
            "authors_count": str(len(authors)),
            "affiliations_count": "0",
            "authors": " | ".join(authors),
            "affiliations": "",
        })
    return rows, issues


def filter_classified_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("country") and row["country"] != "Unknown"]


def count_country_resolution_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    single_country_rows = sum(1 for row in rows if row.get("country") not in {"", "Unknown", "Multiple"})
    multiple_country_rows = sum(1 for row in rows if row.get("country") == "Multiple")
    unresolved_country_rows = sum(1 for row in rows if row.get("country") in {"", "Unknown"})
    return {
        "single_country_resolved_rows": single_country_rows,
        "multiple_country_rows": multiple_country_rows,
        "unresolved_country_rows": unresolved_country_rows,
    }


def normalize_papers(config: ConferenceConfig, papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{
        "conference": config.conference,
        "year": config.year,
        "paper_id": paper.get("paperId", ""),
        "title": normalize_space(paper.get("title", "")),
        "article_tag": build_article_tag(config, paper.get("title", "")),
        "authors_count": len(paper.get("authors", [])),
        "url": paper.get("url", ""),
    } for paper in papers]


def build_affiliation_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["inst"], row["classification_reason"])
        candidates.setdefault(key, {
            "inst": row["inst"],
            "country": row["country"],
            "classification_source": row["classification_source"],
            "classification_confidence": row["classification_confidence"],
            "classification_reason": row["classification_reason"],
            "example_conference": row["conference"],
            "example_paper_id": row["paper_id"],
            "example_title": row["title"],
        })
    return sorted(candidates.values(), key=lambda item: (item["inst"], item["classification_reason"]))


def run_single_conference(
    config: ConferenceConfig,
    raw_json_path: Path,
    output_dir: Path,
    papers: list[dict[str, Any]] | None = None,
    fetch_affiliations: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    if papers is None:
        papers = json.loads(raw_json_path.read_text(encoding="utf-8"))
    overrides = load_institution_overrides(output_dir / "reference" / "institution_country_overrides.csv")
    cache_dir = output_dir / "resolution" / "affiliation_cache"
    conference_output = conference_output_dir(output_dir, config.key)
    conference_interim = conference_interim_dir(output_dir, config.key)
    paper_rows = normalize_papers(config, papers)
    rows, issues = expand_author_rows(config, papers, overrides, cache_dir, fetch_affiliations)
    classified_rows = filter_classified_rows(rows)
    classified_rows_final = classified_rows
    country_counts = count_country_resolution_rows(rows)
    papers_with_author_rows = len({row["paper_id"] for row in rows if row.get("paper_id")})
    papers_without_affiliation_data = sum(1 for issue in issues if issue.get("issue") == "no_affiliation_data")
    partial_affiliation_coverage = sum(1 for issue in issues if issue.get("issue") == "partial_author_affiliation_coverage")
    author_affiliation_match_failed = sum(1 for issue in issues if issue.get("issue") == "author_affiliation_match_failed")

    write_csv(conference_interim / "author_affiliations_expanded.csv", rows,
              ["conference", "year", "paper_id", "title", "name", "article_tag",
               "author_order", "inst", "country", "classification_source",
               "classification_confidence", "classification_reason"])
    write_csv(conference_interim / "affiliation_resolution_queue.csv", issues,
              ["conference", "year", "paper_id", "title", "issue",
               "authors_count", "affiliations_count", "authors", "affiliations"])
    write_csv(conference_output / "author_affiliations.csv", classified_rows,
              ["name", "year", "article_tag", "author_order", "inst", "country"])
    write_csv(conference_output / "author_affiliations_audit.csv", classified_rows_final,
              ["conference", "year", "paper_id", "title", "name", "article_tag",
               "author_order", "inst", "country", "classification_source",
               "classification_confidence", "classification_reason"])
    write_workbook(conference_output / "author_affiliations.xlsx", classified_rows_final, ["name", "year", "article_tag", "author_order", "inst", "country"])
    write_csv(conference_interim / "institution_classification_candidates.csv", build_affiliation_candidates(rows),
              ["inst", "country", "classification_source", "classification_confidence",
               "classification_reason", "example_conference", "example_paper_id", "example_title"])
    report = {
        "conference": config.conference,
        "year": config.year,
        "raw_json": str(raw_json_path),
        "papers_count": len(papers),
        "papers_with_author_rows": papers_with_author_rows,
        "papers_without_affiliation_data": papers_without_affiliation_data,
        "papers_with_partial_affiliation_coverage": partial_affiliation_coverage,
        "papers_with_author_affiliation_match_failed": author_affiliation_match_failed,
        "expanded_author_rows": len(rows),
        "classified_author_rows": len(classified_rows),
        "resolved_country_rows": len(classified_rows),
        **country_counts,
        "no_affiliation_issues": len(issues),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (conference_output / "validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return report, paper_rows, rows, issues


def run_all_pipelines(
    output_dir: Path,
    conference_keys: list[str] | None = None,
    fetch_affiliations: bool = False,
    download_pdfs: bool = False,
    pdf_limit: int = 0,
    start: int = 0,
    limit: int = 0,
) -> dict[str, Any]:
    selected_keys = conference_keys or list(CONFERENCES.keys())
    summary_output = summary_output_dir(output_dir, "top4_security")
    summary_interim = summary_interim_dir(output_dir, "top4_security")
    reports = []
    all_papers = []
    all_rows = []
    all_issues = []
    pdf_reports = []

    for key in selected_keys:
        config = CONFERENCES[key]
        raw_json_path = conference_raw_dir(output_dir, config.key) / "papers.json"
        if not raw_json_path.exists():
            print(f"Skipping {config.key}: no raw JSON at {raw_json_path}", file=sys.stderr)
            continue
        papers = json.loads(raw_json_path.read_text(encoding="utf-8"))
        if start > 0 or limit > 0:
            stop = start + limit if limit > 0 else None
            papers = papers[start:stop]
        if download_pdfs:
            pdf_reports.append(download_pdfs_for_conference(config, papers, output_dir, pdf_limit=pdf_limit))
        report, paper_rows, rows, issues = run_single_conference(
            config,
            raw_json_path,
            output_dir,
            papers=papers,
            fetch_affiliations=fetch_affiliations,
        )
        reports.append(report)
        all_papers.extend(paper_rows)
        all_rows.extend(rows)
        all_issues.extend(issues)

    all_classified_rows = filter_classified_rows(all_rows)
    all_classified_rows_final = all_classified_rows
    country_counts = count_country_resolution_rows(all_rows)
    candidates = build_affiliation_candidates(all_rows)

    write_csv(summary_interim / "papers_normalized.csv", all_papers,
              ["conference", "year", "paper_id", "title", "article_tag", "authors_count", "url"])
    write_csv(summary_interim / "author_affiliations_expanded.csv", all_rows,
              ["conference", "year", "paper_id", "title", "name", "article_tag",
               "author_order", "inst", "country", "classification_source",
               "classification_confidence", "classification_reason"])
    write_csv(summary_interim / "institution_classification_candidates.csv", candidates,
              ["inst", "country", "classification_source", "classification_confidence",
               "classification_reason", "example_conference", "example_paper_id", "example_title"])
    write_csv(summary_interim / "affiliation_resolution_queue.csv", all_issues,
              ["conference", "year", "paper_id", "title", "issue",
               "authors_count", "affiliations_count", "authors", "affiliations"])
    write_csv(summary_output / "四大安全顶会_作者机构国家.csv", all_classified_rows,
              ["name", "year", "article_tag", "author_order", "inst", "country"])
    write_csv(summary_output / "四大安全顶会_作者机构国家_audit.csv", all_classified_rows_final,
              ["conference", "year", "paper_id", "title", "name", "article_tag",
               "author_order", "inst", "country", "classification_source",
               "classification_confidence", "classification_reason"])
    write_workbook(summary_output / "四大安全顶会_作者机构国家.xlsx", all_classified_rows_final, ["name", "year", "article_tag", "author_order", "inst", "country"])
    combined = {
        "reports": reports,
        "papers_count": sum(report["papers_count"] for report in reports),
        "papers_with_author_rows": len({row["paper_id"] for row in all_rows if row.get("paper_id")}),
        "papers_without_affiliation_data": sum(1 for issue in all_issues if issue.get("issue") == "no_affiliation_data"),
        "papers_with_partial_affiliation_coverage": sum(1 for issue in all_issues if issue.get("issue") == "partial_author_affiliation_coverage"),
        "papers_with_author_affiliation_match_failed": sum(1 for issue in all_issues if issue.get("issue") == "author_affiliation_match_failed"),
        "expanded_author_rows": len(all_rows),
        "classified_author_rows": len(all_classified_rows),
        "resolved_country_rows": len(all_classified_rows),
        **country_counts,
        "no_affiliation_issues": len(all_issues),
        "pdf_download_reports": pdf_reports,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (summary_output / "validation_report.json").write_text(
        json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return combined


def fetch_dblp_and_save(config: ConferenceConfig, output_dir: Path) -> None:
    papers = fetch_dblp_papers(config)
    output_path = conference_raw_dir(output_dir, config.key) / "papers.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(papers, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Fetched {len(papers)} papers for {config.key}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Security conference affiliation and country extraction pipeline")
    parser.add_argument("--conference", nargs="*", default=["all"], help="Conference keys or 'all'")
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    parser.add_argument("--fetch", action="store_true", help="Fetch papers from DBLP")
    parser.add_argument("--fetch-affiliations", action="store_true", help="Fetch affiliations from conference websites")
    parser.add_argument("--download-pdfs", action="store_true", help="Download PDFs when paper pages expose PDF links")
    parser.add_argument("--pdf-limit", type=int, default=0, help="Limit PDF downloads per conference; 0 means no limit")
    parser.add_argument("--start", type=int, default=0, help="Start index for per-conference batching")
    parser.add_argument("--limit", type=int, default=0, help="Limit papers per conference for batching; 0 means no limit")
    parser.add_argument("--list-conferences", action="store_true")
    args = parser.parse_args(argv)

    if args.list_conferences:
        for key, config in CONFERENCES.items():
            print(f"  {key}: {config.conference} {config.year}")
        return 0

    if "all" in args.conference:
        keys = list(CONFERENCES.keys())
    else:
        keys = args.conference

    if args.fetch:
        for key in keys:
            config = CONFERENCES[key]
            fetch_dblp_and_save(config, args.output_dir)

    report = run_all_pipelines(
        args.output_dir,
        keys,
        args.fetch_affiliations,
        args.download_pdfs,
        args.pdf_limit,
        args.start,
        args.limit,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
