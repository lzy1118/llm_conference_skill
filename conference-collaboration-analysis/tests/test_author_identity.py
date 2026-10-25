import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "collaboration_analysis.py"
SPEC = importlib.util.spec_from_file_location("collaboration_analysis", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def fact(paper, key, name, order, title="Shared title"):
    return {
        "paper_key": paper,
        "conference": "venue-alpha",
        "year": "2025",
        "title": title,
        "author_key": key,
        "name": name,
        "author_order": order,
        "institution_key": "INST1",
        "institution_id": "INST1",
        "inst": "Institute Alpha",
        "country": "Country Alpha",
    }


def test_same_display_names_with_distinct_explicit_keys_stay_distinct():
    rows = [
        fact("paper-a", "author-1", "Same Name", "00"),
        fact("paper-a", "author-1", "Same Name", "0"),
        fact("paper-a", "author-2", "Coauthor", "1"),
        fact("paper-b", "author-1", "Same Name", "0"),
        fact("paper-b", "author-2", "Coauthor", "1"),
        fact("paper-c", "author-3", "Same Name", "0"),
        fact("paper-c", "author-2", "Coauthor", "1"),
    ]

    edges, summary = MODULE.aggregate_edges(rows, "author")

    assert summary[0]["paper_count"] == 2
    assert len(edges) == 2
    by_pair = {(row["left_key"], row["right_key"]): row["shared_papers"] for row in edges}
    assert by_pair[("author-1", "author-2")] == 1
    assert by_pair[("author-2", "author-3")] == 1


def test_unresolved_composite_country_is_preserved_as_unknown():
    rows = [
        fact("paper-a", "author-1", "Author One", "0"),
        fact("paper-a", "author-2", "Author Two", "1"),
        fact("paper-a", "author-3", "Author Three", "2"),
    ]
    rows[0].update({
        "country": "United States | Unmapped Region",
        "inst": "Institute US | Institute Unknown",
        "institution_id": "INST1 | INST2",
        "institution_key": "INST1 | INST2",
    })
    rows[1]["country"] = "United States"
    rows[1]["inst"] = "Institute US"
    rows[1]["institution_id"] = "INST1"
    rows[1]["institution_key"] = "INST1"
    rows[2]["country"] = "France"
    rows[2]["inst"] = "Institute France"
    rows[2]["institution_id"] = "INST3"
    rows[2]["institution_key"] = "INST3"

    edges, _summary = MODULE.aggregate_edges(rows, "country")

    country_pairs = {(row["left_key"], row["right_key"]) for row in edges}
    assert ("France", "United States") in country_pairs
    assert ("France", "Unknown") in country_pairs
    assert ("United States", "Unknown") in country_pairs


def test_fallback_name_resolves_only_to_a_unique_same_paper_key():
    rows = [
        fact("paper-a", "author-1", "Same Name", "0"),
        fact("paper-a", "", "Same Name", "0"),
        fact("paper-b", "author-2", "Same Name", "0"),
        fact("paper-b", "author-3", "Same Name", "1"),
        fact("paper-b", "", "Same Name", "2"),
    ]

    assert MODULE.resolve_author_keys_by_row(rows) == [
        "author-1",
        "author-1",
        "author-2",
        "author-3",
        "Same Name",
    ]


def test_fallback_name_is_not_aliased_to_an_explicit_key_from_another_paper():
    rows = [
        fact("paper-a", "author-1", "Same Name", "0"),
        fact("paper-a", "coauthor", "Coauthor", "1"),
        fact("paper-b", "", "Same Name", "0"),
        fact("paper-b", "coauthor", "Coauthor", "1"),
    ]

    edges, _summary = MODULE.aggregate_edges(rows, "author")

    assert MODULE.resolve_author_keys_by_row(rows) == [
        "author-1",
        "coauthor",
        "Same Name",
        "coauthor",
    ]
    assert {(edge["left_key"], edge["right_key"]) for edge in edges} == {
        ("author-1", "coauthor"),
        ("Same Name", "coauthor"),
    }


def test_missing_titles_do_not_merge_distinct_papers():
    rows = [
        fact("paper-a", "author-1", "Author One", "0", title=""),
        fact("paper-b", "author-1", "Author One", "0", title="---"),
    ]

    assert MODULE.build_canonical_paper_keys(rows) == {
        "paper-a": "paper-a",
        "paper-b": "paper-b",
    }


def test_non_latin_paper_signatures_do_not_collapse():
    rows = [
        fact("paper-a", "author-1", "张伟", "0", title="安全数据系统"),
        fact("paper-b", "author-1", "张伟", "0", title="隐私保护系统"),
    ]

    assert MODULE.normalize_author_identity("张伟")
    assert MODULE.normalize_title_key("安全数据系统") != MODULE.normalize_title_key("隐私保护系统")
    assert MODULE.build_canonical_paper_keys(rows) == {
        "paper-a": "paper-a",
        "paper-b": "paper-b",
    }
