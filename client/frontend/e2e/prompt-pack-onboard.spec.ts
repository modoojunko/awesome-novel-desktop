import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page } from "@playwright/test";
import { stableClick } from "./helpers";

/**
 * c-prompt-pack-onboard-modal 6.1 · 写作能力引导弹窗 E2E。
 *
 * 口径（spec「写作能力引导弹窗」）：
 * - 首装：进入「我的作品」页未装包 → 自动弹窗并立即开始（POST /prompt-pack/check），
 *   分步进度 → 完成提示可关闭（开始写作）；
 * - 更新确认制：探测有新版 → 「当前 vN → 最新 vM」确认弹窗；暂不更新＝不安装不重复
 *   打扰当前停留，再进页面再探测；确认后复用下载安装进度；
 * - 菜单入口：账号面板「数据」组「写作能力」→ 同一弹窗手动检查更新；
 * - running 中途关窗＝纯视觉退出，后台同步不中断。
 *
 * 打桩口径与 prompt-pack.spec 同源（verify/check-auth/prompt-pack 全桩；S端 真注册
 * 种 OAuth 会话）。登录态种 localStorage（AuthGuard 判据；config-page.spec 同款）。
 */

const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
const S_API = process.env.E2E_S_API || "http://127.0.0.1:19000/api/web";
const CONFIG_PATH = path.join(
  process.env.E2E_CLIENT_DATA || path.join(process.cwd(), "..", "..", ".docker-data", "client"),
  "config.json",
);
const TEST_PASSWORD = ["TestPass", "789!"].join("");

/** fail-fast 网络断言（评审后补：后端出错立刻点名，不再挂到用例超时无法定位） */
async function mustOk(r: Response, what: string): Promise<any> {
  const body = await r.json().catch(() => ({}));
  if (!r.ok || (body && typeof body === "object" && "code" in body && body.code !== 0)) {
    throw new Error(`${what} 失败: HTTP ${r.status} ${JSON.stringify(body).slice(0, 300)}`);
  }
  return body;
}

type PackStub = { phase: string; reason?: string; tier?: string; version?: string; step?: string };
type ProbeStub = { installed_version: string; latest_version: string; update_available: boolean; source?: "pack" | "dev" };

