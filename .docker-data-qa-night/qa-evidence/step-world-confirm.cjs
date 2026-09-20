// 步骤：填势力行+三条铁律 → 确认完成
const path = require('path');
const { chromium } = require('playwright');
const EV = __dirname;

(async () => {
  const browser = await chromium.connectOverCDP('http://localhost:9333');
  const ctx = browser.contexts()[0];
  const out = {};
  let page = ctx.pages().find((p) => p.url().startsWith('http://localhost:6174'));
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(400);

  // 势力行两个输入
  const factionInputs = page.getByPlaceholder('例：丹阁');
  out.factionNameCount = await factionInputs.count();
  await factionInputs.fill('星阑会');
  await page.getByPlaceholder('例：要为残卷讨一个说法，与青梧宗敌对').fill('星阑会要收缴民间古灯、封锁坠星渊，认为点灯术烧掉的正是星海秩序的根基，视守灯人为祸源');

  // 三条铁律内容
  const ruleInputs = page.getByPlaceholder('例：元婴老祖能移山填海，不能起死回生');
  out.ruleCount = await ruleInputs.count();
  const ruleTexts = [
    '长明为顶点；引焰一次至多点亮一星，一夜不过三次',
    '祖母的残影仍在星海深处；九座浮陆正在缓慢下坠',
    '坠星渊的「回声」就是历代点灯人被烧掉的记忆',
  ];
  for (let i = 0; i < Math.min(out.ruleCount, 3); i++) {
    await ruleInputs.nth(i).fill(ruleTexts[i]);
  }
  await page.screenshot({ path: path.join(EV, 't19_world_details.png') });
  await page.getByRole('button', { name: '确认完成' }).click();
  await page.waitForTimeout(1200);
  out.afterConfirm = (await page.innerText('body')).slice(0, 400);
  await page.screenshot({ path: path.join(EV, 't20_after_world.png') });
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})().catch((e) => { console.error('STEP FAILED:', e.message); process.exit(1); });
