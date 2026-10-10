import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page, type APIRequestContext } from "@playwright/test";
import { addFirstChapterViaTree, cleanupSessionNovels, stableClick } from "./helpers";
import { entitlementFor } from "./tier-features";

// =========================================================================
// 提示词 → 正文生成 全链路 E2E（ai-prompt-crafting；c-retire-prompt-polish 后
// 单段式，打桩 AI）：
//   ① AiModal：本次组装稿（标「本次组装」，无润色入口）→ 作家编辑提示词 →
//      「生成正文」（stub /write SSE）→ 正文落 editor
//   ② 完工检查横幅：word_check 字数不足提示 + self_check 规则清单（可关闭）
// 会话/打桩手法与 workbench-features.spec.ts 一致：S端 真注册登录 +
// config.json 注入 trial；AI 端点用 page.route fulfill（不依赖真实模型）。
// =========================================================================

const S_API = process.env.E2E_S_API || "http://127.0.0.1:19000/api/web";
const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
const CONFIG_PATH = path.join(
  process.env.E2E_CLIENT_DATA || path.join(process.cwd(), "..", "..", ".docker-data", "client"),
  "config.json",
);
// e2e 一次性账号夹具（本地 docker 栈，非真实凭据）
const TEST_PASSWORD = ["TestPass", "789!"].join("");
const FAKE_KEY = ["sk-e2e", "-not-real"].join("");

