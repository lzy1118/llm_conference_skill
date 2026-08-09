import sys

import reconcile_security_official_metadata as reconcile


def make_metadata(affiliations=None):
    return {
        "title": "Example Paper",
        "year": "2025",
        "abstract": "Abstract.",
        "authors": [
            {
                "order": 0,
                "name": "Alice Smith",
                "email": "alice@example.org",
                "affiliations": list(affiliations or []),
                "affiliation_source": "author_node" if affiliations else "empty",
                "first_author": True,
                "co_first_author": False,
                "corresponding": False,
                "equal_contribution": False,
            }
        ],
        "_extraction": {"evidence": [], "candidates": {}, "decisions": [], "review_reasons": []},
    }


def make_entry(name="Alice Smith", affiliation="Example University"):
    return {
        "title": "Example Paper",
        "authors": [name],
        "official_affiliations": [{"name": name, "affiliations": [affiliation]}],
        "url": "https://conference.example/paper",
    }


def test_four_conference_config_keys_are_supported():
    assert reconcile.conference_config_key("CCS", 2025) == "ccs_2025"
    assert reconcile.conference_config_key("IEEE_S&P", 2025) == "ieee_sp_2025"
    assert reconcile.conference_config_key("NDSS", 2025) == "ndss_2025"
    assert reconcile.conference_config_key("USENIX_SECURITY", 2025) == "usenix_security_2025"


def test_official_web_fills_only_blank_affiliation():
    updated, outcome = reconcile.reconcile_metadata(
        make_metadata(),
        make_entry(),
        "https://conference.example/accepted",
    )

    assert updated["authors"][0]["affiliations"] == ["Example University"]
    assert updated["authors"][0]["affiliation_source"] == "conference_official_web"
    assert outcome["affiliations_filled"] == 1
    assert not updated["_extraction"]["review_reasons"]


def test_nonempty_pdf_affiliation_is_preserved_and_conflict_is_reviewed():
    updated, outcome = reconcile.reconcile_metadata(
        make_metadata(["PDF University"]),
        make_entry(affiliation="Official University"),
        "https://conference.example/accepted",
    )

    assert updated["authors"][0]["affiliations"] == ["PDF University"]
    assert outcome["affiliations_filled"] == 0
    assert outcome["affiliation_conflicts"] == 1
    assert updated["_extraction"]["review_reasons"][0]["code"] == "official_web_affiliation_conflict"


def test_official_supplement_preserves_pdf_affiliation_and_existing_diagnostics():
    metadata = make_metadata(["PDF University"])
    metadata["_extraction"]["review_reasons"] = [
        {"code": "suspicious_author_name", "field": "author"},
        {"code": "ambiguous_equal_contribution_scope", "field": "co_first_author"},
    ]
    updated, outcome = reconcile.reconcile_metadata(
        metadata,
        make_entry(affiliation="Official University"),
        "https://conference.example/accepted",
    )

    assert updated["authors"][0]["affiliations"] == ["PDF University"]
    assert updated["authors"][0]["email"] == "alice@example.org"
    assert outcome["affiliation_conflicts"] == 1
    assert outcome["blank_affiliations_after"] == 0
    assert updated["_extraction"]["review_reasons"][:2] == metadata["_extraction"]["review_reasons"]
    assert updated["_extraction"]["review_reasons"][-1]["code"] == "official_web_affiliation_conflict"


def test_author_list_conflict_is_not_applied():
    updated, outcome = reconcile.reconcile_metadata(
        make_metadata(),
        make_entry(name="Bob Jones"),
        "https://conference.example/accepted",
    )

    assert [author["name"] for author in updated["authors"]] == ["Alice Smith"]
    assert outcome["author_conflict"] is True
    assert any(
        reason["code"] == "official_web_author_list_conflict"
        for reason in updated["_extraction"]["review_reasons"]
    )


def test_exact_title_does_not_rebuild_conflicting_pdf_author_list():
    updated, outcome = reconcile.reconcile_metadata(
        make_metadata(),
        make_entry(name="Bob Jones"),
        "https://conference.example/accepted",
    )

    assert [author["name"] for author in updated["authors"]] == ["Alice Smith"]
    assert updated["authors"][0]["affiliations"] == []
    assert outcome["authors_rebuilt"] is False
    assert outcome["author_count_delta"] == 0


def test_empty_author_list_is_recovered_only_for_exact_source_filename_match():
    metadata = make_metadata()
    metadata["title"] = ""
    metadata["authors"] = []

    updated, outcome = reconcile.reconcile_metadata(
        metadata,
        make_entry(),
        "https://conference.example/accepted",
        match_status="source_filename_exact",
    )

    assert [author["name"] for author in updated["authors"]] == ["Alice Smith"]
    assert updated["authors"][0]["affiliations"] == ["Example University"]
    assert updated["title"] == "Example Paper"
    assert outcome["authors_recovered"] == 1
    assert any(
        reason["code"] == "official_web_author_list_recovered_from_empty_extraction"
        for reason in updated["_extraction"]["review_reasons"]
    )

