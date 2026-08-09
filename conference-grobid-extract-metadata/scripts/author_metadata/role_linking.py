import re

from author_metadata.config import EMAIL_RE, NS, ascii_fold, clean_text, compact_alpha, normalize_name
from author_metadata.tei_parser import get_node_text


ROLE_MARKERS = "*∗†‡§¶★✉"
ENCODED_ENVELOPE_MARKER = "encoded-envelope-b"
ROLE_TEXT_RE = re.compile(
    r"equal\s+contributions?|contribut(?:e|ed|ing)\s+equally|"
    r"co[- ]?first|shared\s+first|joint\s+first",
    re.IGNORECASE,
)
CORRESPONDING_TEXT_RE = re.compile(
    r"corresponding\s+authors?|author\s+for\s+correspondence|"
    r"correspondence\s+(?:should\s+be\s+)?addressed\s+to|"
    r"correspondence\s+can\s+be\s+sent\s+to|"
    r"to\s+whom\s+correspondence",
    re.IGNORECASE,
)
FIRST_N_RE = re.compile(r"\bfirst\s+(two|three|four|five|\d+)\s+authors?\b", re.IGNORECASE)
FIRST_ORDINAL_PAIR_RE = re.compile(r"\bfirst\s+and\s+second\s+authors?\b", re.IGNORECASE)
BOTH_AUTHORS_RE = re.compile(r"\bboth\s+authors?\b", re.IGNORECASE)
NUMBER_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5}


def extract_role_hints(root, pdf_context, author_names, author_emails=None):
    hints = {
        "corresponding_names": set(),
        "equal_contribution_names": set(),
        "equal_contribution": False,
        "role_evidence": [],
        "review_reasons": [],
    }
    note_texts = []
    if root is not None:
        note_texts = [
            get_node_text(note)
            for note in root.findall(".//tei:teiHeader//tei:note", NS)
            if get_node_text(note)
        ]
    pdf_lines = _dedupe_role_lines(
        list(getattr(pdf_context, "first_page_lines", []) or [])
        + list((getattr(pdf_context, "pypdf_page_lines", {}) or {}).get(1, []) or [])
        + list((getattr(pdf_context, "first_page_text", "") or "").splitlines())
    )
    combined_lines = _dedupe_role_lines(note_texts + pdf_lines)
    combined_text = "\n".join(combined_lines)
    hints["equal_contribution"] = bool(ROLE_TEXT_RE.search(combined_text))
    marker_map = _extract_author_marker_map(pdf_lines, author_names)
    email_map = _normalize_author_emails(author_names, author_emails)

    for line in _role_segments(combined_lines):
        equal_role = bool(ROLE_TEXT_RE.search(line))
        corresponding_role = bool(CORRESPONDING_TEXT_RE.search(line))
        _collect_equal_contribution_hints(line, author_names, hints)
        _collect_corresponding_hints(line, author_names, email_map, hints)
        leading_markers = _leading_role_markers(line)
        if leading_markers and equal_role:
            _link_marker_roles(marker_map, leading_markers, hints["equal_contribution_names"])
        if leading_markers and corresponding_role:
            _link_marker_roles(marker_map, leading_markers, hints["corresponding_names"])
        if equal_role or corresponding_role:
            hints["role_evidence"].append({
                "raw_text": line,
                "roles": [
                    role
                    for role, present in (
                        ("equal_contribution", equal_role),
                        ("corresponding_author", corresponding_role),
                    )
                    if present
                ],
                "markers": sorted(leading_markers),
            })

    if len(hints["equal_contribution_names"]) == 1 and author_names:
        sole_name = next(iter(hints["equal_contribution_names"]))
        first_name = normalize_name(author_names[0])
        equal_evidence = "\n".join(
            evidence["raw_text"]
            for evidence in hints["role_evidence"]
            if "equal_contribution" in evidence["roles"]
        )
        implies_joint_first = bool(re.search(
            r"joint\s+first|co[- ]?first|has\s+contributed\s+equally",
            equal_evidence,
            flags=re.IGNORECASE,
        ))
        if sole_name != first_name and implies_joint_first:
            hints["equal_contribution_names"].add(first_name)
        else:
            hints["equal_contribution_names"].clear()
            hints["review_reasons"].append({
                "code": "ambiguous_equal_contribution_scope",
                "stage": "role_linking",
                "field": "co_first_author",
                "reason": "role_text_resolved_to_only_one_author",
            })

    if hints["equal_contribution"] and not hints["equal_contribution_names"]:
        if not any(reason.get("code") == "ambiguous_equal_contribution_scope" for reason in hints["review_reasons"]):
            hints["review_reasons"].append({
                "code": "ambiguous_equal_contribution_scope",
                "stage": "role_linking",
                "field": "co_first_author",
                "reason": "role_text_found_without_explicit_names_or_first_N_scope",
            })
    return hints


