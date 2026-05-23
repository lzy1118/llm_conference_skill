from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RegisteredConference:
    key: str
    conference: str
    year: int
    family: str
    backend: str
    description: str


@dataclass(frozen=True)
class ConferenceGroup:
    key: str
    description: str
    conference_keys: tuple[str, ...]


CONFERENCES: dict[str, RegisteredConference] = {
    "asiacrypt_2025": RegisteredConference(
        key="asiacrypt_2025",
        conference="ASIACRYPT",
        year=2025,
        family="crypto",
        backend="iacr_top3",
        description="IACR JSON accepted papers with aligned affiliations.",
    ),
    "crypto_2025": RegisteredConference(
        key="crypto_2025",
        conference="CRYPTO",
        year=2025,
        family="crypto",
        backend="iacr_top3",
        description="IACR JSON accepted papers with aligned affiliations.",
    ),
    "eurocrypt_2026": RegisteredConference(
        key="eurocrypt_2026",
        conference="EUROCRYPT",
        year=2026,
        family="crypto",
        backend="iacr_top3",
        description="IACR JSON accepted papers with aligned affiliations.",
    ),
    "usenix_security_2022": RegisteredConference(
        key="usenix_security_2022",
        conference="USENIX_SECURITY",
        year=2022,
        family="security",
        backend="security_real",
        description="DBLP papers with USENIX page meta affiliation resolution.",
    ),
    "usenix_security_2023": RegisteredConference(
        key="usenix_security_2023",
        conference="USENIX_SECURITY",
        year=2023,
        family="security",
        backend="security_real",
        description="DBLP papers with USENIX page meta affiliation resolution.",
    ),
    "usenix_security_2025": RegisteredConference(
        key="usenix_security_2025",
        conference="USENIX_SECURITY",
        year=2025,
        family="security",
        backend="security_real",
        description="DBLP papers with USENIX page meta affiliation resolution.",
    ),
    "usenix_security_2026": RegisteredConference(
        key="usenix_security_2026",
        conference="USENIX_SECURITY",
        year=2026,
        family="security",
        backend="security_real",
        description="DBLP papers with USENIX page meta affiliation resolution.",
    ),
    "ndss_2025": RegisteredConference(
        key="ndss_2025",
        conference="NDSS",
        year=2025,
        family="security",
        backend="security_real",
        description="DBLP papers with NDSS page affiliation parsing.",
    ),
    "ndss_2026": RegisteredConference(
        key="ndss_2026",
        conference="NDSS",
        year=2026,
        family="security",
        backend="security_real",
        description="DBLP papers with NDSS page affiliation parsing.",
    ),
    "ieee_sp_2025": RegisteredConference(
        key="ieee_sp_2025",
        conference="IEEE_S&P",
        year=2025,
        family="security",
        backend="security_real",
        description="DBLP papers with IEEE Xplore metadata resolution.",
    ),
    "ieee_sp_2026": RegisteredConference(
        key="ieee_sp_2026",
        conference="IEEE_S&P",
        year=2026,
        family="security",
        backend="security_real",
        description="DBLP papers with IEEE Xplore metadata resolution.",
    ),
    "ccs_2025": RegisteredConference(
        key="ccs_2025",
        conference="CCS",
        year=2025,
        family="security",
        backend="security_real",
        description="DBLP papers with Semantic Scholar fallback affiliations.",
    ),
    "ccs_2026": RegisteredConference(
        key="ccs_2026",
        conference="CCS",
        year=2026,
        family="security",
        backend="security_real",
        description="DBLP papers with Semantic Scholar fallback affiliations.",
    ),
}


GROUPS: dict[str, ConferenceGroup] = {
    "top3_crypto": ConferenceGroup(
        key="top3_crypto",
        description="Three flagship IACR cryptography conferences.",
        conference_keys=("asiacrypt_2025", "crypto_2025", "eurocrypt_2026"),
    ),
    "top4_security": ConferenceGroup(
        key="top4_security",
        description="Four flagship security conferences.",
        conference_keys=(
            "usenix_security_2022",
            "usenix_security_2023",
            "usenix_security_2025",
            "usenix_security_2026",
            "ndss_2025",
            "ndss_2026",
            "ieee_sp_2025",
            "ieee_sp_2026",
            "ccs_2025",
            "ccs_2026",
        ),
    ),
    "all": ConferenceGroup(
        key="all",
        description="All registered crypto and security conferences.",
        conference_keys=tuple(CONFERENCES.keys()),
    ),
}


def list_backend_keys() -> tuple[str, ...]:
    return tuple(sorted({conference.backend for conference in CONFERENCES.values()}))


def expand_selection(conference_keys: list[str], group_keys: list[str]) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()

    for group_key in group_keys:
        if group_key not in GROUPS:
            raise KeyError(f"Unknown conference group: {group_key}")
        for conference_key in GROUPS[group_key].conference_keys:
            if conference_key not in seen:
                selected.append(conference_key)
                seen.add(conference_key)

    for conference_key in conference_keys:
        if conference_key not in CONFERENCES:
            raise KeyError(f"Unknown conference: {conference_key}")
        if conference_key not in seen:
            selected.append(conference_key)
            seen.add(conference_key)

    return selected


def group_by_backend(conference_keys: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for conference_key in conference_keys:
        conference = CONFERENCES[conference_key]
        grouped.setdefault(conference.backend, []).append(conference_key)
    return grouped
