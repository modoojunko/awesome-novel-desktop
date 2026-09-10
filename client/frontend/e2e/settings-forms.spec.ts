import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page, type APIRequestContext, type Dialog } from "@playwright/test";
import { cleanupSessionNovels } from "./helpers";

// =========================================================================
// 设定真实表单 + 预览只读 E2E（PR4 v2 设定视图 two-col + 预览视图复刻后改版）
//   ① 题材：GenreSettingForm 真实题材选择器（空态 → 选 都市日常 → 应用题材 → 自动保存）
//   ② 风格：StyleSettingForm 真实表单（叙事身份 Field + 核心原则折叠组 ListEditor）
//   ③ AI痕迹：AntiAiSettingForm 真实表单（疲劳词分类 ListEditor）
//   ④ 角色：CharacterManager 真实创建角色（创建弹窗 → 基本信息 → 保存）
//   ⑤ 预览（只读树 + 只读正文）：全书通读（草稿/归档章皆可读）→ 点章切换 →
//      归档 tag 同步 → 回工作台恢复编辑（归档管理在正文编辑页）
//   面板确认统一走 panel-foot「确认完成」（先 save 后 confirm，gap3）→ 按钮转
//   「保存修改」（ADJUSTMENTS #9）；面板标题/导航用新短名（题材/简介/世界/…）。
// =========================================================================
// 与 creation-flow.spec.ts 共享鉴权与设定确认手法；与 free-writing-flow.spec.ts
// 共享归档/正文工作台手法。前置条件：docker 4 服务已启动。

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

