import json
import re
from pathlib import Path

from author_metadata.exporter import export_json
from author_metadata.author_order import get_export_author_rank


COUNTRY_ALIASES = {
    "australia": "Australia", "austria": "Austria", "belgium": "Belgium", "argentina": "Argentina",
    "brazil": "Brazil", "canada": "Canada", "china": "China", "cn": "China",
    "people's republic of china": "China", "pr china": "China",
    "colombia": "Colombia", "costa rica": "Costa Rica",
    "czech republic": "Czech Republic", "denmark": "Denmark", "england": "UK",
    "estonia": "Estonia", "finland": "Finland", "france": "France",
    "german": "Germany", "germany": "Germany", "greece": "Greece", "hong kong": "Hong Kong",
    "hungary": "Hungary", "india": "India", "iran": "Iran", "israel": "Israel",
    "italy": "Italy", "japan": "Japan", "korea": "South Korea",
    "republic of korea": "South Korea", "south korea": "South Korea",
    "ireland": "Ireland", "iceland": "Iceland", "luxembourg": "Luxembourg", "malaysia": "Malaysia",
    "mexico": "Mexico", "netherlands": "Netherlands",
    "the netherlands": "Netherlands", "new zealand": "New Zealand", "norway": "Norway",
    "pakistan": "Pakistan", "poland": "Poland", "portugal": "Portugal", "romania": "Romania",
    "russia": "Russia", "serbia": "Serbia", "slovenia": "Slovenia", "south africa": "South Africa",
    "saudi arabia": "Saudi Arabia", "singapore": "Singapore", "slovakia": "Slovakia",
    "spain": "Spain", "sweden": "Sweden", "switzerland": "Switzerland",
    "taiwan": "Taiwan", "uae": "United Arab Emirates",
    "united arab emirates": "United Arab Emirates", "uk": "UK",
    "thailand": "Thailand", "turkey": "Turkey", "türkiye": "Turkey", "ukraine": "Ukraine",
    "united kingdom": "UK", "us": "USA", "usa": "USA", "united states": "USA",
    "united states of america": "USA", "vietnam": "Vietnam",
}


def trailing_country(affiliation):
    """Return a country only when a known country is an explicit final token."""
    text = " ".join(str(affiliation or "").split()).strip(" ,.;")
    if not text:
        return ""
    token = text.rsplit(",", 1)[-1].strip(" .;()[]").casefold()
    if token in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[token]
    # PDF text layers sometimes separate every country letter (for example
    # "Z a m a, P a r i s, F r a n c e"). Only collapse a terminal token when
    # all whitespace-separated components are single letters, so ordinary
    # multi-word country names keep their normal matching path.
    token_parts = token.split()
    if len(token_parts) > 1 and all(len(part) == 1 and part.isalpha() for part in token_parts):
        collapsed_token = "".join(token_parts)
        if collapsed_token in COUNTRY_ALIASES:
            return COUNTRY_ALIASES[collapsed_token]
    for alias, normalized in sorted(COUNTRY_ALIASES.items(), key=lambda item: -len(item[0])):
        if re.search(rf"(?:^|[,;\s]){re.escape(alias)}$", text.casefold()):
            return normalized
    return ""


def merge_countries_with_pdf_priority(affiliations, pdf_countries):
    """Keep countries extracted from the PDF; use affiliation text only for gaps."""
    countries = [trailing_country(affiliation) for affiliation in affiliations]
    if len(countries) > 1 and countries[-1] and not any(countries[:-1]):
        countries = [countries[-1]] * len(countries)

    preserved = [trailing_country(country) for country in (pdf_countries or [])]
    nonempty = [country for country in preserved if country]
    if len(set(nonempty)) == 1:
        return [nonempty[0]] * len(affiliations)
    return [
        preserved[index]
        if index < len(preserved) and preserved[index]
        else countries[index]
        for index in range(len(affiliations))
    ]


def _orcid(value):
    value = str(value or "").strip()
    if not value:
        return ""
    match = re.search(r"(?:https?://)?(?:orcid\.org/)?(\d{4}-\d{4}-\d{4}-[\dX]{4})", value, re.I)
    return f"https://orcid.org/{match.group(1).upper()}" if match else ""


ACTION_METRICS = {
    "restore_nonempty_field": "restored_fields",
    "fill_from_pdf_layout": "layout_affiliations_filled",
    "fill_default_and_symbol_affiliations_from_pdf": "default_symbol_affiliations_filled",
    "fill_ordered_group_email_from_pdf": "ordered_group_emails_filled",
    "fill_affiliation_note_from_pdf": "affiliation_note_fills",
    "fill_affiliation_note_from_pdf_layout": "affiliation_note_fills",
    "replace_affiliations_from_complete_symbol_layout": "complete_symbol_affiliations_replaced",
    "fill_affiliation_from_email_domain": "email_domain_affiliations_filled",
    "replace_fragmented_affiliation_from_pdf_layout": "fragmented_affiliations_replaced",
    "rebuild_author_list_from_pdf_layout": "layout_author_lists_rebuilt",
    "reject_author_list_rebuild": "author_list_rebuilds_rejected",
    "remove_organization_author": "organization_authors_removed",
}


