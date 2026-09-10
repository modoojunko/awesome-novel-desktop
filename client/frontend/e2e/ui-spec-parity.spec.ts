import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page } from "@playwright/test";
import { cleanupSessionNovels } from "./helpers";

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
  const mine = JSON.stringify(cfg, null, 2);
  // 注入后必须**盯三轮**确认没被回写冲掉：本文件按字母序紧跟 settings-forms
  // （全量跑最重的一档），其收尾残余 check-auth 会异步回写 config.json——
  // 一次性写入曾被冲掉 → 注入 token 失效 → 401 拦截器把页面登出 → 用例干等超时。
  const writeMine = () => fs.writeFileSync(CONFIG_PATH, mine);
  writeMine();
  for (let stable = 0, tries = 0; stable < 3 && tries < 12; tries++) {
    await new Promise((r) => setTimeout(r, 300));
    if (fs.readFileSync(CONFIG_PATH, "utf-8") === mine) stable += 1;
    else {
      writeMine();
      stable = 0;
    }
  }
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  await page.route("**/api/auth/check-auth", (r) =>
    r.fulfill({ json: { code: 0, data: {} } }),
  );
  const restoreConfig = () => fs.writeFileSync(CONFIG_PATH, original);
  const restore = async () => {
    await cleanupSessionNovels(ORIGIN, token); // 先删本次测试自建的书，再还原本地会话
    restoreConfig();
  };
  return { restore };
}

