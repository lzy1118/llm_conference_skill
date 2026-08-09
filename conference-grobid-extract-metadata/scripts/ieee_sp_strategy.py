import re

import metadata_strategy_common as common


ORG_MARKERS = (
    "university", "institute", "laboratory", "lab", "school",
    "college", "department", "center", "centre", "research",
    "technology", "purdue", "columbia", "xiamen", "riverside",
    "cambridge", "edinburgh", "toronto", "vector", "inria",
    "microsoft", "iit", "gandhinagar", "clustar", "csail",
    "distrinet", "leuven", "virginia tech", "tu wien", "cdl", "astra",
    "universit", "g.o.s.s.i.p", "feiyu", "qi zhi", "griffith",
    "google", "deepmind", "nvidia", "robust intelligence", "baidu", "hust",
    "ciise", "ericsson", "eth", "zurich", " inc", " corp", " corporation",
    " llc", " ltd", " limited", " company",
)
MARKERS = (":", ";")
COUNTRY_TERMS = (
    "USA", "United States", "Canada", "China", "Germany", "Denmark",
    "Singapore", "Korea", "South Korea", "Japan", "Australia", "UK",
    "United Kingdom", "France", "Switzerland", "Netherlands", "Italy",
    "Spain", "Sweden", "Finland", "Norway", "Israel", "India",
    "Hong Kong", "Taiwan",
)


def _clean_text(text):
    return " ".join(str(text or "").split()).strip()


def _clean_title_text(text):
    text = _clean_text(text)
    return re.sub(r"\s+([:;])", r"\1", text)


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


def _compact_alpha(text):
    return re.sub(r"[^a-z]+", "", _clean_text(text).lower())


def _compact_alpha_with_transliterations(text):
    text = _clean_text(text).lower()
    german = (
        text.replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )
    return {_compact_alpha(text), _compact_alpha(german)}


def _looks_like_contaminated_title(title, authors):
    if title.count(":") >= 2:
        return True
    if "\x00" in title or title.count(",") >= 4 or title.count(";") >= 1:
        return True
    author_names = [_clean_text(author.get("name", "")) for author in authors]
    surnames = [name.split()[-1] for name in author_names if len(name.split()) >= 2]
    hits = sum(1 for surname in surnames if surname and surname in title)
    return hits >= 2


def _truncate_title_on_author_marker(title, authors):
    cut_positions = []
    for author in authors:
        name = _clean_text(author.get("name", ""))
        if not name:
            continue
        idx = title.find(name)
        if idx > 0:
            cut_positions.append(idx)
    if cut_positions:
        return _clean_text(title[: min(cut_positions)]).rstrip(":,;")
    generic_marker = re.search(
        r"\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\s*:\s*(?:,|\u0000|\s)",
        title,
    )
    if generic_marker and generic_marker.start() > 20:
        return _clean_text(title[: generic_marker.start()]).rstrip(":,;")
    return _clean_text(title)


def _title_from_pdf_lines(pdf_lines):
    title_parts = []
    for line in pdf_lines[:8]:
        line = _clean_text(line)
        lower = line.lower()
        if not line:
            continue
        if any(marker in lower for marker in ("ieee", "symposium", "conference", "isbn")):
            continue
        if (
            lower.startswith(("abstract", "index terms", "introduction")) or
            _looks_like_email_line(line) or
            _looks_like_org_line(line) or
            _looks_like_author_name(line) or
            _extract_mixed_author_refs(line)
        ):
            break
        if line.count(",") >= 2:
            break
        title_parts.append(line)
    return _clean_title_text(" ".join(title_parts)).rstrip(":,;")


def _find_title_end_index(lines, title):
    title_key = _compact_alpha(title)
    if not title_key:
        return -1
    for start in range(min(12, len(lines))):
        combined = ""
        for end in range(start, min(start + 4, len(lines))):
            combined += _compact_alpha(lines[end])
            if title_key in combined:
                return end
    return -1


def _looks_like_email_line(text):
    text = _clean_text(text)
    return "@" in text or bool(re.search(r"\{[^}]+\}@", text))


def _looks_like_org_line(text):
    lower = _clean_text(text).lower().lstrip(":; ")
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


