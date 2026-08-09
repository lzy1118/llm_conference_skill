#!/usr/bin/env python3
import csv
import re
import sys
from collections import Counter, defaultdict


COUNTRY_ALIASES = {
    "australia": "Australia", "austria": "Austria", "belgium": "Belgium", "argentina": "Argentina", "brazil": "Brazil",
    "canada": "Canada", "china": "China", "cn": "China", "people's republic of china": "China",
    "pr china": "China", "colombia": "Colombia", "costa rica": "Costa Rica",
    "czech republic": "Czech Republic", "denmark": "Denmark", "england": "UK",
    "estonia": "Estonia", "finland": "Finland", "france": "France", "german": "Germany",
    "germany": "Germany", "greece": "Greece", "hong kong": "Hong Kong", "hungary": "Hungary",
    "india": "India", "iran": "Iran", "israel": "Israel", "italy": "Italy", "japan": "Japan",
    "korea": "South Korea", "republic of korea": "South Korea", "south korea": "South Korea",
    "ireland": "Ireland", "iceland": "Iceland", "luxembourg": "Luxembourg", "malaysia": "Malaysia", "mexico": "Mexico", "netherlands": "Netherlands",
    "the netherlands": "Netherlands", "new zealand": "New Zealand", "norway": "Norway",
    "pakistan": "Pakistan", "poland": "Poland", "portugal": "Portugal", "romania": "Romania", "russia": "Russia", "serbia": "Serbia", "slovenia": "Slovenia", "south africa": "South Africa", "saudi arabia": "Saudi Arabia",
    "singapore": "Singapore", "slovakia": "Slovakia", "spain": "Spain", "sweden": "Sweden",
    "switzerland": "Switzerland", "taiwan": "Taiwan", "uae": "United Arab Emirates",
    "thailand": "Thailand", "turkey": "Turkey", "türkiye": "Turkey", "ukraine": "Ukraine", "united arab emirates": "United Arab Emirates", "uk": "UK", "united kingdom": "UK",
    "us": "USA", "usa": "USA", "united states": "USA", "united states of america": "USA",
    "vietnam": "Vietnam",
}


def trailing_country(affiliation):
    text = " ".join((affiliation or "").split()).strip(" ,.;")
    for alias, normalized in sorted(COUNTRY_ALIASES.items(), key=lambda item: -len(item[0])):
        if re.search(rf"(?:^|[,;\s]){re.escape(alias)}$", text.casefold()):
            return normalized
    return ""


REQUIRED = [
    "year",
    "conference",
    "title",
    "author",
    "author_rank",
    "affiliation_rank",
    "affiliations",
    "emails",
    "first_author",
    "co_first_author",
    "corresponding",
    "equal_contribution",
    "country",
    "orcid",
]


def clip(value, n=140):
    value = str(value)
    return value if len(value) <= n else value[: n - 3] + "..."


def print_items(title, items, limit):
    print(f"\n{title}: {len(items)}")
    for item in items[:limit]:
        print("  -", item)
    if len(items) > limit:
        print(f"  ... {len(items) - limit} more")


