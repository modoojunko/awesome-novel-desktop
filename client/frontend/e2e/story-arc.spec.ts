import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page, type APIRequestContext } from "@playwright/test";
import { cleanupSessionNovels, stableClick } from "./helpers";
import { entitlementFor } from "./tier-features";

// =========================================================================
// 主线设定 E2E（storyline-settings-v2：全景 fullstory + 结局三问）
// 1. 空内容确认 → 后端 400「还未填写」提示，进度不动
// 2. 手填全流程（全景 + 三问）→ 确认完成 → 5/8 + 徽标已确认 + 前进文风
// 3. 三问脏态切换 → window.confirm 拦截
// 4. AI 三行 + 行内 tone（浏览器侧打桩）：弹窗出卡 / 采纳写回 / 撤销 / 换一个版数递增 / 500 弹窗错误体重试
// 5. 免费版：AI 点击 0 请求 + 统一升级 toast；手填全流程不受影响
// 6. 主线体检：报告卡弹窗（无写回键）+ 确认按钮仍可点 + 重新检查
// 7. 存量旧书（legacy premise + volumes）→ 打开不炸 / 归一显示 / 保存镜像 / volumes 保留
// =========================================================================
// 会话注入与既有 spec 同法（S端 真实签发 + docker config.json + check-auth 页面级桩）。

const S_API = process.env.E2E_S_API || "http://127.0.0.1:19000/api/web";
const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
const CONFIG_PATH = path.join(
  process.cwd(), "..", "..", ".docker-data", "client", "config.json",
);
const TEST_PASSWORD = ["Test", "Pass789", "!"].join("");

async function sRegisterAndLogin() {
  const name = `e2e_arc_${Date.now()}_${randomUUID().slice(0, 8)}`;
  const password = TEST_PASSWORD;
  const r1 = await fetch(`${S_API}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: name, password,
      security_question: "最喜欢的颜色", security_answer: "蓝色",
    }),
  });
  const regBody = await r1.json();
  if (regBody.code !== 0) throw new Error(`S端 register 失败: ${JSON.stringify(regBody)}`);
  const login = await fetch(`${S_API}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: name, password }),
  });
  const loginBody = await login.json();
  if (loginBody.code !== 0) throw new Error(`S端 login 失败: ${JSON.stringify(loginBody)}`);
  return { token: loginBody.data.token as string, username: name };
}

function writeOAuthSession(t: string, u: string, tier = "trial") {
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = t;
  cfg.username = u;
  cfg.tier = tier;
  cfg.entitlement = entitlementFor(tier); // 快照单源（tier-features 6.2）
  delete cfg.expires_at;
  cfg.last_login_at = new Date().toISOString();
  cfg.pc_hash = randomUUID().replace(/-/g, "");
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2));
  return () => fs.writeFileSync(CONFIG_PATH, original);
}

async function setupSession(page: Page, tier = "trial") {
  const { token, username } = await sRegisterAndLogin();
  const restore = writeOAuthSession(token, username, tier);
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  // 页面级桩 check-auth：e2e 注入的 pc_hash 在 S端 无设备授权（code 1），后端会
  // 据此清空 config.json 的注入 token → 业务请求 401（已知环境阻塞）。桩掉这次
  // 往返即可保住注入会话；会员判定仍走后端 check_permission()（读 config.json tier）。
  await page.route("**/api/auth/check-auth", (r) =>
    r.fulfill({ json: { code: 0, data: {} } }),
  );
  const restoreAndCleanup = async () => {
    await cleanupSessionNovels(ORIGIN, token);
    await restore();
  };
  return { restore: restoreAndCleanup, token };
}

