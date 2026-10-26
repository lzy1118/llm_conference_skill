import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent.parent
PACKAGE_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = PACKAGE_DIR.parent
DATA_DIR = Path(os.environ.get("GROBID_METADATA_DATA_DIR", PROJECT_ROOT / "data")).resolve()
GROBID_RUNTIME_DIR = PACKAGE_DIR / "grobid-runtime"
GROBID_HOME = GROBID_RUNTIME_DIR / "grobid-home"
GROBID_LIB_DIR = GROBID_RUNTIME_DIR / "grobid-core" / "build" / "libs"

NS = {"tei": "http://www.tei-c.org/ns/1.0"}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
EMAIL_LABEL_RE = re.compile(r"\b(?:e[\-\s]?mail|email)\s*:\s*", re.IGNORECASE)
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
NON_ASCII_ALPHA_RE = re.compile(r"[^a-z0-9]+")

ORG_KEYWORDS = [
    "university", "institute", "laboratory", "laboratories", "lab", "labs",
    "school", "college", "department", "faculty", "academy",
    "centre", "center", "foundation", "fondazione", "research",
    "corporation", "corp", "inc", "ltd", "gmbh", "cnrs", "inria",
    "mit", "ibm", "google", "microsoft", "stanford", "berkeley",
    "high school", "huawei", "sap", "national", "engineering",
    "sandia", "cispa", "mozilla", "bloomberg",
]
ORG_STEM_KEYWORDS = ["technolo"]
BLOCK_STOP_MARKERS = ("abstract", "keywords", "1 introduction", "introduction", "doi")
HEADER_NOISE_MARKERS = (
    "proceedings of the", "sponsored by", "isbn", "ieee", "usenix",
    "internet society", "downloaded on", "authorized licensed use",
)
TITLE_WORD_HINTS = (
    "attack", "attacks", "analysis", "apps", "control", "defense", "detecting",
    "fingerprinting", "flow", "fuzzing", "graph", "learning", "model", "models",
    "monitoring", "privacy", "protection", "security", "systems", "transfer",
    "vulnerability", "vulnerabilities",
)

CONFERENCE_STRATEGY_MODULES = {
    "ccs": "author_metadata.strategies.ccs",
    "ieee_s&p": "author_metadata.strategies.ieee_sp",
    "ndss": "author_metadata.strategies.ndss",
    "usenix_security": "author_metadata.strategies.usenix",
    "crypto": "author_metadata.strategies.lncs",
    "eurocrypt": "author_metadata.strategies.lncs",
    "asiacrypt": "author_metadata.strategies.lncs",
}


@dataclass
class DatasetPaths:
    raw_dir: str
    dataset_dir: str
    pdf_stage_dir: str
    xml_dir: str
    json_dir: str
    evidence_dir: str
    candidate_dir: str
    csv_path: str
    abstract_csv_path: str
    index_path: str
    skipped_path: str
    review_path: str
    metrics_path: str


def build_dataset_paths(raw_dir, output_dir, dataset_name):
    dataset_dir = str(Path(output_dir) / dataset_name)
    return DatasetPaths(
        raw_dir=os.path.abspath(raw_dir),
        dataset_dir=dataset_dir,
        pdf_stage_dir=str(Path(dataset_dir) / "pdf_stage"),
        xml_dir=str(Path(dataset_dir) / "tei_header_xml"),
        json_dir=str(Path(dataset_dir) / "metadata_json"),
        evidence_dir=str(Path(dataset_dir) / "evidence_json"),
        candidate_dir=str(Path(dataset_dir) / "candidate_json"),
        csv_path=str(Path(dataset_dir) / "paper_metadata.csv"),
        abstract_csv_path=str(Path(dataset_dir) / "conference_year_paper_abstract.csv"),
        index_path=str(Path(dataset_dir) / "paper_index.csv"),
        skipped_path=str(Path(dataset_dir) / "skipped_files.csv"),
        review_path=str(Path(dataset_dir) / "review_queue.csv"),
        metrics_path=str(Path(dataset_dir) / "extraction_metrics.json"),
    )


def clean_text(text):
    if text is None:
        return ""
    # Some malformed PDF cmap tables yield unpaired UTF-16 surrogates. They
    # are not valid UTF-8 and would make evidence/metadata JSON unserializable.
    text = re.sub(r"[\ud800-\udfff]", "", str(text))
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\uffff]", "", text)
    text = " ".join(text.split()).strip()
    replacements = {
        "T he": "The",
        "F rance": "France",
        "f or": "for",
        "Tec hnology": "Technology",
        "Attac k": "Attack",
        "P Atrick": "Patrick",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


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


def ascii_fold(text):
    text = clean_text(text)
    normalized = unicodedata.normalize("NFKD", text)
    return normalized.encode("ascii", "ignore").decode("ascii")


def compact_text(text):
    return re.sub(r"[^a-z0-9]+", "", ascii_fold(text).lower())


def compact_alpha(text):
    return re.sub(r"[^a-z]+", "", ascii_fold(text).lower())


def normalize_name(text):
    text = clean_text(text).lower()
    text = re.sub(r"[^a-z\s]", " ", text)
    return clean_text(text)


def strip_marker(text):
    text = clean_text(text)
    text = re.sub(r"^[*†‡§¶#\d,;，；\s]+", "", text).strip()
    text = re.sub(r"^[-–—:：\s]+", "", text).strip()
    return clean_text(text)


def replace_pdf_ligatures(text):
    replacements = {
        "ﬁ": "fi",
        "ﬂ": "fl",
        "ﬀ": "ff",
        "ﬃ": "ffi",
        "ﬄ": "ffl",
        "’": "'",
        "–": "-",
        "—": "-",
        "\u00a0": " ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def slugify_filename(text):
    text = clean_text(os.path.splitext(os.path.basename(text))[0]).lower()
    text = text.replace("&amp;", "and")
    text = replace_pdf_ligatures(text)
    text = NON_ASCII_ALPHA_RE.sub("_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "paper"


def normalize_basename(text):
    text = clean_text(os.path.splitext(os.path.basename(text))[0]).lower()
    text = text.replace("&amp;", "and")
    text = re.sub(r"[：:]", " ", text)
    text = re.sub(r"[^0-9a-z]+", "", text)
    return text


def contains_cjk(text):
    return bool(text and CJK_RE.search(text))


def should_skip_input(text):
    return contains_cjk(text)


def looks_like_org(text):
    text = clean_text(text)
    lower = text.lower()
    if any(re.search(rf"\b{re.escape(keyword)}\b", lower) for keyword in ORG_KEYWORDS):
        return True
    if any(stem in lower for stem in ORG_STEM_KEYWORDS):
        return True
    if re.match(r"^(?:uc|ut|ui|nyu|mit|cmu)\s+[A-Z]", text, re.IGNORECASE):
        return True
    if re.match(r"^[A-Z]{2,5}$", text) and text.isupper():
        return True
    return False


def is_noise_text(text):
    lower = clean_text(text).lower()
    noise_markers = [
        "authorized licensed use limited",
        "downloaded on",
        "restrictions apply",
        "ieee xplore",
        "for more convenient discussion",
        "icse '",
        "icse 2",
        "fse '",
        "ase '",
        "ccs '",
        "usenix security",
        "s&p '",
        "is sponsored by",
        "proceedings of the",
        "international conference on",
    ]
    if any(marker in lower for marker in noise_markers):
        return True
    if re.search(r"\b(19|20)\d{2}\.\s+\w+:", lower):
        return True
    if re.search(r",\s*yuan$", lower):
        return True
    if lower.startswith("http://") or lower.startswith("https://"):
        return True
    return False
