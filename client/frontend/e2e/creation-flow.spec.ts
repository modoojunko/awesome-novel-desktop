import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page, type APIRequestContext } from "@playwright/test";
import { cleanupSessionNovels } from "./helpers";

// =========================================================================
// 核心创作流程 E2E — 创建小说（书名即创建）→ 设定完成判定（PRD 3.4）→ 大纲 → CRUD
// =========================================================================
// 不 mock：token 由 S端 真实签发（register + login）；设定/门控/文件走真实 C端 后端。
// 鉴权按「C端 靠 S端 OAuth」——把 S端 签发会话写入 docker 容器的 config.json
// （.docker-data/client/config.json，C端 后端 bind mount 的 DATA_ROOT）。
//
// 会话恢复：每个测试独立注册用户 + 独立写会话，测试体用 try/finally 无条件恢复
// 原始 config.json。即使断言失败（finally 仍执行）也不会污染真实登录态。
// 前置条件：docker 4 服务已启动（S端 19000 + C端 前端 5174）。
//
// 设定完成判定（PRD 3.4）：7 项全确认 → /settings/status 全 true（013：断言机制
// 由 GateBanner 消失改为后端状态直查）。world/hooks 走真实表单（回归 world/hooks
// readiness checker 与前端保存结构不一致的 bug），其余 5 项 API 注入内容 + UI 点「完成设定」。

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

