import importlib.util
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "country_statistics.py"
SPEC = importlib.util.spec_from_file_location("country_statistics", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def fact(paper, author, order, country, institution="", identity=""):
    return {
        "paper_key": paper,
        "conference": "venue-alpha",
        "year": "2025",
        "title": f"Study {paper}",
        "author_key": author,
        "name": author,
        "author_order": order,
        "institution_key": identity,
        "institution_id": identity,
        "canonical_institution_name": institution,
        "inst": institution,
        "country": country,
    }


def test_unknown_country_rows_remain_in_share_denominators():
    rows = [
        fact("paper-alpha", "author-alpha", "0", "Country Alpha", "Institute Alpha", "INST1"),
        fact("paper-beta", "author-beta", "0", ""),
    ]

    summary, _, _ = MODULE.aggregate_country(rows)

    by_country = {row["country"]: row for row in summary}
    assert by_country["Country Alpha"]["paper_share"] == 0.5
    assert by_country["Unknown"]["papers"] == 1
    assert by_country["Unknown"]["paper_share"] == 0.5
    assert by_country["Unknown"]["author_share"] == 0.5


def test_partially_resolved_aligned_country_keeps_unresolved_component():
    rows = [
        fact("paper-alpha", "author-alpha", "0", "Country Alpha", "Institute Alpha", "INST1"),
        fact(
            "paper-alpha",
            "author-alpha",
            "0",
            "Country Alpha | Unresolved Region",
            "Institute Alpha | Institute Beta",
            "INST1 | INST2",
        ),
    ]

    summary, _, _ = MODULE.aggregate_country(rows)

    by_country = {row["country"]: row for row in summary}
    assert set(by_country) == {"Country Alpha", "Unknown"}
    assert by_country["Country Alpha"]["papers"] == 1
    assert by_country["Unknown"]["papers"] == 1
    assert by_country["Country Alpha"]["author_share"] == 0.5
    assert by_country["Unknown"]["author_share"] == 0.5
