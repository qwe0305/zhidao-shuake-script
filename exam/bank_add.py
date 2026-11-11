"""exam/bank_add.py —— 往题库录入答案

用法：
    # 单条录入（题干=答案，答案如 ABC / C / 对）
    python exam/bank_add.py "心理学的任务=ABC"
    python exam/bank_add.py "以下哪项不属于心理健康的标准？=C"

    # 批量录入（JSON 文件，格式：[{"question": "...", "answer": "ABC"}, ...]）
    python exam/bank_add.py --file answers.json

题库文件：data/question_bank.json
键 = 题干归一化 md5（忽略标点/空白差异），与 server.py 保持一致
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
BANK_PATH = BASE / "data" / "question_bank.json"


def qkey(question: str) -> str:
    norm = re.sub(r"[\s，。：:；;？?（）()【】\[\]\"'、.]", "", question or "")
    return hashlib.md5(norm.encode("utf-8")).hexdigest()


def load_bank() -> dict:
    try:
        return json.loads(BANK_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_bank(bank: dict) -> None:
    BANK_PATH.parent.mkdir(parents=True, exist_ok=True)
    BANK_PATH.write_text(
        json.dumps(bank, ensure_ascii=False, indent=2), encoding="utf-8")


def add(question: str, answer: str, bank: dict) -> bool:
    answer = answer.strip().upper()
    if not question or not answer:
        return False
    key = qkey(question)
    existed = bank.get(key)
    bank[key] = {"answer": answer, "question": question[:120], "source": "manual"}
    return existed is None


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    bank = load_bank()
    added, updated = 0, 0
    if "--file" in args:
        path = Path(args[args.index("--file") + 1])
        items = json.loads(path.read_text(encoding="utf-8"))
        for it in items:
            if add(it.get("question", ""), it.get("answer", ""), bank):
                added += 1
            else:
                updated += 1
    else:
        for arg in args:
            if "=" not in arg:
                print(f"[跳过] 缺少 '='：{arg}")
                continue
            q, a = arg.split("=", 1)
            if add(q, a, bank):
                added += 1
            else:
                updated += 1
    save_bank(bank)
    print(f"完成：新增 {added} 条，覆盖 {updated} 条，题库共 {len(bank)} 条 -> {BANK_PATH}")


if __name__ == "__main__":
    main()
