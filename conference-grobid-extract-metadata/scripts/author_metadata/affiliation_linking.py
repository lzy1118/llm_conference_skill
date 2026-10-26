import copy
import re

from author_metadata.author_validation import is_author_name_noise, is_org_name
from author_metadata.config import (
    EMAIL_LABEL_RE,
    EMAIL_RE,
    ascii_fold,
    clean_text,
    compact_alpha,
    is_noise_text,
    looks_like_org,
    normalize_name,
    strip_marker,
)


AFFILIATION_MARKERS = "*∗†‡§¶#∥"
PUBLIC_EMAIL_DOMAINS = {
    "126.com", "163.com", "aol.com", "foxmail.com", "gmail.com",
    "googlemail.com", "hotmail.com", "icloud.com", "live.com", "mail.com",
    "outlook.com", "proton.me", "protonmail.com", "qq.com", "yahoo.com",
    "yahoo.co.jp", "yandex.com", "zoho.com",
}
AFFILIATION_NOTE_RE = re.compile(r"(?:is\s*)?affiliated\s*with", re.IGNORECASE)
ACRONYM_ORG_RE = re.compile(r"\b[A-Z]{2,}(?:['-]s)?\s+[A-Za-z0-9]")
ROLE_TEXT_RE = re.compile(
    r"\b(?:corresponding\s+authors?|co[- ]?first\s+authors?|"
    r"equal\s+contribution|contributed\s+equally|made\s+equal\s+contribution)\b",
    re.IGNORECASE,
)


def apply_default_and_symbol_affiliations(authors, pdf_context):
    """Apply a complete shared-default plus symbol-exception header mapping.

    The rule is conference-independent, but intentionally requires a closed
    author/symbol/affiliation relationship before changing any affiliation.
    """
    if not authors or not pdf_context:
        return authors, [], []

    parsed = _extract_default_and_symbol_header(authors, pdf_context)
    if not parsed:
        return authors, [], []

    result = copy.deepcopy(authors)
    proposed = parsed["affiliations_by_author"]
    for author in result:
        name_key = normalize_name(author.get("name", ""))
        existing = [clean_text(value) for value in author.get("affiliations", []) if clean_text(value)]
        candidate = proposed.get(name_key, [])
        if (
            existing
            and not parsed.get("replace_existing")
            and not _equivalent_affiliation_lists(existing, candidate)
        ):
            return authors, [], []

    decisions = []
    for author in result:
        name_key = normalize_name(author.get("name", ""))
        candidate = proposed[name_key]
        existing = [clean_text(value) for value in author.get("affiliations", []) if clean_text(value)]
        if not existing:
            author["affiliations"] = list(candidate)
            author["affiliation_source"] = parsed.get(
                "affiliation_source",
                "pdf_default_symbol_affiliation",
            )
            decisions.append({
                "action": "fill_default_and_symbol_affiliations_from_pdf",
                "stage": "field_level_pdf_merge",
                "field": "affiliations",
                "author": author.get("name", ""),
                "selected": list(candidate),
                "author_markers": parsed["author_markers"].get(name_key, []),
                "evidence_lines": list(parsed["evidence_lines"]),
                "evidence_block_ids": list(parsed["evidence_block_ids"]),
            })
        elif parsed.get("replace_existing") and not _exact_affiliation_lists(existing, candidate):
            author["affiliations"] = list(candidate)
            author["affiliation_source"] = parsed.get(
                "affiliation_source",
                "pdf_detached_symbol_affiliation",
            )
            decisions.append({
                "action": "replace_affiliations_from_complete_symbol_layout",
                "stage": "field_level_pdf_merge",
                "field": "affiliations",
                "author": author.get("name", ""),
                "replaced": existing,
                "selected": list(candidate),
                "author_markers": parsed["author_markers"].get(name_key, []),
                "evidence_lines": list(parsed["evidence_lines"]),
                "evidence_block_ids": list(parsed["evidence_block_ids"]),
            })

    for name_key, additions in parsed.get("additional_affiliations", {}).items():
        author = next(
            (item for item in result if normalize_name(item.get("name", "")) == name_key),
            None,
        )
        if not author:
            continue
        new_values = [
            value for value in additions
            if value and not any(compact_alpha(value) == compact_alpha(existing) for existing in author.get("affiliations", []))
        ]
        if not new_values:
            continue
        author["affiliations"] = dedupe_affiliations(author.get("affiliations", []) + new_values)
        author["affiliation_source"] = author.get("affiliation_source") or "pdf_affiliation_note"
        decisions.append({
            "action": "fill_affiliation_note_from_pdf",
            "stage": "field_level_pdf_merge",
            "field": "affiliations",
            "author": author.get("name", ""),
            "selected": new_values,
        })

    email_decisions = _fill_complete_ordered_group_emails(
        result,
        parsed["author_markers"],
        parsed["header_lines"],
    )
    decisions.extend(email_decisions)
    return result, decisions, []


