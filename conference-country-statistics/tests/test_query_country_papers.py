import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "query_country_papers.py"
SPEC = importlib.util.spec_from_file_location("query_country_papers", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fact(paper, name, author_key, order, institution_key, institution, country):
    return {
        "paper_key": paper,
        "conference": "venue-alpha",
        "year": "period-alpha",
        "title": f"Study {paper}",
        "author_key": author_key,
        "name": name,
        "author_order": order,
        "institution_key": institution_key,
        "canonical_institution_name": institution,
        "inst": f"Raw {institution}",
        "country": country,
    }


def test_preserves_all_authors_but_limits_attribution_to_selected_region():
    rows = [
        fact("paper-alpha", "Researcher Alpha", "author-alpha", "0", "institution-alpha", "Institute Alpha", "Region Alpha"),
        fact("paper-alpha", "Researcher Alpha", "author-alpha", "0", "institution-beta", "Institute Beta", "Region Alpha"),
        fact("paper-alpha", "Researcher Beta", "author-beta", "1", "institution-gamma", "Institute Gamma", "Region Beta"),
        fact("paper-beta", "Researcher Gamma", "author-gamma", "0", "institution-delta", "Institute Delta", "Region Beta"),
    ]

    papers, authors, institutions, summary = MODULE.query_country(rows, country=" region alpha ")

    assert len(papers) == 1
    assert papers[0]["all_authors"] == "Researcher Alpha | Researcher Beta"
    assert [row["author"] for row in authors] == ["Researcher Alpha"]
    assert authors[0]["institutions"] == "Institute Alpha | Institute Beta"
    assert {row["institution"] for row in institutions} == {"Institute Alpha", "Institute Beta"}
    assert summary["input_fact_rows"] == 4
    assert summary["matched_fact_rows"] == 2
    assert summary["paper_count"] == 1


def test_deduplicates_institution_by_stable_key_and_prefers_canonical_name():
    raw_first = fact(
        "paper-alpha", "Researcher Alpha", "author-alpha", "0",
        "institution-alpha", "", "Region Alpha",
    )
    raw_first["inst"] = "Observed Institute Alpha"
    canonical_second = fact(
        "paper-alpha", "Researcher Beta", "author-beta", "1",
        "institution-alpha", "Institute Alpha", "Region Alpha",
    )
    rows = [raw_first, canonical_second]

    _, _, institutions, _ = MODULE.query_country(rows, country="Region Alpha")

    assert len(institutions) == 1
    assert institutions[0]["institution"] == "Institute Alpha"


def test_applies_scope_filters_before_country_matching():
    included = fact(
        "paper-alpha", "Researcher Alpha", "author-alpha", "0",
        "institution-alpha", "Institute Alpha", "Region Alpha",
    )
    excluded = fact(
        "paper-beta", "Researcher Beta", "author-beta", "0",
        "institution-beta", "Institute Beta", "Region Alpha",
    )
    excluded["conference"] = "venue-beta"
    excluded["year"] = "period-beta"

    papers, _, _, summary = MODULE.query_country(
        [included, excluded],
        country="Region Alpha",
        conference="venue-alpha",
        year="period-alpha",
    )

    assert [row["paper_key"] for row in papers] == ["paper-alpha"]
    assert summary["scoped_fact_rows"] == 1


def test_splits_aligned_country_and_institution_components_and_drops_fragment():
    singleton_alpha = fact(
        "paper-single-alpha", "Researcher Alpha", "author-alpha", "0",
        "institution-alpha", "Institute Alpha", "Region Alpha",
    )
    singleton_beta = fact(
        "paper-single-beta", "Researcher Beta", "author-beta", "0",
        "institution-beta", "Institute Beta", "Region Beta",
    )
    composite = fact(
        "paper-composite", "Researcher Gamma", "author-gamma", "0",
        "institution-alpha;fragment-id", "Institute Alpha;Unresolved Fragment",
        "Region Alpha | Unresolved Region",
    )
    composite["institution_id"] = "institution-alpha;fragment-id"

    papers, _, institutions, _ = MODULE.query_country(
        [singleton_alpha, singleton_beta, composite], country="Region Alpha"
    )

    assert {row["paper_key"] for row in papers} == {"paper-single-alpha", "paper-composite"}
    composite_institutions = [
        row["institution"] for row in institutions if row["paper_key"] == "paper-composite"
    ]
    assert composite_institutions == ["Institute Alpha"]
