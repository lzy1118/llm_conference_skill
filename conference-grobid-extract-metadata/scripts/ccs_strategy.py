import re

import metadata_strategy_common as common


ORG_MARKERS = (
    "university", "institute", "laboratory", "lab", "labs", "school",
    "college", "department", "center", "centre", "cispa", "qi-anxin",
    "xuanwu", "fau", "unist", "sjtu", "alibaba", "georgia institute",
    "central oklahoma", "texas at dallas", "columbia", "foundation",
    "mit", "csail", "inria", "cas-klonat", "ucas", "nervos",
    "ant group", "360", "gesg", "corporation", "corp", "inc", "ltd",
    "aist", "hitachi", "consensys", "linea", "iohk", "tripleblind",
    "independent", "cornell tech", "ethereum foundation", "université",
    "cea", "cnrs", "loria", "fireblocks", "organization", "security",
    "cfar", "ihpc", "a*star", "astar", "imec", "cosic", "esat",
    "ku leuven", "apple", "base power", "researcher", "ut austin",
    "ntt research", "tu crete", "helmholtz", "hasso", "plattner",
    "bergische", "wuppertal", "eth zurich", "ibm research", "aarno",
    "engineering", "management", "technological",
    "computer science", "queen mary", "software", "communications",
    "privacy", "server", "fraunhofer", "umass", "universität",
    "univ.", "athene", "kaist",
    "polytechnic",
)

