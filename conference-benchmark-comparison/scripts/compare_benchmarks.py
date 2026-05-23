from __future__ import annotations

import argparse
import csv
from pathlib import Path


ENTITY_FIELDS = ("country", "institution_name", "author_name")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def detect_entity_field(rows: list[dict[str, str]]) -> str:
    if not rows:
        raise ValueError("Summary file has no rows")
    for field in ENTITY_FIELDS:
        if field in rows[0]:
            return field
    raise ValueError("Unsupported summary file: missing entity field")


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare leaderboard-style conference summary outputs.")
    parser.add_argument("--label", action="append", default=[], help="Comparison label. Repeat once per summary.")
    parser.add_argument("--summary", action="append", default=[], help="Summary CSV path. Repeat once per label.")
    parser.add_argument("--output-dir", required=True, help="Output directory for comparison files")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if len(args.label) != len(args.summary) or not args.label:
        raise SystemExit("Provide matching --label and --summary pairs")

    labels = args.label
    summaries = [Path(path).resolve() for path in args.summary]
    summary_rows = [read_csv_rows(path) for path in summaries]
    entity_fields = [detect_entity_field(rows) for rows in summary_rows]
    if len(set(entity_fields)) != 1:
        raise SystemExit("All summaries must use the same entity field")

    entity_field = entity_fields[0]
    comparison: dict[str, dict[str, object]] = {}
    for label, rows in zip(labels, summary_rows):
        if rows and "papers" not in rows[0]:
            raise SystemExit("All summaries must include a papers column")
        for row in rows:
            entity = row.get(entity_field, "")
            if not entity:
                continue
            entry = comparison.setdefault(entity, {"entity": entity})
            entry[label] = int(row.get("papers", "0") or "0")

    output_rows: list[dict[str, object]] = []
    for entity, entry in comparison.items():
        values = {label: int(entry.get(label, 0)) for label in labels}
        best_label = max(values, key=lambda label: (values[label], label))
        max_value = max(values.values()) if values else 0
        min_value = min(values.values()) if values else 0
        output_rows.append(
            {
                **entry,
                **values,
                "best_label": best_label,
                "max_value": max_value,
                "min_value": min_value,
                "spread": max_value - min_value,
            }
        )

    output_rows.sort(key=lambda row: (-int(row["max_value"]), str(row["entity"])))
    output_dir = Path(args.output_dir).resolve()
    write_rows(output_dir / "benchmark_comparison.csv", output_rows)

    lines = [
        "# Conference Benchmark Comparison Report",
        "",
        f"- labels: {', '.join(labels)}",
        f"- entity_field: {entity_field}",
        "",
        "## Highlights",
        "",
    ]
    for row in output_rows[:10]:
        lines.append(f"- {row['entity']}: best_label={row['best_label']} max_value={row['max_value']} spread={row['spread']}")
    (output_dir / "benchmark_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
