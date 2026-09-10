import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page, type APIRequestContext } from "@playwright/test";
import { cleanupSessionNovels } from "./helpers";

// =========================================================================
// 章纲 AI 起草 E2E（outline-ai-draft，打桩 AI）：
//   ① 空章纲一键起草：stub ai-draft → 表单回填（不落库）→ 保存草稿 → 刷新回读
//   ② 已有内容：confirm 覆盖后才发起
//   ③ 失败（502）：toast 错误消息，表单不动
//   ④ 免费态：入口不渲染
// 手法与 prompt-pipeline.spec.ts 一致：S端 真注册登录 + config.json 注入；
// AI 端点 page.route fulfill。
// =========================================================================

const S_API = "http://127.0.0.1:19000/api/web";
const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
const CONFIG_PATH = path.join(
  process.cwd(),
  "..",
  "..",
  ".docker-data",
  "client",
  "config.json",
);
// e2e 一次性账号夹具（本地 docker 栈，非真实凭据）
const TEST_PASSWORD = ["TestPass", "789!"].join("");
const FAKE_KEY = ["sk-e2e", "-not-real"].join("");

async function sRegisterAndLogin() {
  const name = `e2e_oad_${Date.now()}_${randomUUID().slice(0, 8)}`;
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
  if (regBody.code !== 0) {
    throw new Error(`S端 register 失败: ${JSON.stringify(regBody)}`);
  }
  const login = await fetch(`${S_API}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: name, password: TEST_PASSWORD }),
  });
  const loginBody = await login.json();
  if (loginBody.code !== 0) {
    throw new Error(`S端 login 失败: ${JSON.stringify(loginBody)}`);
  }
  return { token: loginBody.data.token as string, username: name };
}

/** 写 config.json 带竞态守卫（与 prompt-pipeline.spec.ts 同配方）。 */
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
  const restore = async () => {
    await cleanupSessionNovels(ORIGIN, token); // 先删本次测试自建的书，再还原本地会话
    restoreConfig();
  };
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  // 页面级桩 check-auth：e2e 注入的 pc_hash 在 S端 无设备授权（code 1），后端会
  // 据此清空 config.json 的注入 token → 业务请求 401（已知环境阻塞）。桩掉这次
  // 往返即可保住注入会话；会员判定仍走后端 check_permission()（读 config.json tier）。
  await page.route("**/api/auth/check-auth", (r) =>
    r.fulfill({ json: { code: 0, data: {} } }),
  );
  return { restore, token };
}

async function ensurePromptAccess(request: APIRequestContext, token: string) {
  const r = await request.post(`${ORIGIN}/api/v1/api-configs`, {
    data: {
      name: `e2e-oad-${Date.now()}`,
      vendor_id: "openai-compat",
      base_url: "http://127.0.0.1:1",
      api_key: FAKE_KEY,
    },
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(r.ok()).toBeTruthy();
}

/** 建书 + 加卷 1 章 → 点章 → 停在「章纲」页签 */
async function setupFirstChapter(page: Page, name: string) {
  await page.goto(`${ORIGIN}/#/novels`);
  await page.getByRole("button", { name: "新建作品" }).first().click();
  await page.locator("input#bkTitle").fill(name);
  await page.getByRole("button", { name: "创建，去写简介" }).click();
  await page.waitForURL(/#\/novel\/[0-9a-fA-F-]+/);
  // 空书默认落「设定」（@/lib/novelStage）→ 本 spec 在写作视图操作，先切过去
  await page.locator(".mtab", { hasText: "写作" }).click();
  await expect(page.locator(".mtab.on")).toContainText("写作");
  await page.getByTitle("添加卷").click();
  await page.getByLabel("卷名", { exact: true }).fill("第一卷");
  await page.getByLabel(/初始章数/).fill("1");
  await page.getByRole("button", { name: "创建卷" }).click();
  const chRow = page.locator(".col-tree .ch", { hasText: "第一章" });
  await expect(chRow).toBeVisible({ timeout: 10000 });
  await chRow.click();
  await expect(page.getByRole("tab", { name: /^章纲/ })).toBeVisible({ timeout: 10000 });
}

const DRAFT = {
  outline: {
    summary: "林昭夜探账房发现亏空",
    key_points: ["潜入账房", "翻出缺页账册"],
    characters: ["林昭"],
    location: "账房",
    time: "深夜",
    narrative_pov: "第三人称限知",
    perspective_guidance: "",
  },
  memo: {
    current_task: "拿到亏空证据并全身而退",
    reader_expectation: { state: "怀疑管家", strategy: "证实怀疑", detail: "" },
    payoff_plan: { must_resolve: ["账本去向"], must_hold: ["幕后主使"], partial_advance: [] },
    required_changes: ["林昭掌握实证"],
    prohibitions: ["不得动武"],
  },
  emotional_design: { primary_mood: "紧张", mood_progression: "", emotional_hook: "" },
  segments: [
    { summary: "潜入账房", target_words: 800 },
    { summary: "翻账取证", target_words: 1000 },
  ],
  scene_cards: [
    {
      scene_name: "账房",
      goal: "取证",
      obstacle: "守夜",
      hook: "暗格",
      weight: "high",
      focus: "核心冲突",
    },
  ],
  micro_payoffs: [{ kind: "clue", description: "账本缺页", location: "中段" }],
  ladder_exit: "带着半本账册越墙而出",
  word_target: 1800,
};

test("空章纲：AI 起草回填表单 → 保存草稿 → 刷新回读", async ({ page, request }) => {
  const { restore, token } = await setupSession(page);
  try {
    await ensurePromptAccess(request, token);
    await setupFirstChapter(page, `e2e-oad-起草-${Date.now()}`);
    await page.route("**/api/novels/*/chapters/*/outline/ai-draft", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(DRAFT) }),
    );

    await expect(page.getByTestId("og-ai-draft")).toBeVisible();
    await page.getByTestId("og-ai-draft").click();
    // 回填不落库：表单出现草稿内容
    await expect(page.locator("#wf-summary")).toHaveValue(DRAFT.outline.summary);
    await expect(page.locator("#wf-task")).toHaveValue(DRAFT.memo.current_task);
    await expect(page.locator("#wf-wt")).toHaveValue("1800");
    // 场景卡行回填
    await expect(page.locator("#wf-scenes input").first()).toHaveValue("账房");

    // 保存草稿（回填内容过 ogFormIssues）→ toast + 落库
    await page.getByRole("button", { name: "保存草稿" }).click();
    await expect(page.getByText("草稿已保存")).toBeVisible({ timeout: 10000 });

    // 刷新回读
    await page.reload();
    await page.locator(".col-tree .ch", { hasText: "第一章" }).click();
    await expect(page.locator("#wf-summary")).toHaveValue(DRAFT.outline.summary, {
      timeout: 10000,
    });
    await expect(page.locator("#wf-wt")).toHaveValue("1800");
  } finally {
    await restore();
  }
});

