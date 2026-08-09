from author_metadata.pdf_context import PdfContext
from author_metadata.role_linking import apply_author_roles, extract_role_hints


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


def make_authors(names):
    return [{"order": index, "name": name} for index, name in enumerate(names)]


def test_links_equal_contribution_marker_to_marked_authors():
    names = ["Ren Ding", "Yonghae Kim", "Fan Sang"]
    context = make_context([
        "Ren Ding∗",
        "Yonghae Kim∗",
        "Fan Sang",
        "ABSTRACT",
        "∗Both authors contributed equally to this work.",
    ])

    hints = extract_role_hints(None, context, names)
    authors = apply_author_roles(make_authors(names), hints)

    assert hints["equal_contribution_names"] == {"ren ding", "yonghae kim"}
    assert [author["co_first_author"] for author in authors] == [True, True, False]
    assert [author["equal_contribution"] for author in authors] == [True, True, False]


def test_links_corresponding_marker_without_name_in_footnote():
    names = ["Xiaoyu Ji", "Wenyuan Xu"]
    context = make_context([
        "Xiaoyu Ji",
        "Wenyuan Xu∗",
        "ABSTRACT",
        "∗Corresponding author.",
    ])

    hints = extract_role_hints(None, context, names)
    authors = apply_author_roles(make_authors(names), hints)

    assert hints["corresponding_names"] == {"wenyuan xu"}
    assert [author["corresponding"] for author in authors] == [False, True]


def test_supports_first_n_and_explicit_corresponding_name_in_same_page():
    names = ["Baolin Zheng", "Peipei Jiang", "Qian Wang", "Qi Li"]
    context = make_context([
        "Baolin Zheng1,∗, Peipei Jiang1,∗, Qian Wang1,†, Qi Li2",
        "ABSTRACT",
        "∗The first two authors contributed equally to this work.",
        "†Qian Wang is the corresponding author.",
    ])

    hints = extract_role_hints(None, context, names)
    authors = apply_author_roles(make_authors(names), hints)

    assert hints["equal_contribution_names"] == {"baolin zheng", "peipei jiang"}
    assert hints["corresponding_names"] == {"qian wang"}
    assert [author["corresponding"] for author in authors] == [False, False, True, False]


def test_does_not_treat_generic_corresponding_word_as_author_role():
    names = ["Alice Smith", "Bob Jones"]
    context = make_context([
        "Alice Smith",
        "Bob Jones",
        "ABSTRACT",
        "The corresponding vulnerability report was retrieved.",
    ])

    hints = extract_role_hints(None, context, names)

    assert not hints["corresponding_names"]


def test_does_not_match_different_given_name_with_same_surname():
    names = ["Yifan Zhang", "Yuqing Zhang"]
    context = make_context([
        "Yifan Zhang, Yuqing Zhang∗",
        "ABSTRACT",
        "∗Corresponding author: Yuqing Zhang.",
    ])

    hints = extract_role_hints(None, context, names)

    assert hints["corresponding_names"] == {"yuqing zhang"}


def test_links_envelope_and_encoded_envelope_markers():
    names = ["Yinqian Zhang", "Xiaorui Gong"]
    context = make_context([
        "Yinqian Zhang✉",
        "Xiaorui Gong B",
        "ABSTRACT",
        "✉Corresponding authors",
        "B Corresponding author.",
    ])

    hints = extract_role_hints(None, context, names)

    assert hints["corresponding_names"] == {"yinqian zhang", "xiaorui gong"}


def test_links_wrapped_corresponding_note_names():
    names = ["Guojun Peng", "Jiang Ming", "Lin Jiang"]
    context = make_context([
        "Jiang Ming3,†, Lin Jiang4",
        "Guojun Peng1,2,†",
        "ABSTRACT",
        "†Guojun Peng and Jiang Ming are the",
        "corresponding authors.",
    ])

    hints = extract_role_hints(None, context, names)

    assert hints["corresponding_names"] == {"guojun peng", "jiang ming"}


def test_links_correspondence_email_to_author():
    names = ["Sreeram Kannan", "Pramod Viswanath"]
    context = make_context([
        "Sreeram Kannan",
        "ksreeram@uw.edu",
        "Pramod Viswanath",
        "pramodv@illinois.edu",
        "ABSTRACT",
        "Correspondence can be sent to ksreeram@uw.edu.",
    ])

    hints = extract_role_hints(
        None,
        context,
        names,
        {"Sreeram Kannan": "ksreeram@uw.edu", "Pramod Viswanath": "pramodv@illinois.edu"},
    )

    assert hints["corresponding_names"] == {"sreeram kannan"}


def test_links_marker_when_middle_initial_is_expanded_in_pdf():
    names = ["Siam U. Hussain", "Mojan Javaheripi"]
    context = make_context([
        "Siam Umar Hussain∗ Mojan Javaheripi∗",
        "ABSTRACT",
        "∗Authors contributed equally to this research.",
    ])

    hints = extract_role_hints(None, context, names)

    assert hints["equal_contribution_names"] == {"siam u hussain", "mojan javaheripi"}


def test_joint_first_marker_on_second_author_includes_first_author():
    names = ["First Author", "Second Author", "Third Author"]
    context = make_context([
        "First Author",
        "Second Author∗",
        "Third Author",
        "ABSTRACT",
        "∗Joint first author",
    ])

    hints = extract_role_hints(None, context, names)
    authors = apply_author_roles(make_authors(names), hints)

    assert hints["equal_contribution_names"] == {"first author", "second author"}
    assert [author["co_first_author"] for author in authors] == [True, True, False]


def test_equal_contribution_among_later_authors_is_not_co_first():
    names = ["First Author", "Second Author", "Third Author", "Fourth Author"]
    context = make_context([
        "First Author",
        "Second Author∗",
        "Third Author∗",
        "Fourth Author",
        "ABSTRACT",
        "∗Equal Contribution",
    ])

    hints = extract_role_hints(None, context, names)
    authors = apply_author_roles(make_authors(names), hints)

    assert [author["first_author"] for author in authors] == [True, False, False, False]
    assert [author["co_first_author"] for author in authors] == [False, False, False, False]
    assert [author["equal_contribution"] for author in authors] == [False, True, True, False]
