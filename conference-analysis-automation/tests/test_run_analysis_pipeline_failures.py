import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_analysis_pipeline.py"
SPEC = importlib.util.spec_from_file_location("run_analysis_pipeline", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def run_args(tmp_path: Path, *, fail_fast: bool, runs: list[str]) -> SimpleNamespace:
    normalized_input = tmp_path / "facts.csv"
    normalized_input.write_text("paper_key\n", encoding="utf-8")
    return SimpleNamespace(
        output_dir=str(tmp_path / "output"),
        normalized_input=str(normalized_input),
        affilgood_input=None,
        conference=None,
        year=None,
        country=None,
        trend_entity="country",
        collaboration_mode="author",
        fail_fast=fail_fast,
        run=runs,
    )


def test_downstream_failure_returns_nonzero_and_keeps_manifest(tmp_path, monkeypatch):
    args = run_args(tmp_path, fail_fast=False, runs=["author"])
    calls = []
    monkeypatch.setattr(MODULE, "parse_args", lambda: args)
    monkeypatch.setattr(
        MODULE,
        "run_command",
        lambda command, cwd: (calls.append(command) or 7, "", "fixture failure"),
    )

    result = MODULE.main()

    output_dir = Path(args.output_dir)
    manifest = json.loads((output_dir / "automation_manifest.json").read_text(encoding="utf-8"))
    report = (output_dir / "automation_report.md").read_text(encoding="utf-8")
    assert result == 1
    assert len(calls) == 1
    assert manifest["steps"][0]["returncode"] == 7
    assert "author: failed" in report


def test_fail_fast_stops_later_steps_but_persists_failure_record(tmp_path, monkeypatch):
    args = run_args(tmp_path, fail_fast=True, runs=["country", "author"])
    calls = []
    monkeypatch.setattr(MODULE, "parse_args", lambda: args)
    monkeypatch.setattr(
        MODULE,
        "run_command",
        lambda command, cwd: (calls.append(command) or 7, "", "fixture failure"),
    )

    result = MODULE.main()

    output_dir = Path(args.output_dir)
    manifest = json.loads((output_dir / "automation_manifest.json").read_text(encoding="utf-8"))
    assert result == 1
    assert len(calls) == 1
    assert len(manifest["steps"]) == 1
    assert manifest["steps"][0]["returncode"] == 7