async function sRegisterAndLogin() {
  const name = `e2e_pp_${Date.now()}_${randomUUID().slice(0, 8)}`;
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

/** 写 config.json 带竞态守卫：上一测试 teardown 残留页面的 check-auth（真实
 * pc_hash 命中 grant）会在服务端异步回写冲掉注入 token → 401；写入后观察，
 * 被冲掉即重写，连续两轮稳定才放行。
 */
async function writeOAuthSession(t: string, u: string, tier = "trial") {
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = t;
  cfg.username = u;
  cfg.tier = tier;
  cfg.entitlement = entitlementFor(tier); // 快照单源（tier-features 6.2）
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

async function setupSession(page: Page, tier = "trial"): Promise<{ restore: () => void; token: string }> {
  const { token, username } = await sRegisterAndLogin();
  const restore = await writeOAuthSession(token, username, tier);
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  // 页面级桩 check-auth：e2e 注入的 pc_hash 在 S端 无设备授权（code 1），后端会
  // 据此清空 config.json 的注入 token → 业务请求 401（已知环境阻塞）。桩掉这次
  // 往返即可保住注入会话；会员判定仍走后端 check_permission()（读 config.json tier）。
  await page.route("**/api/auth/check-auth", (r) =>
    r.fulfill({ json: { code: 0, data: {} } }),
  );
  const restoreAndCleanup = async () => {
    await cleanupSessionNovels(ORIGIN, token); // 先删本次测试自建的书，再还原本地会话
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
  // 空书默认落「设定」（@/lib/novelStage：无章节 → 设定，用户 2026-09-10 拍板）；
  // 本 spec 的用例都在写作视图操作 → 建书后显式切过去。
  await page.locator(".mtab", { hasText: "写作" }).click();
  await expect(page.locator(".mtab.on")).toContainText("写作");
  return m[1];
}

async function ensurePromptAccess(request: APIRequestContext, token: string) {
  const r = await request.post(`${ORIGIN}/api/v1/api-configs`, {
    data: {
      name: `e2e-pipeline-${Date.now()}`,
      vendor_id: "openai-compat",
      base_url: "http://127.0.0.1:1",
      api_key: FAKE_KEY,
    },
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(r.ok()).toBeTruthy();
}

/** 空书起手：树底「＋ 新增一章」垫第一卷排第一章 → 点章 → 停在「章纲」页签 */
async function setupFirstChapter(page: Page) {
  await addFirstChapterViaTree(page);
}

const EDITED_PROMPT = [
  "# 整章任务",
  "",
  "城门对峙一场戏：目标是带信入城，守卫盘查是阻碍，通缉令画像是钩子。",
  "章末落点：他收起通缉令，转身没入夜色。",
].join("\n");

test("单段式：AiModal 组装→编辑→生成 + 完工检查横幅（c-retire-prompt-polish）", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    await ensurePromptAccess(request, token);
    await createNovel(page, `管线${Date.now() % 100000}`);
    await setupFirstChapter(page);

    // ── 打桩 AI 端点（不依赖真实模型） ─────────────────────────────────
    // /write SSE（glob 以 /write 结尾：不会误吞 /write/prompt 等子路径；续写端点已随
    // c-retire-continue-writing 退役；提示词润色端点已随 c-retire-prompt-polish 退役）
    const CHUNK = "雨点砸在铁皮棚上，他没有抬头。守卫把通缉令举到火把下比对了很久。";
    const DONE_WORD_CHECK = {
      target: 2500,
      actual: 32,
      below_limit: true,
      message: "字数不足：目标 2500，实写 32",
    };
    const DONE_SELF_CHECK = [
      { rule: "因果自然呈现", excerpts: ["因为画像不像，所以他松了手。"] },
    ];
    let sentPrompt = "";
    await page.route("**/api/novels/*/chapters/*/write", async (route) => {
      try {
        sentPrompt = (JSON.parse(route.request().postData() || "{}") as { prompt?: string })
          .prompt ?? "";
      } catch {
        sentPrompt = "";
      }
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body:
          `data: ${JSON.stringify({ type: "chunk", text: CHUNK })}\n\n` +
          `data: ${JSON.stringify({
            type: "done",
            full_text: CHUNK,
            word_check: DONE_WORD_CHECK,
            self_check: DONE_SELF_CHECK,
          })}\n\n`,
      });
    });

    // ── 阶段一：AiModal 打开 → 本次组装稿（无润色入口） ────────────────
    await page.getByRole("tab", { name: /^正文/ }).click();
    await page.getByTestId("ai-write-btn").click(); // 2026-09-20 AI 入口唯一化右栏
    const ai = page.getByRole("dialog", { name: "AI 生成正文" });
    await expect(ai.getByTestId("ai-prompt")).toBeEnabled({ timeout: 10000 });
    await expect(ai.getByTestId("ai-raw-tag")).toHaveText("本次组装");
    // 退役面：弹窗内不得再有润色入口与两段式文案
    await expect(ai.getByTestId("ai-polish")).toHaveCount(0);
    await expect(ai.getByText("AI 润色")).toHaveCount(0);
    await expect(ai.getByText(/两段式/)).toHaveCount(0);

    // ── 阶段二：作家编辑提示词（组装稿可直接改）────────────────────────
    await ai.getByTestId("ai-prompt").fill(EDITED_PROMPT);

    // ── 阶段三：生成正文 → SSE 落 editor + 完工检查（c-workbench-density：
    // 横幅收缩为编辑态工具行警示胶囊，点开展开明细条）─────────────────────
    await ai.getByTestId("ai-confirm").click();
    const editor = page.locator(".editor");
    await expect(editor).toBeVisible({ timeout: 5000 });
    await expect(editor).toContainText("雨点砸在铁皮棚上", { timeout: 10000 });
    // 编辑稿原样透传给生成端点（弹窗内不再有 AI 改写步骤）
    expect(sentPrompt).toBe(EDITED_PROMPT);

    const pill = page.getByTestId("qc-banner");
    await expect(pill).toBeVisible({ timeout: 10000 });
    await expect(pill).toContainText("字数未达标");
    // 明细条：点胶囊展开（qc-word/qc-self 迁入明细条，定位口径不变）
    await pill.click();
    await expect(page.getByTestId("qc-word")).toContainText("字数未达标");
    await expect(page.getByTestId("qc-word")).toContainText("2500");
    await expect(page.getByTestId("qc-self")).toContainText("因果自然呈现");
    await expect(page.getByTestId("qc-self")).toContainText("1 处");
    // 再点收起明细（胶囊常驻至下次生成，无「知道了」关闭语义）
    await pill.click();
    await expect(page.getByTestId("qc-word")).toHaveCount(0);
  } finally {
    await restore();
  }
});

// ═══ 生成模型选择位（c-prose-model-select）════════════════════════════════════
//  模型域打桩（跨配置 × 多模型 + 本书模型就绪）→ 默认路径请求体不带按次模型对；
//  换到另一配置的模型后请求体携带所选 `api_config_id` + `model`（仅本次生成）；
//  弹层几何：多配置不越出视口（封顶＋整层滚动）、大屏 zoom 下与触发位对齐。

/** 模型域打桩件（不依赖真实 Key/探测）：一条配置 = 组头 + 模型清单。 */
const modelCfg = (id: string, name: string, vendor: string, models: string[]) => ({
  id,
  name,
  vendor,
  vendor_display_name: vendor,
  api_format: "openai",
  base_url: "https://example.com/v1",
  api_key_masked: "sk-•••",
  status: "active",
  last_test_status: "ok",
  last_test_error: null,
  last_tested_at: null,
  models,
  models_updated_at: null,
  created_at: "",
  updated_at: "",
});

/** 起一单「生成正文」链路（会话＋空书一章＋模型域与 /write 桩），返回弹窗入口与抓到的请求体。 */
async function setupModelPickerCase(
  page: Page,
  request: APIRequestContext,
  configs?: Array<Record<string, unknown>>,
) {
  const { restore, token } = await setupSession(page);
  await ensurePromptAccess(request, token);
  await createNovel(page, `选模型${Date.now() % 100000}`);
  await setupFirstChapter(page);

  await page.route("**/api/v1/api-configs", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        configs ?? [
          modelCfg("c1", "深度求索", "deepseek", ["deepseek-v4-pro", "deepseek-v4-flash"]),
          modelCfg("c2", "本地 · Ollama", "ollama", ["qwen2.5:14b"]),
        ],
      ),
    }),
  );
  await page.route("**/api/v1/novels/*/ai-model", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        api_config_id: "c1",
        config_name: "深度求索",
        model: "deepseek-v4-pro",
        ai_state: "ready",
        message: "",
      }),
    }),
  );

  const CHUNK = "雨点砸在铁皮棚上，他没有抬头。";
  const bodies: Array<Record<string, unknown>> = [];
  await page.route("**/api/novels/*/chapters/*/write", async (route) => {
    try {
      bodies.push(JSON.parse(route.request().postData() || "{}"));
    } catch {
      bodies.push({});
    }
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body:
        `data: ${JSON.stringify({ type: "chunk", text: CHUNK })}\n\n` +
        `data: ${JSON.stringify({ type: "done", full_text: CHUNK })}\n\n`,
    });
  });

  await page.getByRole("tab", { name: /^正文/ }).click();
  const openModal = async () => {
    await page.getByTestId("ai-write-btn").click();
    // c-prose-regen-replace：章内已有正文（前一次生成过）→ 先确认清空重写；空章直进
    const regen = page.getByTestId("regen-confirm");
    try {
      await regen.waitFor({ state: "visible", timeout: 3000 });
      await regen.click();
    } catch {
      /* 空章无确认门禁 */
    }
    const ai = page.getByRole("dialog", { name: "AI 生成正文" });
    await expect(ai.getByTestId("ai-prompt")).toBeEnabled({ timeout: 10000 });
    return ai;
  };
  return { restore, bodies, CHUNK, openModal };
}

