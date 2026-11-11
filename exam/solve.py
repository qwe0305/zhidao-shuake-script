"""exam/solve.py —— 剪贴板接力答题（绕过考试页 CSP 对本地请求的限制）

流程：
    ① 浏览器控制台跑 exam/export_questions.js → 题目 JSON 进入剪贴板
    ② 本脚本：读剪贴板 → 题库优先/大模型兜底 → 答案 JSON 写回剪贴板
    ③ 浏览器控制台跑 exam/fill_answers.js → 弹窗里 Ctrl+V 粘贴答案 → 自动填答提交

用法：
    python exam/solve.py            # 从剪贴板读题，答案写回剪贴板
    python exam/solve.py --dry      # 只显示答案，不写剪贴板
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "exam"))

from server import ask_llm, get_provider, load_bank, qkey, save_bank  # noqa: E402


# ---------------------------------------------------------------- 剪贴板（Windows API，免依赖）
def _api():
    global ctypes
    import ctypes

    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    # 64 位下必须显式声明句柄类型，否则被截断成 32 位 int
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    user32.GetClipboardData.restype = ctypes.c_void_p
    user32.GetClipboardData.argtypes = [ctypes.c_uint]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    return user32, kernel32


def _clipboard_text() -> str:
    user32, kernel32 = _api()
    if not user32.OpenClipboard(0):
        return ""
    try:
        handle = user32.GetClipboardData(13)  # CF_UNICODETEXT
        if not handle:
            return ""
        ptr = kernel32.GlobalLock(handle)
        text = ctypes.c_wchar_p(ptr).value if ptr else ""
        kernel32.GlobalUnlock(handle)
        return text or ""
    finally:
        user32.CloseClipboard()


def _clipboard_set(text: str) -> None:
    user32, kernel32 = _api()
    data = text.encode("utf-16-le") + b"\x00\x00"
    if not user32.OpenClipboard(0):
        raise OSError("无法打开剪贴板")
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(0x2002, len(data))  # GMEM_MOVEABLE|GMEM_DDESHARE
        if not handle:
            raise OSError("GlobalAlloc 失败")
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            raise OSError("GlobalLock 失败")
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(13, handle):
            raise OSError("SetClipboardData 失败")
    finally:
        user32.CloseClipboard()


# ---------------------------------------------------------------- 答题
def solve(questions: list[dict]) -> tuple[dict, list[dict]]:
    bank = load_bank()
    provider = get_provider()
    answers: dict = {}
    from_bank: list[str] = []
    new_entries: list[dict] = []

    for q in questions:
        no = str(q.get("no", len(answers) + 1))
        key = qkey(q.get("question", ""))
        hit = bank.get(key)
        if hit:
            answers[no] = hit["answer"]
            from_bank.append(no)
            continue
        if provider:
            ans = ask_llm(provider, q)
            if ans:
                answers[no] = ans
                new_entries.append({"key": key, "answer": ans,
                                    "question": q.get("question", "")[:120],
                                    "source": "llm"})
                continue
        answers[no] = ""

    if new_entries:
        for item in new_entries:
            bank[item["key"]] = {"answer": item["answer"],
                                 "question": item["question"],
                                 "source": item["source"]}
        save_bank(bank)
    return answers, from_bank


def main() -> None:
    dry = "--dry" in sys.argv
    raw = _clipboard_text().strip()
    if not raw:
        print("[solve] 剪贴板为空。请先在浏览器控制台运行 exam/export_questions.js")
        return

    questions: list[dict] = []
    try:
        payload = json.loads(raw)
        questions = payload.get("questions", [])
    except json.JSONDecodeError:
        print("[solve] 剪贴板内容不是 JSON，已忽略")
        return

    if not questions:
        print("[solve] 未解析到题目（questions 为空）")
        return

    provider = get_provider()
    name = getattr(provider, "model_name", None) or ("configured" if provider else "未配置")
    print(f"[solve] 共 {len(questions)} 题 | 模型: {name}")

    answers, from_bank = solve(questions)
    blank = [no for no, a in answers.items() if not a]

    for no in sorted(answers, key=int):
        mark = "题库" if no in from_bank else "模型"
        print(f"  第{no}题 [{mark}] -> {answers[no] or '（无答案）'}")

    print(f"\n结果：题库命中 {len(from_bank)}，模型作答 {len(questions) - len(from_bank) - len(blank)}，"
          f"未答出 {len(blank)}")
    if blank:
        print(f"未答出的题号：{','.join(sorted(blank, key=int))}（可截图题目发给 Buddy 补答案）")

    if dry:
        print("\n[dry] 答案 JSON（未写入剪贴板）：")
        print(json.dumps({"answers": answers}, ensure_ascii=False))
        return

    _clipboard_set(json.dumps({"answers": answers}, ensure_ascii=False))
    print("\n答案 JSON 已复制到剪贴板！下一步：回到答题页控制台，运行 exam/fill_answers.js，"
          "在弹窗里 Ctrl+V 粘贴并确定。")


if __name__ == "__main__":
    main()
