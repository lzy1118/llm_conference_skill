import re

import metadata_strategy_common as common


PROCEEDINGS_TAIL_PATTERNS = [
    r",?\s*San Diego,\s*CA,\s*USA\b.*$",
    r",?\s*ISBN\b.*$",
    r",?\s*Internet Society\b.*$",
    r",?\s*NDSS Symposium\b.*$",
]

KNOWN_SEGMENTS = [
    "CISPA Helmholtz Center for Information Security",
    "Xi'an Jiaotong University",
    "University of Southern California",
    "University of California, Davis",
]
ORG_MARKERS = (
    "university", "institute", "laboratory", "lab", "academy",
    "school", "college", "department", "center", "centre", "research",
    "cispa", "helmholtz", "eth", "leibniz", "csiro", "data61",
    "vrije", "tu berlin", "ruhr", "bochum", "cloudflare",
)
AFFILIATION_SYMBOLS = "*∗†‡§¶"
CID_SYMBOL_RE = re.compile(r"\(+cid:\d+\)+")
COUNTRY_TERMS = (
    "USA", "United States", "Canada", "China", "Germany", "Denmark",
    "Singapore", "Korea", "South Korea", "Japan", "Australia", "UK",
    "United Kingdom", "France", "Switzerland", "Netherlands", "Italy",
    "Spain", "Sweden", "Finland", "Norway", "Israel", "India",
    "Hong Kong", "Taiwan",
)


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


def _compact_alpha(text):
    return re.sub(r"[^a-z]+", "", _clean_text(text).lower())


def _looks_like_org(text):
    lower = _clean_text(text).lower()
    return any(segment.lower() in lower for segment in KNOWN_SEGMENTS) or any(marker in lower for marker in ORG_MARKERS)


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
    text = _clean_text(text)
    for country in sorted(COUNTRY_TERMS, key=len, reverse=True):
        if re.search(
            rf"\b(?:University|Institute|Laboratory|Lab|School|College|Department|Center|Centre)\s+of\s+{re.escape(country)}$",
            text,
            flags=re.IGNORECASE,
        ):
            continue
        text = re.sub(
            rf"(?<![,;])\s+\b({re.escape(country)})\b$",
            r", \1",
            text,
            flags=re.IGNORECASE,
        )
    return text


def _looks_like_email_line(text):
    text = _clean_text(text)
    return "@" in text or bool(re.search(r"\{[^}]+\}@", text))


def _split_names(line):
    names = []
    for part in re.split(r",|\band\b", _clean_text(line)):
        name = _clean_text(part)
        name = re.sub(rf"\s*[{re.escape(AFFILIATION_SYMBOLS)}]+\s*$", "", name)
        if len(name.split()) >= 2 and not _looks_like_org(name) and "@" not in name:
            names.append(name)
    return names


def _symbol_tokens(text):
    text = _clean_text(text)
    tokens = re.findall(rf"[{re.escape(AFFILIATION_SYMBOLS)}]", text)
    tokens.extend(CID_SYMBOL_RE.findall(text))
    return tokens


def _match_email_local_to_author(local, names):
    local_key = _compact_alpha(local)
    matches = []
    for name in names:
        parts = [_compact_alpha(part) for part in name.split() if _compact_alpha(part)]
        if len(parts) < 2:
            continue
        first = parts[0]
        surname = parts[-1]
        full = "".join(parts)
        candidates = {
            full,
            f"{first}{surname}",
            f"{first[:1]}{surname}",
            f"{surname}{first}",
        }
        if (
            local_key in candidates or
            full.startswith(local_key) or
            local_key.startswith(f"{first}{surname}") or
            local_key.startswith(f"{first[:1]}{surname}")
        ):
            matches.append(name)
    return matches[0] if len(matches) == 1 else ""


