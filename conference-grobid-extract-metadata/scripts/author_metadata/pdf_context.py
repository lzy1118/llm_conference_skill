import re
from dataclasses import dataclass, field

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

from author_metadata.config import (
    BLOCK_STOP_MARKERS,
    EMAIL_RE,
    HEADER_NOISE_MARKERS,
    TITLE_WORD_HINTS,
    clean_text,
    looks_like_org,
    replace_pdf_ligatures,
)


@dataclass
class PdfContext:
    first_page_text: str
    first_page_lines: list[str]
    page_lines: dict[int, list[str]]
    title_lines: list[str]
    author_lines: list[str]
    affiliation_lines: list[str]
    email_lines: list[str]
    preabstract_lines: list[str]
    page_blocks: dict[int, list[dict]] = field(default_factory=dict)
    pdf_links: list[dict] = field(default_factory=list)
    document_info: dict[str, str] = field(default_factory=dict)
    extractor_status: dict[str, str] = field(default_factory=dict)
    pypdf_page_lines: dict[int, list[str]] = field(default_factory=dict)


def _extract_page_text_and_blocks(page, page_number):
    blocks = []

    def visitor(text, _cm, tm, _font_dict, font_size):
        raw_text = clean_text(replace_pdf_ligatures(text or ""))
        if not raw_text:
            return
        try:
            x = float(tm[4])
            y = float(tm[5])
            size = float(font_size or 0)
        except (IndexError, TypeError, ValueError):
            return
        width = max(size * 0.45 * len(raw_text), size)
        blocks.append({
            "block_id": f"pdf:p{page_number}:b{len(blocks)}",
            "page": page_number,
            "bbox": [round(x, 3), round(y, 3), round(x + width, 3), round(y + size, 3)],
            "x": round(x, 3),
            "y": round(y, 3),
            "font_size": round(size, 3),
            "raw_text": raw_text,
        })

    try:
        text = replace_pdf_ligatures(page.extract_text(visitor_text=visitor) or "")
    except Exception:
        try:
            text = replace_pdf_ligatures(page.extract_text() or "")
        except Exception:
            text = ""
        blocks = []
    return text, _merge_line_fragments(blocks)


def _extract_page_with_pdfplumber(page, page_number):
    text = replace_pdf_ligatures(page.extract_text(layout=False) or "")
    try:
        words = page.extract_words(
            use_text_flow=True,
            keep_blank_chars=False,
            extra_attrs=["size"],
        )
    except Exception:
        words = page.extract_words(use_text_flow=True, keep_blank_chars=False)

    rows = []
    for word in words or []:
        raw_text = clean_text(replace_pdf_ligatures(word.get("text", "")))
        if not raw_text:
            continue
        top = float(word.get("top", 0))
        size = float(word.get("size") or max(1.0, float(word.get("bottom", top)) - top))
        row = next(
            (
                item
                for item in rows
                if abs(item["top"] - top) <= max(1.2, min(2.5, size * 0.18))
            ),
            None,
        )
        if row is None:
            row = {"top": top, "words": []}
            rows.append(row)
        row["words"].append({**word, "text": raw_text, "size": size})

    blocks = []
    page_height = float(getattr(page, "height", 0) or 0)
    for row in sorted(rows, key=lambda item: item["top"]):
        ordered = sorted(row["words"], key=lambda item: float(item.get("x0", 0)))
        segments = []
        current = []
        for word in ordered:
            if current:
                gap = float(word.get("x0", 0)) - float(current[-1].get("x1", 0))
                size = max(float(word.get("size", 0)), float(current[-1].get("size", 0)))
                if gap > max(20.0, size * 2.0):
                    segments.append(current)
                    current = []
            current.append(word)
        if current:
            segments.append(current)

        for segment in segments:
            x0 = min(float(item.get("x0", 0)) for item in segment)
            x1 = max(float(item.get("x1", x0)) for item in segment)
            top = min(float(item.get("top", 0)) for item in segment)
            bottom = max(float(item.get("bottom", top)) for item in segment)
            font_size = max(float(item.get("size", 0)) for item in segment)
            y = page_height - top
            blocks.append({
                "block_id": "",
                "page": page_number,
                "bbox": [round(x0, 3), round(page_height - bottom, 3), round(x1, 3), round(y, 3)],
                "x": round(x0, 3),
                "y": round(y, 3),
                "font_size": round(font_size, 3),
                "raw_text": clean_text(" ".join(item["text"] for item in segment)),
                "extractor": "pdfplumber",
            })
    for index, block in enumerate(sorted(blocks, key=lambda item: (-item["y"], item["x"]))):
        block["block_id"] = f"pdfplumber:p{page_number}:b{index}"
    return text, sorted(blocks, key=lambda item: (-item["y"], item["x"]))


