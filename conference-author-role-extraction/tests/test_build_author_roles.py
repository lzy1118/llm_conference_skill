import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_author_roles.py"
SPEC = importlib.util.spec_from_file_location("build_author_roles", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", 0),
        ("2.0", 2),
        ("2.5", None),
        ("-0.5", None),
        ("-1", None),
        ("Infinity", None),
        ("-Infinity", None),
        ("NaN", None),
        ("", None),
        ("not-a-number", None),
    ],
)
def test_parse_author_order_requires_nonnegative_finite_integer(value, expected):
    assert MODULE.parse_author_order(value) == expected


def test_invalid_fractional_and_nonfinite_orders_never_become_first_author():
    rows = [
        {"paper_key": "p1", "name": "Valid First", "author_order": "0.0"},
        {"paper_key": "p1", "name": "Fractional Positive", "author_order": "0.5"},
        {"paper_key": "p1", "name": "Fractional Negative", "author_order": "-0.5"},
        {"paper_key": "p1", "name": "Negative", "author_order": "-1"},
        {"paper_key": "p1", "name": "Infinite", "author_order": "Infinity"},
    ]

    roles, report = MODULE.build_roles(rows)

    assert [(row["author_name"], row["is_first_author"]) for row in roles] == [("Valid First", "true")]
    assert report["invalid_author_order_rows"] == 4


def test_unicode_names_and_fallback_paper_titles_get_distinct_keys():
    assert MODULE.row_author_key({"name": "张伟"}) != MODULE.row_author_key({"name": "李伟"})
    assert MODULE.row_paper_key({"conference": "crypto", "year": "2025", "title": "密码学新进展"}) != MODULE.row_paper_key(
        {"conference": "crypto", "year": "2025", "title": "计算机安全新进展"}
    )
