import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page, type APIRequestContext, type Dialog } from "@playwright/test";
import { cleanupSessionNovels, pollBackend, stableClick, writeFirstChapter } from "./helpers";
import { entitlementFor } from "./tier-features";

// =========================================================================
// 设定真实表单 + 预览只读 E2E（PR4 v2 设定视图 two-col + 预览视图复刻后改版）
//   ① 题材：GenreSettingForm 真实题材选择器（空态 → 选 都市日常 → 应用题材 → 自动保存）
//   ② 风格：StyleSettingForm 真实表单（叙事身份 Field + 核心原则折叠组 ListEditor）
//   ③ 禁用词收编（banned-words-into-style）：文风硬约束区禁用词折叠组（原 AI痕迹面板退役）
//   ④ 角色：CharacterManager 真实创建角色（创建弹窗 → 基本信息 → 保存）
//   ⑤ 预览（只读树 + 只读正文）：全书通读（草稿/归档章皆可读）→ 点章切换 →
//      归档 tag 同步 → 回工作台恢复编辑（归档管理在正文编辑页）
//   面板确认统一走 panel-foot「确认完成」（先 save 后 confirm，gap3）→ 按钮转
//   「保存修改」（ADJUSTMENTS #9）；面板标题/导航用新短名（题材/简介/世界/…）。
// =========================================================================
// 与 creation-flow.spec.ts 共享鉴权与设定确认手法；与 free-writing-flow.spec.ts
// 共享归档/正文工作台手法。前置条件：docker 4 服务已启动。

const S_API = process.env.E2E_S_API || "http://127.0.0.1:19000/api/web";
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
  cfg.entitlement = entitlementFor(tier); // 快照单源（tier-features 6.2）
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
/**
 * 点「确认完成」。**顺序无关**：确认即前进会切到 SETTINGS_ITEMS 的下一项，
 * 故成功判据＝「留在本格（脚部转『保存修改』）」**或**「已推进到另一格」。
 * （此前写死「必出现保存修改」，在末项或推进目标未确认时会假失败。）
 */
async function confirmPanel(page: Page) {
  const btn = page
    .locator(".panel-foot")
    .getByRole("button", { name: "确认完成" });
  await expect(btn).toBeVisible({ timeout: 5000 });
  const title = page.locator(".settings-v main h2").first();
  const before = (await title.count()) ? await title.innerText() : "";
  await btn.click();
  await expect(async () => {
    const now = (await title.count()) ? await title.innerText() : "";
    const saveBtn = await page
      .locator(".panel-foot")
      .getByRole("button", { name: "保存修改" })
      .count();
    expect(now !== before || saveBtn > 0).toBe(true);
  }).toPass({ timeout: 5000 });
}