def _emails_by_name(email_line, names):
    result = {}
    for local_group, domain in re.findall(r"\{([^}]+)\}@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})", email_line):
        for local in [part.strip() for part in local_group.split(",") if part.strip()]:
            name = _match_email_local_to_author(local, names)
            if name:
                result[name] = f"{local}@{domain}"
    for local, domain in re.findall(r"([A-Za-z0-9._%+\-]+)@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})", email_line):
        name = _match_email_local_to_author(local, names)
        if name:
            result[name] = f"{local}@{domain}"
    return result


def _extract_numbered_author_refs(line):
    refs = []
    pattern = re.compile(
        r"([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,4})"
        r"\s*([0-9]+(?:\s*,\s*[0-9]+)*)"
    )
    for match in pattern.finditer(line):
        name = _clean_text(match.group(1))
        if _looks_like_org(name):
            continue
        ref_text = match.group(2)
        if "," not in ref_text and len(ref_text) > 1:
            ref_list = list(ref_text)
        else:
            ref_list = [ref.strip() for ref in ref_text.split(",") if ref.strip()]
        if len(name.split()) >= 2 and ref_list:
            refs.append((name, ref_list))
    return refs


def _parse_numbered_affiliations(lines):
    text = _clean_text(" ".join(lines))
    matches = re.finditer(r"(\d+)\.?\s*(.+?)(?=\s+\d+\.?\s*[A-Z]|$)", text)
    affiliations = {}
    for match in matches:
        affiliation = _normalize_affiliation(match.group(2))
        if affiliation and (_looks_like_org(affiliation) or "," in affiliation):
            affiliations[match.group(1)] = affiliation
    return affiliations


def _parse_ndss_numbered_header(lines):
    preabstract = []
    for line in lines:
        if line.lower().startswith("abstract"):
            break
        preabstract.append(line)

    author_refs = []
    affiliation_lines = []
    email_lines = []
    for line in preabstract:
        if _looks_like_email_line(line):
            email_lines.append(line)
            continue
        if re.match(r"^\d+", line) and _looks_like_org(line):
            affiliation_lines.append(line)
            continue
        refs = _extract_numbered_author_refs(line)
        if refs and not re.match(r"^\d+", line):
            author_refs.extend(refs)

    if len(author_refs) < 2 or not affiliation_lines:
        return []

    numbered_affiliations = _parse_numbered_affiliations(affiliation_lines)
    required_refs = {ref for _, refs in author_refs for ref in refs if ref.isdigit()}
    if not required_refs.issubset(numbered_affiliations):
        return []
    names = [name for name, _ in author_refs]
    email_map = _emails_by_name(" ".join(email_lines), names)
    authors = []
    for name, refs in author_refs:
        affiliations = [numbered_affiliations[ref] for ref in refs]
        authors.append({
            "name": name,
            "email": email_map.get(name, ""),
            "affiliations": _dedupe(affiliations),
        })
    return authors


def _extract_symbol_author_refs(line):
    refs = []
    pattern = re.compile(
        rf"([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){{1,4}})"
        rf"\s*([{re.escape(AFFILIATION_SYMBOLS)}]+)"
    )
    for match in pattern.finditer(_clean_text(line)):
        name = _clean_text(match.group(1))
        if _looks_like_org(name):
            continue
        refs.append((name, list(match.group(2))))
    return refs


def _parse_symbol_affiliations(line):
    line = _clean_text(line)
    pattern = re.compile(
        rf"([{re.escape(AFFILIATION_SYMBOLS)}])\s*"
        rf"(.+?)(?=\s*[{re.escape(AFFILIATION_SYMBOLS)}]\s*[A-Z]|$)"
    )
    affiliations = {}
    for match in pattern.finditer(line):
        affiliation = _normalize_affiliation(match.group(2))
        if affiliation and _looks_like_org(affiliation):
            affiliations[match.group(1)] = affiliation
    return affiliations


