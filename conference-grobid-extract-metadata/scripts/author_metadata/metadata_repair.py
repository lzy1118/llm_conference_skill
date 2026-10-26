import re
from collections import Counter

from author_metadata.config import (
    clean_text,
    compact_alpha,
    compact_text,
    normalize_name,
)
from author_metadata.pdf_context import extract_abstract_from_pdf_context, extract_preabstract_text
from author_metadata.paper_fields import build_paper_relationship_summary, select_abstract_candidate
from author_metadata.role_linking import apply_author_roles, extract_role_hints, match_author_reference
from author_metadata.author_validation import is_abbreviated_duplicate, is_author_name_noise, is_org_name
# Compatibility re-export for existing tests/callers; new code imports this helper directly.
from author_metadata.affiliation_linking import (
    _clean_ccs_publication_location_noise,
    _has_numbered_pdf_affiliation_evidence,
    apply_default_and_symbol_affiliations,
    apply_email_domain_affiliations,
    assign_aligned_orphan_affiliations,
    compact_initial_sequence,
    dedupe_affiliations,
    extract_affiliation_text_fragment,
    extract_author_emails,
    extract_author_footnote_affiliations,
    extract_usenix_style_affiliations,
    looks_like_address_only_affiliation,
    match_email_token_to_author,
    merge_orphan_affiliation_chunks,
)
from author_metadata.layout_relations import (
    analyze_layout,
    apply_layout_affiliations,
    reconcile_authors_from_layout,
)
from author_metadata.extraction_trace import (
    build_candidates,
    build_evidence,
    clone_authors,
    preserve_nonempty_author_fields,
    validate_metadata,
)
# Compatibility re-export for existing callers; new code imports from author_order.
from author_metadata.author_order import get_export_author_rank


LAYOUT_CARD_CONFERENCES = {"ccs", "ndss"}


def _complete_layout_mapping(analysis, author_count, require_card_email=False):
    relations = analysis.get("relations", [])
    indexes = [relation.get("author_index") for relation in relations]
    return bool(
        analysis.get("auto_eligible")
        and len(relations) == author_count
        and len(set(indexes)) == author_count
        and set(indexes) == set(range(author_count))
        and all(relation.get("local_auto_eligible") for relation in relations)
        and (
            not require_card_email
            or all(
                relation.get("email_raw") and relation.get("email_block_ids")
                for relation in relations
            )
        )
    )


