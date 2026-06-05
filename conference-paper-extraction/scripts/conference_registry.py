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
    "asiacrypt_2020": RegisteredConference(
        key="asiacrypt_2020",
        conference="ASIACRYPT",
        year=2020,
        family="crypto",
        backend="iacr_top3",
        description="IACR JSON accepted papers with aligned affiliations.",
    ),
    "asiacrypt_2021": RegisteredConference(
        key="asiacrypt_2021",
        conference="ASIACRYPT",
        year=2021,
        family="crypto",
        backend="iacr_top3",
        description="IACR JSON accepted papers with aligned affiliations.",
    ),
    "asiacrypt_2022": RegisteredConference(
        key="asiacrypt_2022",
        conference="ASIACRYPT",
        year=2022,
        family="crypto",
        backend="iacr_top3",
        description="IACR JSON accepted papers with aligned affiliations.",
    ),
    "asiacrypt_2023": RegisteredConference(
        key="asiacrypt_2023",
        conference="ASIACRYPT",
        year=2023,
        family="crypto",
        backend="iacr_top3",
        description="IACR JSON accepted papers with aligned affiliations.",
    ),
    "asiacrypt_2024": RegisteredConference(
        key="asiacrypt_2024",
        conference="ASIACRYPT",
        year=2024,
        family="crypto",
        backend="iacr_top3",
        description="IACR JSON accepted papers with aligned affiliations.",
    ),
    "asiacrypt_2025": RegisteredConference(
        key="asiacrypt_2025",
        conference="ASIACRYPT",
        year=2025,
        family="crypto",
        backend="iacr_top3",
        description="IACR JSON accepted papers with aligned affiliations.",
    ),
    "crypto_2020": RegisteredConference(
        key="crypto_2020",
        conference="CRYPTO",
        year=2020,
        family="crypto",
        backend="iacr_top3",
        description="IACR JSON accepted papers with aligned affiliations.",
    ),
    "crypto_2021": RegisteredConference(
        key="crypto_2021",
        conference="CRYPTO",
        year=2021,
        family="crypto",
        backend="iacr_top3",
        description="IACR JSON accepted papers with aligned affiliations.",
    ),
    "crypto_2022": RegisteredConference(
        key="crypto_2022",
        conference="CRYPTO",
        year=2022,
        family="crypto",
        backend="iacr_top3",
        description="IACR JSON accepted papers with aligned affiliations.",
    ),
    "crypto_2023": RegisteredConference(
        key="crypto_2023",
        conference="CRYPTO",
        year=2023,
        family="crypto",
        backend="iacr_top3",
        description="IACR JSON accepted papers with aligned affiliations.",
    ),
    "crypto_2024": RegisteredConference(
        key="crypto_2024",
        conference="CRYPTO",
        year=2024,
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
    "eurocrypt_2020": RegisteredConference(
        key="eurocrypt_2020",
        conference="EUROCRYPT",
        year=2020,
        family="crypto",
        backend="iacr_top3",
        description="IACR JSON accepted papers with aligned affiliations.",
    ),
    "eurocrypt_2021": RegisteredConference(
        key="eurocrypt_2021",
        conference="EUROCRYPT",
        year=2021,
        family="crypto",
        backend="iacr_top3",
        description="IACR JSON accepted papers with aligned affiliations.",
    ),
    "eurocrypt_2022": RegisteredConference(
        key="eurocrypt_2022",
        conference="EUROCRYPT",
        year=2022,
        family="crypto",
        backend="iacr_top3",
        description="IACR JSON accepted papers with aligned affiliations.",
    ),
    "eurocrypt_2023": RegisteredConference(
        key="eurocrypt_2023",
        conference="EUROCRYPT",
        year=2023,
        family="crypto",
        backend="iacr_top3",
        description="IACR JSON accepted papers with aligned affiliations.",
    ),
    "eurocrypt_2024": RegisteredConference(
        key="eurocrypt_2024",
        conference="EUROCRYPT",
        year=2024,
        family="crypto",
        backend="iacr_top3",
        description="IACR JSON accepted papers with aligned affiliations.",
    ),
    "eurocrypt_2025": RegisteredConference(
        key="eurocrypt_2025",
        conference="EUROCRYPT",
        year=2025,
        family="crypto",
        backend="iacr_top3",
        description="IACR JSON accepted papers with aligned affiliations.",
    ),
    "usenix_security_2020": RegisteredConference(
        key="usenix_security_2020",
        conference="USENIX_SECURITY",
        year=2020,
        family="security",
        backend="security_real",
        description="DBLP papers with USENIX page meta affiliation resolution.",
    ),
    "usenix_security_2021": RegisteredConference(
        key="usenix_security_2021",
        conference="USENIX_SECURITY",
        year=2021,
        family="security",
        backend="security_real",
        description="DBLP papers with USENIX page meta affiliation resolution.",
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
    "usenix_security_2024": RegisteredConference(
        key="usenix_security_2024",
        conference="USENIX_SECURITY",
        year=2024,
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
    "ndss_2020": RegisteredConference(
        key="ndss_2020",
        conference="NDSS",
        year=2020,
        family="security",
        backend="security_real",
        description="DBLP papers with NDSS page affiliation parsing.",
    ),
    "ndss_2021": RegisteredConference(
        key="ndss_2021",
        conference="NDSS",
        year=2021,
        family="security",
        backend="security_real",
        description="DBLP papers with NDSS page affiliation parsing.",
    ),
    "ndss_2022": RegisteredConference(
        key="ndss_2022",
        conference="NDSS",
        year=2022,
        family="security",
        backend="security_real",
        description="DBLP papers with NDSS page affiliation parsing.",
    ),
    "ndss_2023": RegisteredConference(
        key="ndss_2023",
        conference="NDSS",
        year=2023,
        family="security",
        backend="security_real",
        description="DBLP papers with NDSS page affiliation parsing.",
    ),
    "ndss_2024": RegisteredConference(
        key="ndss_2024",
        conference="NDSS",
        year=2024,
        family="security",
        backend="security_real",
        description="DBLP papers with NDSS page affiliation parsing.",
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
    "ieee_sp_2020": RegisteredConference(
        key="ieee_sp_2020",
        conference="IEEE_S&P",
        year=2020,
        family="security",
        backend="security_real",
        description="DBLP papers with IEEE Xplore metadata resolution.",
    ),
    "ieee_sp_2021": RegisteredConference(
        key="ieee_sp_2021",
        conference="IEEE_S&P",
        year=2021,
        family="security",
        backend="security_real",
        description="DBLP papers with IEEE Xplore metadata resolution.",
    ),
    "ieee_sp_2022": RegisteredConference(
        key="ieee_sp_2022",
        conference="IEEE_S&P",
        year=2022,
        family="security",
        backend="security_real",
        description="DBLP papers with IEEE Xplore metadata resolution.",
    ),
    "ieee_sp_2023": RegisteredConference(
        key="ieee_sp_2023",
        conference="IEEE_S&P",
        year=2023,
        family="security",
        backend="security_real",
        description="DBLP papers with IEEE Xplore metadata resolution.",
    ),
    "ieee_sp_2024": RegisteredConference(
        key="ieee_sp_2024",
        conference="IEEE_S&P",
        year=2024,
        family="security",
        backend="security_real",
        description="DBLP papers with IEEE Xplore metadata resolution.",
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
    "ccs_2020": RegisteredConference(
        key="ccs_2020",
        conference="CCS",
        year=2020,
        family="security",
        backend="security_real",
        description="DBLP papers with Semantic Scholar fallback affiliations.",
    ),
    "ccs_2021": RegisteredConference(
        key="ccs_2021",
        conference="CCS",
        year=2021,
        family="security",
        backend="security_real",
        description="DBLP papers with Semantic Scholar fallback affiliations.",
    ),
    "ccs_2022": RegisteredConference(
        key="ccs_2022",
        conference="CCS",
        year=2022,
        family="security",
        backend="security_real",
        description="DBLP papers with Semantic Scholar fallback affiliations.",
    ),
    "ccs_2023": RegisteredConference(
        key="ccs_2023",
        conference="CCS",
        year=2023,
        family="security",
        backend="security_real",
        description="DBLP papers with Semantic Scholar fallback affiliations.",
    ),
    "ccs_2024": RegisteredConference(
        key="ccs_2024",
        conference="CCS",
        year=2024,
        family="security",
        backend="security_real",
        description="DBLP papers with Semantic Scholar fallback affiliations.",
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
        conference_keys=(
            "asiacrypt_2020",
            "asiacrypt_2021",
            "asiacrypt_2022",
            "asiacrypt_2023",
            "asiacrypt_2024",
            "asiacrypt_2025",
            "crypto_2020",
            "crypto_2021",
            "crypto_2022",
            "crypto_2023",
            "crypto_2024",
            "crypto_2025",
            "eurocrypt_2020",
            "eurocrypt_2021",
            "eurocrypt_2022",
            "eurocrypt_2023",
            "eurocrypt_2024",
            "eurocrypt_2025",
        ),
    ),
    "top4_security": ConferenceGroup(
        key="top4_security",
        description="Four flagship security conferences.",
        conference_keys=(
            "usenix_security_2020",
            "usenix_security_2021",
            "usenix_security_2022",
            "usenix_security_2023",
            "usenix_security_2024",
            "usenix_security_2025",
            "usenix_security_2026",
            "ndss_2020",
            "ndss_2021",
            "ndss_2022",
            "ndss_2023",
            "ndss_2024",
            "ndss_2025",
            "ndss_2026",
            "ieee_sp_2020",
            "ieee_sp_2021",
            "ieee_sp_2022",
            "ieee_sp_2023",
            "ieee_sp_2024",
            "ieee_sp_2025",
            "ieee_sp_2026",
            "ccs_2020",
            "ccs_2021",
            "ccs_2022",
            "ccs_2023",
            "ccs_2024",
            "ccs_2025",
            "ccs_2026",
        ),
    ),
    "top7_2020_2025": ConferenceGroup(
        key="top7_2020_2025",
        description="Top3 crypto plus top4 security for 2020-2025.",
        conference_keys=(
            "asiacrypt_2020",
            "asiacrypt_2021",
            "asiacrypt_2022",
            "asiacrypt_2023",
            "asiacrypt_2024",
            "asiacrypt_2025",
            "crypto_2020",
            "crypto_2021",
            "crypto_2022",
            "crypto_2023",
            "crypto_2024",
            "crypto_2025",
            "eurocrypt_2020",
            "eurocrypt_2021",
            "eurocrypt_2022",
            "eurocrypt_2023",
            "eurocrypt_2024",
            "eurocrypt_2025",
            "usenix_security_2020",
            "usenix_security_2021",
            "usenix_security_2022",
            "usenix_security_2023",
            "usenix_security_2024",
            "usenix_security_2025",
            "ndss_2020",
            "ndss_2021",
            "ndss_2022",
            "ndss_2023",
            "ndss_2024",
            "ndss_2025",
            "ieee_sp_2020",
            "ieee_sp_2021",
            "ieee_sp_2022",
            "ieee_sp_2023",
            "ieee_sp_2024",
            "ieee_sp_2025",
            "ccs_2020",
            "ccs_2021",
            "ccs_2022",
            "ccs_2023",
            "ccs_2024",
            "ccs_2025",
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