def _looks_like_author_name(text):
    text = _clean_text(common.normalize_detached_diacritics(text))
    if not text or len(text) > 80 or _extract_country(text) or _looks_like_org_line(text) or _looks_like_email_line(text):
        return False
    tokens = re.findall(r"[^\W\d_][^\W\d_]*(?:[.'-][^\W\d_]+)*", text)
    if len(tokens) < 2 or len(tokens) > 5:
        return False
    return sum(token[:1].isupper() for token in tokens) == len(tokens)


def _strip_affiliation_marker(text):
    return _clean_text(re.sub(r"^\s*[:;]\s*", "", text))


def _extract_numbered_author_refs(line):
    refs = []
    pattern = re.compile(
        r"([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,4})"
        r"\s*([0-9]+(?:\s*,\s*[0-9]+)*)"
    )
    for match in pattern.finditer(_clean_text(line)):
        name = _clean_text(match.group(1))
        if _looks_like_org_line(name):
            continue
        ref_list = [ref.strip() for ref in match.group(2).split(",") if ref.strip()]
        if len(name.split()) >= 2 and ref_list:
            refs.append((name, ref_list))
    return refs


def _extract_mixed_author_refs(line):
    refs = []
    ref_token = rf"(?:\d+|[{re.escape(common.AFFILIATION_SYMBOLS)}])"
    name_token = r"[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'.-]+"
    pattern = re.compile(
        rf"({name_token}(?:\s+{name_token}){{1,4}})"
        rf"\s*({ref_token}(?:\s*,?\s*{ref_token})*)"
    )
    for match in pattern.finditer(_clean_text(line)):
        name = _clean_text(match.group(1))
        if _looks_like_org_line(name):
            continue
        ref_list = re.findall(ref_token, match.group(2))
        if len(name.split()) >= 2 and ref_list:
            refs.append((name, ref_list))
    return refs


def _parse_numbered_affiliations(line):
    line = _strip_affiliation_marker(line)
    result = {}
    for match in re.finditer(
        rf"(\d+)\s*(.+?)(?=\s+(?:\d+\s*[A-Z]|[{re.escape(common.AFFILIATION_SYMBOLS)}]\s*[A-Z])|$)",
        line,
    ):
        affiliation = _clean_text(match.group(2))
        if affiliation:
            result[match.group(1)] = affiliation
    return result


def detect_ieee_layout(pdf_lines):
    lines = [_clean_text(line) for line in pdf_lines or []]
    lines = [line for line in lines if line]
    title = _title_from_pdf_lines(lines)
    if not title:
        return "unknown"

    title_index = _find_title_end_index(lines, title)
    if title_index < 0:
        return "unknown"

    preabstract = []
    for line in lines[title_index + 1:title_index + 12]:
        if line.lower().startswith(("abstract", "index terms", "introduction")):
            break
        preabstract.append(line)

    for index, line in enumerate(preabstract):
        if _extract_numbered_author_refs(line):
            following = " ".join(preabstract[index + 1:index + 3])
            if _parse_numbered_affiliations(following):
                return "numbered_inline"

    if any(("," in line or ";" in line) and not _looks_like_org_line(line) for line in preabstract[:3]):
        return "marker_inline"

    person_lines = [line for line in preabstract if _looks_like_author_name(line)]
    if len(person_lines) >= 2:
        return "vertical_with_email" if any(_looks_like_email_line(line) for line in preabstract) else "vertical_no_email"
    if len(person_lines) == 1:
        return "single_vertical"
    return "unknown"


def _parse_vertical_author_blocks(lines, start_index):
    authors = []
    current = None

    def flush():
        nonlocal current
        if current and current.get("name"):
            affiliations = _dedupe(current.get("affiliation_lines", []))
            current["affiliations"] = [", ".join(affiliations)] if affiliations else []
            current.pop("affiliation_lines", None)
            current["marker"] = current.get("marker") or ":"
            current["corresponding_marker"] = current.get("corresponding_marker", False)
            authors.append(current)
        current = None

    for line in lines[start_index:]:
        lower = line.lower()
        if lower.startswith(("abstract", "index terms", "introduction")):
            break
        if _looks_like_email_line(line):
            if current:
                current["email"] = line
            continue
        if _looks_like_author_name(line):
            flush()
            current = {
                "name": line.replace("\x00", " ").strip(),
                "email": "",
                "affiliation_lines": [],
                "marker": ":",
                "corresponding_marker": "\x00" in line,
            }
            continue
        if current:
            country = _extract_country(line)
            if country and current["affiliation_lines"]:
                current["affiliation_lines"][-1] = _append_country(current["affiliation_lines"][-1], country)
            else:
                current["affiliation_lines"].append(_strip_affiliation_marker(line))

    flush()
    return [author for author in authors if author.get("affiliations") or author.get("email")]