def repair_metadata(metadata, pdf_context, strategy=None, conference_name="", pdf_path=""):
    conference_key = (conference_name or "").strip().lower()
    raw_metadata = {
        "title": metadata.get("title", ""),
        "year": metadata.get("year", ""),
        "abstract": metadata.get("abstract", ""),
        "authors": clone_authors(metadata.get("authors", [])),
    }
    authors = metadata.get("authors", [])
    root = metadata.get("root")
    raw_title = metadata.get("title", "")
    author_names = [author["name"] for author in authors if author.get("name")]
    pdf_abstract = extract_abstract_from_pdf_context(pdf_context)
    abstract, abstract_decisions, abstract_reviews = select_abstract_candidate(
        metadata.get("abstract", ""),
        pdf_abstract,
    )

    pdf_footnote_affs = extract_author_footnote_affiliations(pdf_context, author_names)
    pdf_emails = extract_author_emails(pdf_context, author_names)
    usenix_affs = extract_usenix_style_affiliations(pdf_context, author_names)
    role_hints = extract_role_hints(
        root,
        pdf_context,
        author_names,
        {author["name"]: author.get("email", "") for author in authors if author.get("name")},
    )

    repaired_authors = []
    for source_index, raw_author in enumerate(authors):
        name = raw_author.get("name", "")
        if not name:
            continue
        if is_org_name(name) or is_author_name_noise(name):
            continue
        if not raw_author.get("email") and not raw_author.get("affiliations"):
            if not appears_in_preabstract_author_region(name, pdf_context):
                continue
        if is_abbreviated_duplicate(name, author_names):
            continue

        email = raw_author.get("email", "") or pdf_emails.get(normalize_name(name), "")
        affiliations = list(raw_author.get("affiliations", []))
        source = raw_author.get("affiliation_source", "empty")

        if not affiliations:
            pdf_aff = pdf_footnote_affs.get(normalize_name(name), "")
            if pdf_aff:
                affiliations = [pdf_aff]
                source = "pdf_footnote"
        if not affiliations:
            usenix_aff = usenix_affs.get(normalize_name(name), "")
            if usenix_aff:
                affiliations = [usenix_aff]
                source = "usenix_pdf"
        repaired_authors.append({
            "order": len(repaired_authors),
            "name": name,
            "email": email,
            "orcid": raw_author.get("orcid", ""),
            "affiliations": affiliations,
            "affiliation_source": source,
            "_source_index": source_index,
        })

    # GROBID sometimes emits an exact tail of N affiliation-only author nodes
    # after N real authors.  The closed N:N order is structural TEI evidence and
    # is independent of conference template.
    repaired_authors = assign_aligned_orphan_affiliations(repaired_authors, authors)
    if conference_key != "ccs":
        repaired_authors = merge_orphan_affiliation_chunks(
            repaired_authors,
            authors,
            pdf_context=(
                pdf_context
                if conference_key in {"crypto", "eurocrypt", "asiacrypt"}
                else None
            ),
        )
        # Do not infer affiliations from a same-surname neighbour or majority
        # consensus.  These are useful review candidates but not publication
        # evidence for an author-affiliation edge.

    for author in repaired_authors:
        author.pop("_source_index", None)
    repaired_authors = apply_author_roles(repaired_authors, role_hints)
    before_strategy = clone_authors(repaired_authors)
    repaired_authors = apply_conference_author_strategy(
        strategy,
        repaired_authors,
        title=raw_title,
        pdf_context=pdf_context,
        pdf_path=pdf_path,
        conference_name=conference_name,
    )
    repaired_authors, author_list_decisions, author_list_reviews = protect_reliable_author_list(
        before_strategy,
        repaired_authors,
        stage="conference_strategy",
    )
    repaired_authors, strategy_decisions, strategy_reviews = preserve_nonempty_author_fields(
        before_strategy,
        repaired_authors,
        stage="conference_strategy",
    )
    repaired_authors, author_artifact_decisions = clean_post_strategy_author_artifacts(
        repaired_authors,
    )
    repaired_authors, cleanup_guard_decisions, cleanup_guard_reviews = protect_reliable_author_list(
        before_strategy,
        repaired_authors,
        stage="post_strategy_author_cleanup",
    )
    cleanup_decisions, cleanup_reviews = [], []
    before_author_layout = clone_authors(repaired_authors)
    # The page-author/card reconstruction is conference-independent.  It is
    # enabled only when the PDF supplies a closed, spatially supported author
    # set, so this does not replace a clean TEI list with weak guesses.
    repaired_authors, author_layout_decisions, author_layout_reviews, layout_discovery = reconcile_authors_from_layout(
        pdf_context,
        repaired_authors,
        enabled=True,
    )
    strong_layout_rebuild = bool(
        layout_discovery.get("fully_supported")
        and len(repaired_authors) >= max(2, int(len(before_author_layout) * 0.70 + 0.999))
        and all(
            _looks_like_conservative_person_name(author.get("name", ""))
            and not _looks_like_explicit_organization_author(author.get("name", ""))
            for author in repaired_authors
        )
    )
    if strong_layout_rebuild:
        layout_guard_decisions, layout_guard_reviews = [], []
    else:
        repaired_authors, layout_guard_decisions, layout_guard_reviews = protect_reliable_author_list(
            before_author_layout,
            repaired_authors,
            stage="pdf_layout_author_reconciliation",
        )
    repaired_authors, post_layout_artifact_decisions = clean_post_strategy_author_artifacts(
        repaired_authors,
    )
    repaired_authors, duplicate_author_decisions = dedupe_authors_with_pdf_evidence(
        repaired_authors,
        pdf_context,
    )
    repaired_authors, default_symbol_decisions, default_symbol_reviews = (
        apply_default_and_symbol_affiliations(repaired_authors, pdf_context)
    )
    repaired_authors = apply_author_roles(
        repaired_authors,
        role_hints,
        preserve_existing=True,
    )
    layout_analysis = analyze_layout(pdf_context, repaired_authors)
    layout_auto_fill_enabled = _complete_layout_mapping(
        layout_analysis,
        len(repaired_authors),
        require_card_email=False,
    )
    repaired_authors, layout_decisions, layout_reviews = apply_layout_affiliations(
        repaired_authors,
        layout_analysis,
        auto_fill_enabled=layout_auto_fill_enabled,
        # A complete horizontal author/affiliation row mapping is equally
        # reliable across conference templates; keep the rule evidence-gated.
        auto_accept_aligned_rows=True,
    )
    repaired_authors, email_domain_decisions, email_domain_reviews = (
        apply_email_domain_affiliations(repaired_authors)
    )

    title = apply_conference_title_strategy(
        strategy,
        raw_title,
        authors=repaired_authors,
        pdf_context=pdf_context,
        conference_name=conference_name,
    )
    if not title:
        title = extract_title_from_pdf_context(pdf_context)

    result = {
        "title": title,
        "year": metadata.get("year", ""),
        "abstract": abstract,
        "authors": repaired_authors,
    }
    result.update(build_paper_relationship_summary(repaired_authors))
    decisions = (
        abstract_decisions
        + author_list_decisions
        + strategy_decisions
        + author_artifact_decisions
        + cleanup_guard_decisions
        + cleanup_decisions
        + author_layout_decisions
        + layout_guard_decisions
        + post_layout_artifact_decisions
        + duplicate_author_decisions
        + default_symbol_decisions
        + layout_decisions
        + email_domain_decisions
    )
    reviews = (
        abstract_reviews
        + role_hints.get("review_reasons", [])
        + author_list_reviews
        + strategy_reviews
        + cleanup_guard_reviews
        + cleanup_reviews
        + author_layout_reviews
        + layout_guard_reviews
        + default_symbol_reviews
        + layout_reviews
        + email_domain_reviews
    )
    reviews.extend(
        layout_analysis.get("classification", {}).get("review_reasons", [])
    )
    extractor_status = pdf_context.extractor_status or {}
    if extractor_status.get("pdfplumber") != "ok":
        reviews.append({
            "code": "pdfplumber_validation_unavailable",
            "stage": "evidence_extraction",
            "field": "pdf_layout",
            "status": extractor_status.get("pdfplumber", "unavailable"),
        })
    if extractor_status.get("pypdf") != "ok":
        reviews.append({
            "code": "pypdf_link_evidence_unavailable",
            "stage": "evidence_extraction",
            "field": "pdf_links",
            "status": extractor_status.get("pypdf", "unavailable"),
        })
    result["_extraction"] = {
        "schema_version": "1.1",
        "evidence": build_evidence(raw_metadata, pdf_context),
        "candidates": build_candidates(raw_metadata, result, layout_analysis, pdf_abstract),
        "decisions": decisions,
        "review_reasons": validate_metadata(raw_metadata, result, decisions, reviews),
    }
    return result


