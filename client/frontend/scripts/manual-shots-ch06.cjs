/* 手册截图播种脚本（一次性）：独立环境 8100，播一本书→卷→章→章纲→正文，拍 5 张图。 */
const fs = require("fs");
const { chromium, expect } = require("playwright/test");

const ORIGIN = "http://127.0.0.1:8100";
const IMG = "/Users/modoojunko/Desktop/coding/ai-novel/docs/manual/img";
const TOKEN = JSON.parse(
  fs.readFileSync("/tmp/an-manual-shots/data/config.json", "utf-8"),
).token;

const PROSE = `夜雨落在抄书坊的青瓦上，像无数细小的指节在敲门。

沈砚把最后一摞书册搬回架上，指尖在《云海潮生志》的书脊上停了停。封皮内衬的夹层里，藏着半页不属于任何名录的残纸——三日前誊抄时，它从禁阁的方向随风飘到他脚边，像一片不肯落地的灰蝶。

坊规第一条：禁阁方向的物件，捡到即焚。他本该焚的。

灯芯爆了个火花。沈砚回头看了一眼门房的方向，把残页重新塞进夹层，动作快得连他自己都心惊。这一晚他抄完了十二页经注，比平日多了四页——多出来的四页，是为了让自己的手忙起来，忙到不去想禁阁方向那道被人动过的封条。

子时的梆子响过，巡夜的灯笼从巷口浮上来。沈砚吹了灯，在黑暗里睁着眼。怀中残页贴着心口，比想象中更凉，也更烫。`;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** 截图前藏 toast（display:none，不可 remove——React 卸载时 removeChild 崩树） */
async function clearToasts(page) {
  await page.evaluate(() => {
    document
      .querySelectorAll(
        '[class*="Toastify"], [class*="toast"], [class*="Toast"], [role="status"]',
      )
      .forEach((e) => { e.style.display = "none"; });
  });
}

/** 等底栏保存指示从「未保存」回到「已自动保存」 */
async function waitSaved(page, timeout = 12000) {
  await page
    .locator("text=已自动保存")
    .first()
    .waitFor({ timeout })
    .catch(async () => {
      await sleep(2000);
    });
  await clearToasts(page);
}

