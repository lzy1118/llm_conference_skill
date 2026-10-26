#!/usr/bin/env python3
"""Review unmatched institutions with a configurable LLM without dense models.

Candidates come from the local ROR registry using lexical overlap plus location
context; the LLM then chooses among candidates or explicitly rejects them. Results
are checkpointed after each batch.
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from affilgood.components.entity_linking.registry import RegistryManager
from affilgood.components.entity_linking.rerankers.llm import LLMListwiseReranker
from affilgood.components.entity_linking.retrievers.base import Candidate


STOPWORDS = {"of", "the", "and", "for", "in", "at", "a", "an", "inc", "ltd", "llc", "co", "corp", "company", "university", "institute", "research", "center", "centre", "laboratory", "laboratories"}
GENERIC_NAME_TOKENS = {
    "security", "cybersecurity", "cryptography", "computer", "science",
    "technology", "information", "systems", "lab", "labs", "research",
    "center", "centre", "institute", "university", "department", "school",
    "faculty", "college", "laboratory", "laboratories",
}


def tokens(value):
    return {token for token in re.findall(r"[a-z0-9]+", (value or "").casefold()) if token not in STOPWORDS}


def compact(value):
    return "".join(re.findall(r"[a-z0-9]", (value or "").casefold()))


def initialism(value):
    ignored = {"of", "the", "and", "for", "in", "at", "a", "an"}
    return "".join(word[0] for word in re.findall(r"[A-Za-z0-9]+", value or "") if word.casefold() not in ignored)


def name_gate(query, candidate):
    """Require explicit containment or a demonstrable abbreviation.

    An LLM score alone is never enough to merge institutional IDs.  This keeps
    similarly named laboratories, commercial entities, and parent/child ROR
    entries in the review queue unless the strings provide direct evidence.
    """
    query_key = compact(query)
    if len(query_key) < 2:
        return False
    distinctive_query_tokens = tokens(query) - GENERIC_NAME_TOKENS
    names = [candidate.get("name", "")]
    names.extend((candidate.get("metadata") or {}).get("aliases", []))
    for name in names:
        name_key = compact(name)
        if distinctive_query_tokens and len(query_key) >= 4 and (query_key in name_key or name_key in query_key):
            return True
        if query_key.upper() == compact(initialism(name)).upper():
            return True
    return False


def load_records():
    records = RegistryManager().get_records("ror", active_only=True)
    prepared = []
    for record in records:
        variants = [(name, tokens(name)) for name in record.all_names()]
        variants = [(name, term_set) for name, term_set in variants if term_set]
        if variants:
            prepared.append((record, variants))
    return prepared


def retrieve(query, context, prepared, top_k):
    query_tokens = tokens(query)
    if not query_tokens:
        return []
    country = (context.get("country") or "").casefold().strip()
    city = (context.get("city") or "").casefold().strip()
    scored = []
    for record, variants in prepared:
        best_score, matched = 0.0, ""
        for name, name_tokens in variants:
            overlap = len(query_tokens & name_tokens)
            if not overlap:
                continue
            # Favors candidates covering the entity words while still
            # penalizing long unrelated registry names.
            score = overlap / max(1, len(query_tokens))
            score *= overlap / max(1, len(name_tokens))
            if query_tokens <= name_tokens or name_tokens <= query_tokens:
                score += 0.35
            if score > best_score:
                best_score, matched = score, name
        if not matched:
            continue
        if country and record.country.casefold() == country:
            best_score += 0.25
        if city and record.city.casefold() == city:
            best_score += 0.10
        scored.append((best_score, record, matched))
    scored.sort(key=lambda entry: entry[0], reverse=True)
    return [
        Candidate(
            id=record.id, name=record.name, score=min(score, 1.0), source=record.source,
            matched_text=matched, retriever="lexical_ror",
            metadata={"aliases": record.aliases + record.acronyms, "country": record.country,
                      "country_code": record.country_code, "city": record.city, "types": record.types},
        )
        for score, record, matched in scored[:top_k]
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--model", default="Qwen/Qwen2.5-3B-Instruct")
    parser.add_argument("--device", default="mps")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--min-score", type=float, default=0.70)
    parser.add_argument("--batch-size", type=int, default=1)
    args = parser.parse_args()
    checkpoint = args.checkpoint or args.output_csv.with_suffix(".checkpoint.jsonl")
    with args.input_csv.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields, rows = reader.fieldnames, list(reader)
    done = {}
    if checkpoint.exists():
        with checkpoint.open(encoding="utf-8") as handle:
            for line in handle:
                entry = json.loads(line)
                done[entry["index"]] = entry["judged"]

    prepared = load_records()
    judge = LLMListwiseReranker(model_name=args.model, device=args.device, max_tokens=1600, verbose=True)
    pending = []
    for index, row in enumerate(rows):
        if index in done:
            continue
        query = row.get("affilgood_institutions", "").strip()
        context = {"country": row.get("affilgood_location_country", "").strip(),
                   "city": row.get("affilgood_location_city", "").strip(), "entity_name": query}
        pending.append((index, query, retrieve(query, context, prepared, args.top_k), context))
    print(f"checkpoint={len(done)} pending={len(pending)}")

    with checkpoint.open("a", encoding="utf-8") as handle:
        for start in range(0, len(pending), args.batch_size):
            chunk = pending[start : start + args.batch_size]
            judged_lists = judge.rerank_batch([(query, candidates, context) for _, query, candidates, context in chunk])
            for (index, _, candidates, _), judged in zip(chunk, judged_lists):
                result = {"candidates": [item.to_dict() for item in candidates],
                          "judged": [item.to_dict() for item in judged]}
                done[index] = result
                handle.write(json.dumps({"index": index, "judged": result}, ensure_ascii=False) + "\n")
            handle.flush()
            print(f"judged {min(start + len(chunk), len(pending))}/{len(pending)}")

    output_fields = list(fields)
    for field in ("llm_ror_ids", "llm_score", "llm_status", "llm_candidates"):
        if field not in output_fields:
            output_fields.append(field)
    with args.output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=output_fields)
        writer.writeheader()
        for index, row in enumerate(rows):
            result = done.get(index, {"candidates": [], "judged": []})
            best = result["judged"][0] if result["judged"] else None
            out = dict(row)
            score = best.get("score", 0.0) if best else 0.0
            accepted = bool(best and score >= args.min_score and name_gate(row.get("affilgood_institutions", ""), best))
            out["llm_ror_ids"] = best["id"] if accepted else ""
            out["llm_score"] = f"{score:.4f}" if best else ""
            out["llm_status"] = "accepted" if accepted else "needs_review"
            out["llm_candidates"] = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
            writer.writerow(out)
    print(f"wrote {args.output_csv}")


if __name__ == "__main__":
    main()
