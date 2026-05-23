from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
UNIFIED_RUNNER = ROOT / "conference-paper-extraction" / "scripts" / "run_unified_pipeline.py"


def translate_args(argv: list[str]) -> list[str]:
    translated: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--conference" and i + 1 < len(argv) and argv[i + 1] == "all":
            translated.extend(["--group", "top3_crypto"])
            i += 2
            continue
        translated.append(arg)
        i += 1
    return translated


def main() -> int:
    argv = translate_args(sys.argv[1:])
    command = ["python3", str(UNIFIED_RUNNER), *argv]
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