def _extract_pypdf_supplement(pdf_path):
    if not PdfReader:
        return [], {}, "unavailable", {}
    try:
        reader = PdfReader(pdf_path)
    except Exception as exc:
        return [], {}, f"error:{type(exc).__name__}", {}

    try:
        metadata = {}
        for key, value in (reader.metadata or {}).items():
            cleaned = clean_text(value)
            if cleaned:
                metadata[str(key).lstrip("/")] = cleaned

        links = []
        page_lines = {}
        for page_index, page in enumerate(reader.pages[:2], start=1):
            try:
                text = replace_pdf_ligatures(page.extract_text() or "")
                page_lines[page_index] = [clean_text(line) for line in text.splitlines() if clean_text(line)]
            except Exception:
                page_lines[page_index] = []
            for annotation_ref in page.get("/Annots", []) or []:
                try:
                    annotation = annotation_ref.get_object()
                    if str(annotation.get("/Subtype", "")) != "/Link":
                        continue
                    action = annotation.get("/A")
                    action = action.get_object() if hasattr(action, "get_object") else action
                    uri = clean_text(action.get("/URI", "") if action else "")
                    if not uri:
                        continue
                    rect = [float(value) for value in (annotation.get("/Rect", []) or [])]
                    links.append({
                        "link_id": f"pypdf:p{page_index}:link:{len(links)}",
                        "page": page_index,
                        "bbox": rect,
                        "uri": uri,
                        "contents": clean_text(annotation.get("/Contents", "")),
                    })
                except Exception:
                    continue
    except Exception as exc:
        return [], {}, f"error:{type(exc).__name__}", {}
    return links, metadata, "ok", page_lines


def _merge_line_fragments(blocks):
    """Merge word-level visitor fragments that form one visual text line."""
    if not blocks:
        return []
    rows = []
    for block in sorted(blocks, key=lambda item: (-float(item.get("y", 0)), float(item.get("x", 0)))):
        row = next(
            (
                item
                for item in rows
                if abs(item["y"] - float(block.get("y", 0))) <= 0.8
                and abs(item["font_size"] - float(block.get("font_size", 0))) <= 0.8
            ),
            None,
        )
        if row is None:
            row = {
                "y": float(block.get("y", 0)),
                "font_size": float(block.get("font_size", 0)),
                "blocks": [],
            }
            rows.append(row)
        row["blocks"].append(block)

    merged = []
    for row in rows:
        segment = []
        for block in sorted(row["blocks"], key=lambda item: float(item.get("x", 0))):
            if segment:
                previous = segment[-1]
                gap = float(block.get("bbox", [0, 0, 0, 0])[0]) - float(previous.get("bbox", [0, 0, 0, 0])[2])
                combined_width = float(block.get("bbox", [0, 0, 0, 0])[2]) - float(segment[0].get("bbox", [0, 0, 0, 0])[0])
                crosses_compact_column = row["font_size"] < 11.2 and combined_width > 250
                if gap > max(20.0, row["font_size"] * 2.0) or crosses_compact_column:
                    merged.append(_merge_block_segment(segment, page_number=block.get("page", 1)))
                    segment = []
            segment.append(block)
        if segment:
            merged.append(_merge_block_segment(segment, page_number=segment[0].get("page", 1)))
    for index, block in enumerate(sorted(merged, key=lambda item: (-item["y"], item["x"]))):
        block["block_id"] = f"pdf:p{block['page']}:b{index}"
    return sorted(merged, key=lambda item: (-item["y"], item["x"]))


def _merge_block_segment(segment, page_number):
    if len(segment) == 1:
        return dict(segment[0])
    x0 = min(float(item["bbox"][0]) for item in segment)
    y0 = min(float(item["bbox"][1]) for item in segment)
    x1 = max(float(item["bbox"][2]) for item in segment)
    y1 = max(float(item["bbox"][3]) for item in segment)
    return {
        "block_id": "",
        "page": page_number,
        "bbox": [round(x0, 3), round(y0, 3), round(x1, 3), round(y1, 3)],
        "x": round(x0, 3),
        "y": round(y0, 3),
        "font_size": round(max(float(item.get("font_size", 0)) for item in segment), 3),
        "raw_text": clean_text(" ".join(item.get("raw_text", "") for item in segment)),
    }


def _looks_like_email_line(text):
    text = clean_text(text)
    return bool(text and ("@" in text or EMAIL_RE.search(text) or "}" in text and "@" in text))


