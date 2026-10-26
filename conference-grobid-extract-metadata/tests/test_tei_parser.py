from author_metadata.tei_parser import parse_tei


def test_extracts_explicit_author_orcid_and_leaves_missing_blank(tmp_path) -> None:
    xml = tmp_path / "paper.tei.xml"
    xml.write_text(
        """<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader><fileDesc><sourceDesc>
        <biblStruct><analytic>
          <author><persName><forename>Alice</forename><surname>Smith</surname></persName>
            <idno type="ORCID">0000-0001-2345-6789</idno></author>
          <author><persName><forename>Bob</forename><surname>Jones</surname></persName></author>
        </analytic></biblStruct></sourceDesc></fileDesc></teiHeader></TEI>""",
        encoding="utf-8",
    )

    authors = parse_tei(xml)["authors"]

    assert authors[0]["orcid"] == "https://orcid.org/0000-0001-2345-6789"
    assert authors[1]["orcid"] == ""


def test_preserves_spaces_between_middle_initials_and_surname(tmp_path) -> None:
    xml = tmp_path / "initials.tei.xml"
    xml.write_text(
        """<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader><fileDesc><sourceDesc>
        <biblStruct><analytic><author><persName>
          <forename type="first">Harry</forename><forename type="middle">W H</forename>
          <surname>Wong</surname>
        </persName></author></analytic></biblStruct>
        </sourceDesc></fileDesc></teiHeader></TEI>""",
        encoding="utf-8",
    )

    authors = parse_tei(xml)["authors"]

    assert authors[0]["name"] == "Harry W H Wong"