def _extract_default_and_symbol_header(authors, pdf_context):
    author_names = [clean_text(author.get("name", "")) for author in authors]
    if not author_names or any(not name for name in author_names):
        return None
    if len({normalize_name(name) for name in author_names}) != len(author_names):
        return None

    for lines in _header_line_sources(pdf_context):
        parsed = _parse_default_and_symbol_lines(author_names, lines)
        if not parsed:
            parsed = _parse_detached_symbol_blocks(author_names, pdf_context)
        if not parsed:
            continue
        parsed["header_lines"] = lines
        parsed["evidence_block_ids"] = _matching_header_block_ids(
            pdf_context,
            author_names,
            parsed["evidence_lines"],
        )
        return parsed
    return None


def _parse_detached_symbol_blocks(author_names, pdf_context):
    blocks = [
        block for block in (pdf_context.page_blocks or {}).get(1, [])
        if clean_text(block.get("raw_text", ""))
    ]
    if not blocks:
        return None

    author_block = max(
        (
            block for block in blocks
            if not EMAIL_RE.search(block.get("raw_text", ""))
            and not looks_like_org(block.get("raw_text", ""))
            and sum(bool(_author_name_pattern(name).search(block.get("raw_text", ""))) for name in author_names) >= 2
        ),
        key=lambda block: sum(
            bool(_author_name_pattern(name).search(block.get("raw_text", "")))
            for name in author_names
        ),
        default=None,
    )
    if not author_block:
        return None

    raw_author_line = clean_text(author_block.get("raw_text", ""))
    occurrences = []
    for author_index, author_name in enumerate(author_names):
        matches = list(_author_name_pattern(author_name).finditer(raw_author_line))
        if len(matches) != 1:
            return None
        match = matches[0]
        occurrences.append((author_index, match.start(), match.end()))
    if [item[0] for item in sorted(occurrences, key=lambda item: item[1])] != list(range(len(author_names))):
        return None

    block_x = float(author_block.get("x", 0) or 0)
    block_width = max(
        float(author_block.get("bbox", [block_x, 0, block_x, 0])[2]) - block_x,
        1.0,
    )
    raw_width = max(len(raw_author_line), 1)
    author_end_x = {
        author_index: block_x + (end / raw_width) * block_width
        for author_index, _start, end in occurrences
    }
    author_markers = {normalize_name(name): [] for name in author_names}
    for block in blocks:
        raw = clean_text(block.get("raw_text", ""))
        marker_chars = list(dict.fromkeys(
            char for char in raw if char in AFFILIATION_MARKERS
        ))
        if not marker_chars or block is author_block:
            continue
        if abs(float(block.get("y", 0) or 0) - float(author_block.get("y", 0) or 0)) > 15:
            continue
        marker_x = float(block.get("x", 0) or 0)
        author_index = min(author_end_x, key=lambda index: abs(author_end_x[index] - marker_x))
        if abs(author_end_x[author_index] - marker_x) <= 30:
            target = author_markers[normalize_name(author_names[author_index])]
            target.extend(marker for marker in marker_chars if marker not in target)

    definitions = _extract_block_affiliation_definitions(blocks, author_block)
    note_markers = _extract_affiliation_note_markers(
        pdf_context,
        author_names,
        author_markers=author_markers,
        definitions=definitions,
    )
    affiliation_markers = set(definitions)
    used_markers = set().union(*(set(value) for value in author_markers.values())) - note_markers
    if not used_markers or used_markers != affiliation_markers:
        return None

    affiliations_by_author = {}
    for name_key, markers in author_markers.items():
        selected = [definitions[marker] for marker in markers if marker in affiliation_markers]
        if selected:
            affiliations_by_author[name_key] = _dedupe_exact_affiliations(selected)

    if set(affiliations_by_author) != {
        normalize_name(name) for name in author_names
    }:
        return None

    evidence_lines = [raw_author_line]
    evidence_lines.extend(definitions.values())
    return {
        "affiliations_by_author": affiliations_by_author,
        "author_markers": {
            key: list(value) for key, value in author_markers.items()
        },
        "symbol_affiliations": definitions,
        "evidence_lines": dedupe_affiliations(evidence_lines),
        "additional_affiliations": _extract_affiliation_note_values(
            pdf_context,
            author_names,
        ),
        "replace_existing": True,
        "affiliation_source": "pdf_detached_symbol_affiliation",
    }


