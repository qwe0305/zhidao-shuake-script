/* ============================================================
   智慧树考试 结构化导题脚本（输出 JSON，配合 exam/solve.py）
   ------------------------------------------------------------
   用法：答题页 → F12 → Console → 粘贴本文件 → 回车
   效果：自动翻完所有题，把结构化题目 JSON 复制到剪贴板，
         页面顶部同时显示文本框（备用）
   下一步：python exam/solve.py   （读剪贴板答题，答案再复制回剪贴板）
   ============================================================ */
(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const norm = (s) => (s || "").replace(/\s+/g, " ").trim();
  const MAX_PAGES = 40;

  function findBtn(words) {
    return [...document.querySelectorAll("button,a,div,span,li")]
      .filter((el) => el.offsetParent !== null)
      .find((el) => words.includes(norm(el.innerText)) && norm(el.innerText).length <= 8);
  }
  function confirmDialog() {
    const ok = findBtn(["确定", "确认"]);
    if (ok) { ok.click(); return true; }
    return false;
  }
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
    const joined = stem.join(" ");
    const typeM = joined.match(/【(单选题|多选题|判断题|填空题)】/);
    return {
      type: typeM ? typeM[1] : "",
      question: joined.replace(/【(单选题|多选题|判断题|填空题)】/g, "")
        .replace(/^\d{1,2}\s*[.、．)）]\s*/, "")
        .replace(/\(\d+分\)/g, "")
        .slice(0, 300),
    };
  }

  const questions = [];
  let no = 0;
  for (let page = 0; page < MAX_PAGES; page++) {
    await sleep(400);
    const groups = collectGroups();
    for (const g of groups) {
      const meta = questionTextFor(g);
      no++;
      questions.push({
        no,
        type: meta.type,
        question: meta.question,
        options: g.map((o) => norm(o.el.innerText)),
      });
    }
    const next = findBtn(["下一题", "下一部分", "下一页"]);
    if (!next) break;
    next.click();
    await sleep(700);
    confirmDialog();
    await sleep(300);
  }

  const payload = JSON.stringify({ url: location.href, questions }, null, 1);
  const ta = document.createElement("textarea");
  ta.value = payload;
  ta.style.cssText = "position:fixed;left:0;top:0;width:100%;height:55%;z-index:999999;" +
    "background:#fff;color:#000;font:11px monospace;border:3px solid red;";
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  try { document.execCommand("copy"); } catch (e) {}
  console.log("%c已抓取 " + questions.length + " 道题，JSON 已复制到剪贴板！", "color:green;font-weight:bold");
  console.log("下一步：运行  python exam/solve.py  （答题后答案自动进剪贴板）");
})();
