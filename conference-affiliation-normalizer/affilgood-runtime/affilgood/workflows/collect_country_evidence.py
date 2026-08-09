#!/usr/bin/env python3
"""Collect resumable web-search evidence for institutions missing country."""

import csv
import json
import time
from collections import defaultdict
from pathlib import Path

from ddgs import DDGS


def load_done(path):
    done = {}
    if path.exists():
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                    done[item["conference_id"]] = item
                except (json.JSONDecodeError, KeyError):
                    continue
    return done


def main():
    data_dir = Path(__file__).resolve().parents[2] / "data"
    checkpoint = data_dir / "institution_country_search_evidence.jsonl"
    with (data_dir / "institution_raw.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    groups = defaultdict(list)
    for row in rows:
        if not row["affilgood_location_country"].strip():
            groups[row["conference_id"]].append(row)
    done = load_done(checkpoint)
    pending = [(conference_id, group) for conference_id, group in groups.items() if conference_id not in done]
    print(f"groups={len(groups)}; checkpoint={len(done)}; pending={len(pending)}")

    with checkpoint.open("a", encoding="utf-8") as handle:
        for index, (conference_id, group) in enumerate(pending, 1):
            names = list(dict.fromkeys(row["affilgood_institutions"].strip() for row in group))
            query_name = max(names, key=len)
            query = f'"{query_name}" organization headquarters country'
            results = []
            error = ""
            try:
                for result in DDGS().text(query, max_results=4):
                    results.append({
                        "title": result.get("title", ""),
                        "url": result.get("href", ""),
                        "snippet": result.get("body", ""),
                    })
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
            item = {
                "conference_id": conference_id,
                "conference_final_id": group[0]["conference_final_id"],
                "names": names,
                "query": query,
                "results": results,
                "error": error,
            }
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
            handle.flush()
            print(f"searched {index}/{len(pending)} {conference_id} {query_name} results={len(results)}")
            time.sleep(0.5)


if __name__ == "__main__":
    main()
