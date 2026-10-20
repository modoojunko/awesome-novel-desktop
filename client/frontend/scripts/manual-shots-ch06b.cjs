/* 手册截图：写正文·AI 链路（确认章纲→生成弹窗→流式写入→加工菜单）。
 * 前置：隔离后端 8100＋本地 mock Anthropic 9100；config.json tier=trial。 */
const fs = require("fs");
const { chromium, expect } = require("playwright/test");

const ORIGIN = "http://127.0.0.1:8100";
const IMG = "/Users/modoojunko/Desktop/coding/ai-novel/docs/manual/img";
const CFG = "/tmp/an-manual-shots/data/config.json";
const TOKEN = JSON.parse(fs.readFileSync(CFG, "utf-8")).token;
const CFG_NAME = `演示模型-${Date.now() % 100000}`;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function clearToasts(page) {
  await page.evaluate(() => {
    document
      .querySelectorAll('[class*="Toastify"], [class*="toast"], [role="status"]')
      .forEach((e) => { e.style.display = "none"; });
  });
}

async function main() {
  // 重置 trial 态
  const cfg = JSON.parse(fs.readFileSync(CFG, "utf-8"));
  cfg.tier = "trial";
  cfg.expires_at = "2026-10-11T00:00:00.000Z";
  cfg.entitlement = {
    features: ["settings-ai-fields", "outline-advanced-fields", "ai-generate", "prompt-panel", "ai-model"],
    limits: { max_projects: null },
  };
  fs.writeFileSync(CFG, JSON.stringify(cfg, null, 2));

  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  global.__page = page;
  page.on("pageerror", (e) => console.log("PAGEERROR:", String(e).slice(0, 200)));
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), TOKEN);
  await page.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 0, data: {} } }));

  // 0. 清旧模型配置（避免重名建不上、绑定拿到旧无 models 的配置）
  const cfgList0 = await fetch(`${ORIGIN}/api/v1/api-configs`, { headers: { Authorization: `Bearer ${TOKEN}` } }).then((r) => r.json());
  for (const c of Array.isArray(cfgList0) ? cfgList0 : cfgList0.data?.configs ?? cfgList0.data ?? []) {
    if (String(c.base_url || "").includes("127.0.0.1:9100") && c.id) {
      await fetch(`${ORIGIN}/api/v1/api-configs/${c.id}`, { method: "DELETE", headers: { Authorization: `Bearer ${TOKEN}` } }).catch(() => {});
    }
  }

  // 0. 清旧书
  const list0 = await fetch(`${ORIGIN}/api/novels`, { headers: { Authorization: `Bearer ${TOKEN}` } }).then((r) => r.json());
  for (const n of Array.isArray(list0) ? list0 : []) {
    await fetch(`${ORIGIN}/api/novels/${n.id}`, { method: "DELETE", headers: { Authorization: `Bearer ${TOKEN}` } }).catch(() => {});
  }

  // 1. 建书＋垫卷章
  await page.goto(`${ORIGIN}/#/novels`);
  await page.getByRole("button", { name: "新建作品" }).first().click();
  await page.locator("input#bkTitle").fill("云海剑歌");
  await page.getByRole("button", { name: "创建，去写简介" }).click();
  await page.waitForURL(/#\/novel\/[0-9a-fA-F-]+/);
  global.__novelUrl = page.url();
  const loaded = page.waitForResponse((r) => r.request().method() === "GET" && /\/chapters\/vol-1-ch-1$/.test(r.url()), { timeout: 15000 }).catch(() => null);
  await page.locator(".mtab", { hasText: "写作" }).click();
  await page.locator('[data-od-id="tree-create"] [data-od-id="add-chapter"]').click();
  const chRow = page.locator(".col-tree .ch", { hasText: "第一章" });
  await chRow.waitFor({ timeout: 15000 });
  await chRow.click();
  await loaded;
  await page.getByTestId("og-edit").waitFor({ timeout: 10000 });
  console.log("chapter ready");

  // 2. 填章纲并确认
  await page.getByTestId("og-edit").click();
  await page.locator('textarea[placeholder="这一章写什么，一两句话说清"]').fill("沈砚夜班誊书时发现禁阁封条被人动过，捡到半页来历不明的残纸；巡夜灯笼逼近，他把残页藏进书夹层，第一次起了探禁阁的念头。");
  await page.locator('textarea[placeholder="一个必须发生的变化"]').fill("沈砚从守规矩的抄书人，变成第一次起意探禁阁的人。");
  await page.locator('textarea[placeholder*="是场景不是正文"]').first().fill("夜半抄书坊，沈砚借装睡观察房梁动静；残纸字迹在他掌心浮现——「禁阁第三层，灯下无人」。");
  await page.evaluate(() => document.querySelectorAll("details").forEach((d) => d.setAttribute("open", "")));
  await page.locator("input#wf-ladder").fill("沈砚吹灯装睡，残页贴着心口；窗外巡夜灯笼停在了坊门外。");
  const moodSel = page.locator('label:has-text("主情绪")').locator("xpath=following::select[1]");
  await moodSel.selectOption({ label: "紧张" });
  await page.locator("body").click({ position: { x: 10, y: 500 } });
  await sleep(2000);
  // 确认章纲在编辑态页脚；若 blur 退出了编辑态则先回去
  const confirmBtn = page.getByRole("button", { name: "确认章纲" });
  if (!(await confirmBtn.count())) await page.getByTestId("og-edit").click();
  await confirmBtn.click();
  await sleep(800);
  // 可能有确认弹窗，有就点确认
  const dlgConfirm = page.locator(".modal, [class*=modal], [role=dialog]").getByRole("button", { name: /确认/ }).last();
  if (await dlgConfirm.count()) await dlgConfirm.click().catch(() => {});
  await sleep(1200);
  await clearToasts(page);
  console.log("outline confirmed");

  // 3. 模型配置：添加 mock 端点（配置页路由 /#/config，工作台顶栏无此入口）
  await page.goto(`${ORIGIN}/#/config`);
  await sleep(1200);
  await page.getByRole("button", { name: "添加 API Key" }).first().click();
  await page.getByPlaceholder("例如：主线 · OpenAI").fill(CFG_NAME);
  await page.getByRole("button", { name: /Anthropic/ }).first().click().catch(() => {});
  await page.getByPlaceholder(/api\.anthropic\.com|https:\/\//).fill("http://127.0.0.1:9100");
  await page.getByPlaceholder(/sk-/).fill("sk-mock-demo");
  // 模型 id 输入框（placeholder 或 label 含 模型）
  const modelInput = page.locator('input[placeholder*="模型"], input[placeholder*="claude"], input[placeholder*="deepseek"]').first();
  if (await modelInput.count()) await modelInput.fill("mock-v4");
  await page.getByRole("button", { name: "保存并测试连接" }).click();
  await sleep(2500);
  await page.screenshot({ path: "/tmp/an-manual-shots/model-config.png" });
  console.log("model config saved");
  await clearToasts(page);

  // 3.5 绑定本书模型（建书在先、配模型在后 → 必须显式绑定，否则 write 503 missing_model）
  const novelId = (global.__novelUrl.match(/\/novel\/([0-9a-fA-F-]+)/) || [])[1];
  const cfgList = await fetch(`${ORIGIN}/api/v1/api-configs`, { headers: { Authorization: `Bearer ${TOKEN}` } }).then((r) => r.json());
  const demo = (Array.isArray(cfgList) ? cfgList : cfgList.data?.configs ?? cfgList.data ?? []).find((c) => c.name === CFG_NAME);
  if (demo && novelId) {
    const bind = await fetch(`${ORIGIN}/api/v1/novels/${novelId}/ai-model`, {
      method: "PUT",
      headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
      body: JSON.stringify({ api_config_id: demo.id, model: "mock-v4" }),
    });
    console.log("model bound:", bind.status);
  } else {
    console.log("WARN: bind skipped", !!demo, novelId);
  }

  // 4. 回写作 → 正文清空
  await page.goto(global.__novelUrl);
  await sleep(1500);
  await page.locator(".mtab", { hasText: "写作" }).click();
  await sleep(1000);
  await page.locator(".col-tree .ch", { hasText: "第一章" }).click();
  await sleep(1200);
  await page.getByRole("tab", { name: /^正文/ }).click();
  const hasEdit = await page.getByTestId("prose-edit").count();
  if (hasEdit) {
    await page.getByTestId("prose-edit").click();
    const editor = page.locator(".editor");
    await editor.waitFor({ timeout: 10000 });
    await editor.fill("");
    await page.getByTestId("prose-done").click();
    await sleep(1500);
  }
  console.log("prose cleared");

  // 5. 生成正文：弹窗提示词
  await page.locator(".rail-assist").getByText("生成正文", { exact: false }).first().click();
  await sleep(1000);
  await page.screenshot({ path: `${IMG}/06-gen-prompt-modal.png` });
  await clearToasts(page);
  console.log("prompt modal shot");

  // 6. 触发生成 → 流式写入
  const genBtn = page.getByRole("button", { name: "生成正文" }).last();
  await genBtn.click();
  // 两段式第一段=AI 润色（badge 未润色→已润色）
  await page.getByText("已润色").first().waitFor({ timeout: 25000 }).catch(() => {});
  await sleep(800);
  // 第二段=正式生成，流式追加正文
  await page.getByRole("button", { name: "生成正文" }).last().click().catch(() => {});
  const editor = page.locator(".editor");
  const editorOrProse = (await editor.count()) ? editor : page.locator(".prose-pane, [class*=prose]").first();
  const baseLen = await editorOrProse.evaluate((el) => (el.textContent || "").length).catch(() => 0);
  for (let i = 0; i < 80; i++) {
    const len = await editorOrProse.evaluate((el) => (el.textContent || "").length).catch(() => 0);
    if (len > baseLen + 120) break;
    await sleep(150);
  }
  await sleep(500);
  await page.screenshot({ path: `${IMG}/06-gen-streaming.png` });
  console.log("streaming shot");
  // 等流式结束（正文长度稳定 3 次）
  let last = -1, stable = 0;
  for (let i = 0; i < 120 && stable < 3; i++) {
    const len = await editorOrProse.evaluate((el) => (el.textContent || "").length).catch(() => 0);
    if (len === last) stable++;
    else { stable = 0; last = len; }
    await sleep(300);
  }
  await sleep(800);
  await clearToasts(page);
  // 关生成弹窗（Esc），退阅读态拍完成帧
  await page.keyboard.press("Escape").catch(() => {});
  await sleep(800);
  await page.getByTestId("prose-done").click().catch(() => {});
  await sleep(1500);
  await clearToasts(page);
  await page.screenshot({ path: `${IMG}/06-gen-done.png` });
  console.log("gen done shot, len=", last);

  // 7. 段落加工菜单：编辑态选中一段
  await page.getByTestId("prose-edit").click().catch(() => {});
  await page.locator(".editor").waitFor({ timeout: 8000 }).catch(() => {});
  // 真实鼠标拖选（合成 Range 不进 ProseMirror 状态）
  const p2 = page.locator(".editor p").nth(1);
  let box = null;
  try { box = await p2.boundingBox({ timeout: 4000 }); } catch {}
  if (!box) { try { box = await page.locator(".editor p").first().boundingBox({ timeout: 4000 }); } catch {} }
  if (!box) { try { box = await page.locator(".editor").boundingBox({ timeout: 4000 }); } catch {} }
  if (box) {
    await page.mouse.move(box.x + 20, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width - 30, box.y + box.height / 2, { steps: 10 });
    await page.mouse.up();
  }
  await sleep(900);
  // 选中后右栏自动展开加工动作，不需要点击行（点击反而收起）
  await page.locator(".rail-assist").getByText("场景扩写", { exact: false }).first().waitFor({ timeout: 6000 }).catch(() => {});
  await sleep(500);
  await page.screenshot({ path: `${IMG}/06-polish-menu.png` });
  console.log("polish menu shot");

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