/**
 * 已确认面板的保存路径：种子模板让 style 开书即有内容（readiness 即
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
// ① 题材：五格新契约面板（口味起点 → 自定义禁区 → 吃苦指数 → 确认落契约）
// -------------------------------------------------------------------------

test("题材：五格面板（口味起点 → 自定义禁区 → 吃苦指数 → 确认落契约）", async ({
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

    // 五格齐全（编号 01-05 + 名称；06 剧情轨道已退役——归主线规划）
    await expect(page.locator(".settings-v .mod")).toHaveCount(5);
    for (const name of ["题材", "主要看什么", "绝对禁止", "吃苦指数", "本小说斗什么"]) {
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
    // 浏览 ≠ 选中（用户报障「题材老是自动变成玄幻」）：点左列科幻只是看它的子类，字段不动
    await trigger.click();
    await themeRow.locator('[data-g="theme:科幻"]').click();
    await expect(trigger).toContainText("仙侠/修真 / 凡人流");
    await expect(page.locator('[data-od-id="sub-genre-row"]')).toContainText("星际");
    // 显式「只归到大类（科幻）」→ 这才换大类，且旧子类被清（跨类子类后端 400，客户端必须自觉）
    await page.locator('[data-od-id="sub-genre-row"] [data-g="theme:科幻"]').click();
    await expect(trigger).toContainText("科幻");
    await expect(trigger).not.toContainText("凡人流");
    await page.keyboard.press("Escape");
    await expect(page.locator('[data-od-id="theme-panel"]')).toHaveCount(0);
    // 换回仙侠/修真 + 凡人流，供后面保存断言
    await trigger.click();
    await themeRow.locator('[data-g="theme:仙侠/修真"]').click();
    await page.locator('[data-od-id="sub-genre-row"] [data-g="sub:凡人流"]').click();

    // 02 常见口味＝起点：填的是**一句话**（作家改的就是这句）+ 03/05 胶囊 + 04 指数
    await page.locator('[data-g="comeback"]').click();
    await expect(page.locator('[data-od-id="m1-input"]')).toHaveValue(/读者要看到/);
    await expect(page.locator('[data-od-id="genre-panel"]')).toContainText("标签：以弱破强的痛快");
    // 作家在这句话上改：改完能保存（主输入可编辑，不是只读的 AI 补充）
    await page
      .locator('[data-od-id="m1-input"]')
      .fill("读者要看到弱者用脑子翻盘，每赢一次都痛快");
    await expect(page.locator('[data-od-id="genre-panel"]')).toContainText("/200");
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

    // 确认完成 → 先 save（PUT /settings/genre）再 confirm，并「确认即前进」切到下一项（新顺序：题材→世界）
    const genreSave = page.waitForResponse(
      (r) => r.request().method() === "PUT" && r.url().includes("/settings/genre"),
    );
    await page.locator(".panel-foot").getByRole("button", { name: "确认完成" }).click();
    await genreSave;
    await expect(
      page.locator(".settings-v main h2", { hasText: "世界" }),
    ).toBeVisible({ timeout: 5000 });
    // 确认即前进＝换面板：上一条回执的撤销闭包属于题材表单，留在世界面板就是
    // 「点了没反应」的死撤销（值还已落库）→ 必须清掉（换面板四条路径统一兜）
    await expect(page.locator('[data-od-id="panel-receipt"]')).toHaveCount(0);

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
// ①b 长回执不折行、不撑宽中栏：脚部折出的第二行会落到窗口状态条（.statusbar，
// fixed 26px）之下点不到；中栏被内容撑宽则会把右栏 AI 挤出屏幕（2026-09-10 实测）
// -------------------------------------------------------------------------

test("题材：长回执单行截断，确认完成点得到", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    await createNovel(page, `回执${Date.now() % 100000}`);
    await page.getByRole("button", { name: /^设定/ }).click();
    await openSetting(page, "题材");

    // 口味胶囊＝一次点击改 5 格 → 最长的一条回执
    await page.locator('[data-g="comeback"]').click();
    const receipt = page.locator('[data-od-id="panel-receipt"]');
    await expect(receipt).toContainText("覆盖：主要看什么 / 绝对禁止");

    // 文本单行截断（scrollWidth > clientWidth），全文挂 title 悬浮可读
    const rt = receipt.locator(".rt");
    expect(await rt.getAttribute("title")).toBe((await rt.textContent())?.trim());
    expect(await rt.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true);

    // 脚部不许折行：`flex-wrap: nowrap` 只禁「项换行」，进度提示文字折行同样会把
    // 脚部顶高（一行 ≈58px，两行 ≈93px；提示折成两行时自身高 43 ≠ 一行 22）
    const foot = page.locator(".panel-foot");
    expect((await foot.boundingBox())!.height).toBeLessThan(70);
    const note = page.locator(".panel-foot .note");
    expect(await note.evaluate((el) => getComputedStyle(el).whiteSpace)).toBe("nowrap");
    expect((await note.boundingBox())!.height).toBeLessThan(30);
    const btn = foot.getByRole("button", { name: "确认完成" });
    await btn.scrollIntoViewIfNeeded();
    const footBox = (await foot.boundingBox())!;
    const statusbar = (await page.locator(".statusbar").boundingBox())!;
    expect(footBox.y + footBox.height).toBeLessThanOrEqual(statusbar.y + 0.5);

    // 主按钮真的点得到：命中测试＝当初的失败签名（点下去命中的是状态条/回执）
    const box = (await btn.boundingBox())!;
    expect(
      await page.evaluate(
        ([x, y]) =>
          (document.elementFromPoint(x as number, y as number) as HTMLElement)?.textContent?.trim(),
        [box.x + box.width / 2, box.y + box.height / 2],
      ),
    ).toBe("确认完成");

    // 中栏没有被回执撑宽：右栏 AI 仍在屏幕内（撑宽时 AI 栏被挤出右侧约 58px）
    const ai = (await page.locator(".settings-v .col-ai").boundingBox())!;
    expect(ai.x + ai.width).toBeLessThanOrEqual((await page.viewportSize())!.width);
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// ② 风格：两页签（文字文风三区＋量化空态）→ 确认完成自动落库（style-settings-v2）
// -------------------------------------------------------------------------

test("文风：两页签（文字文风三区＋量化空态）→ 确认完成自动落库", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `风格${Date.now() % 100000}`);
    await page.getByRole("button", { name: /^设定/ }).click();
    await openSetting(page, "文风");

    // 两页签：文字文风（默认签）｜量化参数（未蒸馏 → 空态）
    await expect(page.locator('[data-od-id="style-tabs"]')).toBeVisible();
    await expect(page.locator('[data-od-id="style-tab-badge"]')).toHaveText("题材默认");
    await page.locator('[data-od-id="ptab-quant"]').click();
    await expect(page.locator('[data-od-id="quant-empty"]')).toBeVisible();
    await expect(page.locator('[data-od-id="quant-tab-badge"]')).toHaveText("未蒸馏");
    await page.locator('[data-od-id="ptab-text"]').click();
    // 未完成（7/8）：完成卡不出现（settings-done-entry）
    await expect(page.locator('[data-od-id="settings-done-card"]')).toHaveCount(0);

    // 三区：叙事身份（textarea）＋硬约束首行 ListEditor
    await page
      .locator('[data-od-id="input-style-role"]')
      .fill("冷静克制的第三人称叙事，短句为主");
    await page
      .locator('[data-od-id="list-rules"] input.input')
      .first()
      .fill("动词驱动叙事，动作外化情绪");
    // 改过身份与红线 → 页签徽标翻「已自定义」
    await expect(page.locator('[data-od-id="style-tab-badge"]')).toHaveText("已自定义 · 2 处");

    // 新书未确认（§5.1 已填≠已确认）→ 点「确认完成」：先 save 再 confirm，
    // 并「确认即前进」到下一项（顺序：文风→伏笔）
    const styleSave = page.waitForResponse(
      (r) => r.request().method() === "PUT" && r.url().includes("/settings/style"),
    );
    await page.locator(".panel-foot").getByRole("button", { name: "确认完成" }).click();
    await styleSave;
    await expect(
      page.locator(".settings-v main h2", { hasText: "伏笔" }),
    ).toBeVisible({ timeout: 5000 });

    // 后端直查：归一三区落盘；撤并键不再出现（_legacy_style 属留底键，GET 已剥）
    const style = await apiGetJSON(request, token, `/novels/${pid}/settings/style`);
    expect(style.role).toContain("克制");
    expect(
      style.rules.some((p: string) => typeof p === "string" && p.includes("动词驱动叙事")),
    ).toBe(true);
    expect(style).not.toHaveProperty("tone");
    expect(style).not.toHaveProperty("possible_mistakes");
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// ③ 禁用词收编（banned-words-into-style）：文风硬约束区「禁用词」折叠组 →
//    确认完成自动落库；文风确认后推进到伏笔（末项语义变更一并回归）
// -------------------------------------------------------------------------

test("禁用词收编：文风硬约束区禁用词折叠组 → 确认完成落库并推进伏笔", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `痕迹${Date.now() % 100000}`);
    await page.getByRole("button", { name: /^设定/ }).click();
    await openSetting(page, "文风");

    // 禁用词折叠组（默认收起）：点组头展开；模板预填 37 词 → 点「添加一项」追加新行
    const bannedCfg = page.locator("details.cfg", { hasText: "禁用词" }).first();
    await bannedCfg.locator("summary").click();
    const addBtn = bannedCfg.getByRole("button", { name: /添加一项/ });
    await addBtn.scrollIntoViewIfNeeded();
    await addBtn.click();
    await bannedCfg.locator("input.input").last().fill("似乎");

    // 确认完成（save + confirm）；文风确认后即前进到伏笔（07 末项语义）
    const stylePut = page.waitForResponse(
      (r) => r.request().method() === "PUT" && r.url().includes("/settings/style"),
    );
    await page.locator(".panel-foot").getByRole("button", { name: "确认完成" }).click();
    await stylePut;
    await expect(
      page.locator(".settings-v main h2", { hasText: "伏笔" }),
    ).toBeVisible({ timeout: 5000 });

    // 后端直查：文风 KV banned_words 含「似乎」（旧 /settings/anti-ai 写通道已退役）
    const style = await apiGetJSON(request, token, `/novels/${pid}/settings/style`);
    expect(style.banned_words).toContain("似乎");
    // 旧面板退役：antiAI 写通道 400
    const retired = await request.put(`${ORIGIN}/api/novels/${pid}/settings/anti-ai`, {
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      data: { fatigue_words_zh: {} },
    });
    expect(retired.status()).toBe(400);
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// ④ 角色：真实创建角色（创建弹窗 → 反派 → 基本信息 → 确认完成自动落库）
// -------------------------------------------------------------------------
test("角色：分组列表新建 → 卷宗卡填写自动保存 → 名称确认删除", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    // UI 建书：C端 鉴权是「token == config.json 会话」的本地比对，request 夹具
    // 在浏览器会话建立前直打 API 会 401（登录状态无效），故走 UI 路径
    const pid = await createNovel(page, `角色${Date.now() % 100000}`);
    await page.getByRole("button", { name: /^设定/ }).click();
    await openSetting(page, "角色");

    // 空状态：左侧添加入口可见
    await expect(page.getByRole("button", { name: "添加角色" })).toBeVisible({
      timeout: 10000,
    });

    // 新建：点击添加 → 自动选中 → 命名（自动保存 PATCH）
    await page.getByRole("button", { name: "添加角色" }).click();
    const nameInput = page.getByRole("textbox", { name: "角色名称" });
    await nameInput.fill("林晚");

    // 自动保存 PATCH 落库（防抖 600ms）
    const patchReq = page.waitForRequest(
      (r) => r.method() === "PATCH" && r.url().includes("/characters/"),
    );
    await patchReq;

    // 类型切换成反派（chip 可点击胶囊）
    await page.getByRole("button", { name: "反派", exact: true }).click();

    // 档案行：外貌标签输入（自动保存）
    await page.getByRole("textbox", { name: "外貌标签" }).fill("眉眼清冷，青色长衫");

    // 等最后一格 PATCH 真落库（条件轮询替代固定 sleep，e2e-speedup-infra）
    const list = await pollBackend(
      () => apiGetJSON(request, token, `/novels/${pid}/characters`),
      (l: {
        data?: { items?: Array<{ name: string; role: string; dossier: { look?: string } }> };
      }) =>
        (l.data?.items ?? []).some(
          (x) =>
            x.name === "林晚" && x.role === "反派" && (x.dossier?.look ?? "").includes("眉眼清冷"),
        ),
    );
    const item = (list.data?.items ?? []).find((x: { name: string }) => x.name === "林晚");
    expect(item).toBeTruthy();
    expect(item.role).toBe("反派");
    expect(item.dossier.look).toContain("眉眼清冷");

    // 删除（L3）：点删除 → 输名字解锁 → 确认
    await page.getByRole("button", { name: "删除", exact: true }).first().click();
    const confirmInput = page.getByPlaceholder(/输入「林晚」以确认/);
    await confirmInput.fill("错字");
    await expect(page.getByRole("button", { name: "删除", exact: true }).last()).toBeDisabled();
    await confirmInput.fill("林晚");
    await page.getByRole("button", { name: "删除", exact: true }).last().click();

    // 撤销找回（undo 是 fire-and-forget 的后台调用，须等 POST 返回再断言）
    const undoPost = page.waitForResponse(
      (r) => r.request().method() === "POST" && r.url().includes("/ops/"),
    );
    await page.getByRole("button", { name: "撤销" }).click();
    await undoPost;
    const list2 = await apiGetJSON(request, token, `/novels/${pid}/characters`);
    expect((list2.data?.items ?? []).some((x: { name: string }) => x.name === "林晚")).toBe(true);

    // 确认链（review P1 回归钉）：立主角 + 人设 → 确认完成走两档门禁端点
    // → settings/status 落盘 → gate/status 已确认；再清人设 → stale
    await page.getByRole("button", { name: "主角", exact: true }).click();
    await page.getByRole("textbox", { name: "一句话人设" }).fill("瘦高个的拾残人");
    await pollBackend(
      () => apiGetJSON(request, token, `/novels/${pid}/characters`),
      (l: { data?: { items?: unknown[] } }) =>
        JSON.stringify(l.data?.items ?? []).includes("瘦高个的拾残人"),
    ); // 末格 PATCH 落库（条件轮询替代固定 sleep）
    // 页脚提示＝整项口径（c-chars-confirm-scope）：未确认＝第一次确认档，只看主角名称+人设
    await expect(page.locator(".panel-foot .note")).toHaveText(
      "主角写全了——第一次确认只看主角；配角、反派后补也行，改动会自动保存",
    );
    const confirmPost = page.waitForResponse(
      (r) =>
        r.request().method() === "POST" && r.url().includes("/characters/confirm"),
    );
    const statusPut = page.waitForResponse(
      (r) =>
        r.request().method() === "PUT" && r.url().includes("/settings/status/characters"),
    );
    await page.locator(".panel-foot").getByRole("button", { name: "确认完成" }).click();
    expect((await confirmPost).status()).toBe(200);
    expect((await statusPut).status()).toBe(200);
    const gate1 = await apiGetJSON(request, token, `/novels/${pid}/characters/gate/status`);
    expect(gate1.data?.confirmed).toBe(true);
    expect(gate1.data?.stale).toBe(false);
    // 回角色面板（确认即前进会切走）：已确认＝此后档，页脚常驻点名缺口卡 + 按钮转「重新确认」
    const charsReload = page.waitForResponse(`**/api/novels/${pid}/characters`);
    await page.locator(".settings-v .col-tree .s-item", { hasText: "角色" }).click();
    await charsReload;
    await expect(page.locator('[data-od-id="chars-gate-hint"]')).toHaveText(
      "还差：主角《林晚》缺 剧情定位、核心认知盲区、能力上限 等",
    );
    await expect(page.locator(".panel-foot").getByRole("button", { name: "重新确认" })).toBeVisible();
    // 清空人设（门禁字段）→ 内容有变
    const list3 = await apiGetJSON(request, token, `/novels/${pid}/characters`);
    const card3 = list3.data.items.find((x: { name: string }) => x.name === "林晚");
    const clr = await request.patch(`/api/novels/${pid}/characters/${card3.id}`, {
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      data: { path: "persona", value: "", base_rev: card3.rev },
    });
    expect(clr.status()).toBe(200);
    const gate2 = await apiGetJSON(request, token, `/novels/${pid}/characters/gate/status`);
    expect(gate2.data?.stale).toBe(true);
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

    // 归档第一章 → 只读 + 写作树「已归档」同步。PR 5：归档走 React 弹窗
    // （arch-confirm）；window.confirm 全兜底 accept（存量路径如 AI 摘要额度提示）
    const onDlg = (d: Dialog) => d.accept();
    page.on("dialog", onDlg);
    // 归档入口在操作页签（2026-09-27 自头部移入）
    await page.getByRole("tab", { name: /^操作/ }).click();
    await page.getByRole("button", { name: "归档本章" }).click();
    await page.getByTestId("arch-confirm").click();
    try {
      // 头部「已归档」徽章（c-rail-ai-only：右栏归档卡退役，只读横幅在正文页签）
      await expect(page.locator(".e-meta")).toContainText("已归档", { timeout: 10000 });
    } finally {
      page.off("dialog", onDlg);
    }
    // 写作树「已归档」即时同步：此刻只有第一章一枚（跨章可见性由预览树 count=2 覆盖）
    await expect(page.locator(".three-col .col-tree .arch-tag")).toHaveCount(1, {
      timeout: 5000,
    });

    // API 备料：第二章直接 API 归档（ai_summary=false 不烧 AI），第三章仅建章
    // 不归档（预览全书可读的草稿章样本）。须在第一章归档之后——正文 PUT 有排队
    // 门禁（仅 frontier 章可写，非 frontier 409），ch1 归档后 frontier 恰好轮到 ch2。
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

    // ── 预览视图：三栏阅读器（preview-reader，c-preview-reader），
    //    定档 = 全书首章（不继承写作页当前章）；目录头主线计数；成稿状态标签 ──
    await page.getByRole("button", { name: "预览", exact: true }).click();
    const pvChapter = page.getByTestId("pv-chapter");
    await expect(pvChapter).toContainText("第一章", { timeout: 10000 });
    await expect(page.getByTestId("pv-count")).toContainText("主线 3 章 · 1 卷 · 不含旧稿");
    // 只读正文：段落渲染（草稿/归档章皆可读；只读由非编辑组件结构保证）
    const pvProse = page.getByTestId("preview-prose");
    await expect(pvProse.locator("p", { hasText: "旧城墙头" })).toBeVisible();
    // 目录行成稿状态 pill：第一章/第二章 已归档、第三章 拟定（章纲三态 dot 不进预览）
    const pvRows = page.locator(".pv-toc .pv-ch");
    await expect(pvRows).toHaveCount(3, { timeout: 5000 });
    await expect(pvRows.locator(".pill", { hasText: "已归档" })).toHaveCount(2);
    await expect(pvRows.locator(".pill", { hasText: "拟定" })).toHaveCount(1);

    // 点第三章（拟定章，无正文）→ 空正文占位（预览可读全部章）
    await pvRows.filter({ hasText: "雾中城" }).click();
    await expect(pvChapter).toContainText("第三章 · 雾中城");
    await expect(pvProse).toContainText("本章还没有正文，回到「写作」开始写。");

    // 点第二章（API 归档章）→ 正文可读
    await pvRows.filter({ hasText: "风起渡口" }).click();
    await expect(pvChapter).toContainText("第二章 · 风起渡口");
    await expect(pvProse.locator("p", { hasText: "渡口的雾" })).toBeVisible();

    // ── 回写作：点「写作」回书主页（页签回默认主页），点回第一章看归档只读横幅 ──
    await page.getByRole("button", { name: /^写作/ }).click();
    await expect(page.getByTestId("write-home")).toBeVisible({ timeout: 10000 });
    await page.locator(".three-col .col-tree .ch").first().click();
    // 点章强制落「章纲」页签（PR3 口径）→ 只读正文在「正文」页签
    await page.getByRole("tab", { name: /^正文/ }).click();
    await expect(page.getByText(/本章已归档 · 只读/).first()).toBeVisible({
      timeout: 5000,
    });
    await expect(page.locator(".three-col .editor")).toHaveAttribute(
      "contenteditable",
      "false",
    );
    page.once("dialog", (d) => d.accept());
    await page.getByRole("button", { name: "恢复编辑" }).click();
    // 恢复是异步 POST + 重拉；c-prose-edit-gate：预览往返卸载过工作台（编辑态已复位），
    // 解锁后落查看态——点「编辑正文」进编辑态再断言可编辑
    await page.getByTestId("prose-edit").click({ timeout: 10000 });
    await expect(page.locator(".three-col .editor")).toHaveAttribute(
      "contenteditable",
      "true",
      { timeout: 10000 },
    );
    await expect(page.getByText(/本章已归档 · 只读/)).toHaveCount(0);
    // 写作树「已归档」只剩 API 归档的第二章（第一章恢复后撤下）
    await expect(page.locator(".three-col .col-tree .arch-tag")).toHaveCount(1);

    // 再进预览：重挂载定档＝首章；已归档 pill 只剩第二章，
    // 第一章恢复后转为「草稿」（有正文未归档）
    await page.getByRole("button", { name: "预览", exact: true }).click();
    await expect(page.getByTestId("pv-chapter")).toContainText("第一章", { timeout: 10000 });
    const pvRows2 = page.locator(".pv-toc .pv-ch");
    await expect(pvRows2.locator(".pill", { hasText: "已归档" })).toHaveCount(1);
    await expect(pvRows2.filter({ hasText: /^第一章/ }).locator(".pill")).toHaveText("草稿");
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

    // v2 默认面板 = 题材 → 切到「世界」（契约 v2 五格），等舞台框加载完成
    await openSetting(page, "世界");
    const stage = page.locator('[data-od-id="stage-input"]');
    await expect(stage).toBeVisible({ timeout: 10000 });

    // 输入 → 脏状态
    await stage.fill("边境城邦：临海要塞，北接荒漠");

    // 取消分支：dismiss 确认框 → 面板不切换、输入保留
    let dialogShown = false;
    page.once("dialog", (d) => {
      dialogShown = true;
      void d.dismiss();
    });
    await openSetting(page, "文风");
    expect(dialogShown).toBe(true);
    await expect(stage).toBeVisible();
    await expect(stage).toHaveValue("边境城邦：临海要塞，北接荒漠");

    // 确认分支：接受确认框 → 面板切换
    page.once("dialog", (d) => void d.accept());
    await openSetting(page, "世界");
    await expect(
      page.locator(".settings-v main h2", { hasText: "世界" }),
    ).toBeVisible({ timeout: 5000 });

    // 后端未写入任何世界设定（脏输入未保存）
    const world = await apiGetJSON(request, token, `/novels/${pid}/settings/world`);
    expect(world?.stage ?? "").toBe("");
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// P2-1b/1c/1d：三个「脏意识」缺口（角色切换 / 离开设定视图 / 完成设定自动保存）
// -------------------------------------------------------------------------

test("P2-1b 角色面板脏接入住守卫：输入未落库时离开设定需确认", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    await createNovel(page, `守卫角色${Date.now() % 100000}`);
    await page.getByRole("button", { name: /^设定/ }).click();
    await openSetting(page, "角色");

    // 新契约 = 自动保存制（单格 PATCH 防抖 600ms），「卡间切换确认」已成历史；
    // 本用例验证角色面板的脏状态接入设定的离开守卫。拖住 PATCH 让脏窗口可复现
    await page.route(/\/characters\/[0-9a-f-]+$/, (route) => {
      if (route.request().method() === "PATCH") {
        setTimeout(() => void route.continue(), 1500);
      } else {
        void route.continue();
      }
    });

    await page.getByRole("button", { name: "添加角色" }).click();
    const nameInput = page.getByRole("textbox", { name: "角色名称" });
    await expect(nameInput).toBeVisible({ timeout: 8000 });

    // 输入即脏（PATCH 被拖住）→ 立即试图离开设定
    await nameInput.fill("阿甲");

    // 取消分支：dismiss → 仍在设定视图、输入保留
    let dialogShown = false;
    page.once("dialog", (d) => {
      dialogShown = true;
      void d.dismiss();
    });
    await page.getByRole("button", { name: /^写作/ }).click();
    expect(dialogShown).toBe(true);
    await expect(nameInput).toHaveValue("阿甲");

    // 确认分支：accept → 离开设定视图（角色面板卸载）
    page.once("dialog", (d) => void d.accept());
    await page.getByRole("button", { name: /^写作/ }).click();
    await expect(nameInput).toHaveCount(0);
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
    const stage = page.locator('[data-od-id="stage-input"]');
    await expect(stage).toBeVisible({ timeout: 10000 });
    await stage.fill("边境城邦：临海要塞，北接荒漠");

    // 取消分支：dismiss → 仍在设定视图、输入保留
    let dialogShown = false;
    page.once("dialog", (d) => {
      dialogShown = true;
      void d.dismiss();
    });
    await page.getByRole("button", { name: /^写作/ }).click();
    expect(dialogShown).toBe(true);
    await expect(stage).toBeVisible();
    await expect(stage).toHaveValue("边境城邦：临海要塞，北接荒漠");

    // 确认分支：accept → 离开设定视图（世界面板卸载）
    page.once("dialog", (d) => void d.accept());
    await page.getByRole("button", { name: /^写作/ }).click();
    await expect(stage).toHaveCount(0);
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

    // v2 默认面板 = 题材 → 切到「世界」；填舞台段落 + 一条势力（readiness：任一非空即过），
    // 不点保存（脏表单）
    await openSetting(page, "世界");
    const stage = page.locator('[data-od-id="stage-input"]');
    await expect(stage).toBeVisible({ timeout: 10000 });
    await stage.fill("一座被沙漠包围的边境城邦");
    await page.locator('[data-od-id="fac-add"]').click();
    await page.locator(".fac-name").fill("丹阁");
    await page.locator(".fac-goal").fill("要为残卷讨一个说法，与城邦敌对");

    // 确认完成 → 应先自动保存（PUT /settings/world）再确认，并「确认即前进」到下一项（新顺序：世界→角色）
    const autoSave = page.waitForResponse(
      (r) => r.request().method() === "PUT" && r.url().includes("/settings/world"),
    );
    await page.locator(".panel-foot").getByRole("button", { name: "确认完成" }).click();
    await autoSave;
    await expect(
      page.locator(".settings-v main h2", { hasText: "角色" }),
    ).toBeVisible({ timeout: 5000 });

    // 后端直查：内容已落库（自动保存生效，契约 v2 形状）
    const world = await apiGetJSON(request, token, `/novels/${pid}/settings/world`);
    expect(world.stage).toContain("边境城邦");
    expect(world.factions[0].name).toBe("丹阁");
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

// -------------------------------------------------------------------------
// ⑤ 角色首进引导（character-bootstrap-from-intro）：简介已填 → 空态引导卡
//    两出口；手动建主角首卡默认「主角」；有名卡后 readiness 角色项即已填
// -------------------------------------------------------------------------
test("角色：首进引导卡 → 手动建主角 → 引导卡退场", async ({ page, request }) => {
  const { restore, token } = await setupSession(page);
  const auth = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
  try {
    const pid = await createNovel(page, `引导${Date.now() % 100000}`);
    // 先把 01 简介填上（readiness synopsis 就绪 → 角色页空态给 AI 出口）
    const putStory = await request.put(`${ORIGIN}/api/novels/${pid}/story`, {
      headers: auth,
      data: { synopsis: "杂役弟子林晚靠一双能看见修为漏洞的眼翻盘。" },
    });
    expect(putStory.ok()).toBeTruthy();
    // settingsStatus 在进书时取自 /readiness，PUT 后须重载工作台拿到新状态
    await page.reload();
    await expect(page.getByRole("button", { name: /^设定/ })).toBeVisible({ timeout: 10000 });

    await page.getByRole("button", { name: /^设定/ }).click();
    await openSetting(page, "角色");

    // 引导卡：AI 出口 + 手动出口，并存（AI 不点：本地栈无模型，门控提示属免费/模型路径）
    await expect(page.getByText("简介里已经有主角的线索了")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByRole("button", { name: "从简介立主角" })).toBeVisible();
    await expect(page.getByTestId("char-empty-guide")).toBeVisible();

    // 手动建主角：首卡默认「主角」
    await page.getByRole("button", { name: "手动建主角" }).click();
    await page.getByRole("textbox", { name: "角色名称" }).fill("林晚");
    await pollBackend(
      () => apiGetJSON(request, token, `/novels/${pid}/characters`),
      (l: { data?: { items?: Array<{ name: string; role: string }> } }) =>
        (l.data?.items ?? []).some((x) => x.name === "林晚" && x.role === "主角"),
    ); // 防抖 PATCH 落库（条件轮询替代固定 sleep）

    const list = await apiGetJSON(request, token, `/novels/${pid}/characters`);
    const item = (list.data?.items ?? []).find((x: { name: string }) => x.name === "林晚");
    expect(item).toBeTruthy();
    expect(item.role).toBe("主角");

    // 一张有名卡 → readiness 角色项不再报缺失（收紧口径的正向面）
    const ready = await apiGetJSON(request, token, `/novels/${pid}/readiness`);
    const keys = (ready.missing ?? []).map((m: { key: string }) => m.key);
    expect(keys).not.toContain("characters");

    // 引导卡退场：列表非空后进来直接是卷宗卡
    await page.reload();
    await page.getByRole("button", { name: /^设定/ }).click();
    await openSetting(page, "角色");
    await expect(page.getByTestId("char-empty-guide")).toHaveCount(0, { timeout: 10000 });
    await expect(page.getByRole("textbox", { name: "角色名称" })).toHaveValue("林晚");
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// ⑥ 认知体检：身心一致三问（cog-logical-levels）——好矛盾判达标、真冲突判矛盾
// -------------------------------------------------------------------------

test("角色体检：身心一致三问（好矛盾判达标、真冲突判矛盾）", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `体检${Date.now() % 100000}`);
    // AI 就绪态桩（ai-model + 配置清单）
    await page.route(`**/api/v1/novels/${pid}/ai-model`, (r) =>
      r.fulfill({
        json: {
          api_config_id: "c1",
          model: "gpt-4o",
          config_name: "主配置",
          ai_state: "ready",
          effective_model: "gpt-4o",
          reason: "ready",
          message: "",
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
            models: ["gpt-4o"],
            status: "active",
            last_test_status: "ok",
          },
        ],
      }),
    );

    await page.getByRole("button", { name: /^设定/ }).click();
    await openSetting(page, "角色");
    await page.getByRole("button", { name: "添加角色" }).click();
    const nameInput = page.getByRole("textbox", { name: "角色名称" });
    await nameInput.fill("林晚");
    await pollBackend(
      () => apiGetJSON(request, token, `/novels/${pid}/characters`),
      (l: { data?: { items?: Array<{ name: string }> } }) =>
        (l.data?.items ?? []).some((x) => x.name === "林晚"),
    ); // 末格 PATCH 落库（条件轮询替代固定 sleep）

    // 体检出参桩：9 项（含 3 组「想的和做的一致」，好矛盾判达标、真冲突判矛盾）
    const items = [
      { name: "简介 × 角色", status: "ok", note: "一致" },
      { name: "题材 × 角色", status: "ok", note: "调子对" },
      { name: "世界 × 能力上限", status: "ok", note: "在体系内" },
      { name: "世界 × 代价", status: "ok", note: "对得上" },
      { name: "势力 × 角色落地", status: "miss", note: "势力未填" },
      { name: "主线 × 角色", status: "miss", note: "主线未填" },
      {
        name: "人设与行事对得上吗",
        status: "ok",
        note: "好矛盾：安稳的人干着最玩命的活，是看点",
      },
      {
        name: "在乎的和会做的一致吗",
        status: "conflict",
        note: "真冲突：底线与手段打架了，二选一改",
      },
      { name: "他的处境和他的命对得上吗", status: "miss", note: "宿命未填" },
    ];
    await page.route(
      `**/api/novels/${pid}/settings/ai/characters/*/check`,
      (r) =>
        r.fulfill({
          json: { ok: true, data: { items, degraded: false, degraded_reasons: [], verdict: "两处看点，一处要改" } },
        }),
    );

    // 右栏点「一致性体检」→ char-ai-card 报告卡弹窗渲染 9 项，含大白话好矛盾/真冲突
    await page.locator('[data-aiact="check"]').click();
    const card = page.getByTestId("char-ai-card");
    await expect(card).toBeVisible({ timeout: 5000 });
    await expect(card).toContainText("人设与行事对得上吗");
    await expect(card).toContainText("好矛盾：安稳的人干着最玩命的活，是看点");
    await expect(card).toContainText("真冲突：底线与手段打架了，二选一改");
    await expect(card).toContainText("缺输入");
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// ⑦ 认知区提示（cog-logical-levels）：层头六问 hint 常显 + 展开自我观见 s5 格位 hint
//    认知区进不了像素基线（角色屏 parity 用例整体 skip、裁剪只覆盖三栏首屏），
//    这块的可见性由本用例兜（ADJUSTMENTS #25）。
// -------------------------------------------------------------------------
test("认知区提示：层头六问 hint + 展开自我观见 s5 格位 hint", async ({ page, request }) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `认知${Date.now() % 100000}`);
    await page.getByRole("button", { name: /^设定/ }).click();
    await openSetting(page, "角色");
    await page.getByRole("button", { name: "添加角色" }).click();
    await page.getByRole("textbox", { name: "角色名称" }).fill("林晚");
    await pollBackend(
      () => apiGetJSON(request, token, `/novels/${pid}/characters`),
      (l: { data?: { items?: Array<{ name: string }> } }) =>
        (l.data?.items ?? []).some((x) => x.name === "林晚"),
    ); // 末格 PATCH 落库（条件轮询替代固定 sleep）

    // 层头六问 hint：不展开即可见（抽验世界观/自我观两层，六层同源）
    await expect(page.getByText("他眼里的世界是什么样的？")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("他把自己当成谁？")).toBeVisible();

    // 展开「自我观」层 → s5 格位 hint 落在 label 下方（.cog-field 内的 .f-hint）
    await page
      .locator(".cog-layer", { hasText: "自我观" })
      .locator(".cog-layer-head")
      .click();
    await expect(
      page.locator(".cog-field", { hasText: "宿命认知观" }).locator(".f-hint"),
    ).toHaveText("他和这个世界到底是怎么回事？这条路走到头，他注定要面对什么？", {
      timeout: 5000,
    });
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// ⑧ 未命名卡可删除、可合并（#359 回归）：空名卡服务端存占位名（\u0000+uuid 段），
//    确认比对必须走 displayName 桶底——修复前 placeholder 会漏占位名、按钮永久 disabled。
//    真机路径兜住 vitest 覆盖不到的 UI 断链（vitest 只测词表与比对表达式）。
// -------------------------------------------------------------------------
test("角色：未命名卡可删除、可合并（占位名不进确认比对）", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `未命名${Date.now() % 100000}`);
    await page.getByRole("button", { name: /^设定/ }).click();
    await openSetting(page, "角色");

    // 连建两张不命名的卡（首张=主角，次张=配角；均为空名 → 后端占位名）
    await page.getByRole("button", { name: "添加角色" }).click();
    await page.waitForTimeout(1200);
    await page.getByRole("button", { name: "添加角色" }).click();
    await page.waitForTimeout(1200);

    const list = await apiGetJSON(request, token, `/novels/${pid}/characters`);
    expect(list.data.items.length).toBe(2);
    expect(
      list.data.items.every((x: { name: string }) => x.name.startsWith("\u0000")),
    ).toBe(true);

    // ── 删除当前选中的未命名卡（B）──
    await page.getByRole("button", { name: "删除", exact: true }).first().click();
    const confirmInput = page.getByPlaceholder(/输入「未命名」以确认/);
    await expect(confirmInput).toBeVisible({ timeout: 5000 }); // 修复前此处显示占位名，断言必红
    const delBtn = page.locator(".char-ops-panel.danger").getByRole("button", { name: "删除" });
    await expect(delBtn).toBeDisabled();
    await confirmInput.fill("错字");
    await expect(delBtn).toBeDisabled();
    await confirmInput.fill("未命名");
    await expect(delBtn).toBeEnabled(); // 修复前永久 disabled
    await delBtn.click();
    await expect
      .poll(
        async () => {
          const r = await apiGetJSON(request, token, `/novels/${pid}/characters`);
          return r.data.items.length;
        },
        { timeout: 5000 },
      )
      .toBe(1);

    // ── 再建一张未命名卡（C），合并进剩下的那张（A）──
    await page.getByRole("button", { name: "添加角色" }).click();
    await page.waitForTimeout(1200);
    const list2 = await apiGetJSON(request, token, `/novels/${pid}/characters`);
    expect(list2.data.items.length).toBe(2);
    const target = (list2.data.items as { id: string; name: string }[])[0];

    await page.getByRole("button", { name: "合并…" }).click();
    const mergeInput = page.getByPlaceholder(/输入「未命名」以确认/);
    await expect(mergeInput).toBeVisible({ timeout: 5000 });
    await page.getByLabel("合并到哪张卡").selectOption(target.id);
    const mergeBtn = page.locator(".char-ops-panel").getByRole("button", { name: "合并" });
    await expect(mergeBtn).toBeDisabled();
    await mergeInput.fill("未命名");
    await expect(mergeBtn).toBeEnabled();
    await mergeBtn.click();
    // 合并后只剩目标卡（服务端真值），撤销不收（本用例只钉「未命名也能操作」）
    await expect
      .poll(
        async () => {
          const r = await apiGetJSON(request, token, `/novels/${pid}/characters`);
          return r.data.items.length;
        },
        { timeout: 5000 },
      )
      .toBe(1);
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// ⑨ 一键立卡（c-char-ai-card-generic）：配角空卡右栏「一键立卡」行→出稿过目→
//    采纳只补空格走真后端（不建卡）；名字/人设齐后提示行退场；路人卡不给行。
//    出稿桩在页面层（本地栈无模型）；AI 就绪态桩同⑥。
// -------------------------------------------------------------------------
test("角色：一键立卡（配角）——右栏行→出稿→采纳只补空格", async ({ page, request }) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `立卡${Date.now() % 100000}`);
    // AI 就绪态桩（ai-model + 配置清单）
    await page.route(`**/api/v1/novels/${pid}/ai-model`, (r) =>
      r.fulfill({
        json: {
          api_config_id: "c1",
          model: "gpt-4o",
          config_name: "主配置",
          ai_state: "ready",
          effective_model: "gpt-4o",
          reason: "ready",
          message: "",
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
            models: ["gpt-4o"],
            status: "active",
            last_test_status: "ok",
          },
        ],
      }),
    );
    // 立卡出稿桩（采纳的 PATCH 走真后端，端点路径与响应形同主角链）
    await page.route("**/settings/ai/characters/bootstrap", (r) =>
      r.fulfill({
        json: {
          ok: true,
          data: {
            name: "周船工",
            aliases: ["老周"],
            persona: "渡口撑船三十年，认得每一道水纹。",
            cells: [
              { path: "dossier.look", value: "黝黑精瘦" },
              { path: "cog.v1", value: "攒钱换新船" },
            ],
            skipped: [],
          },
        },
      }),
    );

    await page.getByRole("button", { name: /^设定/ }).click();
    await openSetting(page, "角色");
    // 连建两张：首张主角（自动选中），次张配角（自动选中＝当前卡）
    await page.getByRole("button", { name: "添加角色" }).click();
    await page.waitForTimeout(1200);
    await page.getByRole("button", { name: "添加角色" }).click();
    await page.waitForTimeout(1200);

    // 配角空卡：卡区提示行与右栏「一键立卡」行同现
    await expect(page.getByTestId("char-ai-hint")).toBeVisible({ timeout: 10000 });
    const row = page.locator('[data-aiact="cardDraft"]');
    await expect(row).toBeVisible();

    await row.click();
    await expect(
      page.getByText("AI 拟稿 · 为「未命名」立卡（采纳才写入）"),
    ).toBeVisible({ timeout: 10000 });
    await page.getByRole("button", { name: "采纳 · 写入" }).click();

    // 采纳走真后端：名字落库、仍只有 2 张卡（不建卡）；轮询钉到 detail 的
    // 最后一格（列表只保证名字已落，中途采样会早退——首跑实锤过这个竞态）
    await pollBackend(
      () => apiGetJSON(request, token, `/novels/${pid}/characters`),
      (l: { data?: { items?: Array<{ name: string; role: string }> } }) =>
        (l.data?.items ?? []).some((x) => x.name === "周船工" && x.role === "配角"),
    );
    const list = await apiGetJSON(request, token, `/novels/${pid}/characters`);
    expect(list.data.items.length).toBe(2);
    const side = (list.data.items as Array<{ id: string; name: string }>).find(
      (x) => x.name === "周船工",
    );
    await pollBackend(
      () => apiGetJSON(request, token, `/novels/${pid}/characters/${side!.id}`),
      (d: { data?: { cog?: Record<string, string> } }) =>
        (d.data?.cog?.v1 ?? "") === "攒钱换新船",
    );
    const detail = await apiGetJSON(request, token, `/novels/${pid}/characters/${side!.id}`);
    expect(detail.data.persona).toBe("渡口撑船三十年，认得每一道水纹。");
    expect(detail.data.dossier.look).toBe("黝黑精瘦");
    expect(detail.data.cog.v1).toBe("攒钱换新船");

    // 名字/人设已齐 → 卡区提示行退场
    await expect(page.getByTestId("char-ai-hint")).toHaveCount(0, { timeout: 10000 });

    // 路人卡不给行：当前卡切成路人 → 行退场（与体检排除同口径）
    await page
      .getByRole("group", { name: "角色类型" })
      .getByRole("button", { name: "路人" })
      .click();
    await expect(page.locator('[data-aiact="cardDraft"]')).toHaveCount(0, { timeout: 10000 });
  } finally {
    await restore();
  }
});
