from author_metadata.artifacts import author_csv_row, author_csv_rows, new_metrics, update_metrics
from author_metadata.author_order import get_export_author_rank
from author_metadata.affiliation_linking import (
    _parse_default_and_symbol_lines,
    apply_email_domain_affiliations,
    extract_author_emails,
)
from types import SimpleNamespace


def test_artifact_metrics_and_author_row_share_export_contract() -> None:
    metadata = {
        "year": "2025",
        "title": "Example",
        "abstract": "Abstract",
        "authors": [{
            "name": "Alice Smith",
            "order": 0,
            "email": "alice@example.org",
            "affiliations": ["Example University"],
            "first_author": True,
            "co_first_author": False,
            "corresponding": True,
            "equal_contribution": False,
        }],
        "_extraction": {
            "decisions": [{"action": "fill_from_pdf_layout"}],
            "review_reasons": [{"code": "review"}],
        },
    }
    metrics = new_metrics(1)

    update_metrics(metrics, metadata)

    assert metrics["papers_processed"] == 1
    assert metrics["authors_exported"] == 1
    assert metrics["abstracts_extracted"] == 1
    assert metrics["layout_affiliations_filled"] == 1
    assert metrics["papers_requiring_review"] == 1
    assert author_csv_row("paper-1", metadata, metadata["authors"][0], "ccs")["author_rank"] == 0


def test_export_rank_handles_noncontiguous_cofirst_authors() -> None:
    authors = [
        {"name": "Alice", "order": 0, "co_first_author": True},
        {"name": "Bob", "order": 1, "co_first_author": False},
        {"name": "Carol", "order": 2, "co_first_author": True},
        {"name": "Dave", "order": 3, "co_first_author": False},
    ]

    assert [get_export_author_rank(author, authors) for author in authors] == [0, 1, 0, 2]


def test_author_csv_rows_expand_affiliations_and_extract_trailing_country() -> None:
    metadata = {
        "year": "2025", "title": "Example",
        "authors": [{
            "name": "Alice Smith", "order": 0, "email": "a@example.org",
            "orcid": "0000-0001-2345-6789", "affiliations": [
                "Example University, Paris, France; Example Lab"
            ], "first_author": True, "co_first_author": False,
            "corresponding": False, "equal_contribution": False,
        }],
    }
    rows = author_csv_rows("p", metadata, metadata["authors"][0], "ccs")
    assert [row["affiliation_rank"] for row in rows] == [0, 1]
    assert [row["country"] for row in rows] == ["France", ""]
    assert rows[0]["orcid"] == "https://orcid.org/0000-0001-2345-6789"


def test_last_affiliation_country_propagates_to_preceding_affiliations() -> None:
    author = {
        "name": "Alice Smith", "order": 0, "email": "",
        "affiliations": ["Example Security Laboratory", "Example University, Paris, France"],
        "first_author": True, "co_first_author": False,
        "corresponding": False, "equal_contribution": False,
    }
    metadata = {"year": "2025", "title": "Example", "authors": [author]}

    rows = author_csv_rows("p", metadata, author, "ccs")

    assert [row["country"] for row in rows] == ["France", "France"]


def test_pdf_country_overrides_conflicting_dom_affiliation_country() -> None:
    author = {
        "name": "Alice Smith", "order": 0, "email": "",
        "affiliations": ["Official University, USA"],
        "pdf_countries": ["China"],
        "first_author": True, "co_first_author": False,
        "corresponding": False, "equal_contribution": False,
    }
    metadata = {"year": "2025", "title": "Example", "authors": [author]}

    rows = author_csv_rows("p", metadata, author, "ndss")

    assert [row["country"] for row in rows] == ["China"]


def test_dom_country_fills_when_pdf_country_is_blank() -> None:
    author = {
        "name": "Alice Smith", "order": 0, "email": "",
        "affiliations": ["Official University, USA"],
        "pdf_countries": [""],
        "first_author": True, "co_first_author": False,
        "corresponding": False, "equal_contribution": False,
    }
    metadata = {"year": "2025", "title": "Example", "authors": [author]}

    rows = author_csv_rows("p", metadata, author, "ndss")

    assert [row["country"] for row in rows] == ["USA"]


