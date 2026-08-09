import lncs_strategy
from types import SimpleNamespace
from xml.etree import ElementTree

from author_metadata.config import CONFERENCE_STRATEGY_MODULES
from author_metadata.metadata_repair import (
    apply_author_roles,
    extract_role_hints,
    is_author_name_noise,
)


def authors(*names):
    return [
        {
            "order": order,
            "name": name,
            "email": "",
            "affiliations": [],
            "first_author": order == 0,
            "co_first_author": False,
            "equal_contribution": False,
            "corresponding": False,
        }
        for order, name in enumerate(names)
    ]


def test_registers_lncs_strategy_for_cryptography_conferences() -> None:
    for conference in ("crypto", "eurocrypt", "asiacrypt"):
        assert CONFERENCE_STRATEGY_MODULES[conference] == "author_metadata.strategies.lncs"


def test_marks_lncs_b_marker_as_corresponding_author() -> None:
    result = lncs_strategy.refine_authors(
        authors("Shweta Agrawal", "Anshu Yadav", "Shota Yamada"),
        pdf_lines=[
            "Multi-input Attribute Based Encryption and Predicate Encryption",
            "Shweta Agrawal1, Anshu Yadav1(B), and Shota Yamada2",
            "1 IIT Madras, Chennai, India",
            "Abstract. Motivated by several applications",
        ],
    )

    assert [item["corresponding"] for item in result] == [False, True, False]


def test_supports_ocr_spaced_names_and_multiple_corresponding_authors() -> None:
    result = lncs_strategy.refine_authors(
        authors("Xiaoyang Dong", "Jian Guo", "Shun Li", "Phuong Pham"),
        pdf_lines=[
            "Xiaoyang Dong1,3(B), J i a n G u o2(B), S h u n L i2,4(B),",
            "and Phuong Pham2(B)",
            "Abstract. Example",
        ],
    )

    assert all(item["corresponding"] for item in result)


def test_does_not_treat_affiliation_or_body_b_as_role_marker() -> None:
    result = lncs_strategy.refine_authors(
        authors("Alice Smith", "Bob Jones"),
        pdf_lines=[
            "Alice Smith1 and Bob Jones2",
            "1 Department B, Example University",
            "Abstract. The corresponding construction is secure.",
        ],
    )

    assert not any(item["corresponding"] for item in result)


def test_restores_missing_corresponding_author_in_pdf_order() -> None:
    result = lncs_strategy.refine_authors(
        authors("Siyao Guo", "Qipeng Liu"),
        pdf_lines=[
            "Time-Space Lower Bounds for Finding Collisions",
            "Akshima1(B), Siyao Guo2, and Qipeng Liu3",
            "1 University of Chicago, Chicago, USA",
            "Abstract. Example",
        ],
    )

    assert [item["name"] for item in result] == ["Akshima", "Siyao Guo", "Qipeng Liu"]
    assert [item["corresponding"] for item in result] == [True, False, False]
    # Numbered mapping is rejected when refs 2 and 3 have no explicit entries.
    assert result[0]["affiliations"] == []
    assert result[0]["affiliation_source"] == "lncs_pdf_corresponding_marker"


def test_restores_missing_marker_author_with_multiple_affiliations() -> None:
    result = lncs_strategy.refine_authors(
        authors("Bob Jones"),
        pdf_lines=[
            "Alice Smith1,3(B), and Bob Jones2",
            "1 Example University",
            "Abstract. Example",
        ],
    )

    assert [item["name"] for item in result] == ["Alice Smith", "Bob Jones"]
    assert result[0]["corresponding"] is True


def test_matches_reversed_grobid_name_to_pdf_marker() -> None:
    result = lncs_strategy.refine_authors(
        authors("Abram Damiano", "Ivan Damgård", "Claudio Orlandi", "Peter Scholl"),
        pdf_lines=[
            "Damiano Abram(B), Ivan Damgård, Claudio Orlandi, and Peter Scholl",
            "Aarhus University, Aarhus, Denmark",
            "Abstract. Example",
        ],
    )

    assert [item["name"] for item in result] == ["Abram Damiano", "Ivan Damgård", "Claudio Orlandi", "Peter Scholl"]
    assert result[0]["corresponding"] is True


