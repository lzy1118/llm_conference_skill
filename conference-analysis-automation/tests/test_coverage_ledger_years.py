import csv
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import build_coverage_ledger as MODULE


def test_fractional_and_nonfinite_years_are_not_coverage_buckets(tmp_path):
    role_path = tmp_path / "paper_author_roles.csv"
    with role_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["conference", "year", "is_first_author", "is_participating_author"],
        )
        writer.writeheader()
        writer.writerows({
            "conference": "ndss",
            "year": invalid_year,
            "is_first_author": "true",
            "is_participating_author": "true",
        } for invalid_year in ("2025.5", "-0.5", "-1", "Infinity", "-Infinity", "NaN"))

    assert MODULE.load_author_role_status(tmp_path) == {}


def test_module_import_and_historical_coverage_registry_are_available(monkeypatch):
    monkeypatch.setattr(MODULE, "candidate_paths", lambda _key: MODULE.ArtifactSet())

    ledger, _, _ = MODULE.build_ledger({}, {}, {}, min_year=2025, max_year=2025)

    expected_keys = {
        f"{venue}_{year}"
        for venue, first_year, last_year in (
            ("asiacrypt", 2020, 2025),
            ("crypto", 2020, 2025),
            ("eurocrypt", 2020, 2025),
            ("usenix_security", 2020, 2026),
            ("ndss", 2020, 2026),
            ("ieee_sp", 2020, 2026),
            ("ccs", 2020, 2026),
        )
        for year in range(first_year, last_year + 1)
    }
    assert set(MODULE.CONFERENCES) == expected_keys
    assert len(MODULE.CONFERENCES) == 46
    assert len(ledger) == 7
    assert {row["conference_key"] for row in ledger} == {
        "asiacrypt_2025",
        "crypto_2025",
        "eurocrypt_2025",
        "usenix_security_2025",
        "ndss_2025",
        "ieee_sp_2025",
        "ccs_2025",
    }
    assert all(row["backend"] == "iacr_top3" for row in ledger if row["family"] == "crypto")
    assert all(row["backend"] == "security_real" for row in ledger if row["family"] == "security")


def test_iacr_paper_id_preserves_historical_field_precedence():
    assert MODULE.paper_id_for(3, {"paperId": "paper-a", "id": "legacy-id"}, "CRYPTO") == "paper-a"
    assert MODULE.paper_id_for(3, {"id": "legacy-id"}, "CRYPTO") == "legacy-id"
    assert MODULE.paper_id_for(3, {}, "CRYPTO") == "legacy_2"


def test_integral_decimal_year_is_accepted(tmp_path):
    role_path = tmp_path / "paper_author_roles.csv"
    with role_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["conference", "year", "is_first_author", "is_participating_author"],
        )
        writer.writeheader()
        writer.writerow({
            "conference": "ndss",
            "year": "2025.0",
            "is_first_author": "true",
            "is_participating_author": "true",
        })

    assert MODULE.load_author_role_status(tmp_path) == {("ndss", 2025): "first_author_only"}
