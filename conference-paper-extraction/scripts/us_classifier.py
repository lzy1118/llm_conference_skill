"""US Institution Classifier for Academic Conference Papers.

Provides three-tier classification engine for determining whether
an author affiliation is a US-based institution.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Classification:
    """Result of affiliation classification."""
    is_us: bool
    source: str  # "rule", "override", "unresolved"
    confidence: float  # 0.0 to 1.0
    reason: str


# Tier 1: Exact aliases (case-insensitive)
US_EXACT_ALIASES: set[str] = {
    # Universities
    "mit", "cmu", "ucla", "ucsd", "ucsb", "ucb", "ucsf",
    "uc irvine", "uc davis", "uc santa barbara", "uc santa cruz",
    "uc los angeles", "uc berkeley", "uc san diego",
    "ut austin", "uiuc", "umd", "nyu", "yale", "duke",
    "usc", "gatech", "georgia tech",
    # Research institutions
    "nist", "sri", "nsf", "nih",
    # Companies
    "google", "microsoft", "meta", "amazon", "aws", "apple",
    "nvidia", "intel", "qualcomm", "ibm",
}

# Tier 2: Non-US exclusion patterns
NON_US_KEYWORD_PATTERNS: list[str] = [
    # Europe
    r"\beth zurich\b", r"\beth z.rich\b",
    r"\buniversity of cambridge\b", r"\buniversity of oxford\b",
    r"\bimperial college\b", r"\bucl\b", r"\buniversity college london\b",
    r"\binria\b", r"\bcnrs\b",
    r"\btechnische universit\b", r"\bludwig maximilian\b", r"\bmax planck\b",
    r"\buniversity of edinburgh\b", r"\buniversity of manchester\b",
    r"\bruhr university bochum\b", r"\buniversity of luxembourg\b",
    # Asia
    r"\btsinghua\b", r"\bpeking\b", r"\bfudan\b",
    r"\buniversity of tokyo\b", r"\bkyoto\b",
    r"\bnanyang technological\b", r"\bnational university of singapore\b",
    r"\bseoul national\b", r"\bkaist\b",
    r"\bhuawei\b", r"\balibaba\b", r"\btencent\b", r"\bbaidu\b",
    # Canada
    r"\buniversity of waterloo\b", r"\buniversity of toronto\b",
    r"\bmcgill\b", r"\buniversity of british columbia\b",
    # Australia
    r"\buniversity of melbourne\b", r"\buniversity of sydney\b",
    # Israel
    r"\bweizmann\b", r"\btechnion\b", r"\btel aviv\b", r"\bhebrew university\b",
]

# Tier 3: US keyword patterns
US_KEYWORD_PATTERNS: list[str] = [
    # Top universities
    r"\bmassachusetts institute of technology\b",
    r"\bcarnegie mellon university\b",
    r"\bstanford university\b", r"\bstanford\b",
    r"\bharvard\b", r"\bprinceton\b", r"\bcolumbia\b",
    r"\bcornell university\b", r"\bcornell tech\b",
    r"\bbrown university\b", r"\bduke university\b",
    r"\byale university\b", r"\byale\b", r"\bcaltech\b",
    # UC system
    r"\buniversity of california\b",
    r"\buc berkeley\b", r"\bucla\b", r"\bucsd\b", r"\bucsb\b",
    # Other major universities
    r"\buniversity of washington\b", r"\buw\b",
    r"\buniversity of maryland\b", r"\bumd\b",
    r"\buniversity of michigan\b",
    r"\buniversity of texas\b", r"\but austin\b",
    r"\buniversity of illinois\b", r"\buiuc\b",
    r"\bgeorgia tech\b", r"\bgeorgia institute of technology\b",
    r"\bpurdue\b", r"\bnortheastern\b",
    r"\brice university\b", r"\bstony brook university\b",
    # Research labs
    r"\bgoogle\b", r"\bmeta\b", r"\bmicrosoft\b",
    r"\bibm research\b", r"\bintel\b",
    r"\bnvidia\b", r"\bqualcomm\b", r"\bapple\b",
    r"\bamazon\b", r"\baws\b",
    r"\bsandia national lab\b", r"\boak ridge national lab\b",
    r"\bnasa\b", r"\bnoaa\b", r"\bnsa\b", r"\bdarpa\b",
    # Location markers
    r"\bunited states\b", r"\busa\b", r"\bu\.s\.a\.\b",
]


def load_overrides(path: Path) -> dict[str, Classification]:
    """Load manual overrides from CSV file."""
    overrides: dict[str, Classification] = {}
    if not path.exists():
        return overrides

    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            inst = row.get("inst", "").strip()
            if inst:
                key = inst.casefold()
                is_us = row.get("is_us_institution", "").lower() == "true"
                reason = row.get("reason", "manual_override")
                overrides[key] = Classification(
                    is_us=is_us, source="override", confidence=1.0, reason=reason
                )
    return overrides


def classify_affiliation(
    affiliation: str,
    overrides: dict[str, Classification] | None = None,
) -> Classification:
    """Classify an affiliation string as US or non-US institution.

    Priority order:
    1. Override file (highest)
    2. Tier 1: Exact aliases
    3. Tier 2: Non-US exclusion
    4. Tier 3: US keywords
    5. Location markers
    6. Unresolved (lowest)
    """
    normalized = re.sub(r"\s+", " ", affiliation).strip()
    lower = normalized.casefold()

    # Check overrides first
    if overrides and lower in overrides:
        return overrides[lower]

    # Tier 1: Exact match
    if lower in US_EXACT_ALIASES:
        return Classification(True, "rule", 1.0, "exact_us_alias")

    # Tier 2: Non-US exclusion
    for pattern in NON_US_KEYWORD_PATTERNS:
        if re.search(pattern, lower):
            return Classification(False, "rule", 1.0, "non_us_keyword")

    # Tier 3: US keywords
    for pattern in US_KEYWORD_PATTERNS:
        if re.search(pattern, lower):
            return Classification(True, "rule", 0.95, "us_keyword")

    # Location marker
    if re.search(r"\b(united states|usa|u\.s\.a\.|, us|, usa)\b", lower):
        return Classification(True, "rule", 0.95, "us_location_marker")

    # Unresolved
    return Classification(False, "unresolved", 0.0, "needs_review")


def classify_batch(
    affiliations: list[str],
    overrides: dict[str, Classification] | None = None,
) -> list[dict]:
    """Classify a batch of affiliations and return results with metadata."""
    results = []
    for aff in affiliations:
        cls = classify_affiliation(aff, overrides)
        results.append({
            "affiliation": aff,
            "is_us_institution": cls.is_us,
            "classification_source": cls.source,
            "classification_confidence": cls.confidence,
            "classification_reason": cls.reason,
        })
    return results


if __name__ == "__main__":
    # Example usage
    test_affiliations = [
        "MIT",
        "ETH Zurich",
        "Stanford University",
        "Tsinghua University",
        "Google",
        "University of Cambridge",
        "Unknown Institute",
    ]

    results = classify_batch(test_affiliations)
    for r in results:
        print(f"{r['affiliation']:40} -> US={r['is_us_institution']}, "
              f"confidence={r['classification_confidence']:.2f}, "
              f"reason={r['classification_reason']}")