def _split_author_names(line):
    line = _clean_text(common.normalize_detached_diacritics(line))
    line = re.sub(r"\band\s+", ",", line, flags=re.IGNORECASE)
    names = []
    for raw_part in line.split(","):
        part = raw_part.replace("\x00", " ")
        part = re.sub(r"[\d∗*⋆†‡§¶]+", " ", part)
        part = re.sub(r"[^\w'. -]+", " ", part, flags=re.UNICODE)
        name = common.clean_author_name(part)
        name = re.sub(r"\s+", " ", name).strip(" :;,")
        if _looks_like_author_name(name):
            names.append(name)
    return names


def _parse_grouped_author_affiliation_blocks(lines, start_index):
    authors = []
    index = start_index
    while index < len(lines):
        line = _clean_text(lines[index])
        if line.lower().startswith(("abstract", "index terms", "introduction")):
            break

        names = []
        while index < len(lines):
            line = _clean_text(lines[index])
            if (
                not line or
                line.lower().startswith(("abstract", "index terms", "introduction")) or
                _looks_like_org_line(line) or
                _looks_like_email_line(line)
            ):
                break
            line_names = _split_author_names(line)
            if not line_names:
                break
            names.extend(line_names)
            index += 1
        if not names:
            index += 1
            continue

        affiliation_lines = []
        while index < len(lines):
            line = _clean_text(lines[index])
            if line.lower().startswith(("abstract", "index terms", "introduction")):
                break
            if _looks_like_email_line(line):
                index += 1
                continue
            next_names = _split_author_names(line)
            if next_names and not _looks_like_org_line(line):
                break
            if _looks_like_org_line(line) or _extract_country(line):
                affiliation_lines.append(line)
                index += 1
                continue
            break

        affiliation = _normalize_affiliation(" ".join(affiliation_lines))
        affiliations = [part.strip() for part in affiliation.split(";") if part.strip()]
        if not affiliations:
            continue
        for name in names:
            authors.append({
                "name": name,
                "marker": ":",
                "email": "",
                "corresponding_marker": False,
                "affiliations": affiliations,
            })

    return authors if len(authors) >= 2 else []


def _parse_stacked_author_blocks(lines, start_index):
    preabstract = []
    for line in lines[start_index:]:
        if line.lower().startswith(("abstract", "index terms", "introduction")):
            break
        preabstract.append(line)
    if sum(1 for line in preabstract if _looks_like_email_line(line)) < 2:
        return []
    first_email_index = next(
        (index for index, line in enumerate(preabstract) if _looks_like_email_line(line)),
        -1,
    )
    if first_email_index < 0 or not any(
        _split_author_names(line) and not _looks_like_email_line(line) and not _looks_like_org_line(line)
        for line in preabstract[first_email_index + 1:]
    ):
        return []

    authors = []
    pending_names = []
    affiliation_lines = []

    def flush(email_line=""):
        nonlocal pending_names, affiliation_lines
        if not pending_names:
            affiliation_lines = []
            return
        affiliation = _normalize_affiliation(" ".join(affiliation_lines))
        email_by_name = _extract_emails(email_line, [{"name": name} for name in pending_names]) if email_line else {}
        for name in pending_names:
            authors.append({
                "name": name,
                "marker": ":",
                "email": email_by_name.get(name, ""),
                "corresponding_marker": False,
                "affiliations": [affiliation] if affiliation else [],
            })
        pending_names = []
        affiliation_lines = []

    for line in preabstract:
        if _looks_like_email_line(line):
            flush(line)
            continue
        if pending_names:
            affiliation_lines.append(line)
            continue
        names = _split_author_names(line)
        if names and not _looks_like_org_line(line):
            pending_names = names
            continue
    flush()
    return authors if len(authors) >= 2 else []


