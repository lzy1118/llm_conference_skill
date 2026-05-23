from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


MODE_CHOICES = ("author", "country", "institution")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def filter_rows(rows: list[dict[str, str]], conference: str | None, year: str | None) -> list[dict[str, str]]:
    filtered = rows
    if conference:
        filtered = [row for row in filtered if row.get("conference") == conference]
    if year:
        filtered = [row for row in filtered if row.get("year") == str(year)]
    return filtered


def node_for_mode(row: dict[str, str], mode: str) -> tuple[str, str]:
    if mode == "author":
        key = row.get("author_key") or row.get("name") or "Unknown"
        return key, row.get("name") or key
    if mode == "country":
        key = row.get("country") or "Unknown"
        return key, key
    key = row.get("institution_key") or row.get("inst") or "Unknown"
    return key, row.get("inst") or key


def aggregate_edges(rows: list[dict[str, str]], mode: str) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    paper_nodes: dict[str, dict[str, tuple[str, str]]] = defaultdict(dict)
    edge_stats: dict[tuple[str, str], dict[str, object]] = {}

    for row in rows:
        paper_key = row.get("paper_key", "")
        if not paper_key:
            continue
        node_key, node_name = node_for_mode(row, mode)
        paper_nodes[paper_key][node_key] = (node_key, node_name)

    for paper_key, nodes_map in paper_nodes.items():
        nodes = [nodes_map[key] for key in sorted(nodes_map)]
        if len(nodes) < 2:
            continue
        conferences = {row.get("conference", "") for row in rows if row.get("paper_key") == paper_key}
        years = {row.get("year", "") for row in rows if row.get("paper_key") == paper_key and row.get("year")}
        conference = sorted(conferences)[0] if conferences else ""
        year = sorted(years)[0] if years else ""
        for index, (left_key, left_name) in enumerate(nodes):
            for right_key, right_name in nodes[index + 1 :]:
                edge_key = (left_key, right_key)
                edge = edge_stats.setdefault(
                    edge_key,
                    {
                        "mode": mode,
                        "left_key": left_key,
                        "left_name": left_name,
                        "right_key": right_key,
                        "right_name": right_name,
                        "shared_papers": 0,
                        "conferences": set(),
                        "years": set(),
                    },
                )
                edge["shared_papers"] += 1
                if conference:
                    edge["conferences"].add(conference)
                if year:
                    edge["years"].add(year)

    edge_rows: list[dict[str, object]] = []
    nodes_all = set()
    repeated_edge_count = 0
    max_shared_papers = 0
    for edge in edge_stats.values():
        nodes_all.add(str(edge["left_key"]))
        nodes_all.add(str(edge["right_key"]))
        shared = int(edge["shared_papers"])
        if shared > 1:
            repeated_edge_count += 1
        max_shared_papers = max(max_shared_papers, shared)
        years = sorted(str(year) for year in edge["years"] if year)
        edge_rows.append(
            {
                "mode": edge["mode"],
                "left_key": edge["left_key"],
                "left_name": edge["left_name"],
                "right_key": edge["right_key"],
                "right_name": edge["right_name"],
                "shared_papers": shared,
                "conference_count": len(edge["conferences"]),
                "year_first": years[0] if years else "",
                "year_last": years[-1] if years else "",
            }
        )

    summary_rows = [
        {
            "mode": mode,
            "node_count": len(nodes_all),
            "edge_count": len(edge_rows),
            "repeated_edge_count": repeated_edge_count,
            "max_shared_papers": max_shared_papers,
        }
    ]
    return (
        sorted(edge_rows, key=lambda row: (-int(row["shared_papers"]), str(row["left_name"]), str(row["right_name"]))),
        summary_rows,
    )


def write_report(path: Path, mode: str, conference: str | None, year: str | None, summary: list[dict[str, object]], edges: list[dict[str, object]]) -> None:
    lines = [
        "# Conference Collaboration Analysis Report",
        "",
        "## Scope",
        "",
        f"- mode: {mode}",
        f"- conference: {conference or 'all'}",
        f"- year: {year or 'all'}",
        "",
        "## Highlights",
        "",
    ]
    if summary:
        row = summary[0]
        lines.append(f"- nodes: {row['node_count']}")
        lines.append(f"- edges: {row['edge_count']}")
        lines.append(f"- repeated_edges: {row['repeated_edge_count']}")
    for edge in edges[:10]:
        lines.append(f"- {edge['left_name']} <-> {edge['right_name']}: shared_papers={edge['shared_papers']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate collaboration edge tables from normalized conference data.")
    parser.add_argument("--input", required=True, help="Path to normalized author_affiliation_facts.csv")
    parser.add_argument("--output-dir", required=True, help="Output analysis directory root")
    parser.add_argument("--mode", required=True, choices=MODE_CHOICES, help="Collaboration mode")
    parser.add_argument("--conference")
    parser.add_argument("--year")
    args = parser.parse_args()

    rows = filter_rows(read_rows(Path(args.input)), args.conference, args.year)
    edges, summary = aggregate_edges(rows, args.mode)
    output_dir = Path(args.output_dir) / "collaboration"
    write_rows(output_dir / "collaboration_edges.csv", edges)
    write_rows(output_dir / "collaboration_summary.csv", summary)
    write_report(output_dir / "collaboration_report.md", args.mode, args.conference, args.year, summary, edges)


if __name__ == "__main__":
    main()
