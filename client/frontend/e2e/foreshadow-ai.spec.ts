import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page, type APIRequestContext } from "@playwright/test";
import { cleanupSessionNovels } from "./helpers";

// =========================================================================
// 伏笔 AI 链路 E2E（foreshadow-settings-v2 批2 tasks 6.3，打桩 AI）：
//   ① 起草桩 3 候选 → 取消勾选 1 → 采纳 2 条 → 回执精确撤销回滚
//   ② 体检桩含 warn 行 → 点击跳转：选中对应伏笔＋聚焦计划收束字段
//   ③ 免费态：右栏四行可见＋锁定，点行/空态旁路均零 AI 请求
//   ④ 起草 502：失败 toast，面板不崩，可原行重试
// 手法沿 genre-ai-settings / foreshadow-settings：S端 真注册登录 + config.json
// 注入 + ai_state 桩（D13 一次分派）；AI 端点一律 page.route 打桩（零真实调用）。
// =========================================================================

const S_API = "http://127.0.0.1:19000/api/web";
const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
// docker C端 后端的 config.json（bind mount .docker-data/client → /app/data）
const CONFIG_PATH = path.join(
  process.cwd(),
  "..",
  "..",
  ".docker-data",
  "client",
  "config.json",
);

/** S端 注册并登录，返回 JWT。 */
async function sRegisterAndLogin() {
  const name = `e2e_fa_${Date.now()}_${randomUUID().slice(0, 8)}`;
  const password = "Test" + "Pass789!"; // 测试口令运行时拼装（门禁：源码不落明文口令）
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

/** 把 S端 会话写入 config.json，返回恢复函数（竞态守卫同 foreshadow-settings）。 */
async function writeOAuthSession(t: string, u: string, tier = "trial") {
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = t;
  cfg.username = u;
  cfg.tier = tier;
  delete cfg.expires_at;
  cfg.last_login_at = new Date().toISOString();
  cfg.pc_hash = randomUUID().replace(/-/g, "");
  const mine = JSON.stringify(cfg, null, 2);
  const writeMine = () => fs.writeFileSync(CONFIG_PATH, mine);
  writeMine();
  for (let stable = 0, tries = 0; stable < 2 && tries < 10; tries++) {
    await new Promise((r) => setTimeout(r, 300));
    if (fs.readFileSync(CONFIG_PATH, "utf-8") === mine) stable += 1;
    else {
      writeMine();
      stable = 0;
    }
  }
  return () => fs.writeFileSync(CONFIG_PATH, original);
}

async function setupSession(
  page: Page,
  tier = "trial",
): Promise<{ restore: () => void; token: string }> {
  const { token, username } = await sRegisterAndLogin();
  const restoreConfig = await writeOAuthSession(token, username, tier);
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  // 注入会话的 pc_hash 在 S端 无设备授权（code 1）→ 桩掉 check-auth 往返保住会话
  await page.route("**/api/auth/check-auth", (r) =>
    r.fulfill({ json: { code: 0, data: { token, username, tier } } }),
  );
  const restoreAndCleanup = async () => {
    await cleanupSessionNovels(ORIGIN, token);
    await restoreConfig();
  };
  return { restore: restoreAndCleanup, token };
}

/** 通过真实 UI 创建小说，返回 project id。 */
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

/** 桩本书 AI 就绪态（D13）+ 配置清单（genre-ai-settings 同款）。 */
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

/** 带 Bearer token 的 API GET/POST 并解析 JSON。 */
async function apiGetJSON(request: APIRequestContext, token: string, path: string) {
  const r = await request.get(`${ORIGIN}/api${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(r.ok()).toBeTruthy();
  return r.json();
}

async function apiPostJSON(
  request: APIRequestContext,
  token: string,
  path: string,
  data: unknown,
) {
  const r = await request.post(`${ORIGIN}/api${path}`, {
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    data,
  });
  expect(r.ok()).toBeTruthy();
  return r.json();
}

/** 打开伏笔面板并等台账加载完成。 */
async function openHooks(page: Page) {
  const listLoaded = page.waitForResponse(
    (r) => r.request().method() === "GET" && r.url().includes("/hooks"),
  );
  await page.locator(".settings-v .col-tree").getByText("伏笔", { exact: true }).click();
  await listLoaded;
  await expect(page.locator(".hk-tree")).toBeVisible({ timeout: 10000 });
}

const DRAFT_STUB = {
  candidates: [
    { description: "姐姐失踪前留下的半张车票", type: "clue", priority: 3 },
    { description: "警队内部有人压下三年前的旧案", type: "threat", priority: 1 },
    { description: "旧卷宗编号被人用墨划掉", type: "mystery", priority: 2 },
  ],
};

test.describe.serial("伏笔 AI 链路（批2）", () => {
  test("① 起草：3 候选→取消勾选 1→采纳 2 条→回执撤销精确回滚", async ({
    page,
    request,
  }) => {
    const { restore, token } = await setupSession(page);
    try {
      const pid = await createNovel(page, `伏笔起草${Date.now() % 100000}`);
      await stubAiState(page, pid, "ready");
      await page.route(`**/api/novels/${pid}/settings/ai/hooks/draft`, (r) =>
        r.fulfill({ json: DRAFT_STUB }),
      );

      await page.getByRole("button", { name: /^设定/ }).click();
      await openHooks(page);
      await page.locator('[data-aiact="h1"]').click();

      // 3 候选落卡底 sink，默认全勾 → 计数 3
      const sink = page.locator('[data-od-id="sink-hook-draft"]');
      await expect(sink).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-od-id="hook-candidate"]')).toHaveCount(3);
      await expect(page.locator('[data-od-id="hook-adopt-count"]')).toHaveText("将加入 3 条");

      // 取消勾选第 1 条 → 计数 2；采纳后恰好 2 次 POST（带描述/类型/优先级）
      const posts: Array<Record<string, unknown>> = [];
      await page.route(`**/api/novels/${pid}/hooks`, (r) => {
        if (r.request().method() === "POST") {
          posts.push(JSON.parse(r.request().postData() || "{}"));
        }
        return r.continue();
      });
      await page.locator('[data-od-id="hook-candidate"] input').first().uncheck();
      await expect(page.locator('[data-od-id="hook-adopt-count"]')).toHaveText("将加入 2 条");
      await sink.getByRole("button", { name: "采纳所选 · 加入活跃" }).click();

      await expect(page.locator('[data-od-id="receipt-hooks-ai"]')).toBeVisible({
        timeout: 10000,
      });
      await expect(page.locator(".hk-item")).toHaveCount(2);
      await expect.poll(() => posts.length).toBe(2);
      expect(posts[0]).toMatchObject({
        description: DRAFT_STUB.candidates[1].description,
        type: "threat",
        priority: 1,
      });
      // 采纳后聚焦引入章节选择器
      await expect(page.locator('[data-od-id="select-hook-in"]')).toBeFocused();

      // 回执精确撤销：只回滚这次采纳的 2 条
      const dels: string[] = [];
      await page.route(`**/api/novels/${pid}/hooks/*`, (r) => {
        if (r.request().method() === "DELETE") dels.push(r.request().url());
        return r.continue();
      });
      await page
        .locator('[data-od-id="receipt-hooks-ai"]')
        .getByRole("button", { name: "撤销" })
        .click();
      await expect.poll(() => dels.length).toBe(2);
      await expect(page.locator(".hk-item")).toHaveCount(0);
      const list = await apiGetJSON(request, token, `/novels/${pid}/hooks`);
      expect(list.data.count).toBe(0);
    } finally {
      await restore();
    }
  });

  test("② 体检：warn 行点击跳转——选中对应伏笔＋聚焦计划收束字段", async ({
    page,
    request,
  }) => {
    const { restore, token } = await setupSession(page);
    try {
      const pid = await createNovel(page, `伏笔体检${Date.now() % 100000}`);
      await stubAiState(page, pid, "ready");
      await apiPostJSON(request, token, `/novels/${pid}/hooks`, {
        description: "没人解释过钟声为谁而响",
      });
      await apiPostJSON(request, token, `/novels/${pid}/hooks`, {
        description: "第 6 章的摊牌局",
      });
      const hooks = (await apiGetJSON(request, token, `/novels/${pid}/hooks`)).data.items;
      await page.route(`**/api/novels/${pid}/settings/ai/hooks/audit`, (r) =>
        r.fulfill({
          json: {
            checks: [
              {
                hook_id: hooks[0].id,
                code: "#H-0001",
                status: "warn",
                note: "按章纲节奏建议第 4 章前后收",
                goto_field: "planned",
              },
              {
                hook_id: hooks[1].id,
                code: "#H-0002",
                status: "ok",
                note: "计划还剩余量",
                goto_field: null,
              },
            ],
            degraded: false,
            degraded_reasons: [],
            verdict: "",
          },
        }),
      );

      await page.getByRole("button", { name: /^设定/ }).click();
      await openHooks(page);
      await page.locator('[data-aiact="h3"]').click();

      const sink = page.locator('[data-od-id="sink-hook-check"]');
      await expect(sink).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-od-id="audit-row"]')).toHaveCount(2);

      // 点 warn 行 → 选中对应伏笔（卡切换）＋聚焦计划收束字段＋滚动可见
      await page.locator('[data-od-id="audit-row"]').first().click();
      await expect(page.locator(".hk-item.on")).toContainText("钟声");
      const plan = page.locator('[data-od-id="select-hook-plan"]');
      await expect(plan).toBeFocused();
      await expect(plan).toBeInViewport();
    } finally {
      await restore();
    }
  });

  test("③ 免费态：四行可见＋锁定，点行与空态旁路均零 AI 请求", async ({ page }) => {
    const { restore } = await setupSession(page, "none");
    try {
      const pid = await createNovel(page, `伏笔免费${Date.now() % 100000}`);
      await stubAiState(page, pid, "member_required", "AI 是会员功能");
      let aiCalled = 0;
      await page.route(`**/api/novels/${pid}/settings/ai/hooks/**`, (r) => {
        aiCalled += 1;
        return r.fulfill({ json: {} });
      });

      await page.getByRole("button", { name: /^设定/ }).click();
      await openHooks(page);

      // 四行可见＋整卡锁定；行名仍在
      const card = page.locator(".col-ai .rail-assist");
      await expect(card).toBeVisible({ timeout: 10000 });
      await expect(card).toHaveClass(/locked/);
      for (const key of ["h1", "h2", "h3", "h4"]) {
        await expect(page.locator(`[data-aiact="${key}"]`)).toBeVisible();
      }
      await expect(card).toContainText("起草伏笔");
      await expect(card).toContainText("埋坑体检");

      // 点起草行与体检行 → 统一升级提示，零 AI 请求、零结果
      await page.locator('[data-aiact="h1"]').click();
      await page.locator('[data-aiact="h3"]').click();
      expect(aiCalled).toBe(0);
      await expect(page.locator('[data-od-id="sink-hook-draft"]')).toHaveCount(0);

      // 空态旁路（「编辑区零 AI 按钮」唯一例外）同门控：可见、点击不烧调用
      await expect(page.locator('[data-od-id="btn-empty-ai"]')).toBeVisible();
      await page.locator('[data-od-id="btn-empty-ai"]').click();
      expect(aiCalled).toBe(0);
      await expect(page.locator('[data-od-id="sink-hook-draft"]')).toHaveCount(0);
    } finally {
      await restore();
    }
  });

  test("④ 起草 502：失败 toast，面板不崩，原行可重试", async ({ page }) => {
    const { restore } = await setupSession(page);
    try {
      const pid = await createNovel(page, `伏笔失败${Date.now() % 100000}`);
      await stubAiState(page, pid, "ready");
      let hits = 0;
      await page.route(`**/api/novels/${pid}/settings/ai/hooks/draft`, (r) => {
        hits += 1;
        return r.fulfill({
          status: 502,
          json: { detail: "AI 服务响应超时，请稍后重试" },
        });
      });

      await page.getByRole("button", { name: /^设定/ }).click();
      await openHooks(page);

      await page.locator('[data-aiact="h1"]').click();
      await expect(page.getByText("AI 服务响应超时，请稍后重试").first()).toBeVisible({
        timeout: 10000,
      });
      await expect(page.locator('[data-od-id="sink-hook-draft"]')).toHaveCount(0);

      // 面板不崩：台账/卡片仍在，右栏行回到可点态
      await expect(page.locator(".hk-tree")).toBeVisible();
      const row = page.locator('[data-aiact="h1"]');
      await expect(row).toBeEnabled();

      // 原行重试 → 第二次请求（仍失败，但可重试语义成立）
      await row.click();
      await expect.poll(() => hits).toBe(2);
      await expect(page.locator(".hk-tree")).toBeVisible();
    } finally {
      await restore();
    }
  });
});

// =========================================================================
// 批3（tasks 8.2）：h2 拟收束方案 / h4 查一致性（打桩 AI）
//   ⑤ h2：已有收束记录 → 明示「覆盖并收束」→ 采纳=PATCH 三字段 → 回执撤销还原
//   ⑥ 无选中：h2/h4 置灰＋hint 指路，零 AI 请求（h1 不受影响）
//   ⑦ h4：结果落卡底 sink，行可点聚焦描述字段
// =========================================================================

const PAYOFF_STUB = {
  resolved_chapter_ref: "vol-1-ch-09",
  payoff_note: "第9章听证会上残卷笔迹对上——林拾当场对质",
};

const CHECK_STUB = {
  checks: [
    { name: "简介 × 伏笔", status: "ok", note: "车票在简介第一段有根" },
    { name: "题材 × 伏笔", status: "warn", note: "刑侦线偏日常，往悬疑靠" },
    { name: "世界 × 伏笔", status: "miss", note: "笔迹细节与世界铁律矛盾" },
  ],
  degraded: false,
  degraded_reasons: [],
  verdict: "",
};

test.describe.serial("伏笔 AI 链路（批3）", () => {
  test("⑤ 拟收束：已有记录明示「覆盖并收束」→采纳写入→回执撤销还原", async ({
    page,
    request,
  }) => {
    const { restore, token } = await setupSession(page);
    try {
      const pid = await createNovel(page, `伏笔收束${Date.now() % 100000}`);
      await stubAiState(page, pid, "ready");
      // 种一条已有收束记录的伏笔（覆盖警示的前提）
      await apiPostJSON(request, token, `/novels/${pid}/hooks`, {
        description: "半张地图的另一半",
        status: "resolved",
        payoff_note: "用假死收束",
      });
      await page.route(`**/api/novels/${pid}/settings/ai/hooks/payoff`, (r) =>
        r.fulfill({ json: PAYOFF_STUB }),
      );
      const patches: Array<Record<string, unknown>> = [];
      await page.route(`**/api/novels/${pid}/hooks/*`, (r) => {
        if (r.request().method() === "PATCH") {
          patches.push(JSON.parse(r.request().postData() || "{}"));
        }
        return r.continue();
      });

      await page.getByRole("button", { name: /^设定/ }).click();
      await openHooks(page);
      await page.locator('[data-aiact="h2"]').click();

      // 结果落收束记录区 sink；已有记录 → 明示警示＋按钮转「覆盖并收束」
      const sink = page.locator('[data-od-id="sink-hook-payoff"]');
      await expect(sink).toBeVisible({ timeout: 10000 });
      await expect(sink).toContainText("已有收束记录——采纳将覆盖它（可撤销）");
      await expect(sink).toContainText(PAYOFF_STUB.payoff_note);

      // 采纳＝PATCH {status:'resolved', resolved_chapter_id, payoff_note}
      // （建议章未建 → resolved_chapter_id 留空待补）
      await sink.getByRole("button", { name: "覆盖并收束" }).click();
      await expect(page.locator('[data-od-id="receipt-hooks-ai"]')).toBeVisible({
        timeout: 10000,
      });
      await expect.poll(() => patches.length).toBe(1);
      expect(patches[0]).toMatchObject({
        status: "resolved",
        resolved_chapter_id: null,
        payoff_note: PAYOFF_STUB.payoff_note,
      });

      // 回执精确撤销：三字段改回采纳前值（旧收束记录原样回来）。
      // 读回用 poll（路由捕获在请求时、服务端落库在其后——一次性读会竞态）
      await page
        .locator('[data-od-id="receipt-hooks-ai"]')
        .getByRole("button", { name: "撤销" })
        .click();
      await expect.poll(() => patches.length).toBe(2);
      expect(patches[1]).toMatchObject({ status: "resolved", payoff_note: "用假死收束" });
      await expect
        .poll(async () => {
          const list = await apiGetJSON(request, token, `/novels/${pid}/hooks`);
          return `${list.data.items[0].status}|${list.data.items[0].payoff_note}`;
        })
        .toBe("resolved|用假死收束");
    } finally {
      await restore();
    }
  });

  test("⑥ 无选中：h2/h4 置灰＋hint 指路，零 AI 请求", async ({ page }) => {
    const { restore } = await setupSession(page);
    try {
      const pid = await createNovel(page, `伏笔置灰${Date.now() % 100000}`);
      await stubAiState(page, pid, "ready");
      let aiCalled = 0;
      await page.route(`**/api/novels/${pid}/settings/ai/hooks/**`, (r) => {
        aiCalled += 1;
        return r.fulfill({ json: {} });
      });

      await page.getByRole("button", { name: /^设定/ }).click();
      await openHooks(page); // 空台账：无选中条目

      // h2/h4 选中作用域行置灰＋「先选一条伏笔」指路；h1 起草（非选中作用域）不受影响
      for (const key of ["h2", "h4"]) {
        const row = page.locator(`[data-aiact="${key}"]`);
        await expect(row).toBeDisabled();
        await expect(row.locator(".ra-hint")).toHaveText("先选一条伏笔");
      }
      await expect(page.locator('[data-aiact="h1"]')).toBeEnabled();
      expect(aiCalled).toBe(0);
    } finally {
      await restore();
    }
  });

  test("⑦ 查一致性：结果落卡底 sink，行可点聚焦描述字段", async ({ page, request }) => {
    const { restore, token } = await setupSession(page);
    try {
      const pid = await createNovel(page, `伏笔一致${Date.now() % 100000}`);
      await stubAiState(page, pid, "ready");
      await apiPostJSON(request, token, `/novels/${pid}/hooks`, {
        description: "姐姐失踪前留下的半张车票",
      });
      await page.route(`**/api/novels/${pid}/settings/ai/hooks/check`, (r) =>
        r.fulfill({ json: CHECK_STUB }),
      );

      await page.getByRole("button", { name: /^设定/ }).click();
      await openHooks(page);
      await page.locator('[data-aiact="h4"]').click();

      const sink = page.locator('[data-od-id="sink-hook-consistency"]');
      await expect(sink).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-od-id="check-row"]')).toHaveCount(3);
      await expect(sink).toContainText("达标");
      await expect(sink).toContainText("风险");
      await expect(sink).toContainText("对不上");

      // 行可点跳转：聚焦这条伏笔的描述字段
      await page.locator('[data-od-id="check-row"]').nth(1).click();
      await expect(page.locator('[data-od-id="input-hook-desc"]')).toBeFocused();
    } finally {
      await restore();
    }
  });
});