def extract_title_from_pdf_context(pdf_context):
    result = clean_text(" ".join(pdf_context.title_lines[:3]))
    return clean_title_text(result) if result and len(result) > 10 else ""


def clean_title_text(text):
    for pattern in [
        r"(?:Open\s+access\s+to\s+)?(?:the\s+)?Proceedings\s+of\s+the\s+\d+\w*\s+\w+.*?(?:is\s+sponsored\s+by|are\s+published\s+by)\s+\w+[\.\s]+",
        r"(?:Open\s+access\s+.*?)",
    ]:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            cleaned = text[match.end():].strip()
            if len(cleaned) >= 10:
                return cleaned
    return text


def apply_conference_author_strategy(
    strategy,
    authors,
    title="",
    pdf_context=None,
    conference_name="",
    pdf_path="",
):
    if not strategy or not hasattr(strategy, "refine_authors"):
        return authors
    try:
        refined = strategy.refine_authors(
            authors,
            title=title,
            pdf_path=pdf_path,
            pdf_lines=(pdf_context.first_page_lines if pdf_context else []),
            pdf_pages=(pdf_context.page_lines if pdf_context else {}),
            conference_name=conference_name,
        )
        return refined if isinstance(refined, list) else authors
    except Exception as exc:
        print(f"  ⚠ 会议策略作者清洗失败: {conference_name} ({exc})")
        return authors


def apply_conference_title_strategy(strategy, title, authors=None, pdf_context=None, conference_name=""):
    if not strategy or not hasattr(strategy, "refine_title"):
        return title
    try:
        refined = strategy.refine_title(
            title,
            authors=authors or [],
            pdf_title_fallback=(extract_title_from_pdf_context(pdf_context) if pdf_context else ""),
            pdf_lines=(pdf_context.first_page_lines if pdf_context else []),
            pdf_pages=(pdf_context.page_lines if pdf_context else {}),
            conference_name=conference_name,
        )
        return clean_text(refined) if refined else title
    except Exception as exc:
        print(f"  ⚠ 会议策略标题清洗失败: {conference_name} ({exc})")
        return title


