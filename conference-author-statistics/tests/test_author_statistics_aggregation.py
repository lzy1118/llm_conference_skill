import importlib.util
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "author_statistics.py"
SPEC = importlib.util.spec_from_file_location("author_statistics", SCRIPT)
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


def test_paper_signature_deduplicates_affiliation_rows_but_respects_author_keys():
    rows = [
        fact("paper-a", "author-1", "Same Name", "00"),
        fact("paper-a", "author-1", "Same Name", "0"),
        fact("paper-a", "", "Same Name", "0"),
        fact("paper-a", "author-2", "Coauthor", "1"),
        fact("paper-b", "author-1", "Same Name", "0"),
        fact("paper-b", "author-2", "Coauthor", "1"),
        fact("paper-c", "author-3", "Same Name", "0"),
    ]

    summary, _, first_authors, edges, _ = MODULE.aggregate_authors(rows)

    by_key = {row["author_key"]: row for row in summary}
    assert by_key["author-1"]["papers"] == 1
    assert by_key["author-2"]["papers"] == 1
    assert by_key["author-3"]["papers"] == 1
    assert len(first_authors) == 2
    assert len(edges) == 1
    assert edges[0]["shared_papers"] == 1


def test_fallback_name_stays_unresolved_when_same_paper_has_name_collision():
    rows = [
        fact("paper-a", "author-1", "Same Name", "0"),
        fact("paper-a", "author-2", "Same Name", "1"),
        fact("paper-a", "", "Same Name", "2"),
    ]

    resolved = MODULE.resolve_author_keys_by_row(rows)

    assert resolved == ["author-1", "author-2", "Same Name"]


def test_distinct_explicit_author_keys_are_not_merged_by_name_evidence():
    rows = [
        fact("paper-a", "author-initial", "J Wu", "0"),
        fact("paper-a", "coauthor", "Coauthor", "1"),
        fact("paper-b", "author-full", "John Wu", "0"),
        fact("paper-b", "coauthor", "Coauthor", "1"),
    ]

    assert MODULE.resolve_author_keys_by_row(rows) == [
        "author-initial",
        "coauthor",
        "author-full",
        "coauthor",
    ]


def test_fallback_name_does_not_globally_alias_to_explicit_key():
    rows = [
        fact("paper-a", "author-1", "Same Name", "0"),
        fact("paper-a", "coauthor", "Coauthor", "1"),
        fact("paper-b", "", "Same Name", "0"),
        fact("paper-b", "coauthor", "Coauthor", "1"),
    ]

    summary, _, _, edges, _ = MODULE.aggregate_authors(rows)

    papers_by_author = {row["author_key"]: row["papers"] for row in summary}
    assert papers_by_author == {"author-1": 1, "coauthor": 2, "Same Name": 1}
    assert len(edges) == 2


def test_non_latin_titles_and_author_names_have_distinct_identity_keys():
    assert MODULE.normalize_title_key("安全数据系统") != MODULE.normalize_title_key("隐私保护系统")
    assert MODULE.normalize_author_identity("张伟") != MODULE.normalize_author_identity("李雷")
    assert MODULE.normalize_title_key("安全数据系统")
    assert MODULE.normalize_author_identity("张伟")


def test_missing_titles_do_not_merge_distinct_papers():
    rows = [
        fact("paper-a", "author-1", "Author One", "0", title=""),
        fact("paper-b", "author-1", "Author One", "0", title="---"),
    ]

    assert MODULE.build_canonical_paper_keys(rows) == {
        "paper-a": "paper-a",
        "paper-b": "paper-b",
    }


def test_rows_without_author_identity_do_not_create_empty_author():
    rows = [fact("paper-a", "", "", "0")]

    summary, _, first_authors, edges, _ = MODULE.aggregate_authors(rows)

    assert summary == []
    assert first_authors == []
    assert edges == []