test("生成模型选择位：默认本书模型不带按次模型对、换模型后进请求体", async ({
  page,
  request,
}) => {
  test.setTimeout(120_000);
  const { restore, bodies, CHUNK, openModal } = await setupModelPickerCase(page, request);
  try {
    const ai = await openModal();

    // 默认＝本书模型：触发位显示「配置名 · 模型名」
    await expect(ai.getByTestId("ai-model-select")).toBeVisible();
    await expect(ai.getByTestId("ai-model-name")).toHaveText("深度求索 · deepseek-v4-pro");
    await ai.getByTestId("ai-confirm").click();
    await expect(page.locator(".editor")).toContainText(CHUNK, { timeout: 10000 });
    // 默认路径：请求体无按次模型对（与今日链路逐字一致）
    expect(bodies[bodies.length - 1]).not.toHaveProperty("api_config_id");
    expect(bodies[bodies.length - 1]).not.toHaveProperty("model");

    // 重开弹窗 → 回本书模型（按次语义：不记忆、不持久）
    const ai2 = await openModal();
    await expect(ai2.getByTestId("ai-model-name")).toHaveText("深度求索 · deepseek-v4-pro");

    // 换到另一配置的模型（弹层 portal 到 body：用 page 级定位）→ 请求体携带该对
    await ai2.getByTestId("ai-model-select").click();
    const panel = page.getByTestId("ai-model-panel");
    await expect(panel).toBeVisible();
    await expect(panel).toContainText("本地 · Ollama");
    await panel.locator('[data-model="c2::qwen2.5:14b"]').click();
    await expect(ai2.getByTestId("ai-model-name")).toHaveText("本地 · Ollama · qwen2.5:14b");
    await ai2.getByTestId("ai-confirm").click();
    await expect.poll(() => bodies.length, { timeout: 10000 }).toBe(2);
    expect(bodies[bodies.length - 1]).toMatchObject({
      api_config_id: "c2",
      model: "qwen2.5:14b",
    });
  } finally {
    await restore();
  }
});