def _extract_block_affiliation_definitions(blocks, author_block):
    result = {}
    author_y = float(author_block.get("y", 0) or 0)
    abstract_y = max(
        (
            float(block.get("y", 0) or 0)
            for block in blocks
            if clean_text(block.get("raw_text", "")).lower().startswith("abstract")
        ),
        default=0.0,
    )
    marker_blocks = []
    for block in blocks:
        raw = clean_text(block.get("raw_text", ""))
        markers = [char for char in raw if char in AFFILIATION_MARKERS]
        if not markers or float(block.get("y", 0) or 0) >= author_y - 2:
            continue
        if abstract_y and float(block.get("y", 0) or 0) <= abstract_y:
            continue
        if EMAIL_RE.search(raw) or "@" in raw:
            continue
        marker_blocks.append((block, markers))

    for marker_block, markers in marker_blocks:
        marker_y = float(marker_block.get("y", 0) or 0)
        candidates = [
            block for block in blocks
            if marker_y - 16 <= float(block.get("y", 0) or 0) < marker_y
            and block is not marker_block
            and not EMAIL_RE.search(block.get("raw_text", ""))
            and "@" not in block.get("raw_text", "")
            and _looks_like_symbol_affiliation(block.get("raw_text", ""))
        ]
        if not candidates:
            continue
        org_block = min(candidates, key=lambda block: marker_y - float(block.get("y", 0) or 0))
        org_text = clean_text(org_block.get("raw_text", ""))
        org_x = float(org_block.get("x", 0) or 0)
        org_width = max(
            float(org_block.get("bbox", [org_x, 0, org_x, 0])[2]) - org_x,
            1.0,
        )
        marker_positions = []
        for other_block, other_markers in marker_blocks:
            if abs(float(other_block.get("y", 0) or 0) - marker_y) <= 3:
                marker_positions.extend(
                    (float(other_block.get("x", 0) or 0), marker)
                    for marker in other_markers
                )
        marker_positions.sort()
        if len(marker_positions) <= 1:
            for marker in markers:
                value = _clean_symbol_affiliation(org_text)
                if marker in result and compact_alpha(result[marker]) != compact_alpha(value):
                    return {}
                result[marker] = value
            continue

        for index, (marker_x, marker) in enumerate(marker_positions):
            if index + 1 < len(marker_positions):
                next_x = marker_positions[index + 1][0]
                cut = round((next_x - org_x) / org_width * len(org_text))
                value = org_text[:cut] if index == 0 else org_text[round((marker_x - org_x) / org_width * len(org_text)):cut]
            else:
                start = round((marker_x - org_x) / org_width * len(org_text)) if index else 0
                value = org_text[start:]
            value = _clean_symbol_affiliation(value)
            if value and looks_like_org(value):
                if marker in result and compact_alpha(result[marker]) != compact_alpha(value):
                    return {}
                result[marker] = value
    return result


def _looks_like_symbol_affiliation(text):
    text = clean_text(text)
    return bool(
        text
        and (
            looks_like_org(text)
            or ACRONYM_ORG_RE.search(text)
        )
    )


def _extract_affiliation_note_markers(pdf_context, author_names, author_markers=None, definitions=None):
    markers = set()
    for line in _affiliation_note_lines(pdf_context):
        if not AFFILIATION_NOTE_RE.search(line):
            continue
        markers.update(char for char in line if char in AFFILIATION_MARKERS)
        if author_markers:
            for name in author_names:
                if not _line_contains_author(line, name):
                    continue
                candidate = set(author_markers.get(normalize_name(name), []))
                if definitions is not None:
                    candidate -= set(definitions)
                markers.update(candidate)
    return markers


def _extract_affiliation_note_values(pdf_context, author_names):
    result = {}
    for line in _affiliation_note_lines(pdf_context):
        if not AFFILIATION_NOTE_RE.search(line):
            continue
        name = next((name for name in author_names if _line_contains_author(line, name)), "")
        if not name:
            continue
        match = re.search(
            r"but\s*was\s*at\s*(.+?)(?:\.|$)",
            line,
            flags=re.IGNORECASE,
        )
        if not match:
            continue
        value = _clean_symbol_affiliation(match.group(1))
        if value and looks_like_org(value):
            result.setdefault(normalize_name(name), []).append(value)
    return result


def _affiliation_note_lines(pdf_context):
    result = []
    sources = [
        pdf_context.first_page_lines or [],
        list((pdf_context.page_lines or {}).get(1, [])),
        list((pdf_context.pypdf_page_lines or {}).get(1, [])),
    ]
    for lines in sources:
        for index, raw_line in enumerate(lines):
            line = clean_text(raw_line)
            if not AFFILIATION_NOTE_RE.search(line):
                continue
            if index + 1 < len(lines) and not line.rstrip().endswith("."):
                line = clean_text(f"{line} {lines[index + 1]}")
            if line and line not in result:
                result.append(line)
    return result


