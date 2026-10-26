#!/usr/bin/env python3
"""Batch wrapper for running AffilGood inside automation pipelines."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional


SKILL_DIR = Path(__file__).resolve().parents[1]
BUNDLED_AFFILGOOD = SKILL_DIR / "affilgood-runtime"
BUNDLED_DATA = SKILL_DIR / "affilgood-data"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize raw affiliation strings with AffilGood and write JSONL."
    )
    parser.add_argument("--input", help="Input JSONL, CSV, or TXT file.")
    parser.add_argument("--output", help="Output JSONL path.")
    parser.add_argument(
        "--job",
        action="append",
        nargs=2,
        metavar=("INPUT", "OUTPUT"),
        help=(
            "Process an input/output pair. Repeat --job to process multiple files "
            "with one shared AffilGood model instance."
        ),
    )
    parser.add_argument(
        "--input-format",
        choices=["auto", "jsonl", "csv", "txt"],
        default="auto",
        help="Input format. Auto uses the input file extension.",
    )
    parser.add_argument(
        "--affiliation-field",
        default="affiliation",
        help="Field containing the raw affiliation string for JSONL/CSV input.",
    )
    parser.add_argument(
        "--id-field",
        default="record_id",
        help="Field containing a stable source id for JSONL/CSV input.",
    )
    parser.add_argument(
        "--affilgood-path",
        default=os.environ.get("AFFILGOOD_PROJECT_PATH") or (
            str(BUNDLED_AFFILGOOD) if BUNDLED_AFFILGOOD.is_dir() else None
        ),
        help="AffilGood project root; defaults to the runtime bundled inside this Skill when present.",
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("AFFILGOOD_DATA_DIR") or (
            str(BUNDLED_DATA) if BUNDLED_DATA.exists() else None
        ),
        help="AffilGood data directory; defaults to data bundled inside this Skill when present.",
    )
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--device", default=None, help="AffilGood device, e.g. cpu or cuda.")
    parser.add_argument(
        "--output-format",
        choices=["normalized", "full"],
        default="normalized",
        help="AffilGood public output format.",
    )
    parser.add_argument("--return-debug", action="store_true")
    parser.add_argument(
        "--check-setup",
        action="store_true",
        help="Check AffilGood import and data cache, then exit before model loading.",
    )
    parser.add_argument("--enable-language-detect", action="store_true")
    parser.add_argument("--add-nuts", action="store_true")
    parser.add_argument("--no-entity-linking", action="store_true")
    parser.add_argument(
        "--reranker",
        choices=["cross_encoder", "none"],
        default="cross_encoder",
        help="Entity-linking reranker. The default preserves AffilGood's cross-encoder cascade.",
    )
    parser.add_argument("--reranker-model", help="Optional cross-encoder model override.")
    parser.add_argument(
        "--llm-judge",
        nargs="?",
        const=True,
        default=None,
        metavar="MODEL",
        help="Enable listwise LLM disambiguation for low-confidence candidates; optionally provide a model name.",
    )
    parser.add_argument(
        "--llm-threshold",
        type=float,
        default=0.5,
        help="Invoke the optional LLM judge below this entity-linking score.",
    )
    parser.add_argument("--no-normalization", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--no-source-record",
        action="store_true",
        help="Do not include the original JSONL/CSV row under source_record.",
    )
    parser.add_argument(
        "--personal-rules",
        default=None,
        help="Reviewed personal rule JSON; defaults to the rules bundled with this skill.",
    )
    parser.add_argument(
        "--no-personal-rules",
        action="store_true",
        help="Disable the reviewed personal post-processing rules.",
    )
    parser.add_argument(
        "--institution-table",
        default=None,
        help="Primary exact institution reference CSV; defaults to institution_raw.csv from the AffilGood project or bundled skill snapshot.",
    )
    parser.add_argument(
        "--no-institution-table",
        action="store_true",
        help="Disable institution_raw.csv reference matching.",
    )
    return parser.parse_args()


def detect_format(path: Path, requested: str) -> str:
    if requested != "auto":
        return requested
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix in {".txt", ".list"}:
        return "txt"
    return "jsonl"


def read_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                yield {
                    "record_id": str(line_no),
                    "_read_error": f"invalid JSON on line {line_no}: {exc}",
                    "_raw_line": stripped,
                }
                continue
            if not isinstance(row, dict):
                yield {
                    "record_id": str(line_no),
                    "_read_error": f"line {line_no} is not a JSON object",
                    "_raw_line": stripped,
                }
                continue
            row.setdefault("_line_no", line_no)
            yield row


def read_csv(path: Path) -> Iterator[Dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for line_no, row in enumerate(reader, start=2):
            normalized = dict(row)
            normalized.setdefault("_line_no", line_no)
            yield normalized


def read_txt(path: Path) -> Iterator[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            affiliation = line.strip()
            if affiliation:
                yield {
                    "record_id": str(line_no),
                    "affiliation": affiliation,
                    "_line_no": line_no,
                }


def iter_rows(path: Path, input_format: str) -> Iterator[Dict[str, Any]]:
    if input_format == "jsonl":
        yield from read_jsonl(path)
    elif input_format == "csv":
        yield from read_csv(path)
    elif input_format == "txt":
        yield from read_txt(path)
    else:
        raise ValueError(f"Unsupported input format: {input_format}")


def source_id(row: Dict[str, Any], id_field: str, fallback: int) -> str:
    value = row.get(id_field)
    if value is None or value == "":
        value = row.get("record_id")
    if value is None or value == "":
        value = row.get("_line_no")
    if value is None or value == "":
        value = fallback
    return str(value)


def build_output(
    row: Dict[str, Any],
    *,
    record_id: str,
    affiliation: str,
    status: str,
    affilgood: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    include_source_record: bool = True,
) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "record_id": record_id,
        "affiliation": affiliation,
        "status": status,
    }
    if affilgood is not None:
        item["affilgood"] = affilgood
    if error:
        item["error"] = error
    if include_source_record:
        item["source_record"] = {
            key: value for key, value in row.items() if not key.startswith("_")
        }
    return item


def chunks(items: Iterable[Dict[str, Any]], size: int) -> Iterator[List[Dict[str, Any]]]:
    batch: List[Dict[str, Any]] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def import_affilgood(project_path: Optional[str]) -> Any:
    if project_path:
        sys.path.insert(0, str(Path(project_path).expanduser().resolve()))
    from affilgood import AffilGood
    from affilgood.data_manager import ensure_data

    return AffilGood, ensure_data


def build_linking_config(args: argparse.Namespace, data_dir: Path) -> Dict[str, Any]:
    config: Dict[str, Any] = {
        "data_dir": str(data_dir),
        "reranker": None if args.reranker == "none" else args.reranker,
        "llm_threshold": args.llm_threshold,
    }
    if args.reranker_model:
        config["reranker_model"] = args.reranker_model
    if args.llm_judge is not None:
        config["llm_judge"] = args.llm_judge
    return config


def check_runtime_dependencies(args: argparse.Namespace) -> None:
    required = ["torch", "transformers", "datasets"]
    if not args.no_entity_linking:
        required.extend(["sentence_transformers", "faiss"])
    missing = []
    for module_name in required:
        try:
            __import__(module_name)
        except ImportError:
            missing.append(module_name)
    if missing:
        raise RuntimeError(
            "AffilGood ML dependencies are missing: " + ", ".join(missing)
        )


def validate_affilgood_runtime(ag: Any, args: argparse.Namespace) -> None:
    pipeline = getattr(ag, "_pipeline", None)
    ner = getattr(pipeline, "ner", None)
    failures = []
    if not getattr(ner, "_available", False):
        failures.append("NER model unavailable")
    if not args.no_entity_linking and getattr(pipeline, "entity_linker", None) is None:
        failures.append("entity linker unavailable")
    if not args.no_normalization and getattr(pipeline, "geocoder", None) is None:
        failures.append("geocoder unavailable")
    if failures:
        raise RuntimeError("AffilGood runtime validation failed: " + "; ".join(failures))


def make_affilgood(args: argparse.Namespace) -> Any:
    AffilGood, ensure_data = import_affilgood(args.affilgood_path)
    data_dir = Path(args.data_dir).expanduser() if args.data_dir else None
    resolved_data_dir = ensure_data(data_dir=data_dir)
    os.environ["AFFILGOOD_DATA_DIR"] = str(resolved_data_dir)

    ag = AffilGood(
        device=args.device,
        batch_size=args.batch_size,
        output_format=args.output_format,
        enable_language_detect=args.enable_language_detect,
        enable_normalization=not args.no_normalization,
        enable_entity_linking=not args.no_entity_linking,
        add_nuts=args.add_nuts,
        verbose=args.verbose,
        linking_config=build_linking_config(args, resolved_data_dir),
        normalization_config={"data_dir": str(resolved_data_dir)},
    )
    validate_affilgood_runtime(ag, args)
    return ag


def write_jsonl(handle: Any, item: Dict[str, Any]) -> None:
    handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")


def process_file(ag: Any, args: argparse.Namespace, input_path: Path, output_path: Path) -> int:
    input_format = detect_format(input_path, args.input_format)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")
    same_path = input_path.resolve() == output_path.resolve()
    if not same_path and output_path.exists():
        same_path = os.path.samefile(input_path, output_path)
    if same_path:
        raise ValueError("Input and output must refer to different files")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with output_path.open("w", encoding="utf-8") as output_handle:
        for batch in chunks(iter_rows(input_path, input_format), args.batch_size):
            process_batch(
                ag,
                batch,
                args=args,
                output_handle=output_handle,
                row_offset=total + 1,
            )
            total += len(batch)

    if args.verbose:
        print(f"Wrote {total} input rows to {output_path}", file=sys.stderr)
    return total


def process_batch(
    ag: Any,
    batch: List[Dict[str, Any]],
    *,
    args: argparse.Namespace,
    output_handle: Any,
    row_offset: int,
) -> None:
    from personal_rules import apply_personal_rules
    from institution_reference import apply_institution_reference

    def finalize(result: Any, row: Dict[str, Any]) -> Any:
        if args.no_personal_rules:
            personal = result
        else:
            personal = apply_personal_rules(result, args.personal_rules_data, row)
        if args.no_institution_table:
            return personal
        return apply_institution_reference(personal, args.institution_table_data)

    prepared: List[Dict[str, Any]] = []
    for index, row in enumerate(batch, start=row_offset):
        record_id = source_id(row, args.id_field, index)

        if "_read_error" in row:
            write_jsonl(
                output_handle,
                build_output(
                    row,
                    record_id=record_id,
                    affiliation=str(row.get(args.affiliation_field, "")),
                    status="error",
                    error=str(row["_read_error"]),
                    include_source_record=not args.no_source_record,
                ),
            )
            continue

        raw_affiliation = row.get(args.affiliation_field)
        affiliation = "" if raw_affiliation is None else str(raw_affiliation).strip()
        if not affiliation:
            write_jsonl(
                output_handle,
                build_output(
                    row,
                    record_id=record_id,
                    affiliation=affiliation,
                    status="skipped",
                    error="empty affiliation",
                    include_source_record=not args.no_source_record,
                ),
            )
            continue

        prepared.append(
            {
                "row": row,
                "record_id": record_id,
                "affiliation": affiliation,
            }
        )

    if not prepared:
        return

    texts = [item["affiliation"] for item in prepared]
    try:
        results = ag.process(
            texts,
            return_debug=args.return_debug,
            batch_size=args.batch_size,
        )
    except Exception:
        # Fall back to row-level processing so one problematic affiliation does not
        # hide all successful rows in the batch.
        for item in prepared:
            try:
                result = ag.process(
                    item["affiliation"],
                    return_debug=args.return_debug,
                    batch_size=args.batch_size,
                )
                write_jsonl(
                    output_handle,
                    build_output(
                        item["row"],
                        record_id=item["record_id"],
                        affiliation=item["affiliation"],
                        status="ok",
                        affilgood=finalize(result, item["row"]),
                        include_source_record=not args.no_source_record,
                    ),
                )
            except Exception as exc:
                write_jsonl(
                    output_handle,
                    build_output(
                        item["row"],
                        record_id=item["record_id"],
                        affiliation=item["affiliation"],
                        status="error",
                        error=f"{type(exc).__name__}: {exc}",
                        include_source_record=not args.no_source_record,
                    ),
                )
        return

    for item, result in zip(prepared, results):
        write_jsonl(
            output_handle,
            build_output(
                item["row"],
                record_id=item["record_id"],
                affiliation=item["affiliation"],
                status="ok",
                affilgood=finalize(result, item["row"]),
                include_source_record=not args.no_source_record,
            ),
        )


def main() -> int:
    args = parse_args()

    if not args.no_personal_rules:
        from personal_rules import load_rules

        args.personal_rules_data = load_rules(args.personal_rules)
    else:
        args.personal_rules_data = {}
    if not args.no_institution_table:
        from institution_reference import load_institution_table

        args.institution_table_data = load_institution_table(args.institution_table, args.affilgood_path)
    else:
        args.institution_table_data = {"path": "disabled", "index": {}}

    if args.batch_size < 1:
        raise SystemExit("--batch-size must be >= 1")

    if args.check_setup:
        check_runtime_dependencies(args)
        _AffilGood, ensure_data = import_affilgood(args.affilgood_path)
        data_dir = Path(args.data_dir).expanduser() if args.data_dir else None
        resolved_data_dir = ensure_data(data_dir=data_dir)
        print(f"AffilGood import and ML dependencies ok; data ready at {resolved_data_dir}")
        return 0

    if args.job and (args.input or args.output):
        raise SystemExit("Use either --job or --input/--output, not both")
    if not args.job and (not args.input or not args.output):
        raise SystemExit("--input and --output are required unless --job or --check-setup is used")

    jobs = (
        [(Path(source).expanduser(), Path(destination).expanduser()) for source, destination in args.job]
        if args.job
        else [(Path(args.input).expanduser(), Path(args.output).expanduser())]
    )
    missing = [str(input_path) for input_path, _ in jobs if not input_path.exists()]
    if missing:
        raise SystemExit("Input file does not exist: " + ", ".join(missing))

    ag = make_affilgood(args)
    for input_path, output_path in jobs:
        process_file(ag, args, input_path, output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
