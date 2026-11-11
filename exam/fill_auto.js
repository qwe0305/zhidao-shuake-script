/* ============================================================
   智慧树考试 全自动填答脚本（配合本地答题服务 exam/server.py）
   ------------------------------------------------------------
   使用前：先在项目目录运行  python exam/server.py
   用法：打开答题页 → F12 → Console → 粘贴本文件 → 回车
   流程：抓题 -> 发给本地服务(题库优先/大模型兜底) -> 自动勾选
         -> 自动翻页 -> 自动提交
   注意：Chrome 首次粘贴需先手打 allow pasting 回车
   ============================================================ */
(async () => {
  const SERVER = "http://127.0.0.1:8766";
  const AUTO_SUBMIT = true;
  const MAX_PAGES = 40;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const norm = (s) => (s || "").replace(/\s+/g, " ").trim();

  /* ---------- 抓取选项元素并按题分组 ---------- */
  function collectGroups() {
    const all = [...document.querySelectorAll("li,label,div,span,p")];
    const cands = all.filter((el) => {
      const t = norm(el.innerText);
      return /^[A-H][.、．)）]/.test(t) && t.length <= 150;
    });
    const inner = cands.filter((el) => !cands.some((o) => o !== el && el.contains(o)));
    const groups = [];
    let cur = null;
    for (const el of inner) {
      const letter = norm(el.innerText)[0].toUpperCase();
      if (!cur || letter === "A") { cur = []; groups.push(cur); }
      cur.push({ letter, el });
    }
    return groups;
  }

  /* ---------- 提取每题题干（选项之前的文字） ---------- */
  function questionTextFor(group) {
    const els = group.map((o) => o.el);
    let anc = els[0];
    while (anc && !els.every((e) => anc.contains(e))) anc = anc.parentElement;
    if (!anc) return "";
    const lines = anc.innerText.split("\n").map((s) => s.trim()).filter(Boolean);
    const optTexts = els.map((e) => norm(e.innerText));
    const stem = [];
    for (const l of lines) {
      if (optTexts.some((o) => l === o)) break;
      stem.push(l);
    }
    return stem.join(" ").replace(/^\d{1,2}\s*[.、．)）]\s*/, "").slice(0, 300);
  }

  function clickEl(el) {
    const target = el.closest("li,label") || el;
    target.click();
    target.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    target.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
    target.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  }

  function findBtn(words) {
    return [...document.querySelectorAll("button,a,div,span,li")]
      .filter((el) => el.offsetParent !== null)
      .find((el) => words.includes(norm(el.innerText)) && norm(el.innerText).length <= 8);
  }

  /* ---------- 填当前页 ---------- */
  function fillPage(groups, answers, startIndex) {
    let filled = 0;
    groups.forEach((g, i) => {
      const no = startIndex + i + 1;
      const ans = (answers[no] || "").toUpperCase();
      if (!ans) return;
      const isJudge = g.every((o) => /^[A-H]\s*[.、．)）]?\s*(对|错|正确|错误|是|否)$/.test(norm(o.el.innerText)));
      for (const token of ans.match(/[A-H]|对|错|正确|错误/g) || []) {
        let hit = null;
        if (isJudge) {
          hit = g.find((o) => norm(o.el.innerText).includes(token));
        } else {
          hit = g.find((o) => o.letter === token);
        }
        if (hit) { clickEl(hit.el); filled++; }
      }
    });
    return filled;
  }

  console.log("%c[ZHS-AI] 全自动答题开始", "color:#0a0;font-weight:bold");

  let page = 0, pageStart = 0, allAnswers = {}, llmUsed = false;
  while (page < MAX_PAGES) {
    const groups = collectGroups();
    if (!groups.length) { console.warn("[ZHS-AI] 本页未识别到选项"); break; }

    const questions = groups.map((g, i) => ({
      no: pageStart + i + 1,
      type: "",
      question: questionTextFor(g),
      options: g.map((o) => norm(o.el.innerText)),
    }));

    let answers = {};
    try {
      const res = await fetch(SERVER + "/answer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ questions }),
      });
      const data = await res.json();
      answers = data.answers || {};
      llmUsed = llmUsed || !!data.llm_used;
      const bankCount = Object.keys(data.from_bank || {}).length;
      console.log(`[ZHS-AI] 第${page + 1}页 ${questions.length} 题 | 题库命中 ${bankCount} | 大模型 ${data.llm_used ? "已用" : "未配置"}`);
    } catch (e) {
      console.error("[ZHS-AI] 本地服务连不上，请先运行: python exam/server.py", e);
      break;
    }
    Object.assign(allAnswers, answers);

    fillPage(groups, answers, pageStart);
    await sleep(600);

    const left = Object.keys(answers).filter((k) => !answers[k]);
    const next = findBtn(["下一题", "下一部分", "下一页"]);
    if (!next) break;
    next.click();
    page++;
    pageStart += groups.length;
    await sleep(900);
  }

  console.log("[ZHS-AI] 答案汇总:", JSON.stringify(allAnswers));
  const blank = Object.entries(allAnswers).filter(([, v]) => !v).map(([k]) => k);
  if (blank.length) console.warn("[ZHS-AI] 未获得答案的题号:", blank.join(", "), "(可截图发给 Buddy 人工补充)");

  if (AUTO_SUBMIT) {
    await sleep(500);
    const submit = findBtn(["提交", "交卷", "提交试卷", "保存并提交"]);
    if (submit) {
      submit.click();
      await sleep(1500);
      const ok = findBtn(["确定", "确认", "确认提交"]);
      if (ok) ok.click();
      console.log("%c[ZHS-AI] 已提交", "color:#0a0;font-weight:bold");
    } else {
      console.warn("[ZHS-AI] 没找到提交按钮，请手动提交");
    }
  }
})();
