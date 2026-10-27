import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page } from "@playwright/test";
import {
  addFirstChapterViaTree,
  cleanupSessionNovels,
  stableClick,
} from "./helpers";

// =========================================================================
// 正文纸面填屏（c-paper-empty-fill，2026-10-24 用户反馈）
//   病灶：查看态纸随内容高——空章只剩上下纸边距（36+56）那一条白条，
//   桌面上像一片碎纸屑。约定：纸是这张桌上的一张纸，任何态都至少
//   撑满可视桌面；内容超一屏照常滚动（纸型＝A 连续纸的 10-22 拍板不变）。
//   三态几何断言（c-stream-ring-width 判例：flex 链改动须空/短/长三态实测）：
//   空（查看＋编辑）/ 短 / 长。
// =========================================================================
// 与 free-writing-flow.spec.ts 共享鉴权手法：S端 真实注册登录 → 写 docker 容器的
// config.json（tier="none"）→ localStorage 注入 auth_token。docker 服务需已启动。

const S_API = process.env.E2E_S_API || "http://127.0.0.1:19000/api/web";
const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
const CONFIG_PATH = path.join(
  process.cwd(),
  "..",
  "..",
  ".docker-data",
  "client",
  "config.json",
);

/** S端 注册并登录，返回 JWT（免费用户，套餐 none）。 */
async function sRegisterAndLogin() {
  const name = `e2e_paper_${Date.now()}_${randomUUID().slice(0, 8)}`;
  const password = "Test" + "Pass789!";
  const reg = await fetch(`${S_API}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: name,
      password,
      security_question: "最喜欢的颜色",
      security_answer: "蓝色",
    }),
  });
  const regBody = await reg.json();
  if (regBody.code !== 0) {
    throw new Error(`S端 register 失败: ${JSON.stringify(regBody)}`);
  }
  const login = await fetch(`${S_API}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: name, password }),
  });
  const loginBody = await login.json();
  if (loginBody.code !== 0) {
    throw new Error(`S端 login 失败: ${JSON.stringify(loginBody)}`);
  }
  return { token: loginBody.data.token as string, username: name };
}

/** 免费会话：tier="none" 写入 docker config.json，返回恢复函数。 */
function writeFreeSession(t: string, u: string) {
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = t;
  cfg.username = u;
  cfg.tier = "none";
  delete cfg.expires_at;
  cfg.last_login_at = new Date().toISOString();
  cfg.pc_hash = randomUUID().replace(/-/g, "");
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2));
  return () => fs.writeFileSync(CONFIG_PATH, original);
}

async function setupFreeSession(page: Page): Promise<{ restore: () => void }> {
  const { token, username } = await sRegisterAndLogin();
  const restoreConfig = writeFreeSession(token, username);
  const restore = async () => {
    await cleanupSessionNovels(ORIGIN, token);
    restoreConfig();
  };
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  await page.route("**/api/auth/check-auth", (r) =>
    r.fulfill({ json: { code: 0, data: {} } }),
  );
  return { restore };
}

/** 通过真实 UI 创建小说（免费限 1 部，测试内仅建一本）。 */
async function createNovel(page: Page, name: string): Promise<string> {
  await page.goto(`${ORIGIN}/#/novels`);
  await stableClick(page.getByRole("button", { name: "新建作品" }).first());
  await page.locator("input#bkTitle").fill(name);
  await page.getByRole("button", { name: "创建，去定题材" }).click();
  await page.waitForURL(/#\/novel\/[0-9a-fA-F-]+/);
  await page.locator(".mtab", { hasText: "写作" }).click();
  await expect(page.locator(".mtab.on")).toContainText("写作");
  const m = page.url().match(/\/novel\/([0-9a-fA-F-]+)/);
  if (!m) throw new Error(`无法解析 novel id: ${page.url()}`);
  return m[1];
}

/** 量纸：wrap 可视高 / 纸高 / 滚动余量（真实布局，jsdom 给不了）。 */
async function measurePaper(page: Page) {
  return page.evaluate(() => {
    const wrap = document.querySelector(".editor-wrap");
    const paper = document.querySelector(".prose-paper");
    if (!wrap || !paper) throw new Error("editor-wrap / prose-paper 不在场");
    return {
      editing: wrap.classList.contains("editing"),
      wrapClient: wrap.clientHeight,
      paperH: paper.getBoundingClientRect().height,
      scrollTop: wrap.scrollTop,
      scrollMax: wrap.scrollHeight - wrap.clientHeight,
    };
  });
}

/** 纸撑满可视桌面：纸高＝wrap 可视高 − 上下纸外距（36+56），±2px 布局容差。 */
async function expectPaperFills(page: Page) {
  const m = await measurePaper(page);
  expect(
    Math.abs(m.paperH + 92 - m.wrapClient),
    `纸高 ${m.paperH} + 外距 92 应≈可视高 ${m.wrapClient}（editing=${m.editing}）`,
  ).toBeLessThanOrEqual(2);
}

async function enterEdit(page: Page) {
  await page.getByTestId("prose-edit").click();
  await expect(page.getByTestId("prose-done")).toBeVisible({ timeout: 10000 });
}

async function exitEdit(page: Page) {
  await page.getByTestId("prose-done").click();
  await expect(page.getByTestId("prose-edit")).toBeVisible({ timeout: 10000 });
}

test("纸面填屏三态：空章不塌、短章撑满、长章照常滚动", async ({ page }) => {
  const { restore } = await setupFreeSession(page);
  try {
    await createNovel(page, `纸屏${Date.now() % 100000}`);
    await addFirstChapterViaTree(page);
    await page.getByRole("tab", { name: /^正文/ }).click();
    await expect(page.getByTestId("prose-edit")).toBeVisible({ timeout: 10000 });

    // ── 空章 · 查看态（病灶现场）：纸至少撑满可视桌面，不再只剩纸边距一条 ──
    await expectPaperFills(page);

    // ── 空章 · 编辑态：同样撑满（既有约定回归钉）──
    await enterEdit(page);
    await expectPaperFills(page);

    // ── 短章：查看态仍撑满（纸不随内容塌回一条）──
    const editor = page.locator(".editor");
    await editor.fill("天还没亮，刀先出了鞘。");
    await expect(page.getByText("已自动保存").first()).toBeVisible({ timeout: 8000 });
    await exitEdit(page);
    await expectPaperFills(page);

    // ── 长章：纸随内容长过可视区（连续纸），滚动到底可达 ──
    await enterEdit(page);
    await editor.fill("夜风把灯焰压得很低。".repeat(400)); // 3600 字单段，稳超一屏
    await expect(page.getByText("已自动保存").first()).toBeVisible({ timeout: 8000 });
    await exitEdit(page);
    const long = await measurePaper(page);
    expect(long.paperH, "长文纸高应长过可视区（连续纸不设上限）").toBeGreaterThan(
      long.wrapClient,
    );
    expect(long.scrollMax, "长文应可滚（滚动容器仍是 wrap）").toBeGreaterThan(0);
    await page.locator(".editor-wrap").evaluate((el) => {
      el.scrollTop = el.scrollHeight;
    });
    const atBottom = await measurePaper(page);
    expect(atBottom.scrollTop).toBeGreaterThan(0);
  } finally {
    await restore();
  }
});
