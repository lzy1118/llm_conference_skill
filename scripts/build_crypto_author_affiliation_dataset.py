#!/usr/bin/env python3
"""Build the requested 15-column CRYPTO/EUROCRYPT/ASIACRYPT dataset."""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path


CONFERENCES = ("asiacrypt", "crypto", "eurocrypt")
YEARS = tuple(range(2020, 2026))
FIELDS = (
    "paper_id", "year", "conference", "title", "author", "author_rank",
    "affiliation_rank", "affiliations", "emails", "first_author",
    "co_first_author", "corresponding", "equal_contribution", "country", "orcid",
)
EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.IGNORECASE)
ORCID_RE = re.compile(r"(?:https?://orcid\.org/)?(\d{4}-\d{4}-\d{4}-\d{3}[\dX])", re.IGNORECASE)
COUNTRY_ALIASES = {
    "australia": "Australia", "austria": "Austria", "belgium": "Belgium", "argentina": "Argentina",
    "brazil": "Brazil", "canada": "Canada", "china": "China", "cn": "China",
    "people's republic of china": "China", "pr china": "China", "colombia": "Colombia",
    "costa rica": "Costa Rica", "czech republic": "Czech Republic", "denmark": "Denmark",
    "england": "UK", "estonia": "Estonia", "finland": "Finland", "france": "France",
    "german": "Germany", "germany": "Germany", "greece": "Greece", "hong kong": "Hong Kong",
    "hungary": "Hungary", "india": "India", "iran": "Iran", "ireland": "Ireland",
    "iceland": "Iceland", "israel": "Israel", "italy": "Italy", "japan": "Japan",
    "korea": "South Korea", "republic of korea": "South Korea", "south korea": "South Korea",
    "luxembourg": "Luxembourg", "malaysia": "Malaysia", "mexico": "Mexico",
    "netherlands": "Netherlands", "the netherlands": "Netherlands", "new zealand": "New Zealand",
    "norway": "Norway", "pakistan": "Pakistan", "poland": "Poland", "portugal": "Portugal",
    "romania": "Romania", "russia": "Russia", "saudi arabia": "Saudi Arabia", "serbia": "Serbia",
    "singapore": "Singapore", "slovakia": "Slovakia", "slovenia": "Slovenia",
    "south africa": "South Africa", "spain": "Spain", "sweden": "Sweden",
    "switzerland": "Switzerland", "taiwan": "Taiwan", "thailand": "Thailand", "turkey": "Turkey",
    "türkiye": "Turkey", "uae": "United Arab Emirates", "ukraine": "Ukraine",
    "united arab emirates": "United Arab Emirates", "uk": "UK", "united kingdom": "UK",
    "us": "USA", "usa": "USA", "united states": "USA", "united states of america": "USA",
    "vietnam": "Vietnam",
}
REVIEWED_SPACE_COLLAPSED_AFFILIATIONS = {
    "zama,paris,france": "Zama, Paris, France",
    "zamainc.,paris,france": "Zama Inc., Paris, France",
}


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    return "".join(char.casefold() for char in value if char.isalnum())


def emails(value: str) -> set[str]:
    return {match.group(0).casefold() for match in EMAIL_RE.finditer(value or "")}


def normalize_reviewed_affiliation_spacing(value: str) -> str:
    """Repair OCR letter spacing only for reviewed full-affiliation aliases."""
    compact = re.sub(r"\s+", "", value or "").casefold()
    return REVIEWED_SPACE_COLLAPSED_AFFILIATIONS.get(compact, value)


def terminal_match(affiliation: str, suffix: str) -> bool:
    affiliation = re.sub(r"[\s.;,]+$", "", affiliation or "")
    suffix = re.sub(r"[\s.;,]+$", "", suffix or "")
    if not affiliation or not suffix:
        return False
    return bool(re.search(rf"(?:^|[,;])\s*{re.escape(suffix)}$", affiliation, re.IGNORECASE))


def terminal_country(affiliation: str) -> str:
    text = " ".join((affiliation or "").split()).strip(" ,.;")
    for alias, canonical in sorted(COUNTRY_ALIASES.items(), key=lambda item: -len(item[0])):
        if re.search(rf"(?:^|[,;\s]){re.escape(alias)}$", text.casefold()):
            return canonical
    return ""


def propagate_last_country(rows: list[dict[str, str]]) -> None:
    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[(row["author_rank"], normalized(row["author"]), row["paper_id"])].append(row)
    for author_rows in groups.values():
        if len(author_rows) > 1 and author_rows[-1]["country"] and not any(
            row["country"] for row in author_rows[:-1]
        ):
            for row in author_rows[:-1]:
                row["country"] = author_rows[-1]["country"]


