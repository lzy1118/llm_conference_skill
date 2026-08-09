#!/usr/bin/env python3
"""Read-only ablation evaluation for the entity-linking cascade.

Input CSV/JSONL records must contain an affiliation field.  For accuracy
metrics, also provide a gold ROR field.  The script never writes institution
or conference data; it writes only the requested experiment report.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from affilgood.components.entity_linking.linker import EntityLinker


def load_records(path: Path, affiliation_field: str, gold_field: str | None):
    if path.suffix.lower() == ".jsonl":
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            records = list(csv.DictReader(handle))
    result = []
    for index, row in enumerate(records):
        affiliation = (row.get(affiliation_field) or "").strip()
        if not affiliation:
            continue
        result.append({
            "record_id": row.get("record_id") or row.get("paper_id") or str(index),
            "affiliation": affiliation,
            "gold_ror_id": (row.get(gold_field) or "").strip() if gold_field else "",
        })
    return result


def run_config(records, config_name, *, data_dir, device, llm_model, limit):
    kwargs = {
        "data_dir": data_dir,
        "device": device,
        "top_k": 10,
        "threshold": 0.3,
    }
    if config_name == "retrieval_only":
        kwargs.update({"reranker": None, "llm_judge": None})
    elif config_name == "cross_encoder":
        kwargs.update({"reranker": "cross_encoder", "llm_judge": None})
    elif config_name == "llm_judge":
        kwargs.update({
            "reranker": "cross_encoder",
            "llm_judge": llm_model,
            "llm_threshold": 0.5,
        })
    else:
        raise ValueError(config_name)

    linker = EntityLinker(**kwargs)
    rows = []
    for item in records[:limit or None]:
        candidate = linker.link_one(item["affiliation"], raw_affiliation=item["affiliation"])
        predicted = candidate.id if candidate else ""
        score = float(candidate.score) if candidate else 0.0
        gold = item["gold_ror_id"]
        rows.append({
            "record_id": item["record_id"],
            "affiliation": item["affiliation"],
            "gold_ror_id": gold,
            "predicted_ror_id": predicted,
            "score": round(score, 6),
            "accepted": bool(candidate),
            "correct": bool(gold and predicted == gold),
            "source": candidate.source if candidate else "abstain",
            "retriever": candidate.retriever if candidate else "",
        })
    linker.free()
    return rows


def summarize(rows):
    total = len(rows)
    labeled = [r for r in rows if r["gold_ror_id"]]
    accepted = [r for r in rows if r["accepted"]]
    correct = [r for r in labeled if r["correct"]]
    accepted_labeled = [r for r in labeled if r["accepted"]]
    return {
        "records": total,
        "labeled_records": len(labeled),
        "accepted": len(accepted),
        "abstained": total - len(accepted),
        "coverage": len(accepted) / total if total else None,
        "labeled_accuracy": len(correct) / len(labeled) if labeled else None,
        "selective_accuracy": (
            sum(r["correct"] for r in accepted_labeled) / len(accepted_labeled)
            if accepted_labeled else None
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--affiliation-field", default="affiliation")
    parser.add_argument("--gold-field", default=None, help="field containing gold ROR ID")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--llm-model", default="Qwen/Qwen2.5-3B-Instruct")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--configs", nargs="+",
        choices=("retrieval_only", "cross_encoder", "llm_judge"),
        default=["retrieval_only", "cross_encoder", "llm_judge"],
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    records = load_records(args.input, args.affiliation_field, args.gold_field)
    report = {"input": str(args.input), "configs": {}}
    for config in args.configs:
        rows = run_config(
            records, config, data_dir=args.data_dir, device=args.device,
            llm_model=args.llm_model, limit=args.limit,
        )
        report["configs"][config] = {"summary": summarize(rows), "rows": rows}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v["summary"] for k, v in report["configs"].items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
