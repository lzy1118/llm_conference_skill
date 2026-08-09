import re


AFFILIATION_SYMBOLS = "*∗⋆†‡§¶"
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def clean_text(text):
    return " ".join(str(text or "").split()).strip()


def normalize_detached_diacritics(text):
    text = str(text or "")
    return re.sub(
        r"\s*¨\s*([AaOoUu])",
        lambda m: {"a": "ä", "o": "ö", "u": "ü"}.get(m.group(1).lower(), m.group(1)),
        text,
    )


def dedupe(items):
    result = []
    seen = set()
    for item in items:
        item = clean_text(item)
        if not item:
            continue
        key = item.lower()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def name_key(text):
    return re.sub(r"[^a-z]+", "", clean_text(text).lower())


def clean_author_name(text):
    text = clean_text(normalize_detached_diacritics(text))
    text = re.sub(r"\b([A-Z])\s+([a-z]{2,})\b", r"\1\2", text)
    text = re.sub(r"^(?:and|,|;)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(rf"^[{re.escape(AFFILIATION_SYMBOLS)}]+\s*", "", text)
    text = re.sub(rf"\s*[{re.escape(AFFILIATION_SYMBOLS)}]+\s*$", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ,;")


def strip_emails(text):
    text = clean_text(text)
    text = re.sub(r"\{[^}]+\}@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", " ", text)
    text = EMAIL_RE.sub(" ", text)
    text = re.sub(r"\s*,\s*(?=$|[;,])", "", text)
    return clean_text(text).strip(" ,;")


def comma_before_trailing_country(text, country_terms):
    text = clean_text(text)
    for country in sorted(country_terms, key=len, reverse=True):
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


def affiliation_symbol_tokens(text):
    return re.findall(rf"[{re.escape(AFFILIATION_SYMBOLS)}]", clean_text(text))


def parse_symbol_affiliation_line(line, normalize_affiliation, looks_like_org):
    line = clean_text(line)
    pattern = re.compile(
        rf"([{re.escape(AFFILIATION_SYMBOLS)}])\s*"
        rf"(.+?)(?=\s*[{re.escape(AFFILIATION_SYMBOLS)}]\s*[^\s{re.escape(AFFILIATION_SYMBOLS)}]|$)"
    )
    result = {}
    for match in pattern.finditer(line):
        affiliation = normalize_affiliation(match.group(2))
        if affiliation and looks_like_org(affiliation):
            result[match.group(1)] = affiliation
    return result


def extract_symbol_author_refs(line):
    line = clean_text(normalize_detached_diacritics(line))
    name_token = r"[^\W\d_][^\W\d_]*(?:[.'-][^\W\d_]+)*"
    pattern = re.compile(
        rf"({name_token}(?:\s+{name_token}){{1,5}})"
        rf"\s*([{re.escape(AFFILIATION_SYMBOLS)}](?:\s*,?\s*[{re.escape(AFFILIATION_SYMBOLS)}])*)"
    )
    refs = []
    for match in pattern.finditer(line):
        name = clean_author_name(match.group(1))
        symbols = affiliation_symbol_tokens(match.group(2))
        if len(name.split()) >= 2 and symbols:
            refs.append((name, symbols))
    return refs


def parse_symbol_author_affiliations(author_line, affiliation_line, normalize_affiliation, looks_like_org):
    author_refs = extract_symbol_author_refs(author_line)
    affiliation_by_symbol = parse_symbol_affiliation_line(
        affiliation_line,
        normalize_affiliation,
        looks_like_org,
    )
    if len(author_refs) < 2 or not affiliation_by_symbol:
        return []
    authors = []
    for name, symbols in author_refs:
        affiliations = [affiliation_by_symbol[symbol] for symbol in symbols if symbol in affiliation_by_symbol]
        authors.append({
            "name": name,
            "affiliations": dedupe(affiliations),
        })
    return authors
