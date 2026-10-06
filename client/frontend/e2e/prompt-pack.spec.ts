import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page } from "@playwright/test";
import { cleanupSessionNovels, stableClick } from "./helpers";

/**
 * c-prompt-pack-client 6.1 · 写作能力（提示词包）四态卡 E2E。
 *
 * 口径（design D5 状态×界面矩阵）：
 * - ready / syncing＝全静默（卡不渲染）；
 * - failed→「重新获取」＋「复制诊断信息」；
 * - tier_denied→「该能力随 MAX 提供」＋去升级（走 member-block 全局升级出口）；
 * - missing→登录语义卡（已登录显示重新获取）；
 * - 「重新获取」→ /prompt-pack/check 触发＋1s 轮询 status，ready 后卡片消失。
 *
 * 打桩口径与 expiry-notice 同源（verify 桩驱动；本地 prompt-pack 端点桩避免真同步）。
 * 真链（假 CDN＋测试签名钥的 force 模式）见 backend 侧 test_prompt_pack_sync。
 */

const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
const S_API = process.env.E2E_S_API || "http://127.0.0.1:19000/api/web";
const CONFIG_PATH = path.join(
  process.env.E2E_CLIENT_DATA || path.join(process.cwd(), "..", "..", ".docker-data", "client"),
  "config.json",
);
const TEST_PASSWORD = ["TestPass", "789!"].join("");

type PackStub = { phase: string; reason?: string; tier?: string; version?: string };

async function sRegisterAndLogin() {
  const name = `e2e_pack_${Date.now()}_${randomUUID().slice(0, 8)}`;
  const reg = await fetch(`${S_API}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: name,
      password: TEST_PASSWORD,
      security_question: "最喜欢的颜色",
      security_answer: "蓝色",
    }),
  });
  const regBody = await reg.json();
  if (regBody.code !== 0) throw new Error(`S端 register 失败: ${JSON.stringify(regBody)}`);
  const login = await fetch(`${S_API}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: name, password: TEST_PASSWORD }),
  });
  const loginBody = await login.json();
  if (loginBody.code !== 0) throw new Error(`S端 login 失败: ${JSON.stringify(loginBody)}`);
  return { token: loginBody.data.token as string, username: name };
}

async function writeOAuthSession(t: string, u: string) {
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = t;
  cfg.username = u;
  cfg.tier = "pro";
  delete cfg.expires_at;
  cfg.last_login_at = new Date().toISOString();
  cfg.pc_hash = randomUUID().replace(/-/g, "");
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2));
  return () => fs.writeFileSync(CONFIG_PATH, original);
}

/** verify / check-auth / prompt-pack 本地端点全桩；packStub 可随轮次变化。 */
async function stubPack(page: Page, packStub: () => PackStub, statusStub?: () => PackStub) {
  const verify = () => ({
    valid: true,
    tier: "pro",
    is_member: true,
    expired: false,
    trial_remaining_days: 0,
    prompt_pack: packStub(),
  });
  await page.route("**/api/auth/verify", (r) => r.fulfill({ json: verify() }));
  await page.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 0, data: {} } }));
  await page.route("**/api/prompt-pack/check", (r) => r.fulfill({ json: { started: true } }));
  await page.route("**/api/prompt-pack/status", (r) =>
    r.fulfill({ json: (statusStub ?? packStub)() }),
  );
}

async function seedBook(page: Page, token: string): Promise<string> {
  const auth = { Authorization: `Bearer ${token}` };
  await page.goto(`${ORIGIN}/#/novels`);
  await stableClick(page.getByRole("button", { name: "新建作品" }).first());
  await page.locator("input#bkTitle").fill(`e2e-pack-${Date.now()}`);
  await page.getByRole("button", { name: "创建，去写简介" }).click();
  await page.waitForURL(/#\/novel\/[0-9a-fA-F-]+/);
  const pid = page.url().match(/#\/novel\/([0-9a-fA-F-]+)/)![1];
  const base = `${ORIGIN}/api/novels/${pid}`;
  await fetch(`${base}/volumes`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({ title: "第一卷" }),
  });
  await fetch(`${base}/volumes/vol-1/chapters`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({ title: "渡口" }),
  });
  return pid;
}

async function enterChapter(page: Page) {
  await page.reload();
  await page.locator(".mtab", { hasText: "写作" }).click();
  await page.locator(".col-tree .ch").first().click();
}

test.describe("写作能力四态卡", () => {
  test("failed：重新获取→轮询到 ready 后卡片消失（全静默）", async ({ page }) => {
    test.setTimeout(120_000);
    const { token, username } = await sRegisterAndLogin();
    const restore = await writeOAuthSession(token, username);
    try {
      let st: PackStub = { phase: "failed", reason: "cdn_unreachable" };
      await stubPack(
        page,
        () => ({ ...st, tier: "pro", version: "7" }),
        () => ({ ...st, tier: "pro", version: "7" }),
      );
      await seedBook(page, token);
      await enterChapter(page);

      const card = page.getByTestId("pack-card");
      await expect(card).toBeVisible({ timeout: 15000 });
      await expect(card).toContainText("写作能力没有就绪");

      // 点「重新获取」后 status 转 ready → 轮询命中 → 卡消失
      st = { phase: "ready", version: "7" };
      await card.getByRole("button", { name: "重新获取" }).click();
      await expect(page.getByTestId("pack-card")).toBeHidden({ timeout: 20000 });
    } finally {
      await cleanupSessionNovels(ORIGIN, token);
      restore();
    }
  });

  test("tier_denied：去升级走 member-block 全局升级出口", async ({ page }) => {
    test.setTimeout(120_000);
    const { token, username } = await sRegisterAndLogin();
    const restore = await writeOAuthSession(token, username);
    try {
      await stubPack(page, () => ({ phase: "tier_denied", reason: "tier" }));
      await seedBook(page, token);
      await enterChapter(page);

      const card = page.getByTestId("pack-card");
      await expect(card).toBeVisible({ timeout: 15000 });
      await expect(card).toContainText("该能力随 MAX 提供");
      await card.getByRole("button", { name: "去升级" }).click();
      await expect(page.locator(".modal", { hasText: "PRO 专属功能" })).toBeVisible({
        timeout: 10000,
      });
    } finally {
      await cleanupSessionNovels(ORIGIN, token);
      restore();
    }
  });

  test("ready：全静默（卡不渲染）", async ({ page }) => {
    test.setTimeout(120_000);
    const { token, username } = await sRegisterAndLogin();
    const restore = await writeOAuthSession(token, username);
    try {
      await stubPack(page, () => ({ phase: "ready", version: "7" }));
      await seedBook(page, token);
      await enterChapter(page);

      await expect(page.locator(".rail-assist").first()).toBeVisible({ timeout: 15000 });
      await expect(page.getByTestId("pack-card")).toHaveCount(0);
    } finally {
      await cleanupSessionNovels(ORIGIN, token);
      restore();
    }
  });
});
