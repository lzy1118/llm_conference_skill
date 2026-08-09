#!/usr/bin/env python3

# 共享抓取核心之上的轻量分发入口。
# 通过会议名同时决定 URL 子集和使用的抓取后端。
import os
from pathlib import Path
import sys

from core import run_ccs_batch, run_dblp_batch, run_sp_batch


CONFERENCE_CONFIG = {
    "asiacrypt": {"kind": "dblp", "summary": "summary_asiacrypt.csv"},
    "crypto": {"kind": "dblp", "summary": "summary_crypto.csv"},
    "eurocrypt": {"kind": "dblp", "summary": "summary_eurocrypt.csv"},
    "ndss": {"kind": "dblp", "summary": "summary_ndss.csv"},
    "usenix_security": {"kind": "dblp", "summary": "summary_usenix_security.csv", "output_venue": "usenix_security"},
    "ieee_s&p": {"kind": "sp", "summary": "summary_ieee_s&p.csv", "output_venue": "ieee_s&p"},
    "ccs": {"kind": "ccs", "summary": "summary_ccs.csv"},
}


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: spider.py <conference> [args...]")
        print("可选 conference: asiacrypt crypto eurocrypt ndss usenix_security ieee_s&p ccs")
        raise SystemExit(1)

    conference = sys.argv[1]
    config = CONFERENCE_CONFIG.get(conference)
    if config is None:
        print(f"不支持的 conference: {conference}")
        print("可选 conference: asiacrypt crypto eurocrypt ndss usenix_security ieee_s&p ccs")
        raise SystemExit(1)

    base = Path(__file__).resolve().parent
    # `urls.txt` 是人工查看用的总列表；旁边的按会议 URL 文件
    # 让统一入口可以保持与具体会议解耦。
    urls_file = base / f"{conference}_urls.txt"
    output_root = Path(
        os.environ.get("CONFERENCE_DOWNLOAD_DIR", base.parent / "download")
    ).expanduser().resolve()
    extra_args = sys.argv[2:]
    default_driver_path = os.environ.get("CHROMEDRIVER_PATH", "")
    default_user_data_dir = os.environ.get("SELENIUM_USER_DATA_DIR", str(base.parent / "selenium_chrome_profile_fresh"))

    if config["kind"] == "dblp":
        sleep = 2.0
        toc_sleep = 8.0
        years: set[str] | None = None
        force = False
        debugger_address = ""
        driver_path = default_driver_path
        index = 0
        while index < len(extra_args):
            arg = extra_args[index]
            if arg == "--sleep":
                sleep = float(extra_args[index + 1])
                index += 2
            elif arg == "--toc-sleep":
                toc_sleep = float(extra_args[index + 1])
                index += 2
            elif arg == "--years":
                years = {item.strip() for item in extra_args[index + 1].split(",") if item.strip()}
                index += 2
            elif arg == "--force":
                force = True
                index += 1
            elif arg == "--debugger-address":
                debugger_address = extra_args[index + 1]
                index += 2
            elif arg == "--driver-path":
                driver_path = extra_args[index + 1]
                index += 2
            else:
                raise SystemExit(f"不支持的参数: {arg}")
        run_dblp_batch(urls_file=urls_file, output_root=output_root, summary_csv=config["summary"], sleep=sleep, toc_sleep=toc_sleep, years=years, force=force, debugger_address=debugger_address, driver_path=driver_path, output_venue=str(config.get("output_venue", "")))
        return

    if config["kind"] == "sp":
        # SP 是这组会议里唯一走 IEEE 的会议。
        driver_path = default_driver_path
        user_data_dir = default_user_data_dir
        profile_directory = ""
        start_year = 0
        start_index = 0
        sleep = 5.0
        toc_sleep = 15.0
        index = 0
        while index < len(extra_args):
            arg = extra_args[index]
            if arg == "--start-year":
                start_year = int(extra_args[index + 1])
                index += 2
            elif arg == "--start-index":
                start_index = int(extra_args[index + 1])
                index += 2
            elif arg == "--sleep":
                sleep = float(extra_args[index + 1])
                index += 2
            elif arg == "--toc-sleep":
                toc_sleep = float(extra_args[index + 1])
                index += 2
            elif arg == "--driver-path":
                driver_path = extra_args[index + 1]
                index += 2
            elif arg == "--user-data-dir":
                user_data_dir = extra_args[index + 1]
                index += 2
            elif arg == "--profile-directory":
                profile_directory = extra_args[index + 1]
                index += 2
            else:
                raise SystemExit(f"不支持的参数: {arg}")
        run_sp_batch(
            urls_file=urls_file,
            output_root=output_root,
            summary_csv=config["summary"],
            driver_path=driver_path,
            user_data_dir=user_data_dir,
            profile_directory=profile_directory,
            start_year=start_year,
            start_index=start_index,
            sleep=sleep,
            toc_sleep=toc_sleep,
            output_venue=str(config.get("output_venue", "")),
        )
        return

    if config["kind"] == "ccs":
        # CCS 走 ACM，并使用 ACM 浏览器流程。
        driver_path = default_driver_path
        user_data_dir = default_user_data_dir
        sleep = 8.0
        toc_sleep = 20.0
        years: set[str] | None = None
        index = 0
        while index < len(extra_args):
            arg = extra_args[index]
            if arg == "--years":
                years = {item.strip() for item in extra_args[index + 1].split(",") if item.strip()}
                index += 2
            elif arg == "--sleep":
                sleep = float(extra_args[index + 1])
                index += 2
            elif arg == "--toc-sleep":
                toc_sleep = float(extra_args[index + 1])
                index += 2
            elif arg == "--driver-path":
                driver_path = extra_args[index + 1]
                index += 2
            elif arg == "--user-data-dir":
                user_data_dir = extra_args[index + 1]
                index += 2
            else:
                raise SystemExit(f"不支持的参数: {arg}")
        run_ccs_batch(
            urls_file=urls_file,
            output_root=output_root,
            summary_csv=config["summary"],
            driver_path=driver_path,
            user_data_dir=user_data_dir,
            sleep=sleep,
            toc_sleep=toc_sleep,
            years=years,
        )
        return


if __name__ == "__main__":
    main()