ORG_PHRASE_RE = re.compile(
    r"(?:"
    r"[A-Z][\w&.'-]+(?:\s+[A-Z][\w&.'-]+){0,7}\s+"
    r"(?:University|Institute|Laboratory|Lab|Labs|School|College|Department|Center|Centre|Security|Technology)"
    r"|(?:School|Department|Institute|Laboratory|Lab|Labs|College|Center|Centre)\s+of\s+[A-Z][^;,]+"
    r"|[A-Z][\w&.'-]+(?:\s+[A-Z][\w&.'-]+){0,5}\s+(?:Corporation|Corp\.?|Inc\.?|Ltd\.?)"
    r"|[A-Z][\w&.'-]+,\s*(?:Corporation|Corp\.?|Inc\.?|Ltd\.?)"
    r"|CAS-KLONAT|IIE,\s*CAS|Nervos|Ant Group|Alpha Lab|360 GESG|UCAS|IOHK|TripleBlind"
    r"|imec-COSIC|ESAT|KU Leuven|Apple|Base Power Company|Researcher"
    r")"
)
COUNTRY_TERMS = (
    "USA", "United States", "Canada", "China", "Germany", "Denmark",
    "Singapore", "Korea", "South Korea", "Japan", "Australia", "UK",
    "United Kingdom", "France", "Switzerland", "Netherlands", "Italy",
    "Spain", "Sweden", "Finland", "Norway", "Israel", "India",
    "Hong Kong", "Taiwan", "Iran", "Republic of Korea", "Belgium",
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


def _looks_like_email(text):
    return bool(re.search(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", _clean_text(text)))


def _looks_like_org(text):
    lower = _clean_text(text).lower()
    text = _clean_text(text)
    return any(marker in lower for marker in ORG_MARKERS) or bool(re.fullmatch(r"[A-Z][A-Z0-9&.-]{2,}", text))


def _looks_like_location(text):
    lower = _clean_text(text).lower()
    return bool(re.search(r"\b(?:usa|united states|united kingdom|uk|netherlands|korea|china|germany|denmark|japan|israel|iran|belgium|switzerland|georgia|texas|oklahoma|virginia|colorado|missouri|ulsan|atlanta|edmond|richardson|charlottesville|urbana|champaign|tel aviv|palaiseau|nancy|paris|bochum|bonn|aarhus|leuven|boston|buffalo|springs|tokyo|sendai|kawasaki|kansas city|zurich|wuppertal|potsdam|stuttgart|philadelphia|lowell|darmstadt|frankfurt)\b", lower))


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


def _append_location(affiliation, location):
    affiliation = _clean_text(affiliation)
    location = _clean_text(location)
    if not affiliation or not location:
        return affiliation
    if location.lower() in affiliation.lower():
        return affiliation
    return f"{affiliation}, {location}"


def _comma_before_location(text):
    text = _clean_text(text)
    location_pattern = r"(Tokyo|Sendai|Kawasaki|Seoul|Ulsan|Atlanta|Edmond|Richardson|Charlottesville|Bochum|Bonn|Aarhus|Boston|Buffalo Springs|Kansas City,\s*Missouri|Zurich|Wuppertal|Potsdam|Stuttgart|Philadelphia)"
    text = re.sub(
        rf"\b(AIST|Hitachi,\s*Ltd|NEC Corporation|Tohoku University|Consensys|IOHK|TripleBlind|IBM Research Europe(?:\s*/\s*ETH Zurich)?|Bergische Universität Wuppertal|Hasso Plattner Institute|University of Stuttgart|University of Pennsylvania)\s+({location_pattern}\b)",
        r"\1, \2",
        text,
    )
    return text


def _comma_before_trailing_country(text):
    return common.comma_before_trailing_country(text, COUNTRY_TERMS)


def _looks_like_person_name(text):
    text = _clean_text(text)
    if not text or len(text) > 80 or any(char.isdigit() for char in text):
        return False
    if "," in text:
        return False
    if text.upper() == text:
        return False
    if _looks_like_location(text):
        return False
    stripped = re.sub(r"[*∗†‡§¶★☆]", "", text)
    if _looks_like_org(stripped) or _looks_like_email(stripped):
        return False
    tokens = re.findall(r"[^\W\d_][^\W\d_'.-]*", stripped)
    if len(tokens) < 2 or len(tokens) > 5:
        return False
    if len(tokens) == 2 and tokens[0].isupper() and len(tokens[0]) <= 4:
        return False
    particles = {"de", "del", "der", "di", "dos", "du", "la", "le", "van", "von"}
    return all(token[:1].isupper() or token.lower() in particles for token in tokens)


def _clean_person_name(text):
    text = _clean_text(re.sub(r"[*∗†‡§¶★☆]", "", text))
    return common.clean_author_name(text)


def _looks_like_single_name_token(text):
    text = _clean_person_name(text)
    return bool(re.fullmatch(r"[^\W\d_][^\W\d_'.-]{2,}", text)) and text[:1].isupper() and not _looks_like_org(text)


def _extract_acm_names_at(lines, index):
    line = _clean_text(lines[index])
    if _looks_like_person_name(line):
        return [_clean_person_name(line)], 1
    parts = [_clean_person_name(part) for part in re.split(r",|\band\b", line) if _clean_person_name(part)]
    if len(parts) >= 2 and all(_looks_like_person_name(part) for part in parts):
        return parts, 1
    if (
        index + 1 < len(lines) and
        re.search(r"[*∗†‡§¶]", lines[index + 1]) and
        _looks_like_single_name_token(line) and
        _looks_like_single_name_token(lines[index + 1])
    ):
        combined = _clean_person_name(f"{line} {lines[index + 1]}")
        if _looks_like_person_name(combined):
            return [combined], 2
    return [], 0


def _extract_numbered_author_refs(line):
    refs = []
    marker = rf"(?:\d+|[{re.escape(common.AFFILIATION_SYMBOLS)}])"
    pattern = re.compile(
        rf"([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){{1,4}})"
        rf"\s*({marker}(?:\s*,\s*{marker})*)"
    )
    for match in pattern.finditer(_clean_text(line)):
        name = _clean_person_name(match.group(1))
        if _looks_like_person_name(name):
            refs.append((name, re.findall(marker, match.group(2))))
    return refs


def _parse_numbered_affiliations(line):
    affiliations = {}
    for match in re.finditer(r"(\d+)\s*(.+?)(?=\s+\d+\s*[A-Z]|$)", _clean_text(line)):
        affiliation = _normalize_affiliation(match.group(2), [])
        if affiliation:
            affiliations[match.group(1)] = affiliation
    return affiliations


def _parse_acm_numbered_author_blocks(pdf_lines):
    lines = [_clean_text(line) for line in pdf_lines or []]
    lines = [line for line in lines if line]
    preabstract = []
    for line in lines:
        if line.lower().startswith(("abstract", "ccs concepts", "keywords")):
            break
        preabstract.append(line)

    start = -1
    for index, line in enumerate(preabstract):
        if _extract_numbered_author_refs(line):
            start = index
            break
    if start < 0:
        return []

    author_refs = []
    affiliation_lines = []
    email_lines = []
    for line in preabstract[start:]:
        if _looks_like_email(line):
            email_lines.append(line)
            continue
        refs = _extract_numbered_author_refs(line)
        if refs and not _looks_like_org(line):
            author_refs.extend(refs)
            continue
        if re.match(r"^\d", line) or _looks_like_org(line):
            affiliation_lines.append(line)

    if len(author_refs) < 2 or not affiliation_lines:
        return []

    numbered_affiliations = _parse_numbered_affiliations(" ".join(affiliation_lines))
    if not numbered_affiliations or not any(
        any(ref.isdigit() for ref in refs)
        for _, refs in author_refs
    ):
        return []
    required_refs = {
        ref for _, refs in author_refs for ref in refs if ref.isdigit()
    }
    if not required_refs.issubset(numbered_affiliations):
        return []
    authors = []
    for name, refs in author_refs:
        numeric_refs = [ref for ref in refs if ref.isdigit()]
        authors.append({
            "name": name,
            "email": "",
            "affiliations": _dedupe(
                numbered_affiliations[ref]
                for ref in numeric_refs
            ),
            "corresponding_marker": bool(set(refs) & set(common.AFFILIATION_SYMBOLS)),
        })
    return authors if len(authors) >= 2 else []


def _parse_acm_author_blocks(pdf_lines):
    lines = [_clean_text(line) for line in pdf_lines or []]
    lines = [line for line in lines if line]
    if not lines:
        return []

    start = -1
    for index, line in enumerate(lines[:30]):
        names, _ = _extract_acm_names_at(lines, index)
        if not names:
            continue
        lookahead = lines[index + 1:index + 5]
        if any(_looks_like_org(item) for item in lookahead) or any(_looks_like_email(item) for item in lookahead):
            start = index
            break
    if start < 0:
        return []

    preabstract = []
    for line in lines[start:]:
        if line.lower().startswith("abstract"):
            break
        preabstract.append(line)

    authors = []
    index = 0
    while index < len(preabstract):
        names, consumed = _extract_acm_names_at(preabstract, index)
        if not names:
            index += 1
            continue

        affiliation_lines = []
        email = ""
        cursor = index + consumed
        while cursor < len(preabstract):
            line = preabstract[cursor]
            if _extract_acm_names_at(preabstract, cursor)[0]:
                break
            email_match = re.search(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", line)
            if email_match:
                email = email_match.group(0)
                cursor += 1
                continue
            country = _extract_country(line)
            if country and line.lower() == country.lower() and affiliation_lines:
                affiliation_lines[-1] = _append_country(affiliation_lines[-1], country)
                cursor += 1
                continue
            if _looks_like_org(line):
                if affiliation_lines and re.search(r"\b(?:for|of)$", affiliation_lines[-1], flags=re.IGNORECASE):
                    affiliation_lines[-1] = _clean_text(f"{affiliation_lines[-1]} {line}")
                else:
                    affiliation_lines.append(line)
                cursor += 1
                continue
            if _looks_like_location(line):
                if affiliation_lines:
                    affiliation_lines[-1] = _append_location(affiliation_lines[-1], line)
                cursor += 1
                continue
            if affiliation_lines:
                affiliation_lines[-1] = _clean_text(f"{affiliation_lines[-1]} {line}")
            cursor += 1

        if not affiliation_lines and not email:
            index += 1
            continue

        name_text = " ".join(preabstract[index:index + consumed])
        corresponding_marker = "(cid:66)" in name_text or bool(re.search(r"\s+B$", name_text))
        for clean_name in names:
            clean_name = re.sub(r"\s+B$", "", clean_name)
            authors.append({
                "name": clean_name,
                "email": email,
                "affiliations": _dedupe(affiliation_lines),
                "corresponding_marker": corresponding_marker or bool(re.search(r"[*∗]", name_text)),
            })
        index = max(cursor, index + 1)

    return authors


def _split_compact_name_line(line, expected_count):
    line = re.sub(r"\(cid:\d+\)", " ", _clean_text(line))
    line = re.sub(r"\s+", " ", line).strip()
    if "," in line:
        candidates = [part for part in re.split(r",|\band\b", line) if part.strip()]
    else:
        tokens = re.findall(r"[A-Za-z][A-Za-z'.-]*", line)
        if expected_count and len(tokens) == expected_count * 2:
            candidates = [" ".join(tokens[index:index + 2]) for index in range(0, len(tokens), 2)]
        else:
            candidates = re.findall(r"[A-Z][A-Za-z'.-]+\s+[A-Z][A-Za-z'.-]+", line)
    return [common.clean_author_name(name) for name in candidates if _looks_like_person_name(name)]


def _emails_from_line(line):
    return re.findall(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", _clean_text(line))


def _merge_card_affiliation_lines(lines):
    merged = []
    for line in lines:
        line = _clean_text(line)
        if not line:
            continue
        if _looks_like_location(line):
            if merged:
                merged[-1] = _append_location(merged[-1], line)
            else:
                merged.append(line)
            continue
        if merged and re.search(r"\b(?:for|of|and)$", merged[-1], flags=re.IGNORECASE):
            merged[-1] = _clean_text(f"{merged[-1]} {line}")
        else:
            merged.append(line)
    return _dedupe(merged)


def _parse_acm_per_author_card_blocks(pdf_lines):
    lines = [_clean_text(line) for line in pdf_lines or []]
    lines = [line for line in lines if line]
    preabstract = []
    for line in lines:
        if line.lower().startswith(("abstract", "ccs concepts", "keywords")):
            break
        preabstract.append(line)

    authors = []
    index = 0
    while index < len(preabstract):
        names, consumed = _extract_acm_names_at(preabstract, index)
        if not names:
            index += 1
            continue

        cursor = index + consumed
        email = ""
        affiliation_lines = []
        saw_detail = False
        while cursor < len(preabstract):
            line = preabstract[cursor]
            next_names, _ = _extract_acm_names_at(preabstract, cursor)
            if next_names and saw_detail:
                break

            emails = _emails_from_line(line)
            if emails:
                email = emails[0]
                saw_detail = True
                cursor += 1
                continue

            if _looks_like_org(line) or _looks_like_location(line):
                affiliation_lines.append(line)
                saw_detail = True
                cursor += 1
                continue

            if affiliation_lines and not next_names:
                affiliation_lines[-1] = _clean_text(f"{affiliation_lines[-1]} {line}")
                cursor += 1
                continue

            break

        if not saw_detail:
            index += 1
            continue

        affiliations = _merge_card_affiliation_lines(affiliation_lines)
        name_text = " ".join(preabstract[index:index + consumed])
        for clean_name in names:
            authors.append({
                "name": clean_name,
                "email": email,
                "affiliations": affiliations,
                "corresponding_marker": bool(re.search(r"[*∗]", name_text)),
            })
        index = max(cursor, index + 1)

    affiliation_coverage = sum(bool(author.get("affiliations")) for author in authors)
    email_coverage = sum(bool(author.get("email")) for author in authors)
    if len(authors) >= 2 and affiliation_coverage >= len(authors) - 1 and email_coverage >= len(authors) - 1:
        return authors
    return []


def _parse_acm_matrix_author_blocks(pdf_lines):
    lines = [_clean_text(line) for line in pdf_lines or []]
    lines = [line for line in lines if line]
    authors = []
    index = 0
    while index + 1 < len(lines):
        if lines[index].lower().startswith(("abstract", "ccs concepts", "keywords")):
            break
        emails = _emails_from_line(lines[index + 1])
        if not emails:
            index += 1
            continue
        names = _split_compact_name_line(lines[index], len(emails))
        if len(names) < 2 or len(names) != len(emails):
            index += 1
            continue
        cursor = index + 2
        affiliation_lines = []
        while cursor < len(lines):
            lower = lines[cursor].lower()
            if lower.startswith(("abstract", "ccs concepts", "keywords")):
                break
            next_emails = _emails_from_line(lines[cursor + 1]) if cursor + 1 < len(lines) else []
            if next_emails and len(_split_compact_name_line(lines[cursor], len(next_emails))) == len(next_emails):
                break
            if _looks_like_org(lines[cursor]) or _looks_like_location(lines[cursor]):
                affiliation_lines.append(lines[cursor])
            cursor += 1
        normalized = _normalize_affiliation(" ; ".join(affiliation_lines), [{"name": name} for name in names])
        affiliations = [part.strip() for part in normalized.split(";") if part.strip()]
        if affiliations:
            for name, email in zip(names, emails):
                authors.append({
                    "name": name,
                    "email": email,
                    "affiliations": affiliations,
                    "corresponding_marker": False,
                })
        index = max(cursor, index + 1)
    return authors if len(authors) >= 2 else []


def _parse_acm_stacked_column_author_blocks(pdf_lines):
    lines = [_clean_text(line) for line in pdf_lines or []]
    lines = [line for line in lines if line]
    authors = []
    index = 0
    while index < len(lines):
        if lines[index].lower().startswith(("abstract", "ccs concepts", "keywords")):
            break
        if not _looks_like_person_name(lines[index]):
            index += 1
            continue

        name_start = index
        names = []
        while index < len(lines) and _looks_like_person_name(lines[index]):
            names.append(_clean_text(re.sub(r"[*∗†‡§¶]", "", lines[index])))
            index += 1

        emails = []
        email_start = index
        while index < len(lines) and _looks_like_email(lines[index]):
            found = _emails_from_line(lines[index])
            if not found:
                break
            emails.extend(found)
            index += 1

        if not emails or len(names) != len(emails):
            index = name_start + 1
            continue

        affiliation_lines = []
        while index < len(lines):
            lower = lines[index].lower()
            if lower.startswith(("abstract", "ccs concepts", "keywords")):
                break
            if _looks_like_person_name(lines[index]) or _looks_like_email(lines[index]):
                break
            if _looks_like_location(lines[index]):
                if affiliation_lines:
                    affiliation_lines[-1] = _append_location(affiliation_lines[-1], lines[index])
                else:
                    affiliation_lines.append(lines[index])
            elif _looks_like_org(lines[index]):
                affiliation_lines.append(lines[index])
            index += 1

        normalized = _normalize_affiliation(
            " ; ".join(affiliation_lines),
            [{"name": name} for name in names],
        )
        affiliations = [part.strip() for part in normalized.split(";") if part.strip()]
        if not affiliations and affiliation_lines:
            affiliation_text = _clean_text(", ".join(affiliation_lines))
            if _looks_like_location(affiliation_text) or _extract_country(affiliation_text):
                affiliations = [affiliation_text]

        for name, email in zip(names, emails):
            authors.append({
                "name": name,
                "email": email,
                "affiliations": affiliations,
                "corresponding_marker": False,
            })

        index = max(index, email_start + 1)

    return authors if len(authors) >= 2 else []


def _parse_acm_grouped_affiliation_blocks(pdf_lines):
    lines = [_clean_text(line) for line in pdf_lines or []]
    lines = [line for line in lines if line]
    preabstract = []
    for line in lines:
        if line.lower().startswith(("abstract", "ccs concepts", "keywords")):
            break
        preabstract.append(line)

    authors = []
    index = 0
    while index < len(preabstract):
        names = []
        while index < len(preabstract) and _looks_like_person_name(preabstract[index]):
            names.append(_clean_person_name(preabstract[index]))
            index += 1
        if not names:
            index += 1
            continue

        emails = []
        while index < len(preabstract) and _looks_like_email(preabstract[index]):
            emails.extend(_emails_from_line(preabstract[index]))
            index += 1

        affiliation_lines = []
        while index < len(preabstract):
            line = preabstract[index]
            if _looks_like_person_name(line) or _looks_like_email(line):
                break
            if _looks_like_org(line):
                affiliation_lines.append(line)
            elif _looks_like_location(line):
                if affiliation_lines:
                    affiliation_lines[-1] = _append_location(affiliation_lines[-1], line)
                else:
                    affiliation_lines.append(line)
            index += 1

        normalized = _normalize_affiliation(
            " ; ".join(affiliation_lines),
            [{"name": name} for name in names],
        )
        affiliations = [part.strip() for part in normalized.split(";") if part.strip()]
        if not affiliations:
            continue
        for offset, name in enumerate(names):
            authors.append({
                "name": name,
                "email": emails[offset] if offset < len(emails) else "",
                "affiliations": affiliations,
                "corresponding_marker": False,
            })

    return authors if len(authors) >= 2 else []


def _name_key(name):
    return re.sub(r"[^a-z]+", "", _clean_text(name).lower())


def _is_affiliation_fragment(text):
    text = _clean_text(text)
    return bool(
        re.search(r"\b(?:and|of|for)\s*[,;](?:\s|$)", text, re.IGNORECASE)
        or re.search(r"\b(?:and|of|for)\s*$", text, re.IGNORECASE)
        or re.match(r"^(?:university|institute|department|school|college|laboratory|lab)\s*[,;]", text, re.IGNORECASE)
    )


def _join_split_university_chunks(affiliations):
    result = []
    for affiliation in affiliations or []:
        affiliation = _clean_text(affiliation)
        if result and re.fullmatch(
            r"(?:USA|United States|China|Germany|France|UK|United Kingdom|Singapore|Korea|South Korea|Japan|Canada|Australia|Switzerland|Netherlands|Italy|Spain|Sweden|Belgium|Israel|India|Taiwan)",
            affiliation,
            re.IGNORECASE,
        ):
            result[-1] = f"{result[-1]}, {affiliation}"
            continue
        match = re.match(r"^University\s*[,;]\s*(.*)$", affiliation, re.IGNORECASE)
        if match and result and re.search(
            r"\b(?:polytechnic|technological|management|engineering|fudan)\s*$",
            result[-1],
            re.IGNORECASE,
        ):
            suffix = _clean_text(match.group(1))
            result[-1] = f"{result[-1]} University{', ' + suffix if suffix else ''}"
        else:
            result.append(affiliation)
    return _dedupe(_repair_affiliation_text(item) for item in result)


def _repair_affiliation_text(text):
    text = _clean_text(text)
    text = re.sub(r"\bRepublic\s+of\s*,\s*Korea\b", "Republic of Korea", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\b(Normal|Polytechnic|Technological|Management|Engineering|Fudan)\s*,\s*University\b",
        r"\1 University",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\b(and|of|for)\s*,\s*(?=(?:Technology|Engineering|Science|Artificial|Computer|Information|Security|Research)\b)",
        r"\1 ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\b([A-Za-z][A-Za-z .'-]+)\s*,\s*\1\s*,",
        r"\1,",
        text,
        flags=re.IGNORECASE,
    )
    return _clean_text(text)


def _select_pdf_author_candidate(candidates, existing_authors, title=""):
    title_key = _name_key(title)
    existing_names = {_name_key(author.get("name", "")) for author in existing_authors or []}
    ranked = []
    for parser_index, candidate in enumerate(candidates):
        filtered = [
            dict(author, affiliations=_join_split_university_chunks(author.get("affiliations", [])))
            for author in candidate
            if not (
                _name_key(author.get("name", "")) == title_key
                or (
                    len(_name_key(author.get("name", ""))) >= 8
                    and _name_key(author.get("name", "")) in title_key
                )
            )
        ]
        if not filtered:
            continue
        names = {_name_key(author.get("name", "")) for author in filtered}
        overlap = len(names & existing_names)
        count_difference = abs(len(filtered) - len(existing_authors or []))
        fragment_count = sum(
            _is_affiliation_fragment(item)
            for author in filtered
            for item in author.get("affiliations", [])
        )
        affiliation_chars = sum(
            len(item)
            for author in filtered
            for item in author.get("affiliations", [])
        )
        email_count = sum(bool(author.get("email")) for author in filtered)
        ranked.append((
            (overlap, -count_difference, -fragment_count, affiliation_chars, email_count, -parser_index),
            filtered,
        ))
    return max(ranked, key=lambda item: item[0])[1] if ranked else []


def _should_rebuild_from_pdf(pdf_authors, authors):
    if len(pdf_authors) < 2:
        return False
    if any(re.search(r"\d", author.get("name", "")) for author in authors or []):
        return True
    if len(pdf_authors) > len(authors or []):
        return True
    if len(pdf_authors) < len(authors or []):
        # GROBID occasionally emits affiliation fragments as additional
        # author nodes.  A complete PDF card candidate may therefore be
        # shorter than the raw list; accept it when the surplus TEI rows are
        # empty and the PDF candidate has strong email/affiliation support.
        surplus = len(authors or []) - len(pdf_authors)
        weak_existing = sum(
            not _clean_text(author.get("email", ""))
            and not _dedupe(author.get("affiliations", []))
            for author in authors or []
        )
        strong_pdf = sum(
            bool(_clean_text(author.get("email", "")))
            or bool(_dedupe(author.get("affiliations", [])))
            for author in pdf_authors
        )
        if len(pdf_authors) < 3 or strong_pdf < max(2, len(pdf_authors) - 1):
            return False
        first_pdf = set(re.findall(r"[a-z]+", _clean_text(pdf_authors[0].get("name", "")).lower()))
        first_existing = set(re.findall(r"[a-z]+", _clean_text((authors or [])[0].get("name", "")).lower()))
        if len(first_pdf & first_existing) < 2:
            return False
    pdf_names = {_name_key(author["name"]) for author in pdf_authors}
    extracted_names = {_name_key(author.get("name", "")) for author in authors or []}
    if pdf_names != extracted_names:
        return True
    # Some ACM layouts expose the author/email block but lose most of the
    # affiliation columns. Do not replace richer TEI metadata with that
    # lower-coverage PDF candidate.
    extracted_affiliation_coverage = sum(
        bool(_dedupe(author.get("affiliations", [])))
        for author in authors or []
    )
    pdf_affiliation_coverage = sum(
        bool(_dedupe(author.get("affiliations", [])))
        for author in pdf_authors
    )
    if pdf_affiliation_coverage < extracted_affiliation_coverage:
        return False
    extracted_affiliation_chars = sum(
        len(item)
        for author in authors or []
        for item in _dedupe(author.get("affiliations", []))
    )
    pdf_affiliation_chars = sum(
        len(item)
        for author in pdf_authors
        for item in _dedupe(author.get("affiliations", []))
    )
    if (
        extracted_affiliation_coverage == pdf_affiliation_coverage
        and extracted_affiliation_chars
        and pdf_affiliation_chars < extracted_affiliation_chars * 0.8
    ):
        return False
    extracted_details = {
        (
            _name_key(author.get("name", "")),
            tuple(_dedupe(author.get("affiliations", []))),
            _clean_text(author.get("email", "")),
        )
        for author in authors or []
    }
    pdf_details = {
        (
            _name_key(author["name"]),
            tuple(_dedupe(author.get("affiliations", []))),
            _clean_text(author.get("email", "")),
        )
        for author in pdf_authors
    }
    return extracted_details != pdf_details


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
                refs = re.split(r"contributed equally|equal contribution|co-first", rest, maxsplit=1, flags=re.IGNORECASE)[0]
                for author_name in author_names:
                    parts = author_name.split()
                    first = parts[0] if parts else ""
                    if author_name in refs or (first and re.search(rf"\b{re.escape(first)}\b", refs)):
                        roles["equal_contribution_names"].add(_name_key(author_name))
            if re.search(r"corresponding authors?", rest, flags=re.IGNORECASE):
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
        if line.lower().startswith(("abstract", "ccs concepts", "keywords")):
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


def _collapse_repeated_phrase(text):
    words = text.split()
    if len(words) % 2 == 0 and words[: len(words) // 2] == words[len(words) // 2 :]:
        return " ".join(words[: len(words) // 2])
    return text


def _strip_author_names(text, authors):
    for author in authors:
        name = _clean_text(author.get("name", ""))
        if name:
            text = re.sub(rf"\b{re.escape(name)}\b", " ", text, flags=re.IGNORECASE)
    return _clean_text(text)


def _normalize_affiliation(text, authors):
    text = common.strip_emails(_strip_author_names(text, authors))
    text = _comma_before_location(text)
    text = text.replace(" ; ", "; ")
    if ";" not in text and _looks_like_org(text):
        return _comma_before_trailing_country(text)
    location_parts = []
    for raw_part in re.split(r";", text):
        part = _comma_before_trailing_country(_comma_before_location(_clean_text(raw_part)))
        if _looks_like_org(part) and (_looks_like_location(part) or _extract_country(part)):
            location_parts.append(part)
    if location_parts:
        return "; ".join(_dedupe(location_parts))
    phrase_hits = _dedupe(_comma_before_trailing_country(match.group(0)) for match in ORG_PHRASE_RE.finditer(text))
    if phrase_hits:
        return "; ".join(phrase_hits)
    parts = []
    for raw_part in re.split(r"[;,]", text):
        part = _comma_before_trailing_country(_collapse_repeated_phrase(_clean_text(raw_part)))
        if not part:
            continue
        if not any(marker in part.lower() for marker in ORG_MARKERS):
            continue
        parts.append(part)
    parts = _dedupe(parts)
    return "; ".join(parts)


def refine_title(title, **kwargs):
    return _clean_text(title)


def refine_authors(authors, **kwargs):
    pdf_lines = kwargs.get("pdf_lines") or []
    pdf_authors = _select_pdf_author_candidate(
        [
            _parse_acm_numbered_author_blocks(pdf_lines),
            _parse_acm_matrix_author_blocks(pdf_lines),
            _parse_acm_per_author_card_blocks(pdf_lines),
            _parse_acm_stacked_column_author_blocks(pdf_lines),
            _parse_acm_grouped_affiliation_blocks(pdf_lines),
            _parse_acm_author_blocks(pdf_lines),
        ],
        authors,
        title=kwargs.get("title", ""),
    )
    if _should_rebuild_from_pdf(pdf_authors, authors):
        corresponding_names = {
            author["name"]
            for author in pdf_authors
            if author.get("corresponding_marker")
        }
        if len(corresponding_names) > 2:
            corresponding_names = set()
        rebuilt = []
        for order, author in enumerate(pdf_authors):
            rebuilt.append({
                "order": order,
                "name": author["name"],
                "email": author["email"],
                "affiliations": _dedupe(
                    _repair_affiliation_text(part)
                    for affiliation in author["affiliations"]
                    for part in _normalize_affiliation(affiliation, pdf_authors).split("; ")
                    if part
                ),
                "affiliation_source": "ccs_pdf",
                "first_author": order == 0,
                "co_first_author": False,
                "equal_contribution": False,
                "corresponding": author["name"] in corresponding_names,
            })
        return _apply_symbol_roles(rebuilt, pdf_lines)

    refined = []
    for author in authors:
        updated = dict(author)
        affiliations = []
        for affiliation in author.get("affiliations", []):
            normalized = _normalize_affiliation(affiliation, authors)
            if normalized:
                affiliations.extend([
                    _repair_affiliation_text(item.strip())
                    for item in normalized.split(";")
                    if item.strip()
                ])
        updated["affiliations"] = _dedupe(affiliations)
        refined.append(updated)
    return _apply_symbol_roles(refined, pdf_lines)