test("生成模型弹层：多配置不越出视口、大屏 zoom 下与触发位对齐（评审整改）", async ({
  page,
  request,
}) => {
  test.setTimeout(120_000);
  const fourConfigs = [
    modelCfg("c1", "深度求索", "deepseek", ["deepseek-v4-pro", "deepseek-v4-flash"]),
    modelCfg("c2", "本地 · Ollama", "ollama", ["qwen2.5:14b", "llama3.1:8b"]),
    modelCfg("c3", "通义 · Qwen", "qwen", ["qwen3.6-plus", "qwen3.6-max"]),
    modelCfg("c4", "自建 · OpenAI 兼容", "openai-compat", ["gpt-5.2", "o3-mini"]),
  ];
  const { restore, openModal } = await setupModelPickerCase(page, request, fourConfigs);
  try {
    const ai = await openModal();
    await ai.getByTestId("ai-model-select").click();
    const panel = page.getByTestId("ai-model-panel");
    await expect(panel).toBeVisible();

    // ① 四组内容仍在，但弹层受视口约束：整层滚动而非下缘落出视口
    for (const name of ["深度求索", "本地 · Ollama", "通义 · Qwen", "自建 · OpenAI 兼容"]) {
      await expect(panel).toContainText(name);
    }
    const vp = page.viewportSize()!;
    const box = (await panel.boundingBox())!;
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.y + box.height).toBeLessThanOrEqual(vp.height + 1);
    expect(await panel.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
    // 末组模型滚到底即可见可点（旧实现下它落在视口外且拽不回来）
    await panel.evaluate((el) => {
      el.scrollTop = el.scrollHeight;
    });
    await expect(panel.locator('[data-model="c4::gpt-5.2"]')).toBeInViewport();

    // ② 大屏 zoom 层（html{zoom}，2560 宽 → 1.28）：弹层按视觉坐标对齐触发位
    await page.setViewportSize({ width: 2560, height: 1400 });
    const zoom = await page.evaluate(
      () => Number.parseFloat(getComputedStyle(document.documentElement).zoom) || 1,
    );
    expect(zoom).toBeGreaterThan(1); // 前提：大屏缩放层确实生效
    const trigger = (await ai.getByTestId("ai-model-select").boundingBox())!;
    await expect
      .poll(async () => {
        const p = (await panel.boundingBox())!;
        return Math.abs(p.width - trigger.width) + Math.abs(p.x - trigger.x);
      })
      .toBeLessThanOrEqual(3);
    const p2 = (await panel.boundingBox())!;
    // 视觉间距 = 6 × zoom（换算回布局 px 后仍随缩放等比放大，不再双重放大）
    expect(p2.y - (trigger.y + trigger.height)).toBeCloseTo(6 * zoom, 0);
  } finally {
    await restore();
  }
});

// ═══ 编辑器内核（c-prose-editor-tiptap）═══════════════════════════════════════
//   spec 场景「AI 生成可整体撤销」＋「采纳替换走范围事务」的回归护栏。

test("重新生成＝替换写：旧正文清空、一次撤销回空稿，落库同步（c-prose-regen-replace）", async ({ page, request }) => {
  test.setTimeout(120_000);
  const { restore, token } = await setupSession(page);
  try {
    await ensurePromptAccess(request, token);
    const pid = await createNovel(page, `撤销流式${Date.now() % 100000}`);
    await setupFirstChapter(page);
    const CHUNK = "雨点砸在铁皮棚上，他没有抬头。";
    await page.route("**/api/novels/*/chapters/*/write", (route) =>
      route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body:
          `data: ${JSON.stringify({ type: "chunk", text: CHUNK })}\n\n` +
          `data: ${JSON.stringify({ type: "done", full_text: CHUNK })}\n\n`,
      }),
    );
    await page.getByRole("tab", { name: /^正文/ }).click();
    // 先手写一段（被替换的旧正文）
    await page.getByTestId("prose-edit").click();
    const editor = page.locator(".editor");
    await editor.click();
    await page.keyboard.type("原有的一段话。");
    await page.waitForTimeout(700); // 等正文入 store（门禁判定读实时字数）
    // 有正文章再生成：先过「重新生成正文」确认（c-prose-regen-replace）
    await page.getByTestId("ai-write-btn").click();
    const regen = page.getByTestId("regen-confirm");
    await expect(regen).toBeVisible({ timeout: 10000 });
    await regen.click();
    const ai = page.getByRole("dialog", { name: "AI 生成正文" });
    await expect(ai.getByTestId("ai-prompt")).toBeEnabled({ timeout: 10000 });
    await ai.getByTestId("ai-confirm").click();
    await expect(editor).toContainText(CHUNK, { timeout: 10000 });
    // 替换语义：旧正文清空，终稿＝本次生成物（不再追加）
    await expect(editor).not.toContainText("原有的一段话。");
    // 一次撤销 → 回空稿（旧正文找回路径＝版本历史）
    await editor.click();
    await page.keyboard.press("ControlOrMeta+z");
    await expect(editor).not.toContainText(CHUNK, { timeout: 5000 });
    await expect(editor).not.toContainText("原有的一段话。");
    // 落库同步确认
    const H = { Authorization: `Bearer ${token}` };
    await expect
      .poll(
        async () =>
          (await (await request.get(`${ORIGIN}/api/novels/${pid}/chapters/vol-1-ch-1`, { headers: H })).json())?.prose ?? "",
        { timeout: 12000 },
      )
      .not.toContain(CHUNK);
  } finally {
    await restore();
  }
});

