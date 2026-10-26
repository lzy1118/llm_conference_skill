import argparse
import csv
import difflib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


def _tokens(text):
    folded = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.findall(r"[a-z0-9]+", folded)


def _key(text):
    return "".join(_tokens(text))


def _title_score(left, right):
    left_key, right_key = _key(left), _key(right)
    if left_key == right_key:
        return 1.0
    if min(len(left_key), len(right_key)) >= 10 and (
        left_key.startswith(right_key) or right_key.startswith(left_key)
    ):
        return 0.99
    return difflib.SequenceMatcher(None, left_key, right_key).ratio()


def _author_score(left, right):
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    if "".join(left_tokens) == "".join(right_tokens):
        return 1.0
    if (
        len(left_tokens) >= 2
        and len(right_tokens) >= 2
        and left_tokens[0] == right_tokens[0]
        and left_tokens[-1] == right_tokens[-1]
    ):
        return 0.9
    if min(len(left_tokens), len(right_tokens)) >= 2 and (
        set(left_tokens) <= set(right_tokens) or set(right_tokens) <= set(left_tokens)
    ):
        return 0.86
    return difflib.SequenceMatcher(
        None,
        "".join(left_tokens),
        "".join(right_tokens),
    ).ratio()


def _affiliation_status(extracted, official):
    if official and not extracted:
        return "missing"
    if extracted and not official:
        return "local_only"
    if not extracted and not official:
        return "both_empty"
    left_key, right_key = _key(extracted), _key(official)
    left_tokens, right_tokens = set(_tokens(extracted)), set(_tokens(official))
    similarity = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    stop = {"of", "the", "and", "for", "at", "in"}
    official_acronym = "".join(token[0] for token in _tokens(official) if token not in stop)
    extracted_acronym = "".join(token[0] for token in _tokens(extracted) if token not in stop)
    if (
        left_key == right_key
        or (len(left_key) >= 4 and left_key in right_key)
        or (len(right_key) >= 4 and right_key in left_key)
        or similarity >= 0.45
        or left_key == official_acronym
        or right_key == extracted_acronym
    ):
        return "similar"
    return "needs_review"


def _group(rows):
    result = defaultdict(list)
    for row in rows:
        result[row.get("title", "")].append(row)
    return result


def _attach_paper_ids(rows, dataset_dir):
    title_to_id = {}
    metadata_dir = dataset_dir / "metadata_json"
    if metadata_dir.is_dir():
        for path in metadata_dir.glob("*.json"):
            try:
                metadata = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            title = metadata.get("title", "")
            if title:
                title_to_id[_key(title)] = path.stem
    for row in rows:
        if not row.get("paper_id"):
            row["paper_id"] = title_to_id.get(_key(row.get("title", "")), "")


def _match_titles(extracted, official):
    matches = {}
    used = set()
    for title in extracted:
        exact = [candidate for candidate in official if _key(candidate) == _key(title)]
        if len(exact) == 1:
            matches[title] = exact[0]
            used.add(exact[0])
    for title in extracted:
        if title in matches:
            continue
        ranked = sorted(
            ((_title_score(title, candidate), candidate) for candidate in official if candidate not in used),
            reverse=True,
        )
        if ranked and ranked[0][0] >= 0.82 and (
            len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= 0.04
        ):
            matches[title] = ranked[0][1]
            used.add(ranked[0][1])
    return matches, used


