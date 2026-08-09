import copy
import re
import unicodedata
from collections import Counter

from author_metadata.config import EMAIL_RE, clean_text, looks_like_org, strip_marker


LOCATION_RE = re.compile(
    r"\b(?:usa|united states|uk|china|germany|france|switzerland|australia|"
    r"singapore|korea|canada|italy|spain|sweden|netherlands|belgium|japan|"
    r"hong kong)\b",
    re.IGNORECASE,
)
SHORT_ORG_RE = re.compile(
    r"\b(?:research|tech|llc|ltd|inc|corp|corporation|ab|labs?|google|meta|"
    r"cloudflare|visa|zama|inria|cnrs|cispa|eth|mit|ibm|microsoft|amazon)\b",
    re.IGNORECASE,
)
MULTILINGUAL_ORG_RE = re.compile(
    r"\b(?:universidade|université|universite|universität|universitat|universita|"
    r"universidad|univeristy|école|ecole|institut|academia|polytechnic|consensys|"
    r"sandbox|pqshield|bifold|irisa|algoCRYPT)\b",
    re.IGNORECASE,
)
ORG_ACRONYM_RE = re.compile(r"\b(?:TU|UC|UNC|ETH|EPFL|MIT|MPI|HAW|INESC|TEC|AQ|AWS)\b")
COMPACT_AFFILIATION_PREFIXES = ("CSAIL", "EPFL", "IDC", "MIT")