def _role_segments(lines):
    segments = []
    for index, raw_line in enumerate(lines):
        line = clean_text(raw_line)
        if not line or not (ROLE_TEXT_RE.search(line) or CORRESPONDING_TEXT_RE.search(line)):
            continue
        split_lines = re.split(
            rf"(?<=[.!?])\s*(?=[{re.escape(ROLE_MARKERS)}])",
            line,
        )
        if len(split_lines) > 1:
            for split_line in split_lines:
                split_line = clean_text(split_line)
                if split_line and split_line not in segments:
                    segments.append(split_line)
            continue
        previous = clean_text(lines[index - 1]) if index else ""
        if previous and _should_join_role_line(previous, line):
            line = clean_text(f"{previous} {line}")
        if line not in segments:
            segments.append(line)
    return segments


def _should_join_role_line(previous, current):
    if _leading_role_markers(current):
        return False
    if current[:1].islower():
        return True
    return bool(re.search(r"\b(?:are|is|the)\s*$", previous, flags=re.IGNORECASE))


def _normalize_author_emails(author_names, author_emails):
    result = {normalize_name(name): set() for name in author_names}
    if isinstance(author_emails, dict):
        for name, values in author_emails.items():
            normalized = normalize_name(name)
            if normalized not in result:
                continue
            if isinstance(values, str):
                values = [values]
            result[normalized].update(
                email.casefold()
                for value in values or []
                for email in EMAIL_RE.findall(str(value))
            )
    elif author_emails:
        for name, value in zip(author_names, author_emails):
            result[normalize_name(name)].update(
                email.casefold() for email in EMAIL_RE.findall(str(value or ""))
            )
    return result


def _dedupe_role_lines(lines):
    result = []
    seen = set()
    for line in lines:
        line = clean_text(line)
        if not line:
            continue
        key = line.casefold()
        if key not in seen:
            seen.add(key)
            result.append(line)
    return result


def _role_compact(text):
    result = []
    for char in str(text or ""):
        if char in ROLE_MARKERS:
            result.append(char)
            continue
        folded = ascii_fold(char).casefold()
        result.extend(item for item in folded if item.isalnum())
    return "".join(result)


def _preabstract_lines(lines):
    result = []
    for line in lines:
        if re.match(r"^\s*(?:abstract|1\s+introduction)\b", line, flags=re.IGNORECASE):
            break
        result.append(line)
    return result


def _extract_author_marker_map(lines, author_names):
    marker_map = {normalize_name(name): set() for name in author_names}
    for line in _preabstract_lines(lines):
        line_key = _role_compact(line)
        occurrences = []
        for author_name in author_names:
            occurrence = _find_author_occurrence(line, author_name)
            if occurrence is None:
                continue
            start, end = occurrence
            occurrences.append((start, end, author_name))
        occurrences.sort()
        for index, (_start, end, author_name) in enumerate(occurrences):
            next_start = occurrences[index + 1][0] if index + 1 < len(occurrences) else len(line_key)
            tail = line_key[end:min(next_start, end + 16)]
            marker_map[normalize_name(author_name)].update(char for char in tail if char in ROLE_MARKERS)
            if _has_encoded_envelope_after_name(line, author_name):
                marker_map[normalize_name(author_name)].add(ENCODED_ENVELOPE_MARKER)
    return marker_map