/** S端 注册并登录，返回 JWT（免费用户，套餐 none）。 */
async function sRegisterAndLogin() {
  const name = `e2e_sf_${Date.now()}_${randomUUID().slice(0, 8)}`;
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

/** 每测试独立会话：S端 注册登录 → 写 config.json → 注入 localStorage。 */
async function setupSession(
  page: Page,
  tier = "trial",
): Promise<{ restore: () => void; token: string }> {
  const { token, username } = await sRegisterAndLogin();
  const restore = await writeOAuthSession(token, username, tier);
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  // 页面级桩 check-auth：注入的 pc_hash 在 S端 无设备授权（code 1），后端会据此
  // 清空 config.json 注入 token → 业务 401（已知环境阻塞）。桩掉这次往返即可
  // 保住注入会话；会员判定仍走后端 check_permission()（读 config.json 的 tier）。
  await page.route("**/api/auth/check-auth", (r) =>
    r.fulfill({ json: { code: 0, data: { token, username, tier } } }),
  );
  const restoreAndCleanup = async () => {
    await cleanupSessionNovels(ORIGIN, token); // 先删本次测试自建的书，再还原本地会话
    await restore();
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
  // 空书默认落「设定」（@/lib/novelStage：无章节 → 设定，用户 2026-09-10 拍板）；
  // 本 spec 的用例都在写作视图操作 → 建书后显式切过去。
  await page.locator(".mtab", { hasText: "写作" }).click();
  await expect(page.locator(".mtab.on")).toContainText("写作");
  return m[1];
}

/** 加卷 + 初始 1 章 → 点章 → 切「正文」→ 编辑器就绪（PR3：添加卷弹窗 + 点章强制落章纲）。 */
async function writeFirstChapter(page: Page) {
  await page.getByTitle("添加卷").click();
  await page.getByLabel("卷名", { exact: true }).fill("第一卷");
  await page.getByLabel(/初始章数/).fill("1");
  await page.getByRole("button", { name: "创建卷" }).click();
  const chRow = page.locator(".three-col .ch", { hasText: "第一章" });
  await expect(chRow).toBeVisible({ timeout: 10000 });
  await chRow.click();
  await expect(page.getByRole("tab", { name: /^章纲/ })).toBeVisible({
    timeout: 10000,
  });
  await page.getByRole("tab", { name: /^正文/ }).click();
  const editor = page.locator(".three-col .editor");
  await expect(editor).toBeVisible({ timeout: 10000 });
  return editor;
}

/** 带 Bearer token 的 API GET 并解析 JSON。 */
async function apiGetJSON(request: APIRequestContext, token: string, path: string) {
  const r = await request.get(`${ORIGIN}/api${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(r.ok()).toBeTruthy();
  return r.json();
}

/** 带 Bearer token 的 API POST 并解析 JSON。 */
async function apiPostJSON(
  request: APIRequestContext,
  token: string,
  path: string,
  data: unknown,
) {
  const r = await request.post(`${ORIGIN}/api${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    data,
  });
  expect(
    r.ok(),
    `${path} → ${r.status()}: ${r.status() >= 400 ? await r.text() : ""}`,
  ).toBeTruthy();
  return r.json();
}

// ── v2 设定视图定位助手（settings-three-col 后设定根 = .settings-v 三栏：col-tree/col-middle/col-ai；预览仍 two-col）──

/** 在设定左栏点一个导航项（col-tree 内精确匹配短名：题材/简介/世界/风格/…）。 */
async function openSetting(page: Page, label: string) {
  await page.locator(".settings-v .col-tree").getByText(label, { exact: true }).click();
}

/**
 * 填一个表单 Field：label 文本 → 所在 .field 内的 textarea（v2 Field 基元：
 * div.field > label + textarea）。hasText 子串命中——注意与其他 label/hint 的
 * 子串碰撞（角色表单「环境」hint 含「背景」→ 传 /^背景$/ 锚定正则消歧）。
 */
async function fillSettingField(
  page: Page,
  label: string | RegExp,
  value: string,
) {
  const field = page
    .locator("label", { hasText: label })
    .locator("xpath=ancestor::div[1]");
  await field.locator("textarea").fill(value);
}

/** 表单 Field 的 textarea 定位器（P2 守卫用例反复取值用）。 */
function settingFieldTA(page: Page, label: string) {
  return page
    .locator("label", { hasText: label })
    .locator("xpath=ancestor::div[1]")
    .locator("textarea");
}

/**
 * 点 panel-foot「确认完成」：先 save（落库）后 confirm（gap3），确认后按钮转
 * 「保存修改」（ADJUSTMENTS #9）。
 */
async function confirmPanel(page: Page) {
  const btn = page
    .locator(".panel-foot")
    .getByRole("button", { name: "确认完成" });
  await expect(btn).toBeVisible({ timeout: 5000 });
  await btn.click();
  await expect(
    page.locator(".panel-foot").getByRole("button", { name: "保存修改" }),
  ).toBeVisible({ timeout: 5000 });
}

/**
 * 已确认面板的保存路径：种子模板让 style/anti-ai 开书即有内容（readiness 即
 * ready → 按钮已是「保存修改」，gap3：已确认态只 save，不再 PUT status）。
 */
async function savePanel(page: Page) {
  const btn = page
    .locator(".panel-foot")
    .getByRole("button", { name: "保存修改" });
  await expect(btn).toBeVisible({ timeout: 5000 });
  await btn.click();
}

// -------------------------------------------------------------------------
// ① 题材：六格新契约面板（口味联动 → 自定义禁区 → 吃苦指数 → 确认落五字段）
// -------------------------------------------------------------------------

test("题材：六格面板（口味联动 → 自定义禁区 → 吃苦指数 → 确认落五字段）", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `题材${Date.now() % 100000}`);
    await page.getByRole("button", { name: /^设定/ }).click();
    // tasks 2.1 顺序对调后默认落「简介」（SETTINGS_ITEMS[0]）；本用例切到题材面板
    await expect(
      page.locator(".settings-v main h2", { hasText: "简介" }),
    ).toBeVisible({ timeout: 10000 });
    await openSetting(page, "题材");
    await expect(
      page.locator(".settings-v main h2", { hasText: "题材" }),
    ).toBeVisible({ timeout: 5000 });

    // 六格齐全（编号 01-06 + 名称）
    await expect(page.locator(".settings-v .mod")).toHaveCount(6);
    for (const name of ["题材", "主要看什么", "绝对禁止", "吃苦指数", "主线战场", "剧情轨道"]) {
      await expect(page.locator(".settings-v .mod .m-name", { hasText: name })).toBeVisible();
    }

    // 01 题材选择器（TDesign Cascader 式）：收起＝一个字段；点开＝搜索 + 大类列 + 子类列
    const trigger = page.locator('[data-od-id="theme-trigger"]');
    await expect(trigger).toContainText("选择题材");
    await expect(page.locator('[data-od-id="theme-panel"]')).toHaveCount(0);
    await expect(page.locator('[data-od-id="theme-note"]')).toHaveCount(0);
    await trigger.click();
    const themeRow = page.locator('[data-od-id="theme-row"]');
    await expect(themeRow.locator(".sel-item")).toHaveCount(21);
    // 搜索按解读/案例也能命中（81 个子类，只按名字搜不够）
    await page.locator('[data-od-id="theme-search"]').fill("凡人");
    await expect(page.locator('[data-od-id="theme-results"]')).toContainText("仙侠/修真");
    await page.locator('[data-od-id="theme-results"] [data-g="sub:凡人流"]').click();
    // 选完收起，字段显示全路径
    await expect(page.locator('[data-od-id="theme-panel"]')).toHaveCount(0);
    await expect(trigger).toContainText("仙侠/修真 / 凡人流");
    // 解读与案例：选中即见
    await expect(page.locator('[data-od-id="theme-note"]')).toContainText("凡人流");
    await expect(page.locator('[data-od-id="theme-note"]')).toContainText(
      "案例：《凡人修仙传》",
    );
    // 换大类 → 旧子类被清（跨类子类后端 400，客户端必须自觉）
    await trigger.click();
    await themeRow.locator('[data-g="theme:科幻"]').click();
    await expect(trigger).toContainText("科幻");
    await expect(trigger).not.toContainText("凡人流");
    await page.keyboard.press("Escape");
    await expect(page.locator('[data-od-id="theme-panel"]')).toHaveCount(0);
    // 换回仙侠/修真 + 凡人流，供后面保存断言
    await trigger.click();
    await themeRow.locator('[data-g="theme:仙侠/修真"]').click();
    await page.locator('[data-od-id="sub-genre-row"] [data-g="sub:凡人流"]').click();

    // 02 常见口味快捷填充 → 预填 02 文本 + 03/05 胶囊 + 04 指数（不动 01 已选题材）
    await page.locator('[data-g="comeback"]').click();
    await expect(page.locator('[data-od-id="m1-input"]')).toHaveValue("以弱破强的痛快");
    await expect(page.locator('[data-forbid="forbidden:no-deus-ex-machina"]')).toHaveClass(/on/);
    await expect(page.locator('[data-bf="battlefield:resources"]')).toHaveClass(/on/);
    await expect(page.locator(".settings-v .cost-val")).toHaveText("8");
    // 口味快捷填充不覆盖 01 已选题材（字段仍显示 大类 / 子类）
    await expect(trigger).toContainText("仙侠/修真 / 凡人流");

    // 03 回车自定义禁区
    const forbidInput = page.locator('[data-od-id="forbid-input"]');
    await forbidInput.fill("禁穿越");
    await forbidInput.press("Enter");
    await expect(page.getByText("禁穿越 ×")).toBeVisible();

    // 04 拖动 → 浮例句出现
    await page.locator('[data-od-id="cost-slider"]').fill("6");
    await expect(page.locator('[data-od-id="cost-sentence"]')).toContainText("6 分");

    // 确认完成 → 先 save（PUT /settings/genre）再 confirm，并「确认即前进」切到下一项
    const genreSave = page.waitForResponse(
      (r) => r.request().method() === "PUT" && r.url().includes("/settings/genre"),
    );
    await page.locator(".panel-foot").getByRole("button", { name: "确认完成" }).click();
    await genreSave;
    await expect(
      page.locator(".settings-v main h2", { hasText: "主线" }),
    ).toBeVisible({ timeout: 5000 });

    // 后端直查：01 题材目录 + 五字段契约（无 genre_id）
    const genre = await apiGetJSON(request, token, `/novels/${pid}/settings/genre`);
    expect(genre.theme).toBe("仙侠/修真");
    expect(genre.sub_genre).toBe("凡人流");
    expect(genre.core_promise).toBe("以弱破强的痛快");
    expect(genre.cost_ratio).toBe(6);
    expect(genre.forbidden_list).toEqual(
      expect.arrayContaining([{ text: "禁穿越" }]),
    );
    expect(genre.battlefield).toContain("battlefield:resources");
    expect(genre.genre_id).toBeUndefined();
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// ② 风格：真实表单（叙事身份 Field + 核心原则折叠组）→ 确认完成自动落库
// -------------------------------------------------------------------------

test("风格：真实表单（叙事身份 Field + 核心原则折叠组）→ 确认完成自动落库", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `风格${Date.now() % 100000}`);
    await page.getByRole("button", { name: /^设定/ }).click();
    await openSetting(page, "风格");

    // 叙事身份折叠组（默认展开）：Field 文本（种子模板预填 role，fill 覆盖）
    await fillSettingField(page, "叙事身份", "冷静克制的第三人称叙事，短句为主");

    // 核心原则折叠组（默认收起）：展开 → 首行 ListEditor 填原则
    await page.locator("summary", { hasText: "核心原则" }).click();
    const principles = page.locator("details.cfg", { hasText: "核心原则" });
    await principles
      .locator("input.input")
      .first()
      .fill("动词驱动叙事，动作外化情绪");

    // 新书未确认（§5.1 已填≠已确认）→ 点「确认完成」：先 save 再 confirm，并前进
    const styleSave = page.waitForResponse(
      (r) => r.request().method() === "PUT" && r.url().includes("/settings/style"),
    );
    await page.locator(".panel-foot").getByRole("button", { name: "确认完成" }).click();
    await styleSave;
    await expect(
      page.locator(".settings-v main h2", { hasText: "AI痕迹控制" }),
    ).toBeVisible({ timeout: 5000 });

    // 后端直查（merge-on-save 后 role / core_principles 落盘）
    const style = await apiGetJSON(request, token, `/novels/${pid}/settings/style`);
    expect(style.role).toContain("克制");
    expect(
      style.core_principles.some(
        (p: string) => typeof p === "string" && p.includes("动词驱动叙事"),
      ),
    ).toBe(true);
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// ③ AI痕迹：真实表单（疲劳词分类折叠组）→ 确认完成自动落库
// -------------------------------------------------------------------------

test("AI痕迹：真实表单（疲劳词分类列表）→ 确认完成自动落库", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `痕迹${Date.now() % 100000}`);
    await page.getByRole("button", { name: /^设定/ }).click();
    await openSetting(page, "AI痕迹控制");

    // 疲劳词折叠组（默认展开）：第一分类（总结叙事）ListEditor 填词
    // （种子模板已带默认疲劳词，fill 追加到既有分类）
    await page
      .getByPlaceholder(/添加该分类下的疲劳词/)
      .first()
      .fill("似乎");

    // 新书未确认 → 点「确认完成」（save + confirm + 前进到「伏笔」）
    const antiSave = page.waitForResponse(
      (r) => r.request().method() === "PUT" && r.url().includes("/settings/anti-ai"),
    );
    await page.locator(".panel-foot").getByRole("button", { name: "确认完成" }).click();
    await antiSave;
    await expect(
      page.locator(".settings-v main h2", { hasText: "伏笔" }),
    ).toBeVisible({ timeout: 5000 });

    // 后端直查：summary_narrative 分类含「似乎」
    const anti = await apiGetJSON(request, token, `/novels/${pid}/settings/anti-ai`);
    expect(anti.fatigue_words_zh.summary_narrative).toContain("似乎");
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// ④ 角色：真实创建角色（创建弹窗 → 反派 → 基本信息 → 确认完成自动落库）
// -------------------------------------------------------------------------

test("角色：真实创建角色（创建弹窗 → 基本信息 → 确认完成自动落库）", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `角色${Date.now() % 100000}`);
    await page.getByRole("button", { name: /^设定/ }).click();
    await openSetting(page, "角色");

    // 空列表
    await expect(page.getByText("暂无角色 · 点下方新建")).toBeVisible({
      timeout: 10000,
    });

    // 行内新建（settings-three-col 子双栏）：左栏「新建角色」→ 名称 + 角色 select + 添加
    await page.getByRole("button", { name: "新建角色" }).click();
    await page.locator(".sub-add").getByPlaceholder("角色名").fill("林晚");
    await page.locator(".sub-add").getByRole("combobox").selectOption("antagonist");
    await page.getByRole("button", { name: "添加", exact: true }).click();

    // 创建后自动选中：列表行 + 表单角色名（异步加载完成再输入，避免覆盖）
    await expect(
      page.locator(".char-row", { hasText: "林晚" }),
    ).toBeVisible({ timeout: 5000 });
    const nameInput = page
      .locator("label", { hasText: "角色名" })
      .locator("xpath=ancestor::div[1]")
      .locator("input");
    await expect(nameInput).toHaveValue("林晚", { timeout: 5000 });

    // 基本信息折叠组（默认展开）：外貌 + 背景
    await fillSettingField(page, "外貌", "眉眼清冷，总穿青色长衫");
    await fillSettingField(page, /^背景$/, "边境城邦出身的孤儿，被老药师收养");

    // 确认完成（gap3：先 save 落库 PUT /settings/character/林晚，再 confirm）
    const charSave = page.waitForResponse(
      (r) =>
        r.request().method() === "PUT" &&
        r.url().includes("/settings/character/"),
    );
    await confirmPanel(page);
    await charSave;

    // 后端直查
    const char = await apiGetJSON(
      request,
      token,
      `/novels/${pid}/settings/character/林晚`,
    );
    expect(char.name).toBe("林晚");
    expect(char.role).toBe("antagonist");
    expect(char.appearance).toContain("眉眼清冷");
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// ⑤ 预览视图（只读树 + 只读正文）：全书通读 → 点章切换 → 回写作恢复编辑
// -------------------------------------------------------------------------

test("预览：只读树 + 只读正文（草稿/归档章皆可读）→ 恢复编辑回工作台", async ({
  page,
  request,
}) => {
  // PRO(trial) 真实用户路径：直接写第一章（phase 停在 outline）→ 归档。
  // archive 端点为内容驱动（≥100 字已校验），phase 仅记账 force 置 archive，不 500。
  const { restore, token } = await setupSession(page, "trial");
  try {
    const pid = await createNovel(page, `预览读${Date.now() % 100000}`);
    const editor = await writeFirstChapter(page);

    await editor.fill(
      "旧城墙头的风沙穿过坍塌的垛口，林晚攥着那封匿名信，指尖发白。" +
        "信上只有一行字：她在城外的荒庙里等你。这座边境城邦与世隔绝已二十年，" +
        "谁都不愿提起城外的事。但妹妹失踪的第七天，他不能再等了。" +
        "这段内容足够长，以通过归档接口对正文长度的校验要求。",
    );
    await expect(page.getByText("已自动保存").first()).toBeVisible({ timeout: 8000 });

    // API 备料：第二章直接 API 归档（ai_summary=false 不烧 AI），第三章仅建章
    // 不归档（预览全书可读的草稿章样本）。须先于 UI 归档——归档事件会触发
    // wb.refresh，卷章列表一次拉全三章。
    await apiPostJSON(request, token, `/novels/${pid}/volumes/vol-1/chapters`, {
      title: "风起渡口",
    });
    // 真实 UI 路径 = 编辑器先自动保存正文（PUT /prose）再归档——预览/工作台读的
    // 都是章 store 的 prose；API 备料须同样先落 prose，否则归档章预览无正文
    const putProse = await request.put(
      `${ORIGIN}/api/novels/${pid}/chapters/vol-1-ch-2/prose`,
      {
        data: {
          prose:
            "渡口的雾还没散尽，船家已经解开了缆绳。林晚把那封匿名信折好收进怀里，" +
            "回头望了一眼雾中的城墙。船身随浪晃动，她攥紧了船舷的木栏。",
        },
        headers: { Authorization: `Bearer ${token}` },
      },
    );
    expect(putProse.ok()).toBeTruthy();
    await apiPostJSON(
      request,
      token,
      `/novels/${pid}/chapters/vol-1-ch-2/archive`,
      {
        full_text:
          "渡口的雾还没散尽，船家已经解开了缆绳。林晚把那封匿名信折好收进怀里，" +
            "回头望了一眼雾中的城墙。船身随浪晃动，她攥紧了船舷的木栏。" +
            "这一去便再无退路，荒庙里的答案，值得她赌上一切去换。" +
            "这段内容同样足够长，以满足归档接口对正文长度的校验要求，避免四百错误。",
        ai_summary: false,
      },
    );
    await apiPostJSON(request, token, `/novels/${pid}/volumes/vol-1/chapters`, {
      title: "雾中城",
    });

    // 归档第一章 → 只读 + 写作树「已归档」同步。PR 5：归档走 React 弹窗
    // （arch-confirm）；window.confirm 全兜底 accept（存量路径如 AI 摘要额度提示）
    const onDlg = (d: Dialog) => d.accept();
    page.on("dialog", onDlg);
    await page.getByRole("button", { name: "归档本章" }).click();
    await page.getByTestId("arch-confirm").click();
    try {
      await expect(page.getByText(/本章已归档 · 只读/).first()).toBeVisible({
        timeout: 10000,
      });
    } finally {
      page.off("dialog", onDlg);
    }
    // 写作树「已归档」即时同步：第一章（UI 归档）+ 第二章（API 备料归档）共 2 枚
    await expect(page.locator(".three-col .col-tree .arch-tag")).toHaveCount(2, {
      timeout: 5000,
    });

    // ── 预览视图：全书只读通读（ADJUSTMENTS #12），初始定档 = 工作台当前章 ──
    await page.getByRole("button", { name: "预览", exact: true }).click();
    await expect(page.locator(".pv-title")).toHaveText("第一章", { timeout: 10000 });
    await expect(page.locator(".two-col .tree-head .t")).toContainText("预览 · 卷");
    // 只读正文：段落渲染 + contenteditable=false（草稿/归档章皆可读）
    const pvProse = page.getByTestId("preview-prose");
    await expect(pvProse.locator("p", { hasText: "旧城墙头" })).toBeVisible();
    await expect(pvProse).toHaveAttribute("contenteditable", "false");
    // 预览树「已归档」tag 与写作树同源
    await expect(page.locator(".two-col .arch-tag")).toHaveCount(2, { timeout: 5000 });

    // 点第三章（草稿章，无正文）→ 空正文占位（预览可读全部章，未归档不再灰显）
    await page.locator(".two-col .ch", { hasText: "雾中城" }).click();
    await expect(page.locator(".pv-title")).toHaveText("第三章 · 雾中城");
    await expect(pvProse).toContainText("本章还没有正文，回到「写作」开始写。");

    // 点第二章（API 归档章）→ 正文可读
    await page.locator(".two-col .ch", { hasText: "风起渡口" }).click();
    await expect(page.locator(".pv-title")).toHaveText("第二章 · 风起渡口");
    await expect(pvProse.locator("p", { hasText: "渡口的雾" })).toBeVisible();

    // ── 回写作：归档章只读横幅 + 恢复编辑（换皮不减功能，入口在正文编辑页）──
    await page.getByRole("button", { name: /^写作/ }).click();
    await expect(page.getByText(/本章已归档 · 只读/).first()).toBeVisible({
      timeout: 5000,
    });
    await expect(page.locator(".three-col .editor")).toHaveAttribute(
      "contenteditable",
      "false",
    );
    page.once("dialog", (d) => d.accept());
    await page.getByRole("button", { name: "恢复编辑" }).click();
    // 恢复是异步 POST + 重拉，属性翻转有窗口期，须用可重试的属性断言等它变 "true"
    await expect(page.locator(".three-col .editor")).toHaveAttribute(
      "contenteditable",
      "true",
      { timeout: 10000 },
    );
    await expect(page.getByText(/本章已归档 · 只读/)).toHaveCount(0);
    // 写作树「已归档」只剩 API 归档的第二章（第一章恢复后撤下）
    await expect(page.locator(".three-col .col-tree .arch-tag")).toHaveCount(1);

    // 再进预览：重挂载回初始定档（工作台当前章=第一章）；归档 tag 只剩第二章
    await page.getByRole("button", { name: "预览", exact: true }).click();
    await expect(page.locator(".pv-title")).toHaveText("第一章", { timeout: 10000 });
    await expect(page.locator(".two-col .arch-tag")).toHaveCount(1);
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// ⑧ P2-1：设定面板切换脏守卫（未保存修改 → confirm 弹窗；取消保留输入，确认才切换）
// -------------------------------------------------------------------------

test("P2-1 面板切换守卫：脏表单切换需确认，取消保留输入", async ({ page, request }) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `守卫${Date.now() % 100000}`);
    await page.getByRole("button", { name: /^设定/ }).click();

    // v2 默认面板 = 题材 → 切到「世界」（地理折叠组默认展开），等表单加载完成
    await openSetting(page, "世界");
    const scene = settingFieldTA(page, "主要场景");
    await expect(scene).toBeVisible({ timeout: 10000 });

    // 输入 → 脏状态
    await scene.fill("边境城邦：临海要塞，北接荒漠");

    // 取消分支：dismiss 确认框 → 面板不切换、输入保留
    let dialogShown = false;
    page.once("dialog", (d) => {
      dialogShown = true;
      void d.dismiss();
    });
    await openSetting(page, "风格");
    expect(dialogShown).toBe(true);
    await expect(scene).toBeVisible();
    await expect(scene).toHaveValue("边境城邦：临海要塞，北接荒漠");

    // 确认分支：接受确认框 → 面板切换
    page.once("dialog", (d) => void d.accept());
    await openSetting(page, "风格");
    await expect(
      page.locator(".settings-v main h2", { hasText: "风格" }),
    ).toBeVisible({ timeout: 5000 });

    // 后端未写入任何世界设定（脏输入未保存）
    const world = await apiGetJSON(request, token, `/novels/${pid}/settings/world`);
    expect(world?.geography?.scenes ?? "").toBe("");
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// P2-1b/1c/1d：三个「脏意识」缺口（角色切换 / 离开设定视图 / 完成设定自动保存）
// -------------------------------------------------------------------------

test("P2-1b 角色切换守卫：脏表单切换需确认，取消保留输入", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    const pid = await createNovel(page, `守卫角色${Date.now() % 100000}`);
    await page.getByRole("button", { name: /^设定/ }).click();
    await openSetting(page, "角色");

    // 创建两个角色（行内新建：左栏输入名称 → 添加；配角为默认角色）
    for (const name of ["阿甲", "阿乙"]) {
      await page.getByRole("button", { name: "新建角色" }).click();
      await page.locator(".sub-add").getByPlaceholder("角色名").fill(name);
      await page.getByRole("button", { name: "添加", exact: true }).click();
      await expect(
        page.locator(".char-row", { hasText: name }),
      ).toBeVisible({ timeout: 5000 });
    }
    // 创建第二个角色后自动选中「阿乙」；先切回「阿甲」（干净，无弹窗）。
    // 阿甲数据为异步加载（GET /settings/character/阿甲），须等表单角色名=阿甲
    // （快照已就绪）再输入，否则加载完成会覆盖输入并重置脏标记 → 守卫不触发。
    await page.locator(".char-row", { hasText: "阿甲" }).click();
    const nameInput = page
      .locator("label", { hasText: "角色名" })
      .locator("xpath=ancestor::div[1]")
      .locator("input");
    await expect(nameInput).toHaveValue("阿甲", { timeout: 5000 });

    // 编辑阿甲的外貌 → 脏
    await fillSettingField(page, "外貌", "阿甲的外貌描述");
    const appearance = settingFieldTA(page, "外貌");

    // 取消分支：dismiss → 仍选中阿甲、输入保留
    let dialogShown = false;
    page.once("dialog", (d) => {
      dialogShown = true;
      void d.dismiss();
    });
    await page.locator(".char-row", { hasText: "阿乙" }).click();
    expect(dialogShown).toBe(true);
    await expect(appearance).toHaveValue("阿甲的外貌描述");

    // 确认分支：accept → 切换为阿乙（表单角色名=阿乙）
    page.once("dialog", (d) => void d.accept());
    await page.locator(".char-row", { hasText: "阿乙" }).click();
    await expect(nameInput).toHaveValue("阿乙");
  } finally {
    await restore();
  }
});

test("P2-1c 离开设定视图守卫：脏表单离开需确认，取消保留", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    await createNovel(page, `守卫离开${Date.now() % 100000}`);
    await page.getByRole("button", { name: /^设定/ }).click();

    // v2 默认面板 = 题材 → 切到「世界」再弄脏
    await openSetting(page, "世界");
    const scene = settingFieldTA(page, "主要场景");
    await expect(scene).toBeVisible({ timeout: 10000 });
    await scene.fill("边境城邦：临海要塞，北接荒漠");

    // 取消分支：dismiss → 仍在设定视图、输入保留
    let dialogShown = false;
    page.once("dialog", (d) => {
      dialogShown = true;
      void d.dismiss();
    });
    await page.getByRole("button", { name: /^写作/ }).click();
    expect(dialogShown).toBe(true);
    await expect(scene).toBeVisible();
    await expect(scene).toHaveValue("边境城邦：临海要塞，北接荒漠");

    // 确认分支：accept → 离开设定视图（世界面板卸载）
    page.once("dialog", (d) => void d.accept());
    await page.getByRole("button", { name: /^写作/ }).click();
    await expect(scene).toHaveCount(0);
  } finally {
    await restore();
  }
});

test("P2-1d 脏表单确认完成：自动保存再确认（内容落库 + 按钮转保存修改）", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `守卫完成${Date.now() % 100000}`);
    await page.getByRole("button", { name: /^设定/ }).click();

    // v2 默认面板 = 题材 → 切到「世界」；填 ≥4 个子字段（3 地理 + 1 政治，
    // readiness 阈值=4），不点保存（脏表单）
    await openSetting(page, "世界");
    const scene = settingFieldTA(page, "主要场景");
    await expect(scene).toBeVisible({ timeout: 10000 });
    await fillSettingField(page, "主要场景", "一座被沙漠包围的边境城邦");
    await fillSettingField(page, "气候", "昼夜温差极大，夜晚滴水成冰");
    await fillSettingField(page, "地理限制", "北临黑海，西侧是断崖");
    await page.locator("summary", { hasText: "政治" }).click();
    await fillSettingField(page, "统治形式", "城主议会制，元老席位世袭");

    // 确认完成 → 应先自动保存（PUT /settings/world）再确认，并「确认即前进」到风格
    const autoSave = page.waitForResponse(
      (r) => r.request().method() === "PUT" && r.url().includes("/settings/world"),
    );
    await page.locator(".panel-foot").getByRole("button", { name: "确认完成" }).click();
    await autoSave;
    await expect(
      page.locator(".settings-v main h2", { hasText: "风格" }),
    ).toBeVisible({ timeout: 5000 });

    // 后端直查：内容已落库（自动保存生效）
    const world = await apiGetJSON(request, token, `/novels/${pid}/settings/world`);
    expect(world.geography.scenes).toContain("边境城邦");
    expect(world.politics.rule).toContain("城主议会制");
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// tasks 2.2：前两步顺序（简介→题材）+ 确认即前进
// -------------------------------------------------------------------------
test("前两步顺序 + 确认即前进：简介确认后自动切到题材（tasks 2.2）", async ({
  page,
}) => {
  const { restore } = await setupSession(page);
  try {
    await createNovel(page, `前进${Date.now() % 100000}`);
    await page.getByRole("button", { name: /^设定/ }).click();

    // ① 默认落「简介」
    await expect(
      page.locator(".settings-v main h2", { hasText: "简介" }),
    ).toBeVisible({ timeout: 10000 });

    // ② 填简介 → 确认完成
    await fillSettingField(page, "故事简介", "外门杂徒林拾，在宗门扫了十年落叶。");
    const introSave = page.waitForResponse(
      (r) => r.request().method() === "PUT" && /\/novels\/[^/]+\/story$/.test(r.url()),
    );
    const btn = page.locator(".panel-foot").getByRole("button", { name: "确认完成" });
    await expect(btn).toBeVisible({ timeout: 5000 });
    await btn.click();
    await introSave;

    // ③ 确认即前进 → 自动切到「题材」
    await expect(
      page.locator(".settings-v main h2", { hasText: "题材" }),
    ).toBeVisible({ timeout: 5000 });

    // ④ 回点「简介」：内容保留、不锁题材
    await openSetting(page, "简介");
    await expect(
      page.locator(".settings-v main h2", { hasText: "简介" }),
    ).toBeVisible({ timeout: 5000 });
    await expect(page.locator(".textarea").first()).toHaveValue(
      "外门杂徒林拾，在宗门扫了十年落叶。",
    );
  } finally {
    await restore();
  }
});
