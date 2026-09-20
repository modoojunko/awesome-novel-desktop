// 数据驱动的章节处理脚本：node fill-chapter.cjs <chapters.json>
// 每章：树中点击 → 填章纲（含主情绪/段落）→ 确认章纲 → 正文 contenteditable 手写 → 验证字数
const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright');
const EV = __dirname;

(async () => {
  const dataFile = process.argv[2];
  const data = JSON.parse(fs.readFileSync(path.join(EV, dataFile), 'utf8'));
  const browser = await chromium.connectOverCDP('http://localhost:9333');
  const ctx = browser.contexts()[0];
  let page = ctx.pages().find((p) => p.url().startsWith('http://localhost:6174'));
  if (!page) { page = await ctx.newPage(); await page.setViewportSize({ width: 1440, height: 900 }); }
  const results = [];

  for (const ch of data.chapters) {
    const r = { title: `卷${ch.vol}-${ch.idx + 1}` };
    try {
      // 树中定位章节：每卷各有一个「第一章/第二章」节点，索引 = 卷号-1
      await page.reload();
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(900);
      const writeTab = page.locator('.mtab').filter({ hasText: '写作' });
      if ((await writeTab.count()) && !(await writeTab.first().getAttribute('class')).includes('on')) {
        await writeTab.first().click();
        await page.waitForTimeout(700);
      }
      const label = ch.idx === 0 ? '第一章' : '第二章';
      const nodes = page.getByText(label, { exact: true });
      const n = await nodes.count();
      const nodeIdx = ch.vol - 1;
      if (n <= nodeIdx) throw new Error('chapter node not found: ' + label + ' count=' + n);
      await nodes.nth(nodeIdx).click();
      await page.waitForTimeout(900);

      // 章纲 tab（默认）——填字段（bodyOnly 跳过）
      if (!ch.bodyOnly) {
      const f = (ph) => page.getByPlaceholder(ph, { exact: true });
      await f('这一章写什么，一两句话说清').fill(ch.summary);
      await f('一个关键事件').fill(ch.event);
      await f('角色名（一行一个）').fill(ch.chars);
      await f('本章主要场景地点').fill(ch.place);
      await f('本章时间背景').fill(ch.time);
      await f('如：第三人称有限').fill(ch.pov);
      await f('视角切换注意事项').fill(ch.povNote);
      await f('这一章必须完成什么').fill(ch.task);
      await f('读者此时的情感状态').fill(ch.reader);
      await f('希望读者如何感受').fill(ch.strategy);
      await f('策略的展开方式与分寸').fill(ch.strategyHow);
      await f('一个必须发生的变化').fill(ch.change);

      // 主情绪 select
      const sel = page.locator('select:visible').first();
      const opts = await sel.locator('option').allTextContents();
      const emo = opts.find(o => o.includes(ch.emotion));
      if (emo) await sel.selectOption({ label: emo });

      // 段落规划（填所有可见的空段落行，规避隐藏模板导致的 strict 冲突）
      const hasRow = await page.locator('textarea[placeholder^="段落概要"]:visible').count();
      if (!hasRow) {
        await page.getByRole('button', { name: '添加段落' }).click();
        await page.waitForTimeout(500);
      }
      const paraRows = page.locator('textarea[placeholder^="段落概要"]:visible');
      const prn = await paraRows.count();
      let filledPara = false;
      for (let i = 0; i < prn; i++) {
        const el = paraRows.nth(i);
        if (!(await el.inputValue()).trim()) {
          await el.fill(ch.para);
          filledPara = true;
          break;
        }
      }
      if (!filledPara && prn === 0) throw new Error('no paragraph row');
      await page.waitForTimeout(400);

      // 确认章纲
      const confirmBtn = page.getByRole('button', { name: '确认章纲' });
      r.confirmEnabled = await confirmBtn.isEnabled();
      if (r.confirmEnabled) {
        await confirmBtn.click();
        await page.waitForTimeout(1200);
      } else { r.confirmBlocked = true; }
      }

      // 正文：点编辑器正文页签（outlineOnly 跳过正文与归档）
      if (!ch.outlineOnly) {
      await page.getByRole('button', { name: /正文/ }).first().click();
      await page.waitForTimeout(700);
      const editor = page.locator('div[contenteditable="true"]:visible, div[contenteditable=""]:visible').first();
      await editor.click();
      await page.waitForTimeout(200);
      await editor.fill(ch.body);
      await page.waitForTimeout(1800); // 等自动保存
      r.wordCount = await page.evaluate(`(() => { const el = [...document.querySelectorAll('*')].find(e => e.children.length === 0 && /\\d+ 字/.test(e.textContent)); return el ? el.textContent.trim() : 'n/a'; })()`);
      r.savedMark = (await page.innerText('body')).includes('已自动保存') ? 'autosaved' : 'check';

      // 归档本章（正文只读，下一章解锁）
      await page.getByRole('button', { name: '归档本章' }).click();
      await page.waitForTimeout(700);
      const archModal = page.locator('.modal.show');
      if (await archModal.count()) {
        await archModal.getByRole('button', { name: '归档本章' }).click();
        await page.waitForTimeout(1800);
        r.archived = (await page.innerText('body')).includes('已归档');
      }
      }
      await page.screenshot({ path: path.join(EV, `ch_${ch.vol}_${ch.idx + 1}.png`) });
      r.ok = true;
    } catch (e) {
      r.ok = false;
      r.error = String(e).slice(0, 200);
      await page.screenshot({ path: path.join(EV, `ch_${ch.vol}_${ch.idx + 1}_FAIL.png`) });
    }
    results.push(r);
  }
  console.log(JSON.stringify(results, null, 2));
  await browser.close();
})().catch((e) => { console.error('DRIVER FAILED:', e.message); process.exit(1); });