def _find_author_occurrence(line, author_name):
    line_key = _role_compact(line)
    author_key = compact_alpha(author_name)
    if author_key:
        start = line_key.find(author_key)
        if start >= 0:
            return start, start + len(author_key)

    tokens = re.findall(r"[A-Za-z]+", ascii_fold(author_name))
    if len(tokens) < 2:
        return None
    token_patterns = [
        rf"{re.escape(token)}[A-Za-z]*" if len(token) == 1 else re.escape(token)
        for token in tokens
    ]
    match = re.search(
        r"\b" + r"[^A-Za-z]+".join(token_patterns) + r"\b",
        ascii_fold(line),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    start = len(_role_compact(ascii_fold(line)[:match.start()]))
    end = start + len(_role_compact(match.group(0)))
    return start, end


def _has_encoded_envelope_after_name(line, author_name):
    name_tokens = re.findall(r"[A-Za-z]+", ascii_fold(author_name))
    if not name_tokens:
        return False
    name_pattern = r"\W*".join(re.escape(token) for token in name_tokens)
    return bool(re.search(rf"\b{name_pattern}\s+B(?:\s|,|$)", ascii_fold(line)))


def _leading_role_markers(line):
    markers = {"✉"} if re.match(r"^\s*✉", line) else set()
    line = re.sub(r"^\s*(?:\(cid:\d+\)|☒|✉)\s*", "", line)
    prefix = re.match(rf"^\s*([{re.escape(ROLE_MARKERS)}]+)", line)
    if prefix:
        markers.update(prefix.group(1))
    if re.match(r"^\s*(?:B|\(cid:\d+\)|☒)\s*corresponding\s+authors?\b", line, flags=re.IGNORECASE):
        markers.add(ENCODED_ENVELOPE_MARKER)
    return markers


def _link_marker_roles(marker_map, role_markers, target_names):
    for normalized_name, author_markers in marker_map.items():
        if author_markers & role_markers:
            target_names.add(normalized_name)


def apply_author_roles(authors, role_hints, preserve_existing=False):
    corresponding_names = role_hints.get("corresponding_names", set())
    equal_contribution_names = role_hints.get("equal_contribution_names", set())
    first_name = normalize_name(authors[0]["name"]) if authors else ""
    is_co_first_scope = first_name in equal_contribution_names

    for author in authors:
        existing_first = bool(author.get("first_author")) if preserve_existing else False
        existing_co_first = bool(author.get("co_first_author")) if preserve_existing else False
        existing_equal = bool(author.get("equal_contribution")) if preserve_existing else False
        existing_corresponding = bool(author.get("corresponding")) if preserve_existing else False
        normalized_name = normalize_name(author["name"])
        author["first_author"] = author["order"] == 0 or existing_first
        author["co_first_author"] = existing_co_first
        author["equal_contribution"] = existing_equal
        author["corresponding"] = existing_corresponding or normalized_name in corresponding_names

    for author in authors:
        if normalize_name(author["name"]) not in equal_contribution_names:
            continue
        author["equal_contribution"] = True
        if is_co_first_scope:
            author["first_author"] = True
            author["co_first_author"] = True
    return authors


def match_author_reference(ref_text, author_name):
    ref_parts = [compact_alpha(part) for part in re.findall(r"[A-Za-z]+", ascii_fold(ref_text))]
    name_parts = [
        compact_alpha(part)
        for part in ascii_fold(author_name).split()
        if compact_alpha(part)
    ]
    if not ref_parts or len(name_parts) < 2:
        return False
    surname = name_parts[-1]
    if ref_parts[-1] != surname and not surname.startswith(ref_parts[-1]):
        return False
    ref_given = ref_parts[:-1]
    name_given = name_parts[:-1]
    if not ref_given:
        return True
    if len(ref_given) > len(name_given):
        return False
    for ref_part, name_part in zip(ref_given, name_given):
        if len(ref_part) == 1:
            if ref_part != name_part[:1]:
                return False
        elif not (ref_part == name_part or ref_part.startswith(name_part) or name_part.startswith(ref_part)):
            return False
    return True


def _collect_equal_contribution_hints(line, author_names, hints):
    if not ROLE_TEXT_RE.search(line):
        return
    count_match = FIRST_N_RE.search(line)
    if count_match:
        token = count_match.group(1).lower()
        count = NUMBER_WORDS.get(token, int(token) if token.isdigit() else 0)
        if 2 <= count <= len(author_names):
            hints["equal_contribution_names"].update(
                normalize_name(name) for name in author_names[:count]
            )
    elif FIRST_ORDINAL_PAIR_RE.search(line):
        hints["equal_contribution_names"].update(
            normalize_name(name) for name in author_names[:2]
        )
    elif BOTH_AUTHORS_RE.search(line) and len(author_names) == 2:
        hints["equal_contribution_names"].update(
            normalize_name(name) for name in author_names
        )

    equal_clause = ROLE_TEXT_RE.split(line, maxsplit=1)[0]
    for author_name in author_names:
        author_key = compact_alpha(author_name)
        if author_key and author_key in compact_alpha(equal_clause):
            hints["equal_contribution_names"].add(normalize_name(author_name))

    prefix = re.split(
        r"these authors contributed equally|contributed equally|equal contribution|co-first",
        line,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    references = [
        part.strip(" -,:;()")
        for part in re.split(r"\band\b|,", prefix)
        if part.strip(" -,:;()")
    ]
    for reference in references:
        for author_name in author_names:
            if match_author_reference(reference, author_name):
                hints["equal_contribution_names"].add(normalize_name(author_name))


def _collect_corresponding_hints(line, author_names, author_emails, hints):
    if not CORRESPONDING_TEXT_RE.search(line):
        return
    line_key = compact_alpha(line)
    line_emails = {email.casefold() for email in EMAIL_RE.findall(line)}
    for author_name in author_names:
        author_key = compact_alpha(author_name)
        if (
            (author_key and author_key in line_key)
            or _find_author_occurrence(line, author_name) is not None
        ):
            hints["corresponding_names"].add(normalize_name(author_name))
            continue
        normalized_name = normalize_name(author_name)
        if line_emails & author_emails.get(normalized_name, set()):
            hints["corresponding_names"].add(normalized_name)
            continue
        for reference in re.split(r"\band\b|,|:|;", line, flags=re.IGNORECASE):
            if match_author_reference(reference.strip(), author_name):
                hints["corresponding_names"].add(normalize_name(author_name))
