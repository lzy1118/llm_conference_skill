import os
import shutil
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

import fcntl

from author_metadata.config import GROBID_HOME, GROBID_LIB_DIR, PROJECT_ROOT

GROBID_LOCK_PATH = Path(
    os.environ.get(
        "GROBID_LOCK_PATH",
        Path(os.environ.get("TMPDIR", "/tmp")) / "conference-grobid-extract-metadata.lock",
    )
)
GROBID_LOG_DIR = Path(
    os.environ.get(
        "GROBID_RUN_LOG_DIR",
        Path(os.environ.get("TMPDIR", "/tmp")) / "conference-grobid-extract-metadata",
    )
)
GROBID_LOCK_TIMEOUT = float(os.environ.get("GROBID_LOCK_TIMEOUT", "86400"))


def reset_directory(path):
    os.makedirs(path, exist_ok=True)
    for name in os.listdir(path):
        full_path = os.path.join(path, name)
        if os.path.isdir(full_path) and not os.path.islink(full_path):
            shutil.rmtree(full_path)
        else:
            os.unlink(full_path)


def find_grobid_onejar():
    if not GROBID_LIB_DIR.exists():
        return ""
    jars = sorted(GROBID_LIB_DIR.glob("*-onejar.jar"))
    return str(jars[0]) if jars else ""


@contextmanager
def grobid_process_lock():
    """Serialize access to the shared GROBID home/native model runtime."""
    GROBID_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_file = GROBID_LOCK_PATH.open("a+", encoding="utf-8")
    started = time.monotonic()
    try:
        while True:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() - started >= GROBID_LOCK_TIMEOUT:
                    raise TimeoutError(
                        f"等待 GROBID 锁超时（{GROBID_LOCK_TIMEOUT:.0f}s）：{GROBID_LOCK_PATH}"
                    )
                time.sleep(1)
        yield
    finally:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()


def run_grobid_header_batch(pdf_stage_dir, xml_dir):
    onejar = find_grobid_onejar()
    if not onejar:
        raise FileNotFoundError("未找到 grobid-core one-jar，请先构建 batch 运行包。")
    if not GROBID_HOME.exists():
        raise FileNotFoundError(f"GROBID home 不存在：{GROBID_HOME}")

    cmd = [
        "java",
        "-jar",
        onejar,
        "-gH",
        str(GROBID_HOME),
        "-dIn",
        pdf_stage_dir,
        "-dOut",
        xml_dir,
        "-exe",
        "processHeader",
    ]
    GROBID_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_name = f"batch-{Path(xml_dir).parent.name}-{int(time.time())}.log"
    log_path = GROBID_LOG_DIR / log_name

    print(f"  ⏳ 等待 GROBID 运行锁: {GROBID_LOCK_PATH}")
    with grobid_process_lock():
        print(f"  ▶ GROBID batch 开始，日志: {log_path}")
        started = time.monotonic()
        with log_path.open("w", encoding="utf-8") as log_file:
            log_file.write("$ " + " ".join(cmd) + "\n\n")
            log_file.flush()
            result = subprocess.run(
                cmd,
                check=False,
                cwd=str(PROJECT_ROOT),
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
        elapsed = time.monotonic() - started
        if result.returncode:
            raise subprocess.CalledProcessError(
                result.returncode,
                cmd,
                output=f"GROBID 日志: {log_path}",
            )
        print(f"  ✓ GROBID batch 完成，耗时 {elapsed / 60:.1f} 分钟")