def test_exact_names_are_aligned_before_same_initial_surname_fallback():
    local = [
        {"name": "Yan Zhang"},
        {"name": "Yanchao Zhang"},
    ]
    web = [
        {"name": "Yan Zhang", "affiliations": ["A"]},
        {"name": "Yanchao Zhang", "affiliations": ["B"]},
    ]

    alignment, unmatched_local, unmatched_web = reconcile.unique_author_alignment(local, web)

    assert alignment == {0: 0, 1: 1}
    assert unmatched_local == []
    assert unmatched_web == []


def test_duplicate_official_author_rows_merge_affiliations():
    entry = {
        "authors": ["Alice Smith", "Alice Smith", "Bob Jones"],
        "official_affiliations": [
            {"name": "Alice Smith", "affiliations": ["University A"]},
            {"name": "Alice Smith", "affiliations": ["Lab B"]},
            {"name": "Bob Jones", "affiliations": ["Company C"]},
        ],
    }

    assert reconcile.official_authors(entry) == ["Alice Smith", "Bob Jones"]
    assert reconcile.official_rows(entry) == [
        {"name": "Alice Smith", "affiliations": ["University A", "Lab B"]},
        {"name": "Bob Jones", "affiliations": ["Company C"]},
    ]


def test_identical_duplicate_official_titles_are_not_ambiguous():
    entry = make_entry()
    lookup, ambiguous = reconcile.make_title_lookup([entry, dict(entry)])

    assert lookup["example paper"] == entry
    assert not ambiguous


def test_canonical_official_page_wins_over_auto_draft_duplicate():
    canonical = {**make_entry(), "url": "https://conference.example/paper/example"}
    auto_draft = {
        **make_entry(affiliation="Older Institution Wording"),
        "url": "https://conference.example/paper/auto-draft-12",
    }

    lookup, ambiguous = reconcile.make_title_lookup([auto_draft, canonical])

    assert lookup["example paper"] == canonical
    assert not ambiguous


def test_unique_fuzzy_title_match_requires_a_clear_margin():
    lookup, _ = reconcile.make_title_lookup([
        {**make_entry(), "title": "DRAWN APART: A Device Identification Technique"},
        {**make_entry(), "title": "Completely Different Security Paper"},
    ])

    entry, score = reconcile.unique_fuzzy_title_match(
        "DRAWNAPART: A Device Identification Technique",
        lookup,
    )

    assert entry["title"].startswith("DRAWN APART")
    assert score >= 0.85


def test_unique_contained_title_match_accepts_one_long_truncated_title():
    lookup, _ = reconcile.make_title_lookup([
        {**make_entry(), "title": "Attacks on Wireless Coexistence"},
        {**make_entry(), "title": "Completely Different Security Paper"},
    ])

    entry = reconcile.unique_contained_title_match(
        "Attacks on Wireless Coexistence: Exploiting Cross-Technology Performance Features",
        lookup,
    )

    assert entry["title"] == "Attacks on Wireless Coexistence"


def test_unique_contained_title_match_rejects_short_or_ambiguous_prefixes():
    lookup, _ = reconcile.make_title_lookup([
        {**make_entry(), "title": "Security Analysis of Wireless Systems"},
        {**make_entry(), "title": "Security Analysis of Wireless Systems at Scale"},
    ])

    assert reconcile.unique_contained_title_match("Security Analysis", lookup) is None
    assert reconcile.unique_contained_title_match(
        "Security Analysis of Wireless Systems at Scale in Practice",
        lookup,
    ) is None


def test_csv_author_sequence_deduplicates_affiliation_rows():
    rows = [
        {"author_rank": "0", "affiliation_rank": "0", "author": "Alice Smith"},
        {"author_rank": "0", "affiliation_rank": "1", "author": "Alice Smith"},
        {"author_rank": "0", "affiliation_rank": "0", "author": "Bob Jones"},
    ]

    assert reconcile.csv_author_sequence(rows) == ["Alice Smith", "Bob Jones"]


def test_csv_author_sequence_keeps_nonconsecutive_same_names():
    rows = [
        {"author_rank": "0", "affiliation_rank": "0", "author": "Information Security"},
        {"author_rank": "1", "affiliation_rank": "0", "author": "Alice Smith"},
        {"author_rank": "2", "affiliation_rank": "0", "author": "Information Security"},
    ]

    assert reconcile.csv_author_sequence(rows) == [
        "Information Security",
        "Alice Smith",
        "Information Security",
    ]


def test_csv_author_sequence_ignores_placeholder_rows():
    rows = [
        {"author_rank": "", "affiliation_rank": "", "author": "NO_AUTHORS_EXTRACTED"},
    ]

    assert reconcile.csv_author_sequence(rows) == []


