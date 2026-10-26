from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import match_institution_reference_csv as matcher
import run_affilgood


def test_terminal_country_preserves_original_institution_and_country_text():
    institution = "École Polytechnique Fédérale de Lausanne"
    components = [f"{institution} Switzerland"]

    remaining, country_raw, country = matcher.extract_terminal_country(
        components, {"switzerland": "Switzerland"}
    )

    assert remaining == [institution]
    assert country_raw == "Switzerland"
    assert country == "Switzerland"


def test_same_input_and_output_fails_without_truncating_input(tmp_path):
    source = tmp_path / "records.jsonl"
    original = b'{"record_id":"p1","affiliation":"ETH Zurich"}\n'
    source.write_bytes(original)
    args = Namespace(input_format="auto", batch_size=1, verbose=False)

    with pytest.raises(ValueError, match="different files"):
        run_affilgood.process_file(None, args, source, source)

    assert source.read_bytes() == original
