import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page } from "@playwright/test";

// ---------------------------------------------------------------------------
// 界面规格 parity：尺寸/字号断言（tasks 9.1.0 / 9.1.0b / 9.4.13）
//   不是"元素存在"而是"渲染出来的尺寸符合 9.0 规格表"——与原型逐项对齐。
// ---------------------------------------------------------------------------

const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
const S_API = process.env.E2E_S_API || "http://127.0.0.1:19000/api/web";
const CONFIG_PATH = path.join(
  process.cwd(),
  "..",
  "..",
  ".docker-data",
  "client",
  "config.json",
);

async function sRegisterAndLogin() {
  const name = `e2e_spec_${Date.now()}_${randomUUID().slice(0, 8)}`;
  const password = "Test" + "Pass789!";
  await fetch(`${S_API}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: name,
      password,
      security_question: "最喜欢的颜色",
      security_answer: "蓝色",
    }),
  });
  const login = await fetch(`${S_API}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: name, password }),
  });
  const body = await login.json();
  if (body.code !== 0) throw new Error(`S端 login 失败: ${JSON.stringify(body)}`);
  return { token: body.data.token as string, username: name };
}

async function setupSession(page: Page) {
  const { token, username } = await sRegisterAndLogin();
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = token;
  cfg.username = username;
  cfg.tier = "trial";
  delete cfg.expires_at;
  cfg.last_login_at = new Date().toISOString();
  cfg.pc_hash = randomUUID().replace(/-/g, "");
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2));
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  await page.route("**/api/auth/check-auth", (r) =>
    r.fulfill({ json: { code: 0, data: {} } }),
  );
  return { restore: () => fs.writeFileSync(CONFIG_PATH, original) };
}