def test_pdf_countries_are_restored_with_affiliation_rank_positions():
    metadata = make_metadata(["Official A", "Official B"])
    source_rows = [
        {"author": "Alice Smith", "affiliation_rank": "0", "country": "China"},
        {"author": "Alice Smith", "affiliation_rank": "1", "country": "UK"},
    ]

    restored_authors, restored_values = reconcile.restore_pdf_countries(
        metadata,
        source_rows,
    )

    assert (restored_authors, restored_values) == (1, 2)
    assert metadata["authors"][0]["pdf_countries"] == ["China", "UK"]
    assert metadata["_extraction"]["decisions"][-1]["stage"] == "pdf_country_preservation"


def test_existing_pdf_countries_are_not_overwritten_on_rerun():
    metadata = make_metadata(["Official University"])
    metadata["authors"][0]["pdf_countries"] = ["China"]

    restored = reconcile.restore_pdf_countries(
        metadata,
        [{"author": "Alice Smith", "affiliation_rank": "0", "country": "USA"}],
    )

    assert restored == (0, 0)
    assert metadata["authors"][0]["pdf_countries"] == ["China"]


def test_pdf_country_restore_uses_position_for_corrected_author_spelling():
    metadata = make_metadata(["Official University"])
    metadata["authors"][0]["name"] = "Alice van Smith"

    restored = reconcile.restore_pdf_countries(
        metadata,
        [{"author": "Alice Smith", "affiliation_rank": "0", "country": "China"}],
    )

    assert restored == (1, 1)
    assert metadata["authors"][0]["pdf_countries"] == ["China"]


def test_oldest_official_backup_is_used_as_pdf_country_source(tmp_path):
    current = tmp_path / "paper_metadata.csv"
    current.write_text("paper_id,author,country\np,Alice Smith,USA\n", encoding="utf-8")
    oldest = tmp_path / "backups" / "before_official_web_20250101T000000" / "paper_metadata.csv"
    newest = tmp_path / "backups" / "before_official_web_20260101T000000" / "paper_metadata.csv"
    oldest.parent.mkdir(parents=True)
    newest.parent.mkdir(parents=True)
    oldest.write_text("paper_id,author,country\np,Alice Smith,China\n", encoding="utf-8")
    newest.write_text("paper_id,author,country\np,Alice Smith,USA\n", encoding="utf-8")

    assert reconcile.earliest_pdf_country_csv(tmp_path, current) == oldest


def test_unmatched_paper_is_routed_to_review():
    updated, outcome = reconcile.reconcile_metadata(
        make_metadata(),
        None,
        "https://conference.example/accepted",
    )

    assert outcome["match_status"] == "unmatched"
    assert outcome["blank_affiliations_after"] == 1
    assert updated["_extraction"]["review_reasons"][0]["code"] == "official_web_paper_unmatched"


def test_unavailable_official_supplement_does_not_block_pdf_dataset(tmp_path, monkeypatch, capsys):
    dataset = tmp_path / "author_metadata_dataset_2025"
    dataset.mkdir()
    (dataset / "metadata_json").mkdir()
    (dataset / "paper_index.csv").write_text("paper_id,status\n", encoding="utf-8")
    (dataset / "paper_metadata.csv").write_text("paper_id,title,author\n", encoding="utf-8")
    cache_path = dataset / "official_web_evidence" / "ccs_2025.json"
    monkeypatch.setattr(
        reconcile,
        "load_official_entries_with_cache",
        lambda *_args: ([], cache_path, "unavailable"),
    )
    monkeypatch.setattr(sys, "argv", [
        "reconcile_security_official_metadata.py",
        "--dataset-dir", str(dataset),
        "--conference", "CCS",
        "--year", "2025",
        "--apply",
    ])

    assert reconcile.main() == 0
    payload = capsys.readouterr().out
    assert "official_supplement_unavailable" in payload
    assert (dataset / "official_web_reconciliation.csv").exists()


def test_pdf_symbol_line_repairs_role_text_used_as_affiliation():
    metadata = make_metadata(["Equal Contribution"])
    metadata["title"] = "Privacy Analysis for Distributed Systems"
    metadata["authors"].append({
        **metadata["authors"][0],
        "order": 1,
        "name": "Bob Jones",
        "email": "bob@example.com",
        "first_author": False,
    })
    metadata["_extraction"]["evidence"] = [
        {"source": "pdf_text", "field": "header_line", "raw_text": "Privacy Analysis for Distributed Systems"},
        {"source": "pdf_text", "field": "header_line", "raw_text": "Alice Smith*†, Bob Jones*"},
        {"source": "pdf_text", "field": "header_line", "raw_text": "* Example Corp, † Equal Contribution."},
    ]
    entry = {
        "title": "Privacy Analysis for Distributed Systems",
        "authors": ["Alice Smith", "Bob Jones"],
        "official_affiliations": [],
    }

    repaired = reconcile.repair_missing_official_affiliations_from_pdf(
        metadata,
        entry,
        "IEEE_S&P",
    )

    assert [author["affiliations"] for author in repaired["authors"]] == [
        ["Example Corp"],
        ["Example Corp"],
    ]
    assert repaired["authors"][0]["co_first_author"] is True
    assert repaired["authors"][1]["co_first_author"] is False
