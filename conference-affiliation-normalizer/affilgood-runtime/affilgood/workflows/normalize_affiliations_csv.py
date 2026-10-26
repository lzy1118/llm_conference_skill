import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from affilgood import AffilGood


def _join_values(items, key):
    values = []
    for item in items or []:
        value = item.get(key)
        if isinstance(value, dict):
            value = value.get("ror_id") or value.get("ror_name")
        if value:
            values.append(str(value))
    return " | ".join(values)


def _extract_first_location(output):
    location = output.get("location") or {}
    return {
        "affilgood_location_country": location.get("country"),
        "affilgood_location_city": location.get("city"),
        "affilgood_location_lat": location.get("lat"),
        "affilgood_location_lon": location.get("lon"),
    }


def _chunked(seq, size):
    for i in range(0, len(seq), size):
        yield i, seq[i : i + size]


def _build_enriched_row(row, result):
    output = (result.get("outputs") or [{}])[0]
    institutions = output.get("institutions") or []
    subunits = output.get("subunits") or []

    enriched = dict(row)
    enriched.update(
        {
            "affilgood_raw_text": result.get("raw_text"),
            "affilgood_institutions": _join_values(institutions, "name"),
            "affilgood_ror_ids": _join_values(institutions, "id"),
            "affilgood_subunits": _join_values(subunits, "name"),
            "affilgood_language": output.get("language"),
            "affilgood_confidence": output.get("confidence"),
            "affilgood_output_json": json.dumps(
                output, ensure_ascii=False, separators=(",", ":")
            ),
        }
    )
    enriched.update(_extract_first_location(output))
    return enriched


def process_csv(
    input_csv: Path,
    output_csv: Path,
    batch_size: int = 32,
    use_reranker: bool = True,
    enable_entity_linking: bool = True,
    enable_normalization: bool = True,
    write_chunk_size: int = 100,
):
    with input_csv.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    ag = AffilGood(
        enable_entity_linking=enable_entity_linking,
        enable_normalization=enable_normalization,
        linking_config={
            "reranker": "cross_encoder" if use_reranker else None,
        }
    )

    fieldnames = list(rows[0].keys()) + [
        "affilgood_raw_text",
        "affilgood_institutions",
        "affilgood_ror_ids",
        "affilgood_subunits",
        "affilgood_language",
        "affilgood_confidence",
        "affilgood_location_country",
        "affilgood_location_city",
        "affilgood_location_lat",
        "affilgood_location_lon",
        "affilgood_output_json",
    ]

    with output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        total = len(rows)
        for start, chunk_rows in _chunked(rows, write_chunk_size):
            chunk_affiliations = [row.get("affiliations", "") for row in chunk_rows]
            chunk_results = ag.process(chunk_affiliations, batch_size=batch_size)
            writer.writerows(
                _build_enriched_row(row, result)
                for row, result in zip(chunk_rows, chunk_results)
            )
            f.flush()
            print(f"processed {min(start + len(chunk_rows), total)}/{total}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--use-reranker", action="store_true")
    parser.add_argument("--enable-linking", action="store_true")
    parser.add_argument("--enable-normalization", action="store_true")
    parser.add_argument("--write-chunk-size", type=int, default=100)
    args = parser.parse_args()

    process_csv(
        args.input_csv,
        args.output_csv,
        batch_size=args.batch_size,
        use_reranker=args.use_reranker,
        enable_entity_linking=args.enable_linking,
        enable_normalization=args.enable_normalization,
        write_chunk_size=args.write_chunk_size,
    )


if __name__ == "__main__":
    main()
