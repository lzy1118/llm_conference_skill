import importlib
import os
import re
from pathlib import Path

from author_metadata.config import CONFERENCE_STRATEGY_MODULES, should_skip_input
from author_metadata.exporter import (
    export_abstract_csv,
    export_csv,
    export_json,
    export_review_queue,
    write_index,
)
from author_metadata.artifacts import (
    abstract_csv_row,
    author_csv_rows,
    export_paper_artifacts,
    new_metrics,
    placeholder_author_row,
    review_csv_rows,
    update_metrics,
)
from author_metadata.grobid_runner import reset_directory, run_grobid_header_batch
from author_metadata.metadata_repair import repair_metadata
from author_metadata.pdf_context import extract_title_hint, load_pdf_context
from author_metadata.tei_parser import extract_year, parse_tei


def load_conference_strategy(conference_name):
    # CLI callers commonly use display casing (for example ``CCS``), while
    # the strategy registry uses stable lowercase identifiers.
    key = (conference_name or "").strip().lower()
    module_name = CONFERENCE_STRATEGY_MODULES.get(key)
    if not module_name:
        return None
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        print(f"  ⚠ 无法加载会议策略 {module_name}: {exc}")
        return None


def make_paper_id(file_name, used_ids, slugify_filename):
    base = slugify_filename(file_name)
    candidate = base
    if candidate not in used_ids:
        used_ids.add(candidate)
        return candidate
    digest = __import__("hashlib").md5(file_name.encode("utf-8")).hexdigest()[:8]
    candidate = f"{base}_{digest}"
    used_ids.add(candidate)
    return candidate


def prepare_pdf_stage(pdf_list, paths, slugify_filename):
    staged = []
    skipped = []
    used_ids = set()

    os.makedirs(paths.dataset_dir, exist_ok=True)
    reset_directory(paths.pdf_stage_dir)
    os.makedirs(paths.xml_dir, exist_ok=True)
    os.makedirs(paths.json_dir, exist_ok=True)
    os.makedirs(paths.evidence_dir, exist_ok=True)
    os.makedirs(paths.candidate_dir, exist_ok=True)

    for rel_path, abs_path in sorted(pdf_list):
        file_name = os.path.basename(rel_path)
        if should_skip_input(file_name):
            skipped.append((rel_path, "unsupported_filename"))
            continue

        pdf_context = load_pdf_context(abs_path)
        title_hint = extract_title_hint(pdf_context)
        if title_hint and should_skip_input(title_hint):
            skipped.append((rel_path, "unsupported_title"))
            continue

        paper_id = make_paper_id(rel_path, used_ids, slugify_filename)
        staged_path = os.path.join(paths.pdf_stage_dir, paper_id + ".pdf")
        try:
            os.symlink(abs_path, staged_path)
        except OSError:
            import shutil
            shutil.copy2(abs_path, staged_path)

        staged.append({
            "paper_id": paper_id,
            "source_file": rel_path,
            "source_path": abs_path,
            "stage_pdf": staged_path,
            "title_hint": title_hint,
            "pdf_context": pdf_context,
        })
    return staged, skipped


def build_stage_index(staged_pdfs, skipped_pdfs, paths):
    records = []
    for item in staged_pdfs:
        paper_id = item["paper_id"]
        xml_path = os.path.join(paths.xml_dir, paper_id + ".tei.xml")
        json_path = os.path.join(paths.json_dir, paper_id + ".json")
        evidence_path = os.path.join(paths.evidence_dir, paper_id + ".json")
        candidate_path = os.path.join(paths.candidate_dir, paper_id + ".json")
        records.append({
            "paper_id": paper_id,
            "status": "staged",
            "source_file": item["source_file"],
            "source_path": item["source_path"],
            "stage_pdf": item["stage_pdf"],
            "tei_xml": xml_path if os.path.exists(xml_path) else "",
            "metadata_json": json_path,
            "evidence_json": evidence_path,
            "candidate_json": candidate_path,
        })
    for file_name, reason in skipped_pdfs:
        records.append({
            "paper_id": "",
            "status": reason,
            "source_file": file_name,
            "source_path": str(Path(paths.raw_dir) / file_name),
            "stage_pdf": "",
            "tei_xml": "",
            "metadata_json": "",
            "evidence_json": "",
            "candidate_json": "",
        })
    return records


def process_paper(
    pdf_path,
    pdf_context,
    tei_path,
    conference_name="",
    year_hint="",
    strategy=None,
    year_is_authoritative=False,
):
    metadata = parse_tei(tei_path)
    if year_hint and not metadata.get("year"):
        metadata["year"] = year_hint
    metadata = repair_metadata(
        metadata,
        pdf_context,
        strategy=strategy,
        conference_name=conference_name,
        pdf_path=pdf_path,
    )
    if year_is_authoritative and year_hint and metadata.get("year") != year_hint:
        previous_year = metadata.get("year", "")
        metadata["year"] = year_hint
        metadata.setdefault("_extraction", {}).setdefault("decisions", []).append({
            "action": "use_explicit_batch_year",
            "stage": "year_arbitration",
            "field": "year",
            "previous": previous_year,
            "selected": year_hint,
            "source": "cli_explicit_year",
        })
    if not metadata.get("year"):
        metadata["year"] = extract_year(parse_tei(tei_path)["root"], os.path.basename(tei_path))
    return metadata


