import importlib.util
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "institution_statistics.py"
SPEC = importlib.util.spec_from_file_location("institution_statistics", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def fact(paper, author, order, country, institution, identity, source=""):
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
        "institution_source": source,
    }


def test_paper_share_uses_all_scoped_papers_even_when_not_rankable():
    rows = [
        fact("paper-alpha", "author-alpha", "0", "Country Alpha", "Institute Alpha", "INST1"),
        fact(
            "paper-beta",
            "author-beta",
            "0",
            "",
            "Independent Researcher",
            "NONINSTITUTIONAL",
            "independent_researcher_default",
        ),
    ]

    summary, _, _ = MODULE.aggregate_institutions(rows)

    assert len(summary) == 1
    assert summary[0]["institution_name"] == "Institute Alpha"
    assert summary[0]["paper_share"] == 0.5


def test_institution_summary_surfaces_conflicting_country_mappings():
    identity = "https://ror.org/abc123"
    rows = [
        fact("paper-alpha", "author-alpha", "0", "United States", "Institute Alpha", identity),
        fact("paper-beta", "author-beta", "0", "United Kingdom", "Institute Alpha", identity),
    ]

    summary, _, _ = MODULE.aggregate_institutions(rows)

    assert len(summary) == 1
    assert summary[0]["country"] == "United Kingdom | United States"


def test_author_and_first_author_counts_normalize_order_and_deduplicate_rows():
    identity = "https://ror.org/abc123"
    rows = [
        fact("paper-alpha", "author-alpha", "0", "Country Alpha", "Institute Alpha", identity),
        fact("paper-alpha", "author-alpha", "00", "Country Alpha", "Institute Alpha", identity),
    ]

    summary, _, _ = MODULE.aggregate_institutions(rows)

    assert summary[0]["authors"] == 1
    assert summary[0]["first_author_papers"] == 1