def _split_affiliation_parts(text):
    text = _clean_text(text)
    text = re.sub(r"\s*,\s*\band\b\s+", "; ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*;\s*\band\b\s+", "; ", text, flags=re.IGNORECASE)
    text = re.sub(rf"\s*,\s*([{re.escape(common.AFFILIATION_SYMBOLS)}])", r"; \1", text)
    parts = []
    for raw_part in re.split(r";", text):
        part = _comma_before_trailing_country(raw_part)
        part = re.sub(r"^\band\b\s+", "", part, flags=re.IGNORECASE)
        part = re.sub(rf"^[{re.escape(common.AFFILIATION_SYMBOLS)}]+\s*", "", part)
        part = _comma_before_trailing_country(part.strip(" ,;"))
        if part:
            parts.append(part)
    return _dedupe(parts)


def _symbol_affiliations_with_base(affiliation_text):
    affiliation_text = _clean_text(affiliation_text)
    if not common.affiliation_symbol_tokens(affiliation_text):
        return [], {}
    first_symbol = re.search(rf"[{re.escape(common.AFFILIATION_SYMBOLS)}]", affiliation_text)
    base_affiliations = []
    if first_symbol:
        base_affiliations = _split_affiliation_parts(affiliation_text[:first_symbol.start()].strip(" ,;"))
    symbol_affiliations = common.parse_symbol_affiliation_line(
        affiliation_text,
        _normalize_affiliation,
        _looks_like_org_line,
    )
    return base_affiliations, symbol_affiliations


def _extract_ieee_author_block(pdf_lines):
    lines = [_clean_text(line) for line in pdf_lines or []]
    lines = [line for line in lines if line]
    title = _title_from_pdf_lines(lines)
    if not title:
        return [], {}, ""

    title_index = _find_title_end_index(lines, title)
    if title_index < 0:
        return [], {}, ""

    grouped_authors = _parse_grouped_author_affiliation_blocks(lines, title_index + 1)
    if grouped_authors:
        return grouped_authors, {}, ""

    stacked_authors = _parse_stacked_author_blocks(lines, title_index + 1)
    if stacked_authors:
        return stacked_authors, {}, ""

    author_line = ""
    affiliation_by_marker = {}
    email_line = ""

    for line in lines[title_index + 1:title_index + 14]:
        lower = line.lower()
        if lower.startswith(("abstract", "index terms", "introduction")):
            break
        if _looks_like_org_line(line):
            marker = line.lstrip()[:1]
            if marker not in MARKERS:
                marker = ":" if not affiliation_by_marker else ";"
            affiliation_by_marker[marker] = _clean_text(
                f"{affiliation_by_marker.get(marker, '')} {_strip_affiliation_marker(line)}"
            )
            if _looks_like_email_line(line):
                email_line = _clean_text(f"{email_line} {line}")
            continue
        if _looks_like_email_line(line):
            email_line = _clean_text(f"{email_line} {line}")
            continue
        if (
            "," in line or ";" in line or common.affiliation_symbol_tokens(line) or
            re.search(r"[A-Za-z]\d", line) or _extract_mixed_author_refs(line)
        ):
            if not author_line:
                author_line = line
            elif not affiliation_by_marker:
                author_line = _clean_text(f"{author_line} {line}")

    if not author_line:
        return _parse_vertical_author_blocks(lines, title_index + 1), {}, email_line

    affiliation_text = " ".join(affiliation_by_marker.values())
    numbered_refs = _extract_mixed_author_refs(author_line)
    numbered_affiliations = _parse_numbered_affiliations(affiliation_text)
    symbol_affiliations = common.parse_symbol_affiliation_line(
        affiliation_text,
        _normalize_affiliation,
        _looks_like_org_line,
    )
    if numbered_refs and numbered_affiliations:
        required_refs = {ref for _, refs in numbered_refs for ref in refs}
        if not required_refs.issubset(numbered_affiliations):
            return [], {}, email_line
        authors = []
        for name, refs in numbered_refs:
            affiliations = []
            for ref in refs:
                affiliations.append(numbered_affiliations[ref])
                if ref in symbol_affiliations:
                    affiliations.append(symbol_affiliations[ref])
            authors.append({
                "name": name,
                "marker": ":",
                "corresponding_marker": False,
                "affiliations": _dedupe(affiliations),
            })
        return authors, {}, email_line

    symbol_authors = common.parse_symbol_author_affiliations(
        author_line,
        affiliation_text,
        _normalize_affiliation,
        _looks_like_org_line,
    )
    if symbol_authors:
        authors = []
        for item in symbol_authors:
            authors.append({
                "name": item["name"],
                "marker": ":",
                "corresponding_marker": False,
                "affiliations": item["affiliations"],
            })
        return authors, {}, email_line

    authors = []
    for raw_part in author_line.split(","):
        part = _clean_text(raw_part)
        has_corresponding_marker = "\x00" in part
        part = part.replace("\x00", " ")
        symbols = common.affiliation_symbol_tokens(part)
        marker = ""
        marker_match = re.search(r"\s*([:;])\s*$", part)
        if marker_match:
            marker = marker_match.group(1)
            part = part[:marker_match.start()]
        name = _clean_text(re.sub(r"[^A-Za-z'.\- ]+", " ", part))
        name = common.clean_author_name(name)
        name = re.sub(r"\s+", " ", name).strip(" :;,")
        if len(name.split()) < 2:
            continue
        authors.append({
            "name": name,
            "marker": marker or ":",
            "corresponding_marker": has_corresponding_marker,
            "symbols": symbols,
        })

    base_affiliations, symbol_affiliations = _symbol_affiliations_with_base(affiliation_text)
    if symbol_affiliations and authors:
        for author in authors:
            author_symbols = author.get("symbols") or []
            affiliations = list(base_affiliations)
            affiliations.extend(
                symbol_affiliations[symbol]
                for symbol in author_symbols
                if symbol in symbol_affiliations
            )
            author["affiliations"] = _dedupe(affiliations)

    return authors, affiliation_by_marker, email_line