def test_single_pdf_country_propagates_across_dom_affiliations() -> None:
    author = {
        "name": "Alice Smith", "order": 0, "email": "",
        "affiliations": ["Official Laboratory", "Official University, USA"],
        "pdf_countries": ["China"],
        "first_author": True, "co_first_author": False,
        "corresponding": False, "equal_contribution": False,
    }
    metadata = {"year": "2025", "title": "Example", "authors": [author]}

    rows = author_csv_rows("p", metadata, author, "ndss")

    assert [row["country"] for row in rows] == ["China", "China"]


def test_multiple_pdf_countries_are_preserved_by_affiliation_rank() -> None:
    author = {
        "name": "Alice Smith", "order": 0, "email": "",
        "affiliations": [
            "Official Laboratory, Germany",
            "Official University, USA",
            "Official Institute, France",
        ],
        "pdf_countries": ["China", "UK", ""],
        "first_author": True, "co_first_author": False,
        "corresponding": False, "equal_contribution": False,
    }
    metadata = {"year": "2025", "title": "Example", "authors": [author]}

    rows = author_csv_rows("p", metadata, author, "ndss")

    assert [row["country"] for row in rows] == ["China", "UK", "France"]


def test_four_security_conferences_share_the_same_author_export_rules() -> None:
    author = {
        "name": "Alice Smith", "order": 0, "email": "alice@example.org",
        "orcid": "0000-0001-2345-6789",
        "affiliations": ["Example Security Laboratory", "Example University, China"],
        "first_author": True, "co_first_author": False,
        "corresponding": True, "equal_contribution": False,
    }
    metadata = {"year": "2025", "title": "Example", "authors": [author]}

    for conference in ("CCS", "IEEE S&P", "NDSS", "USENIX Security"):
        rows = author_csv_rows("001_example", metadata, author, conference)
        assert [row["affiliation_rank"] for row in rows] == [0, 1]
        assert [row["country"] for row in rows] == ["China", "China"]
        assert all(row["orcid"] == "https://orcid.org/0000-0001-2345-6789" for row in rows)


def test_complete_symbol_mapping_preserves_multiple_affiliations() -> None:
    names = ["Alex Chen", "Blair Stone", "Casey Reed"]
    parsed = _parse_default_and_symbol_lines(names, [
        "Sample title",
        "Alex Chen†*, Blair Stone†, Casey Reed‡",
        "*Example University, †Center at Example University, ‡Example Institute",
        "achen@example.edu, bstone@example.edu, creed@institute.edu",
    ])

    assert parsed is not None
    assert parsed["replace_existing"] is True
    assert parsed["affiliations_by_author"]["alex chen"] == [
        "Center at Example University", "Example University",
    ]


def test_grouped_partial_domains_are_completed_and_matched_by_unique_name() -> None:
    lines = ["{achen@, bstone@mail.}example.edu"]
    context = SimpleNamespace(first_page_lines=lines, email_lines=lines)

    emails = extract_author_emails(context, ["Alex Chen", "Blair Stone"])

    assert emails == {
        "alex chen": "achen@example.edu",
        "blair stone": "bstone@mail.example.edu",
    }


def test_email_domain_affiliation_fill_requires_unique_direct_single_affiliation() -> None:
    authors = [
        {
            "name": "Alex Chen", "email": "alex@lab.example.edu",
            "affiliations": ["Example University"], "affiliation_source": "author_node",
        },
        {
            "name": "Blair Stone", "email": "blair@example.edu",
            "affiliations": [], "affiliation_source": "empty",
        },
        {
            "name": "Casey Reed", "email": "casey@gmail.com",
            "affiliations": [], "affiliation_source": "empty",
        },
        {
            "name": "* Damaged", "email": "damaged@example.edu",
            "affiliations": [], "affiliation_source": "empty",
        },
    ]

    result, decisions, reviews = apply_email_domain_affiliations(authors)

    assert result[1]["affiliations"] == ["Example University"]
    assert result[1]["affiliation_source"] == "email_domain_same_paper"
    assert result[2]["affiliations"] == []
    assert result[3]["affiliations"] == []
    assert decisions[0]["action"] == "fill_affiliation_from_email_domain"
    assert reviews == []