async function createNovel(page: Page, name: string): Promise<string> {
  await page.goto(`${ORIGIN}/#/novels`);
  await page.getByRole("button", { name: "新建作品" }).first().click();
  await page.locator("input#bkTitle").fill(name);
  await page.getByRole("button", { name: "创建并开始写作" }).click();
  await page.waitForURL(/#\/novel\/[0-9a-fA-F-]+/);
  const m = page.url().match(/\/novel\/([0-9a-fA-F-]+)/);
  if (!m) throw new Error(`无法解析 novel id: ${page.url()}`);
  return m[1];
}

async function stubAiState(page: Page, pid: string) {
  await page.route(`**/api/v1/novels/${pid}/ai-model`, (r) =>
    r.fulfill({
      json: {
        api_config_id: "c1",
        model: "gpt-4o",
        config_name: "主配置",
        ai_state: "ready",
        effective_model: "gpt-4o",
        reason: "ready",
        message: "已就绪",
      },
    }),
  );
  await page.route("**/api/v1/api-configs", (r) =>
    r.fulfill({
      json: [
        {
          id: "c1",
          name: "主配置",
          vendor: "openai",
          models: ["gpt-4o", "gpt-4o-mini"],
          status: "active",
          last_test_status: "ok",
        },
      ],
    }),
  );
}

/** getComputedStyle 取值（px 数值化）。 */
async function cssNum(page: Page, sel: string, prop: string) {
  return page.$eval(
    sel,
    (el, p) => parseFloat(getComputedStyle(el).getPropertyValue(p as string)),
    prop,
  );
}

test.describe("界面规格 parity（尺寸/字号）", () => {
  test("简介框 / 按钮 / 胶囊 / 徽标 / ai-sink 的规格断言（9.1.0/9.4.13）", async ({ page }) => {
    const { restore } = await setupSession(page);
    try {
      const pid = await createNovel(page, `规格${Date.now() % 100000}`);
      await stubAiState(page, pid);
      await page.getByRole("button", { name: /^设定/ }).click();
      await expect(page.locator(".settings-v main h2", { hasText: "简介" })).toBeVisible({
        timeout: 10000,
      });

      // 简介框：minHeight 132 / fontSize 14 / lineHeight 1.9 / borderRadius 9
      const ta = ".settings-v .intro-ta";
      expect(await cssNum(page, ta, "min-height")).toBe(132);
      expect(await cssNum(page, ta, "font-size")).toBe(14);
      expect(await cssNum(page, ta, "line-height")).toBeCloseTo(26.6, 0); // 14 * 1.9
      expect(await cssNum(page, ta, "border-radius")).toBe(9);

      // 按钮：height 34 / padding 0 15 / fontSize 13.5
      const btn = ".settings-v .panel-foot .btn";
      expect(await cssNum(page, btn, "height")).toBe(34);
      expect(await page.$eval(btn, (el) => getComputedStyle(el).padding)).toBe("0px 15px");
      expect(await cssNum(page, btn, "font-size")).toBe(13.5);

      // 徽标：borderRadius 999
      expect(
        await cssNum(page, ".settings-v .panel-head .badge", "border-radius"),
      ).toBe(999);
      // 面板脚注的「确认完成」按钮不溢出
      const overflow = await page.$eval(".settings-v .col-middle", (el) => ({
        sw: el.scrollWidth,
        cw: el.clientWidth,
      }));
      expect(overflow.sw).toBeLessThanOrEqual(overflow.cw + 1);
    } finally {
      restore();
    }
  });

  test("题材：胶囊 999px + 模型行同行等高 + ai-sink 底色＝fg-soft≠surface（9.1.0/9.4.13）", async ({
    page,
  }) => {
    const { restore } = await setupSession(page);
    try {
      const pid = await createNovel(page, `规格题材${Date.now() % 100000}`);
      await stubAiState(page, pid);
      await page.route(`**/api/novels/${pid}/settings/ai/genre/cost_ratio`, (r) =>
        r.fulfill({ json: { value: 8 } }),
      );

      await page.getByRole("button", { name: /^设定/ }).click();
      await page.locator(".settings-v .col-tree .s-item", { hasText: "题材" }).click();
      await expect(page.locator(".settings-v .mod")).toHaveCount(6);

      // 口味胶囊 borderRadius 999
      expect(await cssNum(page, ".settings-v .cap", "border-radius")).toBe(999);

      // 五行 AI 落结果区后：底色＝--fg-soft 且 ≠ --surface
      await page.locator('[data-aiact="m3"]').click();
      const sink = page.locator('[data-od-id="genre-ai-sink-cost_ratio"]');
      await expect(sink).toBeVisible({ timeout: 10000 });
      // 变量值是 oklch 等格式 → 用探针元素转成 rgb 再比
      const colors = await page.evaluate(() => {
        const toRgb = (v: string) => {
          const probe = document.createElement("div");
          probe.style.color = v;
          document.body.appendChild(probe);
          const out = getComputedStyle(probe).color;
          probe.remove();
          return out;
        };
        const root = getComputedStyle(document.documentElement);
        const sinkEl = document.querySelector('[data-od-id="genre-ai-sink-cost_ratio"]')!;
        return {
          sink: getComputedStyle(sinkEl).backgroundColor,
          fgSoft: toRgb(root.getPropertyValue("--fg-soft").trim()),
          surface: toRgb(root.getPropertyValue("--surface").trim()),
        };
      });
      expect(colors.sink).toBe(colors.fgSoft);
      expect(colors.sink).not.toBe(colors.surface);

      // 模型窗：分组内模型行同行等高
      await page.locator(".settings-v .col-tree .s-item", { hasText: "AI 模型" }).click();
      await expect(page.locator(".model-group")).toHaveCount(1);
      const heights = await page.$$eval(".model-row", (els) =>
        els.map((e) => Math.round(e.getBoundingClientRect().height)),
      );
      expect(new Set(heights).size).toBe(1);
    } finally {
      restore();
    }
  });

  test("简介输入框边界：min-height 不塌陷 / 500 截断 / 长串不撑破（9.1.0b）", async ({
    page,
  }) => {
    const { restore } = await setupSession(page);
    try {
      const pid = await createNovel(page, `边界${Date.now() % 100000}`);
      await stubAiState(page, pid);
      await page.getByRole("button", { name: /^设定/ }).click();
      const ta = page.locator(".settings-v .intro-ta");
      await expect(ta).toBeVisible({ timeout: 10000 });

      const minHeight = async () =>
        ta.evaluate((el) => Math.round(el.getBoundingClientRect().height));
      const h0 = await minHeight();

      await ta.fill("一");
      expect(await minHeight()).toBe(h0);

      await ta.fill("字".repeat(499));
      expect(await minHeight()).toBe(h0);

      // 501 字被 maxlength 截断到 500
      await ta.fill("字".repeat(501));
      const len = await ta.evaluate((el) => (el as HTMLTextAreaElement).value.length);
      expect(len).toBe(500);

      // 长英文/无空格长串不撑破容器
      await ta.fill("A".repeat(500));
      const box = await ta.evaluate((el) => ({
        sw: el.scrollWidth,
        cw: el.clientWidth,
      }));
      expect(box.sw).toBeLessThanOrEqual(box.cw + 1);

      // 纯空白 → 不触发「已填」徽标（面板头仍是未填/已确认态而非已填）
      await ta.fill("   ");
      await expect(page.locator(".settings-v .panel-head .badge")).not.toHaveClass(/warn/);
    } finally {
      restore();
    }
  });

  test("窄屏 900px：设定视图卡片不溢出（9.4.13）", async ({ page }) => {
    const { restore } = await setupSession(page);
    try {
      const pid = await createNovel(page, `窄屏${Date.now() % 100000}`);
      await stubAiState(page, pid);
      await page.getByRole("button", { name: /^设定/ }).click();
      await expect(page.locator(".settings-v main h2")).toBeVisible({ timeout: 10000 });

      await page.setViewportSize({ width: 900, height: 800 });
      const overflow = await page.$eval(".settings-v .col-middle", (el) => ({
        sw: el.scrollWidth,
        cw: el.clientWidth,
      }));
      expect(overflow.sw).toBeLessThanOrEqual(overflow.cw + 1);
    } finally {
      restore();
    }
  });
});
