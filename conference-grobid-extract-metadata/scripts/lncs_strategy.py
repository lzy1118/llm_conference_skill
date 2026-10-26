"""LNCS/Springer metadata refinements shared by cryptography conferences."""

from __future__ import annotations

import re

from author_metadata.config import ascii_fold, clean_text, compact_alpha, looks_like_org


_ENVELOPE_MARKERS = ("✉", "✉︎", "\uf0d0", "\uf02a")


def _searchable_text(value: str) -> str:
    text = value or ""
    for marker in _ENVELOPE_MARKERS:
        text = text.replace(marker, "(B)")
    text = ascii_fold(text).lower()
    return re.sub(r"[\s.'’`-]+", "", text)


def _author_region(pdf_lines: list[str]) -> str:
    lines = []
    for line in pdf_lines or []:
        cleaned = clean_text(line)
        if not cleaned:
            continue
        if re.match(r"^abstract\b", cleaned, flags=re.IGNORECASE):
            break
        lines.append(cleaned)
    return " ".join(lines)


def _normalized_marker_line(line: str) -> str:
    text = line or ""
    for marker in _ENVELOPE_MARKERS:
        text = text.replace(marker, "(B)")
    return text


def _marker_name_candidates(pdf_lines: list[str]) -> list[str]:
    candidates = []
    for raw_line in pdf_lines or []:
        line = _normalized_marker_line(clean_text(raw_line))
        if not line or re.match(r"^abstract\b", line, flags=re.IGNORECASE):
            break
        for marker in re.finditer(r"\(B\)", line, flags=re.IGNORECASE):
            prefix = line[:marker.start()]
            prefix = re.split(r"\(B\)", prefix, flags=re.IGNORECASE)[-1]
            prefix = re.sub(r"\d+(?:\s*,\s*\d+)*\s*$", "", prefix)
            part = re.split(r",|\band\b", prefix, flags=re.IGNORECASE)[-1]
            part = clean_text(part).strip(" ,;()")
            alpha_tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ.'’`-]*", part)
            if not alpha_tokens or len(alpha_tokens) > 8:
                continue
            if len(alpha_tokens) > 2 and sum(len(token) == 1 for token in alpha_tokens) > len(alpha_tokens) // 2:
                continue
            candidates.append(part)
    return list(dict.fromkeys(candidates))


def _same_person(left: str, right: str) -> bool:
    left_key = compact_alpha(left)
    right_key = compact_alpha(right)
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True
    left_tokens = {compact_alpha(token) for token in left.split() if compact_alpha(token)}
    right_tokens = {compact_alpha(token) for token in right.split() if compact_alpha(token)}
    return bool(left_tokens and left_tokens == right_tokens)


def _author_position(name: str, author_region: str) -> int:
    region = _searchable_text(author_region)
    key = _searchable_text(name)
    position = region.find(key)
    if position >= 0:
        return position
    tokens = [compact_alpha(token) for token in name.split() if len(compact_alpha(token)) >= 3]
    positions = [region.find(token) for token in tokens if region.find(token) >= 0]
    return min(positions) if positions else len(region)


def _has_corresponding_marker(author_name: str, author_region: str) -> bool:
    name = _searchable_text(author_name)
    region = _searchable_text(author_region)
    if not name or not region:
        return False
    position = region.find(name)
    if position < 0:
        return False
    suffix = region[position + len(name):position + len(name) + 24]
    return bool(re.match(r"^[^a-z]{0,16}\(b\)", suffix))