def _line_contains_author(line, author_name):
    return bool(
        _author_name_pattern(author_name).search(line)
        or compact_alpha(author_name) in compact_alpha(line)
    )


def _header_line_sources(pdf_context):
    sources = []
    for raw_lines in [
        pdf_context.preabstract_lines or pdf_context.first_page_lines,
        (pdf_context.pypdf_page_lines or {}).get(1, []),
    ]:
        lines = []
        for raw_line in raw_lines or []:
            line = clean_text(raw_line)
            if not line:
                continue
            if line.lower().startswith(("abstract", "keywords", "1 introduction", "introduction")):
                break
            lines.append(line)
        if lines and lines not in sources:
            sources.append(lines)
    return sources


def _parse_default_and_symbol_lines(author_names, lines):
    occurrences = []
    for author_index, author_name in enumerate(author_names):
        pattern = _author_name_pattern(author_name)
        matches = [
            (line_index, match.start(), match.end())
            for line_index, line in enumerate(lines)
            for match in pattern.finditer(line)
        ]
        if len(matches) != 1:
            return None
        occurrences.append((author_index, *matches[0]))

    if [item[0] for item in sorted(occurrences, key=lambda item: (item[1], item[2]))] != list(range(len(author_names))):
        return None
    author_line_indexes = [item[1] for item in occurrences]
    if max(author_line_indexes) - min(author_line_indexes) > 3:
        return None

    role_markers = _role_semantic_markers(lines)
    author_markers = {}
    for author_index, line_index, start, end in occurrences:
        line = lines[line_index]
        same_line_next = min(
            (
                other_start
                for _, other_line, other_start, _ in occurrences
                if other_line == line_index and other_start > start
            ),
            default=len(line),
        )
        tail = line[end:same_line_next]
        trailing = re.match(
            rf"^[\s,;:()]*([{re.escape(AFFILIATION_MARKERS)}]+)",
            tail,
        )
        markers = list(dict.fromkeys(trailing.group(1))) if trailing else []
        if not markers:
            prefix = line[:start]
            leading = re.search(
                rf"(?:^|[,;])\s*([{re.escape(AFFILIATION_MARKERS)}]+)\s*$",
                prefix,
            )
            markers = list(dict.fromkeys(leading.group(1))) if leading else []
        if set(markers) & role_markers:
            return None
        author_markers[normalize_name(author_names[author_index])] = markers

    used_markers = set().union(*(set(value) for value in author_markers.values()))
    if not used_markers:
        return None
    all_authors_have_markers = all(author_markers.values())

    affiliation_start = max(author_line_indexes) + 1
    affiliation_lines = []
    for line in lines[affiliation_start:]:
        if EMAIL_RE.search(line) or "@" in line:
            break
        if ROLE_TEXT_RE.search(line):
            continue
        affiliation_lines.append(line)
    if not affiliation_lines:
        return None

    affiliation_text = clean_text(" ".join(affiliation_lines))
    marker_pattern = re.compile(rf"([{re.escape(AFFILIATION_MARKERS)}])\s*")
    definitions = list(marker_pattern.finditer(affiliation_text))
    if not definitions:
        return None

    base_affiliation = _clean_symbol_affiliation(affiliation_text[:definitions[0].start()])
    if not all_authors_have_markers and (
        not base_affiliation or not looks_like_org(base_affiliation)
    ):
        return None
    if all_authors_have_markers and base_affiliation:
        return None

    symbol_affiliations = {}
    for index, match in enumerate(definitions):
        marker = match.group(1)
        end = definitions[index + 1].start() if index + 1 < len(definitions) else len(affiliation_text)
        candidate = _clean_symbol_affiliation(affiliation_text[match.end():end])
        if marker in symbol_affiliations or ROLE_TEXT_RE.search(candidate):
            return None
        if candidate and looks_like_org(candidate):
            symbol_affiliations[marker] = candidate

    if used_markers != set(symbol_affiliations):
        return None

    affiliations_by_author = {}
    for name_key, markers in author_markers.items():
        if markers:
            affiliations_by_author[name_key] = _dedupe_exact_affiliations(
                [symbol_affiliations[marker] for marker in markers]
            )
        else:
            affiliations_by_author[name_key] = [base_affiliation]

    return {
        "affiliations_by_author": affiliations_by_author,
        "author_markers": author_markers,
        "base_affiliation": base_affiliation,
        "symbol_affiliations": symbol_affiliations,
        "evidence_lines": [
            lines[index]
            for index in sorted(set(author_line_indexes))
        ] + affiliation_lines,
        "replace_existing": all_authors_have_markers,
        "affiliation_source": (
            "pdf_complete_symbol_affiliation"
            if all_authors_have_markers
            else "pdf_default_symbol_affiliation"
        ),
    }


