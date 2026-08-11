"""Conference-independent PDF header layout classification.

The classifier is deliberately field-oriented: a paper may use a multi-line
title, a column matrix for authors, numbered affiliations, and a shared email
domain at the same time.  It only routes parsers and records evidence; final
field replacement remains guarded by the relation and arbitration layers.
"""

import re
from collections import Counter

from author_metadata.config import EMAIL_RE, HEADER_NOISE_MARKERS, clean_text, looks_like_org


ROLE_RE = re.compile(
    r"\b(?:corresponding authors?|correspondence|contributed equally|equal contribution|"
    r"co[- ]?first|shared first authorship|first (?:two|three|four|five|\d+) authors?)\b",
    re.IGNORECASE,
)
CORRESPONDING_RE = re.compile(r"\b(?:corresponding authors?|correspondence)\b", re.IGNORECASE)
EQUAL_RE = re.compile(
    r"\b(?:contributed equally|equal contribution|co[- ]?first|shared first authorship)\b",
    re.IGNORECASE,
)
MARKER_RE = re.compile(r"(?:[\u00b9\u00b2\u00b3\u2070-\u2079*\u2020\u2021\u00b6\u2709]|\(B\))")
PLAIN_AUTHOR_NUMBER_RE = re.compile(r"(?<=[A-Za-z\u00c0-\u024f])[1-9](?:\s*[,;]|\s*$)")
NUMBERED_AFFILIATION_RE = re.compile(
    r"^\s*(?:[1-9]\d*|[\u00b9\u00b2\u00b3\u2070-\u2079])(?:[.)\s]|$)"
)
BRACED_EMAIL_RE = re.compile(r"\{[^{}]+(?:,|;)[^{}]+\}[^\s@]*@|\{[^{}]+@[^{}]+\}[^\s]+", re.I)
ORG_LEVEL_RE = re.compile(
    r"\b(?:department|school|faculty|college|laboratory|lab|centre|center)\b.*"
    r"\b(?:university|institute|academy|company|corporation|research)\b",
    re.IGNORECASE,
)
LOCATION_ONLY_RE = re.compile(
    r"^(?:[A-Z][\w.' -]+,\s*)?(?:USA|United States|UK|China|Germany|France|"
    r"Switzerland|Australia|Singapore|Korea|Canada|Italy|Spain|Japan|Hong Kong)$",
    re.IGNORECASE,
)


def _key(text):
    return re.sub(r"[^a-z0-9]+", "", clean_text(text).casefold())


def _block_ids_for_text(pdf_context, text, pages=(1, 2)):
    target = _key(text)
    if not target:
        return []
    result = []
    for page in pages:
        for block in (pdf_context.page_blocks or {}).get(page, []):
            candidate = _key(block.get("raw_text", ""))
            if target in candidate or candidate in target and len(candidate) >= 5:
                result.append(block.get("block_id", ""))
    return [item for item in result if item]


def _candidate(label, score, evidence_ids=None, reasons=None, parser=""):
    return {
        "type": label,
        "score": round(max(0.0, min(1.0, score)), 3),
        "evidence_ids": list(dict.fromkeys(evidence_ids or [])),
        "reasons": list(dict.fromkeys(reasons or [])),
        "parser": parser or label,
    }


def _select(candidates, minimum=0.55):
    ranked = sorted(candidates, key=lambda item: (-item["score"], item["type"]))
    selected = ranked[0] if ranked and ranked[0]["score"] >= minimum else _candidate(
        "unclassified", 0.0, reasons=["no_candidate_above_threshold"], parser="tei_direct"
    )
    margin = selected["score"] - (ranked[1]["score"] if len(ranked) > 1 else 0.0)
    return {
        "selected_type": selected["type"],
        "confidence": selected["score"],
        "parser": selected["parser"],
        "evidence_ids": selected["evidence_ids"],
        "reasons": selected["reasons"],
        "margin": round(margin, 3),
        "candidates": ranked,
    }


