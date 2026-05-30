from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_OUTPUT_DIR = Path("generated-data") / "author-roles"
DEFAULT_OVERRIDE_TEMPLATE = "author_role_overrides_template.csv"

ROLE_FIELDS = [
    "paper_key",
    "conference",
    "year",
    "paper_id",
    "title",
    "author_key",
    "author_name",
    "author_order",
    "is_first_author",
    "is_participating_author",
    "is_corresponding_author",
    "is_equal_contribution",
    "role_source",
    "role_evidence",
    "confidence",
    "needs_review",
]

OVERRIDE_FIELDS = [
    "paper_key",
    "conference",
    "year",
    "paper_id",
    "title",
    "author_key",
    "author_name",
    "author_order",
    "is_corresponding_author",
    "is_equal_contribution",
    "role_source",
    "role_evidence",
    "confidence",
    "needs_review",
    "notes",
]


def normalize_space(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def slug_text(value: str) -> str:
    lowered = normalize_space(value).casefold()
    return re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")


def stable_key(*parts: str) -> str:
    cleaned = [slug_text(part) for part in parts if normalize_space(part)]
    joined = "|".join(cleaned)
    if not joined:
        return ""
    digest = hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]
    preview = "-".join(part for part in cleaned[:3] if part)[:80].strip("-")
    return f"{preview}-{digest}" if preview else digest


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_author_order(value: object) -> int | None:
    text = normalize_space(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def row_paper_key(row: dict[str, str]) -> str:
    paper_key = normalize_space(row.get("paper_key", ""))
    if paper_key:
        return paper_key
    return stable_key(
        normalize_space(row.get("conference", "")),
        normalize_space(row.get("year", "")),
        normalize_space(row.get("paper_id", "")) or normalize_space(row.get("title", "")) or normalize_space(row.get("article_tag", "")),
    )


def row_author_key(row: dict[str, str]) -> str:
    author_key = normalize_space(row.get("author_key", ""))
    if author_key:
        return author_key
    return stable_key(normalize_space(row.get("name", "")) or normalize_space(row.get("author_name", "")))


def build_roles(rows: list[dict[str, str]]) -> tuple[list[dict[str, object]], dict[str, object]]:
    roles_by_key: dict[tuple[str, int, str], dict[str, object]] = {}
    invalid_author_order_rows = 0
    missing_author_rows = 0

    for row in rows:
        paper_key = row_paper_key(row)
        author_name = normalize_space(row.get("name", "")) or normalize_space(row.get("author_name", ""))
        author_key = row_author_key(row)
        author_order = parse_author_order(row.get("author_order", ""))
        if not author_name:
            missing_author_rows += 1
            continue
        if author_order is None:
            invalid_author_order_rows += 1
            continue
        role_key = (paper_key, author_order, author_key or author_name)
        roles_by_key.setdefault(
            role_key,
            {
                "paper_key": paper_key,
                "conference": normalize_space(row.get("conference", "")),
                "year": normalize_space(row.get("year", "")),
                "paper_id": normalize_space(row.get("paper_id", "")),
                "title": normalize_space(row.get("title", "")),
                "author_key": author_key,
                "author_name": author_name,
                "author_order": author_order,
                "is_first_author": str(author_order == 0).lower(),
                "is_participating_author": "true",
                "is_corresponding_author": "false",
                "is_equal_contribution": "false",
                "role_source": "author_order",
                "role_evidence": "author_order == 0" if author_order == 0 else "present_in_author_list",
                "confidence": "1.0" if author_order == 0 else "0.95",
                "needs_review": "true",
            },
        )

    roles = sorted(roles_by_key.values(), key=lambda row: (str(row["conference"]), str(row["year"]), str(row["paper_key"]), int(row["author_order"])))
    report = {
        "input_rows": len(rows),
        "role_rows": len(roles),
        "papers": len({row["paper_key"] for row in roles}),
        "first_author_rows": sum(1 for row in roles if row["is_first_author"] == "true"),
        "participating_author_rows": sum(1 for row in roles if row["is_participating_author"] == "true"),
        "corresponding_author_rows": sum(1 for row in roles if row["is_corresponding_author"] == "true"),
        "equal_contribution_rows": sum(1 for row in roles if row["is_equal_contribution"] == "true"),
        "invalid_author_order_rows": invalid_author_order_rows,
        "missing_author_rows": missing_author_rows,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return roles, report


def load_overrides(path: Path | None) -> dict[tuple[str, str, str], dict[str, str]]:
    if path is None or not path.exists() or path.stat().st_size == 0:
        return {}
    overrides: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in read_rows(path):
        paper_key = normalize_space(row.get("paper_key", ""))
        author_key = normalize_space(row.get("author_key", ""))
        author_order = normalize_space(row.get("author_order", ""))
        if not paper_key or not author_key or not author_order:
            continue
        overrides[(paper_key, author_order, author_key)] = row
    return overrides


def apply_overrides(roles: list[dict[str, object]], overrides: dict[tuple[str, str, str], dict[str, str]]) -> tuple[list[dict[str, object]], int]:
    applied = 0
    for role in roles:
        key = (str(role.get("paper_key", "")), str(role.get("author_order", "")), str(role.get("author_key", "")))
        override = overrides.get(key)
        if not override:
            continue
        for field in ("is_corresponding_author", "is_equal_contribution", "needs_review"):
            value = normalize_space(override.get(field, ""))
            if value:
                role[field] = "true" if value.lower() in {"1", "true", "yes", "y"} else "false"
        for field in ("role_source", "role_evidence", "confidence"):
            value = normalize_space(override.get(field, ""))
            if value:
                role[field] = value
        applied += 1
    return roles, applied


def write_override_template(output_dir: Path, roles: list[dict[str, object]], limit: int = 200) -> None:
    rows: list[dict[str, object]] = []
    for role in roles[:limit]:
        rows.append(
            {
                "paper_key": role.get("paper_key", ""),
                "conference": role.get("conference", ""),
                "year": role.get("year", ""),
                "paper_id": role.get("paper_id", ""),
                "title": role.get("title", ""),
                "author_key": role.get("author_key", ""),
                "author_name": role.get("author_name", ""),
                "author_order": role.get("author_order", ""),
                "is_corresponding_author": "",
                "is_equal_contribution": "",
                "role_source": "manual",
                "role_evidence": "",
                "confidence": "",
                "needs_review": "",
                "notes": "",
            }
        )
    write_csv(output_dir / DEFAULT_OVERRIDE_TEMPLATE, rows, OVERRIDE_FIELDS)


def write_report(output_dir: Path, report: dict[str, object]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "author_role_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Author Role Extraction Report",
        "",
        "## Summary",
        "",
        f"- input_rows: {report['input_rows']}",
        f"- role_rows: {report['role_rows']}",
        f"- papers: {report['papers']}",
        f"- first_author_rows: {report['first_author_rows']}",
        f"- corresponding_author_rows: {report['corresponding_author_rows']}",
        f"- equal_contribution_rows: {report['equal_contribution_rows']}",
        f"- applied_override_rows: {report['applied_override_rows']}",
        f"- invalid_author_order_rows: {report['invalid_author_order_rows']}",
        "",
        "## Notes",
        "",
        "- Corresponding author and equal-contribution fields are placeholders in this minimal pipeline.",
        "- The current deterministic role source is author_order only.",
    ]
    (output_dir / "author_role_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build paper-author role facts from normalized author rows.")
    parser.add_argument("--input", required=True, type=Path, help="Input author affiliation CSV")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--role-overrides", type=Path, help="Optional manually verified role overrides CSV")
    parser.add_argument("--override-template-limit", type=int, default=200, help="Number of rows to include in override template")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = read_rows(args.input.resolve())
    roles, report = build_roles(rows)
    output_dir = args.output_dir.resolve()
    overrides = load_overrides(args.role_overrides.resolve() if args.role_overrides else None)
    roles, applied_overrides = apply_overrides(roles, overrides)
    report["applied_override_rows"] = applied_overrides
    report["corresponding_author_rows"] = sum(1 for row in roles if row["is_corresponding_author"] == "true")
    report["equal_contribution_rows"] = sum(1 for row in roles if row["is_equal_contribution"] == "true")
    write_csv(output_dir / "paper_author_roles.csv", roles, ROLE_FIELDS)
    write_override_template(output_dir, roles, limit=args.override_template_limit)
    write_report(output_dir, report)


if __name__ == "__main__":
    main()
