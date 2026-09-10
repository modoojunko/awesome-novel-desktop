import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page } from "@playwright/test";

// =========================================================================
// 免费主流程 E2E（FE-34 / TE-17，change 004）—— P0 断点 1 第 8 条纵切
//   免费 = 完整手动写作（限 1 部作品）；PRO = 同一界面 + AI 解锁。
//   覆盖：① 建书直达写作工作台可写 ② 树头「+添加卷」→ 加章即达编辑器
//   ③ 树 CRUD + hover 铅笔重命名/删除 + 空章三态点 ⑤ 自动保存 + 实时字数
//   ⑥ 归档只读 + 树「已归档」同步 + 免费归档不 500 ⑦ modnav 三态（设定/写作/预览）
//   ⑧ 全程无阶段催促 UI、无 AI 字段、免费零 phase-status 请求
// =========================================================================
// 与 creation-flow.spec.ts 共享鉴权手法：S端 真实注册登录 → 写 docker 容器的
// config.json（tier="none"）→ localStorage 注入 auth_token。docker 4 服务需已启动。

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

/** S端 注册并登录，返回 JWT（免费用户，套餐 none）。 */
async function sRegisterAndLogin() {
  const name = `e2e_free_${Date.now()}_${randomUUID().slice(0, 8)}`;
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

/** 免费会话：tier="none" 写入 docker config.json，返回恢复函数。 */
function writeFreeSession(t: string, u: string) {
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = t;
  cfg.username = u;
  cfg.tier = "none"; // 免费：限 1 部作品，无 AI
  // docker config.json 可能残留已过去的会员到期日（auth middleware 见 expires_at
  // 过期即 401「登录已过期」），注入会话必须清掉，否则全部用例秒挂
  delete cfg.expires_at;
  cfg.last_login_at = new Date().toISOString();
  // 关键：随机 pc_hash 使 S端 check-auth 无该设备 grant（返回 code 1），useAuthHeal 不覆盖
  // config.json，注入 token 保持有效。保留真实 pc_hash 会命中 modoojunko 已授权设备 → 401。
  cfg.pc_hash = randomUUID().replace(/-/g, "");
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2));
  return () => fs.writeFileSync(CONFIG_PATH, original);
}

async function setupFreeSession(page: Page): Promise<{ restore: () => void }> {
  const { token, username } = await sRegisterAndLogin();
  const restore = writeFreeSession(token, username);
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  // 页面级桩 check-auth：注入的 pc_hash 在 S端 无设备授权（code 1），后端会据此清空
  // config.json 的注入 token → 业务 401（已知环境阻塞）；桩掉往返即可保住注入会话。
  await page.route("**/api/auth/check-auth", (r) =>
    r.fulfill({ json: { code: 0, data: {} } }),
  );
  return { restore };
}

