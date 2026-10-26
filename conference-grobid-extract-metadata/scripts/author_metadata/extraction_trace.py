import copy
import re
import unicodedata

from author_metadata.config import clean_text, dedupe
from author_metadata.author_validation import is_org_name
from author_metadata.pdf_context import extract_abstract_from_pdf_context


def author_key(name):
    text = unicodedata.normalize("NFKD", clean_text(name)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def clone_authors(authors):
    return copy.deepcopy(authors or [])


def _field_value(author, field):
    value = author.get(field, [] if field == "affiliations" else "")
    return dedupe(value) if field == "affiliations" else clean_text(value)


def _comparison_value(value, field):
    if field == "affiliations":
        return tuple(sorted(author_key(item) for item in value))
    return clean_text(value).lower()


DIRECT_AFFILIATION_SOURCES = {
    "author_node",
    "pdf_footnote",
    "usenix_pdf",
    "ccs_pdf",
    "ieee_pdf",
    "ndss_pdf",
    "pdf_layout",
}

DIRECT_AFFILIATION_OVERRIDE_SOURCES = {"lncs_pdf_numbered"}


def _affiliation_restore_rejection(author, affiliation, all_authors):
    source = author.get("affiliation_source", "empty")
    if source not in DIRECT_AFFILIATION_SOURCES:
        return f"weak_source:{source}"
    affiliation_key = author_key(" ".join(affiliation))
    current_key = author_key(author.get("name", ""))
    for other in all_authors or []:
        other_key = author_key(other.get("name", ""))
        if other_key and other_key != current_key and len(other_key) >= 6 and other_key in affiliation_key:
            return f"contains_other_author:{other.get('name', '')}"
    return ""


def preserve_nonempty_author_fields(baseline, proposed, stage):
    """Prevent a later stage from silently turning reliable fields into blanks."""
    baseline_by_name = {
        author_key(author.get("name", "")): author
        for author in baseline or []
        if author_key(author.get("name", ""))
    }
    decisions = []
    reviews = []

    for author in proposed or []:
        key = author_key(author.get("name", ""))
        previous = baseline_by_name.get(key)
        if not previous:
            continue
        for field in ("affiliations", "email", "orcid"):
            old_value = _field_value(previous, field)
            new_value = _field_value(author, field)
            if old_value and not new_value:
                rejection = ""
                if field == "affiliations":
                    rejection = _affiliation_restore_rejection(previous, old_value, baseline)
                if rejection:
                    decisions.append({
                        "action": "reject_restore",
                        "stage": stage,
                        "author": author.get("name", ""),
                        "field": field,
                        "rejected_value": old_value,
                        "reason": rejection,
                    })
                    reviews.append({
                        "code": "nonempty_field_dropped_with_reason",
                        "stage": stage,
                        "field": field,
                        "author": author.get("name", ""),
                        "baseline": old_value,
                        "reason": rejection,
                    })
                    continue
                author[field] = copy.deepcopy(old_value)
                if field == "affiliations":
                    author["affiliation_source"] = previous.get("affiliation_source", "preserved")
                decisions.append({
                    "action": "restore_nonempty_field",
                    "stage": stage,
                    "author": author.get("name", ""),
                    "field": field,
                    "restored_value": old_value,
                    "reason": "later_stage_produced_blank",
                })
            elif (
                old_value
                and new_value
                and _comparison_value(old_value, field) != _comparison_value(new_value, field)
            ):
                if (
                    field == "affiliations"
                    and author.get("affiliation_source") in DIRECT_AFFILIATION_OVERRIDE_SOURCES
                ):
                    decisions.append({
                        "action": "replace_nonempty_field_from_direct_pdf",
                        "stage": stage,
                        "author": author.get("name", ""),
                        "field": field,
                        "replaced_value": old_value,
                        "selected_value": new_value,
                        "source": author.get("affiliation_source"),
                    })
                    continue
                reviews.append({
                    "code": "author_field_conflict",
                    "stage": stage,
                    "field": field,
                    "author": author.get("name", ""),
                    "baseline": old_value,
                    "selected": new_value,
                })
    return proposed, decisions, reviews


def build_evidence(raw_metadata, pdf_context):
    evidence = []
    if raw_metadata.get("title"):
        evidence.append({
            "evidence_id": "tei:title",
            "source": "grobid_tei",
            "field": "title",
            "raw_text": raw_metadata["title"],
        })
    if raw_metadata.get("year"):
        evidence.append({
            "evidence_id": "tei:year",
            "source": "grobid_tei",
            "field": "year",
            "raw_text": raw_metadata["year"],
        })
    if raw_metadata.get("abstract"):
        evidence.append({
            "evidence_id": "tei:abstract",
            "source": "grobid_tei",
            "field": "abstract",
            "raw_text": raw_metadata["abstract"],
        })
    for index, author in enumerate(raw_metadata.get("authors", [])):
        prefix = f"tei:author:{index}"
        evidence.append({
            "evidence_id": prefix,
            "source": "grobid_tei",
            "field": "author",
            "raw_text": author.get("name", ""),
            "order": index,
            "email": author.get("email", ""),
            "affiliations": list(author.get("affiliations", [])),
        })
    for index, line in enumerate(pdf_context.preabstract_lines or []):
        evidence.append({
            "evidence_id": f"pdf:page1:preabstract:{index}",
            "source": "pdf_text",
            "field": "header_line",
            "page": 1,
            "raw_text": line,
        })
    for block in (pdf_context.page_blocks or {}).get(1, []):
        evidence.append({
            "evidence_id": block.get("block_id", f"pdf:page1:block:{len(evidence)}"),
            "source": "pdf_layout",
            "field": "page_block",
            "page": 1,
            "bbox": block.get("bbox", []),
            "font_size": block.get("font_size", 0),
            "raw_text": block.get("raw_text", ""),
            "extractor": block.get("extractor", "pdf_layout"),
        })
    pdf_abstract = extract_abstract_from_pdf_context(pdf_context)
    if pdf_abstract:
        evidence.append({
            "evidence_id": "pdfplumber:abstract",
            "source": "pdf_layout",
            "field": "abstract",
            "raw_text": pdf_abstract,
            "extractor": "pdfplumber_section_boundary",
        })
    for link in pdf_context.pdf_links or []:
        evidence.append({
            "evidence_id": link.get("link_id", f"pypdf:link:{len(evidence)}"),
            "source": "pypdf_link",
            "field": "link",
            "page": link.get("page"),
            "bbox": link.get("bbox", []),
            "raw_text": link.get("uri", ""),
            "contents": link.get("contents", ""),
        })
    if pdf_context.document_info:
        evidence.append({
            "evidence_id": "pypdf:document_info",
            "source": "pdf_document_info",
            "field": "document_info",
            "value": dict(pdf_context.document_info),
        })
    evidence.append({
        "evidence_id": "pdf:extractor_status",
        "source": "runtime",
        "field": "extractor_status",
        "value": dict(pdf_context.extractor_status or {}),
    })
    return evidence


def build_candidates(raw_metadata, repaired_metadata, layout_analysis=None, pdf_abstract=""):
    result = {
        "title": [
            {"source": "grobid_tei", "value": raw_metadata.get("title", "")},
            {"source": "selected", "value": repaired_metadata.get("title", "")},
        ],
        "year": [
            {"source": "grobid_tei", "value": raw_metadata.get("year", "")},
            {"source": "selected", "value": repaired_metadata.get("year", "")},
        ],
        "abstract": [
            {"source": "grobid_tei", "value": raw_metadata.get("abstract", "")},
            {"source": "pdfplumber", "value": clean_text(pdf_abstract)},
            {"source": "selected", "value": repaired_metadata.get("abstract", "")},
        ],
        "authors": {
            "grobid_tei": clone_authors(raw_metadata.get("authors", [])),
            "selected": clone_authors(repaired_metadata.get("authors", [])),
        },
    }
    if layout_analysis:
        result["layout_relations"] = copy.deepcopy(layout_analysis)
    return result


def validate_metadata(raw_metadata, repaired_metadata, decisions=None, reviews=None):
    issues = list(reviews or [])
    raw_authors = [
        author
        for author in raw_metadata.get("authors", [])
        if clean_text(author.get("name", ""))
        and not is_org_name(clean_text(author.get("name", "")))
        and len(clean_text(author.get("name", "")).split()) >= 2
    ]
    authors = repaired_metadata.get("authors", [])

    if not repaired_metadata.get("title"):
        issues.append({"code": "missing_title", "field": "title"})
    if not repaired_metadata.get("abstract"):
        issues.append({"code": "missing_abstract", "field": "abstract"})
    if not authors:
        issues.append({"code": "missing_authors", "field": "authors"})
    layout_rebuild_accepted = any(
        decision.get("action") == "rebuild_author_list_from_pdf_layout"
        for decision in decisions or []
    )
    if raw_authors and len(raw_authors) != len(authors) and not layout_rebuild_accepted:
        issues.append({
            "code": "author_count_changed",
            "field": "authors",
            "raw_count": len(raw_authors),
            "selected_count": len(authors),
        })

    for author in authors:
        name = clean_text(author.get("name", ""))
        if len(name.split()) > 8 or len(name) > 100:
            issues.append({
                "code": "suspicious_author_name",
                "field": "author",
                "author": name,
            })
    for decision in decisions or []:
        if decision["action"] != "restore_nonempty_field":
            continue
        issues.append({
            "code": "field_restored_after_loss",
            "field": decision["field"],
            "author": decision["author"],
            "stage": decision["stage"],
        })
    return issues