async function sRegisterAndLogin() {
  const name = `e2e_pack_modal_${Date.now()}_${randomUUID().slice(0, 8)}`;
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
  const regBody = await mustOk(reg, "S端 register");
  const login = await fetch(`${S_API}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: name, password: TEST_PASSWORD }),
  });
  const loginBody = await mustOk(login, "S端 login");
  return { token: loginBody.data.token as string, username: name };
}

async function writeOAuthSession(t: string, u: string) {
  // 独立数据目录首跑时 config.json 可能尚不存在（后端懒创建）：缺省从空配置起步，
  // 恢复函数据 existed 决定还原或删除（不残留测试配置）
  const existed = fs.existsSync(CONFIG_PATH);
  const original = existed ? fs.readFileSync(CONFIG_PATH, "utf-8") : "{}";
  const cfg = JSON.parse(original);
  cfg.token = t;
  cfg.username = u;
  cfg.tier = "pro";
  delete cfg.expires_at;
  cfg.last_login_at = new Date().toISOString();
  cfg.pc_hash = randomUUID().replace(/-/g, "");
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2));
  return () => {
    if (existed) fs.writeFileSync(CONFIG_PATH, original);
    else fs.rmSync(CONFIG_PATH, { force: true });
  };
}

interface PackRoutes {
  pack?: () => PackStub;
  status: () => PackStub;
  probe?: () => ProbeStub;
}

/** 全桩：登录态种 localStorage＋verify/check-auth/status/probe/check 路由；check 计数。 */
async function stubOnboard(page: Page, token: string, routes: PackRoutes) {
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  const checkCalls = { n: 0 };
  await page.route("**/api/auth/verify", (r) =>
    r.fulfill({
      json: {
        valid: true,
        tier: "pro",
        is_member: true,
        expired: false,
        trial_remaining_days: 0,
        prompt_pack: (routes.pack ?? routes.status)(),
      },
    }),
  );
  await page.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 0, data: {} } }));
  await page.route("**/api/prompt-pack/check", (r) => {
    checkCalls.n += 1;
    return r.fulfill({ json: { started: true } });
  });
  await page.route("**/api/prompt-pack/status", (r) => r.fulfill({ json: routes.status() }));
  await page.route("**/api/prompt-pack/probe", (r) =>
    r.fulfill({
      json: routes.probe?.() ?? {
        installed_version: "",
        latest_version: "",
        update_available: false,
        source: "pack",
      },
    }),
  );
  return checkCalls;
}

test.describe("写作能力引导弹窗（c-prompt-pack-onboard-modal）", () => {
  test("首装：落地作品页自动弹窗开跑，完成提示可关闭", async ({ page }) => {
    test.setTimeout(120_000);
    const { token, username } = await sRegisterAndLogin();
    const restore = await writeOAuthSession(token, username);
    try {
      let st: PackStub = { phase: "missing", step: "" };
      const checkCalls = await stubOnboard(page, token, {
        status: () => ({ ...st }),
        probe: () => ({ installed_version: "", latest_version: "", update_available: false, source: "pack" }),
      });
      await page.goto(`${ORIGIN}/#/novels`);

      // 未装包 → 自动弹窗 + 立即触发同步（POST /check 由弹窗发起）
      const modal = page.locator(".modal", { hasText: "正在准备写作能力" });
      await expect(modal).toBeVisible({ timeout: 15000 });
      await expect(modal.getByTestId("pack-steps")).toBeVisible();
      // 进度文案明说不能关闭此窗口＋预计耗时（拍板 10-07 三次）
      await expect(modal).toContainText("不能关闭此窗口");
      await expect(modal).toContainText("预计 1 分钟左右");
      await expect
        .poll(async () => checkCalls.n, { timeout: 10000 })
        .toBe(1);

      // 同步完成 → 完成态提示可关闭（完成标题已变，用 testid 直取）
      st = { phase: "ready", version: "7", step: "" };
      await expect(page.getByTestId("pack-done")).toContainText("v7", { timeout: 15000 });
      await page.getByRole("button", { name: "开始写作" }).click();
      await expect(page.getByTestId("pack-done")).toHaveCount(0);
    } finally {
      restore();
    }
  });

  test("更新确认制：暂不更新不安装，再进页面再探测；确认后复用进度", async ({ page }) => {
    test.setTimeout(180_000);
    const { token, username } = await sRegisterAndLogin();
    const restore = await writeOAuthSession(token, username);
    try {
      let st: PackStub = { phase: "ready", version: "7", step: "" };
      const probe = { installed_version: "7", latest_version: "8", update_available: true, source: "pack" as const };
      const checkCalls = await stubOnboard(page, token, {
        status: () => ({ ...st }),
        probe: () => ({ ...probe }),
      });
      await page.goto(`${ORIGIN}/#/novels`);

      // 有新版 → 确认弹窗（当前 7 → 最新 8）；未确认前不触发安装
      const confirm = page.locator(".modal", { hasText: "写作能力有更新" });
      await expect(confirm).toBeVisible({ timeout: 15000 });
      await expect(confirm.getByTestId("pack-versions")).toContainText("7");
      await expect(confirm.getByTestId("pack-versions")).toContainText("8");
      // 更新（升级）同口径：明说不能关闭此窗口＋预计耗时
      await expect(confirm).toContainText("不能关闭此窗口");
      await expect(confirm).toContainText("预计 1 分钟左右");
      await expect.poll(async () => checkCalls.n).toBe(0);

      // 暂不更新：关闭、不安装
      await confirm.getByRole("button", { name: "暂不更新" }).click();
      await expect(page.locator(".modal", { hasText: "写作能力有更新" })).toHaveCount(0);

      // 再进页面（reload 重挂载）→ 再探测再提示
      await page.reload();
      await expect(page.locator(".modal", { hasText: "写作能力有更新" })).toBeVisible({
        timeout: 15000,
      });

      // 确认 → 立即更新：触发同步并复用进度；ready v8 → 完成
      const confirm2 = page.locator(".modal", { hasText: "写作能力有更新" });
      await confirm2.getByRole("button", { name: "立即更新" }).click();
      // 点确认不关窗：转「正在更新写作能力」锁定态并显示进度（拍板 10-07 三次）
      const running = page.locator(".modal", { hasText: "正在更新写作能力" });
      await expect(running).toBeVisible({ timeout: 10000 });
      await expect(running.getByTestId("pack-steps")).toBeVisible();
      await expect(running).toContainText("不能关闭此窗口");
      await expect.poll(async () => checkCalls.n, { timeout: 10000 }).toBe(1);
      st = { phase: "ready", version: "8", step: "" };
      await expect(page.getByTestId("pack-done")).toContainText("v8", { timeout: 15000 });
    } finally {
      restore();
    }
  });

  test("菜单手动入口：数据组「写作能力」开同一弹窗；无更新提示已是最新", async ({ page }) => {
    test.setTimeout(120_000);
    const { token, username } = await sRegisterAndLogin();
    const restore = await writeOAuthSession(token, username);
    try {
      const checkCalls = await stubOnboard(page, token, {
        status: () => ({ phase: "ready", version: "7", step: "" }),
        probe: () => ({ installed_version: "7", latest_version: "7", update_available: false, source: "pack" }),
      });
      await page.goto(`${ORIGIN}/#/novels`);

      // 已装无更新 → 全静默不弹窗
      await expect(page.getByText("我的作品").first()).toBeVisible({ timeout: 15000 });
      await expect(page.locator(".modal", { hasText: "写作能力" })).toHaveCount(0);

      // 账号菜单 → 数据组「写作能力」→ 手动弹窗
      await stableClick(page.locator('[data-od-id="acct-trigger"]'));
      await stableClick(page.locator('[data-od-id="acct-menu-pack"]'));
      const manual = page.locator(".modal", { hasText: "写作能力" }).first();
      await expect(manual).toBeVisible({ timeout: 10000 });

      // 检查更新：probe 无更新 → toast 已是最新，不触发安装
      await manual.getByTestId("pack-check-update").click();
      await expect(page.getByText("已是最新")).toBeVisible({ timeout: 10000 });
      await expect.poll(async () => checkCalls.n).toBe(0);
    } finally {
      restore();
    }
  });

  test("进度期弹窗锁定：X 不可关，完成转完成态才提示可关闭", async ({ page }) => {
    test.setTimeout(120_000);
    const { token, username } = await sRegisterAndLogin();
    const restore = await writeOAuthSession(token, username);
    try {
      let st: PackStub = { phase: "missing", step: "" };
      const checkCalls = await stubOnboard(page, token, {
        status: () => ({ ...st }),
        probe: () => ({ installed_version: "", latest_version: "", update_available: false, source: "pack" }),
      });
      await page.goto(`${ORIGIN}/#/novels`);

      // missing → 自动弹窗进入首装流；再翻 syncing 维持 running 态
      const modal = page.locator(".modal", { hasText: "正在准备写作能力" });
      await expect(modal).toBeVisible({ timeout: 15000 });
      await expect
        .poll(async () => checkCalls.n, { timeout: 10000 })
        .toBe(1);
      st = { phase: "syncing", step: "download" };
      // 进度期锁定：无「先去写作」退出出口；X 钮 disabled，点击弹窗仍在
      await expect(modal.getByRole("button", { name: "先去写作" })).toHaveCount(0);
      const x = modal.getByRole("button", { name: "关闭" });
      await expect(x).toBeDisabled();
      await x.click({ force: true });
      await expect(modal).toBeVisible();
      // 触发计数不增加（锁定≠重复触发）；同步链路由轮询驱动直至完成
      await page.waitForTimeout(2500);
      expect(checkCalls.n).toBe(1);
      // 完成才提示可关闭（开始写作出口出现）
      st = { phase: "ready", version: "9", step: "" };
      await expect(page.getByTestId("pack-done")).toContainText("v9", { timeout: 15000 });
      await expect(page.getByRole("button", { name: "开始写作" })).toBeEnabled();
    } finally {
      restore();
    }
  });
});
