/* 思考呈现原型底稿抓取：独立栈 5291→8101（假 MiniMax 8102），种书→章纲→正文→
   点生成正文，在假流式的思考期/写作期分别抓 DOM+CSS+截图。 */
const fs = require("fs");
const { execSync } = require("child_process");
const { chromium } = require("playwright/test");

const ORIGIN = "http://localhost:5317";
const OUT = "/Users/modoojunko/Desktop/coding/ai-novel/docs/design-c/drafts/thinkproto-captures";
const TOKEN = "proto-think-token-2026";
const DB = "/tmp/proto-think-data/novel-dev.db";

const PROSE = `夜雨落在抄书坊的青瓦上，像无数细小的指节在敲门。

沈砚把最后一摞书册搬回架上，指尖在《云海潮生志》的书脊上停了停。封皮内衬的夹层里，藏着半页不属于任何名录的残纸——三日前誊抄时，它从禁阁的方向随风飘到他脚边，像一片不肯落地的灰蝶。

坊规第一条：禁阁方向的物件，捡到即焚。他本该焚的。

灯芯爆了个火花。沈砚回头看了一眼门房的方向，把残页重新塞进夹层，动作快得连他自己都心惊。这一晚他抄完了十二页经注，比平日多了四页——多出来的四页，是为了让自己的手忙起来，忙到不去想禁阁方向那道被人动过的封条。

子时的梆子响过，巡夜的灯笼从巷口浮上来。沈砚吹了灯，在黑暗中睁着眼。怀中残页贴着心口，比想象中更凉，也更烫。`;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function grab(page, tag) {
  const { css, host } = await page.evaluate(() => ({
    css: Array.from(document.querySelectorAll("style"))
      .map((s) => s.textContent)
      .join("\n/*──style分界──*/\n"),
    host: (document.querySelector(".app-shell") || document.body).outerHTML,
  }));
  fs.writeFileSync(`${OUT}/css-${tag}.css`, css);
  fs.writeFileSync(`${OUT}/dom-${tag}.html`, host);
  await page.screenshot({ path: `${OUT}/shot-${tag}.png` });
  console.log(`grabbed ${tag} (css=${css.length} host=${host.length})`);
}

