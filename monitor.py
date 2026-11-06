"""
monitor.py —— 刷课进度面板

零依赖（只用标准库），启动后浏览器打开 http://127.0.0.1:8765 即可。
实时显示：运行状态、当前课程、已看/总视频数、错误统计、最近日志。

用法：
    python monitor.py            # 默认 8765 端口
    python monitor.py -p 9000    # 自定义端口
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOG_DIR = BASE / "logs"
INFO_LOG = LOG_DIR / "info.log"
ERROR_LOG = LOG_DIR / "error.log"
WATCHDOG_LOG = LOG_DIR / "watchdog.log"

VIDEO_LINE = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+:\s+(.*)")
COURSE_LINE = re.compile(r"Fucking (?:Zhidao|Hike) course\s+(\S+)")
COUNT_LINE = re.compile(r"(\d+) lessons,\s*(\d+) videos")
WATCHED_LINE = re.compile(r"Video (.+?) already watched")
FINISH_LINE = re.compile(r"Video (.+?) finished")
IDLE_HINT = re.compile(r"Fucking lesson|Fucking video|进度|Submitting|save")


def tail_lines(path: Path, limit: int = 400) -> list[str]:
    if not path.exists():
        return []
    try:
        data = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return data[-limit:]


def file_age_minutes(path: Path) -> float | None:
    if not path.exists():
        return None
    return (time.time() - path.stat().st_mtime) / 60


def build_status() -> dict:
    info = tail_lines(INFO_LOG, 800)
    err = tail_lines(ERROR_LOG, 200)
    wd = tail_lines(WATCHDOG_LOG, 30)

    watched: list[str] = []
    current_course = ""
    total_videos = 0
    lessons = 0

    for line in info:
        m = VIDEO_LINE.match(line)
        if not m:
            continue
        msg = m.group(2).strip()

        c = COURSE_LINE.search(msg)
        if c:
            current_course = c.group(1)
            continue

        n = COUNT_LINE.search(msg)
        if n:
            lessons = int(n.group(1))
            total_videos = int(n.group(2))
            continue

        w = WATCHED_LINE.search(msg)
        if w:
            name = w.group(1).strip()
            if name not in watched:
                watched.append(name)

    recent = []
    for line in info[-25:]:
        m = VIDEO_LINE.match(line)
        if m:
            recent.append({"time": m.group(1)[11:], "msg": m.group(2).strip()})

    errors = [l for l in err if re.match(r"^\d{4}-\d{2}-\d{2}", l)]
    risk_hits = sum(1 for l in err if "疑是多窗口" in l)
    captcha_hits = sum(1 for l in err if "captcha required" in l)
    dns_hits = sum(1 for l in err if "getaddrinfo failed" in l)

    age = file_age_minutes(INFO_LOG)
    if age is None:
        state, state_text = "unknown", "未启动"
    elif age < 5:
        state, state_text = "running", "运行中"
    elif age < 30:
        state, state_text = "playing", "播放中（进度提交间隔较长）"
    else:
        state, state_text = "stalled", f"可能停滞（{age:.0f} 分钟无更新）"

    done = len(watched)
    percent = round(done / total_videos * 100, 1) if total_videos else 0.0

    return {
        "state": state,
        "state_text": state_text,
        "age_minutes": None if age is None else round(age, 1),
        "course": current_course[:16] if current_course else "—",
        "lessons": lessons,
        "total_videos": total_videos,
        "watched_count": done,
        "percent": percent,
        "watched": watched[-12:],
        "recent": recent[-14:],
        "error_count": len(errors),
        "risk_hits": risk_hits,
        "captcha_hits": captcha_hits,
        "dns_hits": dns_hits,
        "watchdog": [l.split(":  ", 1)[-1] for l in wd[-6:]],
        "server_time": datetime.now().strftime("%H:%M:%S"),
    }


PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>知道刷课脚本 · 进度面板</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
    background: #0f1419; color: #e6edf3; padding: 24px;
  }
  .wrap { max-width: 1080px; margin: 0 auto; }
  h1 { font-size: 19px; font-weight: 600; margin-bottom: 4px; }
  .sub { color: #7d8590; font-size: 12px; margin-bottom: 20px; }
  .grid { display: grid; grid-template-columns: 260px 1fr; gap: 16px; }
  .card { background: #161b22; border: 1px solid #21262d; border-radius: 10px; padding: 18px; }
  .row { display: flex; justify-content: space-between; align-items: baseline; padding: 7px 0; border-bottom: 1px solid #21262d; font-size: 13px; }
  .row:last-child { border-bottom: none; }
  .row span:first-child { color: #7d8590; }
  .badge { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 12px; font-weight: 500; }
  .b-running { background: #12351f; color: #3fb950; }
  .b-playing { background: #2b2611; color: #d29922; }
  .b-stalled { background: #3d1a1a; color: #f85149; }
  .b-unknown { background: #21262d; color: #7d8590; }
  .num { font-size: 26px; font-weight: 600; }
  .muted { color: #7d8590; font-size: 12px; }
  .log { font-family: ui-monospace, Consolas, monospace; font-size: 12px; line-height: 1.85; }
  .log div { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .t { color: #484f58; margin-right: 8px; }
  .pie-wrap { display: flex; align-items: center; gap: 16px; margin-top: 6px; }
  .legend { font-size: 12px; line-height: 1.9; }
  .dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 6px; }
  .warn { color: #d29922; }
  .err { color: #f85149; }
</style>
</head>
<body>
<div class="wrap">
  <h1>知道刷课脚本 · 进度面板</h1>
  <div class="sub">每 3 秒自动刷新 · <span id="clock">--:--:--</span></div>

  <div class="grid">
    <div>
      <div class="card" style="margin-bottom:16px">
        <div style="margin-bottom:12px"><span id="state" class="badge b-unknown">加载中</span></div>
        <div class="pie-wrap">
          <svg width="96" height="96" viewBox="0 0 42 42">
            <circle cx="21" cy="21" r="15.9" fill="none" stroke="#21262d" stroke-width="6"></circle>
            <circle id="pie" cx="21" cy="21" r="15.9" fill="none" stroke="#3fb950" stroke-width="6"
                    stroke-dasharray="0 100" stroke-dashoffset="25" stroke-linecap="round"></circle>
          </svg>
          <div class="legend">
            <div><span class="dot" style="background:#3fb950"></span>已看完 <b id="watchedCount">0</b></div>
            <div><span class="dot" style="background:#21262d"></span>未完成 <b id="leftCount">0</b></div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="row"><span>当前课程</span><span id="course">—</span></div>
        <div class="row"><span>章节 / 视频</span><span><b id="lessons">0</b> / <b id="total">0</b></span></div>
        <div class="row"><span>日志新鲜度</span><span id="age">—</span></div>
        <div class="row"><span>错误条数</span><span id="errs">0</span></div>
        <div class="row"><span>多窗口风控</span><span id="risk">0</span></div>
        <div class="row"><span>验证码</span><span id="captcha">0</span></div>
        <div class="row"><span>断网失败</span><span id="dns">0</span></div>
      </div>
    </div>

    <div>
      <div class="card" style="margin-bottom:16px">
        <div style="font-size:13px;color:#7d8590;margin-bottom:10px">最近日志</div>
        <div class="log" id="recent"></div>
      </div>
      <div class="card">
        <div style="font-size:13px;color:#7d8590;margin-bottom:10px">看护记录</div>
        <div class="log" id="watchdog" style="color:#8b949e"></div>
      </div>
    </div>
  </div>
</div>

<script>
function setText(id, v) { document.getElementById(id).textContent = v; }

function refresh() {
  fetch('/api/status').then(r => r.json()).then(d => {
    setText('clock', d.server_time);
    const badge = document.getElementById('state');
    badge.textContent = d.state_text;
    badge.className = 'badge b-' + d.state;

    setText('course', d.course);
    setText('lessons', d.lessons);
    setText('total', d.total_videos);
    setText('watchedCount', d.watched_count);
    setText('leftCount', Math.max(d.total_videos - d.watched_count, 0));
    setText('age', d.age_minutes === null ? '—' : d.age_minutes + ' 分钟前');

    const errs = document.getElementById('errs');
    errs.textContent = d.error_count;
    errs.className = d.error_count > 0 ? 'err' : '';
    const risk = document.getElementById('risk');
    risk.textContent = d.risk_hits;
    risk.className = d.risk_hits > 0 ? 'warn' : '';
    const cap = document.getElementById('captcha');
    cap.textContent = d.captcha_hits;
    cap.className = d.captcha_hits > 0 ? 'err' : '';
    const dns = document.getElementById('dns');
    dns.textContent = d.dns_hits;
    dns.className = d.dns_hits > 0 ? 'warn' : '';

    const pie = document.getElementById('pie');
    const pct = Math.max(0, Math.min(100, d.percent));
    pie.setAttribute('stroke-dasharray', pct + ' ' + (100 - pct));

    document.getElementById('recent').innerHTML = d.recent.map(r =>
      '<div><span class="t">' + r.time + '</span>' + r.msg + '</div>').join('') || '<div class="muted">暂无日志</div>';

    document.getElementById('watchdog').innerHTML = d.watchdog.map(w =>
      '<div>' + w + '</div>').join('') || '<div class="muted">暂无看护记录</div>';
  }).catch(() => setText('state', '连接失败'));
}
refresh();
setInterval(refresh, 3000);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 静默，不刷屏
        pass

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            if self.path.startswith("/api/status"):
                payload = json.dumps(build_status(), ensure_ascii=False).encode("utf-8")
                self._send(200, payload, "application/json; charset=utf-8")
            else:
                self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        except Exception as exc:  # 面板自身不能崩
            self._send(500, str(exc).encode("utf-8"), "text/plain; charset=utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="知道刷课脚本进度面板")
    parser.add_argument("-p", "--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"进度面板已启动： http://{args.host}:{args.port}")
    print("按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