def _attach_detached_symbol_lines(lines):
    merged = []
    for line in lines:
        if (
            re.fullmatch(rf"[{re.escape(AFFILIATION_SYMBOLS)}]+", _clean_text(line)) and
            merged and
            not _looks_like_org(merged[-1]) and
            not _looks_like_email_line(merged[-1])
        ):
            merged[-1] = _clean_text(f"{merged[-1]} {line}")
            continue
        merged.append(line)
    return merged


def _parse_ndss_symbol_header(lines):
    preabstract = []
    for line in lines:
        if line.lower().startswith("abstract"):
            break
        preabstract.append(line)
    preabstract = _attach_detached_symbol_lines(preabstract)

    author_refs = []
    symbol_affiliations = {}
    email_lines = []
    for line in preabstract:
        parsed_affiliations = _parse_symbol_affiliations(line)
        if parsed_affiliations and _looks_like_org(line):
            symbol_affiliations.update(parsed_affiliations)
            if _looks_like_email_line(line):
                email_lines.append(line)
            continue
        if _looks_like_email_line(line):
            email_lines.append(line)
            continue
        refs = _extract_symbol_author_refs(line)
        if refs and not _looks_like_org(line):
            author_refs.extend(refs)

    if len(author_refs) < 2 or not symbol_affiliations:
        return []

    names = [name for name, _ in author_refs]
    email_map = _emails_by_name(" ".join(email_lines), names)
    authors = []
    for name, symbols in author_refs:
        affiliations = [symbol_affiliations[symbol] for symbol in symbols if symbol in symbol_affiliations]
        authors.append({
            "name": name,
            "email": email_map.get(name, ""),
            "affiliations": _dedupe(affiliations),
        })
    return authors


def _parse_ndss_author_blocks(pdf_lines):
    lines = [_clean_text(line).replace("ﬁ", "fi") for line in pdf_lines or []]
    lines = [line for line in lines if line]
    numbered_authors = _parse_ndss_numbered_header(lines)
    if numbered_authors:
        return numbered_authors
    symbol_authors = _parse_ndss_symbol_header(lines)
    if symbol_authors:
        return symbol_authors

    blocks = []
    index = 0
    while index + 2 < len(lines):
        names = _split_names(lines[index])
        if not names:
            index += 1
            continue
        affiliation = lines[index + 1]
        cursor = index + 2
        country = ""
        if cursor < len(lines) and not _looks_like_email_line(lines[cursor]):
            country = _extract_country(lines[cursor])
            if country:
                cursor += 1
        if cursor >= len(lines):
            break
        email_line = lines[cursor]
        if not _looks_like_org(affiliation) or not _looks_like_email_line(email_line):
            index += 1
            continue
        affiliation = _append_country(affiliation, country)
        email_map = _emails_by_name(email_line, names)
        for name in names:
            blocks.append({
                "name": name,
                "email": email_map.get(name, ""),
                "affiliations": [_normalize_affiliation(affiliation)],
            })
        index = cursor + 1
    return blocks


