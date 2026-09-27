import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page, type APIRequestContext } from "@playwright/test";
import { addFirstChapterViaTree, cleanupSessionNovels, stableClick } from "./helpers";

// =========================================================================
// 两段式提示词 → 正文生成 全链路 E2E（ai-prompt-crafting，打桩 AI）：
//   ① AiModal：粗组稿「未润色」→「AI 润色」（stub polish 端点）→ 换稿换标 →
//      作家补一句 →「生成正文」（stub /write SSE）→ 正文落 editor
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

async function setupSession(page: Page): Promise<{ restore: () => void; token: string }> {
  const { token, username } = await sRegisterAndLogin();
  const restore = await writeOAuthSession(token, username);
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

const POLISHED_PROMPT = [
  "# 整章任务",
  "",
  "城门对峙一场戏：目标是带信入城，守卫盘查是阻碍，通缉令画像是钩子。",
  "章末落点：他收起通缉令，转身没入夜色。",
].join("\n");

test("两段式：AiModal 粗组→AI 润色→编辑→生成 + 完工检查横幅", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    await ensurePromptAccess(request, token);
    await createNovel(page, `管线${Date.now() % 100000}`);
    await setupFirstChapter(page);

    // ── 打桩 AI 端点（不依赖真实模型） ─────────────────────────────────
    await page.route("**/api/novels/*/chapters/*/write/prompt/polish", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ prompt: POLISHED_PROMPT, polished: true }),
      }),
    );
    // /write SSE（glob 以 /write 结尾：不会误吞 /write/continue 等子路径）
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
    await page.route("**/api/novels/*/chapters/*/write", (route) =>
      route.fulfill({
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
      }),
    );

    // ── 阶段一：AiModal 打开 → 粗组稿「未润色」 ────────────────────────
    await page.getByRole("tab", { name: /^正文/ }).click();
    await page.getByTestId("ai-write-btn").click(); // 2026-09-20 AI 入口唯一化右栏
    const ai = page.getByRole("dialog", { name: "AI 生成正文" });
    await expect(ai.getByTestId("ai-prompt")).toBeEnabled({ timeout: 10000 });
    await expect(ai.getByTestId("ai-raw-tag")).toHaveText("未润色");

    // ── 阶段二：AI 润色 → 换稿 + 换标 ──────────────────────────────────
    await ai.getByTestId("ai-polish").click();
    await expect(ai.getByTestId("ai-prompt")).toHaveValue(POLISHED_PROMPT, {
      timeout: 10000,
    });
    await expect(ai.getByTestId("ai-polished-tag")).toHaveText("已润色");
    await expect(ai.getByTestId("ai-polish")).toHaveCount(0);

    // 作家过目补一句（编辑不丢润色稿）
    await ai.getByTestId("ai-prompt").fill(`${POLISHED_PROMPT}\n补充：风声里夹着马蹄。`);

    // ── 阶段三：生成正文 → SSE 落 editor + 完工检查横幅 ─────────────────
    await ai.getByTestId("ai-confirm").click();
    const editor = page.locator(".editor");
    await expect(editor).toBeVisible({ timeout: 5000 });
    await expect(editor).toContainText("雨点砸在铁皮棚上", { timeout: 10000 });

    const banner = page.getByTestId("qc-banner");
    await expect(banner).toBeVisible({ timeout: 10000 });
    // 字数不足提示（word_check：below_limit）
    await expect(page.getByTestId("qc-word")).toContainText("字数未达标");
    await expect(page.getByTestId("qc-word")).toContainText("2500");
    // 叙事自查清单（self_check：规则 + 命中数）
    await expect(page.getByTestId("qc-self")).toContainText("因果自然呈现");
    await expect(page.getByTestId("qc-self")).toContainText("1 处");

    // 提示性质：可关闭
    await page.getByTestId("qc-close").click();
    await expect(banner).toHaveCount(0);
  } finally {
    await restore();
  }
});

// ═══ 编辑器内核（c-prose-editor-tiptap）═══════════════════════════════════════
//   spec 场景「AI 生成可整体撤销」＋「采纳替换走范围事务」的回归护栏。

test("流式写入可整体撤销：一次撤销回到生成前，落库同步", async ({ page, request }) => {
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
    // 先手写一段（撤销的「生成前」基线）
    await page.getByTestId("prose-edit").click();
    const editor = page.locator(".editor");
    await editor.click();
    await page.keyboard.type("原有的一段话。");
    await page.waitForTimeout(700); // 拉开与生成的历史分组窗口（newGroupDelay 500ms）
    await page.getByTestId("ai-write-btn").click();
    const ai = page.getByRole("dialog", { name: "AI 生成正文" });
    await expect(ai.getByTestId("ai-prompt")).toBeEnabled({ timeout: 10000 });
    await ai.getByTestId("ai-confirm").click();
    await expect(editor).toContainText(CHUNK, { timeout: 10000 });
    await expect(editor).toContainText("原有的一段话。");
    // 一次撤销 → 回到生成前（CHUNK 消失、原段保留）
    await editor.click();
    await page.keyboard.press("ControlOrMeta+z");
    await expect(editor).not.toContainText(CHUNK, { timeout: 5000 });
    await expect(editor).toContainText("原有的一段话。");
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

test("润色采纳＝范围事务替换，一次撤销还原原文", async ({ page, request }) => {
  test.setTimeout(120_000);
  const { restore, token } = await setupSession(page);
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
    // 右栏「段落润色」→ 对照弹窗 → 接受
    const rail = page.locator(".col-ai");
    await rail.getByRole("button", { name: /段落润色/ }).click();
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


