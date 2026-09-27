const path = require('path');
// 可移植：优先 worktree 自己的 node_modules，允许 PW_MODULE 环境变量兜底（未装依赖的检出）
const pwCandidates = [
  path.join(__dirname, '../../../../client/frontend/node_modules/playwright'),
  process.env.PW_MODULE,
].filter(Boolean);
let chromium;
for (const c of pwCandidates) {
  try { ({ chromium } = require(c)); break; } catch (e) { /* 试下一个 */ }
}
if (!chromium) { console.error('playwright not found; set PW_MODULE=/path/to/playwright'); process.exit(2); }
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  await page.goto('file://' + path.join(__dirname, '../../../../docs/design-c/drafts/ai-novel-c端-人物精盘.html'));
  await page.waitForTimeout(300);
  const t = (name, ok) => console.log((ok ? 'PASS' : 'FAIL') + ' ' + name);

  // S1 入口
  t('S1 弹窗标题=盘点出场人物', (await page.textContent('.mcard-head .mh')) === '盘点出场人物');
  t('S1 统一卡结构（ra-head+ai-target+6行+ra-foot）', await page.evaluate(() => {
    const c = document.querySelector('.rail-assist');
    return !!c.querySelector('.ra-head .plan-badge') && !!c.querySelector('.ai-target')
      && c.querySelectorAll('.ra-step').length === 6 && !!c.querySelector('.ra-foot');
  }));
  t('S1 盘点=第5条 ra-step 且免费可点', await page.evaluate(() => {
    const rows = document.querySelectorAll('.rail-assist .ra-step');
    return rows[4].id === 'btn-open-review' && !rows[4].classList.contains('ra-off');
  }));
  t('S1 e-meta 八枚徽章', (await page.$$('.e-head .e-meta .tag')).length === 8);
  t('S1 卡标题=AI 助手 · 章纲', (await page.textContent('.rail-assist .rh-t b')) === 'AI 助手 · 章纲');
  t('S1 魏七新徽隐藏', await page.isHidden('#og-chips [data-wb="fresh-chip"]'));
  t('S1 秦伯没卡带建卡入口', await page.isVisible('[data-testid="claim-qinbo"]'));
  t('S1 v1 术语「人物精盘」清零', await page.evaluate(() => !document.body.innerText.includes('人物精盘')));

  // S2→S3
  await page.click('#btn-open-review');
  await page.waitForTimeout(1100);
  t('S3 逐段盘点行=4', (await page.$$('#sc-s3 .cr-row')).length === 4);
  t('S3 两缺口（已延后+待处理）', await page.isVisible('[data-testid="gap-deferred"].done') && await page.isVisible('[data-testid="gap-active"]:not(.done)'));
  t('S3 PRO 角标在按钮外', await page.evaluate(() => {
    const act = document.querySelector('#sc-s3 .g-act');
    const btn = act.querySelector('button');
    return !btn.textContent.includes('PRO') && !!act.querySelector('.ai-tag');
  }));
  t('S3 三选一 aria-checked', (await page.getAttribute('[data-testid="cr-opt-add"]', 'aria-checked')) === 'true');
  t('V2.3 AI 建议标在预填上', await page.isVisible('#sc-s3 .cr-sug'));
  t('S3 术语「落库」清零', !(await page.textContent('#modal')).includes('落库'));

  // 三选一：改段 → 已处理观感+补救出口
  await page.click('[data-testid="cr-opt-edit"]');
  t('S3 改段→缺口转已处理', await page.evaluate(() => document.querySelector('[data-testid="gap-active"]').classList.contains('done')));
  t('S3 改段→抽人隐藏/去改剧情出现', await page.isHidden('#btn-draw') && await page.isVisible('[data-testid="cr-go-edit"]'));
  await page.click('[data-testid="cr-opt-defer"]');
  t('S3 延后→pill 转中性', (await page.textContent('[data-testid="gap-active"] .g-head .pill')) === '已延后');
  await page.click('[data-testid="cr-opt-add"]');
  t('S3 切回加人→恢复 warn+抽人', await page.isVisible('#btn-draw') && (await page.textContent('[data-testid="gap-active"] .g-head .pill')) === '缺 1 人');

  // S5 抽卡
  await page.click('#btn-draw');
  t('S5 三卡 radiogroup', (await page.getAttribute('#pick-grid-5', 'role')) === 'radiogroup');
  t('S5 返回盘点结果出口在', await page.isVisible('[data-testid="cr-back-review"]'));
  t('S5 note 讲清两按钮差异', (await page.textContent('#sc-s5 .pick-foot .note')).includes('清掉记录重出'));

  // 返回盘点结果再进
  await page.click('[data-testid="cr-back-review"]');
  t('S3′ 返回后缺口仍待处理', await page.isVisible('#btn-draw'));
  await page.click('#btn-draw');
  await page.click('[data-testid="cr-pick-card-1"]');
  await page.waitForTimeout(500);

  // S7 两出口
  t('S7 主出口=建卡并写入章纲', (await page.textContent('[data-testid="cr-write"]')).includes('建卡并写入章纲'));
  t('S7 次出口=只加名单', await page.isVisible('[data-testid="cr-list-only"]'));
  t('S7 术语「申报」清零', !(await page.textContent('#sc-s6')).includes('申报'));

  // 次出口 → 名单回执
  await page.click('[data-testid="cr-list-only"]');
  t('S8′ 名单回执（暂未建卡）', (await page.textContent('#done-notice')).includes('暂未建卡'));

  // 主流程 → 建卡回执：写入后回盘点结果页（多缺人回程）
  await page.click('.demo-bar .chip[data-scene="s6"]');
  await page.click('[data-testid="cr-write"]');
  t('S8 写入后回结果页（弹窗不关）', await page.isVisible('#modal') && await page.isVisible('#sc-s3'));
  t('S8 缺口转已处理（gap-written）', await page.isVisible('[data-testid="gap-written"]') && await page.isHidden('[data-testid="gap-active"]'));
  t('S8 建卡回执三处落账', (await page.textContent('#done-notice')).includes('角色表') && (await page.textContent('#done-notice')).includes('自动汇总'));
  t('S8 回执 aria-live', (await page.getAttribute('#done-notice', 'aria-live')) === 'polite');
  t('S8 名单魏七 chip+统计4人', await page.isVisible('#og-chips .chip:has-text("魏七")') && (await page.textContent('#stat-cast')).includes('4 人'));

  // 完成按钮关窗（全部处理完才收场）
  await page.click('#btn-cancel');
  t('S8 完成→关窗', await page.isHidden('#modal'));

  // S4 零新增
  await page.click('.demo-bar .chip[data-scene="s4"]');
  t('S4 配额区间 5–8 软话术', (await page.textContent('#sc-s4')).includes('5–8') && (await page.textContent('#sc-s4')).includes('你自己填名单永远不受限'));

  // S5b 免费锁定
  await page.click('.demo-bar .chip[data-scene="s5b"]');
  t('S6b 抽卡按钮禁点', await page.evaluate(() => document.querySelector('[data-testid="cr-draw-locked"]').disabled));
  t('S6b 无假卡面（零 pick-card）', (await page.$$('#sc-s5b .pick-card')).length === 0);
  t('S6b 升级出口+自己填可用', await page.isVisible('.lock-card .btn-primary') && await page.isVisible('.lock-card .btn-secondary'));
  t('S6b 免费行级门控（盘点可点+PRO行需PRO）', await page.evaluate(() => {
    const rows = document.querySelectorAll('.rail-assist .ra-step');
    const cast = document.getElementById('btn-open-review');
    const pro = document.querySelector('.ra-step[data-pro]');
    return document.getElementById('wb').classList.contains('free-mode')
      && !cast.classList.contains('ra-off')
      && pro.classList.contains('ra-off') && pro.querySelector('.ra-hint')?.textContent === '需 PRO'
      && pro.querySelector('.ra-hint') && getComputedStyle(pro.querySelector('.ra-hint')).display !== 'none';
  }));

  // ⑩抽卡中 / ⑪抽卡失败
  await page.click('.demo-bar .chip[data-scene="s10"]');
  t('S10 抽卡中等待态', (await page.textContent('#sc-s10')).includes('正在想'));
  await page.click('.demo-bar .chip[data-scene="s11"]');
  t('S11 抽卡失败三出口', await page.isVisible('[data-testid="cr-draw-error"]') && (await page.$$('#sc-s11 .edit-bar .btn')).length === 3);

  // v2.3 稿面断言
  await page.click('.demo-bar .chip[data-scene="s5"]');
  t('V2.3 A/B 角标小字', (await page.textContent('#pick-grid-5 .pk-corner.g-A')).includes('也行') && (await page.textContent('#pick-grid-5 .pk-corner.g-B')).includes('备选'));
  t('V2.3 组合禁令底注', (await page.textContent('#sc-s5 .pick-foot .note')).includes('避开最近走过的方向'));
  await page.click('.demo-bar .chip[data-scene="s3"]');
  t('V2.3 预填可改提示', (await page.textContent('#sc-s3 .cr-pick .k')).includes('AI 预填可改'));
  t('V2.3 重新盘点入口', await page.isVisible('[data-testid="cr-recheck"]'));
  t('V2.3 行序 1/2/3/4 缺口随行', await page.evaluate(() => {
    const nos = [...document.querySelectorAll('#sc-s3 .cr-no')].map(x => x.textContent);
    return JSON.stringify(nos) === JSON.stringify(['剧情 1','剧情 2','剧情 3','剧情 4']);
  }));
  await page.click('.demo-bar .chip[data-scene="s6"]');
  t('V2.3 返回换一张+丢预填告知', await page.isVisible('[data-testid="cr-back-cards"]') && (await page.textContent('#sc-s6 .hint')).includes('上面几格不保存'));

  // S9 失败态
  await page.click('.demo-bar .chip[data-scene="s9"]');
  t('S9 失败态三出口（重试/去模型配置/先不盘点）', await page.isVisible('[data-testid="cr-error"]') && (await page.$$('#sc-s9 .edit-bar .btn')).length === 3 && (await page.textContent('#sc-s9 .edit-bar')).includes('重试') && !(await page.textContent('#sc-s9')).includes('自己填'));
  // v2.4：两形态＋档位继承＋AI 建议标消失＋回执全清行
  await page.click('.demo-bar .chip[data-scene="s3"]');
  await page.click('#lnk-fill-manual');
  t('V2.4 手填形态=空格表单无返回', await page.evaluate(() => {
    const inputs = [...document.querySelectorAll('#sc-s6 input.input')];
    return inputs.every(i => i.value === '') && document.getElementById('btn-back-cards').hidden;
  }));
  await page.click('.demo-bar .chip[data-scene="s5b"]');
  await page.click('#sc-s5b .lock-card .btn-secondary');
  t('V2.4 手填路径免费视角继承', await page.evaluate(() => document.getElementById('wb').classList.contains('free-mode') && document.getElementById('btn-back-cards').hidden));
  await page.click('.demo-bar .chip[data-scene="s5"]');
  await page.click('[data-testid="cr-pick-card-1"]');
  await page.waitForTimeout(500);
  t('V2.4 选卡形态=预填+返回换一张', await page.evaluate(() => {
    const inputs = [...document.querySelectorAll('#sc-s6 input.input')];
    return inputs[0].value === '魏七' && !document.getElementById('btn-back-cards').hidden;
  }));
  await page.click('.demo-bar .chip[data-scene="s3"]');
  await page.click('[data-testid="cr-opt-edit"]');
  t('V2.4 AI 建议标随改选消失', (await page.$$('#sc-s3 .cr-sug')).length === 0);

  // 文案人话化断言（v2.1）——跨态取样，弹窗一次只显示一个 scene
  let visText = '';
  for (const sc of ['s3', 's5', 's6', 's4', 's5b']) {
    await page.click(`.demo-bar .chip[data-scene="${sc}"]`);
    visText += await page.evaluate(() => document.getElementById('modal').innerText
      + document.getElementById('btn-open-review').innerText);
  }
  t('V2.1 三分类新标签在位', visText.includes('老角色能演') && visText.includes('不起名也行') && visText.includes('缺一个新角色'));
  const jargon = ['可扛', '功能定位', '旧人', '泛称', '落库', '聚合', '申报', '功能位', '进场方式', '退场计划', '缺口'];
  const leaked = jargon.filter(w => visText.includes(w));
  t('V2.1 旧黑话清零: ' + (leaked.join('/') || '无'), leaked.length === 0);
  t('V2.1 卡面人话标签', visText.includes('他是干什么的') && visText.includes('怎么出场') && visText.includes('怎么退场') && visText.includes('老角色为什么不行'));

  t('零页面错误', errors.length === 0);
  if (errors.length) console.log(errors.join('\n'));
  await browser.close();
})();