def _author_name_pattern(author_name):
    parts = [re.escape(part) for part in clean_text(author_name).split()]
    return re.compile(r"(?<![A-Za-z])" + r"\s+".join(parts) + r"(?![A-Za-z])", re.IGNORECASE)


def _role_semantic_markers(lines):
    result = set()
    for line in lines:
        if not ROLE_TEXT_RE.search(line):
            continue
        result.update(re.findall(rf"[{re.escape(AFFILIATION_MARKERS)}]", line))
    return result


def _clean_symbol_affiliation(text):
    text = clean_text(text).strip(" ,;:()")
    text = re.sub(r"\s+,", ",", text)
    return text


def _dedupe_exact_affiliations(affiliations):
    result = []
    seen = set()
    for affiliation in affiliations:
        value = clean_text(affiliation)
        key = compact_alpha(value)
        if value and key and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _equivalent_affiliation_lists(left, right):
    left_keys = {compact_alpha(value) for value in left if compact_alpha(value)}
    right_keys = {compact_alpha(value) for value in right if compact_alpha(value)}
    if left_keys == right_keys:
        return True
    return len(left_keys) == len(right_keys) == 1 and (
        next(iter(left_keys)) in next(iter(right_keys))
        or next(iter(right_keys)) in next(iter(left_keys))
    )


def _exact_affiliation_lists(left, right):
    return {
        compact_alpha(value) for value in left if compact_alpha(value)
    } == {
        compact_alpha(value) for value in right if compact_alpha(value)
    }


def _extract_grouped_emails(page_text):
    pattern = re.compile(
        r"\{(?P<parts>[^}]+)\}\s*(?P<suffix>@?[A-Za-z0-9.\-]+\.[A-Za-z]{2,})"
    )
    groups = []
    for match in pattern.finditer(page_text):
        suffix = clean_text(match.group("suffix"))
        values = []
        for raw_part in match.group("parts").split(","):
            part = clean_text(raw_part).strip(" ;")
            if not part:
                continue
            if suffix.startswith("@") and "@" not in part:
                email = f"{part}{suffix}"
                token = part
            elif not suffix.startswith("@") and "@" in part:
                email = f"{part}{suffix}"
                token = part.split("@", 1)[0]
            else:
                values = []
                break
            if not EMAIL_RE.fullmatch(email):
                values = []
                break
            values.append((token, email))
        if values:
            groups.append({"source": match.group(0), "values": values})
    return groups


def _fill_complete_ordered_group_emails(authors, author_markers, lines):
    page_text = "\n".join(lines)
    decisions = []
    author_names = [author.get("name", "") for author in authors]
    for group in _extract_grouped_emails(page_text):
        matches = [
            match_email_token_to_author(token, author_names)
            for token, _email in group["values"]
        ]
        if not all(matches) or len(set(map(normalize_name, matches))) != len(matches):
            continue
        targets = [
            next(author for author in authors if normalize_name(author.get("name", "")) == normalize_name(name))
            for name in matches
        ]
        emails = [email for _token, email in group["values"]]
        if any(
            author.get("email") and author.get("email", "").casefold() != email.casefold()
            for author, email in zip(targets, emails)
        ):
            continue
        filled_authors = []
        for author, email in zip(targets, emails):
            if author.get("email"):
                continue
            author["email"] = email
            filled_authors.append(author.get("name", ""))
        if filled_authors:
            decisions.append({
                "action": "fill_ordered_group_email_from_pdf",
                "stage": "field_level_pdf_merge",
                "field": "emails",
                "authors": filled_authors,
                "source": group["source"],
            })
    return decisions


def _organization_email_domain(email):
    match = EMAIL_RE.fullmatch(clean_text(email))
    if not match:
        return ""
    domain = email.rsplit("@", 1)[-1].lower().rstrip(".")
    if domain in PUBLIC_EMAIL_DOMAINS:
        return ""
    parts = domain.split(".")
    if len(parts) < 2:
        return ""
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in {
        "ac", "com", "edu", "gov", "net", "org",
    }:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _looks_like_domain_fill_author(name):
    parts = clean_text(name).split()
    if len(parts) < 2:
        return False
    for part in parts:
        letters = part.replace("-", "").replace("'", "").replace(".", "")
        if not letters or not all(char.isalpha() for char in letters):
            return False
    return True


