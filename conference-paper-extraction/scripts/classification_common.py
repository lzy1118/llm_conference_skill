from __future__ import annotations

import csv
import html
import re
import unicodedata
from pathlib import Path
from typing import Any, Callable


COUNTRY_PATTERN_RULES: list[tuple[str, list[str]]] = [
    ("China", [r"\btsinghua\b", r"\bpeking\b", r"\bfudan\b", r"\bzhejiang\b", r"\bshanghai jiao\b", r"\bshanghai jiaotong\b", r"\bnanjing\b", r"\bwuhan\b", r"\bhuazhong\b", r"\bxidian\b", r"\bbeihang\b", r"\brenmin\b", r"\bchina\b", r"\bchinese academy of sciences\b", r"\bustc\b", r"\buniversity of science and technology of china\b", r"\bbeijing university of posts and telecommunications\b", r"\bshenzhen university\b", r"\bguangzhou university\b", r"\bshanghaitech\b", r"\bsouthern university of science and technology\b", r"\bnankai university\b", r"\bqi-?anxin\b", r"\bcoremail\b", r"\bhuawei\b", r"\balibaba\b", r"\bant group\b", r"\bsangfor\b", r"\bxi'?an jiaotong\b", r"\btencent keen security lab\b", r"\bshandong university\b", r"\bsouthern university of science and technology\b", r"\bnational university of defense technology\b", r"\bsun yat-sen university\b", r"\bbeijing institute of technology\b", r"\bzhongguancun laboratory\b", r"\bzhongguancun lab\b", r"\btianjin university\b", r"\banhui university\b", r"\banhui university of science and technology\b", r"\bxuanwu lab, tencent\b", r"\bhangzhou dianzi university\b", r"\bhunan university\b", r"\bjd explore academy\b", r"\bchinese aeronautical establishment\b", r"\bsoutheast university\b", r"\bchongqing university\b", r"\bbeijing jiaotong university\b", r"\binstitute of information engineering, cas\b", r"\bkey laboratory of cyberspace security defense, institute of information engineering, cas\b", r"\bshanghai university\b", r"\bsouthern university of science and technolog\b", r"\bbeijing university of technology\b", r"\binstitute of information engineering, chinese academy of science\b", r"\bhenan key laboratory of information security\b", r"\bpengcheng laboratory\b", r"\binformation engineering university\b", r"\binstitute for network sciences and cyberspace\b", r"\bacademy of military sciences\b", r"\bbytedance inc\.\b", r"\bbytedance inc\b", r"\bhang zhou city brain co\., ltd\b", r"\bfeiyu tech\b", r"\bshanghai decareer consulting co\., ltd\b", r"\bjinan university\b", r"\bnyu shanghai\b", r"\bbeijing academy of blockchain and edge computing\b", r"\bbeijing electronic science\s*&\s*technology institute\b", r"\bbeijing electronic science and technology institute\b", r"\bstate key laboratory of cryptology\b"]),
    ("Hong Kong", [r"\bhong kong\b", r"\bcuhk\b", r"\bhkust\b", r"\bcity university of hong kong\b", r"\buniversity of macau\b", r"\bcity university of macau\b"]),
    ("Taiwan", [r"\btaiwan\b", r"\bnational taiwan\b", r"\bnational tsing hua\b", r"\bnational chiao tung\b", r"\bacademia sinica\b", r"\bhon hai research institute\b"]),
    ("Singapore", [r"\bsingapore\b", r"\bnational university of singapore\b", r"\bnanyang technological\b", r"\bsmu\b", r"\ba\*star\b", r"\binfocomm research\b"]),
    ("Japan", [r"\bjapan\b", r"\buniversity of tokyo\b", r"\bkyoto\b", r"\bsony\b", r"\bntt\b", r"\bfujitsu\b", r"\bhitachi\b", r"\bpanasonic\b", r"\baist\b", r"\bnational institute of advanced industrial science and technology\b", r"\bnational institute of information and communications technology\b", r"\bnict\b", r"\bkeio university\b", r"\bnec laboratories europe\b"]),
    ("South Korea", [r"\bkorea\b", r"\bkaist\b", r"\bseoul national\b", r"\byonsei\b", r"\bkorea university\b", r"\bsamsung\b", r"\bsoongsil university\b", r"\bkookmin university\b", r"\bunist\b", r"\bewha womans university\b", r"\bkyung hee university\b", r"\bthe affiliated institute of etri, rok\b"]),
    ("India", [r"\bindia\b", r"\biisc\b", r"\biit bombay\b", r"\biit delhi\b", r"\biit madras\b", r"\bindian institute of technology kharagpur\b", r"\bnit tiruchirappalli\b", r"\bindian institute of technology,? delhi\b"]),
    ("Israel", [r"\bisrael\b", r"\bweizmann\b", r"\btechnion\b", r"\btel aviv\b", r"\btel-?aviv university\b", r"\bhebrew university\b", r"\bbar ilan\b", r"\bbar-ilan\b", r"\bben-gurion\b", r"\breichman university\b", r"\buniversity of haifa\b"]),
    ("Canada", [r"\bcanada\b", r"\buniversity of toronto\b", r"\buniversity of waterloo\b", r"\bmcgill\b", r"\buniversity of british columbia\b", r"\bmerit network\b", r"\buniversity of calgary\b", r"\buniversity of guelph\b", r"\bconcordia university\b", r"\bsimon fraser university\b", r"\buniversity of victoria\b"]),
    ("United Kingdom", [r"\buk\b", r"\bunited kingdom\b", r"\bengland\b", r"\buniversity of cambridge\b", r"\buniversity of oxford\b", r"\bimperial college\b", r"\bucl\b", r"\buniversity college london\b", r"\bking'?s college london\b", r"\broyal holloway\b", r"\buniversity of edinburgh\b", r"\buniversity of manchester\b", r"\buniversity of birmingham\b", r"\buniversity of bristol\b", r"\buniversity of glasgow\b", r"\balan turing institute\b", r"\bdurham university\b", r"\blancaster university\b", r"\bnewcastle university\b", r"\bnorthumbria university\b", r"\bdeepmind\b", r"\buniversity of liverpool\b", r"\buniversity of warwick\b"]),
    ("Switzerland", [r"\bswitzerland\b", r"\beth zurich\b", r"\beth z.rich\b", r"\beth zürich\b", r"\beth zuerich\b", r"\bepfl\b", r"\buniversity of zurich\b", r"\buniversity of bern\b", r"\buniversity of geneva\b", r"\bbasel\b", r"\barmasuisse\b"]),
    ("Germany", [r"\bgermany\b", r"\bbochum\b", r"\bdarmstadt\b", r"\bkarlsruhe institute\b", r"\bmax planck\b", r"\btechnische universit\b", r"\bludwig maximilian\b", r"\buniversity of stuttgart\b", r"\bcispa\b", r"\bfraunhofer\b", r"\bfreie universität berlin\b", r"\bfreie universitat berlin\b", r"\bhamburg\b", r"\bleibniz university hannover\b", r"\bleibniz universität hannover\b", r"\bleibniz universitat hannover\b", r"\buniversity of würzburg\b", r"\buniversity of wurzburg\b", r"\btechnische universität braunschweig\b", r"\btechnische universitat braunschweig\b", r"\buniversity of duisburg-essen\b", r"\bpaderborn university\b", r"\btechnische universität berlin\b", r"\btechnische universitat berlin\b", r"\btu braunschweig\b", r"\buniversity of lübeck\b", r"\bfriedrich-alexander-universität erlangen-nürnberg\b", r"\bfriedrich-alexander-universitat erlangen-nurnberg\b", r"\bmünster university of applied sciences\b", r"\bmunster university of applied sciences\b", r"\bdatenanfragen\.de\b", r"\bsaarland university\b", r"\brwth aachen university\b", r"\btechnical university of munich\b", r"\btu dortmund university\b", r"\bhasso plattner institute\b", r"\buniversity of potsdam\b", r"\buniversity of osnabrück\b", r"\buniversity of osnabruck\b"]),
    ("France", [r"\bfrance\b", r"\binria\b", r"\bcnrs\b", r"\borange\b", r"\beurecom\b", r"\bcea, list, université paris saclay\b", r"\bcea, list, universite paris saclay\b", r"\buniversité paris saclay\b", r"\buniversite paris saclay\b"]),
    ("Netherlands", [r"\bnetherlands\b", r"\bdelft\b", r"\beindhoven\b", r"\braadboud\b", r"\bradboud university\b", r"\bvrije universiteit\b", r"\buniversiteit leiden\b", r"\buniversiteit utrecht\b", r"\buniversiteit amsterdam\b", r"\bsidn labs\b", r"\buniversity of twente\b", r"\butrecht university\b"]),
    ("Luxembourg", [r"\bluxembourg\b", r"\buniversity of luxembourg\b"]),
    ("Denmark", [r"\bdenmark\b", r"\btechnical university of denmark\b", r"\baarhus university\b"]),
    ("Sweden", [r"\bsweden\b", r"\bkth\b", r"\bchalmers\b", r"\bkarlstad university\b"]),
    ("Norway", [r"\bnorway\b", r"\buniversity of oslo\b"]),
    ("Finland", [r"\bfinland\b", r"\baalto\b", r"\buniversity of helsinki\b", r"\btampere university\b", r"\bf-secure\b", r"\bmozilla\b"]),
    ("Australia", [r"\baustralia\b", r"\buniversity of melbourne\b", r"\buniversity of sydney\b", r"\bmonash\b", r"\buniversity of queensland\b", r"\buniversity of adelaide\b", r"\buniversity of new south wales\b", r"\bswinburne university of technology\b", r"\bmacquarie university\b", r"\baustralian national university\b", r"\bcsiro'?s data61\b", r"\bdata61\b", r"\buniversity of technology sydney\b", r"\brmit university\b", r"\bwestern sydney university\b", r"\bdefence science and technology group\b"]),
    ("New Zealand", [r"\bnew zealand\b", r"\buniversity of auckland\b"]),
    ("Austria", [r"\baustria\b", r"\ba-sit\b", r"\baustrian institute of technology\b", r"\bgraz university of technology\b", r"\bdynatrace research\b", r"\bcomplexity science hub vienna\b", r"\biak\b", r"\biaik\b", r"\btu wien\b", r"\buniversity of innsbruck\b", r"\buniversity of vienna\b"]),
    ("Belgium", [r"\bbelgium\b", r"\bku leuven\b", r"\bimec\b", r"\buclouvain\b"]),
    ("Saudi Arabia", [r"\bsaudi arabia\b", r"\bking abdullah university of science and technology\b", r"\bkaust\b", r"\bthuwal\b"]),
    ("Czech Republic", [r"\bbrno university of technology\b"]),
    ("Portugal", [r"\bportugal\b", r"\buniversidade do minho\b", r"\binesc-id\b", r"\binstituto superior técnico\b", r"\binstituto superior tecnico\b", r"\buniversidade de lisboa\b", r"\bnova lincs\b", r"\buniversidade nova de lisboa\b"]),
    ("Hungary", [r"\beötvös loránd university\b", r"\beotvos lorand university\b"]),
    ("Greece", [r"\bnational technical university of athens\b"]),
    ("Turkey", [r"\btobb university of economics and technology\b"]),
    ("Ireland", [r"\bireland\b"]),
    ("Italy", [r"\bitaly\b", r"\buniversity of trento\b", r"\buniversity of padua\b", r"\buniversità ca' foscari venezia\b", r"\buniversita ca' foscari venezia\b", r"\bsapienza university of rome\b", r"\blink campus university of rome\b"]),
    ("Spain", [r"\bspain\b", r"\bimdea software institute\b", r"\bimdea networks institute\b", r"\buniversidad carlos iii de madrid\b", r"\buniversidad politécnica de madrid\b", r"\buniversidad politecnica de madrid\b"]),
]

