import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "query_author_details.py"
SPEC = importlib.util.spec_from_file_location("query_author_details", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fact(paper, name, author_key, order, affiliation):
    return {
        "paper_key": paper,
        "conference": "venue-alpha",
        "year": "period-alpha",
        "title": f"Study {paper}",
        "author_key": author_key,
        "name": name,
        "author_order": order,
        "institution_key": affiliation,
    }


def test_queries_papers_collaborators_and_first_author_papers():
    rows = [
        fact("paper-alpha", "Researcher Alpha", "author-alpha", "0", "institution-alpha"),
        fact("paper-alpha", "Researcher Alpha", "author-alpha", "0", "institution-beta"),
        fact("paper-alpha", "Researcher Beta", "author-beta", "1", "institution-gamma"),
        fact("paper-beta", "Researcher Beta", "author-beta", "0", "institution-gamma"),
        fact("paper-beta", "Researcher Alpha", "author-alpha", "1", "institution-alpha"),
        fact("paper-beta", "Researcher Gamma", "author-gamma", "2", "institution-delta"),
    ]

    papers, collaborators, first_papers, summary = MODULE.query_author(rows, author=" researcher alpha ")

    assert [row["paper_key"] for row in papers] == ["paper-alpha", "paper-beta"]
    assert [row["paper_key"] for row in first_papers] == ["paper-alpha"]
    assert {row["author"]: row["shared_papers"] for row in collaborators} == {
        "Researcher Beta": 2,
        "Researcher Gamma": 1,
    }
    assert summary["matched_fact_rows"] == 3
    assert summary["identity_ambiguous"] is False


def test_reports_display_name_identity_ambiguity():
    rows = [
        fact("paper-alpha", "Researcher Alpha", "author-alpha", "0", "institution-alpha"),
        fact("paper-beta", "Researcher Alpha", "author-beta", "0", "institution-beta"),
    ]

    _, _, _, summary = MODULE.query_author(rows, author="Researcher Alpha")

    assert summary["matched_author_keys"] == ["author-alpha", "author-beta"]
    assert summary["identity_ambiguous"] is True


def test_applies_scope_filters_before_querying():
    included = fact("paper-alpha", "Researcher Alpha", "author-alpha", "00", "institution-alpha")
    excluded = fact("paper-beta", "Researcher Alpha", "author-alpha", "0", "institution-beta")
    excluded["conference"] = "venue-beta"
    excluded["year"] = "period-beta"

    papers, _, first_papers, summary = MODULE.query_author(
        [included, excluded],
        author_key="author-alpha",
        conference="venue-alpha",
        year="period-alpha",
    )

    assert [row["paper_key"] for row in papers] == ["paper-alpha"]
    assert [row["paper_key"] for row in first_papers] == ["paper-alpha"]
    assert summary["scoped_fact_rows"] == 1
