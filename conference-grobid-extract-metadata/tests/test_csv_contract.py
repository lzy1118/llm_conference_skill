import csv

from author_metadata.exporter import (
    ABSTRACT_FIELDNAMES,
    CSV_FIELDNAMES,
    export_abstract_csv,
    export_csv,
)


def test_paper_metadata_csv_preserves_paper_id(tmp_path) -> None:
    assert CSV_FIELDNAMES == [
        "paper_id", "year", "conference", "title", "author", "author_rank",
        "affiliation_rank", "affiliations", "emails", "first_author",
        "co_first_author", "corresponding", "equal_contribution", "country", "orcid",
    ]
    output = tmp_path / "paper_metadata.csv"
    row = {field: "" for field in CSV_FIELDNAMES}
    row.update({"paper_id": "crypto_2022_p0001", "year": "2022", "title": "Example"})

    export_csv(output, [row])

    with output.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        saved = next(reader)
    assert reader.fieldnames[0] == "paper_id"
    assert saved["paper_id"] == "crypto_2022_p0001"
    assert saved["year"] == "2022"


def test_abstract_csv_has_one_paper_level_contract(tmp_path) -> None:
    output = tmp_path / "conference_year_paper_abstract.csv"
    export_abstract_csv(output, [{
        "conference": "ccs",
        "year": "2025",
        "title": "Example",
        "abstract": "A paper-level abstract.",
    }])

    with output.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        saved = next(reader)
    assert reader.fieldnames == ABSTRACT_FIELDNAMES
    assert saved == {
        "conference": "ccs",
        "year": "2025",
        "title": "Example",
        "abstract": "A paper-level abstract.",
    }
