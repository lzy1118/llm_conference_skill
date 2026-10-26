"""Fill missing ROR IDs in an institution CSV using the LLM entity-linking judge."""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from affilgood.components.entity_linking import EntityLinker


def _split_institutions(value):
    return [part.strip() for part in (value or "").split(" | ") if part.strip()]


def _match_to_dict(match):
    if match is None:
        return None
    return match.to_dict()


def process_csv(input_csv, output_csv, model_name, top_k=10, threshold=0.3):
    with input_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    linker = EntityLinker(
        reranker="cross_encoder",
        llm_judge=model_name,
        llm_threshold=0.7,
        threshold=threshold,
        top_k=top_k,
        verbose=True,
    )

    fieldnames = list(rows[0])
    for field in ("llm_ror_ids", "llm_match_details", "llm_processed"):
        if field not in fieldnames:
            fieldnames.append(field)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        for index, row in enumerate(rows, start=1):
            output = dict(row)
            if row.get("affilgood_ror_ids", "").strip():
                output["llm_processed"] = "skipped_existing"
                output.setdefault("llm_ror_ids", "")
                output.setdefault("llm_match_details", "")
            else:
                context = {
                    "country": row.get("affilgood_location_country", ""),
                    "city": row.get("affilgood_location_city", ""),
                }
                details = []
                for institution in _split_institutions(row.get("affilgood_institutions")):
                    match = linker.link_one(
                        institution,
                        context=context,
                        raw_affiliation=institution,
                    )
                    details.append({
                        "query": institution,
                        "match": _match_to_dict(match),
                    })

                output["llm_ror_ids"] = " | ".join(
                    item["match"]["id"]
                    for item in details
                    if item["match"] is not None
                )
                output["llm_match_details"] = json.dumps(
                    details, ensure_ascii=False, separators=(",", ":")
                )
                output["llm_processed"] = "yes"

            writer.writerow(output)
            handle.flush()
            print(f"processed {index}/{len(rows)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument(
        "--model", default="Qwen/Qwen2.5-3B-Instruct",
        help="Hugging Face causal language model used by the LLM judge",
    )
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--threshold", type=float, default=0.3)
    args = parser.parse_args()
    process_csv(
        args.input_csv,
        args.output_csv,
        model_name=args.model,
        top_k=args.top_k,
        threshold=args.threshold,
    )


if __name__ == "__main__":
    main()