def run_pipeline(
    pdf_list,
    paths,
    label="",
    conference_name="",
    year_hint="",
    strategy=None,
    slugify_filename=None,
    year_is_authoritative=False,
):
    staged_pdfs, skipped_pdfs = prepare_pdf_stage(pdf_list, paths, slugify_filename)
    if not staged_pdfs:
        raise RuntimeError(f"{label or '默认'}: 未找到可处理的 PDF")

    reset_directory(paths.xml_dir)
    reset_directory(paths.json_dir)
    reset_directory(paths.evidence_dir)
    reset_directory(paths.candidate_dir)
    run_grobid_header_batch(paths.pdf_stage_dir, paths.xml_dir)

    xml_files = sorted(file for file in os.listdir(paths.xml_dir) if file.lower().endswith(".xml"))
    if not xml_files:
        raise RuntimeError(f"{label or '默认'}: GROBID 未生成任何 TEI XML")

    staged_by_id = {item["paper_id"]: item for item in staged_pdfs}
    pdf_year_map = {}
    for _, abs_path in pdf_list:
        filename = os.path.basename(abs_path)
        match = re.search(r"[_\s\-]((?:19|20)\d{2})[_\s\-]", filename)
        if match:
            pdf_year_map[os.path.splitext(filename)[0]] = match.group(1)

    csv_rows = []
    abstract_rows = []
    review_rows = []
    metrics = new_metrics(len(staged_pdfs))
    for file_name in xml_files:
        xml_path = os.path.join(paths.xml_dir, file_name)
        paper_id = os.path.splitext(os.path.splitext(file_name)[0])[0]
        staged_item = staged_by_id.get(paper_id)
        pdf_context = staged_item["pdf_context"] if staged_item else load_pdf_context("")
        try:
            metadata = process_paper(
                staged_item["stage_pdf"] if staged_item else "",
                pdf_context,
                xml_path,
                conference_name=conference_name,
                year_hint=year_hint,
                strategy=strategy,
                year_is_authoritative=year_is_authoritative,
            )
            if not metadata.get("year"):
                xml_base = os.path.splitext(file_name)[0]
                for pdf_base, year in pdf_year_map.items():
                    if pdf_base in xml_base or xml_base in pdf_base:
                        metadata["year"] = year
                        break

            export_paper_artifacts(
                paper_id,
                metadata,
                paths.json_dir,
                paths.evidence_dir,
                paths.candidate_dir,
            )
            extraction = metadata.get("_extraction", {})
            reasons = extraction.get("review_reasons", [])
            update_metrics(metrics, metadata)
            source_file = staged_item["source_file"] if staged_item else ""
            review_rows.extend(review_csv_rows(paper_id, source_file, reasons))
            abstract_rows.append(abstract_csv_row(metadata, conference_name, fallback_title=file_name, fallback_year=year_hint))

            if not metadata["authors"]:
                csv_rows.append(placeholder_author_row(
                    paper_id,
                    metadata.get("year", ""),
                    conference_name,
                    metadata.get("title", "") or file_name,
                    "NO_AUTHORS_EXTRACTED",
                ))
                print(f"  ⚠ {file_name}  (0 authors extracted)")
                continue

            for author in metadata["authors"]:
                csv_rows.extend(author_csv_rows(paper_id, metadata, author, conference_name))
            print(f"  ✓ {file_name}  ({len(metadata['authors'])} authors, year={metadata.get('year') or '?'})")
        except Exception as exc:
            metrics["parse_errors"] += 1
            abstract_rows.append({
                "conference": conference_name,
                "year": year_hint,
                "title": file_name,
                "abstract": "",
            })
            csv_rows.append(placeholder_author_row(
                paper_id, year_hint, conference_name, str(exc), "PARSE_ERROR"
            ))
            print(f"  ✗ {file_name}: {exc}")

    write_index(paths.index_path, paths.skipped_path, build_stage_index(staged_pdfs, skipped_pdfs, paths))
    export_csv(paths.csv_path, csv_rows)
    export_abstract_csv(paths.abstract_csv_path, abstract_rows)
    export_review_queue(paths.review_path, review_rows)
    export_json(paths.metrics_path, metrics)

    tag = f"[{label}] " if label else ""
    print(f"\n{tag}提取完成！")
    print(f"  输入目录：{paths.raw_dir}")
    if skipped_pdfs:
        print(f"  跳过文件数量：{len(skipped_pdfs)}")
    print(f"  纳入处理的 PDF 数量：{len(staged_pdfs)}")
    print(f"  XML 文件数量：{len(xml_files)}")
    print(f"  作者记录数量：{len(csv_rows)}")
    print(f"  CSV 输出：{paths.csv_path}")
    print(f"  摘要 CSV：{paths.abstract_csv_path}")
    print(f"  JSON 输出目录：{paths.json_dir}")
    print(f"  证据输出目录：{paths.evidence_dir}")
    print(f"  候选输出目录：{paths.candidate_dir}")
    print(f"  复核队列：{paths.review_path} ({len(review_rows)} 条原因)")


def scan_pdf_groups(raw_dir):
    raw_path = Path(raw_dir)
    groups = {}
    for pdf_path in sorted(raw_path.rglob("*.pdf")):
        rel = pdf_path.relative_to(raw_path)
        group_key = str(rel.parent) if rel.parent != Path(".") else "."
        groups.setdefault(group_key, []).append((str(rel), str(pdf_path)))
    return groups


def dataset_name_for_group(group_key):
    if group_key == ".":
        return "author_metadata_dataset", "顶层", ""
    year_hint = group_key if re.fullmatch(r"(?:19|20)\d{2}", group_key) else ""
    return f"author_metadata_dataset_{group_key}", group_key, year_hint
