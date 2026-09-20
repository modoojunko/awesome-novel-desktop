// 步骤：填主角卡基础字段 + 六层认知
const path = require('path');
const { chromium } = require('playwright');
const EV = __dirname;

(async () => {
  const browser = await chromium.connectOverCDP('http://localhost:9333');
  const ctx = browser.contexts()[0];
  const out = {};
  let page = ctx.pages().find((p) => p.url().startsWith('http://localhost:6174'));
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(300);

  await page.getByPlaceholder('姓名 / 称号').fill('陈晏');
  await page.getByPlaceholder('别名 / 称号（可选）').fill('守灯人');
  await page.getByPlaceholder('此人是谁、凭什么是他').fill('一个靠遗忘换取星光的守灯人，越走越强，也越走越不认识自己');
  await page.getByPlaceholder('性别', { exact: true }).fill('男');
  await page.getByPlaceholder('年龄', { exact: true }).fill('26');
  await page.getByPlaceholder('种族', { exact: true }).fill('人族');
  await page.getByPlaceholder('例：青梧宗外门 · 杂役弟子').fill('执灯城守夜塔 · 末代守灯人');
  await page.getByPlaceholder('例：瘦长个 · 旧道袍').fill('瘦削挺拔 · 眼底有星屑状光斑 · 旧棉袍');
  await page.getByPlaceholder('例：说话慢半拍 · 口头禅').fill('语速慢 · 爱用灯谜打比方 · 紧张时摸袖口');
  await page.getByPlaceholder('出身与来路').fill('祖母是拾遗巷灯匠，自幼随祖母守着老宅地下那扇星尘之门；祖母去世后接下守灯印，才发现每代守灯人以记忆续灯的真相。');
  await page.getByPlaceholder('在故事里干什么——主角必填').fill('主角：从守灯人成长为重燃九陆星桥的人，代价是与所爱之人的记忆逐一告别');
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(EV, 't32_char_basic_filled.png') });

  // 六层认知：点击「还没写——展开补这一层的核心一句」展开后填
  const cogTexts = [
    '世界是九座会坠落的浮陆，星光是唯一的秩序',
    '我只是个守灯的，替祖母把灯守住',
    '记忆比命重——人可以死，不能忘了为什么活',
    '点灯术照明与引焰，能以记忆点燃星光开路',
    '先护人后理事；遇险先把自己的灯拧亮半分',
    '身边只剩祖母的老宅与一只不肯走的橘猫，城邦正在盯上老宅地契',
  ];
  const expanders = page.getByText('还没写——展开补这一层的核心一句');
  const n = await expanders.count();
  out.expanders = n;
  for (let i = 0; i < Math.min(n, 6); i++) {
    await expanders.nth(i).click();
    await page.waitForTimeout(350);
    // 展开区新出现的输入框：找最近的可编辑元素
    const filled = await page.evaluate(`(() => {
      const tas = [...document.querySelectorAll('textarea, input[type=text]')].filter(e => e.offsetParent !== null && !e.value && e.placeholder !== '搜名字 / 别名');
      return tas.length;
    })()`);
    out['emptyInputsAfterExpand' + i] = filled;
    // 填最后出现的空输入框（认知行内）
    const inputs = page.locator('textarea, input[type=text]');
    const total = await inputs.count();
    for (let j = total - 1; j >= 0; j--) {
      const el = inputs.nth(j);
      const vis = await el.isVisible().catch(() => false);
      if (!vis) continue;
      const val = await el.inputValue().catch(() => 'x');
      const ph = await el.getAttribute('placeholder').catch(() => '');
      if (!val && !['姓名 / 称号','别名 / 称号（可选）'].includes(ph) && ph !== '搜名字 / 别名' && !['性别','年龄','种族'].includes(ph)) {
        await el.fill(cogTexts[i]);
        out['filledAt' + i] = ph || 'no-ph';
        break;
      }
    }
    await page.waitForTimeout(250);
  }
  await page.screenshot({ path: path.join(EV, 't33_char_cog_filled.png') });
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})().catch((e) => { console.error('STEP FAILED:', e.message); process.exit(1); });