def _match_email_local_to_author(local, authors):
    local_key = _compact_alpha(local)
    matches = []
    for item in authors:
        name = item["name"]
        raw_parts = [part for part in name.split() if _compact_alpha(part)]
        parts = [_compact_alpha(part) for part in raw_parts]
        if len(parts) < 2:
            continue
        given = parts[:-1]
        surname = parts[-1]
        first = given[0]
        first_initial = first[:1]
        full = "".join(parts)
        candidates = {
            full,
            first,
            f"{first}{surname}",
            f"{first_initial}{surname}",
            f"{surname}{first}",
            f"{first}{surname[:1]}",
            f"{surname}{''.join(given)}",
        }
        transliterated_parts = [_compact_alpha_with_transliterations(part) for part in raw_parts]
        for first_variant in transliterated_parts[0]:
            for surname_variant in transliterated_parts[-1]:
                candidates.update({
                    "".join(next(iter(variants)) for variants in transliterated_parts),
                    f"{first_variant}{surname_variant}",
                    f"{first_variant[:1]}{surname_variant}",
                })
        if (
            local_key in candidates or
            local_key.startswith(f"{first}{surname}") or
            local_key.startswith(f"{first_initial}{surname}") or
            local_key.startswith(surname)
        ):
            matches.append(name)
    return matches[0] if len(matches) == 1 else ""


def _extract_emails(email_line, authors):
    email_line = _clean_text(email_line)
    email_by_name = {}
    for local_group, domain in re.findall(r"\{([^}]+)\}@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})", email_line):
        for local in [part.strip() for part in local_group.split(",") if part.strip()]:
            local = re.sub(r"\s+", "", local)
            name = _match_email_local_to_author(local, authors)
            if name:
                email_by_name[name] = f"{local}@{domain}"

    consumed_ranges = [match.span() for match in re.finditer(r"\{[^}]+\}@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", email_line)]
    def consumed(index):
        return any(start <= index < end for start, end in consumed_ranges)

    for match in re.finditer(r"([A-Za-z0-9._%+\-]+)@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})", email_line):
        if consumed(match.start()):
            continue
        local, domain = match.groups()
        local = re.sub(r"\s+", "", local)
        name = _match_email_local_to_author(local, authors)
        if name:
            email_by_name[name] = f"{local}@{domain}"
    return email_by_name