US_PATTERN_RULES: list[str] = [
    r"\bindiana university bloomington\b",
    r"\bbinghamton university\b",
    r"\bclemson university\b",
    r"\bdartmouth college\b",
    r"\bflorida state university\b",
    r"\biowa state university\b",
    r"\bnew jersey institute of technology\b",
    r"\blehigh university\b",
    r"\bmichigan state university\b",
    r"\bmichigan technological\b",
    r"\bpennsylvania state university\b",
    r"\bgeorgetown law\b",
    r"\bsanta clara university\b",
    r"\bakamai\b",
    r"\bcisco\b",
    r"\bcisco talos\b",
    r"\bibm\b",
    r"\bibm t\.j\. watson\b",
    r"\bicann\b",
    r"\bduckduckgo\b",
    r"\bmassmutual\b",
    r"\boracle\b",
    r"\bred hat\b",
    r"\braytheon\b",
    r"\bperaton labs\b",
    r"\brivos\b",
    r"\bkentik\b",
    r"\bnorton research group\b",
    r"\buniversity of chicago\b",
    r"\buc riverside\b",
    r"\buniversity of california,? riverside\b",
    r"\buniversity of vermont\b",
    r"\buniversity of rochester\b",
    r"\brochester institute of technology\b",
    r"\bwilliam\s*&\s*mary\b",
    r"\bwilliam and mary\b",
    r"\bwilliam\s*&\s*mary\b",
    r"\badobe research\b",
    r"\btexas advanced computing center\b",
    r"\btrustwave\b",
    r"\btower research\b",
    r"\btufts university\b",
    r"\bnxp semiconductors\b",
    r"\bwashington university in st\. louis\b",
    r"\bgeorgetown university\b",
    r"\bbrigham young university\b",
    r"\buniversity of central florida\b",
    r"\bflorida international university\b",
    r"\bnetapp\b",
    r"\bgalois\b",
    r"\bgalois, inc\.\b",
    r"\bj\.p\. morgan\b",
    r"\bcyber-physical systems security lab, florida international university\b",
    r"\buniversity of louisiana at lafayette\b",
    r"\buniversity at buffalo\b",
    r"\bvirginia commonwealth university\b",
    r"\bvmware research\b",
    r"\billinois institute of technology\b",
    r"\bcal poly, san luis obispo\b",
    r"\bbrave software\b",
    r"\btulane university\b",
    r"\buniversity of wyoming\b",
    r"\bfordham university\b",
    r"\bgeorgia state university\b",
    r"\bindiana university\b",
    r"\bindiana university bloomington\b",
    r"\buniversity of denver\b",
    r"\bvanderbilt university\b",
    r"\bvirginia polytechnic institute and state university\b",
    r"\bvirginia polytechnic institute & state university\b",
    r"\btexas tech university\b",
    r"\buniversity of georgia\b",
    r"\buniversity of louisville\b",
    r"\buniversity of north texas\b",
    r"\buniversity of south florida\b",
    r"\buniversity of virginia\b",
    r"\buniversity of vriginia\b",
    r"\bwichita state university\b",
]