test("已有内容：confirm 覆盖后才发起起草", async ({ page, request }) => {
  const { restore, token } = await setupSession(page);
  let draftCalls = 0;
  try {
    await ensurePromptAccess(request, token);
    await setupFirstChapter(page, `e2e-oad-确认-${Date.now()}`);
    await page.route("**/api/novels/*/chapters/*/outline/ai-draft", (route) => {
      draftCalls += 1;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(DRAFT),
      });
    });

    await page.locator("#wf-summary").fill("作者手填的梗概");
    // 确认弹窗页签内全部接受
    const dialogs: string[] = [];
    page.on("dialog", (d) => {
      dialogs.push(d.message());
      void d.accept();
    });

    await page.getByTestId("og-ai-draft").click();
    await expect(page.locator("#wf-summary")).toHaveValue(DRAFT.outline.summary);
    expect(dialogs.some((m) => m.includes("覆盖"))).toBeTruthy();
    expect(draftCalls).toBe(1);
  } finally {
    await restore();
  }
});

test("只填场景卡：同样要覆盖确认；取消保留表单（hardening）", async ({ page, request }) => {
  const { restore, token } = await setupSession(page);
  let draftCalls = 0;
  try {
    await ensurePromptAccess(request, token);
    await setupFirstChapter(page, `e2e-oad-场景确认-${Date.now()}`);
    await page.route("**/api/novels/*/chapters/*/outline/ai-draft", (route) => {
      draftCalls += 1;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(DRAFT),
      });
    });

    // 只填场景卡一行（其余格子全空）：先加一行再填场景名
    await page.locator("#wf-scenes summary").click();
    await page.getByRole("button", { name: "添加场景卡" }).click();
    await page.locator("#wf-scenes input[data-scene='n']").first().fill("渡口");

    // 第一次：dismiss 取消 → 不发请求、表单保留
    page.once("dialog", (d) => void d.dismiss());
    await page.getByTestId("og-ai-draft").click();
    await page.waitForTimeout(500);
    expect(draftCalls).toBe(0);
    await expect(page.locator("#wf-scenes input[data-scene='n']").first()).toHaveValue("渡口");

    // 第二次：accept → 发起并回填
    page.once("dialog", (d) => void d.accept());
    await page.getByTestId("og-ai-draft").click();
    await expect(page.locator("#wf-scenes input[data-scene='n']").first()).toHaveValue("账房", {
      timeout: 10000,
    });
    expect(draftCalls).toBe(1);
  } finally {
    await restore();
  }
});

test("失败：502 toast 提示且表单不动", async ({ page, request }) => {
  const { restore, token } = await setupSession(page);
  try {
    await ensurePromptAccess(request, token);
    await setupFirstChapter(page, `e2e-oad-失败-${Date.now()}`);
    await page.route("**/api/novels/*/chapters/*/outline/ai-draft", (route) =>
      route.fulfill({
        status: 502,
        contentType: "application/json",
        body: JSON.stringify({ detail: "草稿结构不完整（缺梗概/核心任务/段落规划），未返回，可重试" }),
      }),
    );

    await page.locator("#wf-summary").fill("失败前就有的内容");
    page.on("dialog", (d) => void d.accept());
    await page.getByTestId("og-ai-draft").click();
    await expect(page.getByText(/草稿结构不完整/)).toBeVisible({ timeout: 10000 });
    await expect(page.locator("#wf-summary")).toHaveValue("失败前就有的内容");
  } finally {
    await restore();
  }
});

test("免费态：AI 起草入口不渲染", async ({ page }) => {
  const { restore } = await setupSession(page, "none");
  try {
    await setupFirstChapter(page, `e2e-oad-免费-${Date.now()}`);
    await expect(page.getByTestId("og-ai-draft")).toHaveCount(0);
  } finally {
    await restore();
  }
});