def _normalize_affiliation(text):
    text = common.strip_emails(text)
    text = re.sub(r"\{[^}]*$", " ", text)
    text = re.sub(r"^[^{}]*\}", " ", text)
    parts = []
    for raw_part in _split_affiliation_parts(text):
        part = _comma_before_trailing_country(raw_part)
        if not part:
            continue
        if any(marker in part.lower() for marker in ORG_MARKERS):
            parts.append(part)
    return "; ".join(_dedupe(parts))


def _parse_symbol_roles(pdf_lines, author_names):
    lines = [_clean_text(line) for line in pdf_lines or []]
    author_names = [_clean_text(name) for name in author_names if _clean_text(name)]
    roles = {"corresponding_names": set(), "equal_contribution_names": set()}
    if not lines or not author_names:
        return roles

    corresponding_symbols = set()
    equal_symbols = set()
    corresponding_phrase_re = re.compile(
        r"corresponding(?:\s+\w+){0,3}\s+authors?",
        flags=re.IGNORECASE,
    )
    for line in lines:
        compact = re.sub(r"\s+", " ", line)
        for symbol in re.findall(r"([*∗†‡§¶✉\x00])\s*(?=corresponding(?:\s+\w+){0,3}\s+authors?)", compact, flags=re.IGNORECASE):
            corresponding_symbols.add(symbol)
        for symbol in re.findall(r"([*∗†‡§¶])\s*(?=Co-first authors?|co-first authors?|contributed equally|equal contribution)", compact, flags=re.IGNORECASE):
            equal_symbols.add(symbol)
        leading = re.match(r"^\s*([*∗†‡§¶✉\x00])\s*(.+)$", compact)
        if leading:
            symbol, rest = leading.groups()
            if re.search(r"contributed equally|equal contribution|co-first", rest, flags=re.IGNORECASE):
                refs = re.split(r"contributed equally|equal contribution|co-first", rest, maxsplit=1, flags=re.IGNORECASE)[0]
                for author_name in author_names:
                    parts = author_name.split()
                    first = parts[0] if parts else ""
                    if author_name in refs or (first and re.search(rf"\b{re.escape(first)}\b", refs)):
                        roles["equal_contribution_names"].add(_compact_alpha(author_name))
            if corresponding_phrase_re.search(rest):
                corresponding_symbols.add(symbol)
                refs = corresponding_phrase_re.split(rest, maxsplit=1)[0]
                for author_name in author_names:
                    parts = author_name.split()
                    first = parts[0] if parts else ""
                    if author_name in refs or (first and re.search(rf"\b{re.escape(first)}\b", refs)):
                        roles["corresponding_names"].add(_compact_alpha(author_name))

    if not corresponding_symbols and not equal_symbols:
        return roles

    preabstract = []
    for line in lines:
        if line.lower().startswith(("abstract", "index terms", "introduction")):
            break
        preabstract.append(line)

    for line in preabstract:
        for author_name in author_names:
            match = re.search(rf"{re.escape(author_name)}\s*(?:[0-9,]+)?\s*([*∗†‡§¶✉\x00]+)", line, flags=re.IGNORECASE)
            if not match:
                continue
            symbols = set(match.group(1))
            if symbols & corresponding_symbols:
                roles["corresponding_names"].add(_compact_alpha(author_name))
            if symbols & equal_symbols:
                roles["equal_contribution_names"].add(_compact_alpha(author_name))
    return roles


def _apply_symbol_roles(authors, pdf_lines):
    roles = _parse_symbol_roles(pdf_lines, [author.get("name", "") for author in authors])
    corresponding_names = roles["corresponding_names"]
    equal_names = roles["equal_contribution_names"]
    if not corresponding_names and not equal_names:
        return authors
    for author in authors:
        name_key = _compact_alpha(author.get("name", ""))
        if name_key in corresponding_names:
            author["corresponding"] = True
        if equal_names:
            author["first_author"] = author.get("order") == 0 or name_key in equal_names
            author["co_first_author"] = False
            author["equal_contribution"] = False
        if equal_names and name_key in equal_names:
            author["first_author"] = True
            author["co_first_author"] = True
            author["equal_contribution"] = True
    return authors


