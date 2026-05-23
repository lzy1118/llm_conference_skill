from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend_common import write_csv, write_workbook
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
    "usenix_security_2022": ConferenceConfig("usenix_security_2022", "USENIX_SECURITY", 2022, "uss", "USENIX_SECURITY"),
    "usenix_security_2023": ConferenceConfig("usenix_security_2023", "USENIX_SECURITY", 2023, "uss", "USENIX_SECURITY"),
    "usenix_security_2025": ConferenceConfig("usenix_security_2025", "USENIX_SECURITY", 2025, "uss", "USENIX_SECURITY"),
    "ndss_2025": ConferenceConfig("ndss_2025", "NDSS", 2025, "ndss", "NDSS"),
    "ieee_sp_2025": ConferenceConfig("ieee_sp_2025", "IEEE_S&P", 2025, "sp", "IEEE_S&P"),
    "ieee_sp_2026": ConferenceConfig("ieee_sp_2026", "IEEE_S&P", 2026, "sp", "IEEE_S&P"),
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


def build_article_tag(config: ConferenceConfig, title: str) -> str:
    return f"{config.venue_tag}-{normalize_space(title)}"


@dataclass(frozen=True)
class AffiliationClassification:
    country: str
    is_us: bool
    source: str
    confidence: float
    reason: str


def classify_affiliation(
    affiliation: str,
    overrides: dict[str, AffiliationClassification] | None = None,
) -> AffiliationClassification:
    parts = split_affiliation_parts(affiliation)
    if len(parts) > 1:
        results = [classify_single_affiliation(part, overrides) for part in parts]
        countries = {result.country for result in results if result.country != "Unknown"}
        if len(countries) > 1:
            return AffiliationClassification(
                "Multiple",
                False,
                "rule",
                min((result.confidence for result in results), default=0.7),
                "multiple_countries",
            )
        if len(countries) == 1:
            country = next(iter(countries))
            return AffiliationClassification(
                country,
                country == "United States",
                "rule",
                min((result.confidence for result in results), default=0.7),
                "multi_affiliation_consensus",
            )
        return results[-1]
    return classify_single_affiliation(affiliation, overrides)


def split_affiliation_parts(affiliation: str) -> list[str]:
    normalized = normalize_space(affiliation)
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
            r"\b(Science and Technology|Posts and Telecommunications|Economics and Technology|Research and Technology|Information and Communications Technology|Polytechnic Institute and State University)\b",
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
    authors = re.findall(r'<meta\s+name="citation_author"\s+content="([^"]+)"', html_text)
    institutions = re.findall(r'<meta\s+name="citation_author_institution"\s+content="([^"]+)"', html_text)
    if not authors:
        author_block_match = re.search(
            r'<div class="field field-name-field-paper-people-text.*?<p>(.*?)</p>',
            html_text,
            re.DOTALL,
        )
        if not author_block_match:
            return []
        author_block = author_block_match.group(1)
        result = []
        for names_text, institution_text in re.findall(r'([^<]+?),\s*<em>(.*?)</em>', author_block, re.DOTALL):
            institution = normalize_space(html.unescape(re.sub(r"<[^>]+>", " ", institution_text)).rstrip(";"))
            names = [normalize_space(html.unescape(part)) for part in re.split(r"\s+and\s+", names_text) if normalize_space(html.unescape(part))]
            for name in names:
                result.append({"name": name, "affiliations": [institution] if institution else []})
        return result
    result = []
    for index, author in enumerate(authors):
        inst = institutions[index] if index < len(institutions) else ""
        clean_author = normalize_space(html.unescape(author))
        clean_inst = normalize_space(html.unescape(inst).rstrip(";"))
        result.append({"name": clean_author, "affiliations": [clean_inst] if clean_inst else []})
    return result