def apply_email_domain_affiliations(authors):
    """Fill a blank affiliation from a unique same-paper institutional domain.

    A seed must have one directly extracted affiliation. Multiple affiliations,
    public mailbox providers, conflicting domain mappings, and chained inferred
    values are deliberately excluded.
    """
    direct_sources = {
        "author_node", "ccs_pdf", "ieee_pdf", "ndss_pdf", "official",
        "pdf_complete_symbol_affiliation", "pdf_default_symbol_affiliation",
        "pdf_detached_symbol_affiliation", "pdf_footnote", "pdf_layout",
        "usenix_pdf",
    }
    candidates = {}
    seeds = {}
    for author in authors or []:
        domain = _organization_email_domain(author.get("email", ""))
        affiliations = dedupe_affiliations(author.get("affiliations", []))
        if (
            not domain
            or len(affiliations) != 1
            or author.get("affiliation_source", "") not in direct_sources
        ):
            continue
        key = compact_alpha(affiliations[0])
        candidates.setdefault(domain, {})[key] = affiliations[0]
        seeds.setdefault((domain, key), []).append(author.get("name", ""))

    unique_by_domain = {
        domain: next(iter(values.items()))
        for domain, values in candidates.items()
        if len(values) == 1
    }
    result = copy.deepcopy(authors)
    decisions = []
    for author in result:
        if author.get("affiliations") or not _looks_like_domain_fill_author(
            author.get("name", "")
        ):
            continue
        domain = _organization_email_domain(author.get("email", ""))
        if domain not in unique_by_domain:
            continue
        key, affiliation = unique_by_domain[domain]
        author["affiliations"] = [affiliation]
        author["affiliation_source"] = "email_domain_same_paper"
        decisions.append({
            "action": "fill_affiliation_from_email_domain",
            "stage": "field_level_pdf_merge",
            "field": "affiliations",
            "author": author.get("name", ""),
            "selected": [affiliation],
            "email_domain": domain,
            "seed_authors": seeds.get((domain, key), []),
        })
    return result, decisions, []


def _matching_header_block_ids(pdf_context, author_names, evidence_lines):
    needles = [compact_alpha(value) for value in author_names + evidence_lines]
    result = []
    blocks = (pdf_context.page_blocks or {}).get(1, [])
    abstract_y = max(
        (
            float(block.get("y", 0) or 0)
            for block in blocks
            if clean_text(block.get("raw_text", "")).lower().startswith("abstract")
        ),
        default=0.0,
    )
    for block in blocks:
        if abstract_y and float(block.get("y", 0) or 0) <= abstract_y:
            continue
        raw_text = clean_text(block.get("raw_text", ""))
        if "@" in raw_text or EMAIL_RE.search(raw_text):
            continue
        block_text = compact_alpha(raw_text)
        if len(block_text) >= 5 and any(
            block_text in needle or needle in block_text
            for needle in needles
            if len(needle) >= 5
        ):
            result.append(block.get("block_id", ""))
    return [value for value in result if value]


def extract_author_footnote_affiliations(pdf_context, author_names):
    lines = pdf_context.preabstract_lines or pdf_context.first_page_lines
    if not lines or not author_names:
        return {}
    affiliation_map = {}
    for index, line in enumerate(lines):
        for author_name in author_names:
            pattern = re.compile(
                rf"^(?:\*?\s*Corresponding Author:\s*)?{re.escape(author_name)}\s*:\s*(.+)$",
                re.IGNORECASE,
            )
            match = pattern.match(line)
            if not match:
                continue
            candidate = match.group(1)
            if index + 1 < len(lines) and "e-mail" not in candidate.lower() and "email" not in candidate.lower():
                next_line = lines[index + 1]
                next_is_author = any(
                    re.match(
                        rf"^(?:\*?\s*Corresponding Author:\s*)?{re.escape(name)}\s*:",
                        next_line,
                        re.IGNORECASE,
                    )
                    for name in author_names
                )
                if not next_is_author and not re.match(
                    r"^(?:Abstract:|Keywords:|DOI\b|Received\b|\d+\s+\w+)", next_line
                ):
                    candidate = clean_text(candidate + " " + next_line)
            affiliation = extract_affiliation_text_fragment(candidate)
            if affiliation:
                affiliation_map[normalize_name(author_name)] = affiliation
            break
    return affiliation_map


def extract_usenix_style_affiliations(pdf_context, author_names):
    if not author_names:
        return {}
    lines = pdf_context.preabstract_lines or pdf_context.first_page_lines
    if not lines or not any("usenix" in line.lower() for line in lines[:12]):
        return {}
    numbered_affiliations = sum(
        bool(re.match(r"^\d+\s+", line) and looks_like_org(line))
        for line in lines[:12]
    )
    if numbered_affiliations >= 2:
        return {}

    author_block = clean_text(" ".join(pdf_context.author_lines))
    if not author_block:
        return {}
    affiliation_map = {}
    for segment in [item.strip() for item in author_block.split(";") if item.strip()]:
        parts = [part.strip() for part in segment.split(",") if part.strip()]
        if len(parts) < 2:
            continue
        institution_parts, author_parts = _split_usenix_segment(parts)
        if not institution_parts or not author_parts:
            continue
        institution = clean_text(", ".join(institution_parts))
        if not institution or is_noise_text(institution):
            continue
        author_text = re.sub(r"\band\s+", ",", clean_text(", ".join(author_parts)))
        for name in [item.strip() for item in author_text.split(",") if item.strip()]:
            if len(name.split()) >= 2:
                affiliation_map[normalize_name(name)] = institution
    return affiliation_map