def _key(text):
    text = unicodedata.normalize("NFKD", clean_text(text)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _tokens(text):
    folded = unicodedata.normalize("NFKD", clean_text(text)).encode("ascii", "ignore").decode("ascii")
    return set(re.findall(r"[a-z0-9]+", folded.lower()))


def _affiliation_equivalent(candidate, selected):
    candidate_key = _key(candidate)
    selected_key = _key(selected)
    if candidate_key == selected_key:
        return True
    if len(candidate_key) >= 8 and candidate_key in selected_key:
        return True
    if len(selected_key) >= 8 and selected_key in candidate_key:
        return True
    candidate_tokens = _tokens(candidate)
    selected_tokens = _tokens(selected)
    return bool(
        len(candidate_tokens) >= 2
        and len(selected_tokens) >= 2
        and (candidate_tokens <= selected_tokens or selected_tokens <= candidate_tokens)
    )


def _looks_fragmented_affiliation(text):
    text = clean_text(text)
    if not text:
        return True
    return bool(
        re.search(r"\b(?:and|of|for)\s*[,;](?:\s|$)", text, re.IGNORECASE)
        or re.search(r"\b(?:and|of|for)\s*$", text, re.IGNORECASE)
        or re.match(
            r"^(?:university|institute|department|school|college|laboratory|lab)\s*[,;]",
            text,
            re.IGNORECASE,
        )
    )


def _center(block):
    bbox = block.get("bbox", [block.get("x", 0), 0, block.get("x", 0), 0])
    return (float(bbox[0]) + float(bbox[2])) / 2


def _clean_aligned_affiliation(text):
    """Restore only spacing that is strongly implied by compact PDF text."""
    text = strip_marker(text)
    text = re.sub(r"^[∗★✉]+\s*", "", text)
    text = re.sub(r"(?<=[A-Z])and(?=[A-Z])", " and ", text)
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    words = []
    for word in text.split():
        for prefix in COMPACT_AFFILIATION_PREFIXES:
            if word.startswith(prefix) and len(word) > len(prefix) and word[len(prefix)].isupper():
                word = f"{prefix} {word[len(prefix):]}"
                break
        words.append(word)
    return clean_text(" ".join(words))


def _row_candidate_text(block, author_block_ids):
    text = clean_text(block.get("raw_text", ""))
    if (
        not text
        or block.get("block_id") in author_block_ids
        or EMAIL_RE.search(text)
        or "@" in text
        or "{" in text
        or "}" in text
    ):
        return ""
    if re.fullmatch(r"[\d\W_]+", text):
        return ""
    return text


def _find_aligned_affiliation_relations(matches, blocks, author_block_ids):
    """Map same-baseline author and affiliation rows by horizontal position."""
    exact = [
        (index, match["block"])
        for index, match in matches.items()
        if match.get("match_score") == 1.0
    ]
    relations = []
    consumed_authors = set()
    for author_index, author_block in sorted(exact, key=lambda item: (-float(item[1].get("y", 0)), _center(item[1]))):
        if author_index in consumed_authors:
            continue
        author_y = float(author_block.get("y", 0))
        author_font = float(author_block.get("font_size", 0))
        author_row = [
            (index, block)
            for index, block in exact
            if index not in consumed_authors
            and abs(float(block.get("y", 0)) - author_y) <= 1.0
            and abs(float(block.get("font_size", 0)) - author_font) <= 0.8
        ]
        if len(author_row) < 2:
            continue

        row_candidates = []
        for block in blocks:
            text = _row_candidate_text(block, author_block_ids)
            if not text:
                continue
            dy = author_y - float(block.get("y", 0))
            if not 5 <= dy <= 22:
                continue
            if abs(float(block.get("font_size", 0)) - author_font) > 0.8:
                continue
            row_candidates.append(block)

        grouped_candidates = []
        for candidate_y in sorted(
            {round(float(block.get("y", 0)), 1) for block in row_candidates},
            reverse=True,
        ):
            group = [
                block for block in row_candidates
                if abs(float(block.get("y", 0)) - candidate_y) <= 1.0
            ]
            if len(group) == len(author_row):
                grouped_candidates.append(group)
        if not grouped_candidates:
            continue

        affiliation_row = sorted(grouped_candidates[0], key=_center)
        ordered_authors = sorted(author_row, key=lambda item: _center(item[1]))
        pairs = list(zip(ordered_authors, affiliation_row))
        if any(abs(_center(author) - _center(affiliation)) > 45 for (_, author), affiliation in pairs):
            continue
        if not any(_looks_like_affiliation(block.get("raw_text", "")) for block in affiliation_row):
            continue

        for (index, matched_author), affiliation in pairs:
            relations.append({
                "author_index": index,
                "author": "",
                "affiliation_raw": _clean_aligned_affiliation(affiliation.get("raw_text", "")),
                "confidence": 0.99,
                "author_block_id": matched_author.get("block_id", ""),
                "affiliation_block_ids": [affiliation.get("block_id", "")],
                "validation_block_ids": [],
                "relation_type": "aligned_author_affiliation_row",
                "vertical_distance": round(author_y - float(affiliation.get("y", 0)), 3),
                "center_distance": round(abs(_center(matched_author) - _center(affiliation)), 3),
                "local_auto_eligible": True,
            })
            consumed_authors.add(index)
    return relations


def _author_match_score(name, text):
    name_key = _key(name)
    text_key = _key(text)
    if not name_key or not text_key:
        return 0.0
    if name_key == text_key:
        return 1.0
    name_tokens = _tokens(name)
    text_tokens = _tokens(text)
    if len(name_tokens) < 2 or len(text_tokens) < 2:
        return 0.0
    overlap = len(name_tokens & text_tokens)
    if overlap < 2:
        return 0.0
    return overlap / max(len(name_tokens), len(text_tokens))


def _looks_like_person_candidate(text):
    text = clean_text(text)
    if (
        not text
        or len(text) > 80
        or "@" in text
        or "," in text
        or any(char.isdigit() for char in text)
    ):
        return False
    if _looks_like_affiliation(text):
        return False
    tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'.-]*", text)
    if not 2 <= len(tokens) <= 7:
        return False
    if not any(len(re.sub(r"\W", "", token)) >= 2 for token in tokens):
        return False
    if tokens[0].lower() in {"while", "during", "where", "when"}:
        return False
    connectors = {"de", "del", "di", "da", "van", "von", "la", "le", "y"}
    return all(token.lower() in connectors or token[:1].isupper() for token in tokens)


def _clean_person_candidate(text):
    text = clean_text(text)
    text = re.sub(r"\s*[*∗†‡§¶#]+\s*$", "", text)
    return clean_text(text)


def _header_blocks(pdf_context):
    blocks = list((pdf_context.page_blocks or {}).get(1, []))
    abstract_y = None
    for block in blocks:
        if clean_text(block.get("raw_text", "")).lower() == "abstract":
            abstract_y = float(block.get("y", 0))
            break
    if abstract_y is not None:
        blocks = [block for block in blocks if float(block.get("y", 0)) > abstract_y]
    return sorted(blocks, key=lambda block: (-float(block.get("y", 0)), float(block.get("x", 0))))


def discover_page_authors(pdf_context, existing_authors=None):
    blocks = _header_blocks(pdf_context)
    existing_keys = {
        _key(author.get("name", ""))
        for author in existing_authors or []
        if _key(author.get("name", ""))
    }
    # Author typefaces vary by publisher/template (NDSS 2025 uses 10.959pt).
    # Infer the font only from exact TEI/PDF name anchors.  With no TEI names,
    # use person-shaped header blocks as a conservative discovery fallback.
    anchored_blocks = [
        block for block in blocks
        if _key(_clean_person_candidate(block.get("raw_text", ""))) in existing_keys
        and _looks_like_person_candidate(_clean_person_candidate(block.get("raw_text", "")))
    ]
    font_source = anchored_blocks if anchored_blocks else (
        [
            block for block in blocks
            if 8.0 <= float(block.get("font_size", 0)) <= 16.0
            and _looks_like_person_candidate(_clean_person_candidate(block.get("raw_text", "")))
        ]
        if not existing_keys else []
    )
    font_counts = Counter(
        round(float(block.get("font_size", 0)), 1)
        for block in font_source
    )
    if not font_counts:
        return {
            "dominant_font_size": 0.0,
            "candidates": [],
            "fully_supported": False,
            "anchored_existing_count": 0,
        }
    dominant_font_size = max(font_counts, key=lambda size: (font_counts[size], size))
    candidates = []
    for block in blocks:
        if abs(float(block.get("font_size", 0)) - dominant_font_size) > 0.4:
            continue
        candidate_name = _clean_person_candidate(block.get("raw_text", ""))
        if not _looks_like_person_candidate(candidate_name):
            continue
        author_y = float(block.get("y", 0))
        author_center = _center(block)
        support_ids = []
        for support in blocks:
            dy = author_y - float(support.get("y", 0))
            if not 5 <= dy <= 36 or abs(author_center - _center(support)) > 110:
                continue
            text = support.get("raw_text", "")
            if EMAIL_RE.search(text) or _looks_like_affiliation(text):
                support_ids.append(support.get("block_id", ""))
        candidates.append({
            "name": candidate_name,
            "block_id": block.get("block_id", ""),
            "font_size": float(block.get("font_size", 0)),
            "support_ids": support_ids,
        })
    unique_names = {_key(candidate["name"]) for candidate in candidates}
    fully_supported = bool(candidates) and len(unique_names) == len(candidates) and all(
        candidate["support_ids"] for candidate in candidates
    )
    return {
        "dominant_font_size": dominant_font_size,
        "candidates": candidates,
        "fully_supported": fully_supported,
        "anchored_existing_count": len({
            _key(_clean_person_candidate(block.get("raw_text", "")))
            for block in anchored_blocks
            if round(float(block.get("font_size", 0)), 1) == dominant_font_size
        }),
    }


def reconcile_authors_from_layout(pdf_context, authors, enabled=True):
    discovery = discover_page_authors(pdf_context, authors)
    if not enabled or len(discovery["candidates"]) < 2:
        return copy.deepcopy(authors or []), [], [], discovery

    existing = copy.deepcopy(authors or [])
    available = set(range(len(existing)))
    matches = {}
    for page_index, candidate in enumerate(discovery["candidates"]):
        exact = [
            index for index in available
            if _key(existing[index].get("name", "")) == _key(candidate["name"])
        ]
        if exact:
            matches[page_index] = exact[0]
            available.remove(exact[0])
    unmatched_page_indices = [
        index for index in range(len(discovery["candidates"])) if index not in matches
    ]
    safe_missing_addition = bool(
        not available
        and len(discovery["candidates"]) > len(existing)
        and unmatched_page_indices
        and all(discovery["candidates"][index]["support_ids"] for index in unmatched_page_indices)
    )
    safe_name_only_correction = bool(
        not available
        and len(discovery["candidates"]) == len(existing) == len(matches)
    )
    safe_invalid_replacement = bool(
        discovery["fully_supported"]
        and available
        and all(
            not _looks_like_person_candidate(existing[index].get("name", ""))
            for index in available
        )
    )
    if (
        (not discovery["fully_supported"] and not safe_missing_addition and not safe_name_only_correction)
        or (available and not safe_invalid_replacement)
    ):
        return copy.deepcopy(authors or []), [], [], discovery

    rebuilt = []
    corrected_names = []
    for order, candidate in enumerate(discovery["candidates"]):
        existing_index = matches.get(order)
        if existing_index is None:
            author = {
                "order": order,
                "name": candidate["name"],
                "email": "",
                "affiliations": [],
                "affiliation_source": "empty",
                "first_author": order == 0,
                "co_first_author": False,
                "equal_contribution": False,
                "corresponding": False,
            }
        else:
            author = copy.deepcopy(existing[existing_index])
            if clean_text(author.get("name", "")) != candidate["name"]:
                corrected_names.append({
                    "from": author.get("name", ""),
                    "to": candidate["name"],
                    "block_id": candidate["block_id"],
                })
            author["name"] = candidate["name"]
            author["order"] = order
        rebuilt.append(author)

    old_names = [author.get("name", "") for author in existing]
    new_names = [author.get("name", "") for author in rebuilt]
    decisions = []
    reviews = []
    if old_names != new_names:
        decisions.append({
            "action": "rebuild_author_list_from_pdf_layout",
            "stage": "layout_author_reconciliation",
            "field": "authors",
            "old_names": old_names,
            "new_names": new_names,
            "corrected_names": corrected_names,
            "removed_names": [existing[index].get("name", "") for index in sorted(available)],
            "evidence_ids": [candidate["block_id"] for candidate in discovery["candidates"]],
        })
    return rebuilt, decisions, reviews, discovery


def _looks_like_affiliation(text):
    text = clean_text(text)
    if not text or EMAIL_RE.search(text):
        return False
    if (
        looks_like_org(text)
        or SHORT_ORG_RE.search(text)
        or MULTILINGUAL_ORG_RE.search(text)
        or ORG_ACRONYM_RE.search(text)
    ):
        return True
    return False


def _looks_like_location(text):
    text = clean_text(text)
    if not text or _looks_like_affiliation(text):
        return False
    return bool(LOCATION_RE.search(text) or ("," in text and len(text.split()) <= 8))


def _match_author_blocks(authors, blocks):
    candidates = []
    for author_index, author in enumerate(authors):
        for block in blocks:
            score = _author_match_score(author.get("name", ""), block.get("raw_text", ""))
            if score >= 0.66 and float(block.get("font_size", 0)) >= 8:
                candidates.append((score, author_index, block))
    exact_font_counts = Counter(
        round(float(block.get("font_size", 0)), 1)
        for score, _, block in candidates
        if score == 1.0 and float(block.get("font_size", 0)) <= 14
    )
    dominant_font_size = 0.0
    if exact_font_counts:
        dominant_font_size = max(exact_font_counts, key=lambda size: (exact_font_counts[size], size))
    matches = {}
    used_blocks = set()
    for score, author_index, block in sorted(candidates, key=lambda item: item[0], reverse=True):
        block_font_size = float(block.get("font_size", 0))
        if dominant_font_size and abs(block_font_size - dominant_font_size) > 0.8:
            continue
        block_id = block.get("block_id", "")
        if author_index in matches or block_id in used_blocks:
            continue
        matches[author_index] = {"block": block, "match_score": round(score, 4)}
        used_blocks.add(block_id)
    return matches, dominant_font_size


def _find_affiliation_relation(author_index, author_match, blocks, author_block_ids):
    author_block = author_match["block"]
    author_y = float(author_block.get("y", 0))
    author_center = _center(author_block)
    author_centers = sorted({
        round(_center(block), 2) for block in blocks
        if block.get("block_id") in author_block_ids
    })
    candidates = []
    for block in blocks:
        if block.get("block_id") in author_block_ids:
            continue
        dy = author_y - float(block.get("y", 0))
        center_distance = abs(author_center - _center(block))
        if not (4 <= dy <= 90) or center_distance > 105:
            continue
        if float(block.get("font_size", 0)) > float(author_block.get("font_size", 0)) + 0.5:
            continue
        text = block.get("raw_text", "")
        if EMAIL_RE.search(text) or "@" in text or "{" in text or "}" in text:
            continue
        bbox = block.get("bbox", [])
        if len(bbox) >= 4 and sum(
            float(bbox[0]) - 5 <= center <= float(bbox[2]) + 5
            for center in author_centers
        ) > 1:
            # A full row spanning several author columns is shared/repeated
            # evidence, not a local card belonging to the middle author.
            continue
        has_org_continuation = any(
            5 <= float(block.get("y", 0)) - float(next_block.get("y", 0)) <= 17
            and abs(_center(block) - _center(next_block)) <= 105
            and _looks_like_affiliation(next_block.get("raw_text", ""))
            for next_block in blocks
            if next_block.get("block_id") not in author_block_ids
            and next_block.get("block_id") != block.get("block_id")
        )
        location_support = [
            next_block
            for next_block in blocks
            if next_block.get("block_id") not in author_block_ids
            and next_block.get("block_id") != block.get("block_id")
            and 5 <= float(block.get("y", 0)) - float(next_block.get("y", 0)) <= 17
            and abs(_center(block) - _center(next_block)) <= 105
            and _looks_like_location(next_block.get("raw_text", ""))
        ]
        email_support = [
            next_block
            for next_block in blocks
            if 5 <= author_y - float(next_block.get("y", 0)) <= 42
            and abs(author_center - _center(next_block)) <= 105
            and EMAIL_RE.search(next_block.get("raw_text", ""))
        ]
        short_card_org = bool(
            location_support
            and email_support
            and 1 <= len(clean_text(text).split()) <= 6
            and clean_text(text)[:1].isupper()
        )
        grouped_card_org = bool(
            dy > 34
            and location_support
            and email_support
            and clean_text(text)[:1].isupper()
        )
        if dy > 34 and not grouped_card_org:
            continue
        if not _looks_like_affiliation(text) and not has_org_continuation and not short_card_org and not grouped_card_org:
            continue
        score = dy + center_distance * 0.04
        validation_ids = [
            item.get("block_id", "")
            for item in location_support[:1] + email_support[:1]
        ] if short_card_org or grouped_card_org else []
        candidates.append((score, dy, center_distance, block, validation_ids, grouped_card_org))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    _, dy, center_distance, affiliation_block, validation_ids, grouped_card_org = candidates[0]
    raw_text = _clean_aligned_affiliation(affiliation_block.get("raw_text", ""))
    evidence_ids = [affiliation_block.get("block_id", "")]
    email_candidates = [
        block
        for block in blocks
        if 5 <= author_y - float(block.get("y", 0)) <= 42
        and abs(author_center - _center(block)) <= 105
        and EMAIL_RE.search(block.get("raw_text", ""))
    ]
    email_block = min(
        email_candidates,
        key=lambda block: (
            author_y - float(block.get("y", 0)),
            abs(author_center - _center(block)),
        ),
        default=None,
    )
    email_match = EMAIL_RE.search(email_block.get("raw_text", "")) if email_block else None
    current_block = affiliation_block
    for _ in range(7):
        current_y = float(current_block.get("y", 0))
        current_center = _center(current_block)
        continuation_candidates = []
        for block in blocks:
            if block.get("block_id") in author_block_ids or block.get("block_id") in evidence_ids:
                continue
            next_dy = current_y - float(block.get("y", 0))
            if not (5 <= next_dy <= 17):
                continue
            if abs(current_center - _center(block)) > 105:
                continue
            text = clean_text(block.get("raw_text", ""))
            if (
                not text
                or EMAIL_RE.search(text)
                or "@" in text
                or "{" in text
                or "}" in text
            ):
                continue
            previous_continues = bool(re.search(r"(?:\b(?:and|of|for)|[,&/-])$", raw_text, re.IGNORECASE))
            short_continuation = bool(
                len(text.split()) <= 6
                and (text[:1].isupper() or text.lower().startswith(("of ", "for ", "and ")))
                and float(block.get("font_size", 0)) <= float(affiliation_block.get("font_size", 0)) + 0.5
            )
            if _looks_like_location(text) or _looks_like_affiliation(text) or previous_continues or short_continuation:
                continuation_candidates.append((next_dy, abs(current_center - _center(block)), block))
        if not continuation_candidates:
            break
        _, _, continuation = min(continuation_candidates, key=lambda item: (item[0], item[1]))
        separator = "; " if (
            _looks_like_location(current_block.get("raw_text", ""))
            and _looks_like_affiliation(continuation.get("raw_text", ""))
        ) else " "
        raw_text = _clean_aligned_affiliation(
            f"{raw_text}{separator}{continuation.get('raw_text', '')}"
        )
        evidence_ids.append(continuation.get("block_id", ""))
        current_block = continuation
    confidence = 0.97 if author_match["match_score"] == 1.0 and 7 <= dy <= 30 else 0.88
    if grouped_card_org and author_match["match_score"] == 1.0:
        confidence = 0.95
    if center_distance > 90:
        confidence -= 0.05
    return {
        "author_index": author_index,
        "author": "",
        "affiliation_raw": raw_text,
        "confidence": round(confidence, 4),
        "author_block_id": author_block.get("block_id", ""),
        "affiliation_block_ids": evidence_ids,
        "email_raw": email_match.group(0) if email_match else "",
        "email_block_ids": [email_block.get("block_id", "")] if email_block else [],
        "validation_block_ids": validation_ids,
        "relation_type": "grouped_author_card" if grouped_card_org else "author_card",
        "vertical_distance": round(dy, 3),
        "center_distance": round(center_distance, 3),
        "local_auto_eligible": bool(author_match["match_score"] == 1.0),
    }


def _numeric_marker_for_block(affiliation_block, author_block, blocks):
    """Find a superscript number attached to an affiliation block."""
    affiliation_bbox = affiliation_block.get("bbox", [])
    if len(affiliation_bbox) < 4:
        return ""
    right = float(affiliation_bbox[2])
    base_y = float(affiliation_block.get("y", 0))
    author_y = float(author_block.get("y", 0))
    markers = []
    for block in blocks:
        text = clean_text(block.get("raw_text", ""))
        if not re.fullmatch(r"\d{1,3}", text):
            continue
        x = float(block.get("x", 0))
        y = float(block.get("y", 0))
        if right - 8 <= x <= right + 12 and base_y - 2 <= y <= author_y + 2:
            markers.append((abs(x - right) + abs(y - base_y) * 0.1, text))
    return min(markers, default=(0, ""))[1]


def _extract_numbered_affiliation_notes(pdf_context):
    """Extract numbered 'while affiliated with' notes from the first page.

    PDF text extraction can place the adjacent body column on the same block;
    therefore the parser stops at the first explicit sentence terminator or
    known organization ending and never treats body prose as an institution.
    """
    blocks = list((pdf_context.page_blocks or {}).get(1, []))
    abstract_y = min(
        (float(block.get("y", 0)) for block in blocks
         if clean_text(block.get("raw_text", "")).lower().startswith("abstract")),
        default=0.0,
    )
    notes = {}
    note_markers = []
    for block in blocks:
        text = clean_text(block.get("raw_text", ""))
        if not re.fullmatch(r"\d{1,3}", text):
            continue
        y = float(block.get("y", 0))
        if abstract_y and y >= abstract_y:
            continue
        note_markers.append(block)
    phrase_re = re.compile(
        r"(?:part\s*of\s*the\s*work\s*was\s*done\s*while\s*affiliated\s*with|"
        r"while\s*affiliated\s*with|during\s*this\s*work\s*(?:at|with)|"
        r"was\s*at)\s*(?P<org>.+?)(?:\.|$)",
        re.IGNORECASE,
    )
    for marker in note_markers:
        marker_y = float(marker.get("y", 0))
        marker_x = float(marker.get("x", 0))
        nearby = [
            block for block in blocks
            if marker_y - float(block.get("y", 0)) <= 28
            and float(block.get("y", 0)) <= marker_y
            and abs(float(block.get("x", 0)) - marker_x) <= 35
            and block.get("block_id") != marker.get("block_id")
        ]
        nearby.sort(key=lambda block: float(block.get("y", 0)), reverse=True)
        raw = " ".join(clean_text(block.get("raw_text", "")) for block in nearby)
        match = phrase_re.search(raw)
        if not match:
            continue
        org = clean_text(match.group("org"))
        # Remove text from a merged adjacent body column.  Organization names
        # in these notes conventionally terminate at the final country/city.
        org = re.split(
            r"\s+(?:tion\s+of\s+network|observing|using|demonstrated|the\s+detec)",
            org,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        # A wrapped continuation such as ``ofMilan.`` is often emitted as the
        # next left-column block while the right-column body is interleaved.
        for continuation in nearby[1:]:
            continuation_text = clean_text(continuation.get("raw_text", ""))
            if not re.match(r"^of(?:\s|[A-Z])", continuation_text):
                continue
            continuation_text = continuation_text.split(".", 1)[0]
            if len(continuation_text.split()) <= 4:
                org = f"{org} {continuation_text}"
                break
        org = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", org)
        org = re.sub(r"^the\s+", "", clean_text(org), flags=re.IGNORECASE).strip(" ,;:")
        if _looks_like_affiliation(org):
            notes[marker.get("raw_text", "")] = org
    return notes


def analyze_layout(pdf_context, authors):
    blocks = _header_blocks(pdf_context)
    matches, dominant_font_size = _match_author_blocks(authors, blocks)
    author_block_ids = {match["block"].get("block_id", "") for match in matches.values()}
    relations = []
    for author_index, match in matches.items():
        relation = _find_affiliation_relation(author_index, match, blocks, author_block_ids)
        if relation:
            relation_blocks = [
                block for block in blocks
                if block.get("block_id") in relation.get("affiliation_block_ids", [])
            ]
            relation["numeric_marker"] = (
                _numeric_marker_for_block(relation_blocks[0], match["block"], blocks)
                if relation_blocks else ""
            )
            relation["author"] = authors[author_index].get("name", "")
            relations.append(relation)
    aligned_relations = _find_aligned_affiliation_relations(matches, blocks, author_block_ids)
    if aligned_relations:
        aligned_by_author = {relation["author_index"]: relation for relation in aligned_relations}
        relations = [
            relation for relation in relations
            if relation["author_index"] not in aligned_by_author
        ] + aligned_relations
        for relation in relations:
            relation["author"] = authors[relation["author_index"]].get("name", "")
    exact_matches = sum(match["match_score"] == 1.0 for match in matches.values())
    auto_eligible = bool(authors) and exact_matches == len(authors) == len(matches)
    layout_type = (
        "aligned_author_affiliation_rows"
        if len(aligned_relations) >= 2
        else "author_card_grid"
        if len(relations) >= 2
        else "unclassified"
    )
    page_author_discovery = discover_page_authors(pdf_context, authors)
    return {
        "schema_version": "1.0",
        "layout_type": layout_type,
        "header_block_count": len(blocks),
        "author_count": len(authors),
        "matched_author_count": len(matches),
        "exact_author_match_count": exact_matches,
        "dominant_author_font_size": dominant_font_size,
        "auto_eligible": auto_eligible,
        "aligned_relation_count": len(aligned_relations),
        "page_author_discovery": page_author_discovery,
        "numbered_affiliation_notes": _extract_numbered_affiliation_notes(pdf_context),
        "author_nodes": [
            {
                "author_index": index,
                "author": authors[index].get("name", ""),
                "block_id": match["block"].get("block_id", ""),
                "match_score": match["match_score"],
            }
            for index, match in sorted(matches.items())
        ],
        "relations": relations,
    }


def apply_layout_affiliations(
    authors,
    analysis,
    auto_fill_enabled=True,
    auto_accept_aligned_rows=False,
):
    result = copy.deepcopy(authors or [])
    decisions = []
    reviews = []
    relations = {relation["author_index"]: relation for relation in analysis.get("relations", [])}
    current_affiliation_sets = {
        tuple(_key(value) for value in author.get("affiliations", []))
        for author in result
    }
    aligned_relations = [
        relation for relation in relations.values()
        if relation.get("relation_type") == "aligned_author_affiliation_row"
    ]
    strong_aligned_mapping = bool(
        auto_accept_aligned_rows
        and len(result) >= 2
        and len(aligned_relations) == len(result)
        and len(current_affiliation_sets) == 1
        and len({_key(relation.get("affiliation_raw", "")) for relation in aligned_relations}) >= 2
        and all(relation.get("local_auto_eligible") for relation in aligned_relations)
    )
    for index, author in enumerate(result):
        relation = relations.get(index)
        if not relation:
            continue
        if strong_aligned_mapping:
            selected = [relation["affiliation_raw"]]
            old_value = list(author.get("affiliations", []))
            if tuple(_key(value) for value in old_value) != tuple(_key(value) for value in selected):
                author["affiliations"] = selected
                author["affiliation_source"] = "pdf_layout_aligned_row"
                decisions.append({
                    "action": "replace_shared_tei_affiliation_from_aligned_pdf_row",
                    "stage": "layout_relation",
                    "author": author.get("name", ""),
                    "field": "affiliations",
                    "old_value": old_value,
                    "selected_value": selected,
                    "confidence": relation["confidence"],
                    "evidence_ids": relation["affiliation_block_ids"],
                    "validation_evidence_ids": relation.get("validation_block_ids", []),
                })
            continue
        if author.get("affiliations"):
            fragmented_items = [
                item for item in author.get("affiliations", []) if _looks_fragmented_affiliation(item)
            ]
            stable_items = [
                item for item in author.get("affiliations", []) if not _looks_fragmented_affiliation(item)
            ]
            relation_key = _key(relation["affiliation_raw"])
            preserves_stable_items = all(
                len(_key(item)) >= 8 and _key(item) in relation_key
                for item in stable_items
            )
            if (
                auto_fill_enabled
                and relation.get("local_auto_eligible")
                and relation["confidence"] >= 0.92
                and fragmented_items
                and preserves_stable_items
                and not _looks_fragmented_affiliation(relation["affiliation_raw"])
            ):
                old_value = list(author.get("affiliations", []))
                author["affiliations"] = [relation["affiliation_raw"]]
                author["affiliation_source"] = "pdf_layout"
                decisions.append({
                    "action": "replace_fragmented_affiliation_from_pdf_layout",
                    "stage": "layout_relation",
                    "author": author.get("name", ""),
                    "field": "affiliations",
                    "old_value": old_value,
                    "selected_value": [relation["affiliation_raw"]],
                    "confidence": relation["confidence"],
                    "evidence_ids": relation["affiliation_block_ids"],
                    "validation_evidence_ids": relation.get("validation_block_ids", []),
                })
                continue
            equivalent = any(
                _affiliation_equivalent(relation["affiliation_raw"], item)
                for item in author.get("affiliations", [])
            )
            if _key(relation["affiliation_raw"]) and not equivalent:
                reviews.append({
                    "code": "layout_affiliation_conflict",
                    "stage": "layout_relation",
                    "field": "affiliations",
                    "author": author.get("name", ""),
                    "selected": list(author.get("affiliations", [])),
                    "candidate": relation["affiliation_raw"],
                    "confidence": relation["confidence"],
                    "evidence_ids": relation["affiliation_block_ids"],
                    "validation_evidence_ids": relation.get("validation_block_ids", []),
                })
            continue
        if (
            auto_fill_enabled
            and relation.get("local_auto_eligible")
            and relation["confidence"] >= 0.92
        ):
            author["affiliations"] = [relation["affiliation_raw"]]
            author["affiliation_source"] = "pdf_layout"
            decisions.append({
                "action": "fill_from_pdf_layout",
                "stage": "layout_relation",
                "author": author.get("name", ""),
                "field": "affiliations",
                "selected_value": [relation["affiliation_raw"]],
                "confidence": relation["confidence"],
                "evidence_ids": relation["affiliation_block_ids"],
                "validation_evidence_ids": relation.get("validation_block_ids", []),
            })
        else:
            reviews.append({
                "code": "layout_affiliation_candidate_not_autoaccepted",
                "stage": "layout_relation",
                "field": "affiliations",
                "author": author.get("name", ""),
                "candidate": relation["affiliation_raw"],
                "confidence": relation["confidence"],
                "reason": (
                    "conference_not_validated"
                    if not auto_fill_enabled
                    else "author_not_locally_exact"
                    if not relation.get("local_auto_eligible")
                    else "low_confidence"
                ),
            })
    # A numbered note belongs only to the author whose local institution block
    # carries that superscript.  Never propagate the note to the whole paper.
    notes = analysis.get("numbered_affiliation_notes", {})
    for index, relation in relations.items():
        marker = relation.get("numeric_marker", "")
        note = notes.get(marker, "")
        if not marker or not note or index >= len(result):
            continue
        author = result[index]
        if any(_affiliation_equivalent(note, item) for item in author.get("affiliations", [])):
            continue
        author["affiliations"] = list(author.get("affiliations", [])) + [note]
        author["affiliation_source"] = "pdf_layout_footnote"
        decisions.append({
            "action": "fill_affiliation_note_from_pdf_layout",
            "stage": "layout_relation",
            "field": "affiliations",
            "author": author.get("name", ""),
            "selected_value": [note],
            "numeric_marker": marker,
            "evidence_ids": relation.get("affiliation_block_ids", []),
        })
    return result, decisions, reviews
