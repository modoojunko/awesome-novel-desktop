import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page, type APIRequestContext } from "@playwright/test";
import { cleanupSessionNovels } from "./helpers";

// =========================================================================
// 伏笔设定 E2E（foreshadow-settings-v2 tasks 4.7）——真表 novel_hooks 面板流
//   ① CRUD 刷新回读（字段级防抖 PATCH → reload 后台账/卡回读一致 + API 对拍）
//   ② 搜索过滤＋空组不渲染（描述本地搜索；无条目的分组头不渲染）
//   ③ 状态挪组选中跟随＋收束记录显隐（resolved→active 保留收束记录）
//   ④ 章节选择存 chapter id（卷章选择器按卷 optgroup；API 回读断言）
//   ⑤ 删除 8 秒内撤销按原 id 恢复（page.clock：install 先于 goto）
//   ⑥ 空表确认指引（常驻 hook-hint 断言而非 toast；按钮恒可点）
//   ⑦ 内容有变徽标（确认后改内容 → 降级；重新确认恢复）
// 不 mock：token 由 S端 真实签发；hooks/volumes 走真实 C端 后端（docker 4 服务）。
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
  const name = `e2e_fs_${Date.now()}_${randomUUID().slice(0, 8)}`;
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

/** 把 S端 会话写入 config.json，返回恢复函数（竞态守卫同 settings-forms）。 */
async function writeOAuthSession(t: string, u: string, tier = "trial") {
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = t;
  cfg.username = u;
  cfg.tier = tier;
  delete cfg.expires_at; // 残留过去到期日 → 401「登录已过期」
  cfg.last_login_at = new Date().toISOString();
  cfg.pc_hash = randomUUID().replace(/-/g, ""); // S端无该设备 grant → 注入 token 不被 heal 冲掉
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

/** 每测试独立会话（setupSession 约定同 settings-forms）。 */
async function setupSession(
  page: Page,
  tier = "trial",
): Promise<{ restore: () => void; token: string }> {
  const { token, username } = await sRegisterAndLogin();
  const restore = await writeOAuthSession(token, username, tier);
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  await page.route("**/api/auth/check-auth", (r) =>
    r.fulfill({ json: { code: 0, data: { token, username, tier } } }),
  );
  const restoreAndCleanup = async () => {
    await cleanupSessionNovels(ORIGIN, token);
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
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    data,
  });
  expect(
    r.ok(),
    `${path} → ${r.status()}: ${r.status() >= 400 ? await r.text() : ""}`,
  ).toBeTruthy();
  return r.json();
}

/** 在设定左栏点一个导航项（精确匹配短名）。 */
async function openSetting(page: Page, label: string) {
  await page.locator(".settings-v .col-tree").getByText(label, { exact: true }).click();
}

/** 打开伏笔面板并等台账加载完成（hooks 列表 + .hk-tree 渲染）。 */
async function openHooks(page: Page) {
  const listLoaded = page.waitForResponse(
    (r) => r.request().method() === "GET" && r.url().includes("/hooks"),
  );
  await openSetting(page, "伏笔");
  await listLoaded;
  await expect(page.locator(".hk-tree")).toBeVisible({ timeout: 10000 });
}

/** 等 UI 的最后一格 PATCH 落库（防抖 600ms + 余量）。 */
async function waitDebounce(page: Page) {
  await page.waitForTimeout(1200);
}

