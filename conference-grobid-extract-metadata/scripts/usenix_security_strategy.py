import re

import metadata_strategy_common as common


BAD_AUTHOR_TERMS = {
    "university", "school", "department", "college", "institute",
    "faculty", "laboratory", "center", "centre", "law",
}
ORG_MARKERS = (
    "university", "institute", "school", "college", "research",
    "group", "cispa", "norton", "harvard", "worcester", "chapel",
    "laboratory", "ministry", "computing", "systems", "eth", "eurecom",
    "fraunhofer", "rwth", "universiteit", "ut austin", "vu amsterdam",
    "leibniz", "paderborn", "george washington",
    "uiuc", "georgia tech", "uc berkeley", "carnegie mellon",
    "university of washington", "univ rennes", "cnrs", "irisa",
    "alpha lab", "360", "internet security center", "max planck",
    "indian institute", "tu wien", "common prefix", "crrc", "tengen",
    "sangfor", "cornell tech", "bloomberg", "terraverum",
    "university of florida",
)
COUNTRY_TERMS = (
    "USA", "United States", "Canada", "China", "Germany", "Denmark",
    "Singapore", "Korea", "South Korea", "Japan", "Australia", "UK",
    "United Kingdom", "France", "Switzerland", "The Netherlands", "Netherlands", "Italy",
    "Spain", "Sweden", "Finland", "Norway", "Israel", "India",
    "Hong Kong", "Taiwan",
)
NAME_PARTICLES = {"da", "de", "del", "der", "di", "du", "la", "le", "van", "von"}


def _clean_text(text):
    return " ".join(str(text or "").split()).strip()


def _dedupe(items):
    result = []
    seen = set()
    for item in items:
        item = _clean_text(item)
        if not item:
            continue
        key = item.lower()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _looks_like_org(text):
    lower = _clean_text(text).lower()
    return any(marker in lower for marker in ORG_MARKERS)


def _extract_country(text):
    text = _clean_text(text)
    for country in COUNTRY_TERMS:
        if re.search(rf"\b{re.escape(country)}\b", text, flags=re.IGNORECASE):
            return country
    return ""


def _append_country(affiliation, country):
    affiliation = _clean_text(affiliation)
    country = _clean_text(country)
    if not affiliation or not country:
        return affiliation
    if re.search(rf"\b{re.escape(country)}\b", affiliation, flags=re.IGNORECASE):
        return affiliation
    return f"{affiliation}, {country}"


def _comma_before_trailing_country(text):
    return common.comma_before_trailing_country(text, COUNTRY_TERMS)


def _looks_like_email_line(text):
    text = _clean_text(text)
    return "@" in text or bool(re.search(r"\{[^}]+\}@", text))