def normalize_space(value: str) -> str:
    value = html.unescape(value)
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("’", "'")
    return re.sub(r"\s+", " ", value).strip()


def load_override_rows(path: Path, classification_factory: Callable[[str, bool, str, float, str], Any]) -> dict[str, Any]:
    if not path.exists():
        return {}
    overrides: dict[str, Any] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            inst = normalize_space(row.get("inst", ""))
            if not inst:
                continue
            is_us = normalize_space(row.get("is_us_institution", "")).casefold() in {"true", "1", "yes", "y"}
            country = normalize_space(row.get("country", ""))
            if not country:
                if is_us:
                    country = "United States"
                else:
                    detected_country, _detected_reason = detect_country_from_patterns(inst.casefold())
                    country = detected_country or "Unknown"
            reason = normalize_space(row.get("reason", "override")) or "override"
            overrides[inst.casefold()] = classification_factory(country, is_us, "override", 1.0, reason)
    return overrides


def detect_country_from_patterns(lower: str) -> tuple[str | None, str | None]:
    for country, patterns in COUNTRY_PATTERN_RULES:
        for pattern in patterns:
            if re.search(pattern, lower):
                return country, f"country_keyword_{country.casefold().replace(' ', '_')}"
    return None, None


def classify_with_patterns(
    affiliation: str,
    *,
    overrides: dict[str, Any] | None,
    exact_aliases: set[str],
    non_us_patterns: list[str],
    us_patterns: list[str],
    classification_factory: Callable[[str, bool, str, float, str], Any],
) -> Any:
    normalized = normalize_space(affiliation)
    lower = normalized.casefold()
    if overrides and lower in overrides:
        return overrides[lower]
    if any(
        marker in lower
        for marker in [
            "hubei minzu university",
            "academy of mathematics and system science, chinese academy sciences",
            "academy of mathematics and systems science, chinese academy of sciences",
            "beijing institute of mathematical sciences and application",
            "beijing institute of mathematical sciences and applications",
        ]
    ):
        return classification_factory("China", False, "rule", 0.95, "reference_alias_china")
    if lower in exact_aliases:
        return classification_factory("United States", True, "rule", 1.0, "exact_us_alias")
    if any(
        marker in lower
        for marker in [
            "aws",
            "amazon web services",
            "university of southern california",
        ]
    ):
        return classification_factory("United States", True, "rule", 0.95, "reference_alias_us")
    if lower == "stanford":
        return classification_factory("United States", True, "rule", 0.95, "reference_alias_us")
    country, country_reason = detect_country_from_patterns(lower)
    if country is not None and country != "United States":
        return classification_factory(country, False, "rule", 0.95, country_reason or "country_keyword")
    for pattern in US_PATTERN_RULES:
        if re.search(pattern, lower):
            return classification_factory("United States", True, "rule", 0.95, "us_keyword")
    for pattern in us_patterns:
        if re.search(pattern, lower):
            return classification_factory("United States", True, "rule", 0.95, "us_keyword")
    if re.search(r"\b(united states|usa|u\.s\.a\.|, us|, usa)\b", lower):
        return classification_factory("United States", True, "rule", 0.95, "us_location_marker")
    if country is not None:
        return classification_factory(country, False, "rule", 0.95, country_reason or "country_keyword")
    for pattern in non_us_patterns:
        if re.search(pattern, lower):
            return classification_factory("Unknown", False, "rule", 0.7, "non_us_keyword")
    return classification_factory("Unknown", False, "unresolved", 0.0, "needs_review")