async function waitSaved(page) {
  await page
    .locator("text=已自动保存")
    .first()
    .waitFor({ timeout: 12000 })
    .catch(() => sleep(2000));
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const b = await chromium.launch();
  const ctx = await b.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
  });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => console.log("PAGEERROR:", String(e).slice(0, 200)));
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), TOKEN);

  // 0. 清旧书（软删除），保证书架只有一本
  await page.goto(`${ORIGIN}/#/novels`);
  await sleep(1500);
  const list0 = await page.evaluate(async () => {
    const r = await fetch("/api/novels", { headers: { Authorization: `Bearer ${localStorage.getItem("auth_token")}` } });
    return r.json();
  });
  for (const n of Array.isArray(list0) ? list0 : (list0.data?.novels ?? list0.data ?? [])) {
    if (n.id) await page.evaluate(async (id) => {
      await fetch(`/api/novels/${id}`, { method: "DELETE", headers: { Authorization: `Bearer ${localStorage.getItem("auth_token")}` } });
    }, n.id).catch(() => {});
  }
  console.log("old novels cleaned");

  // 1. 建书
  await page.goto(`${ORIGIN}/#/novels`);
  await page.getByRole("button", { name: "新建作品" }).first().click();
  await page.locator("input#bkTitle").fill("云海剑歌");
  await page.getByRole("button", { name: "创建，去写简介" }).click();
  await page.waitForURL(/#\/novel\/[0-9a-fA-F-]+/);
  const novelId = page.url().match(/#\/novel\/([0-9a-fA-F-]+)/)[1];
  console.log("novel:", novelId);

  // 2. 写作视图 + 第一卷一章
  await page.locator(".mtab", { hasText: "写作" }).click();
  await page.locator('[data-od-id="tree-create"] [data-od-id="add-chapter"]').click();
  const chRow = page.locator(".col-tree .ch", { hasText: "第一章" });
  await chRow.waitFor({ timeout: 15000 });
  await chRow.click();
  await page.getByTestId("og-edit").waitFor({ timeout: 10000 });

  // 3. 章纲必填格
  await page.getByTestId("og-edit").click();
  await page.locator('textarea[placeholder="这一章写什么，一两句话说清"]')
    .fill("沈砚夜班誊书时发现禁阁封条被人动过，捡到半页来历不明的残纸；巡夜灯笼逼近，他把残页藏进书夹层，第一次起了探禁阁的念头。");
  await page.evaluate(() =>
    document.querySelectorAll("details").forEach((d) => d.setAttribute("open", "")),
  );
  await page.locator("input#wf-ladder").fill("沈砚吹灯装睡，残页贴着心口；窗外巡夜灯笼停在了坊门外。");
  await page.locator("input#wf-wt").fill("1800").catch(() => {});
  await page.locator('textarea[placeholder="一个必须发生的变化"]')
    .fill("沈砚从守规矩的抄书人，变成第一次起意探禁阁的人。").catch(() => {});
  await page.locator('label:has-text("主情绪")').locator("xpath=following::select[1]")
    .selectOption({ label: "紧张" }).catch(() => {});
  await page.locator("body").click({ position: { x: 10, y: 500 } });
  await sleep(2200);
  await waitSaved(page);
  console.log("outline saved");

  // 4. 正文编辑态：敲入正文，抓「编辑态」底稿
  await page.getByRole("tab", { name: /^正文/ }).click();
  await page.getByTestId("prose-edit").click();
  const editor = page.locator(".editor");
  await editor.waitFor({ timeout: 10000 });
  await editor.click();
  await page.keyboard.insertText(PROSE);
  await sleep(1500);
  await waitSaved(page);
  await grab(page, "workbench-editing");

  // 5. 把假模型绑到这本书（ novels.ai_model 直种 ）
  execSync(
    `sqlite3 ${DB} "UPDATE novels SET ai_model='MiniMax-M3.1-Flash', ai_config_id='f0e1d2c3-0000-4000-8000-000000000001' WHERE id='${novelId}'; SELECT ai_model, ai_config_id FROM novels WHERE id='${novelId}';"`,
  );
  console.log("ai_model bound");

  // 6. 点生成正文 → 过「清空重写」确认门禁 → 思考期（+10s）与写作期（+30s）各抓一份
  await page.locator(".rail-assist").getByText(/AI 生成正文|生成正文/).first().click();
  await page
    .getByRole("button", { name: "继续生成" })
    .click({ timeout: 4000 })
    .then(() => console.log("regen confirm passed"))
    .catch(() => console.log("no regen confirm (empty chapter)"));
  // 提示词预览弹窗（AI 生成正文 ★PRO）里的「生成正文」才是真触发
  await page
    .locator(".mcard .vbtn, .mcard button")
    .filter({ hasText: /生成正文/ })
    .last()
    .click({ timeout: 8000 })
    .then(() => console.log("prompt modal generate clicked"))
    .catch(() => console.log("no prompt modal"));
  await sleep(9000);
  await grab(page, "wait-thinking");
  await sleep(8500);
  await grab(page, "mid-writing");
  await sleep(12000);
  await grab(page, "done-editing");

  // 7. 等完成 → 阅读态底稿
  await waitSaved(page);
  await sleep(4000);
  await page.getByTestId("prose-done").click().catch(() => console.log("prose-done not found (maybe already reading)"));
  await sleep(1200);
  await waitSaved(page);
  await grab(page, "workbench-reading");

  await b.close();
  console.log("ALL CAPTURES DONE");
}

main().catch(async (e) => {
  console.error("CAPTURE FAIL:", String(e).slice(0, 500));
  process.exit(1);
});