def _looks_like_affiliation_line(text):
    text = clean_text(text)
    if not text:
        return False
    lower = text.lower()
    if lower.startswith(BLOCK_STOP_MARKERS):
        return False
    if looks_like_org(text):
        return True
    return bool(re.search(r"\b(?:usa|uk|china|germany|france|singapore|korea|hong kong)\b", lower))


def _looks_like_person_line(text):
    text = clean_text(text)
    if not text:
        return False
    if len(text) > 80 or "abstract" in text.lower():
        return False
    if any(char.isdigit() for char in text):
        return False
    tokens = re.findall(r"[A-Za-z][A-Za-z'.-]*", text)
    if not tokens or len(tokens) > 8:
        return False
    capitalized = sum(1 for token in tokens if token[:1].isupper())
    return capitalized == len(tokens)


def _looks_like_author_block_line(text):
    text = clean_text(text)
    if not text:
        return False
    lower = text.lower()
    if lower.startswith(BLOCK_STOP_MARKERS):
        return False
    if _looks_like_affiliation_line(text) or _looks_like_email_line(text):
        return False
    if len(text) > 200:
        return False
    comma_count = text.count(",")
    semicolon_count = text.count(";")
    and_count = len(re.findall(r"\band\b", lower))
    capitalized_words = re.findall(r"\b[A-Z][A-Za-z'.-]+\b", text)
    alpha_tokens = re.findall(r"[A-Za-z][A-Za-z'.-]*", text)
    if any(hint in lower for hint in TITLE_WORD_HINTS) and comma_count == 0 and semicolon_count == 0:
        return False
    person_line = _looks_like_person_line(text) and 1 < len(alpha_tokens) <= 3
    return len(capitalized_words) >= 2 and (
        comma_count >= 1 or semicolon_count >= 1 or and_count >= 1 or person_line
    )


def _looks_like_page_header_line(text):
    text = clean_text(text)
    if not text:
        return True
    lower = text.lower()
    if any(marker in lower for marker in HEADER_NOISE_MARKERS):
        return True
    if re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}[-–]\d{1,2},\s*(?:19|20)\d{2}\b", lower):
        return True
    if re.search(r"\b(?:19|20)\d{2}\s*[•,]\s*[A-Z][A-Za-z]+", text):
        return True
    if re.fullmatch(r"(?:97[89][-\d ]{8,}|(?:\d[- ]*){10,})", text):
        return True
    return False


def _parse_first_page_structure(lines):
    if not lines:
        return {
            "title_lines": [],
            "author_lines": [],
            "affiliation_lines": [],
            "email_lines": [],
            "preabstract_lines": [],
        }

    filtered = []
    for line in lines[:40]:
        if _looks_like_page_header_line(line):
            continue
        filtered.append(line)

    preabstract_lines = []
    for line in filtered:
        if line.lower().startswith(BLOCK_STOP_MARKERS):
            break
        preabstract_lines.append(line)

    title_lines = []
    author_lines = []
    affiliation_lines = []
    email_lines = []
    stage = "title"

    for line in preabstract_lines:
        lower = line.lower()
        if lower.startswith(BLOCK_STOP_MARKERS):
            break

        if _looks_like_email_line(line):
            email_lines.append(line)
            if stage in {"title", "authors"}:
                stage = "affiliations"
            continue

        if stage == "title":
            if _looks_like_author_block_line(line) and title_lines:
                stage = "authors"
            elif _looks_like_affiliation_line(line) and title_lines:
                stage = "affiliations"
            else:
                title_lines.append(line)
                continue

        if stage == "authors":
            if _looks_like_affiliation_line(line):
                stage = "affiliations"
                affiliation_lines.append(line)
            else:
                author_lines.append(line)
            continue

        if stage == "affiliations":
            if _looks_like_author_block_line(line) and not _looks_like_affiliation_line(line):
                author_lines.append(line)
            else:
                affiliation_lines.append(line)

    if not author_lines and title_lines:
        trailing = []
        while title_lines and _looks_like_author_block_line(title_lines[-1]):
            trailing.insert(0, title_lines.pop())
        author_lines.extend(trailing)

    return {
        "title_lines": title_lines,
        "author_lines": author_lines,
        "affiliation_lines": affiliation_lines,
        "email_lines": email_lines,
        "preabstract_lines": preabstract_lines,
    }