async function createNovel(page: Page, name: string): Promise<string> {
  await page.goto(`${ORIGIN}/#/novels`);
  await stableClick(page.getByRole("button", { name: "新建作品" }).first()); // 稳定点击保险（风暴由守卫用例钉死）
  await page.locator("input#bkTitle").fill(name);
  await page.getByRole("button", { name: "创建，去写简介" }).click();
  await page.waitForURL(/#\/novel\/[0-9a-fA-F-]+/);
  const m = page.url().match(/\/novel\/([0-9a-fA-F-]+)/);
  if (!m) throw new Error(`无法解析 novel id: ${page.url()}`);
  return m[1];
}

async function apiGetJSON(request: APIRequestContext, token: string, path: string) {
  const r = await request.get(`${ORIGIN}/api${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(r.ok()).toBeTruthy();
  return r.json();
}

async function apiPutJSON(
  request: APIRequestContext, token: string, path: string, body: unknown,
) {
  const r = await request.put(`${ORIGIN}/api${path}`, {
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    data: body as object,
  });
  expect(r.ok()).toBeTruthy();
  return r.json();
}

async function openArcPanel(page: Page) {
  await page.getByRole("button", { name: /^设定/ }).click();
  await page.locator(".settings-v .col-tree").getByText("主线", { exact: true }).click();
}

/** 串行填主线四字段：受控组件对并发 fill 有 onChange 批处理竞态（实测并发时
 *  值会串位进最后一个输入框），必须逐个 await。 */
async function fillArc(page: Page, opts?: { fullstory?: string; tone?: string }) {
  await page
    .locator('[data-od-id="arc-fullstory"]')
    .fill(opts?.fullstory ?? "陆征追查苏棠失踪案，从坊市查进警队，最后在听证会上揭开真相。");
  await page.locator('[data-od-id="arc-ending-scene"]').fill("侦探所里看着旧卷宗");
  await page.locator('[data-od-id="arc-ending-hero"]').fill("破案但心里装了更多");
  await page.locator('[data-od-id="arc-ending-tone"]').fill(opts?.tone ?? "苍凉但平静");
}

/** 浏览器层打桩 arc AI（正则锚 /api/ 前缀，防误吞 Vite /src/api/*）。
 *  一并桩 /ai-model 下发 ai_state=ready（D13 单源）——docker 会话无 API Key，
 *  不桩则 AI 卡被 no_key 拦走跳模型配置，AI 用例全灭（genre-ai-settings 同配方）。 */
async function stubArcAi(page: Page, handler: (action: string) => { status: number; body: unknown }) {
  await page.route(/\/api\/v1\/novels\/[^/]+\/ai-model/, (route) =>
    route.fulfill({
      status: 200,
      body: JSON.stringify({ api_config_id: "stub", config_name: "stub", model: "stub", ai_state: "ready" }),
      contentType: "application/json",
    }),
  );
  await page.route(/\/api\/novels\/[^/]+\/settings\/ai\/arc\/(draft|calibrate|check|tone)/, (route) => {
    const action = route.request().url().match(/arc\/(\w+)$/)![1];
    const r = handler(action);
    return route.fulfill({ status: r.status, body: JSON.stringify(r.body), contentType: "application/json" });
  });
}

test.describe("主线面板（v2：全景 + 结局三问）", () => {
  test("空内容确认 → 400 提示，进度不动", async ({ page }) => {
    const { restore } = await setupSession(page, "trial");
    try {
      await createNovel(page, `主线空确认${Date.now() % 100000}`);
      await openArcPanel(page);
      await page.locator(".panel-foot").getByRole("button", { name: "确认完成" }).click();
      // 后端 400 → toast 中文提示；面板留在主线
      await expect(page.getByText(/还未填写/).first()).toBeVisible({ timeout: 5000 });
      await expect(page.locator(".settings-v main h2", { hasText: "主线" })).toBeVisible();
      // 无分卷区、无基调选择题（tone-opt 退役）
      await expect(page.getByText("加一卷")).toHaveCount(0);
      await expect(page.locator('.settings-v [role="radio"]')).toHaveCount(0);
    } finally {
      await restore();
    }
  });

  test("手填全流程 → 确认完成：5/8 + 徽标已确认 + 前进文风 + 已确认态再确认＝保存修改", async ({ page, request }) => {
    const { restore, token } = await setupSession(page, "trial");
    try {
      const pid = await createNovel(page, `主线确认${Date.now() % 100000}`);
      await openArcPanel(page);
      await fillArc(page);

      const arcSave = page.waitForResponse(
        (r) => r.request().method() === "PUT" && /\/story\/arc$/.test(r.url()),
);
      await page.locator(".panel-foot").getByRole("button", { name: "确认完成" }).click();
      await arcSave;
      // 确认即前进 → 文风
      await expect(
        page.locator(".settings-v main h2", { hasText: "文风" }),
      ).toBeVisible({ timeout: 5000 });
      // 左栏：主线徽标已确认（进度数字随建书 seed 变，不锚绝对数——锚徽标与 status API）
      await page.locator(".settings-v .col-tree").getByText("主线", { exact: true }).click();
      await expect(
        page.locator(".settings-v .col-tree .s-item", { hasText: "主线" }).getByText("已确认"),
      ).toBeVisible();
      // 已确认态：按钮转「保存修改」，再点＝保存（不弹确认语义）
      await page.locator(".panel-foot").getByRole("button", { name: "保存修改" }).click();
      await expect(page.getByText(/已保存/).first()).toBeVisible({ timeout: 5000 });

      // 后端直查：fullstory 契约 + 镜像 + volumes 空
      const arc = await apiGetJSON(request, token, `/novels/${pid}/story/arc`);
      expect(arc.fullstory).toContain("听证会上揭开真相");
      expect(arc.premise).toBe(arc.fullstory);
      expect(arc.ending.tone).toBe("苍凉但平静");
      const status = await apiGetJSON(request, token, `/novels/${pid}/settings/status`);
      expect(status["story-arc"]).toBe(true);
    } finally {
      await restore();
    }
  });

  test("三问脏态：切面板弹 confirm，接受则切走", async ({ page }) => {
    const { restore } = await setupSession(page, "trial");
    try {
      await createNovel(page, `主线脏态${Date.now() % 100000}`);
      await openArcPanel(page);
      await page.locator('[data-od-id="arc-ending-tone"]').fill("意难平");
      page.once("dialog", (d) => d.accept());
      await page.locator(".s-item", { hasText: "文风" }).click();
      await expect(page.locator(".settings-v main h2", { hasText: "文风" })).toBeVisible();
    } finally {
      await restore();
    }
  });
});

test.describe("主线 AI（会员，浏览器侧打桩）", () => {
  test("起草主线：弹窗出卡 → 采纳写回 → 回执一步撤销", async ({ page }) => {
    const { restore } = await setupSession(page, "trial");
    try {
      await createNovel(page, `主线起草${Date.now() % 100000}`);
      await stubArcAi(page, (action) => ({
        status: 200,
        body: { value: action === "draft" ? {
          fullstory: "AI 全景：陆征追查失踪案触及保护伞，最后听证会翻案。",
          ending: { scene: "AI 画面", hero: "AI 归宿", tone: "苦尽甘来" },
        } : {} },
      }));
      await openArcPanel(page);
      await page.locator('.col-ai [data-aiact="draft"]').click();
      // 结果进 arc-ai-card 弹窗（portal 到 body），卡体带草稿内容与版数徽标
      const card = page.getByTestId("arc-ai-card");
      await expect(card).toBeVisible({ timeout: 5000 });
      await expect(card).toContainText("AI 全景：陆征追查失踪案触及保护伞");
      await expect(page.getByTestId("ai-card-version")).toHaveText("第 1 版");
      // 采纳 → 弹窗关 + 写回全景与三问
      await page.getByTestId("ai-card-adopt").click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(page.locator('[data-od-id="arc-fullstory"]')).toHaveValue(/AI 全景/, { timeout: 8000 });
      await expect(page.locator('[data-od-id="arc-ending-tone"]')).toHaveValue("苦尽甘来");
      // 回执一步撤销 → 还原
      await page.locator(".panel-foot").getByRole("button", { name: "撤销" }).click();
      await expect(page.locator('[data-od-id="arc-fullstory"]')).toHaveValue("");
      await expect(page.locator('[data-od-id="arc-ending-tone"]')).toHaveValue("");
    } finally {
      await restore();
    }
  });

  test("行内基调 AI：500 → 弹窗错误体 → 换一个重试成功 → 采纳写回", async ({ page }) => {
    const { restore } = await setupSession(page, "trial");
    try {
      await createNovel(page, `主线行内${Date.now() % 100000}`);
      let calls = 0;
      await stubArcAi(page, () => {
        calls += 1;
        return calls === 1
          ? { status: 500, body: { detail: "boom" } }
          : { status: 200, body: { value: { tone: "苦尽甘来" } } };
      });
      await openArcPanel(page);
      // 第一次点击 → 500（错误 toast 由 vitest 覆盖文案；此处验行为未死锁）
      const firstCall = page.waitForResponse((r) => r.url().includes("/ai/arc/tone"));
      await page.locator('[data-od-id="arc-tone-ai-fill"]').click();
      await firstCall; // 500 往返真落地（条件等待替代固定 sleep）
      // 无缓存失败：弹窗开着展示错误体，换一个（重试）可用
      const card = page.getByTestId("arc-ai-card");
      await expect(card).toBeVisible({ timeout: 5000 });
      await expect(page.getByTestId("ai-card-error")).toBeVisible();
      // 换一个 → 第二次请求成功，卡体出建议（失败不计版数，成功后＝第 1 版）
      await page.getByTestId("ai-card-regen").click();
      await expect(card).toContainText("苦尽甘来", { timeout: 5000 });
      await expect(page.getByTestId("ai-card-version")).toHaveText("第 1 版");
      // 采纳 → 弹窗关 + 写回基调
      await page.getByTestId("ai-card-adopt").click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(page.locator('[data-od-id="arc-ending-tone"]')).toHaveValue("苦尽甘来");
    } finally {
      await restore();
    }
  });

  test("主线体检：报告卡弹窗（无写回键）+ 确认按钮仍可点 + 重新检查", async ({ page }) => {
    const { restore } = await setupSession(page, "trial");
    try {
      await createNovel(page, `主线体检${Date.now() % 100000}`);
      await stubArcAi(page, (action) => ({
        status: 200,
        body: { value: action === "check" ? {
          checks: [
            { name: "故事连贯", status: "ok", note: "一条线到底" },
            { name: "开头接结局", status: "ok", note: "闭环" },
            { name: "三问对得上", status: "warn", note: "基调与画面差一点" },
            { name: "和简介一个方向", status: "miss", note: "简介为空，先补再查更准" },
          ],
          summary: "主线立得住",
        } : {} },
      }));
      await openArcPanel(page);
      await page.locator('.col-ai [data-aiact="check"]').click();
      const card = page.getByTestId("arc-ai-card");
      await expect(card).toBeVisible({ timeout: 5000 });
      await expect(card).toContainText("三问对得上");
      // 报告卡只提醒：无写回键（footer 只有 关闭 + 重新检查）
      await expect(page.getByTestId("ai-card-adopt")).toHaveCount(0);
      // 只提醒不拦确认
      await expect(
        page.locator(".panel-foot").getByRole("button", { name: "确认完成" }),
      ).toBeEnabled();
      // 重新检查可用：报告卡保持在弹窗内刷新
      await page.getByTestId("ai-card-regen").click();
      await expect(card).toContainText("三问对得上", { timeout: 5000 });
    } finally {
      await restore();
    }
  });

  test("换一个重生成：版数递增；重开展示缓存不发新请求（D9）", async ({ page }) => {
    const { restore } = await setupSession(page, "trial");
    try {
      await createNovel(page, `主线历史${Date.now() % 100000}`);
      let calls = 0;
      await stubArcAi(page, () => ({ status: 200, body: {} })); // ai-model 就绪桩（tone 路由下面单独接管）
      await page.route(/\/api\/novels\/[^/]+\/settings\/ai\/arc\/tone/, async (route) => {
        calls += 1;
        if (calls === 2) await new Promise((r) => setTimeout(r, 400)); // 第二版放慢：钉 D3 在途态
        return route.fulfill({
          status: 200,
          body: JSON.stringify({ value: { tone: `第${calls}版` } }),
          contentType: "application/json",
        });
      });
      await openArcPanel(page);
      const btn = page.locator('[data-od-id="arc-tone-ai-fill"]');
      const card = page.getByTestId("arc-ai-card");
      await btn.click();
      await expect(card).toContainText("第1版", { timeout: 5000 });
      await expect(page.getByTestId("ai-card-version")).toHaveText("第 1 版");
      // 换一个在途（D3）：旧版保持可见、采纳键仍 enabled（禁用的只是「换一个」）
      const regenResp = page.waitForResponse((r) => r.url().includes("/ai/arc/tone"));
      await page.getByTestId("ai-card-regen").click();
      await expect(page.getByTestId("ai-card-adopt")).toBeEnabled();
      await expect(card).toContainText("第1版");
      await regenResp;
      // 第二版落地：卡体刷新 + 版数徽标递增（历史切条退役，只留最新一版）
      await expect(card).toContainText("第2版", { timeout: 5000 });
      await expect(page.getByTestId("ai-card-version")).toHaveText("第 2 版");
      // 采纳 → 写回的是当前版
      await page.getByTestId("ai-card-adopt").click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(page.locator('[data-od-id="arc-ending-tone"]')).toHaveValue("第2版");
      // 同一能力行再点＝重开缓存（D9）：弹窗带来源提示条，请求计数不变
      await btn.click();
      await expect(card).toBeVisible({ timeout: 5000 });
      await expect(page.getByTestId("ai-card-cache")).toBeVisible();
      expect(calls).toBe(2);
    } finally {
      await restore();
    }
  });

  test("落库后回执消失：确认成功 → 撤销不可达", async ({ page }) => {
    const { restore } = await setupSession(page, "trial");
    try {
      await createNovel(page, `主线落库${Date.now() % 100000}`);
      await stubArcAi(page, () => ({ status: 200, body: { value: { tone: "苦尽甘来" } } }));
      await openArcPanel(page);
      await page.locator('[data-od-id="arc-tone-ai-fill"]').click();
      await expect(page.getByTestId("arc-ai-card")).toBeVisible({ timeout: 5000 });
      await page.getByTestId("ai-card-adopt").click();
      await expect(page.locator(".panel-foot").getByRole("button", { name: "撤销" })).toBeVisible();
      // 确认完成（save 成功 → 回执清空）
      await page.locator(".panel-foot").getByRole("button", { name: "确认完成" }).click();
      await expect(
        page.locator(".settings-v main h2", { hasText: "文风" }),
      ).toBeVisible({ timeout: 5000 });
    } finally {
      await restore();
    }
  });
});

test.describe("免费版", () => {
  test("AI 点击 → 0 请求 + 统一升级 toast；手填全流程不受影响", async ({ page, request }) => {
    const { restore, token } = await setupSession(page, "none");
    try {
      const pid = await createNovel(page, `主线免费${Date.now() % 100000}`);
      await openArcPanel(page);

      // 双层防御：前端 aiState=member_required 预拦（0 请求），或后端 403 后统一升级
      // toast——docker 后端就绪态判定下请求可能真发出（1 次），两者都可接受；关键是
      // 给出统一升级提示且不写回。
      let aiCalls = 0;
      await page.route(/\/api\/novels\/[^/]+\/settings\/ai\/arc\//, (route) => {
        aiCalls += 1;
        return route.fulfill({ status: 403, body: JSON.stringify({ detail: { reason: "member_required" } }), contentType: "application/json" });
      });
      await page.locator('.col-ai [data-aiact="draft"]').click();
      // 统一升级提示：rail guard 的 onBlocked toast 或 403 后 MemberBlockPrompt，二者其一
      await expect(
        page.getByText(/会员功能|开通|升级 PRO 后解锁/).first(),
      ).toBeVisible({ timeout: 8000 });
      await page.locator('[data-od-id="arc-tone-ai-fill"]').click();
      // 预拦=0 请求；穿透=恰好 1 发 403：等往返或确认无请求（替代固定 sleep）
      await Promise.race([
        page.waitForResponse((r) => r.url().includes("/ai/arc/tone")).catch(() => null),
        page.waitForTimeout(1500),
      ]);
      expect(aiCalls).toBeLessThanOrEqual(1); // 预拦则 0；穿透则恰好 1（403 后不再重试）
      await expect(page.locator('[data-od-id="arc-ending-tone"]')).toHaveValue(""); // 不写回
      // 403 穿透时全局升级弹窗（MemberBlockPrompt 模态，事件异步挂载）会挡住面板——
      // 确定性关闭：等标题出现再点「稍后再说」；前端预拦（0 请求）时无弹窗，短等后跳过
      const promptTitle = page.getByText("PRO 专属功能");
      if (await promptTitle.waitFor({ state: "visible", timeout: 3000 }).then(() => true).catch(() => false)) {
        await page.getByRole("button", { name: "稍后再说" }).click();
      }

      // 手填不受影响（确认全流程已由 PRO 用例覆盖，免费版验「手填+存草稿」即可等价）
      await fillArc(page, { tone: "苦尽甘来" });
      const draftSave = page.waitForResponse(
        (r) => r.request().method() === "PUT" && /\/story\/arc$/.test(r.url()),
      );
      await page.locator(".panel-foot").getByRole("button", { name: "存草稿" }).click();
      await draftSave;
      const arc = await apiGetJSON(request, token, `/novels/${pid}/story/arc`);
      expect(arc.fullstory).toContain("听证会上揭开真相");
      expect(arc.ending.tone).toBe("苦尽甘来");
    } finally {
      await restore();
    }
  });
});

test.describe("存量兼容（legacy premise + volumes）", () => {
  test("旧形状 KV：打开不炸 / fullstory 显示旧 premise / 保存镜像 / volumes 保留 / 无分卷区", async ({ page, request }) => {
    const { restore, token } = await setupSession(page, "trial");
    try {
      const pid = await createNovel(page, `主线存量${Date.now() % 100000}`);
      // 旧客户端整份 PUT（legacy 形状：premise + volumes 两行）
      await apiPutJSON(request, token, `/novels/${pid}/story/arc`, {
        premise: "旧一句话主线：陆征查案",
        ending: { scene: "", hero: "", tone: "" },
        volumes: [
          { title: "失踪", conflict: "追查失踪案", chapters: "10" },
          { title: "待定", conflict: "待定", chapters: "?" },
        ],
      });

      await openArcPanel(page);
      // 归一显示：fullstory 框显示旧 premise；无分卷区；不炸
      await expect(page.locator('[data-od-id="arc-fullstory"]')).toHaveValue("旧一句话主线：陆征查案");
      await expect(page.getByText("加一卷")).toHaveCount(0);

      // 新契约保存（改基调）：镜像 + volumes 原样保留
      await page.locator('[data-od-id="arc-ending-tone"]').fill("苦尽甘来");
      const saveOk = page.waitForResponse(
        (r) => r.request().method() === "PUT" && /\/story\/arc$/.test(r.url()),
      );
      await page.locator(".panel-foot").getByRole("button", { name: "存草稿" }).click();
      await saveOk;
      const arc = await apiGetJSON(request, token, `/novels/${pid}/story/arc`);
      expect(arc.fullstory).toBe("旧一句话主线：陆征查案");
      expect(arc.premise).toBe(arc.fullstory);
      expect(arc.ending.tone).toBe("苦尽甘来");
      expect(arc.volumes.map((v: { title: string }) => v.title)).toEqual(["失踪", "待定"]);
    } finally {
      await restore();
    }
  });

  test("前端容错：GET 返回 legacy 形状也能显示", async ({ page, request }) => {
    const { restore, token } = await setupSession(page, "trial");
    try {
      const pid = await createNovel(page, `主线容错${Date.now() % 100000}`);
      // route-stub GET 旧形状（模拟直连旧后端）——前端 fetch 兜底 d.fullstory ?? d.premise
      await page.route(/\/api\/novels\/[^/]+\/story\/arc$/, (route) => {
        if (route.request().method() !== "GET") return route.continue();
        return route.fulfill({
          status: 200,
          body: JSON.stringify({ premise: "仅旧字段", ending: { scene: "", hero: "", tone: "" }, volumes: [] }),
          contentType: "application/json",
        });
      });
      await openArcPanel(page);
      await expect(page.locator('[data-od-id="arc-fullstory"]')).toHaveValue("仅旧字段");
      void token; void pid;
    } finally {
      await restore();
    }
  });
});
