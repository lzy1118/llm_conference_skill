#!/usr/bin/env python3
"""Evaluate author-affiliation relation recovery on a manually verified set.

The annotation contract is JSONL. Each row contains ``paper_id``, ``authors``
and ``affiliations`` plus gold/predicted author-affiliation pairs. Use
``--build-template`` to create an annotation queue from existing
``metadata_json`` files. Replace pending ``null`` annotations with reviewed
lists before evaluation; rows whose ``gold_pairs`` remain pending are ignored.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


LAYOUT_TAGS = ("superscript", "multiple_affiliation", "shared_affiliation", "footnote", "multi-column")
METHODS = ("grobid", "sequential", "skill")
ABLATIONS = ("remove_layout_rules", "remove_evidence_validation", "remove_domain_rules")


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _pair(value: Any) -> tuple[str, str] | None:
    if isinstance(value, dict):
        author, affiliation = value.get("author"), value.get("affiliation")
    elif isinstance(value, (list, tuple)) and len(value) >= 2:
        author, affiliation = value[0], value[1]
    else:
        return None
    author, affiliation = _text(author), _text(affiliation)
    return (author, affiliation) if author and affiliation else None


def pairs(values: Any) -> set[tuple[str, str]]:
    if isinstance(values, str):
        try:
            values = json.loads(values)
        except json.JSONDecodeError:
            values = []
    return {item for value in (values or []) if (item := _pair(value))}


def _authors_and_affiliations(payload: dict) -> tuple[list[str], list[str]]:
    authors_raw = payload.get("authors") or []
    authors = [_text(a.get("name") if isinstance(a, dict) else a) for a in authors_raw]
    affiliations = [_text(a) for a in (payload.get("affiliations") or []) if _text(a)]
    if not affiliations:
        for author in authors_raw:
            if isinstance(author, dict):
                affiliations.extend(_text(a) for a in author.get("affiliations", []) if _text(a))
    return list(dict.fromkeys(a for a in authors if a)), list(dict.fromkeys(affiliations))


def _relations_from_authors(payload: dict) -> list[dict[str, str]]:
    rows = []
    for author in payload.get("authors") or []:
        if not isinstance(author, dict):
            continue
        for affiliation in author.get("affiliations") or []:
            rows.append({"author": _text(author.get("name")), "affiliation": _text(affiliation)})
    return rows


def _relations_from_grobid_evidence(payload: dict) -> list[dict[str, str]] | None:
    """Recover TEI edges, or return None when author evidence is unavailable."""
    extraction = payload.get("_extraction")
    if not isinstance(extraction, dict):
        extraction = {}
    evidence_rows = extraction.get("evidence")
    if evidence_rows is None:
        evidence_rows = payload.get("evidence")
    if evidence_rows is None:
        return None
    author_evidence = [
        evidence for evidence in evidence_rows
        if isinstance(evidence, dict)
        and evidence.get("source") == "grobid_tei"
        and evidence.get("field") == "author"
    ]
    if not author_evidence:
        return None
    rows = []
    for evidence in author_evidence:
        author = _text(evidence.get("raw_text"))
        for affiliation in evidence.get("affiliations") or []:
            if author and _text(affiliation):
                rows.append({"author": author, "affiliation": _text(affiliation)})
    return rows


def _load_grobid_evidence(path: Path, payload: dict) -> dict:
    """Use the sibling evidence artifact if metadata JSON omitted its trace."""
    extraction = payload.get("_extraction")
    if isinstance(extraction, dict) and "evidence" in extraction:
        return payload
    evidence_path = path.parent.parent / "evidence_json" / path.name
    try:
        evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return payload
    return evidence_payload if isinstance(evidence_payload, dict) else payload


def _sequential_pairs(authors: list[str], affiliations: list[str]) -> list[dict[str, str]]:
    """Simple order-only baseline: one-to-one, then proportional block assignment."""
    if not authors or not affiliations:
        return []
    if len(authors) == len(affiliations):
        return [{"author": author, "affiliation": affiliation} for author, affiliation in zip(authors, affiliations)]
    result = []
    for index, author in enumerate(authors):
        start = round(index * len(affiliations) / len(authors))
        end = round((index + 1) * len(affiliations) / len(authors))
        end = max(end, start + 1)
        for affiliation in affiliations[start:min(end, len(affiliations))]:
            result.append({"author": author, "affiliation": affiliation})
    return result


def build_template(
    metadata_dir: Path | list[Path], output: Path, limit: int = 500, seed: int = 13,
    stratify_conference: bool = False,
) -> int:
    roots = metadata_dir if isinstance(metadata_dir, list) else [metadata_dir]
    candidates = []
    for root in roots:
        conference = root.parents[2].name if len(root.parents) > 2 else root.name
        year = root.parents[1].name if len(root.parents) > 1 else ""
        candidates.extend(
            (path, conference, year)
            for path in root.rglob("*.json")
            if "backups" not in path.parts
        )
    rng = random.Random(seed)
    if stratify_conference:
        grouped = defaultdict(list)
        for candidate in candidates:
            grouped[candidate[1]].append(candidate)
        for values in grouped.values():
            rng.shuffle(values)
        files = []
        while any(grouped.values()) and len(files) < limit:
            for conference in sorted(grouped):
                if grouped[conference] and len(files) < limit:
                    files.append(grouped[conference].pop())
    else:
        rng.shuffle(candidates)
        files = candidates[:limit]
    rows = []
    seen_ids = set()
    for path, conference, year in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        authors, affiliations = _authors_and_affiliations(payload)
        if not authors:
            continue
        skill = payload.get("author_affiliation_relations")
        if skill is None:
            skill = _relations_from_authors(payload)
        if "grobid_pairs" in payload:
            grobid = payload["grobid_pairs"]
        else:
            grobid = _relations_from_grobid_evidence(_load_grobid_evidence(path, payload))
        paper_id = _text(payload.get("paper_id") or path.stem)
        if paper_id in seen_ids:
            continue
        seen_ids.add(paper_id)
        rows.append({
            "paper_id": paper_id,
            "conference": conference,
            "year": year,
            "authors": authors,
            "affiliations": affiliations,
            "grobid_pairs": grobid,
            "grobid_evidence_available": grobid is not None,
            "sequential_pairs": _sequential_pairs(authors, affiliations),
            "skill_pairs": skill,
            "gold_pairs": None,
            "layout_tags": None,
            "ablation_pairs": {name: None for name in ABLATIONS},
            "source_file": str(path),
        })
        if len(rows) >= limit:
            break
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def prf(predicted: set, gold: set) -> dict[str, float | int]:
    tp = len(predicted & gold)
    fp, fn = len(predicted - gold), len(gold - predicted)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0}


def evaluate(rows: list[dict], output_dir: Path) -> int:
    annotated_rows = [row for row in rows if row.get("gold_pairs") is not None]
    if not annotated_rows:
        raise ValueError("No annotated gold_pairs found; replace pending null values with reviewed lists.")
    output_dir.mkdir(parents=True, exist_ok=True)
    detail, summary = [], []
    for row in annotated_rows:
        gold = pairs(row.get("gold_pairs"))
        for method in METHODS:
            prediction = row.get(f"{method}_pairs")
            if prediction is None:
                continue
            metric = prf(pairs(prediction), gold)
            detail.append({"paper_id": _text(row.get("paper_id")), "scope": "overall", "category": "all",
                           "method": method, **metric, "gold_pairs": len(gold)})
        for ablation in ABLATIONS:
            prediction = (row.get("ablation_pairs") or {}).get(ablation)
            if prediction is None:
                continue
            metric = prf(pairs(prediction), gold)
            detail.append({"paper_id": _text(row.get("paper_id")), "scope": "ablation", "category": ablation,
                           "method": "skill", **metric, "gold_pairs": len(gold)})
        for tag in row.get("layout_tags") or []:
            if tag not in LAYOUT_TAGS:
                continue
            for method in METHODS:
                prediction = row.get(f"{method}_pairs")
                if prediction is None:
                    continue
                metric = prf(pairs(prediction), gold)
                detail.append({"paper_id": _text(row.get("paper_id")), "scope": "layout", "category": tag,
                               "method": method, **metric, "gold_pairs": len(gold)})

    def aggregate(items: list[dict], scope: str, category: str, method: str) -> dict:
        tp = sum(r["tp"] for r in items); fp = sum(r["fp"] for r in items); fn = sum(r["fn"] for r in items)
        p = tp / (tp + fp) if tp + fp else 0.0; rec = tp / (tp + fn) if tp + fn else 0.0
        return {"scope": scope, "category": category, "method": method, "papers": len({r["paper_id"] for r in items}),
                "tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": rec,
                "f1": 2 * p * rec / (p + rec) if p + rec else 0.0}

    for scope, category, method in [("overall", "all", m) for m in METHODS] + [("ablation", a, "skill") for a in ABLATIONS] + [("layout", t, m) for t in LAYOUT_TAGS for m in METHODS]:
        items = [r for r in detail if r["scope"] == scope and r["category"] == category and r["method"] == method]
        if items:
            summary.append(aggregate(items, scope, category, method))
    skill_f1 = next((r["f1"] for r in summary if r["scope"] == "overall" and r["method"] == "skill"), None)
    for row in summary:
        row["delta_f1"] = (
            row["f1"] - skill_f1
            if row["scope"] == "ablation" and skill_f1 is not None
            else ""
        )
    fields = ["paper_id", "scope", "category", "method", "tp", "fp", "fn", "precision", "recall", "f1", "gold_pairs"]
    with (output_dir / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(detail)
    sfields = ["scope", "category", "method", "papers", "tp", "fp", "fn", "precision", "recall", "f1", "delta_f1"]
    with (output_dir / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=sfields); writer.writeheader(); writer.writerows(summary)
    with (output_dir / "results.tex").open("w", encoding="utf-8") as handle:
        handle.write("\\begin{tabular}{llrrrrrr}\n\\toprule\nScope & Method & P & R & F1 & $\\Delta$F1 & TP & FN\\\\\n\\midrule\n")
        for r in summary:
            if r["scope"] in {"overall", "ablation"}:
                delta = f"{r['delta_f1']:.3f}" if isinstance(r["delta_f1"], float) else ""
                handle.write(f"{r['category']} & {r['method']} & {r['precision']:.3f} & {r['recall']:.3f} & {r['f1']:.3f} & {delta} & {r['tp']} & {r['fn']}\\\\\n")
        handle.write("\\bottomrule\n\\end{tabular}\n")
    _write_figure(summary, output_dir / "f1_comparison.png")
    return len(annotated_rows)


def _write_figure(summary: list[dict], path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return
    rows = [r for r in summary if r["scope"] == "overall"]
    method_colors = {"grobid": "#718096", "sequential": "#d69e2e", "skill": "#2b6cb0"}
    fig, ax = plt.subplots(figsize=(6, 4)); ax.bar(
        [r["method"] for r in rows], [r["f1"] for r in rows],
        color=[method_colors.get(r["method"], "#718096") for r in rows],
    )
    ax.set_ylim(0, 1); ax.set_ylabel("F1"); ax.set_title("Author-affiliation relation recovery"); fig.tight_layout(); fig.savefig(path, dpi=180); plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-dir", type=Path, nargs="+", help="one or more directories containing GROBID metadata_json files")
    parser.add_argument("--build-template", type=Path, help="write JSONL annotation queue")
    parser.add_argument("--input", type=Path, help="annotated JSONL input")
    parser.add_argument("--output-dir", type=Path, default=Path("experiment-results"))
    parser.add_argument("--limit", type=int, default=500); parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--stratify-conference", action="store_true", help="round-robin sample across conference roots")
    args = parser.parse_args()
    if args.build_template:
        if not args.metadata_dir: parser.error("--metadata-dir is required with --build-template")
        print(f"wrote {build_template(args.metadata_dir, args.build_template, args.limit, args.seed, args.stratify_conference)} annotation records")
        return
    if not args.input: parser.error("--input is required unless --build-template is used")
    rows = load_jsonl(args.input)
    evaluated = evaluate(rows, args.output_dir)
    print(f"evaluated {evaluated} annotated papers; skipped {len(rows) - evaluated} pending papers")


if __name__ == "__main__":
    main()