def load_pdf_context(pdf_path):
    if not pdf_path:
        return PdfContext("", [], {}, [], [], [], [], [])
    page_lines = {}
    page_blocks = {}
    first_page_text = ""
    first_page_lines = []
    extractor_status = {
        "pdfplumber": "unavailable" if pdfplumber is None else "pending",
        "pypdf": "unavailable" if PdfReader is None else "pending",
    }

    if pdfplumber is not None:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_index, page in enumerate(pdf.pages[:2], start=1):
                    text, blocks = _extract_page_with_pdfplumber(page, page_index)
                    lines = [clean_text(line) for line in text.splitlines() if clean_text(line)]
                    page_lines[page_index] = lines
                    page_blocks[page_index] = blocks
                    if page_index == 1:
                        first_page_text = text
                        first_page_lines = lines
            extractor_status["pdfplumber"] = "ok"
        except Exception as exc:
            extractor_status["pdfplumber"] = f"error:{type(exc).__name__}"

    links, document_info, pypdf_status, pypdf_page_lines = _extract_pypdf_supplement(pdf_path)
    extractor_status["pypdf"] = pypdf_status

    if not page_lines and PdfReader is not None:
        try:
            reader = PdfReader(pdf_path)
            for page_index, page in enumerate(reader.pages[:2], start=1):
                text, blocks = _extract_page_text_and_blocks(page, page_index)
                for block in blocks:
                    block["extractor"] = "pypdf_fallback"
                lines = [clean_text(line) for line in text.splitlines() if clean_text(line)]
                page_lines[page_index] = lines
                page_blocks[page_index] = blocks
                if page_index == 1:
                    first_page_text = text
                    first_page_lines = lines
            extractor_status["pypdf_text_fallback"] = "ok"
        except Exception as exc:
            extractor_status["pypdf_text_fallback"] = f"error:{type(exc).__name__}"

    parsed = _parse_first_page_structure(first_page_lines)
    return PdfContext(
        first_page_text=first_page_text,
        first_page_lines=first_page_lines,
        page_lines=page_lines,
        title_lines=parsed["title_lines"],
        author_lines=parsed["author_lines"],
        affiliation_lines=parsed["affiliation_lines"],
        email_lines=parsed["email_lines"],
        preabstract_lines=parsed["preabstract_lines"],
        page_blocks=page_blocks,
        pdf_links=links,
        document_info=document_info,
        extractor_status=extractor_status,
        pypdf_page_lines=pypdf_page_lines,
    )


def extract_preabstract_text(pdf_context):
    return "\n".join(pdf_context.preabstract_lines)


def extract_title_hint(pdf_context):
    return clean_text(" ".join(pdf_context.title_lines[:3]))


_ABSTRACT_START_RE = re.compile(r"^\s*(?:abstract|summary)\b\s*[:.\-—–]?\s*(.*)$", re.IGNORECASE)
_ABSTRACT_STOP_RE = re.compile(
    r"^\s*(?:keywords?|index terms?|ccs concepts?|categories and subject descriptors|"
    r"acm reference format|\d+(?:\.\d+)*\s+introduction\b|i\.?\s+introduction\b|introduction\b)",
    re.IGNORECASE,
)


def _extract_abstract_from_lines(lines):
    captured = []
    started = False
    for line in lines:
        line = clean_text(line)
        if not line:
            continue
        if not started:
            match = _ABSTRACT_START_RE.match(line)
            if not match:
                continue
            started = True
            remainder = clean_text(match.group(1))
            if remainder:
                captured.append(remainder)
            continue
        if _ABSTRACT_STOP_RE.match(line):
            return clean_text(" ".join(captured))
        if _looks_like_page_header_line(line):
            continue
        captured.append(line)
        if len(" ".join(captured)) >= 12000:
            return clean_text(" ".join(captured))
    return clean_text(" ".join(captured))


def extract_abstract_from_pdf_context(pdf_context):
    """Extract a conservative PDF abstract candidate with explicit section boundaries."""
    plumber_lines = [
        line
        for page_number in sorted((pdf_context.page_lines or {}).keys())
        for line in pdf_context.page_lines.get(page_number, [])
    ]
    plumber_candidate = _extract_abstract_from_lines(plumber_lines)
    pypdf_lines = [
        line
        for page_number in sorted(getattr(pdf_context, "pypdf_page_lines", {}).keys())
        for line in getattr(pdf_context, "pypdf_page_lines", {}).get(page_number, [])
    ]
    pypdf_candidate = _extract_abstract_from_lines(pypdf_lines)
    if not plumber_candidate:
        return pypdf_candidate
    if not pypdf_candidate:
        return plumber_candidate

    def readability(text):
        letters = sum(char.isalpha() for char in text)
        spaces = text.count(" ")
        return spaces / max(1, letters)

    # Some embedded fonts make pdfplumber concatenate words.  pypdf is retained
    # as a text-quality fallback for the same page, while its links remain the
    # independent evidence channel.
    if readability(pypdf_candidate) > readability(plumber_candidate) * 1.25:
        return pypdf_candidate
    return plumber_candidate
