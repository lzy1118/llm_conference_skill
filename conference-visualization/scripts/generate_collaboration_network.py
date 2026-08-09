from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
from collections import defaultdict
from pathlib import Path


REQUIRED_EDGE_COLUMNS = {
    "left_key",
    "left_name",
    "right_key",
    "right_name",
    "shared_papers",
    "conference_count",
    "year_first",
    "year_last",
}
DEFAULT_TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "collaboration-network-fragment.html"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_EDGE_COLUMNS - columns
        if missing:
            raise ValueError(f"Missing collaboration edge columns: {sorted(missing)}")
        return list(reader)


def read_summary(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return next(csv.DictReader(handle), {})


def parse_positive_int(value: str, field: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid integer in {field}: {value!r}") from exc
    if parsed < 0:
        raise ValueError(f"{field} must be non-negative: {value!r}")
    return parsed


def build_network(edge_rows: list[dict[str, str]]) -> tuple[list[list[object]], list[list[object]], dict[str, int]]:
    if not edge_rows:
        raise ValueError("The collaboration edge table is empty for the requested scope")

    raw_edges: list[tuple[str, str, int, int, str, str]] = []
    names: dict[str, str] = {}
    strength: defaultdict[str, int] = defaultdict(int)
    neighbors: defaultdict[str, set[str]] = defaultdict(set)
    for row in edge_rows:
        left_key = row["left_key"].strip() or row["left_name"].strip()
        right_key = row["right_key"].strip() or row["right_name"].strip()
        if not left_key or not right_key or left_key == right_key:
            continue
        names[left_key] = row["left_name"].strip() or left_key
        names[right_key] = row["right_name"].strip() or right_key
        shared = parse_positive_int(row["shared_papers"], "shared_papers")
        conference_count = parse_positive_int(row["conference_count"], "conference_count")
        if shared == 0:
            continue
        raw_edges.append(
            (
                left_key,
                right_key,
                shared,
                conference_count,
                row["year_first"].strip(),
                row["year_last"].strip(),
            )
        )
        strength[left_key] += shared
        strength[right_key] += shared
        neighbors[left_key].add(right_key)
        neighbors[right_key].add(left_key)

    if not raw_edges:
        raise ValueError("The collaboration edge table has no valid non-zero edges")

    ordered_keys = sorted(names, key=lambda key: (-strength[key], -len(neighbors[key]), names[key].casefold()))
    index = {key: position for position, key in enumerate(ordered_keys)}
    nodes = [[names[key], strength[key], len(neighbors[key])] for key in ordered_keys]
    edges = [
        [index[left], index[right], shared, conference_count, year_first, year_last]
        for left, right, shared, conference_count, year_first, year_last in raw_edges
    ]
    edges.sort(key=lambda edge: (-edge[2], str(nodes[edge[0]][0]).casefold(), str(nodes[edge[1]][0]).casefold()))
    stats = {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "repeated_edge_count": sum(edge[2] > 1 for edge in edges),
        "max_shared_papers": max(edge[2] for edge in edges),
    }
    return nodes, edges, stats


def json_for_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":")).replace("</", "<\\/")


def choose_render_floor(edges: list[list[object]], max_render_edges: int) -> int:
    max_shared = max(int(edge[2]) for edge in edges)
    for threshold in range(1, max_shared + 1):
        if sum(int(edge[2]) >= threshold for edge in edges) <= max_render_edges:
            return threshold
    return max_shared