async function main() {
  const b = await chromium.launch();
  const ctx = await b.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
  });
  const page = await ctx.newPage();
  global.__page = page;
  page.on("pageerror", (err) => console.log("PAGEERROR:", String(err).slice(0, 300)));
  page.on("console", (m) => {
    if (m.type() === "error") console.log("CONSOLE-ERR:", m.text().slice(0, 200));
  });
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), TOKEN);
  await page.route("**/api/auth/check-auth", (r) =>
    r.fulfill({ json: { code: 0, data: {} } }),
  );

  // 0. 清掉本环境里的旧测试书（软删除），保证书架只有一本
  const list0 = await fetch(`${ORIGIN}/api/novels`, {
    headers: { Authorization: `Bearer ${TOKEN}` },
  }).then((r) => r.json());
  for (const n of Array.isArray(list0) ? list0 : (list0.data?.novels ?? list0.data ?? [])) {
    if (n.id)
      await fetch(`${ORIGIN}/api/novels/${n.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${TOKEN}` },
      }).catch(() => {});
  }

  // 1. 建书
  await page.goto(`${ORIGIN}/#/novels`);
  await page.getByRole("button", { name: "新建作品" }).first().click();
  await page.locator("input#bkTitle").fill("云海剑歌");
  await page.getByRole("button", { name: "创建，去写简介" }).click();
  await page.waitForURL(/#\/novel\/[0-9a-fA-F-]+/);
  console.log("novel created");

  // 2. 写作视图 + 垫第一卷一章
  const loaded = page
    .waitForResponse(
      (r) => r.request().method() === "GET" && /\/chapters\/vol-1-ch-1$/.test(r.url()),
      { timeout: 15000 },
    )
    .catch(() => null);
  await page.locator(".mtab", { hasText: "写作" }).click();
  await page.locator('[data-od-id="tree-create"] [data-od-id="add-chapter"]').click();
  const chRow = page.locator(".col-tree .ch", { hasText: "第一章" });
  await chRow.waitFor({ timeout: 15000 });
  await chRow.click();
  await loaded;
  await page.getByTestId("og-edit").waitFor({ timeout: 10000 });
  console.log("chapter ready");

  // 3. 编辑章纲：填关键格
  await page.getByTestId("og-edit").click();
  const field = (label) =>
    page
      .locator("em", { hasText: label })
      .locator("xpath=ancestor::div[contains(@class,'field') or contains(@class,'og-field')][1]");

  const summary = page.locator('textarea[placeholder="这一章写什么，一两句话说清"]');
  await summary.fill("沈砚夜班誊书时发现禁阁封条被人动过，捡到半页来历不明的残纸；巡夜灯笼逼近，他把残页藏进书夹层，第一次起了探禁阁的念头。");

  // 挑战/落点在默认收起的 details 组里，先全展开
  await page.evaluate(() =>
    document.querySelectorAll("details").forEach((d) => d.setAttribute("open", "")),
  );
  const ladder = page.locator("input#wf-ladder");
  await ladder.fill("沈砚吹灯装睡，残页贴着心口；窗外巡夜灯笼停在了坊门外。");

  const wt = page.locator("input#wf-wt");
  if (await wt.count()) await wt.fill("1800");

  // 必须完成的变化（必填格）
  const change = page.locator('textarea[placeholder="一个必须发生的变化"]');
  if (await change.count()) await change.fill("沈砚从守规矩的抄书人，变成第一次起意探禁阁的人。");

  // 主情绪（必填格，select）
  const moodSel = page
    .locator('label:has-text("主情绪")')
    .locator("xpath=following::select[1]");
  if (await moodSel.count()) await moodSel.selectOption({ label: "紧张" });

  await page.locator("body").click({ position: { x: 10, y: 500 } }); // blur 触发防抖保存
  await sleep(2200);
  await summary.scrollIntoViewIfNeeded();
  await waitSaved(page);
  await page.screenshot({ path: `${IMG}/06-workbench-outline.png` });
  console.log("outline shot done");

  // 4. 正文：编辑态（打字）→ 阅读态
  await page.getByRole("tab", { name: /^正文/ }).click();
  await page.getByTestId("prose-edit").click();
  const editor = page.locator(".editor");
  await editor.waitFor({ timeout: 10000 });
  await editor.click();
  await page.keyboard.type(PROSE.slice(0, 120), { delay: 5 }); // 编辑态截图有字即可
  await page.screenshot({ path: `${IMG}/06-prose-editing.png` });
  await editor.fill("");
  await editor.click();
  await page.keyboard.insertText(PROSE);
  await page.getByTestId("prose-done").click();
  await page.waitForTimeout(1200);
  await waitSaved(page);
  await page.screenshot({ path: `${IMG}/06-prose-reading.png` });
  console.log("prose shots done");

  // 5. 右栏 AI 面板（trial=PRO 态）
  const rail = page.locator(".rail-assist").first();
  if (await rail.count()) {
    await rail.screenshot({ path: `${IMG}/06-ai-panel-pro.png` });
    console.log("pro rail shot done");
  } else {
    console.log("WARN: .rail-assist not found");
  }

  // 6. 免费态：tier 置 none → 重载 → 点 AI 行看升级引导
  const cfgPath = "/tmp/an-manual-shots/data/config.json";
  const cfg = JSON.parse(fs.readFileSync(cfgPath, "utf-8"));
  cfg.tier = "none";
  cfg.entitlement = { features: [], limits: { max_projects: 1 } };
  fs.writeFileSync(cfgPath, JSON.stringify(cfg, null, 2));
  await page.reload();
  await page.getByRole("tab", { name: /^正文/ }).click().catch(() => {});
  await page.waitForTimeout(800);
  if (await rail.count()) {
    const aiRow = rail.getByText(/AI 生成正文|生成正文/).first();
    try {
      await aiRow.click({ timeout: 4000 });
      await page.waitForTimeout(900);
      await page.screenshot({ path: `${IMG}/06-ai-panel-free.png` });
      console.log("free upgrade modal shot done");
    } catch {
      await rail.screenshot({ path: `${IMG}/06-ai-panel-free.png` });
      console.log("free rail fallback shot done");
    }
  }

  await b.close();
}

main().catch(async (e) => {
  console.error("SEED FAIL:", e.message.split("\n")[0]);
  if (global.__page) {
    await global.__page.screenshot({ path: "/tmp/an-manual-shots/fail.png" }).catch(() => {});
    console.log("fail shot saved (live page)");
  }
  process.exit(1);
});
