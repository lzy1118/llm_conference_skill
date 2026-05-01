from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.resolve_affiliations_from_sources import extract_frontmatter_from_html, extract_frontmatter_from_pdf


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--kind", choices=["pdf", "html"], default="pdf")
    parser.add_argument("--max-pages", type=int, default=2)
    args = parser.parse_args()

    if args.kind == "pdf":
        text = extract_frontmatter_from_pdf(args.input, max_pages=args.max_pages)
    else:
        text = extract_frontmatter_from_html(args.input.read_text(encoding="utf-8", errors="replace"))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