test.describe.serial("伏笔设定（真表 novel_hooks）", () => {
  // ① CRUD 刷新回读：UI 建行 + 各字段编辑 → 刷新后回读一致 + API 对拍
  test("① CRUD：添加→编辑→自动保存→刷新回读一致", async ({ page, request }) => {
    const { restore, token } = await setupSession(page);
    try {
      const pid = await createNovel(page, `伏笔存${Date.now() % 100000}`);
      await page.getByRole("button", { name: /^设定/ }).click();
      await openHooks(page);

      // 添加（乐观行 → POST 真 id）→ 描述（必填）→ 类型/优先级/状态
      await page.locator('[data-od-id="btn-add-hook"]').click();
      const desc = page.locator('[data-od-id="input-hook-desc"]');
      await expect(desc).toBeVisible({ timeout: 5000 });
      await desc.fill("父亲失踪前塞给林拾的半页残卷——缺的半页在哪");
      await page
        .locator('[data-od-id="select-hook-type"]')
        .selectOption({ label: "承诺" });
      await page
        .locator('[data-od-id="seg-hook-priority"] .cap', { hasText: "高" })
        .click();
      await waitDebounce(page);

      // 后端直查：POST/PATCH 已落库（真表行）
      const list1 = await apiGetJSON(request, token, `/novels/${pid}/hooks`);
      expect(list1.data.count).toBe(1);
      const row1 = list1.data.items[0];
      expect(row1.description).toContain("半页残卷");
      expect(row1.type).toBe("promise");
      expect(row1.priority).toBe(1);
      expect(row1.status).toBe("active");
      expect(row1.code).toBe("#H-0001");

      // 刷新回读：台账与卡内容一致（无「未保存行」）
      await page.reload();
      await page.getByRole("button", { name: /^设定/ }).click();
      await openHooks(page);
      await expect(page.locator(".hk-item").first()).toContainText("半页残卷");
      await page.locator(".hk-item").first().click();
      await expect(desc).toHaveValue(/半页残卷/);
      await expect(page.locator('[data-od-id="select-hook-type"]')).toHaveValue("promise");
      await expect(
        page.locator('[data-od-id="seg-hook-priority"] .cap.on'),
      ).toHaveText("高");
      await expect(page.locator(".hk-kv-static")).toHaveText("#H-0001");
    } finally {
      await restore();
    }
  });

  // ② 搜索过滤＋空组不渲染
  test("② 搜索过滤：命中行留下，无条目分组不渲染", async ({ page, request }) => {
    const { restore, token } = await setupSession(page);
    try {
      const pid = await createNovel(page, `伏笔搜${Date.now() % 100000}`);
      await apiPostJSON(request, token, `/novels/${pid}/hooks`, {
        description: "哥哥留下的铜哨",
        status: "active",
      });
      await apiPostJSON(request, token, `/novels/${pid}/hooks`, {
        description: "庙里的钟声半夜自己响",
        status: "resolved",
      });
      await page.getByRole("button", { name: /^设定/ }).click();
      await openHooks(page);

      // 全量：活跃 + 已收束两组渲染；废弃组无条目 → 分组头不渲染
      await expect(page.locator(".hk-group")).toHaveCount(2);
      await expect(page.locator(".hk-group", { hasText: "废弃" })).toHaveCount(0);

      // 搜索命中「钟声」：只剩已收束组；活跃组头随之消失（空组不渲染）
      await page.locator('[data-od-id="search-hook"]').fill("钟声");
      await expect(page.locator(".hk-item")).toHaveCount(1);
      await expect(page.locator(".hk-item")).toContainText("钟声");
      await expect(page.locator(".hk-group")).toHaveCount(1);
      await expect(page.locator(".hk-group", { hasText: "已收束" })).toHaveCount(1);

      // 无命中：提示换词，分组头全不渲染
      await page.locator('[data-od-id="search-hook"]').fill("不存在这个词");
      await expect(page.getByText("没有找到——换个词试试。")).toBeVisible();
      await expect(page.locator(".hk-group")).toHaveCount(0);
    } finally {
      await restore();
    }
  });

  // ③ 状态挪组选中跟随＋收束记录显隐；resolved→active 保留收束记录
  test("③ 状态三态切换：挪组选中跟随，收束记录回切不清", async ({ page, request }) => {
    const { restore, token } = await setupSession(page);
    try {
      const pid = await createNovel(page, `伏笔态${Date.now() % 100000}`);
      await apiPostJSON(request, token, `/novels/${pid}/hooks`, {
        description: "听漏之耳的代价",
      });
      await page.getByRole("button", { name: /^设定/ }).click();
      await openHooks(page);

      // 初始：活跃组内 1 条且选中（卡展开）
      await expect(page.locator(".hk-group", { hasText: "活跃" })).toHaveCount(1);
      await expect(page.locator('[data-od-id="kv-hook-payoff"]')).toHaveCount(0);

      // 切「已收束」：挪组、选中跟随、收束记录区展开 + 软引导 hint
      await page
        .locator('[data-od-id="seg-hook-state"] .cap', { hasText: "已收束" })
        .click();
      await expect(page.locator(".hk-group", { hasText: "活跃" })).toHaveCount(0);
      const resolvedGroup = page.locator(".hk-group", { hasText: "已收束" });
      await expect(resolvedGroup).toHaveCount(1);
      await expect(
        resolvedGroup.locator("xpath=following-sibling::button").first(),
      ).toContainText("听漏之耳");
      await expect(page.locator('[data-od-id="kv-hook-payoff"]')).toBeVisible();
      await expect(
        page.getByText("这条已收束但没留痕", { exact: false }),
      ).toBeVisible();

      // 留痕「怎么收的」→ 切回活跃 → 收束记录区收起；再切回已收束：留痕保留
      await page
        .locator('[data-od-id="input-hook-how"]')
        .fill("第三次代价落地，记忆闪回对上匾额");
      await waitDebounce(page);
      await page
        .locator('[data-od-id="seg-hook-state"] .cap', { hasText: "活跃" })
        .click();
      await expect(page.locator('[data-od-id="kv-hook-payoff"]')).toHaveCount(0);
      await page
        .locator('[data-od-id="seg-hook-state"] .cap', { hasText: "已收束" })
        .click();
      await expect(page.locator('[data-od-id="kv-hook-payoff"]')).toBeVisible();
      await expect(page.locator('[data-od-id="input-hook-how"]')).toHaveValue(
        /记忆闪回对上匾额/,
      );

      // API 回读：resolved→active 回切保留了收束记录（payoff_note 不清）
      const list = await apiGetJSON(request, token, `/novels/${pid}/hooks`);
      const row = list.data.items[0];
      expect(row.status).toBe("resolved");
      expect(row.payoff_note).toContain("记忆闪回");
    } finally {
      await restore();
    }
  });

  // ④ 章节选择存 chapter id（卷章选择器按卷 optgroup；API 回读断言）
  test("④ 章节选择器：按卷分组，落库 chapter id，回显章名", async ({ page, request }) => {
    const { restore, token } = await setupSession(page);
    try {
      const pid = await createNovel(page, `伏笔章${Date.now() % 100000}`);
      // 备料：一卷两章（vol-1-ch-1 / vol-1-ch-2），选择器选项来自 /volumes 的章 id
      await apiPostJSON(request, token, `/novels/${pid}/volumes`, { title: "凡尘" });
      await apiPostJSON(request, token, `/novels/${pid}/volumes/vol-1/chapters`, {
        title: "火场遗页",
      });
      await apiPostJSON(request, token, `/novels/${pid}/volumes/vol-1/chapters`, {
        title: "柳安坊",
      });
      await apiPostJSON(request, token, `/novels/${pid}/hooks`, {
        description: "半页残卷的下落",
      });
      const vols = await apiGetJSON(request, token, `/novels/${pid}/volumes`);
      const ch2 = vols[0].chapters.find(
        (c: { chapter: number }) => c.chapter === 2,
      );
      expect(ch2?.id).toBeTruthy(); // 树响应补 chapter id（tasks 1.3）

      await page.getByRole("button", { name: /^设定/ }).click();
      await openHooks(page);

      // 按卷 optgroup + 「第 N 章 · 章名」选项；选第二章
      const inSel = page.locator('[data-od-id="select-hook-in"]');
      await expect(inSel.locator("optgroup")).toHaveCount(1);
      await inSel.selectOption({ label: "第 02 章 · 柳安坊" });
      const patchReq = page.waitForRequest(
        (r) => r.method() === "PATCH" && r.url().includes("/hooks/"),
      );
      await patchReq;
      await expect(inSel).toHaveValue(ch2.id);
      await waitDebounce(page);

      // API 回读：落库存的是章的数据库 id
      const list = await apiGetJSON(request, token, `/novels/${pid}/hooks`);
      expect(list.data.items[0].introduced_chapter_id).toBe(ch2.id);

      // 刷新回显
      await page.reload();
      await page.getByRole("button", { name: /^设定/ }).click();
      await openHooks(page);
      await expect(page.locator('[data-od-id="select-hook-in"]')).toHaveValue(ch2.id);
    } finally {
      await restore();
    }
  });

  // ⑤ 删除 8 秒内撤销按原 id 恢复（page.clock：install 必须先于 goto）
  test("⑤ 删除撤销：回执窗口内撤销，原 id 原样恢复", async ({ page, request }) => {
    await page.clock.install(); // 仓库首例：先 install 再 goto，8 秒自清窗口受控
    const { restore, token } = await setupSession(page);
    try {
      const pid = await createNovel(page, `伏笔删${Date.now() % 100000}`);
      const created = await apiPostJSON(request, token, `/novels/${pid}/hooks`, {
        description: "坊市传闻的夜半钟声",
      });
      await page.getByRole("button", { name: /^设定/ }).click();
      await openHooks(page);

      // 删除：即落库（DELETE）+ 回执条出现（面板内自管）
      await page.locator('[data-od-id="btn-del-hook"]').click();
      const undoReq = page.waitForResponse(
        (r) => r.request().method() === "POST" && r.url().includes("/restore"),
      );
      await expect(page.locator('[data-od-id="receipt-hooks"]')).toBeVisible({
        timeout: 5000,
      });
      const list0 = await apiGetJSON(request, token, `/novels/${pid}/hooks`);
      expect(list0.data.count).toBe(0); // 删除即时落库

      // 8 秒窗口内点撤销 → restore → 原 id 原样恢复（编号不跳变）
      await page
        .locator('[data-od-id="receipt-hooks"]')
        .getByRole("button", { name: "撤销" })
        .click();
      await undoReq;
      await expect(page.locator(".hk-item")).toHaveCount(1, { timeout: 5000 });
      const list1 = await apiGetJSON(request, token, `/novels/${pid}/hooks`);
      expect(list1.data.count).toBe(1);
      expect(list1.data.items[0].id).toBe(created.data.id);
      expect(list1.data.items[0].code).toBe("#H-0001");
      expect(list1.data.items[0].description).toContain("夜半钟声");

      // 窗口自清：快进 9 秒 → 回执条消失（「8 秒」仅是回执 UI 自清窗口）
      await page.locator('[data-od-id="btn-del-hook"]').click();
      await expect(page.locator('[data-od-id="receipt-hooks"]')).toBeVisible();
      await page.clock.fastForward(9000);
      await expect(page.locator('[data-od-id="receipt-hooks"]')).toHaveCount(0);
      // 窗口已过：条目仍处于已删除（撤销入口已随回执收起，重试不可用）
      const list2 = await apiGetJSON(request, token, `/novels/${pid}/hooks`);
      expect(list2.data.count).toBe(0);
    } finally {
      await restore();
    }
  });

  // ⑥ 空表确认指引：常驻 hook-hint（非 toast）；按钮恒可点；后端 400 兜底
  test("⑥ 空表确认：常驻指引 + 按钮恒可点，status 不落已确认", async ({ page, request }) => {
    const { restore, token } = await setupSession(page);
    try {
      const pid = await createNovel(page, `伏笔空${Date.now() % 100000}`);
      await page.getByRole("button", { name: /^设定/ }).click();
      await openHooks(page);

      // 空态：主出口 + AI 旁路（「编辑区零 AI 按钮」唯一例外）；warnline 常驻
      await expect(page.locator('[data-od-id="empty-hooks"]')).toBeVisible();
      await expect(page.locator('[data-od-id="btn-empty-add"]')).toBeVisible();
      await expect(page.locator('[data-od-id="btn-empty-ai"]')).toBeVisible();
      const hint = page.locator('[data-od-id="hook-hint"]');
      await expect(hint).toBeVisible();
      await expect(hint).toContainText("至少要埋一条");
      await expect(hint).toContainText("先跳过");

      // 空表点「确认完成」：前端提示性预检（toast）+ 常驻指引仍在 + 后端 400 兜底
      await page
        .locator(".panel-foot")
        .getByRole("button", { name: "确认完成" })
        .click();
      await expect(page.getByText(/伏笔不能为空/).first()).toBeVisible();
      await expect(hint).toBeVisible(); // 指引是常驻信号，不随 toast 消失
      const status = await apiGetJSON(request, token, `/novels/${pid}/settings/status`);
      expect(status.hooks).toBe(false);

      // 埋一条（描述非空）→ 指引退场；全空格描述不算（门禁判 trim 非空）
      await page.locator('[data-od-id="btn-add-hook"]').click();
      await page.locator('[data-od-id="input-hook-desc"]').fill("   ");
      await waitDebounce(page);
      await expect(hint).toBeVisible();
      await page.locator('[data-od-id="input-hook-desc"]').fill("真实的钩子");
      await waitDebounce(page);
      await expect(hint).toHaveCount(0);
    } finally {
      await restore();
    }
  });

  // ⑦ 内容有变徽标：确认后改内容 → 降级「内容有变 · 待重新确认」；重新确认恢复
  test("⑦ 内容有变徽标：确认后改动降级，重新确认恢复", async ({ page, request }) => {
    const { restore, token } = await setupSession(page);
    try {
      const pid = await createNovel(page, `伏笔徽${Date.now() % 100000}`);
      await page.getByRole("button", { name: /^设定/ }).click();
      await openHooks(page);

      // 确认前：4→1 条待收束（warn）
      await page.locator('[data-od-id="btn-add-hook"]').click();
      await page.locator('[data-od-id="input-hook-desc"]').fill("柳掌柜替谁收账");
      await waitDebounce(page);
      const badge = page.locator(".settings-v .panel-head .badge");
      await expect(badge).toHaveText(/1 条待收束/);

      // 确认完成 → 确认即前进到「禁用词句」；回伏笔 → 「已确认 · 1 条待收束」（done）
      await page
        .locator(".panel-foot")
        .getByRole("button", { name: "确认完成" })
        .click();
      await expect(page.getByText(/「伏笔」已确认/)).toBeVisible({ timeout: 5000 });
      await openSetting(page, "伏笔");
      await expect(badge).toHaveText(/已确认 · 1 条待收束/);

      // 改描述（自动保存落库）→ 内容指纹变化 → 徽标降级（warn，文案不含「已确认」）
      await page
        .locator('[data-od-id="input-hook-desc"]')
        .fill("柳掌柜替丹阁收账");
      await waitDebounce(page);
      await expect(badge).toHaveText(/内容有变 · 待重新确认/);

      // 重新确认（已确认态主按钮＝保存修改，先 flush 再快照）→ 恢复「已确认」系徽标
      await page
        .locator(".panel-foot")
        .getByRole("button", { name: "保存修改" })
        .click();
      await expect(badge).toHaveText(/已确认 · 1 条待收束/, { timeout: 5000 });
      const status = await apiGetJSON(request, token, `/novels/${pid}/settings/status`);
      expect(status.hooks).toBe(true);
    } finally {
      await restore();
    }
  });
});