def clean_post_strategy_author_artifacts(authors):
    result = []
    decisions = []
    country_terms = (
        "Australia|Belgium|Canada|China|Denmark|France|Germany|India|Israel|Italy|"
        "Japan|Korea|Netherlands|Norway|Singapore|Spain|Sweden|Switzerland|UK|USA|"
        "United Kingdom|United States"
    )
    location_only_re = re.compile(
        rf"^(?:Hong Kong|The Netherlands|{country_terms})$",
        re.IGNORECASE,
    )
    names = [clean_text(author.get("name", "")) for author in authors or []]
    non_country_first_tokens = {
        name.split()[0].lower()
        for name in names
        if name.split() and not re.search(rf"\b(?:{country_terms})$", name, re.IGNORECASE)
    }
    organization_re = re.compile(
        r"\b(?:university|institute|institution|laborator(?:y|ies)|labs?|research|"
        r"networks?|college|school|department|centre|center|academy|polytechnic|"
        r"communications?|software|privacy|servers?|universit(?:y|é|ät)|corporation|corp|inc|ltd|gmbh|"
        r"foundation|company|fraunhofer|athene|kaist|umass)\b",
        re.IGNORECASE,
    )
    for author in authors or []:
        original_name = clean_text(author.get("name", ""))
        name = re.sub(r"\s+(?:imec[- ]cosic)\s*$", "", original_name, flags=re.IGNORECASE)
        name = clean_text(re.sub(r"\b(?:19|20)\d{2}\b", "", name))
        if name != original_name:
            decisions.append({
                "action": "clean_author_name_artifact",
                "stage": "post_strategy_author_cleanup",
                "field": "authors",
                "old_name": original_name,
                "new_name": name,
            })

        if name.startswith(","):
            parts = [clean_text(item) for item in name.split(",") if clean_text(item)]
            if parts and all(_looks_like_conservative_person_name(item) for item in parts):
                for part in parts:
                    split_author = dict(author)
                    split_author["name"] = part
                    split_author["order"] = len(result)
                    result.append(split_author)
                decisions.append({
                    "action": "split_combined_author_string",
                    "stage": "post_strategy_author_cleanup",
                    "field": "authors",
                    "old_name": original_name,
                    "new_names": parts,
                })
                continue

        if (
            organization_re.search(name)
            or re.fullmatch(r"(?:UC|UT|NYU|MIT|CMU)\s+[A-Z][A-Za-z .&-]+", name)
            or re.fullmatch(r"[A-Z]\s+U[A-Z][A-Za-z.'-]+", name)
            or (
                location_only_re.fullmatch(name)
                and not clean_text(author.get("email", ""))
            )
            or (
                re.search(rf"\b(?:{country_terms})$", name, re.IGNORECASE)
                and name.split()[0].lower() in non_country_first_tokens
            )
        ):
            decisions.append({
                "action": "remove_organization_author",
                "stage": "post_strategy_author_cleanup",
                "field": "authors",
                "removed_name": name,
            })
            continue

        updated = dict(author)
        updated["name"] = name
        updated["order"] = len(result)
        result.append(updated)
    return result, decisions