def extract_author_emails(pdf_context, author_names):
    page_text = "\n".join(pdf_context.email_lines + pdf_context.first_page_lines)
    if not page_text or not author_names:
        return {}
    email_map = {}
    for group in _extract_grouped_emails(page_text):
        for local, email in group["values"]:
            author_name = match_email_token_to_author(local, author_names)
            if author_name:
                email_map[normalize_name(author_name)] = email
    for email in EMAIL_RE.findall(page_text):
        local = email.rsplit("@", 1)[0]
        author_name = match_email_token_to_author(local, author_names)
        if author_name:
            email_map.setdefault(normalize_name(author_name), email)
    return email_map


def extract_affiliation_text_fragment(text):
    text = clean_text(text)
    if not text:
        return ""
    text = EMAIL_RE.sub("", text)
    text = EMAIL_LABEL_RE.sub("", text)
    text = re.sub(r"^\*?\s*corresponding author\s*:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^[A-Z][A-Za-z.\-']+(?:\s+[A-Z][A-Za-z.\-']+){0,4}\s*:\s*", "", text)
    text = re.sub(r"\s*[;,]?\s*(?:and\s+)?$", "", text).strip(" ,;:")
    text = strip_marker(text)
    if not text or is_noise_text(text):
        return ""
    return text if looks_like_org(text) else ""


def match_email_token_to_author(token, author_names):
    token_key = compact_alpha(token)
    if not token_key:
        return ""
    matches = []
    for author_name in author_names:
        parts = [
            compact_alpha(part)
            for part in ascii_fold(author_name).split()
            if compact_alpha(part)
        ]
        if len(parts) < 2:
            continue
        surname = parts[-1]
        given_parts = parts[:-1]
        full_name = "".join(parts)
        first_plus_surname = f"{given_parts[0]}{surname}" if given_parts else surname
        initials = "".join(part[:1] for part in given_parts)
        initials_plus_surname = f"{initials}{surname}"
        if (
            token_key == full_name
            or token_key == surname
            or surname.startswith(token_key)
            or token_key == first_plus_surname
            or full_name.startswith(token_key)
            or token_key == f"{surname}{initials}"
            or token_key.startswith(f"{surname}{initials}")
            or token_key == initials_plus_surname
            or token_key.startswith(initials_plus_surname)
        ):
            matches.append(author_name)
    return matches[0] if len(matches) == 1 else ""


def merge_orphan_affiliation_chunks(authors, raw_authors, pdf_context=None):
    if not authors or not raw_authors:
        return authors
    result_by_index = {author["_source_index"]: author for author in authors}
    real_indices = sorted(result_by_index)

    for index, raw_author in enumerate(raw_authors):
        if index in result_by_index:
            continue
        name = raw_author.get("name", "")
        email = raw_author.get("email", "")
        affiliations = raw_author.get("affiliations", [])
        next_affiliations = (
            raw_authors[index + 1].get("affiliations", [])
            if index + 1 < len(raw_authors)
            else []
        )
        if not _has_numbered_pdf_affiliation_evidence(name, next_affiliations, pdf_context):
            continue

        org_fragments = []
        orphan_affiliations = list(affiliations)
        if not affiliations:
            if not name or email:
                continue
            org_fragments.append(compact_initial_sequence(name))

        cursor = index + 1
        while cursor < len(raw_authors) and cursor not in result_by_index:
            next_author = raw_authors[cursor]
            next_name = next_author.get("name", "")
            next_email = next_author.get("email", "")
            next_affiliations = next_author.get("affiliations", [])
            if next_affiliations:
                orphan_affiliations.extend(next_affiliations)
                cursor += 1
                continue
            if next_name and is_org_name(next_name) and not next_email and not is_author_name_noise(next_name):
                org_fragments.append(compact_initial_sequence(next_name))
                cursor += 1
                continue
            break

        target = next(
            (
                result_by_index[real_index]
                for real_index in reversed(real_indices)
                if real_index < index and not result_by_index[real_index]["affiliations"]
            ),
            None,
        )
        if target is None:
            continue
        merged = _merge_affiliation_parts(org_fragments, orphan_affiliations)
        if not merged:
            continue
        target["affiliations"] = dedupe_affiliations(target["affiliations"] + merged)
        if target.get("affiliation_source") == "empty":
            target["affiliation_source"] = "orphan_affiliation_pdf_evidence"
    return authors


