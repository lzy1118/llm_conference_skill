import csv
import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_affilgood_facts.py"
SPEC = importlib.util.spec_from_file_location("prepare_affilgood_facts", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_converts_affilgood_row_to_fact_and_dimension():
    facts, dimensions = MODULE.convert_rows([{
        "paper_id": "001_example",
        "conference": "crypto",
        "year": "2022",
        "title": "Example",
        "author": "Alice Smith",
        "author_rank": "0",
        "affiliation_rank": "0",
        "affiliations": "Example University, Boston, USA",
        "record_id": "row-1",
        "affilgood_institutions": "Example University",
        "affilgood_standard_institutions": "Example University",
        "affilgood_ror_ids": "https://ror.org/example",
        "affilgood_location_country": "United States",
        "affiliation_subunits": "Security Laboratory",
        "country_source": "pdf_explicit",
        "country_confidence": "high",
        "institution_reference_match_method": "component",
        "institution_reference_confidence": "high",
        "institution_reference_status": "matched",
    }])

    assert facts[0]["paper_key"] == "001_example"
    assert facts[0]["name"] == "Alice Smith"
    assert facts[0]["institution_id"] == "https://ror.org/example"
    assert facts[0]["country"] == "United States"
    assert facts[0]["institution_source"] == "institution_raw"
    assert facts[0]["subunit"] == "Security Laboratory"
    assert facts[0]["country_source"] == "pdf_explicit"
    assert facts[0]["institution_match_method"] == "component"
    assert dimensions[0]["needs_review"] == "false"


def test_keeps_raw_affiliation_as_automatic_fallback():
    facts, dimensions = MODULE.convert_rows([{
        "paper_id": "001_example",
        "conference": "crypto",
        "year": "2022",
        "title": "Example",
        "author": "Alice Smith",
        "author_rank": "0",
        "affiliation_rank": "0",
        "affiliations": "State Key Laboratory, Beijing, China",
        "record_id": "row-1",
        "affilgood_institutions": "",
        "affilgood_standard_institutions": "",
        "affilgood_ror_ids": "",
        "affilgood_location_country": "China",
    }])

    assert facts[0]["inst"] == "State Key Laboratory, Beijing, China"
    assert facts[0]["institution_source"] == "raw_affiliation_fallback"
    assert dimensions[0]["needs_review"] == "false"


def test_defaults_standalone_department_to_independent_researcher():
    facts, dimensions = MODULE.convert_rows([{
        "paper_id": "001_example",
        "conference": "crypto",
        "year": "2022",
        "title": "Example",
        "author": "Alice Smith",
        "author_rank": "0",
        "affiliation_rank": "0",
        "affiliations": "Department of Electronic Engineering, China",
        "record_id": "row-1",
        "affilgood_institutions": "",
        "affilgood_standard_institutions": "",
        "affilgood_location_country": "China",
        "affiliation_subunits": "Department of Electronic Engineering",
    }])

    assert facts[0]["institution_source"] == "independent_researcher_default"
    assert facts[0]["inst"] == "Independent Researcher"
    assert facts[0]["institution_id"] == "NONINSTITUTIONAL"
    assert facts[0]["subunit"] == "Department of Electronic Engineering"
    assert dimensions == []


def test_defaults_affilgood_secondary_unit_to_independent_researcher():
    facts, dimensions = MODULE.convert_rows([{
        "paper_id": "001_example",
        "conference": "ccs",
        "year": "2025",
        "title": "Example",
        "author": "Alice Smith",
        "author_rank": "0",
        "affiliation_rank": "0",
        "affiliations": "College of Cyber Security, Guangzhou, China",
        "record_id": "row-1",
        "affilgood_institutions": "College of Cyber Security",
        "affilgood_standard_institutions": "College of Cyber Security",
        "affilgood_location_country": "China",
        "affiliation_subunits": "College of Cyber Security",
    }])

    assert facts[0]["institution_source"] == "independent_researcher_default"
    assert facts[0]["canonical_institution_name"] == "Independent Researcher"
    assert dimensions == []


def test_merges_ocr_inserted_author_spaces():
    rows = []
    for index, name in enumerate(("Xiaoyun Wang", "Xiaoyun WAng", "Xiaoyun Wa Ng")):
        rows.append({
            "paper_id": f"p{index}",
            "conference": "asiacrypt",
            "year": "2025",
            "title": "Example",
            "author": name,
            "author_rank": "0",
            "affiliation_rank": "0",
            "affiliations": "Tsinghua University, China",
            "record_id": f"row-{index}",
            "emails": "xiaoyunwang@tsinghua.edu.cn",
            "affilgood_institutions": "Tsinghua University",
            "affilgood_standard_institutions": "Tsinghua University",
            "affilgood_location_country": "China",
            "institution_reference_status": "matched",
        })

    facts, _ = MODULE.convert_rows(rows)
    assert {row["author_key"] for row in facts} == {facts[0]["author_key"]}
    assert {row["name"] for row in facts} == {"Xiaoyun Wang"}


def test_unifies_cispa_variants_with_helmholtz_center():
    facts, dimensions = MODULE.convert_rows([{
        "paper_id": "cispa-example",
        "conference": "eurocrypt",
        "year": "2025",
        "title": "CISPA example",
        "author": "Alice Smith",
        "author_rank": "0",
        "affiliation_rank": "0",
        "affiliations": "CISPA Helmholtz Center for Information Security, Saarbrucken, Germany",
        "record_id": "cispa-row",
        "affilgood_institutions": "",
        "affilgood_standard_institutions": "",
        "affilgood_location_country": "Germany",
    }])

    assert facts[0]["canonical_institution_name"] == "Helmholtz Center for Information Security"
    assert facts[0]["institution_id"] == "https://ror.org/02njgxr09"
    assert facts[0]["country"] == "Germany"
    assert dimensions[0]["inst_display"] == "Helmholtz Center for Information Security"


def test_cispa_overrides_incorrect_helmholtz_standard_name():
    facts, _ = MODULE.convert_rows([{
        "paper_id": "cispa-hips-example",
        "conference": "ccs",
        "year": "2025",
        "title": "CISPA alias example",
        "author": "Alice Smith",
        "author_rank": "0",
        "affiliation_rank": "0",
        "affiliations": "CISPA Helmholtz, Saarbrucken, Germany",
        "record_id": "cispa-hips-row",
        "affilgood_institutions": "CISPA Helmholtz",
        "affilgood_standard_institutions": "Helmholtz Institute for Pharmaceutical Research Saarland",
        "affilgood_ror_ids": "https://ror.org/042dsac10",
        "affilgood_location_country": "Germany",
    }])

    assert facts[0]["inst"] == "Helmholtz Center for Information Security"
    assert facts[0]["canonical_institution_name"] == "Helmholtz Center for Information Security"
    assert facts[0]["institution_id"] == "https://ror.org/02njgxr09"


def test_splits_aligned_institutions_in_one_affiliation_rank():
    facts, dimensions = MODULE.convert_rows([{
        "paper_id": "001_composite",
        "conference": "eurocrypt",
        "year": "2025",
        "title": "Composite",
        "author": "Alice Smith",
        "author_rank": "0",
        "affiliation_rank": "0",
        "affiliations": "University Alpha, Institute Beta, France",
        "record_id": "row-composite",
        "affilgood_institutions": "University Alpha;Institute Beta",
        "affilgood_standard_institutions": "University Alpha;Institute Beta",
        "affilgood_ror_ids": "ror-alpha;ror-beta",
        "affilgood_location_country": "France",
        "institution_reference_status": "affilgood_resolved",
    }])

    assert len(facts) == 2
    assert len(dimensions) == 2
    assert {
        (row["canonical_institution_name"], row["institution_id"])
        for row in facts
    } == {
        ("University Alpha", "ror-alpha"),
        ("Institute Beta", "ror-beta"),
    }
    assert {row["institution_key"] for row in facts} == {
        row["institution_key"] for row in dimensions
    }


def test_splits_aligned_institutions_and_countries_by_position():
    facts, _ = MODULE.convert_rows([{
        "paper_id": "001_composite_country",
        "conference": "eurocrypt",
        "year": "2025",
        "title": "Composite Country",
        "author": "Alice Smith",
        "author_rank": "0",
        "affiliation_rank": "0",
        "affiliations": "University Alpha;Institute Beta",
        "record_id": "row-composite-country",
        "affilgood_institutions": "University Alpha;Institute Beta",
        "affilgood_standard_institutions": "University Alpha;Institute Beta",
        "affilgood_ror_ids": "ror-alpha;ror-beta",
        "affilgood_location_country": "Country Alpha | Country Beta",
        "institution_reference_status": "affilgood_resolved",
    }])

    assert {
        (row["canonical_institution_name"], row["country"])
        for row in facts
    } == {
        ("University Alpha", "Country Alpha"),
        ("Institute Beta", "Country Beta"),
    }


def test_primary_country_backfill_reaches_analytics_fact():
    facts, _ = MODULE.convert_rows([{
        "paper_id": "001_country",
        "conference": "crypto",
        "year": "2025",
        "title": "Country",
        "author": "Alice Smith",
        "author_rank": "0",
        "affiliation_rank": "0",
        "affiliations": "EPFL",
        "record_id": "row-country",
        "affilgood_institutions": "EPFL",
        "affilgood_standard_institutions": "EPFL",
        "affilgood_location_country": "",
        "primary_country": "Switzerland",
        "primary_country_source": "reviewed_rule_country_backfill:epfl",
    }])

    assert facts[0]["country"] == "Switzerland"
    assert facts[0]["country_source"] == "reviewed_rule_country_backfill:epfl"


def test_keeps_paper_when_affilgood_component_lists_have_different_lengths():
    facts, dimensions = MODULE.convert_rows([{
        "paper_id": "001_mismatched_components",
        "conference": "ccs",
        "year": "2020",
        "title": "Mismatched components",
        "author": "Alice Smith",
        "author_rank": "0",
        "affiliation_rank": "0",
        "affiliations": "Inria Paris, Microsoft Research, Carnegie Mellon University, Inria Paris",
        "record_id": "row-mismatch",
        "affilgood_institutions": "Inria Paris;Microsoft Research;Carnegie Mellon University;Inria Paris",
        "affilgood_standard_institutions": "Centre Inria de Paris;Microsoft Research;Carnegie Mellon University",
        "affilgood_ror_ids": "ror-inria;ror-ms;ror-cmu",
        "affilgood_location_country": "France;United States",
    }])

    assert {row["paper_key"] for row in facts} == {"001_mismatched_components"}
    assert {row["canonical_institution_name"] for row in facts if row["canonical_institution_name"]} == {
        "Centre Inria de Paris", "Microsoft Research", "Carnegie Mellon University",
    }
    assert all(row["institution_source"] != "unresolved_composite_fragment" for row in facts)
    assert len(dimensions) == 3


def test_resolves_partial_identity_list_by_name_registry_and_drops_fragment():
    rows = [
        {
            "paper_id": "001_ruhr",
            "conference": "asiacrypt",
            "year": "2023",
            "title": "Registry",
            "author": "Bob Jones",
            "author_rank": "0",
            "affiliation_rank": "0",
            "affilgood_standard_institutions": "Ruhr University Bochum",
            "affilgood_institutions": "Ruhr University Bochum",
            "affilgood_ror_ids": "ror-ruhr",
            "affilgood_location_country": "Germany",
        },
        {
            "paper_id": "001_paderborn",
            "conference": "asiacrypt",
            "year": "2023",
            "title": "Registry",
            "author": "Carol Jones",
            "author_rank": "0",
            "affiliation_rank": "0",
            "affilgood_standard_institutions": "Paderborn University",
            "affilgood_institutions": "Paderborn University",
            "affilgood_ror_ids": "ror-paderborn",
            "affilgood_location_country": "Germany",
        },
        {
            "paper_id": "002_partial",
            "conference": "ccs",
            "year": "2020",
            "title": "Partial",
            "author": "Alice Smith",
            "author_rank": "0",
            "affiliation_rank": "0",
            "affilgood_standard_institutions": "Ruhr University Bochum;Münster University of Applied Sciences;Paderborn University",
            "affilgood_institutions": "Ruhr University Bochum;Münster University of Applied Sciences;Paderborn University",
            "affilgood_ror_ids": "ror-ruhr;ror-paderborn",
            "affilgood_location_country": "Germany",
        },
    ]

    facts, _ = MODULE.convert_rows(rows)
    partial = [row for row in facts if row["paper_key"] == "002_partial"]
    assert {(row["canonical_institution_name"], row["institution_id"]) for row in partial} == {
        ("Ruhr University Bochum", "ror-ruhr"),
        ("Paderborn University", "ror-paderborn"),
    }


def test_defaults_unresolved_composite_to_independent_researcher():
    facts, dimensions = MODULE.convert_rows([{
        "paper_id": "003_unresolved_composite",
        "conference": "ndss",
        "year": "2025",
        "title": "Unresolved",
        "author": "Alice Smith",
        "author_rank": "0",
        "affiliation_rank": "0",
        "affilgood_institutions": "Unresolved Alpha;Unresolved Beta",
        "affilgood_standard_institutions": "Unresolved Alpha;Unresolved Beta",
        "affilgood_ror_ids": "",
        "affilgood_location_country": "Country Alpha;Country Beta",
    }])

    assert {(row["paper_key"], row["country"]) for row in facts} == {
        ("003_unresolved_composite", "Country Alpha"),
        ("003_unresolved_composite", "Country Beta"),
    }
    assert all(row["institution_source"] == "independent_researcher_default" for row in facts)
    assert all(row["canonical_institution_name"] == "Independent Researcher" for row in facts)
    assert all(row["institution_id"] == "NONINSTITUTIONAL" for row in facts)
    assert dimensions == []


def test_unicode_names_titles_and_institutions_get_distinct_keys():
    rows = [
        {
            "paper_id": "p1",
            "title": "密码学的新进展",
            "author": "张伟",
            "author_rank": "0",
            "affiliation_rank": "0",
            "affiliations": "清华大学",
            "affilgood_institutions": "清华大学",
            "affilgood_standard_institutions": "清华大学",
            "affilgood_location_country": "China",
        },
        {
            "paper_id": "p2",
            "title": "计算机安全的新进展",
            "author": "李伟",
            "author_rank": "0",
            "affiliation_rank": "0",
            "affiliations": "北京大学",
            "affilgood_institutions": "北京大学",
            "affilgood_standard_institutions": "北京大学",
            "affilgood_location_country": "China",
        },
    ]

    facts, _ = MODULE.convert_rows(rows)

    assert len({row["author_key"] for row in facts}) == 2
    assert len({row["institution_key"] for row in facts}) == 2
    assert MODULE.stable_key("title", rows[0]["title"]) != MODULE.stable_key("title", rows[1]["title"])


def test_preserves_explicit_author_key():
    facts, _ = MODULE.convert_rows([{
        "paper_id": "p1",
        "title": "Explicit key",
        "author": "Alice Smith",
        "author_key": "person:verified-42",
        "author_rank": "0",
        "affiliation_rank": "0",
        "affiliations": "Example University",
        "affilgood_institutions": "Example University",
        "affilgood_standard_institutions": "Example University",
        "affilgood_location_country": "United States",
    }])

    assert facts[0]["author_key"] == "person:verified-42"
