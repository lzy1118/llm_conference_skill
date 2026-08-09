import apply_reviewed_metadata_corrections as reviewed
import finalize_ccs_metadata as finalize


def test_reviewed_correction_requires_exact_prior_state_and_rebuilds_relations():
    metadata = {
        "title": "Paper",
        "authors": [{"name": "Alice"}, {"name": "Wrong Place"}],
        "_extraction": {
            "evidence": [],
            "candidates": {"authors": {"selected": []}},
            "decisions": [],
            "review_reasons": [
                {"code": "author_count_changed"},
                {"code": "official_web_paper_unmatched"},
            ],
        },
    }
    correction = {
        "paper_id": "001_paper",
        "expected_title": "Paper",
        "expected_authors": ["Alice", "Wrong Place"],
        "source_file": "paper.pdf",
        "page": 1,
        "review_note": "Visually checked.",
        "resolved_review_codes": ["author_count_changed"],
        "authors": [
            {
                "name": "Alice",
                "email": "alice@example.org",
                "affiliations": ["University A"],
                "first_author": True,
                "co_first_author": False,
                "corresponding": False,
                "equal_contribution": False,
            },
            {
                "name": "Bob",
                "email": "bob@example.org",
                "affiliations": ["University B"],
                "first_author": False,
                "co_first_author": False,
                "corresponding": True,
                "equal_contribution": False,
            },
        ],
    }

    updated = reviewed.apply_correction(metadata, correction)

    assert [author["name"] for author in updated["authors"]] == ["Alice", "Bob"]
    assert updated["participating_affiliations"] == ["University A", "University B"]
    assert updated["corresponding_authors"] == ["Bob"]
    assert [reason["code"] for reason in updated["_extraction"]["review_reasons"]] == [
        "official_web_paper_unmatched"
    ]
    assert updated["_extraction"]["decisions"][-1]["action"] == "apply_reviewed_pdf_author_affiliations"


def test_empty_role_override_preserves_roles_from_pdf_replay():
    authors = [{
        "name": "Alice",
        "first_author": True,
        "co_first_author": True,
        "equal_contribution": True,
        "corresponding": True,
    }, {
        "name": "Bob",
        "first_author": True,
        "co_first_author": True,
        "equal_contribution": True,
        "corresponding": False,
    }]

    finalize.apply_role_override(authors, {})

    assert authors[0]["co_first_author"] is True
    assert authors[1]["equal_contribution"] is True
    assert authors[0]["corresponding"] is True