def evaluate(extracted_rows, official_rows, dataset_dir):
    _attach_paper_ids(extracted_rows, dataset_dir)
    extracted, official = _group(extracted_rows), _group(official_rows)
    title_matches, used_official_titles = _match_titles(extracted, official)
    issues = []
    counts = Counter()
    author_true_positive = 0
    author_extra = 0
    author_missing = 0
    official_affiliations = 0
    extracted_nonempty_affiliations = 0

    for extracted_title, official_title in title_matches.items():
        local_rows, official_paper_rows = extracted[extracted_title], official[official_title]
        candidates = sorted(
            (
                _author_score(local["author"], reference["author"]),
                local_index,
                official_index,
            )
            for local_index, local in enumerate(local_rows)
            for official_index, reference in enumerate(official_paper_rows)
        )
        local_used, official_used, author_pairs = set(), set(), []
        for score, local_index, official_index in reversed(candidates):
            if score < 0.72 or local_index in local_used or official_index in official_used:
                continue
            local_used.add(local_index)
            official_used.add(official_index)
            author_pairs.append((local_index, official_index, score))

        author_true_positive += len(author_pairs)
        author_extra += len(local_rows) - len(author_pairs)
        author_missing += len(official_paper_rows) - len(author_pairs)
        paper_id = local_rows[0].get("paper_id", "")
        evidence_path = str(dataset_dir / "evidence_json" / f"{paper_id}.json") if paper_id else ""
        candidate_path = str(dataset_dir / "candidate_json" / f"{paper_id}.json") if paper_id else ""

        for local_index, official_index, score in author_pairs:
            local, reference = local_rows[local_index], official_paper_rows[official_index]
            status = _affiliation_status(local.get("affiliations", ""), reference.get("affiliations", ""))
            counts[f"affiliation_{status}"] += 1
            if reference.get("affiliations", "").strip():
                official_affiliations += 1
                extracted_nonempty_affiliations += bool(local.get("affiliations", "").strip())
            if status in {"missing", "needs_review"}:
                issues.append({
                    "issue": f"affiliation_{status}",
                    "paper_id": paper_id,
                    "extracted_title": extracted_title,
                    "official_title": official_title,
                    "extracted_author": local["author"],
                    "official_author": reference["author"],
                    "author_match_score": round(score, 4),
                    "extracted_affiliation": local.get("affiliations", ""),
                    "official_affiliation": reference.get("affiliations", ""),
                    "evidence_json": evidence_path,
                    "candidate_json": candidate_path,
                })
        for index, row in enumerate(local_rows):
            if index not in local_used:
                issues.append({"issue": "extra_author", "paper_id": paper_id, "extracted_title": extracted_title, "official_title": official_title, "extracted_author": row["author"], "official_author": "", "author_match_score": "", "extracted_affiliation": row.get("affiliations", ""), "official_affiliation": "", "evidence_json": evidence_path, "candidate_json": candidate_path})
        for index, row in enumerate(official_paper_rows):
            if index not in official_used:
                issues.append({"issue": "missing_author", "paper_id": paper_id, "extracted_title": extracted_title, "official_title": official_title, "extracted_author": "", "official_author": row["author"], "author_match_score": "", "extracted_affiliation": "", "official_affiliation": row.get("affiliations", ""), "evidence_json": evidence_path, "candidate_json": candidate_path})

    for title, rows in extracted.items():
        if title not in title_matches:
            issues.append({"issue": "local_only_paper", "paper_id": rows[0].get("paper_id", ""), "extracted_title": title, "official_title": "", "extracted_author": "", "official_author": "", "author_match_score": "", "extracted_affiliation": "", "official_affiliation": "", "evidence_json": "", "candidate_json": ""})
    for title in official:
        if title not in used_official_titles:
            issues.append({"issue": "missing_official_paper", "paper_id": "", "extracted_title": "", "official_title": title, "extracted_author": "", "official_author": "", "author_match_score": "", "extracted_affiliation": "", "official_affiliation": "", "evidence_json": "", "candidate_json": ""})

    return {
        "papers_extracted": len(extracted),
        "papers_official": len(official),
        "papers_matched": len(title_matches),
        "local_only_papers": len(extracted) - len(title_matches),
        "missing_official_papers": len(official) - len(used_official_titles),
        "author_true_positive": author_true_positive,
        "author_extra": author_extra,
        "author_missing": author_missing,
        "author_precision": author_true_positive / (author_true_positive + author_extra),
        "author_recall": author_true_positive / (author_true_positive + author_missing),
        "official_affiliation_nonempty_recall": extracted_nonempty_affiliations / official_affiliations,
        "affiliation_status_counts": dict(sorted(counts.items())),
    }, issues


def main():
    parser = argparse.ArgumentParser(description="Compare extracted metadata with official author rows.")
    parser.add_argument("--extracted", required=True)
    parser.add_argument("--official", required=True)
    parser.add_argument("--conference", default="CCS")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    with open(args.extracted, encoding="utf-8-sig") as handle:
        extracted_rows = list(csv.DictReader(handle))
    with open(args.official, encoding="utf-8-sig") as handle:
        official_rows = [row for row in csv.DictReader(handle) if row.get("conference") == args.conference]
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary, issues = evaluate(extracted_rows, official_rows, Path(args.extracted).parent)
    (output_dir / "official_comparison_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    fieldnames = ["issue", "paper_id", "extracted_title", "official_title", "extracted_author", "official_author", "author_match_score", "extracted_affiliation", "official_affiliation", "evidence_json", "candidate_json"]
    with (output_dir / "official_comparison_issues.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(issues)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