def _compact_alnum(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", ascii_fold(value or "").lower())


def _author_affiliation_numbers(author_name: str, pdf_lines: list[str]) -> list[str]:
    name_key = _searchable_text(author_name)
    if not name_key:
        return []
    for raw_line in pdf_lines or []:
        line = clean_text(raw_line)
        if re.match(r"^\d+\s+", line) or re.match(r"^abstract\b", line, re.IGNORECASE):
            break
        searchable_line = _searchable_text(_normalized_marker_line(line))
        position = searchable_line.find(name_key)
        if position < 0:
            continue
        suffix = searchable_line[position + len(name_key):]
        match = re.match(r"(\d+(?:,\d+)*)", suffix)
        if match:
            return match.group(1).split(",")
    return []


def _numbered_affiliations(pdf_lines: list[str]) -> dict[str, str]:
    affiliations: dict[str, list[str]] = {}
    current = ""
    for raw_line in pdf_lines or []:
        line = clean_text(raw_line)
        if not line:
            continue
        if re.match(r"^abstract\b", line, re.IGNORECASE):
            break
        match = re.match(r"^(\d+)\s+(.+)$", line)
        if match:
            current = match.group(1)
            affiliations[current] = [match.group(2)]
            continue
        if "@" in line:
            current = ""
            continue
        if current:
            affiliations[current].append(line)
    return {
        number: clean_text(" ".join(parts))
        for number, parts in affiliations.items()
        if clean_text(" ".join(parts))
    }


def _shared_affiliation(pdf_lines: list[str], author_names: list[str]) -> str:
    last_author_line = -1
    name_keys = [_compact_alnum(name) for name in author_names if _compact_alnum(name)]
    for index, raw_line in enumerate(pdf_lines or []):
        line = clean_text(raw_line)
        if "@" in line or re.match(r"^\d+\s+", line):
            break
        line_key = _compact_alnum(_normalized_marker_line(line))
        if looks_like_org(line) and not any(key in line_key for key in name_keys):
            break
        if any(key in line_key for key in name_keys):
            last_author_line = index
    if last_author_line < 0:
        return ""
    candidates = []
    for raw_line in (pdf_lines or [])[last_author_line + 1:]:
        line = clean_text(raw_line)
        if not line or re.match(r"^abstract\b", line, re.IGNORECASE) or "@" in line:
            break
        if re.match(r"^\d+\s+", line):
            return ""
        if looks_like_org(line):
            candidates.append(line)
    return candidates[0] if len(candidates) == 1 else ""


def refine_title(title: str, **_kwargs) -> str:
    return clean_text(title)


def refine_authors(authors: list[dict], **kwargs) -> list[dict]:
    pdf_lines = kwargs.get("pdf_lines") or []
    author_region = _author_region(pdf_lines)
    marker_names = _marker_name_candidates(pdf_lines)
    refined = []
    for author in authors:
        updated = dict(author)
        updated.setdefault("first_author", updated.get("order") == 0)
        updated.setdefault("co_first_author", False)
        updated.setdefault("equal_contribution", False)
        updated.setdefault("corresponding", False)
        if _has_corresponding_marker(updated.get("name", ""), author_region) or any(
            _same_person(updated.get("name", ""), candidate)
            for candidate in marker_names
        ):
            updated["corresponding"] = True
        refined.append(updated)

    for candidate in marker_names:
        if any(_same_person(item.get("name", ""), candidate) for item in refined):
            continue
        refined.append({
            "order": len(refined),
            "name": candidate,
            "email": "",
            "affiliations": [],
            "affiliation_source": "lncs_pdf_corresponding_marker",
            "first_author": False,
            "co_first_author": False,
            "equal_contribution": False,
            "corresponding": True,
        })

    refined.sort(key=lambda item: _author_position(item.get("name", ""), author_region))
    numbered_affiliations = _numbered_affiliations(pdf_lines)
    author_numbers = {
        id(author): _author_affiliation_numbers(author.get("name", ""), pdf_lines)
        for author in refined
    }
    required_numbers = {
        number for numbers in author_numbers.values() for number in numbers
    }
    numbered_complete = bool(required_numbers) and required_numbers.issubset(numbered_affiliations)
    shared_affiliation = (
        ""
        if numbered_affiliations
        else _shared_affiliation(pdf_lines, [item.get("name", "") for item in refined])
    )
    for order, author in enumerate(refined):
        author["order"] = order
        author["first_author"] = order == 0 or bool(author.get("co_first_author"))
        numbers = author_numbers.get(id(author), [])
        mapped = [numbered_affiliations[number] for number in numbers] if numbered_complete else []
        if numbers and numbered_complete:
            author["affiliations"] = list(dict.fromkeys(mapped))
            author["affiliation_source"] = "lncs_pdf_numbered"
        elif shared_affiliation and not author.get("affiliations"):
            author["affiliations"] = [shared_affiliation]
            author["affiliation_source"] = "lncs_pdf_shared"
    return refined
