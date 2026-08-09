import re

from author_metadata.config import compact_alpha, looks_like_org


def is_org_name(name):
    if looks_like_org(name):
        return True
    return bool(re.match(r"^[A-Z](?:\s+[A-Z])+\s+[A-Z][a-z]", name))


def is_abbreviated_duplicate(name, existing_names):
    name_lower = name.lower().strip()
    for existing in existing_names:
        existing_lower = existing.lower().strip()
        if name_lower == existing_lower:
            continue
        if compact_alpha(name) and compact_alpha(name) == compact_alpha(existing):
            return True
        parts = name_lower.split()
        existing_parts = existing_lower.split()
        if len(parts) == 2 and len(existing_parts) >= 2:
            if parts[1] == existing_parts[-1] and len(parts[0]) == 1 and existing_parts[0].startswith(parts[0]):
                return True
            if parts[1] == existing_parts[-1] and parts[0] == existing_parts[0][:len(parts[0])]:
                return True
        if len(parts) == 1 and len(existing_parts) >= 2 and parts[0] == existing_parts[-1]:
            return True
    return False


def is_author_name_noise(name):
    if not name:
        return True
    if any(symbol in name for symbol in ["]", "[", "⊕", "Δ", "•"]):
        return True
    if re.match(r"^[;,:.]", name):
        return True
    if len(name.replace(" ", "")) <= 2:
        return True
    parts = name.split()
    if len(parts) == 1 and not name[0].isupper():
        return True
    if not re.search(r"[a-zA-Z]", name):
        return True
    if len(parts) == 1:
        return True
    if any(token in name for token in ["•", "+"]):
        return True
    lower = name.lower()
    noise_terms = {
        "modified", "lightmac", "pmac", "classic", "algocrypt", "single-key",
        "lightweight", "security", "robustness", "asynchronous", "network",
        "work", "approach", "cryptanalysis", "integral", "adaptive", "sim",
    }
    return any(re.search(rf"\b{re.escape(term)}\b", lower) for term in noise_terms)