def refine_title(title, authors=None, pdf_title_fallback="", pdf_lines=None, **kwargs):
    title = _clean_title_text(title)
    if not title:
        return _clean_title_text(pdf_title_fallback or _title_from_pdf_lines(pdf_lines or []))
    if _looks_like_contaminated_title(title, authors or []):
        pdf_line_title = _title_from_pdf_lines(pdf_lines or [])
        if pdf_line_title:
            return pdf_line_title
        if pdf_title_fallback:
            return _clean_title_text(pdf_title_fallback)
        return _clean_title_text(_truncate_title_on_author_marker(title, authors or []))
    return title


def refine_authors(authors, **kwargs):
    pdf_lines = kwargs.get("pdf_lines") or []
    pdf_authors, affiliation_by_marker, email_line = _extract_ieee_author_block(pdf_lines)
    title = kwargs.get("title", "")
    pdf_names = {_compact_alpha(author.get("name", "")) for author in pdf_authors}
    extracted_names = {_compact_alpha(author.get("name", "")) for author in authors or []}
    extracted_by_key = {
        _compact_alpha(author.get("name", "")): author
        for author in authors or []
    }
    pdf_has_better_details = any(
        _clean_text(pdf_author.get("name", "")) != _clean_text(extracted_by_key.get(_compact_alpha(pdf_author.get("name", "")), {}).get("name", ""))
        for pdf_author in pdf_authors
        if _compact_alpha(pdf_author.get("name", "")) in extracted_by_key
    )
    should_rebuild = (
        len(pdf_authors) >= 2 and
        (
            len(authors or []) < 2 or
            len(pdf_authors) != len(authors or []) or
            pdf_names != extracted_names or
            pdf_has_better_details or
            _looks_like_contaminated_title(title, authors or []) or
            any(_clean_text(author.get("name", "")).lower() in {"hong the", "kong"} for author in authors or [])
        )
    )
    if should_rebuild and pdf_authors:
        email_by_name = _extract_emails(email_line, pdf_authors)
        corresponding_names = {
            item["name"]
            for item in pdf_authors
            if item.get("corresponding_marker")
        }
        if len(corresponding_names) > 2:
            corresponding_names = set()
        rebuilt = []
        for order, item in enumerate(pdf_authors):
            affiliations = item.get("affiliations") or []
            if not affiliations:
                affiliation = affiliation_by_marker.get(item["marker"], "")
                affiliations = [affiliation] if affiliation else []
            affiliations = _dedupe(
                part
                for affiliation in affiliations
                for part in _split_affiliation_parts(affiliation)
            )
            rebuilt.append({
                "order": order,
                "name": item["name"],
                "email": item.get("email") or email_by_name.get(item["name"], ""),
                "affiliations": affiliations,
                "affiliation_source": "ieee_sp_pdf",
                "first_author": order == 0,
                "co_first_author": False,
                "equal_contribution": False,
                "corresponding": item["name"] in corresponding_names,
            })
        return _apply_symbol_roles(rebuilt, pdf_lines)

    refined = []
    pdf_by_name = {_compact_alpha(author.get("name", "")): author for author in pdf_authors}
    for author in authors:
        updated = dict(author)
        affiliations = []
        for affiliation in author.get("affiliations", []):
            normalized = _normalize_affiliation(affiliation)
            if normalized:
                affiliations.extend([item.strip() for item in normalized.split(";") if item.strip()])
        pdf_author = pdf_by_name.get(_compact_alpha(author.get("name", "")))
        if pdf_author:
            if pdf_author.get("affiliations"):
                affiliations = _dedupe(
                    part
                    for affiliation in pdf_author.get("affiliations", [])
                    for part in _split_affiliation_parts(affiliation)
                )
            if not _clean_text(updated.get("email", "")) and pdf_author.get("email"):
                updated["email"] = pdf_author["email"]
        updated["affiliations"] = _dedupe(affiliations)
        refined.append(updated)
    return _apply_symbol_roles(refined, pdf_lines)