test("替换写中断与找回：停止留半截，旧正文经版本历史恢复（c-prose-regen-replace）", async ({
  page,
  request,
}) => {
  test.setTimeout(120_000);
  const { restore, token } = await setupSession(page);
  try {
    await ensurePromptAccess(request, token);
    const pid = await createNovel(page, `中断找回${Date.now() % 100000}`);
    await setupFirstChapter(page);
    const editor = page.locator(".editor");
    const H = { Authorization: `Bearer ${token}` };

    // 旧正文：手写一段并等真落盘（版本快照的前提）
    await page.getByRole("tab", { name: /^正文/ }).click();
    await page.getByTestId("prose-edit").click();
    await editor.click();
    await page.keyboard.type("旧正文独占标记找回甲，这一段是被清空前的旧稿。");
    await expect
      .poll(
        async () =>
          (await (await request.get(`${ORIGIN}/api/novels/${pid}/chapters/vol-1-ch-1`, { headers: H })).json())?.prose ?? "",
        { timeout: 12000 },
      )
      .toContain("找回甲");
    await page.waitForTimeout(300); // 版本快照随保存落库

    // 生成流：两个 chunk 后流被切断（无 done）→ 前端流式标记停留 → 走「停止」按钮
    await page.route("**/api/novels/*/chapters/*/write", (route) =>
      route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body:
          `data: ${JSON.stringify({ type: "chunk", text: "新稿第一段。" })}\n\n` +
          `data: ${JSON.stringify({ type: "chunk", text: "新稿第二段半截。" })}\n\n`,
      }),
    );
    await page.getByRole("tab", { name: /^正文/ }).click();
    await page.getByTestId("ai-write-btn").click();
    const regen = page.getByTestId("regen-confirm");
    await expect(regen).toBeVisible({ timeout: 10000 });
    await regen.click(); // 继续生成（清空重写确认）
    const ai = page.getByRole("dialog", { name: "AI 生成正文" });
    await expect(ai.getByTestId("ai-prompt")).toBeEnabled({ timeout: 10000 });
    await ai.getByTestId("ai-confirm").click();

    // 半截已写入、旧正文已清空、流式标记停留（无 done）
    await expect(editor).toContainText("新稿第二段半截。", { timeout: 10000 });
    await expect(editor).not.toContainText("找回甲");
    await expect(page.getByTestId("ai-streaming-badge")).toBeVisible();

    // 「停止」：半截即为该章正文并走自动保存
    await page.getByTestId("ai-streaming-badge").getByRole("button", { name: "停止" }).click();
    await expect(page.getByTestId("ai-streaming-badge")).toHaveCount(0, { timeout: 10000 });
    await expect
      .poll(
        async () =>
          (await (await request.get(`${ORIGIN}/api/novels/${pid}/chapters/vol-1-ch-1`, { headers: H })).json())?.prose ?? "",
        { timeout: 12000 },
      )
      .toContain("新稿第二段半截");

    // 找回：版本历史恢复旧正文
    await page.getByRole("button", { name: "版本历史" }).click();
    const dlg = page.getByRole("dialog");
    await expect(dlg.locator(".ver-row").nth(1)).toBeVisible({ timeout: 10000 });
    await dlg.locator(".ver-row").nth(1).getByRole("button", { name: "恢复" }).click();
    await expect(page.getByText("已恢复至该版本")).toBeVisible({ timeout: 10000 });
    await expect(editor).toContainText("找回甲", { timeout: 10000 });
    await expect(editor).not.toContainText("新稿第二段半截");
  } finally {
    await restore();
  }
});