def _extract_email(text):
    match = re.search(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", _clean_text(text))
    return match.group(0) if match else ""


def _strip_email_label(text):
    text = re.sub(r"\bE-?mail\s*:\s*[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", "", _clean_text(text), flags=re.IGNORECASE)
    text = re.sub(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", "", text)
    return _clean_text(text.strip(" ,;."))


def _looks_like_author_name(text):
    text = _clean_author_name(text)
    if not text or "," in text or len(text) > 90 or _extract_country(text) or _looks_like_org(text):
        return False
    tokens = re.findall(r"[^\W\d_][^\W\d_'.-]*", text)
    if len(tokens) < 2 or len(tokens) > 5:
        return False
    return all(token[:1].isupper() or token.lower() in NAME_PARTICLES for token in tokens)


def _clean_author_name(text):
    text = _clean_text(text)
    text = re.sub(r"^[,;\s]+", "", text)
    text = re.sub(r"\band\b\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[\d∗*⋆†‡§¶]+", "", text)
    return common.clean_author_name(text)


def _extract_author_refs(author_text):
    refs = []
    pattern = re.compile(
        r"([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,4})"
        r"([0-9]+(?:,[0-9]+)*)[∗*]?"
    )
    for match in pattern.finditer(author_text):
        name = _clean_author_name(match.group(1))
        if _looks_like_author_name(name):
            refs.append((name, [ref for ref in match.group(2).split(",") if ref]))
    return refs


def _split_author_line(line):
    line = _clean_text(line)
    if re.search(r"[A-Za-z]\d", line):
        return _extract_author_refs(line)
    refs = []
    for part in re.split(r",|\band\b", line):
        name = _clean_author_name(part)
        if _looks_like_author_name(name):
            refs.append((name, []))
    return refs


def _has_numbered_author_refs(line):
    return bool(_extract_author_refs(line))


def _has_unnumbered_author_list(line):
    if re.search(r"[A-Za-z]\d", line):
        return False
    return ("," in line or re.search(r"\band\b", line, flags=re.IGNORECASE)) and len(_split_author_line(line)) >= 2


def _has_symbol_author_refs(line):
    return len(common.extract_symbol_author_refs(line)) >= 2


def _parse_numbered_affiliation(line):
    line = _clean_text(line)
    if re.match(r"^\d+", line):
        matches = list(re.finditer(r"(\d+)\s*(.+?)(?=\s*,?\s*\d+\s*[A-Z]|$)", line))
    else:
        if _extract_author_refs(line):
            return []
        matches = [
            (match.group(2), match.group(1))
            for match in re.finditer(r"(.+?)\s*(\d+)(?=\s+[A-Z][^\d]+?\d+|$)", line)
        ]
    result = []
    for match in matches:
        if isinstance(match, tuple):
            ref, aff = match
        else:
            ref, aff = match.group(1), match.group(2)
        aff = _clean_text(aff)
        aff = re.split(rf"\s*[{re.escape(common.AFFILIATION_SYMBOLS)}]\s*(?:equal contribution|contributed equally|corresponding)", aff, maxsplit=1, flags=re.IGNORECASE)[0]
        if _looks_like_org(aff) or "," in aff:
            result.append((ref, aff))
    return result


def _parse_marker_affiliations(lines):
    affiliations = {}
    for line in lines:
        match = re.match(r"^([A-Z])\s+(.+)$", _clean_text(line))
        if not match:
            continue
        marker, affiliation = match.groups()
        affiliation = _normalize_affiliation(affiliation)
        if affiliation and _looks_like_org(affiliation):
            affiliations[marker] = affiliation
    return affiliations


def _parse_marker_author_tokens(text, markers):
    marker_set = set(markers)
    if not marker_set:
        return []
    text = _clean_text(text)
    text = re.sub(
        rf"(?<=[^\W\d_])([{''.join(re.escape(marker) for marker in sorted(marker_set))}])(?=\s|$)",
        r" \1",
        text,
    )
    tokens = text.split()
    refs = []
    current = []
    index = 0
    while index < len(tokens):
        token = tokens[index].strip(",;")
        if token in marker_set:
            markers_for_name = [token]
            index += 1
            while index < len(tokens) and tokens[index].strip(",;") in marker_set:
                markers_for_name.append(tokens[index].strip(",;"))
                index += 1
            name = _clean_author_name(" ".join(current))
            if _looks_like_author_name(name):
                refs.append((name, markers_for_name))
            current = []
            continue
        current.append(tokens[index])
        index += 1
    return refs


def _parse_letter_marker_second_page(preabstract):
    affiliation_start = next(
        (
            index for index, line in enumerate(preabstract)
            if re.match(r"^[A-Z]\s+", _clean_text(line)) and _looks_like_org(_clean_text(line)[2:])
        ),
        -1,
    )
    if affiliation_start < 2:
        return "", []
    marker_affiliations = _parse_marker_affiliations(preabstract[affiliation_start:])
    if len(marker_affiliations) < 2:
        return "", []

    best_start = -1
    best_refs = []
    for start in range(1, affiliation_start):
        refs = _parse_marker_author_tokens(" ".join(preabstract[start:affiliation_start]), marker_affiliations)
        if len(refs) > len(best_refs):
            best_start = start
            best_refs = refs
    if len(best_refs) < 2 or best_start < 1:
        return "", []

    authors = []
    for name, markers in best_refs:
        authors.append({
            "name": name,
            "email": "",
            "affiliations": _dedupe(marker_affiliations[marker] for marker in markers if marker in marker_affiliations),
        })
    return _clean_text(" ".join(preabstract[:best_start])), authors


def _parse_vertical_second_page(preabstract):
    title_lines = []
    cursor = 0
    while cursor + 1 < len(preabstract):
        line = preabstract[cursor]
        next_line = preabstract[cursor + 1]
        if (
            _looks_like_author_name(line)
            and not re.search(r"[A-Za-z]\d", line)
            and next_line
            and (
                _looks_like_org(next_line) or
                _extract_country(next_line) or
                _looks_like_email_line(next_line)
            )
        ):
            break
        title_lines.append(line)
        cursor += 1

    authors = []
    while cursor < len(preabstract):
        name_line = preabstract[cursor]
        if not _looks_like_author_name(name_line):
            cursor += 1
            continue
        affiliation_lines = []
        email = ""
        cursor += 1
        while cursor < len(preabstract):
            next_line = preabstract[cursor]
            if _looks_like_author_name(next_line):
                break
            if _looks_like_email_line(next_line):
                email = email or _extract_email(next_line)
                affiliation = _strip_email_label(next_line)
                if affiliation:
                    affiliation_lines.append(affiliation)
                cursor += 1
                continue
            country = _extract_country(next_line)
            if country and affiliation_lines:
                affiliation_lines[-1] = _append_country(affiliation_lines[-1], country)
            else:
                affiliation_lines.append(next_line)
            cursor += 1
        authors.append({
            "name": _clean_author_name(name_line),
            "email": email,
            "affiliations": _dedupe(
                _normalize_affiliation(affiliation)
                for affiliation in affiliation_lines
            ),
        })

    if len(authors) < 2:
        return "", []
    if not any(author.get("affiliations") for author in authors):
        tail_affiliations = []
        last_email_index = max(
            (index for index, line in enumerate(preabstract) if _looks_like_email_line(line)),
            default=-1,
        )
        for line in preabstract[last_email_index + 1:]:
            if _looks_like_email_line(line) or re.search(r"contributed equally|equal contribution|co-first", line, flags=re.IGNORECASE):
                continue
            if _looks_like_org(line) or _extract_country(line):
                tail_affiliations.append(line)
        shared_affiliation = _normalize_affiliation(" ".join(tail_affiliations))
        if shared_affiliation:
            for author in authors:
                author["affiliations"] = [shared_affiliation]
    return _clean_text(" ".join(title_lines)), authors


def _parse_usenix_second_page(pdf_pages):
    lines = list((pdf_pages or {}).get(2, []))
    if not lines:
        return "", []
    preabstract = []
    for line in lines:
        if line.lower().startswith("abstract"):
            break
        preabstract.append(line)
    if len(preabstract) < 3:
        return "", []

    marker_title, marker_authors = _parse_letter_marker_second_page(preabstract)
    if marker_authors:
        return marker_title, marker_authors

    vertical_title, vertical_authors = _parse_vertical_second_page(preabstract)
    if vertical_authors:
        return vertical_title, vertical_authors

    title_lines = []
    cursor = 0
    while cursor < len(preabstract):
        line = preabstract[cursor]
        next_line = preabstract[cursor + 1] if cursor + 1 < len(preabstract) else ""
        after_next_line = preabstract[cursor + 2] if cursor + 2 < len(preabstract) else ""
        next_line_continues_authors = (
            _has_unnumbered_author_list(next_line) and
            (
                _looks_like_org(after_next_line) or
                _extract_country(after_next_line) or
                common.parse_symbol_affiliation_line(after_next_line, _normalize_affiliation, _looks_like_org)
            )
        )
        if (
            (_has_numbered_author_refs(line) or _has_unnumbered_author_list(line) or _has_symbol_author_refs(line)) and
            (
                _looks_like_org(next_line) or
                _looks_like_email_line(next_line) or
                common.parse_symbol_affiliation_line(next_line, _normalize_affiliation, _looks_like_org) or
                _parse_numbered_affiliation(next_line) or
                _has_numbered_author_refs(next_line) or
                next_line_continues_authors or
                next_line.lstrip().startswith(",")
            )
        ):
            break
        title_lines.append(line)
        cursor += 1
    title = _clean_text(" ".join(title_lines))

    author_refs = []
    numbered_affiliations = {}
    sequential_affiliations = []
    while cursor < len(preabstract):
        line = preabstract[cursor]
        if (
            _split_author_line(line) and
            cursor + 1 < len(preabstract) and
            preabstract[cursor + 1].lstrip().startswith(",")
        ):
            line = _clean_text(line + " " + preabstract[cursor + 1])
            cursor += 1
        numbered_items = _parse_numbered_affiliation(line)
        if numbered_items:
            for ref, affiliation in numbered_items:
                numbered_affiliations[ref] = affiliation
            cursor += 1
            continue
        if cursor + 1 < len(preabstract):
            symbol_authors = common.parse_symbol_author_affiliations(
                line,
                preabstract[cursor + 1],
                _normalize_affiliation,
                _looks_like_org,
            )
            if symbol_authors:
                for author in symbol_authors:
                    author_refs.append((author["name"], []))
                    sequential_affiliations.append("; ".join(author["affiliations"]))
                cursor += 2
                continue
        if _looks_like_org(line):
            sequential_affiliations.append(line)
            cursor += 1
            continue
        refs = _split_author_line(line)
        if refs:
            author_refs.extend(refs)
            cursor += 1
            continue
        cursor += 1

    if not author_refs:
        return title, []

    authors = []
    required_refs = {
        ref for _, refs in author_refs for ref in refs if ref.isdigit()
    }
    if required_refs and not required_refs.issubset(numbered_affiliations):
        return title, []
    for index, (name, refs) in enumerate(author_refs):
        affiliations = []
        if refs and numbered_affiliations:
            affiliations = [numbered_affiliations[ref] for ref in refs]
        elif not refs and len(sequential_affiliations) == 1:
            affiliations = [sequential_affiliations[0]]
        elif index < len(sequential_affiliations):
            affiliations = [sequential_affiliations[index]]
        authors.append({
            "name": name,
            "email": "",
            "affiliations": _dedupe(_normalize_affiliation(aff) for aff in affiliations),
        })
    return title, authors


def _front_page_candidates(pdf_pages):
    lines = list((pdf_pages or {}).get(1, []))
    result = []
    for line in lines:
        lower = line.lower()
        if lower.startswith(("this paper is included", "open access", "34th usenix", "33rd usenix")):
            continue
        if re.search(r"^\w+\s+\d{1,2}-\d{1,2},\s+\d{4}\b", line):
            continue
        if re.search(r"\busenix security symposium\b|sponsored by usenix|proceedings of the|978-", lower):
            continue
        if lower.startswith(("https://", "http://", "www.")):
            break
        result.append(line)
    return result


def _parse_inline_author_affiliations(author_text):
    authors = []
    for segment in re.split(r";", _clean_text(author_text)):
        segment = _clean_text(segment)
        if "," not in segment:
            continue
        split_at = -1
        comma_positions = [match.start() for match in re.finditer(",", segment)]
        for position in reversed(comma_positions):
            if _looks_like_org(segment[position + 1:]):
                split_at = position
                break
        if split_at < 0:
            continue
        names_part = segment[:split_at]
        affiliation = segment[split_at + 1:]
        affiliation = _normalize_affiliation(affiliation)
        if not affiliation or not _looks_like_org(affiliation):
            continue
        names = [
            _clean_author_name(part)
            for part in re.split(r"\band\b|,", names_part)
            if _clean_author_name(part)
        ]
        names = [name for name in names if _looks_like_author_name(name)]
        for name in names:
            authors.append({
                "name": name,
                "email": "",
                "affiliations": [affiliation],
            })
    return authors


def _parse_usenix_front_page(pdf_pages):
    lines = _front_page_candidates(pdf_pages)
    if len(lines) < 2:
        return "", []

    start = -1
    for index, line in enumerate(lines):
        if "," not in line:
            continue
        tail = line.split(",", 1)[1]
        if _looks_like_org(tail) or ";" in line:
            start = index
            break
    if start < 1:
        return "", []

    title = _clean_text(" ".join(lines[:start]))
    author_text = _clean_text(" ".join(lines[start:]))
    authors = _parse_inline_author_affiliations(author_text)
    if len(authors) < 2 or not title:
        return "", []
    return title, authors


def _name_key(name):
    return re.sub(r"[^a-z]+", "", _clean_text(name).lower())


def _parse_symbol_roles(pdf_lines, author_names):
    lines = [_clean_text(line) for line in pdf_lines or []]
    author_names = [_clean_text(name) for name in author_names if _clean_text(name)]
    roles = {"corresponding_names": set(), "equal_contribution_names": set()}
    if not lines or not author_names:
        return roles

    corresponding_symbols = set()
    equal_symbols = set()
    for line in lines:
        compact = re.sub(r"\s+", " ", line)
        for symbol in re.findall(r"([*∗†‡§¶✉])\s*(?=Corresponding authors?|corresponding authors?)", compact, flags=re.IGNORECASE):
            corresponding_symbols.add(symbol)
        for symbol in re.findall(r"([*∗†‡§¶])\s*(?=Co-first authors?|co-first authors?|contributed equally|equal contribution)", compact, flags=re.IGNORECASE):
            equal_symbols.add(symbol)
        leading = re.match(r"^\s*([*∗†‡§¶✉])\s*(.+)$", compact)
        if leading:
            symbol, rest = leading.groups()
            if re.search(r"contributed equally|equal contribution|co-first", rest, flags=re.IGNORECASE):
                equal_symbols.add(symbol)
                refs = re.split(r"contributed equally|equal contribution|co-first", rest, maxsplit=1, flags=re.IGNORECASE)[0]
                for author_name in author_names:
                    parts = author_name.split()
                    first = parts[0] if parts else ""
                    if author_name in refs or (first and re.search(rf"\b{re.escape(first)}\b", refs)):
                        roles["equal_contribution_names"].add(_name_key(author_name))
            if re.search(r"corresponding authors?", rest, flags=re.IGNORECASE):
                corresponding_symbols.add(symbol)
                refs = re.split(r"corresponding authors?", rest, maxsplit=1, flags=re.IGNORECASE)[0]
                for author_name in author_names:
                    parts = author_name.split()
                    first = parts[0] if parts else ""
                    if author_name in refs or (first and re.search(rf"\b{re.escape(first)}\b", refs)):
                        roles["corresponding_names"].add(_name_key(author_name))

    if not corresponding_symbols and not equal_symbols:
        return roles

    preabstract = []
    for line in lines:
        if line.lower().startswith("abstract"):
            break
        preabstract.append(line)

    for line in preabstract:
        for author_name in author_names:
            match = re.search(rf"{re.escape(author_name)}\s*(?:[0-9,]+)?\s*([*∗†‡§¶✉]+)", line, flags=re.IGNORECASE)
            if not match:
                continue
            symbols = set(match.group(1))
            if symbols & corresponding_symbols:
                roles["corresponding_names"].add(_name_key(author_name))
            if symbols & equal_symbols:
                roles["equal_contribution_names"].add(_name_key(author_name))
    return roles


def _apply_symbol_roles(authors, pdf_lines):
    roles = _parse_symbol_roles(pdf_lines, [author.get("name", "") for author in authors])
    corresponding_names = roles["corresponding_names"]
    equal_names = roles["equal_contribution_names"]
    if not corresponding_names and not equal_names:
        return authors
    for author in authors:
        name_key = _name_key(author.get("name", ""))
        if name_key in corresponding_names:
            author["corresponding"] = True
        if name_key in equal_names:
            author["first_author"] = True
            author["co_first_author"] = True
            author["equal_contribution"] = True
    return authors


def _looks_like_false_author(name):
    tokens = re.findall(r"[A-Za-z]+", name.lower())
    if not tokens:
        return True
    if len(tokens) == 1 and tokens[0] in BAD_AUTHOR_TERMS:
        return True
    return any(token in BAD_AUTHOR_TERMS for token in tokens)


def _normalize_affiliation(text):
    text = common.strip_emails(text)
    text = re.sub(r"^\band\b\s*,?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(rf"\s*[{re.escape(common.AFFILIATION_SYMBOLS)}]\s*$", "", text)
    text = text.replace("Hong, Kong", "Hong Kong")
    text = re.sub(r"\bVrije Universiteit Amsterdam\s+Amsterdam\b", "Vrije Universiteit Amsterdam, Amsterdam", text)
    text = text.replace("L.P .", "L.P.")
    text = _comma_before_trailing_country(text.strip(" ,;"))
    text = text.replace("The, Netherlands", "The Netherlands")
    if text.lower() in BAD_AUTHOR_TERMS:
        return ""
    return text


def refine_title(title, **kwargs):
    pdf_pages = kwargs.get("pdf_pages") or {}
    pdf_title, pdf_authors = _parse_usenix_second_page(pdf_pages)
    front_title, front_authors = _parse_usenix_front_page(pdf_pages)
    if front_title and len(front_authors) > len(pdf_authors):
        return front_title
    if pdf_title:
        return pdf_title
    if front_title:
        return front_title
    return _clean_text(title)


def refine_authors(authors, **kwargs):
    pdf_pages = kwargs.get("pdf_pages") or {}
    pdf_lines = pdf_pages.get(2, []) or kwargs.get("pdf_lines") or []
    _, page2_authors = _parse_usenix_second_page(pdf_pages)
    _, front_authors = _parse_usenix_front_page(pdf_pages)
    pdf_authors = page2_authors
    if front_authors and len(front_authors) > len(page2_authors):
        pdf_authors = front_authors
        pdf_lines = pdf_pages.get(1, []) or pdf_lines
    if pdf_authors:
        rebuilt = []
        for order, author in enumerate(pdf_authors):
            rebuilt.append({
                "order": order,
                "name": author["name"],
                "email": author.get("email", ""),
                "affiliations": _dedupe(
                    _normalize_affiliation(affiliation)
                    for affiliation in author.get("affiliations", [])
                ),
                "affiliation_source": "usenix_pdf",
                "first_author": order == 0,
                "co_first_author": False,
                "equal_contribution": False,
                "corresponding": False,
            })
        return _apply_symbol_roles(rebuilt, pdf_lines)

    refined = []
    for author in authors:
        name = _clean_text(author.get("name", ""))
        if _looks_like_false_author(name):
            if refined and not refined[-1].get("affiliations"):
                refined[-1]["affiliations"] = [name]
            continue
        updated = dict(author)
        updated["affiliations"] = _dedupe(
            _normalize_affiliation(affiliation)
            for affiliation in author.get("affiliations", [])
        )
        refined.append(updated)
    return _apply_symbol_roles(refined, pdf_lines)