async function createNovel(page: Page, name: string): Promise<string> {
  await page.goto(`${ORIGIN}/#/novels`);
  await page.getByRole("button", { name: "新建作品" }).first().click();
  await page.locator("input#bkTitle").fill(name);
  await page.getByRole("button", { name: "创建，去写简介" }).click();
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

/** px 级断言前等字体就绪：全量跑时字体晚到会让 font-size/line-height 读出过渡值。 */
async function fontsReady(page: import("@playwright/test").Page) {
  await page.evaluate(() => document.fonts.ready);
}

test.describe("界面规格 parity（尺寸/字号）", () => {
  test("简介框 / 按钮 / 胶囊 / 徽标 / ai-sink 的规格断言（9.1.0/9.4.13）", async ({ page }) => {
    const { restore } = await setupSession(page);
    try {
      const pid = await createNovel(page, `规格${Date.now() % 100000}`);
      await stubAiState(page, pid);
      await fontsReady(page);
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
      await restore();
    }
  });

  test("题材：胶囊 999px + 模型行同行等高 + ai-sink 底色＝fg-soft≠surface（9.1.0/9.4.13）", async ({
    page,
  }) => {
    const { restore } = await setupSession(page);
    try {
      const pid = await createNovel(page, `规格题材${Date.now() % 100000}`);
      await stubAiState(page, pid);
      await fontsReady(page);
      await page.route(`**/api/novels/${pid}/settings/ai/genre/cost_ratio`, (r) =>
        r.fulfill({ json: { value: 8 } }),
      );

      await page.getByRole("button", { name: /^设定/ }).click();
      await page.locator(".settings-v .col-tree .s-item", { hasText: "题材" }).click();
      await expect(page.locator(".settings-v .mod")).toHaveCount(5);

      // 口味胶囊 borderRadius 999
      expect(await cssNum(page, ".settings-v .cap", "border-radius")).toBe(999);

      // 01 题材选择器：收起态是一行控件（不是巨框）、图标有尺寸。
      // 回归背景：Ico 不传 size 时 <svg> 无内在宽高，漏了上下文 CSS 就会把字段
      // 撑成几百 px 高的巨框＋巨型箭头（截图抓到，断言文本/类名的用例看不见）。
      const selBox = await page.locator('[data-od-id="theme-trigger"]').boundingBox();
      expect(selBox!.height).toBeLessThan(56);
      const iconBox = await page.locator('[data-od-id="theme-trigger"] svg').boundingBox();
      expect(iconBox!.width).toBeLessThanOrEqual(20);
      expect(iconBox!.height).toBeLessThanOrEqual(20);
      // 展开态：面板可见且两列在（大类列 + 子类列）
      await page.locator('[data-od-id="theme-trigger"]').click();
      await expect(page.locator('[data-od-id="theme-row"]')).toBeVisible();
      await expect(page.locator('[data-od-id="sub-genre-row"]')).toBeVisible();
      const panelBox = await page.locator('[data-od-id="theme-panel"]').boundingBox();
      expect(panelBox!.height).toBeLessThan(420); // 两列各自 288 上限 + 搜索框
      await page.keyboard.press("Escape");
      await expect(page.locator('[data-od-id="theme-panel"]')).toHaveCount(0);

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
      await page.locator(".settings-v .col-tree .s-item", { hasText: "模型设定" }).click();
      await expect(page.locator(".model-group")).toHaveCount(1);
      const heights = await page.$$eval(".model-row", (els) =>
        els.map((e) => Math.round(e.getBoundingClientRect().height)),
      );
      expect(new Set(heights).size).toBe(1);
    } finally {
      await restore();
    }
  });

  test("简介输入框边界：min-height 不塌陷 / 500 截断 / 长串不撑破（9.1.0b）", async ({
    page,
  }) => {
    const { restore } = await setupSession(page);
    try {
      const pid = await createNovel(page, `边界${Date.now() % 100000}`);
      await stubAiState(page, pid);
      await fontsReady(page);
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
      await restore();
    }
  });

  test("窄屏 900px：设定视图卡片不溢出（9.4.13）", async ({ page }) => {
    const { restore } = await setupSession(page);
    try {
      const pid = await createNovel(page, `窄屏${Date.now() % 100000}`);
      await stubAiState(page, pid);
      await fontsReady(page);
      await page.getByRole("button", { name: /^设定/ }).click();
      await expect(page.locator(".settings-v main h2")).toBeVisible({ timeout: 10000 });

      await page.setViewportSize({ width: 900, height: 800 });
      const overflow = await page.$eval(".settings-v .col-middle", (el) => ({
        sw: el.scrollWidth,
        cw: el.clientWidth,
      }));
      expect(overflow.sw).toBeLessThanOrEqual(overflow.cw + 1);
    } finally {
      await restore();
    }
  });
});

// ── 设定面板宽度：填满中栏、左右留白对称（不留"到 AI 栏的假空白"）──────────
// 回归背景：`.wb .panel{max-width:660px}`（book.html 旧稿）在中栏 924px 时只在
// 左侧留 660px，右侧空出 ~216px 到 AI 栏——1440 视口实测肉眼可见的大面积空白。
// 现口径＝genre-signup.html（简介/题材权威稿）：面板为 1fr 填满，超宽屏按原型
// `.wrap{max-width:1180px}` 居中。
test("设定面板填满中栏且左右留白对称（1440/1920）", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    const pid = await createNovel(page, `宽度${Date.now() % 100000}`);
    await stubAiState(page, pid);
      await fontsReady(page);

    for (const width of [1440, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(`${ORIGIN}/#/novel/${pid}`);
      await page.waitForTimeout(1500);
      await page.getByRole("button", { name: /^设定/ }).click();
      await expect(page.locator(".settings-v main h2")).toBeVisible({ timeout: 15000 });

      const m = await page.evaluate(() => {
        const q = (s: string) => document.querySelector(s) as HTMLElement | null;
        const mid = q(".settings-v .col-middle")!;
        const panel = q(".settings-v .col-middle .panel")!;
        const ai = q(".settings-v .col-ai")!;
        const mr = mid.getBoundingClientRect();
        const pr = panel.getBoundingClientRect();
        const ar = ai.getBoundingClientRect();
        return {
          midW: mr.width,
          panelW: pr.width,
          leftGap: pr.left - mr.left,
          rightGap: ar.left - pr.right,
        };
      });

      // ① 面板至少填满中栏 80%：1440 → 90%、1920 → 84%
      //    （旧 `.wb .panel{max-width:660px}` 在 1440 只有 71%，此断言即失败）
      expect(m.panelW / m.midW).toBeGreaterThan(0.8);
      // ② 左右留白对称（窄屏同为 48px 栏内边距；超宽屏同为居中留白）
      //    旧 bug 的特征是"左 48 / 右 216"的偏侧空白，此处必失败
      expect(Math.abs(m.leftGap - m.rightGap)).toBeLessThan(2);
    }
  } finally {
    await restore();
  }
});

