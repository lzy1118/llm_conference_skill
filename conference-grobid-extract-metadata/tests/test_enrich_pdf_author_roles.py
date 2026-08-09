from enrich_pdf_author_roles import csv_author_names, enrich_metadata_roles, non_role_projection
from author_metadata.pdf_context import PdfContext


def make_context(lines):
    return PdfContext(
        first_page_text="\n".join(lines),
        first_page_lines=lines,
        page_lines={1: lines},
        title_lines=[],
        author_lines=[],
        affiliation_lines=[],
        email_lines=[],
        preabstract_lines=[],
        pypdf_page_lines={1: lines},
    )


def make_metadata():
    return {
        "title": "Example",
        "year": "2021",
        "abstract": "An abstract.",
        "authors": [
            {
                "order": 0,
                "name": "Alice Smith",
                "email": "alice@example.org",
                "affiliations": ["Example University"],
                "affiliation_source": "official",
                "first_author": True,
                "co_first_author": False,
                "corresponding": False,
                "equal_contribution": False,
            },
            {
                "order": 1,
                "name": "Bob Jones",
                "email": "bob@example.org",
                "affiliations": ["Example Institute"],
                "affiliation_source": "official",
                "first_author": False,
                "co_first_author": False,
                "corresponding": False,
                "equal_contribution": False,
            },
        ],
        "_extraction": {"evidence": [], "candidates": {}, "decisions": [], "review_reasons": []},
    }


def test_role_replay_preserves_non_role_metadata_and_adds_audit_trace():
    metadata = make_metadata()
    context = make_context([
        "Alice Smith∗",
        "Bob Jones∗†",
        "ABSTRACT",
        "∗Both authors contributed equally.",
        "†Corresponding author.",
    ])

    updated, selected = enrich_metadata_roles(metadata, context)

    assert non_role_projection(updated) == non_role_projection(metadata)
    assert [author["co_first_author"] for author in updated["authors"]] == [True, True]
    assert [author["corresponding"] for author in updated["authors"]] == [False, True]
    assert selected["confidence"] == "high"
    assert any(
        evidence.get("source") == "pdf_role_linking"
        for evidence in updated["_extraction"]["evidence"]
    )


def test_role_replay_replaces_stale_unsupported_roles():
    metadata = make_metadata()
    metadata["authors"][1]["corresponding"] = True

    updated, _selected = enrich_metadata_roles(
        metadata,
        make_context(["Alice Smith", "Bob Jones", "ABSTRACT"]),
    )

    assert [author["corresponding"] for author in updated["authors"]] == [False, False]


def test_csv_author_names_collapses_affiliation_rows_and_preserves_co_first_order():
    rows = [
        {"author": "Alice Smith", "author_rank": "0", "affiliation_rank": "0"},
        {"author": "Alice Smith", "author_rank": "0", "affiliation_rank": "1"},
        {"author": "Bob Jones", "author_rank": "0", "affiliation_rank": "0"},
        {"author": "Carol Lee", "author_rank": "1", "affiliation_rank": "0"},
    ]

    assert csv_author_names(rows) == ["Alice Smith", "Bob Jones", "Carol Lee"]