def new_metrics(papers_total, include_extended=False):
    metrics = {
        "schema_version": "1.0",
        "papers_total": papers_total,
        "papers_processed": 0,
        "authors_exported": 0,
        "abstracts_extracted": 0,
        "parse_errors": 0,
        "papers_without_authors": 0,
        "papers_requiring_review": 0,
        "review_reasons": 0,
        "restored_fields": 0,
        "layout_affiliations_filled": 0,
        "fragmented_affiliations_replaced": 0,
        "layout_author_lists_rebuilt": 0,
        "default_symbol_affiliations_filled": 0,
        "ordered_group_emails_filled": 0,
        "affiliation_note_fills": 0,
        "complete_symbol_affiliations_replaced": 0,
        "email_domain_affiliations_filled": 0,
    }
    if include_extended:
        metrics.update({
            "author_list_rebuilds_rejected": 0,
            "organization_authors_removed": 0,
        })
    return metrics


def update_metrics(metrics, metadata):
    extraction = metadata.get("_extraction", {})
    reasons = extraction.get("review_reasons", [])
    metrics["papers_processed"] += 1
    metrics["authors_exported"] += len(metadata.get("authors", []))
    metrics["abstracts_extracted"] += bool(metadata.get("abstract"))
    metrics["papers_without_authors"] += not bool(metadata.get("authors"))
    metrics["papers_requiring_review"] += bool(reasons)
    metrics["review_reasons"] += len(reasons)
    for decision in extraction.get("decisions", []):
        metric = ACTION_METRICS.get(decision.get("action"))
        if metric in metrics:
            metrics[metric] += 1


def author_csv_rows(paper_id, metadata, author, conference):
    affiliations = [
        part.strip()
        for item in author.get("affiliations", [])
        for part in re.split(r"[;；]", str(item))
        if part.strip()
    ]
    if not affiliations:
        affiliations = [""]
    countries = merge_countries_with_pdf_priority(
        affiliations,
        author.get("pdf_countries", []),
    )
    author_rank = get_export_author_rank(author, metadata["authors"])
    common = {
        "paper_id": paper_id,
        "year": metadata.get("year", ""),
        "conference": conference,
        "title": metadata.get("title", ""),
        "author": author.get("name", ""),
        "author_rank": author_rank,
        "emails": author.get("email", ""),
        "first_author": str(author.get("first_author", False)).lower(),
        "co_first_author": str(author.get("co_first_author", False)).lower(),
        "corresponding": str(author.get("corresponding", False)).lower(),
        "equal_contribution": str(author.get("equal_contribution", False)).lower(),
        "orcid": _orcid(author.get("orcid", "")),
    }
    return [
        {
            **common,
            "affiliation_rank": index,
            "affiliations": affiliation,
            "country": countries[index],
        }
        for index, affiliation in enumerate(affiliations)
    ]


def author_csv_row(paper_id, metadata, author, conference):
    """Backward-compatible single-row accessor; exporters use author_csv_rows."""
    return author_csv_rows(paper_id, metadata, author, conference)[0]


def placeholder_author_row(paper_id, year, conference, title, status):
    return {
        "paper_id": paper_id,
        "year": year,
        "conference": conference,
        "title": title,
        "author": status,
        "author_rank": "",
        "affiliation_rank": "",
        "affiliations": "",
        "emails": "",
        "first_author": "",
        "co_first_author": "",
        "corresponding": "",
        "equal_contribution": "",
        "country": "",
        "orcid": "",
    }


def abstract_csv_row(metadata, conference, fallback_title="", fallback_year=""):
    return {
        "conference": conference,
        "year": metadata.get("year", "") or fallback_year,
        "title": metadata.get("title", "") or fallback_title,
        "abstract": metadata.get("abstract", ""),
    }


def review_csv_rows(paper_id, source_file, reasons):
    rows = []
    for reason in reasons:
        details = {
            key: value
            for key, value in reason.items()
            if key not in {"code", "field", "author", "stage"}
        }
        rows.append({
            "paper_id": paper_id,
            "source_file": source_file,
            "code": reason.get("code", "review_required"),
            "field": reason.get("field", ""),
            "author": reason.get("author", ""),
            "stage": reason.get("stage", ""),
            "details": json.dumps(details, ensure_ascii=False, sort_keys=True),
        })
    return rows


def export_paper_artifacts(paper_id, metadata, metadata_dir, evidence_dir, candidate_dir):
    metadata_dir = Path(metadata_dir)
    evidence_dir = Path(evidence_dir)
    candidate_dir = Path(candidate_dir)
    extraction = metadata.get("_extraction", {})
    export_json(metadata_dir / f"{paper_id}.json", metadata)
    export_json(
        evidence_dir / f"{paper_id}.json",
        {"paper_id": paper_id, "evidence": extraction.get("evidence", [])},
    )
    export_json(
        candidate_dir / f"{paper_id}.json",
        {
            "paper_id": paper_id,
            "candidates": extraction.get("candidates", {}),
            "decisions": extraction.get("decisions", []),
        },
    )
