import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type APIRequestContext, type Page } from "@playwright/test";
import { writeConfigAtomic } from "./helpers";

// ---------------------------------------------------------------------------
// 世界设定 v2 界面测试（world-setting-v2）：
//   - AI 端点一律 page.route 打桩（不烧真实额度、不依赖模型）
//   - ai_model 就绪态桩走 stubAiState（D13 一次分派，genre-ai-settings 同款）
//   - 覆盖：五格渲染 / 现实向开关联动 / AI 采纳 · 覆盖+回执+撤销+历史切回 /
//           一致性体检三态+重跑 / 免费版锁定
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
  const name = `e2e_worldv2_${Date.now()}_${randomUUID().slice(0, 8)}`;
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

async function setupSession(page: Page, tier = "trial") {
  const { token, username } = await sRegisterAndLogin();
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = token;
  cfg.username = username;
  cfg.tier = tier;
  delete cfg.expires_at;
  cfg.last_login_at = new Date().toISOString();
  cfg.pc_hash = randomUUID().replace(/-/g, "");
  writeConfigAtomic(CONFIG_PATH, JSON.stringify(cfg, null, 2));
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  // 注入会话的 pc_hash 在 S端 无设备授权（code 1），后端会据此清空注入 token → 401；
  // 桩掉 check-auth 往返保住会话（settings-forms / genre-ai-settings 同注）
  await page.route("**/api/auth/check-auth", (r) =>
    r.fulfill({ json: { code: 0, data: {} } }),
  );
  return { token, username, restore: () => writeConfigAtomic(CONFIG_PATH, original) };
}

