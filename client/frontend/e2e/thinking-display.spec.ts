// c-thinking-display 全链 e2e（任务 3.5）：真后端（uvicorn 隔离栈）＋假 MiniMax
// 上游（anthropic thinking_delta→text_delta 流式）驱动真实生成链路，断言四态：
//   ① 思考面板让位占位行 ② 首字转收起条＋回看抽屉 ③ 完成账目行＋正文零思考
// 隔离栈拓扑（e2e-iso-stack-traps）：显式 127.0.0.1、专属端口（vite 5174→uvicorn
// 8399→fake 8398）、私有 DATA_ROOT；鉴权走 config.json token＋localStorage 同值。
import { test, expect, type Page } from "@playwright/test";

const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
const TOKEN = "e2e-think-token";
const THINK_TEXT = "这一章的落点：沈砚第一次起意探禁阁";
const PROSE_HEAD = "夜雨落在抄书坊的青瓦上";

async function api(page: Page, m: string, p: string, b?: unknown) {
  const r = await page.request.fetch(`${ORIGIN}${p}`, {
    method: m,
    headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
    data: b === undefined ? undefined : JSON.stringify(b),
  });
  expect(r.status(), `${m} ${p} → ${await r.text()}`).toBeLessThan(300);
  return r.json();
}

test("思考呈现全链：面板让位→收起条回看→正文零思考", async ({ page }) => {
  test.setTimeout(180_000);
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), TOKEN);
  await page.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 0, data: {} } }));

  // 种子：配置→书→卷→章→绑定模型（全 API，同前端同链路）
  const cfg = await api(page, "POST", "/api/v1/api-configs", {
    name: `e2e-mm-${Date.now() % 100000}`,
    vendor_id: "openai-compat",
    vendor_display_name: "OpenAI 兼容",
    api_format: "anthropic",
    api_key: "sk-fake-minimax",
    base_url: "http://127.0.0.1:8398/anthropic",
    models: ["MiniMax-M3.1-Flash"],
  });
  const cfgId = cfg.id as string;

  await page.goto(`${ORIGIN}/#/novels`);
  await page.getByRole("button", { name: "新建作品" }).first().click();
  await page.locator("input#bkTitle").fill("思考呈现e2e");
  await page.getByRole("button", { name: "创建，去定题材" }).click();
  await page.waitForURL(/#\/novel\/[0-9a-fA-F-]+/);
  const pid = page.url().match(/#\/novel\/([0-9a-fA-F-]+)/)![1];
  await page.locator(".mtab", { hasText: "写作" }).click();
  await page.locator('[data-od-id="tree-create"] [data-od-id="add-chapter"]').click();
  const chRow = page.locator(".col-tree .ch", { hasText: "第一章" });
  await chRow.waitFor({ timeout: 20000 });
  await chRow.click();
  await page.getByRole("tab", { name: /^正文/ }).click();

  await api(page, "PUT", `/api/v1/novels/${pid}/ai-model`, {
    api_config_id: cfgId,
    model: "MiniMax-M3.1-Flash",
  });

  // 真实入口：右栏「生成正文」→提示词弹窗→「生成正文」
  await page.locator(".rail-assist").getByText(/AI 生成正文|生成正文/).first().click();
  await page
    .getByRole("button", { name: "生成正文" })
    .last()
    .click({ timeout: 10000 });

  // ① 面板让位：思考面板在场、占位行退场、模型名与思考内容呈现
  const panel = page.getByTestId("think-panel");
  await expect(panel).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId("gen-line")).toHaveCount(0);
  await expect(panel).toContainText("思考过程");
  await expect(panel).toContainText("MiniMax-M3.1-Flash");
  await expect(panel).toContainText(THINK_TEXT.slice(0, 3));

  // ② 首字到达：面板收起为收起条，抽屉可展开回看全量思考
  const bar = page.getByTestId("think-bar");
  await expect(bar).toBeVisible({ timeout: 60000 });
  await expect(page.getByTestId("think-panel")).toHaveCount(0);
  await bar.click();
  const drawer = page.getByTestId("think-drawer");
  await expect(drawer).toContainText(THINK_TEXT);

  // ③ 完成：账目行补齐；编辑器正文零思考混入
  await expect(bar).toContainText("本章生成完毕", { timeout: 60000 });
  await expect(drawer).toContainText(/正文 \d+ 字/);
  const prose = await page.locator(".editor").textContent();
  expect(prose).toContain(PROSE_HEAD);
  expect(prose).not.toContain(THINK_TEXT);
  // 字数不含思考（编辑器字数＝正文本身）
  const status = await page.locator(".editor-status").textContent();
  expect(status).not.toContain(String(THINK_TEXT.length));
});