def render_fragment(
    template: str,
    *,
    root_id: str,
    scope_label: str,
    nodes: list[list[object]],
    edges: list[list[object]],
    stats: dict[str, int],
    paper_count: int | None,
    minimum_threshold: int,
    default_threshold: int,
    top_edge_count: int,
) -> str:
    active_ids = {int(edge[0]) for edge in edges} | {int(edge[1]) for edge in edges}
    label_ids = sorted(active_ids)[:12]
    max_threshold = min(minimum_threshold + 2, stats["max_shared_papers"])
    thresholds = list(range(minimum_threshold, max_threshold + 1))
    if default_threshold not in thresholds:
        thresholds.append(default_threshold)
        thresholds.sort()
    threshold_buttons = "\n      ".join(
        f'<button type="button" class="btn" data-threshold="{value}" '
        f'aria-pressed="{str(value == default_threshold).lower()}">{value}+</button>'
        for value in thresholds
    )
    paper_stat = f'<span><strong>{paper_count}</strong> 篇论文</span>' if paper_count is not None else ""
    replacements = {
        "__ROOT_ID__": root_id,
        "__PAPER_STAT__": paper_stat,
        "__NODE_COUNT__": str(stats["node_count"]),
        "__EDGE_COUNT__": str(stats["edge_count"]),
        "__REPEATED_EDGE_COUNT__": str(stats["repeated_edge_count"]),
        "__THRESHOLD_BUTTONS__": threshold_buttons,
        "__ACCESSIBLE_TITLE__": html.escape(scope_label),
        "__DEFAULT_THRESHOLD__": str(default_threshold),
        "__NODES_JSON__": json_for_script(nodes),
        "__EDGES_JSON__": json_for_script(edges),
        "__LABEL_IDS_JSON__": json_for_script(label_ids),
        "__TOP_EDGE_COUNT__": str(top_edge_count),
    }
    rendered = template
    for placeholder, value in replacements.items():
        rendered = rendered.replace(placeholder, value)
    unresolved = sorted(set(re.findall(r"__[A-Z][A-Z0-9_]*__", rendered)))
    if unresolved:
        raise ValueError(f"Unresolved template placeholders remain: {unresolved}")
    return rendered.rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an interactive collaboration-network HTML fragment.")
    parser.add_argument("--edges", required=True, help="Path to collaboration_edges.csv")
    parser.add_argument("--summary", help="Optional path to collaboration_summary.csv")
    parser.add_argument("--output", required=True, help="Output HTML fragment path")
    parser.add_argument("--scope-label", default="Conference collaboration network")
    parser.add_argument("--default-threshold", type=int)
    parser.add_argument("--top-edges", type=int, default=10)
    parser.add_argument("--max-render-edges", type=int, default=600)
    parser.add_argument("--data-output", help="Optional JSON export for audit or reuse")
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE), help="HTML fragment template")
    args = parser.parse_args()

    if args.default_threshold is not None and args.default_threshold < 1:
        parser.error("--default-threshold must be at least 1")
    if args.top_edges < 1:
        parser.error("--top-edges must be at least 1")
    if args.max_render_edges < 1:
        parser.error("--max-render-edges must be at least 1")

    edge_path = Path(args.edges).resolve()
    summary_path = Path(args.summary).resolve() if args.summary else None
    output_path = Path(args.output).resolve()
    template_path = Path(args.template).resolve()
    nodes, edges, stats = build_network(read_csv(edge_path))
    summary = read_summary(summary_path)
    paper_count = parse_positive_int(summary["paper_count"], "paper_count") if summary.get("paper_count") else None
    minimum_threshold = choose_render_floor(edges, args.max_render_edges)
    rendered_edges = [edge for edge in edges if int(edge[2]) >= minimum_threshold]
    default_threshold = args.default_threshold or max(minimum_threshold, 2 if stats["max_shared_papers"] >= 2 else 1)
    if default_threshold < minimum_threshold:
        parser.error(
            f"--default-threshold {default_threshold} would render more than "
            f"--max-render-edges {args.max_render_edges}; use at least {minimum_threshold}"
        )
    if default_threshold > stats["max_shared_papers"]:
        parser.error(
            f"--default-threshold {default_threshold} exceeds the strongest edge "
            f"({stats['max_shared_papers']})"
        )

    digest = hashlib.sha1(f"{edge_path}|{args.scope_label}".encode("utf-8")).hexdigest()[:10]
    root_id = f"conference-collaboration-network-{digest}"
    fragment = render_fragment(
        template_path.read_text(encoding="utf-8"),
        root_id=root_id,
        scope_label=args.scope_label,
        nodes=nodes,
        edges=rendered_edges,
        stats=stats,
        paper_count=paper_count,
        minimum_threshold=minimum_threshold,
        default_threshold=default_threshold,
        top_edge_count=args.top_edges,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(fragment, encoding="utf-8")

    if args.data_output:
        data_path = Path(args.data_output).resolve()
        data_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "scope_label": args.scope_label,
            "source_edges": str(edge_path),
            "paper_count": paper_count,
            "stats": stats,
            "render_floor": minimum_threshold,
            "rendered_edge_count": len(rendered_edges),
            "nodes": [
                {"id": index, "name": node[0], "weighted_degree": node[1], "degree": node[2]}
                for index, node in enumerate(nodes)
            ],
            "edges": [
                {
                    "source": edge[0],
                    "target": edge[1],
                    "shared_papers": edge[2],
                    "conference_count": edge[3],
                    "year_first": edge[4],
                    "year_last": edge[5],
                }
                for edge in edges
            ],
        }
        data_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