/** 通过真实 UI 创建小说（免费限 1 部，测试内仅建一本）。 */
async function createNovel(page: Page, name: string): Promise<string> {
  await page.goto(`${ORIGIN}/#/novels`);
  await page.getByRole("button", { name: "新建作品" }).first().click();
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

/** 加卷 + 初始 1 章 → 点章 → 切「正文」→ 编辑器就绪（PR3：添加卷弹窗 + 点章强制落章纲）。
 *  卷名「第一卷」为默认序号形态（树上只显示序号），章标题=程序默认「第一章」。 */
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

// -------------------------------------------------------------------------
// ①⑦⑧ 免费建书直达正文工作台：无阶段催促、无 AI 字段、3 label 导航
// -------------------------------------------------------------------------

test("免费建书直达写作工作台：零 phase-status，无阶段催促，modnav 三态", async ({
  page,
}) => {
  const { restore } = await setupFreeSession(page);
  try {
    // 记录整个流程中是否出现 phase-status 请求（⑧：免费直呼 AI 端点 403 / 零阶段请求）
    const phaseReqs: string[] = [];
    page.on("request", (r) => {
      if (r.url().includes("/workflow/phase-status")) phaseReqs.push(r.url());
    });

    await createNovel(page, `免费${Date.now() % 100000}`);

    // ① 落点即写作工作台（而非设定页）：空面板 + 左树空态
    await expect(page.getByText("开始创作")).toBeVisible({ timeout: 10000 });
    await expect(
      page.getByText("还没有卷与章节。点击左上「＋」添加第一卷。"),
    ).toBeVisible();
    // 免费标识（novelbar free-hint）
    await expect(page.getByText(/免费模式 · 写作功能完整/)).toBeVisible();
    // ⑦ modnav 三态（PR3 设计稿）：设定 / 写作 / 预览
    await expect(page.getByRole("button", { name: /^设定/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /^写作/ })).toBeVisible();
    await expect(page.getByRole("button", { name: "预览", exact: true })).toBeVisible();
    // ⑧ 空项目无章 → 无章页签
    await expect(page.getByRole("tab", { name: /^正文/ })).toHaveCount(0);
    // ⑧ 无阶段催促 UI（GateBanner/软门控文案）
    await expect(page.getByText(/尚未完成设定/)).toHaveCount(0);
    await expect(page.getByText("设定尚未全部完成")).toHaveCount(0);
    // ⑧ 全程零 phase-status 请求
    expect(phaseReqs.length).toBe(0);

    // ⑦ 免费可进设定视图 → 经 modnav「写作」返回
    await page.getByRole("button", { name: /^设定/ }).click();
    // 设定视图挂载（三栏 col-tree 左栏导航短名「世界」可见即证明）
    await expect(
      page.locator(".settings-v .col-tree").getByText("世界", { exact: true }),
    ).toBeVisible({ timeout: 5000 });
    await page.getByRole("button", { name: /^写作/ }).click();
    await expect(page.getByText("开始创作")).toBeVisible();
    // 全程仍零 phase-status（设定确认 refetch 免费态为 no-op）
    expect(phaseReqs.length).toBe(0);
  } finally {
    restore();
  }
});

// -------------------------------------------------------------------------
// ①②⑤ 直接写第一章即达编辑器：实时字数 + 自动保存 + 空章「未写」弱化
// -------------------------------------------------------------------------

test("加卷加章：即达编辑器，实时字数 + 自动保存，空章三态点", async ({
  page,
}) => {
  const { restore } = await setupFreeSession(page);
  try {
    await createNovel(page, `直写${Date.now() % 100000}`);
    await writeFirstChapter(page);

    // ② 树头「+添加卷」常驻；新章在树上可见（三态点：未填=空心）
    await expect(page.getByTitle("添加卷")).toBeVisible();
    const tree = page.locator(".col-tree");
    await expect(tree.getByText("第一卷")).toBeVisible();
    await expect(tree.getByText("第一章")).toBeVisible();
    await expect(tree.locator(".ch .dot-empty").first()).toBeVisible();

    // 点卷节点 → 卷纲面板（PR4：常编辑态全字段，无独立右栏）
    await tree.locator(".vol-head", { hasText: "第一卷" }).click();
    await expect(
      page.getByRole("button", { name: "保存卷纲" }),
    ).toBeVisible({ timeout: 10000 });

    // 点回第一章 → 强制落「章纲」页签 → 切「正文」→ 编辑器恢复 → ⑤ 实时字数 + 自动保存
    await tree.locator(".ch", { hasText: "第一章" }).click();
    await expect(page.getByRole("tab", { name: /^章纲/ })).toBeVisible({ timeout: 10000 });
    await page.getByRole("tab", { name: /^正文/ }).click();
    const editor = page.locator(".editor");
    await expect(editor).toBeVisible({ timeout: 5000 });
    await editor.fill("你好 世界");
    await expect(page.locator(".editor-status").getByText("4 字")).toBeVisible({
      timeout: 5000,
    });
    // 自动保存（防抖）→ 已自动保存
    await expect(page.getByText("已自动保存").first()).toBeVisible({ timeout: 8000 });
  } finally {
    restore();
  }
});

// -------------------------------------------------------------------------
// ③ 树 CRUD：hover 铅笔行内重命名 + hover 删除（N2 / ADJUSTMENTS #6）
// -------------------------------------------------------------------------

test("树 CRUD：hover 铅笔重命名 + 删除（N2）", async ({ page }) => {
  const { restore } = await setupFreeSession(page);
  try {
    await createNovel(page, `树${Date.now() % 100000}`);
    await writeFirstChapter(page);
    const tree = page.locator(".col-tree");

    // hover 章 → 铅笔 → 行内重命名（预填空：默认序号形态 = 没起过名）→ Enter
    const chRow = tree.locator(".ch", { hasText: "第一章" });
    await chRow.hover();
    await chRow.getByTitle("重命名章节").click();
    const renameInput = tree.locator(".ch input");
    await renameInput.fill("改名第一章");
    await renameInput.press("Enter");
    await expect(tree.getByText("第一章 · 改名第一章")).toBeVisible({
      timeout: 5000,
    });

    // hover 章节点 → 删除 → 分级确认弹窗（PR5：本章未写正文/章纲 → 零盘点 chips）
    const delRow = tree.locator(".ch", { hasText: "改名第一章" });
    await delRow.hover();
    await delRow.getByTitle("删除章节").click();
    const delModal = page.getByRole("dialog");
    await expect(delModal.getByRole("heading", { name: "删除确认" })).toBeVisible();
    await expect(delModal.getByText(/确定删除章节/)).toBeVisible();
    await expect(delModal.locator(".inv-chip")).toHaveCount(0);
    await delModal.getByTestId("del-confirm").click();
    await expect(page.getByText("开始创作")).toBeVisible({ timeout: 5000 });
  } finally {
    restore();
  }
});

// -------------------------------------------------------------------------
// ⑥ 免费归档不 500 + 树「已归档」即时同步（N9）
// -------------------------------------------------------------------------

test("免费归档：不 500，正文只读，树已归档即时同步", async ({ page }) => {
  const { restore } = await setupFreeSession(page);
  try {
    await createNovel(page, `归档${Date.now() % 100000}`);
    const editor = await writeFirstChapter(page);

    await editor.fill(
      "归档的正文内容，这是一个完整的故事段落，用来验证免费归档流程不会返回 500 错误。" +
        "这个段落需要足够长，因为后端归档接口要求至少一百个字符的内容才会接受归档请求。" +
        "所以这里再补充一些叙述，确保总量超过一百字符，从而能够正常进入归档流程验证。",
    );
    await expect(page.getByText("已自动保存").first()).toBeVisible({ timeout: 8000 });

    // 触发归档（PR 5：React 弹窗确认；免费档无 AI 摘要弹窗）
    await page.getByRole("button", { name: "归档本章" }).click();
    await page.getByTestId("arch-confirm").click();

    // 归档成功 → 只读横幅（免费归档不 500）+ 编辑器不可编辑
    await expect(page.getByText(/本章已归档 · 只读/).first()).toBeVisible({
      timeout: 10000,
    });
    // not.toBeEditable() 对 div[contenteditable="false"] 会直接抛「无法判定」——改断言属性
    await expect(page.locator(".editor")).toHaveAttribute("contenteditable", "false");
    // 树「已归档」即时同步（useChapterData dispatch → useWorkbench 刷新）
    await expect(page.locator(".col-tree .arch-tag").first()).toBeVisible({
      timeout: 5000,
    });
  } finally {
    restore();
  }
});