def _title_candidates(pdf_context, authors):
    title_lines = [clean_text(line) for line in pdf_context.title_lines if clean_text(line)]
    first_lines = [clean_text(line) for line in pdf_context.first_page_lines[:12] if clean_text(line)]
    title = clean_text(" ".join(title_lines[:3]))
    evidence = [item for line in title_lines[:3] for item in _block_ids_for_text(pdf_context, line, (1,))]
    result = []
    if len(title_lines) == 1:
        result.append(_candidate("single_line_title", 0.82, evidence, ["one_title_line"], "title_lines"))
    elif len(title_lines) >= 2:
        score = 0.91 if len(title_lines) <= 3 else 0.72
        result.append(_candidate("multi_line_title", score, evidence, [f"title_line_count:{len(title_lines)}"], "merge_title_lines"))
    if title and re.search(r"[:\u2014\u2013]\s*\S", title):
        result.append(_candidate("title_with_subtitle", 0.86, evidence, ["subtitle_separator"], "preserve_subtitle"))
    contaminated = [author.get("name", "") for author in authors if len(_key(author.get("name", ""))) >= 6 and _key(author.get("name", "")) in _key(title)]
    if contaminated:
        result.append(_candidate("title_author_joined", 0.96, evidence, ["recognized_author_inside_title"], "split_title_before_author"))
    header_lines = [line for line in first_lines if any(marker in line.casefold() for marker in HEADER_NOISE_MARKERS)]
    if header_lines and title_lines:
        header_evidence = [item for line in header_lines for item in _block_ids_for_text(pdf_context, line, (1,))]
        result.append(_candidate("title_after_publication_header", 0.92, header_evidence + evidence, ["publication_header_precedes_title"], "skip_header_then_title"))
    page1_author_hits = sum(bool(_block_ids_for_text(pdf_context, author.get("name", ""), (1,))) for author in authors)
    page2_author_hits = sum(bool(_block_ids_for_text(pdf_context, author.get("name", ""), (2,))) for author in authors)
    if authors and page2_author_hits > page1_author_hits and page2_author_hits >= max(1, len(authors) // 2):
        page2_ids = [item for author in authors for item in _block_ids_for_text(pdf_context, author.get("name", ""), (2,))]
        result.append(_candidate("title_on_later_content_page", 0.88, page2_ids, ["page2_has_more_author_anchors"], "compare_first_two_pages"))
    return result or [_candidate("unclassified", 0.0, parser="tei_direct")]


def _author_candidates(pdf_context, authors, relation_analysis):
    result = []
    layout_type = relation_analysis.get("layout_type", "unclassified")
    relation_ids = [
        item
        for relation in relation_analysis.get("relations", [])
        for item in [relation.get("author_block_id", "")] + relation.get("affiliation_block_ids", [])
        if item
    ]
    if layout_type == "aligned_author_affiliation_rows":
        result.append(_candidate("column_aligned_matrix", 0.99, relation_ids, ["complete_aligned_rows"], "column_matrix"))
    elif layout_type == "author_card_grid":
        score = 0.96 if relation_analysis.get("auto_eligible") else 0.78
        result.append(_candidate("author_cards", score, relation_ids, ["local_author_affiliation_relations"], "author_card"))

    author_lines = [clean_text(line) for line in pdf_context.author_lines if clean_text(line)]
    if len(author_lines) == 1 and len(authors) >= 2:
        result.append(_candidate("single_line_author_list", 0.82, _block_ids_for_text(pdf_context, author_lines[0], (1,)), ["one_author_line"], "inline_authors"))
    elif len(author_lines) >= 2:
        ids = [item for line in author_lines for item in _block_ids_for_text(pdf_context, line, (1,))]
        result.append(_candidate("multi_line_author_list", 0.76, ids, [f"author_line_count:{len(author_lines)}"], "reading_order_authors"))

    affiliation_lines = [clean_text(line) for line in pdf_context.affiliation_lines if clean_text(line)]
    if len(authors) >= 2 and len(affiliation_lines) == 1 and not relation_analysis.get("relations"):
        result.append(_candidate(
            "all_authors_shared_affiliation",
            0.84,
            _block_ids_for_text(pdf_context, affiliation_lines[0], (1,)),
            ["multiple_authors_and_one_unambiguous_affiliation_block"],
            "shared_affiliation",
        ))
    if len(author_lines) >= 2 and len(affiliation_lines) >= 2:
        interleaved_transitions = 0
        previous = ""
        for line in pdf_context.preabstract_lines:
            current = "author" if line in author_lines else "affiliation" if line in affiliation_lines else ""
            if current and previous and current != previous:
                interleaved_transitions += 1
            if current:
                previous = current
        if interleaved_transitions >= 3:
            result.append(_candidate(
                "grouped_authors_with_local_affiliations",
                0.86,
                reasons=[f"author_affiliation_transitions:{interleaved_transitions}"],
                parser="grouped_blocks",
            ))

    preabstract = [clean_text(line) for line in pdf_context.preabstract_lines if clean_text(line)]
    anchored_author_lines = [
        line for line in preabstract
        if any(_key(author.get("name", "")) in _key(line) for author in authors)
    ]
    author_marker_hits = sum(
        bool(MARKER_RE.search(line) or PLAIN_AUTHOR_NUMBER_RE.search(line))
        for line in anchored_author_lines
    )
    numbered_affiliations = [line for line in preabstract if NUMBERED_AFFILIATION_RE.match(line) and looks_like_org(line)]
    if author_marker_hits and numbered_affiliations:
        ids = [item for line in numbered_affiliations for item in _block_ids_for_text(pdf_context, line, (1,))]
        result.append(_candidate("authors_with_numbered_affiliations", 0.94, ids, ["author_markers_and_numbered_organizations"], "numbered_reference"))
    if any(ROLE_RE.search(line) for line in preabstract) and author_marker_hits:
        result.append(_candidate("authors_with_symbol_footnotes", 0.88, reasons=["author_markers_and_role_notes"], parser="symbol_footnote"))

    page1_hits = sum(bool(_block_ids_for_text(pdf_context, author.get("name", ""), (1,))) for author in authors)
    page2_hits = sum(bool(_block_ids_for_text(pdf_context, author.get("name", ""), (2,))) for author in authors)
    if authors and page1_hits and page2_hits:
        result.append(_candidate("cross_page_author_information", 0.84, reasons=["author_anchors_on_pages_1_and_2"], parser="cross_page_merge"))

    x_positions = []
    y_positions = []
    for node in relation_analysis.get("author_nodes", []):
        for block in (pdf_context.page_blocks or {}).get(1, []):
            if block.get("block_id") == node.get("block_id"):
                x_positions.append(round(float(block.get("x", 0)) / 25) * 25)
                y_positions.append(round(float(block.get("y", 0)) / 3) * 3)
    if len(x_positions) >= 2 and len(set(x_positions)) == 1 and len(set(y_positions)) >= 2:
        result.append(_candidate("vertical_author_stacks", 0.81, relation_ids, ["shared_x_separate_y"], "vertical_stack"))
    return result or [_candidate("tei_stable", 0.58, reasons=["no_distinct_pdf_author_layout"], parser="tei_direct")]


def _affiliation_candidates(pdf_context, authors, relation_analysis):
    lines = [clean_text(line) for line in pdf_context.affiliation_lines if clean_text(line)]
    preabstract = [clean_text(line) for line in pdf_context.preabstract_lines if clean_text(line)]
    result = []
    numbered = [line for line in preabstract if NUMBERED_AFFILIATION_RE.match(line) and looks_like_org(line)]
    if numbered:
        ids = [item for line in numbered for item in _block_ids_for_text(pdf_context, line, (1,))]
        result.append(_candidate("numbered_or_symbol_affiliation_list", 0.95, ids, [f"numbered_affiliation_count:{len(numbered)}"], "numbered_reference"))
    relations = relation_analysis.get("relations", [])
    if relations:
        relation_types = Counter(item.get("relation_type", "") for item in relations)
        label = "local_card_or_matrix_affiliations"
        score = 0.97 if relation_analysis.get("auto_eligible") else 0.78
        result.append(_candidate(label, score, [item for relation in relations for item in relation.get("affiliation_block_ids", [])], [f"relation_count:{len(relations)}", f"relation_types:{','.join(sorted(relation_types))}"], "layout_relations"))
    unique_author_affiliations = {
        _key(affiliation)
        for author in authors
        for affiliation in author.get("affiliations", [])
        if _key(affiliation)
    }
    if len(authors) >= 2 and len(unique_author_affiliations) == 1:
        result.append(_candidate("shared_affiliation", 0.82, reasons=["same_single_tei_affiliation_across_authors"], parser="shared_affiliation"))
    if any(len(author.get("affiliations", [])) >= 2 for author in authors):
        result.append(_candidate(
            "multiple_affiliations_per_author",
            0.88,
            reasons=["tei_author_has_multiple_affiliation_nodes"],
            parser="multi_affiliation_relations",
        ))
    if any(ORG_LEVEL_RE.search(line) for line in lines):
        result.append(_candidate("department_parent_institution_hierarchy", 0.84, reasons=["subunit_and_parent_terms"], parser="hierarchical_affiliation"))
    if len(lines) >= 2 and any(line.casefold().endswith((" of", " for", " and")) for line in lines[:-1]):
        result.append(_candidate("multi_line_affiliation_address", 0.9, reasons=["continuation_word_at_line_end"], parser="merge_affiliation_lines"))
    fragmented = [
        line for line in lines
        if re.search(r"\b(?:university|institute|science|technology|republic|of|for|and)\s*[,;]\s*$", line, re.I)
    ]
    if fragmented:
        result.append(_candidate(
            "fragmented_affiliation_text",
            0.91,
            reasons=[f"fragment_count:{len(fragmented)}"],
            parser="reconstruct_affiliation_fragments",
        ))
    if lines and all(LOCATION_ONLY_RE.match(line) for line in lines):
        result.append(_candidate("location_only_candidates", 0.93, reasons=["no_organization_line"], parser="location_candidate_only"))
    elif len(lines) == 1:
        result.append(_candidate("single_line_affiliation", 0.72, _block_ids_for_text(pdf_context, lines[0], (1,)), ["one_affiliation_line"], "single_affiliation_line"))
    footnote_lines = [line for line in preabstract if re.search(r"\b(?:is with|affiliated with|was with|currently with|now at|during this work)\b", line, re.I)]
    if footnote_lines:
        result.append(_candidate("footnote_or_margin_affiliations", 0.94, reasons=["explicit_author_affiliation_phrase"], parser="affiliation_footnote"))
    return result or [_candidate("unclassified", 0.0, parser="tei_direct")]


def _email_candidates(pdf_context, authors, relation_analysis):
    lines = [clean_text(line) for line in pdf_context.email_lines if clean_text(line)]
    preabstract = [clean_text(line) for line in pdf_context.preabstract_lines if clean_text(line)]
    all_email_lines = list(dict.fromkeys(lines + [line for line in preabstract if "@" in line]))
    result = []
    braced = [line for line in all_email_lines if BRACED_EMAIL_RE.search(line)]
    if braced:
        result.append(_candidate("braced_shared_domain_emails", 0.97, reasons=["brace_group_email_syntax"], parser="expand_braced_email"))
    complete_emails = [email for line in all_email_lines for email in EMAIL_RE.findall(line)]
    if len(complete_emails) == 1:
        result.append(_candidate("single_complete_email", 0.75, reasons=["one_complete_email"], parser="single_email"))
    elif len(complete_emails) >= 2:
        result.append(_candidate("concentrated_complete_emails", 0.82, reasons=[f"email_count:{len(complete_emails)}"], parser="email_list"))
    relation_emails = [item for item in relation_analysis.get("relations", []) if item.get("email_raw")]
    if relation_emails:
        score = 0.96 if len(relation_emails) == len(authors) and authors else 0.79
        result.append(_candidate("card_or_matrix_emails", score, [item for relation in relation_emails for item in relation.get("email_block_ids", [])], [f"locally_linked_email_count:{len(relation_emails)}"], "layout_email_relation"))
    if any(CORRESPONDING_RE.search(line) and "@" in line for line in preabstract):
        result.append(_candidate("footnote_corresponding_email", 0.91, reasons=["corresponding_text_with_email"], parser="role_footnote_email"))
    if any("@" in line and not EMAIL_RE.search(line) for line in all_email_lines):
        result.append(_candidate("fragmented_email_text", 0.77, reasons=["at_sign_without_complete_email"], parser="reconstruct_email_fragments"))
    if complete_emails and authors and len(complete_emails) not in {1, len(authors)}:
        result.append(_candidate("unassigned_or_public_emails", 0.71, reasons=["email_author_count_not_closed"], parser="paper_level_email_candidates"))
    return result or [_candidate("no_email_detected", 0.9, reasons=["no_email_evidence"], parser="none")]


def _role_candidates(pdf_context):
    lines = [clean_text(line) for line in pdf_context.preabstract_lines if clean_text(line)]
    role_lines = [line for line in lines if ROLE_RE.search(line)]
    result = []
    corresponding = [line for line in role_lines if CORRESPONDING_RE.search(line)]
    equal = [line for line in role_lines if EQUAL_RE.search(line)]
    if corresponding:
        plural = any(re.search(r"corresponding authors\b", line, re.I) for line in corresponding)
        result.append(_candidate("multiple_corresponding_authors" if plural else "corresponding_author", 0.94, reasons=["explicit_corresponding_semantics"], parser="role_semantics"))
    if equal:
        cofirst = any(re.search(r"co[- ]?first|shared first|first (?:two|three|four|five|\d+) authors?", line, re.I) for line in equal)
        result.append(_candidate("co_first_authors" if cofirst else "equal_contribution", 0.93 if cofirst else 0.82, reasons=["explicit_equal_contribution_semantics"], parser="role_semantics"))
    if corresponding and equal and any(CORRESPONDING_RE.search(line) and EQUAL_RE.search(line) for line in role_lines):
        result.append(_candidate("mixed_role_footnote", 0.97, reasons=["multiple_role_semantics_in_one_line"], parser="split_role_footnote"))
    return result or [_candidate("first_author_only", 0.95, reasons=["no_explicit_additional_role"], parser="author_order")]


def classify_header_layout(pdf_context, authors, relation_analysis=None):
    """Return independent title/author/affiliation/email/role classifications."""
    relation_analysis = relation_analysis or {}
    dimensions = {
        "title": _select(_title_candidates(pdf_context, authors)),
        "author": _select(_author_candidates(pdf_context, authors, relation_analysis)),
        "affiliation": _select(_affiliation_candidates(pdf_context, authors, relation_analysis)),
        "email": _select(_email_candidates(pdf_context, authors, relation_analysis)),
        "role": _select(_role_candidates(pdf_context)),
    }
    review_reasons = []
    for field, classification in dimensions.items():
        if classification["selected_type"] == "unclassified":
            review_reasons.append({"code": "layout_dimension_unclassified", "stage": "layout_classification", "field": field})
        elif classification["confidence"] < 0.72 or classification["margin"] < 0.08:
            review_reasons.append({
                "code": "layout_classification_ambiguous",
                "stage": "layout_classification",
                "field": field,
                "selected_type": classification["selected_type"],
                "confidence": classification["confidence"],
                "margin": classification["margin"],
            })
    auto_routes = {
        field: value["parser"]
        for field, value in dimensions.items()
        if value["confidence"] >= 0.78 and value["margin"] >= 0.08
    }
    return {
        "schema_version": "1.0",
        "classifier": "general_pdf_header_rules",
        "conference_independent": True,
        "dimensions": dimensions,
        "auto_routes": auto_routes,
        "review_reasons": review_reasons,
    }