def parse_ndss_affiliations_html(html: str) -> list[dict[str, Any]]:
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.DOTALL | re.IGNORECASE)
    if not h1_match:
        return []
    after_h1 = text[h1_match.end():h1_match.end() + 3000]
    after_h1_clean = re.sub(r"<[^>]+>", " ", after_h1)
    after_h1_clean = re.sub(r"\s+", " ", after_h1_clean).strip()
    result = []
    pattern = r"([A-Z][a-zA-ZÀ-ÿ\-']+(?:\s+(?:van|de|di|da|von|le|la|el)\s+)?(?:\s+[A-Z][a-zA-ZÀ-ÿ\-']+(?:\s+\d{4})?)+)\s*\(([^)]+)\)"
    for match in re.finditer(pattern, after_h1_clean):
        name = re.sub(r"\s+\d{4}$", "", match.group(1).strip())
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
        name = author.get("name", "")
        affiliations = author.get("affiliation", [])
        if name:
            result.append({"name": name, "affiliations": affiliations})
    return result


def fetch_text(url: str, timeout: int = 20) -> str:
    request = urllib.request.Request(url, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


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
                authors.append(normalize_space(author.text))
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
        request = urllib.request.Request(url, headers={"User-Agent": BROWSER_HEADERS["User-Agent"]})
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
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


def resolve_affiliations_for_paper(
    config: ConferenceConfig,
    paper: dict[str, Any],
    cache_dir: Path,
    fetch_from_network: bool = False,
) -> list[dict[str, Any]]:
    import time

    cache_file = cache_dir / f"{paper['paperId'].replace('/', '_')}_affiliations.json"
    if cache_file.exists():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        if cached or not fetch_from_network:
            return cached
    if not fetch_from_network:
        return []

    affiliations = []
    url = paper.get("url", "")
    time.sleep(0.3)
    if config.conference == "USENIX_SECURITY" and url:
        affiliations = fetch_usenix_affiliations(url)
    elif config.conference == "NDSS" and url:
        affiliations = fetch_ndss_affiliations(url)
    elif config.conference == "IEEE_S&P" and url and "doi.org" in url:
        affiliations = fetch_ieee_affiliations(url)
    elif config.conference == "CCS" and url:
        affiliations = fetch_semantic_scholar_affiliations(paper["title"], paper["authors"])

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
            aff_map = {normalize_space(item["name"]).lower(): item.get("affiliations", []) for item in author_affiliations}
            matched_affiliations = []
            for author in authors:
                key = author.lower().strip()
                if key in aff_map:
                    matched_affiliations.append(aff_map[key])
                    continue
                matched = False
                for aff_name, affs in aff_map.items():
                    if aff_name in key or key in aff_name:
                        matched_affiliations.append(affs)
                        matched = True
                        break
                    key_parts = key.split()
                    aff_parts = aff_name.split()
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

            if sum(1 for affs in matched_affiliations if affs) > 0:
                for order, (author, affs) in enumerate(zip(authors, matched_affiliations)):
                    if not affs:
                        continue
                    inst = "; ".join(affs)
                    classification = classify_affiliation(inst, overrides)
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
                        "is_us_institution": classification.is_us,
                        "classification_source": classification.source,
                        "classification_confidence": classification.confidence,
                        "classification_reason": classification.reason,
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


def filter_us_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row["is_us_institution"]]