test("去AI味采纳＝范围事务替换，一次撤销还原原文", async ({ page, request }) => {
  test.setTimeout(120_000);
  // 去AI味=ai-polish（MAX，2026-10-05 拍板）——会话种 max
  const { restore, token } = await setupSession(page, "max");
  try {
    await ensurePromptAccess(request, token);
    await createNovel(page, `撤销采纳${Date.now() % 100000}`);
    await setupFirstChapter(page);
    await page.route("**/api/novels/*/chapters/*/write/polish", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ polished_text: "丙段改写。" }),
      }),
    );
    await page.getByRole("tab", { name: /^正文/ }).click();
    await page.getByTestId("prose-edit").click();
    const editor = page.locator(".editor");
    await editor.click();
    await page.keyboard.type("甲段。乙段。丙段。");
    await page.waitForTimeout(700); // 拉开与采纳事务的历史分组窗口（newGroupDelay 500ms）
    // 选中「丙段。」= 末尾 3 字
    await page.keyboard.down("Shift");
    for (let i = 0; i < 3; i++) await page.keyboard.press("ArrowLeft");
    await page.keyboard.up("Shift");
    // 选区上抛到右栏有一帧延迟（React 状态更新），等按钮解禁
    // 右栏「去AI味」→ 对照弹窗 → 接受
    const rail = page.locator(".col-ai");
    await rail.getByRole("button", { name: /去AI味/ }).click();
    const dlg = page.getByRole("dialog");
    await expect(dlg.getByRole("button", { name: "接受" })).toBeEnabled({ timeout: 10000 });
    await dlg.getByRole("button", { name: "接受" }).click();
    await expect(editor).toContainText("甲段。乙段。丙段改写。", { timeout: 5000 });
    // 撤销 → 原文回来
    await editor.click();
    await page.keyboard.press("ControlOrMeta+z");
    await expect(editor).toContainText("甲段。乙段。丙段。", { timeout: 5000 });
  } finally {
    await restore();
  }
});

test("编辑工具箱：开章不入历史（⌘Z 不清空正文）＋撤销/重做按钮生效", async ({
  page,
  request,
}) => {
  test.setTimeout(120_000);
  const { restore, token } = await setupSession(page);
  try {
    await ensurePromptAccess(request, token);
    const pid = await createNovel(page, `撤销钮${Date.now() % 100000}`);
    await setupFirstChapter(page);
    // 铺一段既有正文（模拟已写好的章）——载入 SHALL NOT 进撤销史，
    // 故开章后按 ⌘Z/点撤销不得改动正文（旧 setContent 入史会把内容写空并自动保存）
    const ORIG = "原有的正文，载入不应进撤销史。";
    const put = await request.put(`${ORIGIN}/api/novels/${pid}/chapters/vol-1-ch-1/prose`, {
      data: { prose: ORIG },
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(put.ok()).toBeTruthy();
    await page.reload();
    await page.getByRole("tab", { name: /^正文/ }).click();
    await page.getByTestId("prose-edit").click();
    const editor = page.locator(".editor");
    await expect(editor).toContainText("原有的正文", { timeout: 10000 });
    // 载入后无历史步 → 撤销/重做皆置灰
    await expect(page.getByTestId("prose-undo")).toBeDisabled();
    await expect(page.getByTestId("prose-redo")).toBeDisabled();
    // 快捷键 ⌘Z 也不得改动正文（同一保护）
    await editor.click();
    await page.keyboard.press("ControlOrMeta+z");
    await page.waitForTimeout(600);
    await expect(editor).toContainText("原有的正文");
    // 输入一段 → 撤销可用；撤销 → 回退到输入前（原有正文仍在）；重做 → 恢复
    await page.keyboard.type("工具栏撤销验证的一段话。");
    await page.waitForTimeout(700); // 拉开历史分组窗口
    await expect(page.getByTestId("prose-undo")).toBeEnabled();
    await page.getByTestId("prose-undo").click();
    await expect(editor).not.toContainText("工具栏撤销验证的一段话。", { timeout: 5000 });
    await expect(editor).toContainText("原有的正文");
    await expect(page.getByTestId("prose-redo")).toBeEnabled();
    await page.getByTestId("prose-redo").click();
    await expect(editor).toContainText("工具栏撤销验证的一段话。", { timeout: 5000 });
  } finally {
    await restore();
  }
});