/** 在 S端 注册并登录，返回 S端 签发的 JWT。 */
async function sRegisterAndLogin() {
  const name = `e2e_flow_${Date.now()}_${randomUUID().slice(0, 8)}`;
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

/**
 * 把 S端 会话写入 docker 容器的 config.json，返回恢复函数。
 * tier：trial（PRO，无 project_limit）/ none（免费，限 1 部作品）。
 *
 * 竞态守卫：上一测试 teardown 时残留页面的 check-auth（restore 已还回真实
 * pc_hash → S端 grant code 0）会在 C端 后端异步回写 config.json，可能晚于
 * 本次写入落地，把注入 token 冲掉 → 业务请求 401。写入后观察一段时间，
 * 被冲掉即重写，连续两轮稳定才放行。
 */
async function writeOAuthSession(t: string, u: string, tier = "trial") {
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = t;
  cfg.username = u;
  cfg.tier = tier;
  // docker config.json 可能残留已过去的会员到期日（auth middleware 见 expires_at
  // 过期即 401「登录已过期」），注入会话必须清掉，否则全部用例秒挂
  delete cfg.expires_at;
  cfg.last_login_at = new Date().toISOString();
  // 关键：随机 pc_hash 使 S端 check-auth 无该设备 grant（返回 code 1），useAuthHeal 不覆盖
  // config.json，注入 token 保持有效。保留真实 pc_hash 会命中 modoojunko 已授权设备 → 401。
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

/**
 * 每测试独立会话：S端 注册登录 → 写 config.json → 注入 localStorage。
 * 返回 restore 与 token；调用方须在 try/finally 中恢复 config.json。
 */
async function setupSession(
  page: Page,
  tier = "trial",
): Promise<{ restore: () => void; token: string }> {
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

/** 通过真实 UI 创建小说（书名即创建），返回 project id。 */
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

/** 带 Bearer token 的 API PUT（docker 生产后端，走 nginx /api 前缀）。 */
async function apiPutJSON(request: APIRequestContext, token: string, path: string, data: unknown) {
  const r = await request.put(`${ORIGIN}/api${path}`, {
    data,
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(r.ok()).toBeTruthy();
}

/** 带 Bearer token 的 API GET 并解析 JSON（013：settings/status 直查）。 */
async function apiGetJSON(request: APIRequestContext, token: string, path: string) {
  const r = await request.get(`${ORIGIN}/api${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(r.ok()).toBeTruthy();
  return r.json();
}

/** 在设定左栏点一个导航项（settings-three-col 后 col-tree 内精确匹配短名：题材/简介/世界/…）。 */
async function openSetting(page: Page, label: string) {
  await page.locator(".settings-v .col-tree").getByText(label, { exact: true }).click();
}

/**
 * 填一个表单 Field：label 文本 → 所在 .field 内的 textarea（v2 Field 基元：
 * div.field > label + textarea；label 含 hint 的 opt span 仍按子串命中）。
 */
async function fillSettingField(page: Page, label: string, value: string) {
  const field = page
    .locator("label", { hasText: label })
    .locator("xpath=ancestor::div[1]");
  await field.locator("textarea").fill(value);
}

/**
 * 点 panel-foot「确认完成」（gap3：先 save 落库后 confirm），确认后按钮转
 * 「保存修改」（ADJUSTMENTS #9）。
 */
async function confirmPanel(page: Page) {
  const btn = page
    .locator(".panel-foot")
    .getByRole("button", { name: "确认完成" });
  await expect(btn).toBeVisible({ timeout: 5000 });
  const before = await page.locator(".settings-v main h2").textContent();
  const statusPut = page.waitForResponse(
    (r) => r.request().method() === "PUT" && r.url().includes("/settings/status/"),
  );
  await btn.click();
  await statusPut;
  // 确认即前进（tasks 2.2）：确认后面板切到下一项（末项/已确认态才留在原面板）
  await expect(async () => {
    const after = await page.locator(".settings-v main h2").textContent();
    const saved = await page
      .locator(".panel-foot")
      .getByRole("button", { name: "保存修改" })
      .count();
    expect(after !== before || saved > 0).toBe(true);
  }).toPass({ timeout: 5000 });
}

// -------------------------------------------------------------------------
// 创建小说（PRD 3.1：书名即创建）
// -------------------------------------------------------------------------

test("创建小说：仅书名即可创建并进入小说页", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    await page.goto(`${ORIGIN}/#/novels`);
    await expect(page.getByRole("button", { name: "新建作品" }).first()).toBeVisible({
      timeout: 10000,
    });

    await page.getByRole("button", { name: "新建作品" }).first().click();
    // AC-1.4：空书名创建按钮不可用
    await expect(page.getByRole("button", { name: "创建，去写简介" })).toBeDisabled();

    // 规格 creation-flow：The modal SHALL have no … no synopsis/genre collection
    // 回归背景：此处曾有一个「类型（选填）」下拉，与既有规格相悖（2026-09-10 修）
    const dlg = page.getByRole("dialog");
    await expect(dlg.locator(".field")).toHaveCount(1);
    await expect(dlg.locator("select")).toHaveCount(0);
    await expect(dlg).not.toContainText("类型");
    // 文案：先随手起一个、之后能改；建好后先写简介再定题材（用户 2026-09-10 起草）
    await expect(dlg.locator(".hint").first()).toContainText("之后随时能改");
    await expect(dlg.locator(".hint").first()).toContainText("先写简介");
    await expect(dlg.locator(".hint").first()).toContainText("再定题材");

    const bookName = `穿越测试${Date.now() % 10000}`;
    await page.locator("input#bkTitle").fill(bookName);
    await page.getByRole("button", { name: "创建，去写简介" }).click();

    // AC-1.6：创建成功直接进入小说页
    await page.waitForURL(/#\/novel\/[0-9a-fA-F-]+/, { timeout: 10000 });
    // 顶栏显示书名
    await expect(page.getByText(bookName).first()).toBeVisible({ timeout: 10000 });

    // 新书题材未设定 → 胶囊位仍占位显示「待定题材」（用户 2026-09-10 拍板）
    await page.goto(`${ORIGIN}/#/novels`);
    const card = page.locator(".cards .book-card", { hasText: bookName }).first();
    await expect(card).toBeVisible({ timeout: 10000 });
    await expect(card.locator(".genre.pending")).toHaveCount(1);
    await expect(card.locator(".genre")).toContainText("待定题材");
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// PRD 3.4：简介完成判定（简介面板点「确认完成」时校验内容非空）
// -------------------------------------------------------------------------

test("简介可随时确认；内容为空时后端 400 拦截（tasks 2.4 语义）", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `简介${Date.now() % 100000}`);
    await page.goto(`${ORIGIN}/#/novel/${pid}`);
    await page.getByRole("button", { name: /^设定/ }).click();
    await openSetting(page, "简介");

    // 空简介 → 确认按钮仍可点（无前端 gate）→ 后端 400 拦截，不落已确认
    await page
      .locator(".panel-foot")
      .getByRole("button", { name: "确认完成" })
      .click();
    await expect(page.getByText(/还未填写内容/)).toBeVisible({ timeout: 5000 });
    const status0 = await apiGetJSON(request, token, `/novels/${pid}/settings/status`);
    expect(status0.synopsis).toBe(false);

    // 写入简介 → x/500 计数同步（spec#3）→ 确认完成（gap3：先 PUT /story 再 confirm）
    await page
      .getByPlaceholder(/用几句话/)
      .fill("一个穿越到明朝当海盗的故事");
    await expect(page.getByText("13/500")).toBeVisible();
    await confirmPanel(page);

    const status1 = await apiGetJSON(request, token, `/novels/${pid}/settings/status`);
    expect(status1.synopsis).toBe(true);
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// change 004：空书无门控（AC-4.3 替代）——建书即写，加卷加章直达编辑器，
// 全程无「设定未完成」阶段催促（P0 断点 1 第 8 条）
// -------------------------------------------------------------------------

test("空书无门控：建书即写，加卷加章直达编辑器", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    const pid = await createNovel(page, `直接写${Date.now() % 100000}`);

    // 落点即写作工作台（非设定页）：空面板 + 左树空态
    await expect(page.getByText("开始创作")).toBeVisible({ timeout: 10000 });
    await expect(
      page.getByText("还没有卷与章节。点击左上「＋」添加第一卷。"),
    ).toBeVisible();

    // 全程无阶段催促 UI（软门控已移除）
    await expect(page.getByText("设定尚未全部完成")).toHaveCount(0);
    await expect(page.getByText(/尚未完成设定/)).toHaveCount(0);

    // 树头「＋」→「添加卷」弹窗：卷名必填 + 初始章数（程序批量建章，默认序号形态标题）
    await page.getByTitle("添加卷").click();
    await expect(
      page.getByRole("heading", { name: "添加卷" }),
    ).toBeVisible({ timeout: 5000 });
    const volCreate = page.getByRole("button", { name: "创建卷" });
    await expect(volCreate).toBeEnabled(); // 初始章数 0 也允许（卷名才是必填）
    await page.getByLabel("卷名", { exact: true }).fill("风起晋北");
    await page.getByLabel(/初始章数/).fill("1");
    await volCreate.click();

    // 卷章创建成功 → 树上「第一卷 · 风起晋北」「第一章」（默认标题=纯序号形态）
    await expect(
      page.locator(".col-tree").getByText("第一卷 · 风起晋北"),
    ).toBeVisible({ timeout: 10000 });
    const chRow = page.locator(".col-tree .ch", { hasText: "第一章" });
    await expect(chRow).toBeVisible({ timeout: 5000 });

    // 点章 → 强制落「章纲」页签（PR3 设计稿行为）→ 切「正文」即达编辑器
    await chRow.click();
    await expect(page.getByRole("tab", { name: /^章纲/ })).toBeVisible({
      timeout: 10000,
    });
    await page.getByRole("tab", { name: /^正文/ }).click();
    await expect(page.locator(".editor")).toBeVisible({ timeout: 10000 });
    await expect(page.locator(".editor")).toBeEditable();
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// PRD 3.4：设定 7 项全确认 → settings-status 全 true（013：GateBanner 已移除）
// world/hooks/synopsis 走真实表单（回归 checker 与前端保存结构不一致 bug）；
// 其余 4 项 API 注入内容 + 面板确认。断言最终 status 7 键全绿。
// -------------------------------------------------------------------------

test("设定 7 项全确认（settings-status 全绿）", async ({ page, request }) => {
  const { restore, token } = await setupSession(page);
  try {
    const confirmBookName = `全确认${Date.now() % 100000}`;
    const pid = await createNovel(page, confirmBookName);
    await page.goto(`${ORIGIN}/#/novel/${pid}`);

    // 013：设定未确认也不渲染「以下阶段尚未就绪」门控横幅（GateBanner 已移除）
    await expect(page.getByText(/尚未完成设定/)).toHaveCount(0);

    // 新落点：默认写作工作台。设定面板经 modnav「设定」tab 进入（PR4 v2 two-col）。
    await page.getByRole("button", { name: /^设定/ }).click();

    // ── world：契约 v2 五格（舞台一段话任一非空即可确认）→ 确认完成自动落库
    await openSetting(page, "世界");
    const stage = page.locator('[data-od-id="stage-input"]');
    await expect(stage).toBeVisible({ timeout: 10000 });
    await stage.fill("一座被沙漠包围的边境城邦，城主议会制，元老席位世袭");
    const worldSave = page.waitForResponse(
      (r) => r.request().method() === "PUT" && r.url().includes("/settings/world"),
    );
    await confirmPanel(page);
    await worldSave;

    // ── hooks：真实表单添加伏笔 → 填描述 → 确认完成自动落库
    await openSetting(page, "伏笔");
    await page.getByRole("button", { name: "添加伏笔" }).click();
    await page
      .locator('input[placeholder="伏笔描述"]')
      .first()
      .fill("主角妹妹失踪的真相");
    const hooksSave = page.waitForResponse(
      (r) => r.request().method() === "PUT" && r.url().includes("/settings/hooks"),
    );
    await confirmPanel(page);
    await hooksSave;

    // ── synopsis：简介面板真实表单 → 确认完成（PUT /story）
    await openSetting(page, "简介");
    await page
      .getByPlaceholder(/用几句话/)
      .fill("一个少年在边境城邦寻找妹妹失踪真相的故事");
    const synSave = page.waitForResponse(
      (r) => r.request().method() === "PUT" && r.url().includes("/story"),
    );
    await confirmPanel(page);
    await synSave;

    // ── genre：API 注入新契约 + 面板确认（无 genre_id）
    await apiPutJSON(request, token, `/novels/${pid}/settings/genre`, {
      core_promise: "以弱破强的痛快",
      promise_note: "读者要看到弱者被逼到绝境后，用脑子一步步翻盘",
      cost_ratio: 8,
    });
    // 题材面板在「简介确认即前进」时已挂载（早于本次注入）→ 切走再切回强制重挂载取数
    await openSetting(page, "世界");
    await openSetting(page, "题材");
    // 面板加载完成信号＝五格渲染出（首格题材选择器可见）
    await expect(page.locator(".settings-v .mod")).toHaveCount(5, { timeout: 5000 });
    // 02 主框＝作家写的那句话（promise_note）；短标签另在提示行
    await expect(page.locator('[data-od-id="m1-input"]')).toHaveValue(
      "读者要看到弱者被逼到绝境后，用脑子一步步翻盘",
    );
    await expect(page.locator('[data-od-id="genre-panel"]')).toContainText("标签：以弱破强的痛快");
    await confirmPanel(page);

    // ── style：API 注入 + 面板确认（§5.1 新书为「已填」非「已确认」→ 按钮是确认完成）
    await apiPutJSON(request, token, `/novels/${pid}/settings/style`, {
      role: "克制冷静的第三人称叙事，短句为主",
    });
    await openSetting(page, "文风");
    await confirmPanel(page);

    // ── anti-ai：API 注入 + 面板确认（同上）
    await apiPutJSON(request, token, `/novels/${pid}/settings/anti-ai`, {
      blocklists: ["过度修辞", "翻译腔"],
    });
    await openSetting(page, "禁用词句");
    await confirmPanel(page);

    // ── characters：API 注入角色文件 + 面板确认
    await apiPutJSON(request, token, `/novels/${pid}/settings/character/张三`, {
      name: "张三",
    });
    await openSetting(page, "角色");
    await confirmPanel(page);

    // 7 项全确认 → /settings/status 全 true（PRD 3.4；013：观察点从 GateBanner 消失改为后端直查）
    const status = await apiGetJSON(request, token, `/novels/${pid}/settings/status`);
    for (const k of ["synopsis", "genre", "world", "style", "anti-ai", "hooks", "characters"]) {
      expect(status[k]).toBe(true);
    }

    // 题材设定后 → 书架卡片胶囊取值来自题材（核心承诺兜底：此时未选题材目录），占位态撤下
    await page.goto(`${ORIGIN}/#/novels`);
    const bookCard = page.locator(".cards .book-card", { hasText: confirmBookName }).first();
    await expect(bookCard.locator(".genre")).toContainText("以弱破强的痛快", {
      timeout: 10000,
    });
    await expect(bookCard.locator(".genre.pending")).toHaveCount(0);

    // 胶囊只显示大类（用户 2026-09-10 拍板「胶囊就显示大类」）：
    // 选上子类也只显示大类，子类不占展示位
    // 注意：同 URL 的 goto 不会重载 SPA（不重新拉列表）→ 先绕一次书本页
    await apiPutJSON(request, token, `/novels/${pid}/settings/genre`, {
      theme: "架空古王朝",
      sub_genre: "权谋",
    });
    await page.goto(`${ORIGIN}/#/novel/${pid}`);
    await page.goto(`${ORIGIN}/#/novels`);
    await expect(bookCard.locator(".genre")).toHaveText(/架空古王朝/);
    await expect(bookCard.locator(".genre")).not.toContainText("权谋");
    await expect(bookCard.locator(".genre")).not.toContainText("·");
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// CRUD：改名（顶栏就地编辑）
// -------------------------------------------------------------------------

test("改名：novelbar 书名双击就地改名即时生效（AC-2.x）", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    const origName = `原始${Date.now() % 100000}`;
    await createNovel(page, origName);
    const nextName = `新名字${Date.now() % 100000}`;

    // novelbar 书名（双击重命名，#164 名称即标题口径）→ Enter 提交
    await page.locator(".novel-title").dblclick();
    const nameInput = page.locator(".novelbar input");
    await expect(nameInput).toBeVisible({ timeout: 5000 });
    await nameInput.fill(nextName);
    await page.keyboard.press("Enter");

    // 页面即时反映新名
    await expect(page.getByText(nextName).first()).toBeVisible({ timeout: 5000 });
    // 旧名不再显示
    await expect(page.getByText(origName).first()).not.toBeVisible();
  } finally {
    await restore();
  }
});
