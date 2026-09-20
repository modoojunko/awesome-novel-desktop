// 步骤：填世界页（01-05）并确认完成
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

  // 01 世界舞台 / 02 力量体系 / 03 代价 —— 页面级 textarea 顺序
  const tas = page.locator('textarea');
  out.textareaCount = await tas.count();
  await tas.nth(0).fill('九州星域，灵潮纪元七百年。世界是悬于星海之上的九座浮陆，彼此以星桥相连；陆上凡人城邦与修士宗门分治。主要地点：执灯城的守夜塔、坠星渊、拾遗巷的老宅。');
  await tas.nth(1).fill('点灯术：以自身记忆为灯油点燃星光，分照明、引焰、续灯、长明四级；每晋升一级烧去一段完整记忆。上限：长明境再往上要燃烧自我认知，古今无一人成功。');
  await tas.nth(2).fill('每用一次引焰以上术法，遗失的记忆不可找回；遗忘越多，对亲友辨识度越低。绝对禁忌：点燃他人记忆，会招致星海「回声」反噬。');

  // 04 势力：加两个
  await page.getByText('加一个势力').first().click();
  await page.waitForTimeout(400);
  out.factionSectionAfterAdd = (await page.locator('body').innerText()).match(/04\n势力[\s\S]{0,400}/)?.[0] ?? 'not-found';
  await page.screenshot({ path: path.join(EV, 't17_faction_row.png') });

  // 05 铁律：点三个预设
  for (const rule of ['能力上限', '世人不知道的事', '真相唯一']) {
    await page.getByText(rule, { exact: true }).first().click();
    await page.waitForTimeout(200);
  }
  await page.screenshot({ path: path.join(EV, 't18_world_filled.png') });
  out.beforeConfirm = (await page.innerText('body')).slice(0, 200);
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})().catch((e) => { console.error('STEP FAILED:', e.message); process.exit(1); });