def test_maps_wrapped_numbered_affiliations_and_replaces_tei_fragment() -> None:
    input_authors = authors("Zhongfeng Niu", "Siwei Sun", "Yunwen Liu", "Chao Li")
    input_authors[3]["affiliations"] = ["Engineering, Chinese Academy of Sciences, Beijing, China"]
    result = lncs_strategy.refine_authors(
        input_authors,
        pdf_lines=[
            "Zhongfeng Niu1,2,3, Siwei Sun2,5(B), Yunwen Liu1,2,3,4,5, and Chao Li4",
            "1 State Key Laboratory of Information Security, Institute of Information",
            "Engineering, Chinese Academy of Sciences, Beijing, China",
            "2 School of Cryptology, University of Chinese Academy of Sciences, Beijing, China",
            "3 School of Cyber Security, University of Chinese Academy of Sciences,",
            "Beijing, China",
            "4 College of Liberal Arts and Science, National University of Defense Technology,",
            "Changsha, China",
            "5 State Key Laboratory of Cryptology, P.O. Box 5159, Beijing 100878, China",
        ],
    )

    assert result[3]["affiliations"] == [
        "College of Liberal Arts and Science, National University of Defense Technology, Changsha, China"
    ]
    assert result[3]["affiliation_source"] == "lncs_pdf_numbered"


def test_assigns_single_shared_lncs_affiliation_to_restored_author() -> None:
    result = lncs_strategy.refine_authors(
        authors("Carsten Baum", "Alexander Munch-Hansen", "Peter Scholl"),
        pdf_lines=[
            "Carsten Baum, Lennart Braun(B), Alexander Munch-Hansen,",
            "and Peter Scholl",
            "Aarhus University, Aarhus, Denmark",
            "{cbaum,braun,almun,peter.scholl}@cs.au.dk",
        ],
    )

    lennart = next(item for item in result if item["name"] == "Lennart Braun")
    assert lennart["affiliations"] == ["Aarhus University, Aarhus, Denmark"]
    assert lennart["affiliation_source"] == "lncs_pdf_shared"


def test_final_generic_role_pass_preserves_strategy_roles() -> None:
    marked = authors("Alice Smith", "Bob Jones")
    marked[1]["corresponding"] = True

    result = apply_author_roles(
        marked,
        {
            "corresponding_names": set(),
            "equal_contribution_names": set(),
            "equal_contribution": False,
        },
        preserve_existing=True,
    )

    assert [item["corresponding"] for item in result] == [False, True]


def test_generic_role_hints_do_not_misread_next_b_name_as_marker() -> None:
    root = ElementTree.fromstring('<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader/></TEI>')
    context = SimpleNamespace(
        first_page_text="Nishanth Chandran1, Bhavana Kanukurthi2, and Sruthi Sekar3(B)",
    )

    hints = extract_role_hints(
        root,
        context,
        ["Nishanth Chandran", "Bhavana Kanukurthi", "Sruthi Sekar"],
    )

    assert hints["corresponding_names"] == set()


def test_generic_role_hints_resolve_explicit_first_n_scope() -> None:
    root = ElementTree.fromstring('<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader/></TEI>')
    names = ["Alice Smith", "Bob Jones", "Carol Lee", "Dan Wu"]
    context = SimpleNamespace(
        first_page_text="The first three authors contributed equally.",
    )

    hints = extract_role_hints(root, context, names)
    result = apply_author_roles(authors(*names), hints)

    assert hints["equal_contribution_names"] == {
        "alice smith", "bob jones", "carol lee",
    }
    assert [item["co_first_author"] for item in result] == [True, True, True, False]


def test_ambiguous_equal_contribution_is_reviewed_not_guessed() -> None:
    root = ElementTree.fromstring('<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader/></TEI>')
    context = SimpleNamespace(first_page_text="Some authors contributed equally.")

    hints = extract_role_hints(root, context, ["Alice Smith", "Bob Jones", "Carol Lee"])
    result = apply_author_roles(authors("Alice Smith", "Bob Jones", "Carol Lee"), hints)

    assert not any(item["co_first_author"] for item in result)
    assert hints["review_reasons"][0]["code"] == "ambiguous_equal_contribution_scope"


def test_person_name_with_sim_substring_is_not_noise() -> None:
    assert is_author_name_noise("Georgios Tsimos") is False