// ── PM 评审四项修复的回归（2026-09-10）────────────────────────────────────
// 背景：面板变宽后暴露 ① 工具项挂「已确认」假徽标 ② 说明型区块被 margin-left:auto
// 甩到两端 ③ 面板脚注悬空 ④ 六段体检单列在宽屏下每行右侧大片空白。
test("设定页：工具项徽标 / 辅助信息邻接 / 脚注贴底", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    const pid = await createNovel(page, `PM评审${Date.now() % 100000}`);
    await stubAiState(page, pid);
      await fontsReady(page);
    await page.setViewportSize({ width: 1660, height: 980 });
    await page.goto(`${ORIGIN}/#/novel/${pid}`);
    await page.waitForTimeout(1500);
    await page.getByRole("button", { name: /^设定/ }).click();
    await expect(page.locator(".settings-v main h2")).toBeVisible({ timeout: 15000 });

    // P3 左栏标题口径：8 设定项 + 1 工具行
    await expect(page.locator(".settings-v .tree-head .t")).toContainText("+ 1 工具");

    // P1a 工具行不挂确认徽标（它从不参与确认，恒「已确认」是误导）
    const toolBadge = page.locator(".settings-v .settings-nav-wrap .s-item", { hasText: "模型设定" }).locator(".badge");
    await expect(toolBadge).toContainText("不参与进度");
    await expect(toolBadge).not.toContainText("已确认");

    // P2b/P2c 辅助信息邻接：计数与「≤500 字」、展开与文案的间距都在 ~30px 内
    const gaps = await page.evaluate(() => {
      const q = (s: string) => document.querySelector(s) as HTMLElement;
      const label = q(".settings-v .field > label");
      const cnt = label.querySelector(".cnt") as HTMLElement;
      const opt = label.querySelector(".opt") as HTMLElement;
      const gtC = q(".settings-v .guide-toggle .gt-c");
      const gtS = q(".settings-v .guide-toggle .gt-s");
      return {
        cnt: Math.round(cnt.getBoundingClientRect().left - opt.getBoundingClientRect().right),
        guide: Math.round(gtC.getBoundingClientRect().left - gtS.getBoundingClientRect().right),
      };
    });
    expect(gaps.cnt).toBeLessThan(30);
    expect(gaps.guide).toBeLessThan(40);

    // P2d 面板脚注贴底：脚注底到中栏底只剩容器内边距（60px），不再悬空 ~180px
    const footGap = await page.evaluate(() => {
      const col = document.querySelector(".settings-v .col-middle")!;
      const foot = document.querySelector(".settings-v .panel-foot")!;
      return Math.round(col.getBoundingClientRect().bottom - foot.getBoundingClientRect().bottom);
    });
    expect(footGap).toBeLessThan(80);

    // P1b 模型窗面板头徽标＝真实就绪态（桩 ready → 可用，不再是恒「已确认」）
    await page.locator(".settings-v .settings-nav-wrap .s-item", { hasText: "模型设定" }).click();
    await expect(page.locator(".settings-v .panel-head .badge")).toContainText("可用");
    await expect(page.locator(".settings-v .panel-foot .note")).toContainText("不参与设定进度");
  } finally {
    await restore();
  }
});

test("简介体检：六段在宽屏两列排布（不再单列稀疏）", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    const pid = await createNovel(page, `六段网格${Date.now() % 100000}`);
    await stubAiState(page, pid);
      await fontsReady(page);
    await page.route(`**/api/novels/${pid}/settings/ai/intro/introspect`, (r) =>
      r.fulfill({
        json: {
          six_segments: [
            { name: "主角身份", status: "ok", excerpt: "外门杂徒林拾", note: "" },
            { name: "本来的生活", status: "ok", excerpt: "熬满十年出宗", note: "" },
            { name: "突发状况", status: "missing", excerpt: "", note: "没写打破平静的变故" },
            { name: "必须面对的矛盾", status: "missing", excerpt: "", note: "缺两难" },
            { name: "不做的后果", status: "ok", excerpt: "丹田枯竭", note: "" },
            { name: "做了的可能结局", status: "ok", excerpt: "一路捅上去", note: "" },
          ],
          taboo: { hits: [] },
          title_check: { fit: "ok", note: "", suggestions: [] },
          verdict: "ok",
        },
      }),
    );

    await page.setViewportSize({ width: 1660, height: 980 });
    await page.goto(`${ORIGIN}/#/novel/${pid}`);
    await page.waitForTimeout(1500);
    await page.getByRole("button", { name: /^设定/ }).click();
    await page.getByPlaceholder(/用几句话/).fill("外门杂徒林拾，在宗门扫了十年落叶。");
    await page.locator('[data-aiact="check"]').click();
    await expect(page.locator('[data-od-id="intro-ai-sink"]')).toBeVisible({ timeout: 15000 });

    const grid = await page.evaluate(() => {
      const g = document.querySelector(".settings-v .ai-sink .chk-grid")!;
      const tops = [...g.querySelectorAll(".chk-line")].map((e) => Math.round(e.getBoundingClientRect().top));
      return {
        cols: getComputedStyle(g).gridTemplateColumns.split(" ").length,
        rows: new Set(tops).size,
        lines: tops.length,
      };
    });
    // 宽屏：6 段排成 3 行 2 列（不再 6 行单列、每行右侧大片空白）
    expect(grid.lines).toBe(6);
    expect(grid.cols).toBeGreaterThan(1);
    expect(grid.rows).toBeLessThan(6);
  } finally {
    await restore();
  }
});