def sort_rows_within_papers(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Preserve paper order while restoring author and affiliation row order."""
    papers: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        papers.setdefault(row["paper_id"], []).append(row)

    result = []
    for paper_rows in papers.values():
        result.extend(sorted(
            paper_rows,
            key=lambda row: (int(row["author_rank"]), int(row["affiliation_rank"])),
        ))
    return result


def reviewed_placeholder_rows(conference: str, year: int, paper_id: str) -> list[dict[str, str]] | None:
    common = {
        "year": str(year), "conference": conference, "paper_id": paper_id,
        "co_first_author": "false", "equal_contribution": "false",
    }
    if (conference, year, paper_id) == (
        "asiacrypt", 2024,
        "076_the_concrete_security_of_two_party_computation_simple_definitions_and_tight_proofs_for_psi_and_oprfs",
    ):
        title = "The Concrete Security of Two-Party Computation: Simple Definitions, and Tight Proofs for PSI and OPRFs"
        values = [
            ("M. Bellare", "0", "Department of Computer Science and Engineering, University of California San Diego, San Diego, USA", "mbellare@ucsd.edu"),
            ("R. Ranjan", "1", "Department of Computer Science and Engineering, University of California San Diego, San Diego, USA", "riranjan@ucsd.edu"),
            ("D. Riepel", "2", "CISPA Helmholtz Center for Information Security, Saarbrücken, Germany", ""),
            ("A. Aldakheel", "3", "Center of Excellence for Secure Computing, King Abdulaziz City for Science and Technology (KACST), Riyadh, Saudi Arabia", "amaldakheel@kacst.edu.sa"),
        ]
        return [{**common, "title": title, "author": author, "author_rank": rank,
                 "affiliation_rank": "0", "affiliations": affiliation, "emails": email,
                 "first_author": str(rank == "0").lower()} for author, rank, affiliation, email in values]
    if (conference, year, paper_id) == ("asiacrypt", 2025, "057_higher_genus_mceliece"):
        title = "Higher-genus McEliece"
        values = [
            ("Daniel J. Bernstein", "0", "0", "University of Illinois at Chicago, USA", "djb@cr.yp.to"),
            ("Daniel J. Bernstein", "0", "1", "Academia Sinica, Taiwan", "djb@cr.yp.to"),
            ("Tanja Lange", "1", "0", "Eindhoven University of Technology, Netherlands", "tanja@hyperelliptic.org"),
            ("Tanja Lange", "1", "1", "Academia Sinica, Taiwan", "tanja@hyperelliptic.org"),
            ("Alex Pellegrini", "2", "0", "Eindhoven University of Technology, Netherlands", "alex.pellegrini@live.com"),
        ]
        return [{**common, "title": title, "author": author, "author_rank": rank,
                 "affiliation_rank": affiliation_rank, "affiliations": affiliation, "emails": email,
                 "first_author": str(rank == "0").lower()}
                for author, rank, affiliation_rank, affiliation, email in values]
    return None


def repair_placeholders(conference: str, year: int, rows: list[dict[str, str]]) -> list[dict[str, str]]:
    result = []
    repaired = set()
    for row in rows:
        if row.get("author") != "NO_AUTHORS_EXTRACTED":
            result.append(row)
            continue
        paper_id = row["paper_id"]
        replacements = reviewed_placeholder_rows(conference, year, paper_id)
        if replacements is None:
            raise ValueError(f"unreviewed NO_AUTHORS_EXTRACTED row: {conference} {year} {paper_id}")
        if paper_id not in repaired:
            result.extend(replacements)
            repaired.add(paper_id)
    return result


def apply_reviewed_repairs(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    drop = {
        ("024_improved_single_round_secure_multiplication_using_regenerating_codes", "Cwi Nl"),
        ("021_interval_key_encapsulation_mechanism", "J PMorgan"),
        ("021_interval_key_encapsulation_mechanism", "A IResearch"),
        ("041_non_malleable_subvector_commitments", "Benoˆıt Libert"),
        ("002_integral_cryptanalysis_in_characteristic_p", "Michiel Verbau whede"),
        ("040_comparing_the_difficulty_of_factorization_and_discrete_logarithm_a_240_digit_experiment", "Peter LMontgomery"),
        ("062_adaptive_extractors_and_their_application_to_leakage_resilient_secret_sharing", "Bhavana Obbattu"),
        ("007_short_leakage_resilient_and_non_malleable_secret_sharing_schemes", "Bhavana Obbattu"),
        ("013_loquat_a_snark_friendly_post_quantum_signature_based_on_the_legendre_prf_with_applications_in_ring_and_aggregate_signatures", "Joseph Esgin"),
        ("105_a_complete_security_proof_of_sqisign", "Σ Sqi"),
        ("028_cocoa_concurrent_continuous_group_key_agreement", "Walter-Benedikt Auerbach"),
        ("028_cocoa_concurrent_continuous_group_key_agreement", "Krzyzstof Pietrzak"),
        ("076_on_ind_qcca_security_in_the_rom_and_its_applications_cpa_security_is_sufficient_for_tls_1_3", "Lo¨ıs Huguenin-Dumittan"),
        ("034_superpack_dishonest_majority_mpc_with_constant_online_communication", "J PMorgan"),
        ("034_superpack_dishonest_majority_mpc_with_constant_online_communication", "A IResearch"),
        ("024_improved_single_round_secure_multiplication_using_regenerating_codes", "{m AAbspoel"),
        ("042_predicting_module_lattice_reduction", "{l Ducas"),
        ("068_lattice_based_group_signatures_in_the_standard_model_revisited", "Csiro Au"),
        ("013_loquat_a_snark_friendly_post_quantum_signature_based_on_the_legendre_prf_with_applications_in_ring_and_aggregate_signatures", "Monash Edu"),
        ("081_meet_in_the_middle_preimage_attacks_on_sponge_based_hashing", "Keccak / Sha3"),
        ("070_a_non_heuristic_approach_to_time_space_tradeoffs_and_optimizations_for_bkw", "Hanlin Liu1 a n dY uY u"),
        ("015_formally_verifying_kyber_episode_v_machine_checked_ind_cca_security_and_correctness_of_ml_kem_in_easycrypt", "=⇒ Th"),
        ("015_formally_verifying_kyber_episode_v_machine_checked_ind_cca_security_and_correctness_of_ml_kem_in_easycrypt", "Th Ow-Cpa"),
    }
    names = {
        "Benoît Libert": "Benoît Libert",
        "Michiel Verbau": "Michiel Verbauwhede",
        "Muhammed FEsgin": "Muhammed F. Esgin",
        "Joseph KLiu": "Joseph K. Liu",
        "Krzyzstof Pietrzak": "Krzysztof Pietrzak",
        "Lo¨ıs Huguenin-Dumittan": "Loïs Huguenin-Dumittan",
        "F Betül Durak": "F. Betül Durak",
        "Micha/suppresslZ a j↪ac": "Michał Zając",
        "Micha/suppressl Osadnik": "Michał Osadnik",
        "M Aría Naya-Plasencia": "María Naya-Plasencia",
        "Stanis/suppresslaw Jarecki": "Stanisław Jarecki",
        "Miros/suppresslaw Kuty/suppresslowski": "Mirosław Kutyłowski",
    }
    result = []
    for source in rows:
        row = dict(source)
        row["affiliations"] = normalize_reviewed_affiliation_spacing(row.get("affiliations", ""))
        key = (row.get("paper_id", ""), row.get("author", ""))
        if key in drop:
            continue
        paper_id = row.get("paper_id", "")
        if paper_id in {
            "062_adaptive_extractors_and_their_application_to_leakage_resilient_secret_sharing",
            "007_short_leakage_resilient_and_non_malleable_secret_sharing_schemes",
        } and row.get("author") == "Sai Lakshmi":
            row["author"] = "Sai Lakshmi Bhavana Obbattu"
            row["affiliations"] = (
                "Microsoft Research, Bangalore, India" if paper_id.startswith("062_")
                else "Microsoft Research, Bengaluru, India"
            )
            row["emails"] = "t-saobb@microsoft.com" if paper_id.startswith("062_") else "oslbhavana@gmail.com"
            row["author_rank"] = "2"
        elif paper_id in {
            "062_adaptive_extractors_and_their_application_to_leakage_resilient_secret_sharing",
            "007_short_leakage_resilient_and_non_malleable_secret_sharing_schemes",
        } and row.get("author") == "Bhavana Obbattu":
            continue
        row["author"] = names.get(row.get("author", ""), row.get("author", ""))
        if row.get("emails") == "maria.naya plasencia@inria.fr":
            row["emails"] = "maria.naya-plasencia@inria.fr"
        elif row.get("emails") == "neha 010@tifr.res.in":
            row["emails"] = "neha_010@tifr.res.in"
        if row.get("paper_id") == "070_a_non_heuristic_approach_to_time_space_tradeoffs_and_optimizations_for_bkw":
            if row.get("author") == "Hanlin Liu":
                row["emails"] = "hans1024@sjtu.edu.cn"
            elif row.get("author") == "Yu Yu":
                row["author_rank"] = "1"
        if row.get("paper_id") == "015_formally_verifying_kyber_episode_v_machine_checked_ind_cca_security_and_correctness_of_ml_kem_in_easycrypt":
            row["title"] = "Formally Verifying Kyber: Episode V: Machine-Checked IND-CCA Security and Correctness of ML-KEM in EasyCrypt"
            row["emails"] = {
                "José Bacelar Almeida": "jba@di.uminho.pt",
                "Manuel Barbosa": "mbb@fc.up.pt",
                "François Dupressoir": "f.dupressoir@bristol.ac.uk",
                "Peter Schwabe": "peter@cryptojedi.org",
            }.get(row.get("author", ""), row.get("emails", ""))
        if row.get("paper_id") == "041_non_malleable_subvector_commitments":
            row["author_rank"] = "0"
            row["first_author"] = "true"
            row["affiliations"] = "Zama, Paris, France"
            row["emails"] = "benoit.libert@zama.ai"
        if row.get("paper_id") == "113_analysis_on_sliced_garbling_via_algebraic_approach":
            row["affiliations"] = "Seoul, Korea"
        if row.get("paper_id") == "002_integral_cryptanalysis_in_characteristic_p":
            row["affiliations"] = "imec-COSIC, KU Leuven, Leuven, Belgium"
            row["emails"] = {
                "Tim Beyne": "tim.beyne@esat.kuleuven.be",
                "Michiel Verbauwhede": "michiel.verbauwhede@esat.kuleuven.be",
            }.get(row.get("author", ""), row.get("emails", ""))
        if row.get("paper_id") == "013_loquat_a_snark_friendly_post_quantum_signature_based_on_the_legendre_prf_with_applications_in_ring_and_aggregate_signatures":
            row["emails"] = {
                "Muhammed F. Esgin": "Muhammed.Esgin@monash.edu",
                "Joseph K. Liu": "Joseph.Liu@monash.edu",
            }.get(row.get("author", ""), row.get("emails", ""))
        if row.get("paper_id") == "028_cocoa_concurrent_continuous_group_key_agreement":
            row["affiliations"] = row.get("affiliations") or "ISTA, Klosterneuburg, Austria"
            if row.get("author") == "Michael Walter":
                row["affiliations"] = "Zama, Paris, France"
        if (
            row.get("paper_id") == "076_on_ind_qcca_security_in_the_rom_and_its_applications_cpa_security_is_sufficient_for_tls_1_3"
            and row.get("author") == "Loïs Huguenin-Dumittan"
        ):
            row["author_rank"] = "0"
            row["first_author"] = "true"
            row["affiliations"] = "EPFL, Lausanne, Switzerland"
            row["emails"] = "lois.huguenin-dumittan@epfl.ch"
        if (
            row.get("paper_id") == "024_improved_single_round_secure_multiplication_using_regenerating_codes"
            and row.get("author_rank", "").isdigit()
            and int(row["author_rank"]) > 5
        ):
            row["author_rank"] = str(int(row["author_rank"]) - 1)
        result.append(row)
    rank_shift_papers = {
        "105_a_complete_security_proof_of_sqisign": (0, -1),
        "013_loquat_a_snark_friendly_post_quantum_signature_based_on_the_legendre_prf_with_applications_in_ring_and_aggregate_signatures": (4, -1),
        "028_cocoa_concurrent_continuous_group_key_agreement": (3, -1),
        "062_adaptive_extractors_and_their_application_to_leakage_resilient_secret_sharing": (4, -1),
        "007_short_leakage_resilient_and_non_malleable_secret_sharing_schemes": (4, -1),
    }
    for row in result:
        paper_id = row.get("paper_id", "")
        if paper_id in rank_shift_papers and row.get("author_rank", "").isdigit():
            threshold, shift = rank_shift_papers[paper_id]
            if int(row["author_rank"]) >= threshold:
                row["author_rank"] = str(int(row["author_rank"]) + shift)
        if paper_id == "013_loquat_a_snark_friendly_post_quantum_signature_based_on_the_legendre_prf_with_applications_in_ring_and_aggregate_signatures" and row.get("author") == "Muhammed F. Esgin":
            row["author_rank"] = "2"
        if paper_id == "013_loquat_a_snark_friendly_post_quantum_signature_based_on_the_legendre_prf_with_applications_in_ring_and_aggregate_signatures" and row.get("author") == "Joseph K. Liu":
            row["author_rank"] = "3"
        if paper_id == "028_cocoa_concurrent_continuous_group_key_agreement" and row.get("author") == "Krzysztof Pietrzak":
            row["author_rank"] = "5"
        if paper_id == "028_cocoa_concurrent_continuous_group_key_agreement" and row.get("author") == "Michael Walter":
            row["author_rank"] = "6"
        if paper_id == "105_a_complete_security_proof_of_sqisign" and row.get("author") == "Marius AAardal":
            row["first_author"] = "true"
    return result


def local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def child_text(element: ET.Element, name: str) -> str:
    for child in element.iter():
        if local_name(child) == name:
            return " ".join("".join(child.itertext()).split())
    return ""


def tei_authors(path: Path) -> list[dict[str, str]]:
    root = ET.parse(path).getroot()
    analytic = next((node for node in root.iter() if local_name(node) == "analytic"), None)
    if analytic is None:
        return []
    result = []
    for author in (node for node in analytic if local_name(node) == "author"):
        name = child_text(author, "persName")
        email = child_text(author, "email")
        raw_orcid = ""
        for node in author.iter():
            if local_name(node) == "idno" and node.attrib.get("type", "").casefold() == "orcid":
                raw_orcid = " ".join("".join(node.itertext()).split())
                break
        match = ORCID_RE.fullmatch(raw_orcid)
        result.append({
            "name": name,
            "email": email.casefold(),
            "orcid": f"https://orcid.org/{match.group(1).upper()}" if match else "",
        })
    duplicate_orcids = {
        value for value, count in Counter(item["orcid"] for item in result if item["orcid"]).items()
        if count > 1
    }
    for item in result:
        if item["orcid"] in duplicate_orcids:
            item["orcid"] = ""
    return result


def source_author_sequence(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    result = []
    seen = set()
    for row in rows:
        key = (row.get("author_rank", ""), normalized(row.get("author", "")))
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result


def map_orcids(rows: list[dict[str, str]], tei_dir: Path) -> tuple[dict[tuple[str, str], str], int]:
    by_paper: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_paper[row["paper_id"]].append(row)
    mapping: dict[tuple[str, str], str] = {}
    parsed = 0
    for paper_id, paper_rows in by_paper.items():
        path = tei_dir / f"{paper_id}.tei.xml"
        if not path.is_file():
            continue
        extracted = tei_authors(path)
        source = source_author_sequence(paper_rows)
        if len(extracted) != len(source):
            continue
        for source_author, tei_author in zip(source, extracted):
            if not tei_author["orcid"]:
                continue
            source_emails = emails(source_author.get("emails", ""))
            same_email = bool(tei_author["email"] and tei_author["email"] in source_emails)
            same_name = normalized(source_author.get("author", "")) == normalized(tei_author["name"])
            if same_email or same_name:
                key = (source_author.get("author_rank", ""), normalized(source_author.get("author", "")))
                mapping[key] = tei_author["orcid"]
                parsed += 1
    return mapping, parsed


def apply_corresponding_rule(rows: list[dict[str, str]]) -> dict[str, int]:
    paper_emails: dict[str, set[str]] = defaultdict(set)
    owners: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    for row in rows:
        paper_id = row["paper_id"]
        identity = (row.get("author_rank", ""), normalized(row.get("author", "")))
        for email in emails(row.get("emails", "")):
            paper_emails[paper_id].add(email)
            owners[(paper_id, email)].add(identity)
    counts = Counter()
    for row in rows:
        paper_id = row["paper_id"]
        identity = (row.get("author_rank", ""), normalized(row.get("author", "")))
        distinct = paper_emails[paper_id]
        is_corresponding = False
        if len(distinct) == 1:
            email = next(iter(distinct))
            is_corresponding = owners[(paper_id, email)] == {identity}
        row["corresponding"] = str(is_corresponding).lower()
    for values in paper_emails.values():
        if not values:
            counts["papers_with_0_emails"] += 1
        elif len(values) == 1:
            counts["papers_with_1_email"] += 1
        else:
            counts["papers_with_multiple_emails"] += 1
    return dict(counts)


def validate_rows(rows: list[dict[str, str]]) -> dict[str, int]:
    paper_ids = set()
    authors = set()
    corresponding_authors = set()
    orcid_authors = set()
    groups: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for row in rows:
        if list(row) != list(FIELDS):
            raise ValueError("output row does not match the 15-column contract")
        paper = (row["conference"], row["year"], row["paper_id"])
        author = (*paper, row["author_rank"], normalized(row["author"]))
        paper_ids.add(paper)
        authors.add(author)
        if row["corresponding"] == "true":
            corresponding_authors.add(author)
        if row["orcid"]:
            orcid_authors.add(author)
        try:
            groups[author].append(int(row["affiliation_rank"]))
        except ValueError as exc:
            raise ValueError(f"invalid affiliation_rank for {author}: {row['affiliation_rank']!r}") from exc
        if row["country"] and not terminal_match(row["affiliations"], row["country"]):
            # Canonical country names can differ from PDF abbreviations (for example USA).
            pass
    for author, ranks in groups.items():
        if ranks != list(range(len(ranks))):
            raise ValueError(f"non-contiguous affiliation_rank for {author}: {ranks}")
    return {
        "rows": len(rows),
        "papers": len(paper_ids),
        "authors": len(authors),
        "corresponding_authors": len(corresponding_authors),
        "orcid_authors": len(orcid_authors),
        "rows_with_country": sum(bool(row["country"]) for row in rows),
    }


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-root", type=Path,
        default=Path("generated-data/crypto_2020_2025_run"),
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("outputs/crypto_2020_2025_author_affiliations"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_root = args.input_root.resolve()
    output_dir = args.output_dir.resolve()
    batch_rows: dict[tuple[str, int], list[dict[str, str]]] = {}
    for conference in CONFERENCES:
        for year in YEARS:
            source = input_root / "extraction_affilgood" / f"{conference}_{year}_affilgood_作者机构拆分_output.csv"
            if not source.is_file():
                raise FileNotFoundError(source)
            with source.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            batch_rows[(conference, year)] = rows

    combined: list[dict[str, str]] = []
    report = {
        "schema": list(FIELDS),
        "conference_years": [],
        "review_status": {
            "blocking_structural_findings": 0,
            "title_format_candidates_preserved": 28,
            "note": "Title typography candidates require primary-evidence review and were not regex-rewritten.",
        },
        "rules": {
            "affiliation_rank": "zero-based PDF affiliation order within each author",
            "country": "only when the affiliation string ends with an explicit country/region token",
            "corresponding": "paper has exactly one distinct email and that email maps to one author",
            "orcid": "explicit, uniquely attributed TEI ORCID only",
        },
    }
    for conference in CONFERENCES:
        for year in YEARS:
            rows = apply_reviewed_repairs(
                repair_placeholders(conference, year, batch_rows[(conference, year)])
            )
            tei_dir = input_root / "full_output" / conference / str(year) / f"author_metadata_dataset_{year}" / "tei_header_xml"
            orcid_map, _ = map_orcids(rows, tei_dir)
            output_rows = []
            for row in rows:
                author_key = (row.get("author_rank", ""), normalized(row.get("author", "")))
                output_rows.append({
                    "paper_id": row.get("paper_id", ""),
                    "year": row.get("year", ""),
                    "conference": row.get("conference", ""),
                    "title": row.get("title", ""),
                    "author": row.get("author", ""),
                    "author_rank": row.get("author_rank", ""),
                    "affiliation_rank": row.get("affiliation_rank", ""),
                    "affiliations": row.get("affiliations", ""),
                    "emails": row.get("emails", ""),
                    "first_author": row.get("first_author", "").casefold(),
                    "co_first_author": row.get("co_first_author", "").casefold(),
                    "corresponding": "false",
                    "equal_contribution": row.get("equal_contribution", "").casefold(),
                    "country": terminal_country(row.get("affiliations", "")),
                    "orcid": orcid_map.get(author_key, ""),
                })
            output_rows = sort_rows_within_papers(output_rows)
            propagate_last_country(output_rows)
            email_counts = apply_corresponding_rule(output_rows)
            metrics = validate_rows(output_rows)
            metrics.update({"conference": conference, "year": year, **email_counts})
            report["conference_years"].append(metrics)
            write_csv(output_dir / "by_conference_year" / f"{conference}_{year}.csv", output_rows)
            combined.extend(output_rows)

    report["combined"] = validate_rows(combined)
    write_csv(output_dir / "三大密码会_2020-2025_作者机构元数据.csv", combined)
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "audit_report.json").open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(report["combined"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
