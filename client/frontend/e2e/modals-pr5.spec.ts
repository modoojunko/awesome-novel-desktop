import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page, type APIRequestContext } from "@playwright/test";

// =========================================================================
// PR 5 弹窗群 E2E（book.html 3/3：删除分级 / 只读章 AI 解锁链 / 版本历史 / 本书偏好）
//   ① 删除分级确认：有正文章盘点 chips（正文 N 字）、删卷带章数字数文案、
//      取消保持 / 确认删除（spec-report §6-1）
//   ② 只读章 AI 解锁链：归档 → 工具栏 AI 生成正文 → 解除只读确认 → AiModal
//      提示词预览 → 取消不生成但已解锁（真 bug #1）+ AI 确认后自动切正文页签（真 bug #2）
//   ③ 版本历史弹窗：两轮自动保存产生快照 → ver-row 列表 + 当前版本 → 恢复回退正文
//   ④ 本书偏好弹窗：面板「本书偏好」→ per-book 字号保存持久 + 免费态升级 PRO 链升级弹窗
// =========================================================================
// 鉴权手法与 workbench-features.spec.ts 一致：S端 真实注册登录 → 写 docker
// 容器 config.json（trial=PRO / none=免费）→ localStorage 注入 auth_token。
// ② 需要 require_ai_access 门控放行 → 先 POST /api/v1/api-configs 假配置。
// 凭据说明：E2E 临时账号 / 假 ApiConfig 仅面向本地 docker 栈，非可用凭据
// （与 workbench-features.spec.ts 同一套），拼串构造以示非密钥。

