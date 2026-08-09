import os
import re
import xml.etree.ElementTree as ET

from author_metadata.config import NS, clean_text, dedupe, is_noise_text, strip_marker


def parse_tei(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    return {
        "root": root,
        "title": extract_title(root),
        "year": extract_year(root, os.path.basename(xml_path)),
        "abstract": extract_abstract(root),
        "authors": extract_authors(root),
    }


def get_node_text(node):
    if node is None:
        return ""
    return clean_text(" ".join(node.itertext()))


def extract_year(root, filename=""):
    for path in [
        ".//tei:teiHeader//tei:sourceDesc//tei:monogr//tei:imprint/tei:date[@type='published']",
        ".//tei:teiHeader//tei:sourceDesc//tei:imprint/tei:date[@type='published']",
        ".//tei:teiHeader//tei:sourceDesc//tei:monogr//tei:date[@type='published']",
    ]:
        node = root.find(path, NS)
        if node is not None:
            when = node.attrib.get("when", "")
            if when and re.match(r"(19|20)\d{2}", when):
                return when[:4]
            text = get_node_text(node)
            match = re.search(r"(19|20)\d{2}", text)
            if match:
                return match.group()

    for note in root.findall(".//tei:teiHeader//tei:sourceDesc//tei:biblStruct//tei:note", NS):
        text = get_node_text(note)
        if is_noise_text(text):
            continue
        match = re.search(r"(19|20)\d{2}", text)
        if match:
            return match.group()

    if filename:
        match = re.search(r"[_\s\-]((?:19|20)\d{2})[_\s\-]", filename)
        if match:
            return match.group(1)
        match = re.search(r"((?:19|20)\d{2})\s*$", os.path.splitext(filename)[0])
        if match:
            return match.group(1)
    return ""


_TITLE_NOISE_PREFIXES = [
    r"(?:Open\s+access\s+to\s+)?(?:the\s+)?Proceedings\s+of\s+the\s+\d+\w*\s+\w+.*?(?:is\s+sponsored\s+by|are\s+published\s+by)\s+\w+[\.\s]+",
    r"(?:Open\s+access\s+.*?)",
]


def _clean_title(text):
    for pattern in _TITLE_NOISE_PREFIXES:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            cleaned = text[match.end():].strip()
            if len(cleaned) >= 10:
                return cleaned
    return text


def extract_title(root):
    paths = [
        ".//tei:teiHeader//tei:sourceDesc//tei:biblStruct//tei:analytic/tei:title[@level='a']",
        ".//tei:teiHeader//tei:titleStmt/tei:title[@level='a']",
        ".//tei:teiHeader//tei:titleStmt/tei:title",
    ]
    for path in paths:
        node = root.find(path, NS)
        text = get_node_text(node)
        if text and not is_noise_text(text):
            return _clean_title(text)
    return ""


def extract_abstract(root):
    node = root.find(".//tei:teiHeader//tei:profileDesc/tei:abstract", NS)
    return get_node_text(node)


def extract_author_name(author):
    pers = author.find("tei:persName", NS)
    if pers is None:
        return ""
    forenames = [
        get_node_text(node)
        for node in pers.findall("tei:forename", NS)
        if get_node_text(node)
    ]
    surname = get_node_text(pers.find("tei:surname", NS))
    name = clean_text(" ".join(forenames + ([surname] if surname else [])))
    name = re.sub(r"^[•*†‡§¶#]+\s*", "", name).strip()
    name = name.replace("¨", "")
    return clean_text(name)


def extract_author_email(author):
    email_node = author.find("tei:email", NS)
    return get_node_text(email_node) if email_node is not None else ""


def extract_author_orcid(author):
    """Extract only an explicit ORCID attached to this TEI author node."""
    values = []
    for node in author.findall(".//tei:idno", NS):
        if node.attrib.get("type", "").casefold() == "orcid":
            values.append(get_node_text(node))
    for node in author.findall(".//tei:ptr", NS) + author.findall(".//tei:ref", NS):
        target = node.attrib.get("target", "")
        if "orcid.org/" in target.casefold():
            values.append(target)
    for value in values:
        match = re.search(r"(?:orcid\.org/)?(\d{4}-\d{4}-\d{4}-[\dX]{4})", value, re.I)
        if match:
            return f"https://orcid.org/{match.group(1).upper()}"
    return ""


def _clean_addr_part(text):
    text = clean_text(text)
    if not text:
        return ""
    text = re.sub(r"\{[^}]*", "", text).strip()
    if not text:
        return ""
    if len(text) <= 4 and not text[0].isupper():
        return ""
    return text


def _clean_org_name(text):
    return re.sub(r"^with\s+", "", clean_text(text), flags=re.IGNORECASE)


def _clean_affiliation_text(text):
    text = clean_text(text)
    text = re.sub(r"[{}]", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[§‡†¶*#]+", "", text)
    text = clean_text(text)
    if ";" in text:
        parts = [part.strip() for part in text.split(";") if part.strip()]
        if len(parts) >= 2:
            text = parts[0]
    if len(text) > 200:
        match = re.search(
            r"(?<=\w)\s+(?=University|Institute|College|Department|School|Laboratory|Center|Centre|Academy)\b",
            text,
        )
        if match and match.start() > 30:
            text = text[:match.start()]
    return clean_text(text)


def extract_author_affiliations(author):
    affiliations = []
    for aff in author.findall("tei:affiliation", NS):
        org_names = dedupe([
            _clean_org_name(get_node_text(org))
            for org in aff.findall(".//tei:orgName", NS)
            if get_node_text(org) and not is_noise_text(get_node_text(org))
        ])
        if not org_names:
            org_names = dedupe([
                _clean_org_name(get_node_text(addr))
                for addr in aff.findall(".//tei:addrLine", NS)
                if get_node_text(addr) and not is_noise_text(get_node_text(addr))
            ])
        settlement = _clean_addr_part(get_node_text(aff.find(".//tei:settlement", NS)))
        region = _clean_addr_part(get_node_text(aff.find(".//tei:region", NS)))
        country = get_node_text(aff.find(".//tei:country", NS))
        parts = org_names + [item for item in [settlement, region, country] if item]
        aff_text = _clean_affiliation_text(strip_marker(", ".join(parts)))
        if aff_text and not is_noise_text(aff_text):
            affiliations.append(aff_text)
    return dedupe(affiliations)


def extract_authors(root):
    result = []
    author_nodes = root.findall(".//tei:teiHeader//tei:sourceDesc//tei:biblStruct/tei:analytic/tei:author", NS)
    for index, author in enumerate(author_nodes):
        name = extract_author_name(author)
        affiliations = extract_author_affiliations(author)
        result.append({
            "order": len(result),
            "name": name,
            "email": extract_author_email(author),
            "orcid": extract_author_orcid(author),
            "affiliations": affiliations,
            "affiliation_source": "author_node" if affiliations else "empty",
            "_source_index": index,
        })
    return result
