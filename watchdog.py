"""
watchdog.py —— 刷课进程看护

替代原来 Windows 专用的 ps1 看护脚本，跨平台可用。

功能：
  - 定时检查刷课进程是否存活，挂了自动重启（当日最多 3 次，防疯狂循环）
  - 断网时跳过重启，等网络恢复再拉起
  - 日志长时间无更新判定卡死，自动重启
  - 扫描 error.log，把验证码 / 多窗口风控 / DNS 失败记录到 watchdog.log

用法：
    python watchdog.py            # 常驻循环，默认每 10 分钟检查一次
    python watchdog.py --once     # 检查一次就退出（配合系统计划任务用）
    python watchdog.py -i 5       # 每 5 分钟检查一次
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from logger import logger  # noqa: E402

LOG_DIR = BASE / "logs"
INFO_LOG = LOG_DIR / "info.log"
ERROR_LOG = LOG_DIR / "error.log"
WD_LOG = LOG_DIR / "watchdog.log"
STDOUT_LOG = LOG_DIR / "stdout.log"
STDERR_LOG = LOG_DIR / "stderr.log"

MAX_RESTARTS_PER_DAY = 3
STALL_MINUTES = 90


def log(msg: str) -> None:
    line = f"{datetime.now().strftime('%m-%d %H:%M:%S')}  {msg}"
    print(line)
    WD_LOG.parent.mkdir(exist_ok=True)
    with open(WD_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def find_process() -> list[dict]:
    """找到刷课进程。优先 psutil，退化到系统命令。"""
    procs: list[dict] = []
    try:
        import psutil  # type: ignore

        for p in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmd = " ".join(p.info.get("cmdline") or [])
                if "main.py" in cmd and "fuckZHS" in cmd.replace("\\", "/"):
                    procs.append({"pid": p.info["pid"]})
            except Exception:
                continue
        return procs
    except ImportError:
        pass

    if sys.platform == "win32":
        try:
            out = subprocess.run(
                ["wmic", "process", "where", "name='python.exe'", "get", "ProcessId,CommandLine"],
                capture_output=True, text=True, timeout=15,
            ).stdout
            for line in out.splitlines():
                if "main.py" in line and "fuckZHS" in line:
                    procs.append({"pid": int(line.strip().split()[-1])})
        except Exception:
            pass
    else:
        try:
            out = subprocess.run(["pgrep", "-f", "main.py"], capture_output=True, text=True, timeout=15).stdout
            procs = [{"pid": int(x)} for x in out.split()]
        except Exception:
            pass
    return procs


def network_ok() -> bool:
    try:
        socket.create_connection(("studyservice-api.zhihuishu.com", 443), timeout=5).close()
        return True
    except OSError:
        return False


def start_process() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    python = sys.executable
    out = open(STDOUT_LOG, "a", encoding="utf-8")
    err = open(STDERR_LOG, "a", encoding="utf-8")
    subprocess.Popen(
        [python, str(BASE / "main.py")],
        cwd=str(BASE), stdout=out, stderr=err,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if sys.platform == "win32" else 0,
    )


def check_once() -> None:
    procs = find_process()

    if not procs:
        if not network_ok():
            log("进程已退出，但网络不通 -> 本轮跳过，等网络恢复")
            return

        today = datetime.now().strftime("%m-%d")
        restarts = 0
        if WD_LOG.exists():
            restarts = sum(
                1 for line in WD_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
                if line.startswith(today) and "自动重启" in line
            )
        if restarts >= MAX_RESTARTS_PER_DAY:
            log("今日已自动重启 3 次，暂停自动重启，需人工检查")
            return

        start_process()
        log("检测到进程不在运行 -> 已自动重启")
        return

    # 进程存活 -> 健康检查
    signals = []
    if ERROR_LOG.exists():
        try:
            tail = ERROR_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-60:]
            text = "\n".join(tail)
            if "captcha required" in text:
                signals.append("CAPTCHA")
            if "疑是多窗口观看" in text:
                signals.append("MULTI_WINDOW")
            if "getaddrinfo failed" in text:
                signals.append("DNS")
        except OSError:
            pass
    if signals:
        log("异常信号: " + ",".join(signals))

    idle = 0
    if INFO_LOG.exists():
        idle = (time.time() - INFO_LOG.stat().st_mtime) / 60
        idle = int(idle)

    if idle >= STALL_MINUTES:
        log(f"日志已 {idle} 分钟无更新，判定卡住 -> 重启进程")
        import os
        for p in procs:
            try:
                os.kill(p["pid"], 9)
            except OSError:
                pass
        time.sleep(3)
        start_process()
        log("已自动重启（停滞恢复）")
    else:
        log(f"正常 pid={procs[0]['pid']} 日志空闲={idle} 分钟")


def main() -> None:
    parser = argparse.ArgumentParser(description="刷课进程看护")
    parser.add_argument("--once", action="store_true", help="只检查一次")
    parser.add_argument("-i", "--interval", type=int, default=10, help="检查间隔（分钟）")
    args = parser.parse_args()

    if args.once:
        check_once()
        return

    log(f"看护启动，每 {args.interval} 分钟检查一次")
    while True:
        try:
            check_once()
        except Exception as exc:
            log(f"看护自身出错（不影响刷课）：{exc}")
        time.sleep(args.interval * 60)


if __name__ == "__main__":
    main()