const S_API = "http://127.0.0.1:19000/api/web";
const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
// E2E 临时账号口令（本地 docker S端 专用，非真实凭据）
const E2E_PASSWORD = ["Test", "Pass", "789", "!"].join("");
// 假 ApiConfig 的 key（base_url 指向不可达端口，仅过 require_ai_access 门控）
const E2E_FAKE_KEY = ["sk-e2e", "not-real"].join("-");
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
  const name = `e2e_md_${Date.now()}_${randomUUID().slice(0, 8)}`;
  const reg = await fetch(`${S_API}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: name,
      password: E2E_PASSWORD,
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
    body: JSON.stringify({ username: name, password: E2E_PASSWORD }),
  });
  const loginBody = await login.json();
  if (loginBody.code !== 0) {
    throw new Error(`S端 login 失败: ${JSON.stringify(loginBody)}`);
  }
  return { token: loginBody.data.token as string, username: name };
}

/** 把 S端 会话写入 config.json，返回恢复函数。tier：trial（PRO）/ none（免费）。
 * 竞态守卫：上一测试 teardown 残留页面的 check-auth（真实 pc_hash 命中 grant）
 * 会在服务端异步回写 config.json 冲掉注入 token → 401；写入后观察，被冲掉
 * 即重写，连续两轮稳定才放行。
 */
async function writeOAuthSession(t: string, u: string, tier = "trial") {
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = t;
  cfg.username = u;
  cfg.tier = tier;
  // 过期的 expires_at 会让 auth middleware 401（runbook 坑 1），注入会话必须清掉
  delete cfg.expires_at;
  cfg.last_login_at = new Date().toISOString();
  // 随机 pc_hash 绕开真实设备 grant，避免 useAuthHeal 覆写注入 token
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

async function setupSession(page: Page, tier = "trial") {
  const { token, username } = await sRegisterAndLogin();
  const restore = await writeOAuthSession(token, username, tier);
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  // 页面级桩 check-auth：e2e 注入的 pc_hash 在 S端 无设备授权（code 1），后端会
  // 据此清空 config.json 的注入 token → 业务请求 401（已知环境阻塞）。桩掉这次
  // 往返即可保住注入会话；会员判定仍走后端 check_permission()（读 config.json tier）。
  await page.route("**/api/auth/check-auth", (r) =>
    r.fulfill({ json: { code: 0, data: {} } }),
  );
  return { restore, token };
}

/** 注入一条 active ApiConfig，使 require_ai_access 门控放行（不测真实连接）。 */
async function ensurePromptAccess(request: APIRequestContext, token: string) {
  const r = await request.post(`${ORIGIN}/api/v1/api-configs`, {
    data: {
      name: `e2e-modal-${Date.now()}`,
      vendor_id: "openai-compat",
      base_url: "http://127.0.0.1:1",
      api_key: E2E_FAKE_KEY,
    },
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(r.ok()).toBeTruthy();
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

/** 加卷 + 初始 1 章 → 点章 → 切「正文」→ 编辑器就绪（PR3 口径）。 */
async function writeFirstChapter(page: Page) {
  await page.getByTitle("添加卷").click();
  await page.getByLabel("卷名", { exact: true }).fill("第一卷");
  await page.getByLabel(/初始章数/).fill("1");
  await page.getByRole("button", { name: "创建卷" }).click();
  const chRow = page.locator(".col-tree .ch", { hasText: "第一章" });
  await expect(chRow).toBeVisible({ timeout: 10000 });
  await chRow.click();
  await expect(page.getByRole("tab", { name: /^章纲/ })).toBeVisible({
    timeout: 10000,
  });
  await page.getByRole("tab", { name: /^正文/ }).click();
  const editor = page.locator(".editor");
  await expect(editor).toBeVisible({ timeout: 10000 });
  return editor;
}

/** 等一次正文自动保存成功落库（PUT /chapters/vol-1-ch-1），注册须先于触发动作。 */
async function waitForProseSave(page: Page) {
  const r = await page.waitForResponse(
    (x) =>
      x.request().method() === "PUT" &&
      x.url().includes("/chapters/vol-1-ch-1"),
    { timeout: 15000 },
  );
  // 状态一并校验：正文过短等 4xx 会让后续归档/盘点全部连锁失败，此处快速暴露
  expect(r.ok()).toBeTruthy();
}

// -------------------------------------------------------------------------
// ① 删除分级确认（免费态：无 AI 依赖）
// -------------------------------------------------------------------------

test("删除分级：章盘点 chips / 删卷带章数字数 / 取消与确认", async ({ page }) => {
  const { restore } = await setupSession(page, "none");
  try {
    await createNovel(page, `删分${Date.now() % 100000}`);
    const editor = await writeFirstChapter(page);

    // 写入正文 → 自动保存（盘点依赖落库后的 word_count）
    const save1 = waitForProseSave(page);
    await editor.fill(
      "删除分级用正文。这段内容用来让章节拥有非零字数，" +
        "从而在删除确认弹窗中触发「正文 N 字」的内容盘点 chip。" +
        "补足一些叙述让内容更完整，故事在这里短暂停留。",
    );
    await save1;

    const tree = page.locator(".col-tree");
    const chRow = tree.locator(".ch", { hasText: "第一章" });
    await chRow.hover();
    await chRow.getByTitle("删除章节").click();

    // 章删除确认：标题 + 确定删除文案 + 内容盘点 chip（未配章纲 → 仅「正文 N 字」）
    const dlg = page.getByRole("dialog");
    await expect(dlg.getByRole("heading", { name: "删除确认" })).toBeVisible();
    await expect(dlg.getByText(/确定删除章节/)).toBeVisible();
    await expect(dlg.locator(".inv-chip", { hasText: "正文" })).toBeVisible();
    await expect(dlg.getByText("此操作不可恢复。")).toBeVisible();
    // 取消 → 弹窗关闭、树行保留
    await dlg.getByRole("button", { name: "取消" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(chRow).toBeVisible();

    // 删卷确认：带「及其全部 N 章（N 字）」文案，无盘点 chips
    const volHead = tree.locator(".vol-head").first();
    await volHead.hover();
    await volHead.getByTitle("删除卷").click();
    await expect(
      page.getByRole("dialog").getByText(/及其全部 1 章/),
    ).toBeVisible();
    await expect(page.getByRole("dialog").locator(".inv-chip")).toHaveCount(0);
    await page.getByRole("dialog").getByRole("button", { name: "取消" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);

    // 确认删除章 → 树清空回空面板（与免费主流程同一断言口径）
    await chRow.hover();
    await chRow.getByTitle("删除章节").click();
    await page.getByTestId("del-confirm").click();
    await expect(page.getByText("开始创作")).toBeVisible({ timeout: 5000 });
  } finally {
    restore();
  }
});

// -------------------------------------------------------------------------
// ② 只读章 AI 解锁链 + AI 确认自动切正文页签（真 bug #1/#2，trial = PRO）
// -------------------------------------------------------------------------

test("解锁链：归档章点 AI → 解除只读 → AiModal 提示词；确认生成自动切正文页签", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    await ensurePromptAccess(request, token);
    const pid = await createNovel(page, `解锁${Date.now() % 100000}`);
    const editor = await writeFirstChapter(page);

    // 本书偏好归档 AI 摘要关（per-book pref 影响 archive 行为，兼降低外部依赖）
    await page.evaluate((p) => {
      localStorage.setItem(`pref.book.${p}.ai_summary`, "off");
    }, pid);

    const save1 = waitForProseSave(page);
    await editor.fill(
      "解锁链验证正文。归档接口要求正文至少一百个字符，" +
        "所以这段内容需要足够长以满足归档校验要求，避免归档请求因太短被拒绝。" +
        "再补充两句叙述：第一句让字数继续增长一些，" +
        "第二句确保总量稳稳超过一百个字符的门槛线。故事在这里继续向前推进。",
    );
    await save1;

    // 归档（React 弹窗确认）→ 只读横幅 + 编辑器只读
    await page.getByRole("button", { name: "归档本章" }).click();
    await page.getByTestId("arch-confirm").click();
    await expect(page.getByText(/本章已归档 · 只读/).first()).toBeVisible({
      timeout: 10000,
    });
    await expect(editor).toHaveAttribute("contenteditable", "false");

    // 归档章点「AI 生成正文」→ 解除只读确认（真 bug #1 门控）
    await page.getByRole("button", { name: "AI 生成正文" }).click();
    // Modal 退场有 200ms 卸载窗口期，链式弹窗可能短暂并存 → 一律按 accessible name 限定
    const unlock = page.getByRole("dialog", { name: "解除只读" });
    await expect(unlock.getByText(/AI 生成将解除只读并继续/)).toBeVisible();

    // 确认解锁 → unarchive 落地后链式打开 AiModal（提示词预览）
    await page.getByTestId("unlock-confirm").click();
    const ai = page.getByRole("dialog", { name: "AI 生成正文" });
    await expect(ai.getByRole("heading", { name: "AI 生成正文" })).toBeVisible({
      timeout: 10000,
    });
    // 提示词加载完成（textarea 解禁 + 两段式说明；本章未配章纲 → 对应提示）
    await expect(ai.getByTestId("ai-prompt")).toBeEnabled({ timeout: 10000 });
    await expect(
      ai.getByText(/两段式：先「AI 润色」|本章尚未配置章纲/),
    ).toBeVisible();

    // 弹窗取消 → 不生成，但解锁已生效（编辑器翻回可编辑、只读横幅撤下）
    await ai.getByRole("button", { name: "取消" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(editor).toHaveAttribute("contenteditable", "true", {
      timeout: 10000,
    });
    await expect(page.getByText(/本章已归档 · 只读/)).toHaveCount(0);

    // 真 bug #2：切到章纲页签（工具栏 AI 按钮随 prose-ctrls 隐藏）→
    // 从右栏 AI 卡触发 → AiModal 确认生成 → 自动切回正文页签并聚焦
    await page.getByRole("tab", { name: /^章纲/ }).click();
    await expect(page.getByText(/章纲：明确「这一章写什么」/)).toBeVisible();
    await page
      .locator(".col-ai")
      .getByRole("button", { name: "生成正文", exact: true })
      .click();
    await expect(
      page.getByRole("dialog", { name: "AI 生成正文" }).getByTestId("ai-prompt"),
    ).toBeEnabled({ timeout: 10000 });
    await page.getByTestId("ai-confirm").click();
    // 页签切回正文（编辑器重新可见；生成请求打向假端点失败属预期，不作断言）
    await expect(editor).toBeVisible({ timeout: 5000 });
  } finally {
    restore();
  }
});

// -------------------------------------------------------------------------
// ③ 版本历史弹窗：自动保存快照 → 列表 + 当前版本 → 恢复回退
// -------------------------------------------------------------------------

test("版本历史弹窗：快照列表 + 当前版本徽标 + 恢复回退正文", async ({ page }) => {
  const { restore } = await setupSession(page, "none");
  try {
    await createNovel(page, `版本${Date.now() % 100000}`);
    const editor = await writeFirstChapter(page);

    // 两轮内容不同的自动保存 → 两条快照（prose 实质变化才落 version）
    const textA =
      "第一版正文，包含独占标记版本甲。" +
      "这一版内容与第二版不同，恢复后应回到这段文字。" +
      "补足叙述长度让两次保存的字数也有明显差异，便于行内字数展示。";
    const textB =
      "第二版正文，包含独占标记版本乙。" +
      "这一版是在第一版之后保存的当前版本，恢复第一版后此标记应消失。" +
      "同样补足叙述长度，保持两版字数相当、内容完全不同。";
    const save1 = waitForProseSave(page);
    await editor.fill(textA);
    await save1;
    const save2 = waitForProseSave(page);
    await editor.fill(textB);
    await save2;

    // 打开版本历史弹窗（wide）：列表新→旧，首行 = 当前版本
    await page.getByRole("button", { name: "版本历史" }).click();
    const dlg = page.getByRole("dialog");
    await expect(dlg.getByRole("heading", { name: /版本历史/ })).toBeVisible();
    await expect(dlg.locator(".ver-row")).toHaveCount(2, { timeout: 10000 });
    await expect(dlg.locator(".ver-row").first()).toContainText("当前版本");
    await expect(
      dlg.locator(".ver-row").first().locator(".cur"),
    ).toHaveText("当前");
    const older = dlg.locator(".ver-row").nth(1);
    await expect(older).toContainText(/版本 1/);
    await expect(older).toContainText(/恢复/);

    // 恢复旧版 → toast + 弹窗关闭 + 正文回退到第一版
    await older.getByRole("button", { name: "恢复" }).click();
    await expect(page.getByText("已恢复至该版本")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(editor).toContainText("版本甲", { timeout: 10000 });
    await expect(editor).not.toContainText("版本乙");
  } finally {
    restore();
  }
});

// -------------------------------------------------------------------------
// ④ 本书偏好弹窗：per-book 保存持久 + 免费态「升级 PRO」链升级弹窗
// -------------------------------------------------------------------------

test("本书偏好：字号 per-book 持久 + 免费态升级 PRO 链升级弹窗", async ({
  page,
}) => {
  const { restore } = await setupSession(page, "none");
  try {
    const pid = await createNovel(page, `偏好${Date.now() % 100000}`);

    // 工作台 appbar 头像触发钮 → 面板「本书偏好」→ 本书偏好弹窗（四行偏好）
    await page.locator('[data-od-id="acct-trigger"]').click();
    await page.locator('[data-od-id="acct-menu-bookprefs"]').click();
    const dlg = page.getByRole("dialog");
    await expect(
      dlg.getByRole("heading", { name: "设置 · 写作偏好" }),
    ).toBeVisible();
    for (const label of ["默认字号", "默认行距", "归档时 AI 摘要", "账号"]) {
      await expect(dlg.getByText(label, { exact: true })).toBeVisible();
    }

    // 版本行（c-version-account-visibility）：吃应用级缓存；docker 后端无烘焙 → 「开发版 dev」
    await expect(dlg.locator('[data-od-id="pref-version"]')).toHaveText(/^(v\d+\.\d+.*|开发版 dev|版本未知)$/);

    // 免费态：账号行「升级 PRO」→ 关偏好弹窗、链出升级弹窗（S端 门户引导）
    await expect(dlg.locator("#pref-upgrade")).toBeVisible();
    await dlg.locator("#pref-upgrade").click();
    await expect(
      page
        .getByRole("dialog")
        .getByRole("heading", { name: "升级 PRO · 解锁 AI 能力" }),
    ).toBeVisible();
    await page.getByRole("dialog").getByRole("button", { name: "暂不" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);

    // 字号切「大」→ 保存 → per-book 落库（pref.book.{pid}.fs）+ 重开保持
    await page.locator('[data-od-id="acct-trigger"]').click();
    await page.locator('[data-od-id="acct-menu-bookprefs"]').click();
    await dlg.getByRole("button", { name: "大", exact: true }).click();
    await dlg.getByRole("button", { name: "保存" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(
      await page.evaluate(
        (p) => localStorage.getItem(`pref.book.${p}.fs`),
        pid,
      ),
    ).toBe("fs-l");

    await page.locator('[data-od-id="acct-trigger"]').click();
    await page.locator('[data-od-id="acct-menu-bookprefs"]').click();
    await expect(
      page
        .getByRole("dialog")
        .getByRole("button", { name: "大", exact: true }),
    ).toHaveClass(/on/);
  } finally {
    restore();
  }
});