def _parse_symbol_roles(pdf_lines, author_names):
    lines = [_clean_text(line).replace("ﬁ", "fi") for line in pdf_lines or []]
    author_names = [_clean_text(name) for name in author_names if _clean_text(name)]
    roles = {
        "corresponding_names": set(),
        "equal_contribution_names": set(),
    }
    if not lines or not author_names:
        return roles

    corresponding_symbols = set()
    equal_symbols = set()
    first_n_equal = 0

    def add_explicit_names(text, role_key):
        for author_name in author_names:
            parts = author_name.split()
            first = parts[0] if parts else ""
            if re.search(rf"\b{re.escape(author_name)}\b", text, flags=re.IGNORECASE) or (
                first and re.search(rf"\b{re.escape(first)}\b", text, flags=re.IGNORECASE)
            ):
                roles[role_key].add(_name_key(author_name))

    for line in lines:
        compact = re.sub(r"\s+", " ", line)
        for footnote in re.split(rf"(?=[{re.escape(AFFILIATION_SYMBOLS)}])", compact):
            footnote = _clean_text(footnote)
            if not footnote:
                continue
            leading_symbol = re.match(rf"^([{re.escape(AFFILIATION_SYMBOLS)}])", footnote)
            symbol = leading_symbol.group(1) if leading_symbol else ""
            if re.search(r"corresponding authors?|corresponding author", footnote, flags=re.IGNORECASE):
                if symbol:
                    corresponding_symbols.add(symbol)
                add_explicit_names(footnote, "corresponding_names")
            if re.search(r"co-first authors?|contributed equally|equal contribution|made equal contribution", footnote, flags=re.IGNORECASE):
                if symbol:
                    equal_symbols.add(symbol)
                add_explicit_names(footnote, "equal_contribution_names")
                count_match = re.search(r"first\s+(two|three|four|five|\d+)\s+authors?", footnote, flags=re.IGNORECASE)
                if count_match:
                    word = count_match.group(1).lower()
                    word_to_int = {"two": 2, "three": 3, "four": 4, "five": 5}
                    first_n_equal = max(first_n_equal, int(word) if word.isdigit() else word_to_int.get(word, 0))

        for symbol in CID_SYMBOL_RE.findall(compact):
            if re.search(r"corresponding authors?|corresponding author", compact, flags=re.IGNORECASE):
                corresponding_symbols.add(symbol)

    if first_n_equal:
        for author_name in author_names[:first_n_equal]:
            roles["equal_contribution_names"].add(_name_key(author_name))

    preabstract = []
    for line in lines:
        if line.lower().startswith("abstract"):
            break
        preabstract.append(line)

    for line in preabstract:
        for author_name in author_names:
            match = re.search(rf"{re.escape(author_name)}\s*(?:[0-9,\s]+)?\s*([*∗†‡§¶]+)", line, flags=re.IGNORECASE)
            symbols = set(match.group(1)) if match else set()
            cid_match = re.search(rf"{re.escape(author_name)}\s*(?:[0-9,\s]+)?\s*({CID_SYMBOL_RE.pattern})", line, flags=re.IGNORECASE)
            if cid_match:
                symbols.add(cid_match.group(1))
            if not symbols:
                continue
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


def _text_left_of_icon(line_chars, icon_char):
    chars = [
        char for char in line_chars
        if char.get("x1", 0) <= icon_char.get("x0", 0) + 1
        and "(cid:" not in str(char.get("text", ""))
    ]
    chars = sorted(chars, key=lambda char: char.get("x0", 0))
    pieces = []
    previous = None
    for char in chars:
        text = str(char.get("text", ""))
        if not text.strip():
            continue
        if previous and char.get("x0", 0) - previous.get("x1", 0) > max(1.5, previous.get("size", 0) * 0.25):
            pieces.append(" ")
        pieces.append(text)
        previous = char
    return _clean_text("".join(pieces))


def _parse_pdf_icon_corresponding_names(pdf_path, author_names):
    author_names = [_clean_text(name) for name in author_names if _clean_text(name)]
    if not pdf_path or not author_names:
        return set()
    try:
        import pdfplumber
    except ImportError:
        return set()

    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                return set()
            chars = pdf.pages[0].chars
    except Exception:
        return set()

    matches = set()
    icon_chars = []
    for char in chars:
        text = str(char.get("text", ""))
        font = str(char.get("fontname", "")).lower()
        top = float(char.get("top", 9999))
        if top > 240:
            continue
        if "bbding" in font or "cid:12" in text or text in {"✉", "✉︎"}:
            icon_chars.append(char)

    for icon_char in icon_chars:
        icon_top = float(icon_char.get("top", 0))
        line_chars = [
            char for char in chars
            if abs(float(char.get("top", 0)) - icon_top) <= max(4, float(icon_char.get("size", 0)) * 0.6)
        ]
        left_text_key = _compact_alpha(_text_left_of_icon(line_chars, icon_char))
        if not left_text_key:
            continue
        candidates = []
        for author_name in author_names:
            name_key = _name_key(author_name)
            position = left_text_key.rfind(name_key)
            if position >= 0:
                candidates.append((position, name_key))
        if candidates:
            matches.add(max(candidates)[1])
    return matches