def assign_aligned_orphan_affiliations(authors, raw_authors):
    """Map a strict N-author/N-affiliation TEI tail by order."""
    if not authors or len(raw_authors) != len(authors) * 2:
        return authors
    if [author.get("_source_index") for author in authors] != list(range(len(authors))):
        return authors
    if any(author.get("affiliations") for author in authors):
        return authors
    orphan_nodes = raw_authors[len(authors):]
    if not all(
        not clean_text(node.get("name", ""))
        and not clean_text(node.get("email", ""))
        and node.get("affiliations")
        for node in orphan_nodes
    ):
        return authors
    for author, node in zip(authors, orphan_nodes):
        author["affiliations"] = dedupe_affiliations([
            _clean_ccs_publication_location_noise(item)
            for item in node.get("affiliations", [])
        ])
        author["affiliation_source"] = "aligned_orphan_affiliation"
    return authors


def dedupe_affiliations(affiliations):
    if len(affiliations) <= 1:
        return affiliations
    result = []
    for affiliation in affiliations:
        affiliation = clean_text(affiliation)
        if not affiliation:
            continue
        lower = affiliation.lower()
        if any(lower == existing.lower() or lower in existing.lower() for existing in result):
            continue
        contained_index = next(
            (index for index, existing in enumerate(result) if existing.lower() in lower),
            None,
        )
        if contained_index is not None:
            result[contained_index] = affiliation
        else:
            result.append(affiliation)
    return result


def looks_like_address_only_affiliation(text):
    text = clean_text(text)
    if not text or looks_like_org(text):
        return False
    return 1 <= len([part for part in text.split(",") if part.strip()]) <= 3


def _split_usenix_segment(parts):
    institution_parts = []
    author_parts = []
    found_institution = False
    for part in reversed(parts):
        if not found_institution and looks_like_org(part):
            institution_parts.insert(0, part)
            found_institution = True
            continue
        if not found_institution:
            author_parts.insert(0, part)
            continue
        words = part.split()
        likely_name = (
            len(words) >= 2
            and all(word[0].isupper() for word in words if len(word) > 1)
            and not looks_like_org(part)
        )
        if likely_name:
            author_parts.insert(0, part)
        elif len(words) <= 3 and not re.search(r"\band\b", part.lower()):
            institution_parts.insert(0, part)
        else:
            author_parts.insert(0, part)
    return institution_parts, author_parts


def _has_numbered_pdf_affiliation_evidence(name, affiliations, pdf_context):
    if not pdf_context or not name or not affiliations:
        return False
    candidates = [
        compact_alpha(f"{name} {affiliation}")
        for affiliation in affiliations
        if looks_like_address_only_affiliation(affiliation)
    ]
    lines = pdf_context.preabstract_lines or pdf_context.first_page_lines or []
    for line in lines:
        match = re.match(r"^\s*\d+\s+(.+?)\s*$", clean_text(line))
        if match and compact_alpha(match.group(1)) in candidates:
            return True
    return False


def _merge_affiliation_parts(org_fragments, orphan_affiliations):
    merged = []
    org_prefix = clean_text(" ".join(org_fragments))
    for affiliation in orphan_affiliations:
        affiliation = clean_text(affiliation)
        if not affiliation:
            continue
        if org_prefix and looks_like_address_only_affiliation(affiliation):
            merged.append(clean_text(f"{org_prefix}, {affiliation}"))
        else:
            merged.append(affiliation)
    if org_prefix and not merged:
        merged.append(org_prefix)
    return merged


def compact_initial_sequence(text):
    return re.sub(r"\b(?:[A-Z]\s+){1,}[A-Z]\b", lambda match: match.group(0).replace(" ", ""), text)


def _clean_ccs_publication_location_noise(text):
    text = clean_text(text)
    mainland_city = re.search(
        r"\b(?:Beijing|Shanghai|Shenzhen|Zhengzhou|Henan|Nanjing|Chengdu|Wuhan|Hunan|Guangdong)\b",
        text,
        re.IGNORECASE,
    )
    if re.search(r"\bChina\b", text, re.IGNORECASE) and mainland_city and re.search(
        r"\b(?:Taipei|Taiwan)\b", text, re.IGNORECASE
    ):
        text = re.sub(r"\b(?:Taipei|Taiwan)\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\bChina(?:\s*,?\s*China)+\b", "China", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+,", ",", text)
        text = re.sub(r",\s*,", ",", text)
    return clean_text(text).strip(" ,;")
