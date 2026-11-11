"""exam/server.py —— 本地答题服务

架构：
    浏览器控制台脚本(fill_auto.js) --POST /answer--> 本服务 --> 题库缓存(命中)
                                                          --> 大模型(未命中且有key)

接口：
    GET  /health   -> {"ok": true, "llm": "deepseek"|"none", "bank": 题库条数}
    POST /answer   -> 请求体 {"questions": [{"no":1,"type":"多选题","question":"...","options":["A. xx",...]}]}
                      返回 {"answers": {"1": "ABC", ...}, "from_bank": {"1": true}, "llm_used": false}

题库：data/question_bank.json，键 = 题干 md5，值 = {"answer": "ABC", "question": "...", "source": "..."}
运行：python exam/server.py  （默认端口 8766）
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

BANK_PATH = BASE / "data" / "question_bank.json"
PORT = 8766


# ---------------------------------------------------------------- 题库
def load_bank() -> dict:
    try:
        return json.loads(BANK_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_bank(bank: dict) -> None:
    BANK_PATH.parent.mkdir(parents=True, exist_ok=True)
    BANK_PATH.write_text(
        json.dumps(bank, ensure_ascii=False, indent=2), encoding="utf-8")


def qkey(question: str) -> str:
    """题干归一化后取 md5，去掉标点/空白差异，提高命中率"""
    norm = re.sub(r"[\s，。：:；;？?（）()【】\[\]\"'、.]", "", question or "")
    return hashlib.md5(norm.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- 大模型
def get_provider():
    """读 config.json 里的 ai.openai 配置，没配 key 返回 None"""
    try:
        conf = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
        ai = conf.get("ai", {})
        if not ai.get("enabled"):
            return None
        from ai_provider import create_provider
        return create_provider(ai.get("openai", {}), {})
    except Exception:
        return None


def ask_llm(provider, q: dict) -> str | None:
    """单题问大模型，返回选项字母串；失败返回 None"""
    opts = "\n".join(q.get("options", []))
    qtype = q.get("type", "")
    prompt = (
        f"你是答题助手。下面是一道{qtype or '选择题'}，请只输出正确选项的字母"
        f"（多选连写如 ABC，判断题输出 对/错），不要任何解释。\n\n"
        f"题目：{q.get('question','')}\n{opts}\n\n"
        f"按格式输出：```answer\n[\"A\"]\n```"
    )
    try:
        ids = provider.generateAnswer(prompt)  # 返回选项序号 [1,2,3]
        return "".join(chr(int(i) + 64) for i in ids if 1 <= int(i) <= 26) or None
    except Exception:
        return None


# ---------------------------------------------------------------- 题面解析（整页文本 -> 题目列表）
NUM_HEAD = re.compile(r"^\s*(\d{1,2})\s*[.、．)）]\s*(.+)$")
TYPE_HINT = re.compile(r"【(单选题|多选题|判断题|填空题)】|（(单选题|多选题|判断题)）")
OPT_HEAD = re.compile(r"^\s*([A-H])\s*[.、．)）]\s*(.+)$")
JUDGE_OPTS = {"对", "错", "正确", "错误", "是", "否"}


def parse_page(text: str) -> list[dict]:
    """把整页 innerText 解析成题目列表（尽力而为）"""
    lines = [unquote(l).strip() for l in text.splitlines()]
    questions: list[dict] = []
    cur: dict | None = None
    for line in lines:
        if not line:
            continue
        om = OPT_HEAD.match(line)
        if om and cur is not None:
            cur["options"].append(line)
            continue
        tm = TYPE_HINT.search(line)
        nm = NUM_HEAD.match(line)
        if nm:
            # 新题开始（题号 + 题干在同一行，可能带【多选题】）
            qtype = ""
            if tm:
                qtype = tm.group(1) or tm.group(2) or ""
            stem = re.sub(TYPE_HINT, "", nm.group(2)).strip()
            cur = {"no": int(nm.group(1)), "type": qtype,
                   "question": stem, "options": []}
            questions.append(cur)
            continue
        # 判断题常见形态：题干行后跟 对/错 两行
        if line in JUDGE_OPTS and cur is not None and not cur["options"]:
            cur["options"].append(line)
            continue
        if cur is not None and not cur["options"]:
            cur["question"] += line  # 题干续行
    return [q for q in questions if q["question"]]


# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, obj: dict, code: int = 200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/health"):
            provider = get_provider()
            name = getattr(provider, "model_name", None) or (
                "configured" if provider else "none")
            self._json({"ok": True, "llm": name,
                        "bank": len(load_bank())})
        else:
            self._json({"ok": False, "error": "unknown path"}, 404)

    def do_POST(self):
        if not self.path.startswith("/answer"):
            self._json({"ok": False, "error": "unknown path"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as e:
            self._json({"ok": False, "error": f"bad json: {e}"}, 400)
            return

        questions = payload.get("questions") or []
        if not questions and payload.get("page_text"):
            questions = parse_page(payload["page_text"])

        bank = load_bank()
        provider = get_provider()
        answers: dict = {}
        from_bank: dict = {}
        bank_new: list = []

        for q in questions:
            no = str(q.get("no", len(answers) + 1))
            key = qkey(q.get("question", ""))
            hit = bank.get(key)
            if hit:
                answers[no] = hit["answer"]
                from_bank[no] = True
                continue
            if provider:
                ans = ask_llm(provider, q)
                if ans:
                    answers[no] = ans
                    bank_new.append({"key": key, "answer": ans,
                                     "question": q.get("question", "")[:120]})
                    continue
            answers[no] = ""
        if bank_new:
            for item in bank_new:
                bank[item["key"]] = {"answer": item["answer"],
                                     "question": item["question"],
                                     "source": "llm"}
            save_bank(bank)

        self._json({"ok": True, "answers": answers,
                    "from_bank": from_bank,
                    "llm_used": bool(provider),
                    "parsed": len(questions)})


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    provider = get_provider()
    name = getattr(provider, "model_name", None) or (
        "configured" if provider else "未配置(仅题库)")
    print(f"[答题服务] http://127.0.0.1:{PORT}")
    print(f"[答题服务] 大模型: {name} | 题库: {len(load_bank())} 条 | {BANK_PATH}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[答题服务] 已停止")


if __name__ == "__main__":
    main()
