/* ============================================================
   智慧树考试页 一键导出题目脚本
   ------------------------------------------------------------
   用法：打开答题页 → F12 → Console → 粘贴本文件 → 回车
   效果：自动翻完所有题，把题目文字复制到剪贴板，
         同时在页面顶部显示一个文本框（可手动 Ctrl+A Ctrl+C）
   ============================================================ */
(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const norm = (s) => (s || "").replace(/\s+/g, " ").trim();
  const MAX_PAGES = 30;

  function findBtn(words) {
    return [...document.querySelectorAll("button,a,div,span,li")]
      .filter((el) => el.offsetParent !== null)
      .find((el) => words.includes(norm(el.innerText)) && norm(el.innerText).length <= 8);
  }

  function confirmDialog() {
    const ok = findBtn(["确定", "确认", "确 定"]);
    if (ok) { ok.click(); return true; }
    return false;
  }

  const pages = [];
  for (let i = 0; i < MAX_PAGES; i++) {
    await sleep(400);
    pages.push("===== 第 " + (i + 1) + " 题 =====\n" + document.body.innerText);
    const next = findBtn(["下一题", "下一部分", "下一页"]);
    if (!next) break;
    next.click();
    await sleep(700);
    confirmDialog();
    await sleep(300);
  }

  const txt = pages.join("\n\n");
  const ta = document.createElement("textarea");
  ta.value = txt;
  ta.style.cssText = "position:fixed;left:0;top:0;width:100%;height:55%;z-index:999999;" +
    "background:#fff;color:#000;font:12px monospace;border:3px solid red;";
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  try { document.execCommand("copy"); console.log("%c已复制到剪贴板！", "color:green;font-weight:bold"); }
  catch (e) { console.warn("自动复制失败，请在文本框里 Ctrl+A Ctrl+C"); }
  console.log("共抓取", pages.length, "屏。把内容直接粘贴给 Buddy 即可。");
})();
