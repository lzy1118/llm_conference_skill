import re

from author_metadata.config import clean_text, dedupe


def select_abstract_candidate(tei_abstract, pdf_abstract):
    tei_abstract = clean_text(tei_abstract)
    pdf_abstract = clean_text(pdf_abstract)
    decisions = []
    reviews = []
    if tei_abstract and not pdf_abstract:
        return tei_abstract, decisions, reviews
    if pdf_abstract and not tei_abstract:
        decisions.append({
            "action": "fill_abstract_from_pdf",
            "stage": "abstract_arbitration",
            "field": "abstract",
            "source": "pdfplumber_section_boundary",
        })
        return pdf_abstract, decisions, reviews
    if not tei_abstract:
        return "", decisions, reviews

    tei_key = _abstract_key(tei_abstract)
    pdf_key = _abstract_key(pdf_abstract)
    shorter, longer = sorted((tei_key, pdf_key), key=len)
    if shorter and (shorter in longer or len(shorter) / max(1, len(longer)) >= 0.92):
        return tei_abstract, decisions, reviews
    reviews.append({
        "code": "abstract_source_conflict",
        "stage": "abstract_arbitration",
        "field": "abstract",
        "tei_length": len(tei_abstract),
        "pdf_length": len(pdf_abstract),
    })
    return tei_abstract, decisions, reviews


def build_paper_relationship_summary(authors):
    first_authors = [author.get("name", "") for author in authors if author.get("first_author")]
    co_first_authors = [author.get("name", "") for author in authors if author.get("co_first_author")]
    corresponding_authors = [author.get("name", "") for author in authors if author.get("corresponding")]
    first_affiliations = dedupe([
        affiliation
        for author in authors
        if author.get("first_author")
        for affiliation in author.get("affiliations", [])
    ])
    participating_affiliations = dedupe([
        affiliation
        for author in authors
        for affiliation in author.get("affiliations", [])
    ])
    relations = [
        {
            "author": author.get("name", ""),
            "affiliation": affiliation,
            "source": author.get("affiliation_source", ""),
        }
        for author in authors
        for affiliation in author.get("affiliations", [])
    ]
    return {
        "first_authors": first_authors,
        "co_first_authors": co_first_authors,
        "corresponding_authors": corresponding_authors,
        "first_affiliations": first_affiliations,
        "first_affiliation": first_affiliations[0] if first_affiliations else "",
        "participating_affiliations": participating_affiliations,
        "author_affiliation_relations": relations,
    }


def _abstract_key(text):
    return re.sub(r"\W+", "", clean_text(text).lower(), flags=re.UNICODE)
