/* ============================================================
   智慧树考试/章节测试 自动填答脚本
   ------------------------------------------------------------
   用法：
   1. 打开某套测试的答题页（能看到题目和 A/B/C/D 选项）
   2. F12 → Console（控制台）→ 粘贴本文件全部内容 → 回车
   3. 脚本会自动逐题勾选、自动翻页、最后自动提交
   4. 顶部有一个 ANSWERS 对象，把 "1":"ABC" 换成实际答案即可
   ============================================================ */
(async () => {
  /* ====================== 答案区 ======================
     优先：弹窗粘贴 exam/solve.py 生成的答案 JSON（已在剪贴板）
     备用：把下面 ANSWERS 对象填成 {1:"ABC", 2:"D", ...}
     键 = 题号，值 = 选项字母（多选连写，判断题可写 对/错）
     ============================================================== */
  let ANSWERS = {};
  const pasted = prompt("粘贴答案 JSON（solve.py 已把它放进剪贴板，直接 Ctrl+V）：");
  if (pasted) {
    try {
      const parsed = JSON.parse(pasted);
      ANSWERS = parsed.answers || parsed;
      console.log(`[ZHS] 已载入 ${Object.keys(ANSWERS).length} 题答案`);
    } catch (e) {
      console.error("[ZHS] 粘贴的内容不是合法 JSON，改用脚本内 ANSWERS", e);
    }
  }

  const AUTO_SUBMIT = true;   // 填完自动点提交
  const MAX_PAGES = 40;       // 最多自动翻多少页

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const norm = (s) => (s || "").replace(/\s+/g, " ").trim();
  const answered = new Set();

  /* 收集"像选项"的元素：以 A./B、/C) 开头且文本不太长 */
  function collectOptions() {
    const all = [...document.querySelectorAll("li,label,div,span,p")];
    const cands = all.filter((el) => {
      const t = norm(el.innerText);
      return /^[A-H][.、．)）]/.test(t) && t.length <= 150;
    });
    // 只保留最内层（避免父子重复计数）
    return cands.filter((el) => !cands.some((o) => o !== el && el.contains(o)));
  }

  /* 按字母序分组：每遇到 A 就开一道新题 */
  function groupByQuestion(opts) {
    const groups = [];
    let cur = null;
    for (const el of opts) {
      const letter = norm(el.innerText)[0].toUpperCase();
      if (!cur || letter === "A") {
        cur = [];
        groups.push(cur);
      }
      cur.push({ letter, el });
    }
    return groups;
  }

  function clickEl(el) {
    const target = el.closest("li,label") || el;
    target.click();
    target.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    target.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
    target.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  }

  function findButton(words) {
    const btns = [...document.querySelectorAll("button,a,div,span,li")];
    return btns.find((el) => {
      const t = norm(el.innerText);
      return t.length <= 12 && words.some((w) => t === w);
    });
  }

  /* 填当前这一屏（一页可能 1 题，也可能 10 题） */
  function fillCurrentPage(startIndex) {
    const groups = groupByQuestion(collectOptions());
    let filled = 0;
    groups.forEach((g, i) => {
      const no = startIndex + i + 1;
      const ans = ANSWERS[no];
      if (!ans) return;
      for (const ch of String(ans).toUpperCase()) {
        const hit = g.find((o) => o.letter === ch);
        if (hit) {
          clickEl(hit.el);
          filled++;
        }
      }
      answered.add(no);
    });
    return { groups: groups.length, filled };
  }

  console.log("%c[ZHS] 自动填答开始", "color:#0a0;font-weight:bold");

  let page = 0;
  let pageStart = 0;
  while (page < MAX_PAGES) {
    const r = fillCurrentPage(pageStart);
    console.log(`[ZHS] 第 ${page + 1} 屏：识别 ${r.groups} 道题，勾选 ${r.filled} 个选项`);
    await sleep(600);

    const left = Object.keys(ANSWERS).filter((k) => !answered.has(Number(k)));
    if (left.length === 0) break;

    const next = findButton(["下一题", "下一页", "下一部分", ">", "＞"]);
    if (!next) break;
    next.click();
    page++;
    pageStart += r.groups;
    await sleep(900);
  }

  console.log(`[ZHS] 已作答题号：${[...answered].sort((a, b) => a - b).join(", ")}`);
  const missing = Object.keys(ANSWERS).filter((k) => !answered.has(Number(k)));
  if (missing.length) console.warn("[ZHS] 没找到的题号：", missing.join(", "));

  if (AUTO_SUBMIT) {
    await sleep(500);
    const submit = findButton(["提交", "交卷", "提交试卷", "保存并提交", "确定提交"]);
    if (submit) {
      console.log("[ZHS] 点击提交");
      submit.click();
      await sleep(1500);
      const ok = findButton(["确定", "确认", "确认提交", "继续交卷"]);
      if (ok) {
        console.log("[ZHS] 二次确认");
        ok.click();
      }
    } else {
      console.warn("[ZHS] 未找到提交按钮，请手动点击提交");
    }
  }
  console.log("%c[ZHS] 完成", "color:#0a0;font-weight:bold");
})();