async function createNovel(page: Page, name: string): Promise<string> {
  await page.goto(`${ORIGIN}/#/novels`);
  await page.waitForLoadState("networkidle");
  const newBtn = page.getByRole("button", { name: "新建作品" }).first();
  for (let attempt = 0; ; attempt++) {
    try {
      await newBtn.click({ timeout: 6000 });
      break;
    } catch (e) {
      // 书架首屏重渲染竞态：重载后再点；三次仍失败则抛出
      if (attempt >= 2) throw e;
      await page.reload();
    }
  }
  await page.locator("input#bkTitle").fill(name);
  await page.getByRole("button", { name: "创建，去写简介" }).click();
  await page.waitForURL(/#\/novel\/[0-9a-fA-F-]+/);
  const m = page.url().match(/\/novel\/([0-9a-fA-F-]+)/);
  if (!m) throw new Error(`无法解析 novel id: ${page.url()}`);
  return m[1];
}

/** 桩本书 AI 就绪态（D13）。 */
async function stubAiState(page: Page, pid: string, aiState: string, message = "") {
  await page.route(`**/api/v1/novels/${pid}/ai-model`, (r) =>
    r.fulfill({
      json: {
        api_config_id: aiState === "missing_model" ? null : "c1",
        model: aiState === "missing_model" ? null : "gpt-4o",
        config_name: "主配置",
        ai_state: aiState,
        effective_model: aiState === "ready" ? "gpt-4o" : "",
        reason: aiState,
        message,
      },
    }),
  );
}

async function openSetting(page: Page, name: string) {
  await page
    .locator(".settings-v .col-tree .s-item")
    .filter({ has: page.locator(".nm", { hasText: new RegExp(`^${name}$`) }) })
    .click();
}

/** 带 Bearer token 的 API GET。 */
async function apiGetJSON(request: APIRequestContext, token: string, urlPath: string) {
  const r = await request.get(`${ORIGIN}/api${urlPath}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(r.ok()).toBeTruthy();
  return r.json();
}

async function stubWorldAi(page: Page, pid: string) {
  let stageGen = 0;
  // v2 通用起草端点：按请求体 topic 分流（stage 两版草稿供历史切回用；topic=中文要素名）
  void page.route(`**/api/novels/${pid}/settings/ai/world/draft`, (route) => {
    const body = route.request().postDataJSON() as { topic?: string };
    if ((body?.topic ?? "") !== "世界舞台") {
      route.fulfill({ json: { value: "通用内容草稿。", topic: body?.topic ?? "" } });
      return;
    }
    stageGen += 1;
    route.fulfill({
      json: {
        value:
          stageGen === 1
            ? "云梁界，古典王朝的修仙世界——故事集中在南境。"
            : "王朝治下的修仙界——主战场在南境青梧宗。",
        topic: "世界舞台",
      },
    });
  });
  let checkGen = 0;
  void page.route(`**/api/novels/${pid}/settings/ai/world/check`, (route) => {
    checkGen += 1;
    const okItems = [
      { name: "简介 × 世界", status: "ok", note: "青梧宗在主战场内" },
      { name: "题材 × 世界", status: "ok", note: "以弱破强有等级差支撑" },
      { name: "铁律 × 简介", status: "ok", note: "无冲突" },
      { name: "代价与边界", status: "ok", note: "代价与边界已写死" },
      { name: "势力立场", status: "ok", note: "各有立场" },
      { name: "历史自洽", status: "ok", note: "对得上" },
    ];
    const firstItems = [
      { name: "简介 × 世界", status: "ok", note: "青梧宗在主战场内" },
      { name: "题材 × 世界", status: "warn", note: "力量体系还没写等级差——逆袭没有发力点" },
      { name: "铁律 × 简介", status: "ok", note: "无冲突" },
      { name: "代价与边界", status: "miss", note: "AI 未给出该项，可重跑体检" },
      { name: "势力立场", status: "ok", note: "各有立场" },
      { name: "历史自洽", status: "ok", note: "对得上" },
    ];
    route.fulfill({
      json: {
        items: checkGen === 1 ? firstItems : okItems,
        degraded: false,
        verdict: checkGen === 1 ? "基本自洽，补一条能力上限" : "边界已锁死，可以开写",
      },
    });
  });
}

test.describe("世界设定 v2", () => {
  test("五格渲染：五格标题 + 题材继承 + 06 折叠组 + 现实向开关收起力量两格", async ({
    page,
  }) => {
    const { restore } = await setupSession(page);
    try {
      const pid = await createNovel(page, `世界V2_${Date.now() % 100000}`);
      await stubAiState(page, pid, "ready");
      await page.getByRole("button", { name: /^设定/ }).click();
      await openSetting(page, "世界");

      for (const name of ["世界舞台", "力量体系", "力量的代价", "势力", "世界铁律"]) {
        await expect(page.locator(".m-name", { hasText: name })).toBeVisible();
      }
      await expect(page.locator('[data-od-id="theme-inherit"]')).toBeVisible();

      // 现实向开关：收起 02 主体与 03 + 右栏力量两行退场；再点恢复
      const powerText = page.locator('[data-od-id="power-text"]');
      const railPower = page.locator('.rail-assist [data-aiact="power"]');
      const railCost = page.locator('.rail-assist [data-aiact="cost"]');
      await expect(powerText).toBeVisible();
      await expect(railPower).toBeVisible();
      await page.locator('[data-od-id="no-power-btn"]').click();
      await expect(powerText).toHaveCount(0);
      await expect(page.locator('[data-od-id="mod-cost"]')).toBeHidden();
      await expect(railPower).toHaveCount(0);
      await expect(railCost).toHaveCount(0);
      await page.locator('[data-od-id="no-power-btn"]').click();
      await expect(powerText).toBeVisible();
      await expect(railPower).toBeVisible();
    } finally {
      await restore();
    }
  });

  test("AI 采纳 · 覆盖 + 回执 + 一步撤销 + 历史切回", async ({ page }) => {
    const { restore } = await setupSession(page);
    try {
      const pid = await createNovel(page, `世界AI_${Date.now() % 100000}`);
      await stubAiState(page, pid, "ready");
      stubWorldAi(page, pid);
      await page.getByRole("button", { name: /^设定/ }).click();
      await openSetting(page, "世界");

      // 第一次生成 → 采纳 · 覆盖 → 回执出现
      await page.locator('.rail-assist [data-aiact="stage"]').click();
      const sink = page.locator('[data-ans-zone="stage"]');
      await expect(sink).toBeVisible({ timeout: 10000 });
      await sink.locator(".ans-act button", { hasText: "采纳" }).click();
      const stage = page.locator('[data-od-id="stage-input"]');
      await expect(stage).toHaveValue(/云梁界/);
      await expect(page.locator('[data-od-id="panel-receipt"]')).toBeVisible();
      await expect(page.locator('[data-od-id="panel-receipt"]')).toContainText("世界舞台");

      // 撤销 → 恢复为空
      await page.locator('[data-od-id="panel-undo"]').click();
      await expect(stage).toHaveValue("");

      // 再生成一次 → 历史切换条出现（2 次），切回第 1 次
      await page.locator('.rail-assist [data-aiact="stage"]').click();
      await expect(sink.locator(".ah-chip")).toHaveCount(2);
      await sink.locator(".ah-chip").first().click();
      await expect(sink).toContainText("云梁界，古典王朝的修仙世界");
    } finally {
      await restore();
    }
  });

  test("一致性体检：三态渲染 + 重跑", async ({ page }) => {
    const { restore } = await setupSession(page);
    try {
      const pid = await createNovel(page, `世界体检_${Date.now() % 100000}`);
      await stubAiState(page, pid, "ready");
      stubWorldAi(page, pid);
      await page.getByRole("button", { name: /^设定/ }).click();
      await openSetting(page, "世界");
      await page.locator('.rail-assist [data-aiact="check"]').click();
      const result = page.locator('[data-od-id="world-check-result"]');
      await expect(result).toBeVisible({ timeout: 10000 });
      for (const state of ["ok", "warn", "miss"]) {
        await expect(result.locator(`.chk-res.${state}`).first()).toBeVisible();
      }
      await result.locator(".ans-act button", { hasText: "重跑" }).click();
      await expect(result.locator(".chk-res.ok")).toHaveCount(6);
    } finally {
      await restore();
    }
  });

  test("存草稿后重进：徽标=已填（不误标已确认）", async ({ page, request }) => {
    const { restore, token } = await setupSession(page);
    try {
      const name = `世界草稿_${Date.now() % 100000}`;
      const pid = await createNovel(page, name);
      await openSetting(page, "世界");
      const stage = page.locator('[data-od-id="stage-input"]');
      await expect(stage).toBeVisible({ timeout: 10000 });
      await stage.fill("只存草稿，不点确认");

      // 存草稿（脚部次按钮）→ 退出书页（存草稿无回执，落库即静默）
      await page.locator(".panel-foot").getByRole("button", { name: "存草稿" }).click();
      await page.getByRole("link", { name: "我的小说" }).click();

      // 重进书 → 世界面板：徽标=已填（从未确认，不得误标已确认）
      const readiness = await apiGetJSON(request, token, `/novels/${pid}/readiness`);
      const worldNow = await apiGetJSON(request, token, `/novels/${pid}/settings/world`);
      await page.goto(`${ORIGIN}/#/novel/${pid}`);
      await page.getByRole("button", { name: /^设定/ }).click();
      await openSetting(page, "世界");
      const badge = page.locator(".settings-v main .panel-head .badge");
      await expect(badge).toHaveText(/已填/);
      await expect(badge).not.toHaveText(/已确认/);
    } finally {
      await restore();
    }
  });

  test("免费版：字段照常手填，右栏 AI 锁定", async ({ page }) => {
    const { restore } = await setupSession(page, "free");
    try {
      const pid = await createNovel(page, `世界免费_${Date.now() % 100000}`);
      await stubAiState(page, pid, "member_required", "这是会员功能，升级 PRO 后解锁");
      await page.getByRole("button", { name: /^设定/ }).click();
      await openSetting(page, "世界");
      const stage = page.locator('[data-od-id="stage-input"]');
      await expect(stage).toBeVisible({ timeout: 10000 });
      await expect(page.locator(".rail-assist")).toHaveClass(/locked/);

      // 免费版照常手填
      await stage.fill("免费版也能填的世界");
      await expect(stage).toHaveValue("免费版也能填的世界");
    } finally {
      await restore();
    }
  });
});


  test("lore 全链：暂存建议 → 06 展示 → 采纳入账", async ({ page, request }) => {
    const { token, restore } = await setupSession(page);
    try {
      const pid = await createNovel(page, `世界Lore_${Date.now() % 100000}`);
      await stubAiState(page, pid, "ready");
      // 模拟归档写入暂存（useChapterData recordLoreSuggestions 的落点）：
      // 应用 JS 跑起来之前种 sessionStorage，验证面板挂载即读
      await page.addInitScript((bookId) => {
        sessionStorage.setItem(
          `lore-suggestions:${bookId}`,
          JSON.stringify([
            { key: "血衣楼", value: "第12章登场的新势力", set: "extra", origin: "vol-1-ch-12" },
          ]),
        );
      }, pid);
      // createNovel 结束时已在 #/novel/{pid}（同文档）；reload 让 init script 真正执行
      await page.reload();
      await page.waitForLoadState("networkidle");
      await page.getByRole("button", { name: /^设定/ }).click();
      await openSetting(page, "世界");
      await page.locator("details.cfg summary").click();
      const pending = page.locator('[data-od-id="lore-pending"]');
      await expect(pending).toBeVisible();
      await expect(pending).toContainText("血衣楼");
      await page.locator('[data-od-id^="lore-adopt-"]').click();
      await expect(page.locator('[data-od-id="lore-pending"]')).toHaveCount(0);
      // 入账落库：extra 里出现血衣楼（带 origin 幂等键）
      const world = await apiGetJSON(request, token, `/novels/${pid}/settings/world`);
      const lore = world.extra.find((e: { key: string }) => e.key === "血衣楼");
      expect(lore).toBeTruthy();
      expect(lore.origin).toBe("vol-1-ch-12");
    } finally {
      await restore();
    }
  });

  test("空世界点确认完成：停留本面板不误标已确认", async ({ page }) => {
    const { restore } = await setupSession(page);
    try {
      const pid = await createNovel(page, `世界空确认_${Date.now() % 100000}`);
      await page.getByRole("button", { name: /^设定/ }).click();
      await openSetting(page, "世界");
      await expect(page.locator('[data-od-id="stage-input"]')).toBeVisible({ timeout: 10000 });
      await page.locator(".panel-foot").getByRole("button", { name: "确认完成" }).click();
      // 后端 400 拦截：仍在本面板（确认按钮未变成保存修改）
      await expect(page.locator(".settings-v main h2")).toHaveText(/世界/, { timeout: 5000 });
      await expect(
        page.locator(".panel-foot").getByRole("button", { name: "保存修改" }),
      ).toHaveCount(0);
    } finally {
      await restore();
    }
  });