def main(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise SystemExit("empty CSV")
        raw_rows = []
        bad_column_count = []
        for line_no, row in enumerate(reader, 2):
            raw_rows.append((line_no, row))
            if len(row) != len(header):
                bad_column_count.append((line_no, len(row), row[:4]))

    rows = []
    if not bad_column_count:
        rows = [(line_no, dict(zip(header, row))) for line_no, row in raw_rows]

    print("CSV:", path)
    print("columns:", header)
    print("rows:", len(raw_rows))
    print("bad_column_count:", len(bad_column_count))
    for item in bad_column_count[:20]:
        print("  -", item)

    missing = [c for c in REQUIRED if c not in header]
    if missing:
        print("missing_required_columns:", missing)
        return 2
    if bad_column_count:
        return 2

    print("\nblank counts:")
    for col in header:
        print(f"  {col}: {sum(1 for _, r in rows if not r.get(col, '').strip())}")

    print("\nvalue counts:")
    for col in ["year", "conference", "first_author", "co_first_author", "corresponding", "equal_contribution"]:
        print(f"  {col}: {dict(Counter(r[col] for _, r in rows))}")
    print("  co/equal:", dict(Counter((r["co_first_author"], r["equal_contribution"]) for _, r in rows)))

    groups = defaultdict(list)
    for line_no, row in rows:
        groups[(row["year"], row["conference"], row["title"])].append((line_no, row))

    bad_bool = []
    bad_rank = []
    rule_problems = []
    duplicate_authors = []
    no_corresponding = []

    for line_no, row in rows:
        for col in ["first_author", "co_first_author", "corresponding", "equal_contribution"]:
            if row[col] not in ("true", "false"):
                bad_bool.append((line_no, col, row[col], clip(row["title"]), row["author"]))
        if not re.fullmatch(r"\d+", row["author_rank"]):
            bad_rank.append((line_no, row["author_rank"], clip(row["title"]), row["author"]))
        if not re.fullmatch(r"\d+", row["affiliation_rank"]):
            bad_rank.append((line_no, row["affiliation_rank"], clip(row["title"]), row["author"]))

    orcid_re = re.compile(r"^https://orcid\.org/\d{4}-\d{4}-\d{4}-[\dX]{4}$", re.I)

    for key, items in groups.items():
        author_groups = defaultdict(list)
        for line_no, row in items:
            author_groups[(row["author_rank"], row["author"].strip().casefold())].append((line_no, row))
        author_items = [(found[0][0], found[0][1]) for found in author_groups.values()]
        for author_key, author_rows in author_groups.items():
            author_rows = sorted(
                author_rows,
                key=lambda item: int(item[1]["affiliation_rank"]) if item[1]["affiliation_rank"].isdigit() else 10**9,
            )
            affiliation_ranks = sorted(
                int(row["affiliation_rank"])
                for _, row in author_rows
                if re.fullmatch(r"\d+", row["affiliation_rank"])
            )
            if affiliation_ranks != list(range(len(author_rows))):
                rule_problems.append((key, "affiliation rank gap/duplicate", author_key, affiliation_ranks))
            expected_countries = [trailing_country(row["affiliations"]) for _, row in author_rows]
            if len(expected_countries) > 1 and expected_countries[-1] and not any(expected_countries[:-1]):
                expected_countries = [expected_countries[-1]] * len(expected_countries)
            for (line_no, row), expected_country in zip(author_rows, expected_countries):
                if row["country"] != expected_country:
                    rule_problems.append((key, "country does not match author affiliation rule", line_no, row["country"], expected_country))
            for field in ("author_rank", "emails", "first_author", "co_first_author", "corresponding", "equal_contribution", "orcid"):
                values = {row[field] for _, row in author_rows}
                if len(values) > 1:
                    rule_problems.append((key, "author field differs across affiliation rows", author_key, field, sorted(values)))
        for line_no, row in items:
            if row["orcid"] and not orcid_re.fullmatch(row["orcid"]):
                rule_problems.append((key, "invalid orcid", line_no, row["orcid"]))
        ranks = []
        for line_no, row in author_items:
            if re.fullmatch(r"\d+", row["author_rank"]):
                ranks.append((int(row["author_rank"]), line_no, row))

        counts = Counter(rank for rank, _, _ in ranks)
        if counts:
            nums = sorted(counts)
            missing_nums = [n for n in range(nums[0], nums[-1] + 1) if n not in counts]
            if nums[0] != 0 or missing_nums:
                rule_problems.append((key, "rank gap/nonzero start", nums, missing_nums))

        for rank, count in counts.items():
            if count > 1:
                same_rank = [(line_no, row) for r, line_no, row in ranks if r == rank]
                valid_cofirst = (
                    rank == 0
                    and len(same_rank) >= 2
                    and all(
                        row["first_author"] == "true"
                        and row["co_first_author"] == "true"
                        and row["equal_contribution"] == "true"
                        for _, row in same_rank
                    )
                )
                if not valid_cofirst:
                    rule_problems.append(
                        (
                            key,
                            "bad duplicate rank",
                            rank,
                            [(line_no, row["author"], row["co_first_author"], row["equal_contribution"]) for line_no, row in same_rank],
                        )
                    )

        first = {line_no for line_no, row in author_items if row["first_author"] == "true"}
        rank0 = {line_no for line_no, row in author_items if row["author_rank"] == "0"}
        if first != rank0:
            rule_problems.append((key, "first_author != rank0", sorted(first), sorted(rank0)))

        co_first_marked = [(line_no, row) for line_no, row in author_items if row["co_first_author"] == "true"]
        equal_marked = [(line_no, row) for line_no, row in author_items if row["equal_contribution"] == "true"]
        if co_first_marked:
            if len(co_first_marked) < 2:
                rule_problems.append((key, "single co-first marker", [(line_no, row["author"], row["author_rank"]) for line_no, row in co_first_marked]))
            if any(row["author_rank"] != "0" or row["first_author"] != "true" for _, row in co_first_marked):
                rule_problems.append((key, "co-first rank is not 0", [(line_no, row["author"], row["author_rank"]) for line_no, row in co_first_marked]))
            if any(row["equal_contribution"] != "true" for _, row in co_first_marked):
                rule_problems.append((key, "co-first author lacks equal-contribution marker", [(line_no, row["author"]) for line_no, row in co_first_marked]))
        if equal_marked and len(equal_marked) < 2:
            rule_problems.append((key, "single equal-contribution marker", [(line_no, row["author"], row["author_rank"]) for line_no, row in equal_marked]))

        author_lines = defaultdict(list)
        for line_no, row in author_items:
            author_lines[row["author"].strip().lower()].append((line_no, row["author_rank"], row["author"]))
        for author, found in author_lines.items():
            if len(found) > 1:
                duplicate_authors.append((key, author, found))

        if not any(row["corresponding"] == "true" for _, row in author_items):
            no_corresponding.append((key, len(author_items)))

    email_re = re.compile(r"^[^@\s;,]+@[^@\s;,]+\.[^@\s;,]+$")
    bad_email = []
    for line_no, row in rows:
        email = row["emails"].strip()
        if not email:
            continue
        parts = [part.strip() for part in re.split(r"[;,]", email) if part.strip()]
        for part in parts:
            if not email_re.match(part):
                bad_email.append((line_no, row["author"], clip(row["title"]), email))
                break

    suspicious_authors = []
    split_name_candidates = []
    for line_no, row in rows:
        author = row["author"]
        reasons = []
        if re.search(r"[{}]", author):
            reasons.append("brace")
        if re.search(r"\d", author):
            reasons.append("digit")
        if "/" in author:
            reasons.append("slash")
        if re.search(r"\b(University|Institute|Laboratory|Lab|Edu|Keccak|Sha3|Csiro|CSIRO)\b", author, re.I):
            reasons.append("looks non-person")
        if reasons:
            suspicious_authors.append((line_no, ",".join(reasons), row["year"], clip(row["title"]), author, clip(row["affiliations"]), row["emails"]))
        elif re.match(r"^[A-Z] [A-Z][a-z]", author):
            split_name_candidates.append((line_no, row["year"], clip(row["title"]), author, row["emails"]))

    title_candidates = {}
    for line_no, row in rows:
        title = row["title"]
        reasons = []
        if re.search(r"\S -\S", title):
            reasons.append("space-before-hyphen")
        if re.search(r"\b(for|from|Over|Under|Characteristic) \.", title) or re.search(r"\. (SIS|BatchQMA|Z 2|F 2|q-ary)", title):
            reasons.append("stray-dot")
        if re.search(r"R andom|Argumen ts|f r o m|I ndia|Universit y", title):
            reasons.append("broken-word")
        if re.search(r"T -depth|log \* -|N 1/3 -|2 n/2 -|√ n-|\.\d+ Rounds", title):
            reasons.append("math-spacing")
        if reasons and title not in title_candidates:
            title_candidates[title] = (line_no, row["year"], ",".join(reasons), title)

    print("\nsummary:")
    print("  papers:", len(groups))
    print("  bad_bool:", len(bad_bool))
    print("  bad_rank:", len(bad_rank))
    print("  rule_problems:", len(rule_problems))
    print("  duplicate_authors_same_paper:", len(duplicate_authors))
    print("  bad_email:", len(bad_email))
    print("  suspicious_authors:", len(suspicious_authors))
    print("  split_name_candidates:", len(split_name_candidates))
    print("  unique_title_candidates:", len(title_candidates))
    print("  papers_without_corresponding:", len(no_corresponding))

    print_items("bad_bool", bad_bool, 40)
    print_items("bad_rank", bad_rank, 40)
    print_items("rule_problems", rule_problems, 80)
    print_items("duplicate_authors_same_paper", duplicate_authors, 40)
    print_items("bad_email", bad_email, 40)
    print_items("suspicious_authors", suspicious_authors, 80)
    print_items("split_name_candidates", split_name_candidates, 80)
    print_items("unique_title_candidates", list(title_candidates.values()), 80)
    print_items("papers_without_corresponding_sample", no_corresponding, 30)

    return 1 if (bad_bool or bad_rank or rule_problems or duplicate_authors or bad_email or suspicious_authors) else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_author_metadata.py path/to/file.csv")
    raise SystemExit(main(sys.argv[1]))
