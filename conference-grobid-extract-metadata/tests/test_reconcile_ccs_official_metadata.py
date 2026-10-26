from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import reconcile_ccs_official_metadata as reconcile


def test_rebuild_metadata_uses_official_name_order_and_affiliations():
    metadata = {
        "title": "Example",
        "year": "2021",
        "authors": [
            {
                "order": 0,
                "name": "Second Author",
                "email": "second@example.org",
                "affiliations": ["Wrong Shared Institution"],
                "first_author": True,
                "co_first_author": False,
                "equal_contribution": False,
                "corresponding": True,
            },
            {
                "order": 1,
                "name": "First Author",
                "email": "first@example.org",
                "affiliations": [],
                "first_author": False,
                "co_first_author": False,
                "equal_contribution": False,
                "corresponding": False,
            },
        ],
        "_extraction": {
            "evidence": [],
            "candidates": {},
            "decisions": [],
            "review_reasons": [
                {"code": "layout_affiliation_conflict", "field": "affiliations"},
                {"code": "abstract_source_conflict", "field": "abstract"},
            ],
        },
    }
    entry = {
        "title": "Example",
        "source_repairs": [],
        "authors": ["First Author", "Second Author"],
        "official_affiliations": [
            {"name": "First Author", "affiliations": ["Institution A"]},
            {"name": "Second Author", "affiliations": ["Institution B"]},
        ],
    }

    rebuilt = reconcile.rebuild_metadata(metadata, entry, "normalized_title_exact")

    assert [author["name"] for author in rebuilt["authors"]] == ["First Author", "Second Author"]
    assert [author["affiliations"] for author in rebuilt["authors"]] == [["Institution A"], ["Institution B"]]
    assert rebuilt["authors"][0]["email"] == "first@example.org"
    assert rebuilt["authors"][1]["email"] == "second@example.org"
    assert rebuilt["authors"][1]["corresponding"] is True
    assert rebuilt["first_affiliation"] == "Institution A"
    assert rebuilt["author_affiliation_relations"][1]["source"] == reconcile.OFFICIAL_SOURCE
    assert rebuilt["_extraction"]["review_reasons"] == [
        {"code": "abstract_source_conflict", "field": "abstract"}
    ]


def test_official_rows_rejects_missing_affiliation():
    entry = {
        "title": "Incomplete",
        "authors": ["First Author"],
        "official_affiliations": [{"name": "First Author", "affiliations": []}],
    }

    try:
        reconcile.official_rows(entry)
    except ValueError as error:
        assert "invalid official author-affiliation row" in str(error)
    else:
        raise AssertionError("incomplete official rows must be rejected")


def test_grouped_legacy_role_is_assigned_only_to_first_contained_author():
    old_authors = [
        {
            "name": "NishanthChandran NishkaDasgupta DivyaGupta",
            "email": "nichandr@microsoft.com",
            "corresponding": True,
        }
    ]

    assignments = reconcile.assign_old_authors(
        ["Nishanth Chandran", "Nishka Dasgupta", "Divya Gupta"],
        old_authors,
    )

    assert assignments == [old_authors[0], None, None]