def _apply_pdf_icon_roles(authors, pdf_path):
    corresponding_names = _parse_pdf_icon_corresponding_names(
        pdf_path,
        [author.get("name", "") for author in authors],
    )
    if not corresponding_names:
        return authors
    for author in authors:
        if _name_key(author.get("name", "")) in corresponding_names:
            author["corresponding"] = True
    return authors


def _name_key(name):
    return _compact_alpha(name)


def _should_rebuild_from_pdf(pdf_authors, authors):
    if len(pdf_authors) < 2:
        return False
    if any(_looks_like_org(author.get("name", "")) for author in authors or []):
        return True
    if len(pdf_authors) != len(authors or []):
        return len(pdf_authors) > len(authors or [])
    pdf_names = {_name_key(author["name"]) for author in pdf_authors}
    extracted_names = {_name_key(author.get("name", "")) for author in authors or []}
    if pdf_names != extracted_names:
        return True
    extracted_pairs = {
        (_name_key(author.get("name", "")), tuple(_dedupe(author.get("affiliations", []))))
        for author in authors or []
    }
    pdf_pairs = {
        (_name_key(author["name"]), tuple(_dedupe(author.get("affiliations", []))))
        for author in pdf_authors
    }
    if extracted_pairs != pdf_pairs:
        return True
    extracted_emails = {
        (_name_key(author.get("name", "")), _clean_text(author.get("email", "")))
        for author in authors or []
    }
    pdf_emails = {
        (_name_key(author["name"]), _clean_text(author.get("email", "")))
        for author in pdf_authors
    }
    return extracted_emails != pdf_emails


def _normalize_affiliation(text):
    text = common.strip_emails(_clean_text(text))
    text = re.sub(rf"^[{re.escape(AFFILIATION_SYMBOLS)}]\s*", "", text)
    text = re.sub(rf"\s*[{re.escape(AFFILIATION_SYMBOLS)}]\s*$", "", text)
    text = re.sub(r":\s*$", "", text)
    text = text.replace("Universit¨at", "Universität")
    for pattern in PROCEEDINGS_TAIL_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    for segment in KNOWN_SEGMENTS:
        text = re.sub(
            rf"(?<!^)\s+(?={re.escape(segment)})",
            "; ",
            text,
            flags=re.IGNORECASE,
        )
    text = text.replace(" University CISPA", " University; CISPA Helmholtz Center for Information Security")
    text = _comma_before_trailing_country(text.strip(" ,;"))
    return text


def refine_title(title, **kwargs):
    return _clean_text(title)


def refine_authors(authors, **kwargs):
    pdf_lines = kwargs.get("pdf_lines") or []
    pdf_path = kwargs.get("pdf_path", "")
    pdf_authors = _parse_ndss_author_blocks(kwargs.get("pdf_lines") or [])
    if _should_rebuild_from_pdf(pdf_authors, authors):
        rebuilt = []
        for order, author in enumerate(pdf_authors):
            rebuilt.append({
                "order": order,
                "name": author["name"],
                "email": author["email"],
                "affiliations": _dedupe(author["affiliations"]),
                "affiliation_source": "ndss_pdf",
                "first_author": order == 0,
                "co_first_author": False,
                "equal_contribution": False,
                "corresponding": False,
            })
        return _apply_pdf_icon_roles(_apply_symbol_roles(rebuilt, pdf_lines), pdf_path)

    refined = []
    for author in authors:
        updated = dict(author)
        updated["affiliations"] = _dedupe(
            _normalize_affiliation(affiliation)
            for affiliation in author.get("affiliations", [])
        )
        refined.append(updated)
    return _apply_pdf_icon_roles(_apply_symbol_roles(refined, pdf_lines), pdf_path)