def filter_classified_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("country") and row["country"] != "Unknown"]


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
            "is_us_institution": row["is_us_institution"],
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
    fetch_affiliations: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    papers = json.loads(raw_json_path.read_text(encoding="utf-8"))
    overrides = load_institution_overrides(output_dir / "reference" / "institution_country_overrides.csv")
    cache_dir = output_dir / "resolution" / "affiliation_cache"
    paper_rows = normalize_papers(config, papers)
    rows, issues = expand_author_rows(config, papers, overrides, cache_dir, fetch_affiliations)
    us_rows = filter_us_rows(rows)
    classified_rows = filter_classified_rows(rows)
    papers_with_author_rows = len({row["paper_id"] for row in rows if row.get("paper_id")})
    papers_without_affiliation_data = sum(1 for issue in issues if issue.get("issue") == "no_affiliation_data")

    write_csv(output_dir / "interim" / f"{config.key}_author_affiliations_expanded.csv", rows,
              ["conference", "year", "paper_id", "title", "name", "article_tag",
               "author_order", "inst", "country", "is_us_institution", "classification_source",
               "classification_confidence", "classification_reason"])
    write_csv(output_dir / "interim" / f"{config.key}_affiliation_resolution_queue.csv", issues,
              ["conference", "year", "paper_id", "title", "issue",
               "authors_count", "affiliations_count", "authors", "affiliations"])
    write_csv(output_dir / "output" / f"{config.key}_author_affiliations.csv", classified_rows,
              ["name", "year", "article_tag", "author_order", "inst", "country"])
    write_csv(output_dir / "output" / f"{config.key}_author_affiliations_audit.csv", classified_rows,
              ["conference", "year", "paper_id", "title", "name", "article_tag",
               "author_order", "inst", "country", "is_us_institution", "classification_source",
               "classification_confidence", "classification_reason"])
    write_workbook(output_dir / "output" / f"{config.key}_author_affiliations.xlsx", classified_rows, ["name", "year", "article_tag", "author_order", "inst", "country"])
    write_csv(output_dir / "interim" / f"{config.key}_institution_classification_candidates.csv", build_affiliation_candidates(rows),
              ["inst", "country", "is_us_institution", "classification_source", "classification_confidence",
               "classification_reason", "example_conference", "example_paper_id", "example_title"])
    write_csv(output_dir / "output" / f"{config.key}_us_institutions.csv", us_rows,
              ["name", "year", "article_tag", "author_order", "inst"])
    write_csv(output_dir / "output" / f"{config.key}_us_institutions_audit.csv", us_rows,
              ["conference", "year", "paper_id", "title", "name", "article_tag",
               "author_order", "inst", "country", "classification_source",
               "classification_confidence", "classification_reason"])
    write_workbook(output_dir / "output" / f"{config.key}_us_institutions.xlsx", us_rows, ["name", "year", "article_tag", "author_order", "inst"])

    report = {
        "conference": config.conference,
        "year": config.year,
        "raw_json": str(raw_json_path),
        "papers_count": len(papers),
        "papers_with_author_rows": papers_with_author_rows,
        "papers_without_affiliation_data": papers_without_affiliation_data,
        "expanded_author_rows": len(rows),
        "classified_author_rows": len(classified_rows),
        "resolved_country_rows": len(classified_rows),
        "unresolved_country_rows": len(rows) - len(classified_rows),
        "us_author_rows": len(us_rows),
        "no_affiliation_issues": len(issues),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (output_dir / "output" / f"{config.key}_validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return report, paper_rows, rows, issues


def run_all_pipelines(
    output_dir: Path,
    conference_keys: list[str] | None = None,
    fetch_affiliations: bool = False,
) -> dict[str, Any]:
    selected_keys = conference_keys or list(CONFERENCES.keys())
    reports = []
    all_papers = []
    all_rows = []
    all_issues = []

    for key in selected_keys:
        config = CONFERENCES[key]
        raw_json_path = output_dir / "raw" / f"{config.key}_papers.json"
        if not raw_json_path.exists():
            print(f"Skipping {config.key}: no raw JSON at {raw_json_path}", file=sys.stderr)
            continue
        report, paper_rows, rows, issues = run_single_conference(config, raw_json_path, output_dir, fetch_affiliations)
        reports.append(report)
        all_papers.extend(paper_rows)
        all_rows.extend(rows)
        all_issues.extend(issues)

    all_us_rows = filter_us_rows(all_rows)
    all_classified_rows = filter_classified_rows(all_rows)
    candidates = build_affiliation_candidates(all_rows)

    write_csv(output_dir / "interim" / "papers_normalized.csv", all_papers,
              ["conference", "year", "paper_id", "title", "article_tag", "authors_count", "url"])
    write_csv(output_dir / "interim" / "author_affiliations_expanded.csv", all_rows,
              ["conference", "year", "paper_id", "title", "name", "article_tag",
               "author_order", "inst", "country", "is_us_institution", "classification_source",
               "classification_confidence", "classification_reason"])
    write_csv(output_dir / "interim" / "us_institution_candidates.csv", candidates,
              ["inst", "country", "is_us_institution", "classification_source", "classification_confidence",
               "classification_reason", "example_conference", "example_paper_id", "example_title"])
    write_csv(output_dir / "interim" / "institution_classification_candidates.csv", candidates,
              ["inst", "country", "is_us_institution", "classification_source", "classification_confidence",
               "classification_reason", "example_conference", "example_paper_id", "example_title"])
    write_csv(output_dir / "interim" / "affiliation_resolution_queue.csv", all_issues,
              ["conference", "year", "paper_id", "title", "issue",
               "authors_count", "affiliations_count", "authors", "affiliations"])
    write_csv(output_dir / "output" / "四大安全顶会_作者机构国家.csv", all_classified_rows,
              ["name", "year", "article_tag", "author_order", "inst", "country"])
    write_csv(output_dir / "output" / "四大安全顶会_作者机构国家_audit.csv", all_classified_rows,
              ["conference", "year", "paper_id", "title", "name", "article_tag",
               "author_order", "inst", "country", "is_us_institution", "classification_source",
               "classification_confidence", "classification_reason"])
    write_workbook(output_dir / "output" / "四大安全顶会_作者机构国家.xlsx", all_classified_rows, ["name", "year", "article_tag", "author_order", "inst", "country"])
    write_csv(output_dir / "output" / "四大安全顶会_美国机构.csv", all_us_rows,
              ["name", "year", "article_tag", "author_order", "inst"])
    write_csv(output_dir / "output" / "四大安全顶会_美国机构_audit.csv", all_us_rows,
              ["conference", "year", "paper_id", "title", "name", "article_tag",
               "author_order", "inst", "country", "classification_source",
               "classification_confidence", "classification_reason"])
    write_workbook(output_dir / "output" / "四大安全顶会_美国机构.xlsx", all_us_rows, ["name", "year", "article_tag", "author_order", "inst"])

    combined = {
        "reports": reports,
        "papers_count": sum(report["papers_count"] for report in reports),
        "papers_with_author_rows": len({row["paper_id"] for row in all_rows if row.get("paper_id")}),
        "papers_without_affiliation_data": sum(1 for issue in all_issues if issue.get("issue") == "no_affiliation_data"),
        "expanded_author_rows": len(all_rows),
        "classified_author_rows": len(all_classified_rows),
        "resolved_country_rows": len(all_classified_rows),
        "unresolved_country_rows": len(all_rows) - len(all_classified_rows),
        "us_author_rows": len(all_us_rows),
        "no_affiliation_issues": len(all_issues),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (output_dir / "output" / "validation_report.json").write_text(
        json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return combined


def fetch_dblp_and_save(config: ConferenceConfig, output_dir: Path) -> None:
    papers = fetch_dblp_papers(config)
    output_path = output_dir / "raw" / f"{config.key}_papers.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(papers, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Fetched {len(papers)} papers for {config.key}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Security conference affiliation and country extraction pipeline")
    parser.add_argument("--conference", nargs="*", default=["all"], help="Conference keys or 'all'")
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    parser.add_argument("--fetch", action="store_true", help="Fetch papers from DBLP")
    parser.add_argument("--fetch-affiliations", action="store_true", help="Fetch affiliations from conference websites")
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

    report = run_all_pipelines(args.output_dir, keys, args.fetch_affiliations)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