def protect_reliable_author_list(baseline, proposed, stage):
    """Reject a parser candidate that discards most of a clean TEI author list.

    Conference parsers are useful for rebuilding genuinely broken author blocks, but
    multi-column PDF text can also combine several names into one card or mistake an
    affiliation for a person.  A clean, person-shaped TEI list is therefore retained
    when a proposal has fewer authors and preserves less than 70% of those names.
    """
    baseline = clone_authors(baseline)
    proposed = clone_authors(proposed)
    if len(baseline) < 2 or len(proposed) > len(baseline):
        return proposed, [], []
    if stage in {
        "conference_strategy",
        "post_strategy_author_cleanup",
        "pdf_layout_author_reconciliation",
    } and len(proposed) < len(baseline):
        surplus = len(baseline) - len(proposed)
        weak_baseline = sum(
            not clean_text(author.get("email", ""))
            and not author.get("affiliations")
            for author in baseline
        )
        rich_proposed = sum(
            bool(clean_text(author.get("email", "")))
            or bool(author.get("affiliations"))
            for author in proposed
        )
        if rich_proposed >= max(2, len(proposed) - 1):
            return proposed, [], []
    if not all(
        _looks_like_conservative_person_name(author.get("name", ""))
        and not _looks_like_explicit_organization_author(author.get("name", ""))
        for author in baseline
    ):
        return proposed, [], []

    proposed_keys = {compact_alpha(author.get("name", "")) for author in proposed}
    retained = sum(any(
        baseline_key == proposed_key
        or (
            min(len(baseline_key), len(proposed_key)) >= 8
            and (
                baseline_key.startswith(proposed_key)
                or proposed_key.startswith(baseline_key)
            )
        )
        for proposed_key in proposed_keys
    ) for baseline_key in (
        compact_alpha(author.get("name", "")) for author in baseline
    ))
    retention = retained / len(baseline)
    if retention >= 0.95:
        return proposed, [], []

    decision = {
        "action": "reject_author_list_rebuild",
        "stage": stage,
        "field": "authors",
        "baseline_count": len(baseline),
        "proposed_count": len(proposed),
        "retained_count": retained,
        "reason": "clean_baseline_author_list_would_be_mostly_lost",
    }
    review = {
        "code": "author_list_rebuild_rejected",
        "stage": stage,
        "field": "authors",
        "baseline_count": len(baseline),
        "proposed_count": len(proposed),
        "retained_count": retained,
    }
    return baseline, [decision], [review]


def _looks_like_explicit_organization_author(text):
    text = clean_text(text)
    if re.fullmatch(
        r"(?:Hong Kong|The Netherlands|Australia|Belgium|Canada|China|Denmark|France|"
        r"Germany|India|Israel|Italy|Japan|Korea|Netherlands|Norway|Singapore|Spain|"
        r"Sweden|Switzerland|UK|USA|United Kingdom|United States)",
        text,
        flags=re.IGNORECASE,
    ):
        return True
    return bool(re.search(
        r"\b(?:university|institute|institution|laborator(?:y|ies)|labs?|research|"
        r"networks?|communications?|software|privacy|servers?|college|school|department|centre|center|academy|"
        r"polytechnic|corporation|corp|inc|ltd|gmbh|foundation|company)\b",
        text,
        flags=re.IGNORECASE,
    ))


def _looks_like_conservative_person_name(text):
    tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'.-]*", clean_text(text))
    particles = {"de", "del", "der", "di", "dos", "du", "la", "le", "van", "von"}
    return 2 <= len(tokens) <= 6 and all(
        token[:1].isupper() or token.lower() in particles
        for token in tokens
    )


def dedupe_authors_with_pdf_evidence(authors, pdf_context):
    """Drop duplicate rows when the PDF has fewer exact author-name lines."""
    authors = clone_authors(authors)
    lines = pdf_context.preabstract_lines or pdf_context.first_page_lines or []
    line_counts = Counter(compact_alpha(line) for line in lines if compact_alpha(line))
    positions = {}
    for index, author in enumerate(authors):
        positions.setdefault(compact_alpha(author.get("name", "")), []).append(index)

    remove = set()
    decisions = []
    for key, indices in positions.items():
        supported = line_counts.get(key, 0)
        if not key or len(indices) <= 1 or supported <= 0 or supported >= len(indices):
            continue
        keep = indices[:supported]
        remove.update(indices[supported:])
        decisions.append({
            "action": "remove_duplicate_author_not_supported_by_pdf",
            "stage": "post_layout_author_cleanup",
            "field": "authors",
            "author": authors[indices[0]].get("name", ""),
            "extracted_count": len(indices),
            "pdf_name_line_count": supported,
            "removed_count": len(indices) - len(keep),
        })

    result = []
    for index, author in enumerate(authors):
        if index in remove:
            continue
        author["order"] = len(result)
        result.append(author)
    return result, decisions


def appears_in_preabstract_author_region(name, pdf_context):
    preabstract = extract_preabstract_text(pdf_context)
    if not preabstract or not name:
        return False
    preabstract_compact = compact_text(preabstract)
    name_compact = compact_text(name)
    surname = compact_alpha(name.split()[-1]) if name.split() else ""
    return bool(
        (name_compact and name_compact in preabstract_compact) or
        (surname and surname in preabstract_compact)
    )
