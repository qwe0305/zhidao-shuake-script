"""答案解析的离线自测（不消耗 API）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_provider import normalize_base_url, parse_answer, resolve_config  # noqa: E402

CASES = [
    # (说明, 原始文本, 期望结果)
    (
        "标准 answer 代码块",
        '这是答案：\n```answer\n[{"id": 652308395, "content": "A"}]\n```\n解析如上',
        [652308395],
    ),
    (
        "json 标签代码块",
        '```json\n[{"id": 1, "content": "A"}, {"id": 2, "content": "B"}]\n```',
        [1, 2],
    ),
    (
        "无标签代码块",
        '答案\n```\n[{"id": 7, "content": "C"}]\n```',
        [7],
    ),
    (
        "裸 JSON 数组（无代码块）",
        '我认为答案是 [{"id": 42, "content": "D"}] 这个。',
        [42],
    ),
    (
        "尾逗号",
        '```answer\n[{"id": 5, "content": "E"},]\n```',
        [5],
    ),
    (
        "单引号 Python 字面量",
        "```answer\n[{'id': 9, 'content': 'F'}]\n```",
        [9],
    ),
    (
        "只有 id 的简写数组",
        '```answer\n[{"id": 3}]\n```',
        [3],
    ),
    (
        "答案块返回单个对象而非数组（宽容处理）",
        '```answer\n{"id": 1}\n```',
        [1],
    ),
]

BAD_CASES = [
    ("完全没有答案块", "我不知道这道题。"),
    ("空文本", ""),
    ("答案项缺 id", '```answer\n[{"content": "没有 id"}]\n```'),
]


def main() -> int:
    passed = failed = 0

    for name, text, expect in CASES:
        try:
            got = parse_answer(text)
            if got == expect:
                print(f"  [OK]   {name} -> {got}")
                passed += 1
            else:
                print(f"  [FAIL] {name}: 期望 {expect}, 实际 {got}")
                failed += 1
        except Exception as exc:
            print(f"  [FAIL] {name}: 抛异常 {exc}")
            failed += 1

    for name, text in BAD_CASES:
        try:
            got = parse_answer(text)
            print(f"  [FAIL] {name}: 本应抛异常，却返回 {got}")
            failed += 1
        except Exception:
            print(f"  [OK]   {name} -> 正确抛出异常")
            passed += 1

    # URL 归一化
    urls = [
        ("https://api.deepseek.com/v1", "https://api.deepseek.com"),
        ("https://api.deepseek.com/v1/", "https://api.deepseek.com"),
        ("https://api.deepseek.com", "https://api.deepseek.com"),
        ("https://open.bigmodel.cn/api/paas/v4", "https://open.bigmodel.cn/api/paas/v4"),
    ]
    for raw, expect in urls:
        got = normalize_base_url(raw)
        if got == expect:
            print(f"  [OK]   url {raw} -> {got}")
            passed += 1
        else:
            print(f"  [FAIL] url {raw}: 期望 {expect}, 实际 {got}")
            failed += 1

    # provider 预设解析
    base, key, model = resolve_config({"provider": "deepseek", "api_key": "sk-test"})
    if base == "https://api.deepseek.com" and model == "deepseek-chat":
        print(f"  [OK]   preset deepseek -> {base} / {model}")
        passed += 1
    else:
        print(f"  [FAIL] preset deepseek: {base} / {model}")
        failed += 1

    print(f"\n通过 {passed} 项，失败 {failed} 项")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
