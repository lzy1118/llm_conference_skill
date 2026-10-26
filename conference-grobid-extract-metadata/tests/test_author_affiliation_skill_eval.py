import csv
import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "evaluate_author_affiliation_skill.py"
spec = importlib.util.spec_from_file_location("author_affiliation_eval", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_prf_and_template(tmp_path):
    metadata = tmp_path / "metadata_json"
    metadata.mkdir()
    payload = {
        "title": "Demo",
        "authors": [
            {"name": "A", "affiliations": ["Inst X"]},
            {"name": "B", "affiliations": ["Inst X", "Inst Y"]},
        ],
        "author_affiliation_relations": [
            {"author": "A", "affiliation": "Inst X"},
            {"author": "B", "affiliation": "Inst X"},
            {"author": "B", "affiliation": "Inst Y"},
        ],
    }
    (metadata / "p1.json").write_text(json.dumps(payload), encoding="utf-8")
    template = tmp_path / "annotations.jsonl"
    assert module.build_template(metadata, template, limit=500, seed=1) == 1
    row = json.loads(template.read_text(encoding="utf-8"))
    assert row["paper_id"] == "p1"
    assert row["authors"] == ["A", "B"]
    assert len(row["skill_pairs"]) == 3
    assert len(row["sequential_pairs"]) == 2
    assert row["grobid_pairs"] is None
    assert row["grobid_evidence_available"] is False
    assert row["gold_pairs"] is None
    assert all(value is None for value in row["ablation_pairs"].values())
    assert module.prf({("A", "X")}, {("A", "X"), ("B", "Y")})["f1"] == 2 / 3


def test_template_reads_separate_grobid_evidence(tmp_path):
    metadata = tmp_path / "metadata_json"
    evidence_dir = tmp_path / "evidence_json"
    metadata.mkdir()
    evidence_dir.mkdir()
    payload = {
        "authors": [{"name": "A", "affiliations": ["Repaired Inst"]}],
        "author_affiliation_relations": [
            {"author": "A", "affiliation": "Repaired Inst"},
        ],
    }
    (metadata / "p1.json").write_text(json.dumps(payload), encoding="utf-8")
    evidence = {
        "paper_id": "p1",
        "evidence": [{
            "source": "grobid_tei",
            "field": "author",
            "raw_text": "A",
            "affiliations": ["TEI Inst"],
        }],
    }
    (evidence_dir / "p1.json").write_text(json.dumps(evidence), encoding="utf-8")

    template = tmp_path / "annotations.jsonl"
    assert module.build_template(metadata, template, limit=1) == 1
    row = json.loads(template.read_text(encoding="utf-8"))

    assert row["grobid_evidence_available"] is True
    assert row["grobid_pairs"] == [{"author": "A", "affiliation": "TEI Inst"}]
    assert row["skill_pairs"] == [{"author": "A", "affiliation": "Repaired Inst"}]


def test_evaluate_writes_outputs(tmp_path):
    row = {
        "paper_id": "p1",
        "grobid_pairs": [{"author": "A", "affiliation": "X"}],
        "sequential_pairs": [{"author": "A", "affiliation": "X"}],
        "skill_pairs": [{"author": "A", "affiliation": "X"}],
        "gold_pairs": [{"author": "A", "affiliation": "X"}],
        "layout_tags": ["footnote"],
        "ablation_pairs": {name: [] for name in module.ABLATIONS},
    }
    out = tmp_path / "results"
    assert module.evaluate([row], out) == 1
    assert (out / "results.csv").exists()
    assert (out / "summary.csv").exists()
    assert (out / "results.tex").exists()


def test_evaluate_omits_unavailable_baselines_and_pending_rows(tmp_path):
    row = {
        "paper_id": "annotated",
        "grobid_pairs": None,
        "sequential_pairs": [],
        "skill_pairs": [],
        "gold_pairs": [{"author": "A", "affiliation": "X"}],
        "layout_tags": [],
        "ablation_pairs": {name: None for name in module.ABLATIONS},
    }
    pending = {"paper_id": "pending", "gold_pairs": None}
    out = tmp_path / "results"

    assert module.evaluate([row, pending], out) == 1
    with (out / "summary.csv").open(encoding="utf-8") as handle:
        summary = list(csv.DictReader(handle))
    assert {item["method"] for item in summary} == {"sequential", "skill"}
    assert all(item["scope"] == "overall" for item in summary)
    with (out / "results.csv").open(encoding="utf-8") as handle:
        results = list(csv.DictReader(handle))
    assert len(results) == 2
    assert all(item["paper_id"] == "annotated" for item in results)


def test_evaluate_rejects_fully_unannotated_template(tmp_path):
    try:
        module.evaluate([{"paper_id": "p1", "gold_pairs": None}], tmp_path / "results")
    except ValueError as exc:
        assert "No annotated gold_pairs" in str(exc)
    else:
        raise AssertionError("pending annotation template must not be scored")


def test_ablation_delta_is_blank_without_skill_baseline(tmp_path):
    row = {
        "paper_id": "p1",
        "grobid_pairs": None,
        "sequential_pairs": None,
        "skill_pairs": None,
        "gold_pairs": [],
        "ablation_pairs": {
            "remove_layout_rules": [],
            "remove_evidence_validation": None,
            "remove_domain_rules": None,
        },
    }
    out = tmp_path / "results"

    module.evaluate([row], out)

    with (out / "summary.csv").open(encoding="utf-8") as handle:
        summary = list(csv.DictReader(handle))
    assert len(summary) == 1
    assert summary[0]["scope"] == "ablation"
    assert summary[0]["delta_f1"] == ""
