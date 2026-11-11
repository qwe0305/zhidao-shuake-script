/* eslint-disable */
/* 智慧树「大学生心理健康 · 绪论单元测试」一键作答
   用法：在考试页 F12 → Console → 粘贴本文件全部内容 → 回车
   特点：答案按【选项文字】匹配，选项顺序被打乱也能正确勾选；
        不会自动提交，填完你自己点右上角【提交作业】。
*/
(async function () {
  const PLAN = [
    { no: 1,  type: '多选', pick: ['探明心理结构', '揭示心理规律', '阐述心理机能', '描述心理事件'] },
    { no: 2,  type: '单选', pick: ['成年前期'] },
    { no: 3,  type: '单选', pick: ['知心朋友、夫妻、情人'] },
    { no: 4,  type: '判断', pick: ['对'] },
    { no: 5,  type: '单选', pick: ['吉尔福特'] },
    { no: 6,  type: '多选', pick: ['坚信感', '或然性', '来得快、直接', '无整体推论过程'] },
    { no: 7,  type: '判断', pick: ['对'] },
    { no: 8,  type: '单选', pick: ['皮亚杰'] },
    { no: 9,  type: '判断', pick: ['对'] },
    { no: 10, type: '多选', pick: ['创造性思维', '创造性人格'] },
  ];

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const norm = (s) => (s || '').replace(/\s+/g, '').replace(/[（）()【】\[\].,，。：:；;]/g, '');
  let failCount = 0;

  // 出现「提交答案失败」提示时点掉，避免挡住后续操作
  async function clearErrorDialog() {
    const txt = document.body.innerText;
    if (txt.indexOf('提交答案失败') === -1 && txt.indexOf('网络异常') === -1) return;
    const btns = [...document.querySelectorAll('button, .el-button, div')];
    const ok = btns.find((b) => {
      const t = (b.innerText || '').trim();
      return t === '我知道了' && b.querySelectorAll('*').length <= 2;
    });
    if (ok) {
      ok.click();
      failCount++;
      await sleep(400);
    }
  }

  const cardItems = [...document.querySelectorAll('.answerCard_list1 li')];
  const subjects = [...document.querySelectorAll('.examPaper_subject')];
  console.log('%c[答题] 题目数=' + subjects.length + '，答题卡=' + cardItems.length, 'color:#1a73e8');

  if (subjects.length === 0) {
    alert('没找到题目元素，请确认已经在答题页（能看到第 1 题）。');
    return;
  }

  let done = 0;
  for (const step of PLAN) {
    const idx = step.no - 1;
    if (cardItems[idx]) {
      cardItems[idx].click();
      await sleep(500);
    }
    const sub = subjects[idx];
    if (!sub) { console.warn('第' + step.no + '题节点缺失'); continue; }

    const labs = [...sub.querySelectorAll('.nodeLab')];
    const texts = labs.map((l) => norm((l.querySelector('.node_detail') || {}).innerText));
    console.log('%c第' + step.no + '题 [' + step.type + '] → ' + texts.join(' / '), 'color:#888');

    let hit = 0;
    for (const want of step.pick) {
      const w = norm(want);
      const k = texts.findIndex((t) => t && (t === w || t.indexOf(w) > -1 || w.indexOf(t) > -1));
      if (k === -1) { console.warn('  ✗ 未匹配「' + want + '」'); continue; }
      const lab = labs[k];
      const input = lab.querySelector('input');
      if (input && input.checked) continue;
      lab.click();
      await sleep(350);
      if (input && !input.checked) { input.click(); await sleep(250); }
      hit++;
      await clearErrorDialog();
    }
    if (hit) done++;
    console.log('%c  ✓ 勾选 ' + hit + ' 项', 'color:#0a0');
    await sleep(350);
    await clearErrorDialog();
  }

  const checked = [...document.querySelectorAll('input.mr30')].filter((i) => i.checked).length;
  console.log('%c[答题] 已处理 ' + done + '/10 题，页面勾选总数=' + checked + '，保存失败提示=' + failCount, 'color:#1a73e8');
  alert('已按答案勾选完成（处理 ' + done + ' 题）。\n' +
        (failCount ? '注意：出现了 ' + failCount + ' 次「提交答案失败」，请检查网络后再点一次选项。\n' : '') +
        '请滚动检查一遍，然后点右上角【提交作业】。');
})();
