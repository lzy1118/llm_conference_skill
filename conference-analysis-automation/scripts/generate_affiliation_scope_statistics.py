from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


SCOPE_CHOICES = ("first", "participating")


def read_rows(path: Path) -> list[dict[str, str]]:
    """从 CSV 读取作者-论文-机构事实表。"""
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    """写出派生统计结果，并保持当前列顺序。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def split_pipe_values(value: str) -> list[str]:
    """将存储的多值机构字段拆分为规范化列表。"""
    text = (value or "").replace(" | ", ";")
    return [part.strip() for part in text.split(";") if part.strip()]


def normalize_institution_name(name: str, canonical_name: str) -> str:
    """优先使用规范机构名，同时保留可读的展示名称。"""
    preferred = (canonical_name or "").strip() or (name or "").strip()
    return " ".join(preferred.replace("&amp;", "&").split())


def filter_rows(rows: list[dict[str, str]], conference: str | None, year: str | None) -> list[dict[str, str]]:
    """在聚合前按指定会议和年份过滤事实数据。"""
    filtered = rows
    if conference:
        filtered = [row for row in filtered if row.get("conference") == conference]
    if year:
        filtered = [row for row in filtered if row.get("year") == str(year)]
    return filtered


def iter_scope_records(row: dict[str, str], scope: str) -> list[dict[str, str]]:
    """按第一机构或参与机构口径展开单位作者的机构记录。"""
    if scope == "first":
        return [
            {
                "institution_name": row.get("first_inst", ""),
                "institution_key": row.get("first_institution_key", ""),
                "institution_id": row.get("first_institution_id", ""),
                "canonical_name": row.get("first_canonical_institution_name", ""),
                "country": row.get("first_country", ""),
            }
        ]

    institutions = split_pipe_values(row.get("participating_insts", ""))
    institution_keys = split_pipe_values(row.get("participating_institution_keys", ""))
    institution_ids = split_pipe_values(row.get("participating_institution_ids", ""))
    canonical_names = split_pipe_values(row.get("participating_canonical_institution_names", ""))
    aligned_countries = split_pipe_values(row.get("participating_inst_countries", ""))
    unique_countries = split_pipe_values(row.get("participating_countries", ""))

    records: list[dict[str, str]] = []
    for index, institution_name in enumerate(institutions):
        records.append(
            {
                "institution_name": institution_name,
                "institution_key": institution_keys[index] if index < len(institution_keys) else "",
                "institution_id": institution_ids[index] if index < len(institution_ids) else "",
                "canonical_name": canonical_names[index] if index < len(canonical_names) else "",
                "country": (
                    aligned_countries[index]
                    if index < len(aligned_countries)
                    else unique_countries[0]
                    if len(unique_countries) == 1
                    else ""
                ),
            }
        )
    return records


def aggregate_country(rows: list[dict[str, str]], scope: str) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    """按单一口径聚合国家层面的论文、作者和机构数量。"""
    by_country: dict[str, dict[str, object]] = defaultdict(
        lambda: {
            "paper_keys": set(),
            "author_keys": set(),
            "institution_keys": set(),
            "conferences": set(),
            "years": set(),
        }
    )
    by_conference: dict[tuple[str, str], dict[str, object]] = defaultdict(
        lambda: {"paper_keys": set(), "author_keys": set(), "institution_keys": set()}
    )
    by_year: dict[tuple[str, str], dict[str, object]] = defaultdict(
        lambda: {"paper_keys": set(), "author_keys": set(), "institution_keys": set()}
    )

    total_papers = {row["paper_key"] for row in rows}
    total_authors = {row["author_paper_key"] for row in rows}

    for row in rows:
        scope_records = iter_scope_records(row, scope)
        author_marker = row["author_paper_key"]
        for record in scope_records:
            country = record.get("country", "") or "Unknown"
            inst_key = record.get("institution_key", "") or record.get("institution_name", "")
            entry = by_country[country]
            entry["paper_keys"].add(row["paper_key"])
            entry["author_keys"].add((author_marker, country))
            if inst_key:
                entry["institution_keys"].add(inst_key)
            entry["conferences"].add(row["conference"])
            entry["years"].add(row["year"])

            conf_key = (country, row["conference"])
            by_conference[conf_key]["paper_keys"].add(row["paper_key"])
            by_conference[conf_key]["author_keys"].add((author_marker, country))
            if inst_key:
                by_conference[conf_key]["institution_keys"].add(inst_key)

            year_key = (country, row["year"])
            by_year[year_key]["paper_keys"].add(row["paper_key"])
            by_year[year_key]["author_keys"].add((author_marker, country))
            if inst_key:
                by_year[year_key]["institution_keys"].add(inst_key)

    total_paper_count = max(len(total_papers), 1)
    total_author_count = max(len(total_authors), 1)
    summary: list[dict[str, object]] = []
    for country, stats in by_country.items():
        papers = len(stats["paper_keys"])
        authors = len(stats["author_keys"])
        summary.append(
            {
                "affiliation_scope": scope,
                "country": country,
                "papers": papers,
                "authors": authors,
                "institutions": len(stats["institution_keys"]),
                "paper_share": round(papers / total_paper_count, 6),
                "author_share": round(authors / total_author_count, 6),
                "avg_authors_per_paper": round(authors / papers, 6) if papers else 0.0,
                "conference_count": len(stats["conferences"]),
                "year_min": min(stats["years"]) if stats["years"] else "",
                "year_max": max(stats["years"]) if stats["years"] else "",
            }
        )

    by_conference_rows = [
        {
            "affiliation_scope": scope,
            "country": country,
            "conference": conference,
            "papers": len(stats["paper_keys"]),
            "authors": len(stats["author_keys"]),
            "institutions": len(stats["institution_keys"]),
        }
        for (country, conference), stats in by_conference.items()
    ]
    by_year_rows = [
        {
            "affiliation_scope": scope,
            "country": country,
            "year": year,
            "papers": len(stats["paper_keys"]),
            "authors": len(stats["author_keys"]),
            "institutions": len(stats["institution_keys"]),
        }
        for (country, year), stats in by_year.items()
    ]
    return (
        sorted(summary, key=lambda row: (-int(row["papers"]), -int(row["authors"]), str(row["country"]))),
        sorted(by_conference_rows, key=lambda row: (row["conference"], -int(row["papers"]), row["country"])),
        sorted(by_year_rows, key=lambda row: (row["year"], -int(row["papers"]), row["country"])),
    )


def aggregate_institutions(rows: list[dict[str, str]], scope: str) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    """按选定归属口径聚合机构层面的统计结果。"""
    grouped: dict[str, dict[str, object]] = defaultdict(
        lambda: {
            "institution_id": "",
            "institution_name": "",
            "country": "",
            "paper_keys": set(),
            "author_keys": set(),
            "first_author_papers": set(),
            "conferences": set(),
            "years": set(),
        }
    )
    by_conference: dict[tuple[str, str], set[str]] = defaultdict(set)
    by_year: dict[tuple[str, str], set[str]] = defaultdict(set)
    total_papers = {row["paper_key"] for row in rows}
    total_paper_count = max(len(total_papers), 1)

    for row in rows:
        scope_records = iter_scope_records(row, scope)
        for record in scope_records:
            institution_key = (record.get("institution_id", "") or record.get("institution_key", "") or record.get("institution_name", "")).strip()
            if not institution_key:
                continue
            entry = grouped[institution_key]
            entry["institution_id"] = entry["institution_id"] or record.get("institution_id", "")
            entry["institution_name"] = entry["institution_name"] or normalize_institution_name(
                record.get("institution_name", ""),
                record.get("canonical_name", ""),
            )
            entry["country"] = entry["country"] or record.get("country", "")
            entry["paper_keys"].add(row["paper_key"])
            entry["author_keys"].add(row["author_paper_key"])
            entry["conferences"].add(row["conference"])
            entry["years"].add(row["year"])
            if str(row["author_order"]) == "0":
                entry["first_author_papers"].add(row["paper_key"])
            by_conference[(institution_key, row["conference"])].add(row["paper_key"])
            by_year[(institution_key, row["year"])].add(row["paper_key"])

    summary: list[dict[str, object]] = []
    for institution_key, entry in grouped.items():
        papers = len(entry["paper_keys"])
        summary.append(
            {
                "affiliation_scope": scope,
                "institution_key": institution_key,
                "institution_id": entry["institution_id"],
                "institution_name": entry["institution_name"],
                "country": entry["country"],
                "papers": papers,
                "authors": len(entry["author_keys"]),
                "first_author_papers": len(entry["first_author_papers"]),
                "conferences": len(entry["conferences"]),
                "years_active": len(entry["years"]),
                "paper_share": round(papers / total_paper_count, 6),
            }
        )

    conference_rows = [
        {
            "affiliation_scope": scope,
            "institution_key": institution_key,
            "conference": conference,
            "papers": len(papers),
        }
        for (institution_key, conference), papers in by_conference.items()
    ]
    year_rows = [
        {
            "affiliation_scope": scope,
            "institution_key": institution_key,
            "year": year,
            "papers": len(papers),
        }
        for (institution_key, year), papers in by_year.items()
    ]
    return (
        sorted(summary, key=lambda row: (-int(row["papers"]), -int(row["authors"]), str(row["institution_name"]))),
        sorted(conference_rows, key=lambda row: (row["conference"], -int(row["papers"]), row["institution_key"])),
        sorted(year_rows, key=lambda row: (row["year"], -int(row["papers"]), row["institution_key"])),
    )


def write_report(path: Path, *, scope: str, conference: str | None, year: str | None, country_rows: list[dict[str, object]], institution_rows: list[dict[str, object]]) -> None:
    """为单次机构口径统计写出简要的 Markdown 摘要。"""
    lines = [
        "# Affiliation Scope Statistics Report",
        "",
        "## Scope",
        "",
        f"- affiliation_scope: {scope}",
        f"- conference: {conference or 'all'}",
        f"- year: {year or 'all'}",
        "",
        "## Country Highlights",
        "",
    ]
    if country_rows:
        for row in country_rows[:10]:
            lines.append(f"- {row['country']}: papers={row['papers']} authors={row['authors']} institutions={row['institutions']}")
    else:
        lines.append("No country rows matched the selected filters.")
    lines.extend(["", "## Institution Highlights", ""])
    if institution_rows:
        for row in institution_rows[:10]:
            lines.append(f"- {row['institution_name']}: papers={row['papers']} authors={row['authors']}")
    else:
        lines.append("No institution rows matched the selected filters.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_default_policy(
    base_dir: Path,
    *,
    conference: str | None,
    year: str | None,
    first_country_summary: list[dict[str, object]],
    first_country_by_conference: list[dict[str, object]],
    first_country_by_year: list[dict[str, object]],
    participating_institution_summary: list[dict[str, object]],
    participating_institution_by_conference: list[dict[str, object]],
    participating_institution_by_year: list[dict[str, object]],
) -> None:
    """导出当前分析使用的混合默认统计口径。"""
    default_dir = base_dir / "default_policy"
    write_rows(default_dir / "country_summary.csv", first_country_summary)
    write_rows(default_dir / "country_by_conference.csv", first_country_by_conference)
    write_rows(default_dir / "country_by_year.csv", first_country_by_year)
    write_rows(default_dir / "institution_summary.csv", participating_institution_summary)
    write_rows(default_dir / "institution_by_conference.csv", participating_institution_by_conference)
    write_rows(default_dir / "institution_by_year.csv", participating_institution_by_year)
    lines = [
        "# Default Affiliation Policy",
        "",
        "## Rule",
        "",
        "- author attribution: primary institution only (first affiliation)",
        "- institution totals: appearance-based wide credit across all confirmed participating institutions",
        f"- conference: {conference or 'all'}",
        f"- year: {year or 'all'}",
        "",
        "## Files",
        "",
        "- country_*: derived from first affiliation scope",
        "- institution_*: derived from participating affiliation scope",
    ]
    (default_dir / "policy_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    """生成第一机构、参与机构及混合口径三套汇总表。"""
    parser = argparse.ArgumentParser(description="Generate dual-scope affiliation statistics from author_paper_affiliation_facts.csv")
    parser.add_argument("--input", required=True, help="Path to author_paper_affiliation_facts.csv")
    parser.add_argument("--output-dir", required=True, help="Output analysis directory")
    parser.add_argument("--conference")
    parser.add_argument("--year")
    args = parser.parse_args()

    rows = filter_rows(read_rows(Path(args.input)), args.conference, args.year)
    base_dir = Path(args.output_dir) / "affiliation_scope"
    results: dict[str, tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]] = {}
    for scope in SCOPE_CHOICES:
        country_summary, country_by_conference, country_by_year = aggregate_country(rows, scope)
        institution_summary, institution_by_conference, institution_by_year = aggregate_institutions(rows, scope)
        results[scope] = (
            country_summary,
            country_by_conference,
            country_by_year,
            institution_summary,
            institution_by_conference,
            institution_by_year,
        )
        scope_dir = base_dir / scope
        write_rows(scope_dir / "country_summary.csv", country_summary)
        write_rows(scope_dir / "country_by_conference.csv", country_by_conference)
        write_rows(scope_dir / "country_by_year.csv", country_by_year)
        write_rows(scope_dir / "institution_summary.csv", institution_summary)
        write_rows(scope_dir / "institution_by_conference.csv", institution_by_conference)
        write_rows(scope_dir / "institution_by_year.csv", institution_by_year)
        write_report(
            scope_dir / "affiliation_scope_report.md",
            scope=scope,
            conference=args.conference,
            year=args.year,
            country_rows=country_summary,
            institution_rows=institution_summary,
        )

    write_default_policy(
        base_dir,
        conference=args.conference,
        year=args.year,
        first_country_summary=results["first"][0],
        first_country_by_conference=results["first"][1],
        first_country_by_year=results["first"][2],
        participating_institution_summary=results["participating"][3],
        participating_institution_by_conference=results["participating"][4],
        participating_institution_by_year=results["participating"][5],
    )


if __name__ == "__main__":
    main()
