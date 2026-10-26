from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import security_affiliation_sources as sources
from bs4 import BeautifulSoup


def test_ccs_missing_semicolon_is_recovered_between_authors():
    text = (
        "Shuichi Katsumata (AIST); Takahiro Matsuda (AIST); "
        "Wataru Nakamura (Hitachi, Ltd.) Kazuma Ohara (AIST); "
        "Kenta Takahashi (Hitachi, Ltd.);"
    )

    authors, rows = sources.parse_ccs_row_author_text(text)

    assert authors == [
        "Shuichi Katsumata",
        "Takahiro Matsuda",
        "Wataru Nakamura",
        "Kazuma Ohara",
        "Kenta Takahashi",
    ]
    assert rows[2]["affiliations"] == ["Hitachi, Ltd."]
    assert rows[3]["affiliations"] == ["AIST"]


def test_ccs_nickname_parentheses_are_not_split_as_author_separator():
    text = (
        "Suibin Sun (Shanghai Jiao Tong University); "
        "Minhui (Jason) Xue (The University of Adelaide); "
        "Bin (Benjamin) Zhu (Microsoft Research Asia)"
    )

    repaired, repair_count = sources.repair_ccs_missing_author_separators(text)
    authors, rows = sources.parse_ccs_row_author_text(text)

    assert repaired == text
    assert repair_count == 0
    assert authors == ["Suibin Sun", "Minhui (Jason) Xue", "Bin (Benjamin) Zhu"]
    assert rows[1]["affiliations"] == ["The University of Adelaide"]


def test_ccs_valid_semicolon_separated_rows_remain_unchanged():
    text = "Ivan De Oliveira Nunes (UC Irvine); Gene Tsudik (UC Irvine)"

    repaired, repair_count = sources.repair_ccs_missing_author_separators(text)

    assert repaired == text
    assert repair_count == 0


def test_ccs_2023_xml_profiles_are_parsed(monkeypatch):
    payloads = {
        "accepted_papers.xml": """<papers><paper><id>p1</id><title>XML Paper</title><authors>a1,a2</authors></paper></papers>""",
        "author_profiles.xml": """<authors><author><id>a1</id><name>First Author</name><institutes>i1</institutes></author><author><id>a2</id><name>Second Author</name><institutes>i1,i2</institutes></author></authors>""",
        "institute_profiles.xml": """<institutes><institute><id>i1</id><name>Example University</name></institute><institute><id>i2</id><name>Example Lab</name></institute></institutes>""",
    }

    def fake_fetch(url, timeout=30):
        return payloads[url.rsplit("/", 1)[-1]]

    monkeypatch.setattr(sources, "fetch_text", fake_fetch)
    entries = sources.fetch_ccs_xml_profile_official_entries()

    assert len(entries) == 1
    assert entries[0]["authors"] == ["First Author", "Second Author"]
    assert entries[0]["official_affiliations"] == [
        {"name": "First Author", "affiliations": ["Example University"]},
        {"name": "Second Author", "affiliations": ["Example University", "Example Lab"]},
    ]


def test_ieee_author_line_is_kept_when_dom_omits_affiliation():
    item = BeautifulSoup(
        """
        <div class="list-group-item">
          <b>Example Paper</b>
          <div class="collapse authorlist">
            Alice Smith, Bob Jones<br />
          </div>
        </div>
        """,
        "html.parser",
    ).select_one("div.list-group-item")

    assert sources.parse_ieee_official_author_affiliations(item) == []
    assert sources.parse_ieee_official_authors(item) == ["Alice Smith", "Bob Jones"]
