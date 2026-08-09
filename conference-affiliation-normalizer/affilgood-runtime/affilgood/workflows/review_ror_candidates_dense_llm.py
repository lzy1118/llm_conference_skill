"""Use a configurable LLM to judge dense-retrieval ROR candidates."""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from affilgood.components.entity_linking import EntityLinker


def run(input_csv, output_csv, model_name, min_score=0.70, top_k=10, device="cpu", batch_size=2):
    with input_csv.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    linker = EntityLinker(
        retriever="dense",
        reranker=None,
        llm_judge=model_name,
        llm_threshold=1.0,
        top_k=top_k,
        threshold=0.0,
        verbose=True,
        device=device,
    )
    linker._ensure_llm_judge()

    fields = list(rows[0])
    for field in ("llm_ror_ids", "llm_score", "llm_status", "llm_candidates"):
        if field not in fields:
            fields.append(field)

    pending = []
    for index, row in enumerate(rows):
        if row.get("affilgood_ror_ids", "").strip():
            continue
        query = row.get("affilgood_institutions", "").strip()
        context = {
            "country": row.get("affilgood_location_country", "").strip(),
            "city": row.get("affilgood_location_city", "").strip(),
            "entity_name": query,
        }
        candidates = linker._retriever.retrieve(query, top_k=top_k, context=context)
        pending.append((index, query, linker._enrich_candidates(candidates), context))

    judged_by_index = {}
    for start in range(0, len(pending), batch_size):
        chunk = pending[start:start + batch_size]
        judged = linker._llm_judge.rerank_batch([
            (query, candidates, context)
            for _, query, candidates, context in chunk
        ])
        for (index, _, _, _), result in zip(chunk, judged):
            judged_by_index[index] = result
        print(f"judged {min(start + len(chunk), len(pending))}/{len(pending)}")

    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, row in enumerate(rows, 1):
            out = dict(row)
            if row.get("affilgood_ror_ids", "").strip():
                for field in ("llm_ror_ids", "llm_score", "llm_status", "llm_candidates"):
                    out.setdefault(field, "")
            else:
                judged = judged_by_index.get(index - 1, [])
                best = judged[0] if judged else None
                out["llm_ror_ids"] = best.id if best and best.score >= min_score else ""
                out["llm_score"] = f"{best.score:.4f}" if best else ""
                out["llm_status"] = "accepted" if best and best.score >= min_score else "needs_review"
                out["llm_candidates"] = json.dumps(
                    [candidate.to_dict() for candidate in judged],
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            writer.writerow(out)
            handle.flush()
            print(f"processed {index}/{len(rows)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--model", default="Qwen/Qwen2.5-3B-Instruct")
    parser.add_argument("--min-score", type=float, default=0.70)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch-size", type=int, default=2)
    args = parser.parse_args()
    run(
        args.input_csv,
        args.output_csv,
        args.model,
        args.min_score,
        args.top_k,
        args.device,
        args.batch_size,
    )


if __name__ == "__main__":
    main()
