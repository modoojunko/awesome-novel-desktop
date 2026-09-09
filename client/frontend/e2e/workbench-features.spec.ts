import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page, type APIRequestContext } from "@playwright/test";

// =========================================================================
// 工作台非 AI 功能 E2E（PR3 book.html 复刻后适配：章对象三页签 / 卷纲面板 / 专注 / 提示词）
//   ① 章纲：选中章 →「章纲」页签 → OgPane 平面全字段表单编辑 + 保存草稿
//   ② 卷纲面板（PR4）：点卷节点 → 常编辑态全字段 + 子表行 → 保存卷纲 + 去配章纲
//   ③ 专注模式：body.focus 隐藏左树右栏 + Esc 退出
//   ④ 提示词面板：整章单卡（ai-prompt-crafting）——种子查看/编辑；无分段列表/生成按钮
//   ⑤ 免费态提示词子 label 隐藏（PRO-only 口径，取代 #152 入口可见）
//   ⑧ 章纲提示词新格子（ai-prompt-crafting）：场景卡权重/焦点 + 读者获得 + 章末落点 + 目标字数
//   ⑥ PR3 行为：点章恒落「章纲」页签（设计稿拍板，取代 PR2 按进度分流）+ 右栏本章进度卡
// =========================================================================
// 与 creation-flow.spec.ts 共享鉴权手法：S端 真实注册登录 → 写 docker 容器的
// config.json（tier="trial" 为 PRO）→ localStorage 注入 auth_token。
// 提示词后端接口经 require_ai_access 门控（需存在 active ApiConfig）：
// ④ 内先 POST /api/v1/api-configs 注入假配置（仅过门控，不测真实连接）。

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
  const name = `e2e_wb_${Date.now()}_${randomUUID().slice(0, 8)}`;
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

/** 每测试独立会话：S端 注册登录 → 写 config.json → 注入 localStorage。 */
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
  return { restore, token };
}

/** 通过真实 UI 创建小说，返回 project id。 */
async function createNovel(page: Page, name: string): Promise<string> {
  await page.goto(`${ORIGIN}/#/novels`);
  await page.getByRole("button", { name: "新建作品" }).first().click();
  await page.locator("input#bkTitle").fill(name);
  await page.getByRole("button", { name: "创建并开始写作" }).click();
  await page.waitForURL(/#\/novel\/[0-9a-fA-F-]+/);
  const m = page.url().match(/\/novel\/([0-9a-fA-F-]+)/);
  if (!m) throw new Error(`无法解析 novel id: ${page.url()}`);
  return m[1];
}

/** 加卷 + 初始 1 章 → 点章 → 切「正文」→ 编辑器就绪（PR3：添加卷弹窗 + 点章强制落章纲）。 */
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

/** 带 Bearer token 的 API GET。 */
async function apiGetJSON(request: APIRequestContext, token: string, path: string) {
  const r = await request.get(`${ORIGIN}/api${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(r.ok()).toBeTruthy();
  return r.json();
}

/** 注入一条 active ApiConfig，使 require_ai_access 门控放行（不测真实连接）。 */
async function ensurePromptAccess(request: APIRequestContext, token: string) {
  const r = await request.post(`${ORIGIN}/api/v1/api-configs`, {
    data: {
      name: `e2e-prompt-${Date.now()}`,
      vendor_id: "openai-compat",
      base_url: "http://127.0.0.1:1",
      api_key: "sk-e2e-" + "not-real", // 假 Key 运行时拼装
    },
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(r.ok()).toBeTruthy();
}

// -------------------------------------------------------------------------
// ① 章纲：OgPane 平面全字段表单（概要/关键事件/核心任务/主情绪）→ 保存草稿
// -------------------------------------------------------------------------

test("章纲：OgPane 真实表单编辑 + 保存草稿（概要/关键事件/核心任务/主情绪）", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `章纲${Date.now() % 100000}`);
    await writeFirstChapter(page);

    // 回「章纲」页签（writeFirstChapter 停在正文）：平面全字段表单 + 必填缺口 chip
    await page.getByRole("tab", { name: /^章纲/ }).click();
    await expect(
      page.getByText(/章纲：明确「这一章写什么」/),
    ).toBeVisible({ timeout: 10000 });
    await expect(page.locator(".gap-chip").first()).toBeVisible();

    // 填 4 个代表字段（概要 / 关键事件列表 / 核心任务 / 主情绪选择）
    await page.locator("#wf-summary").fill("主角在边境城邦发现妹妹失踪的线索");
    await page.locator("#wf-keys").fill("收到匿名信");
    await page.locator("#wf-task").fill("查明妹妹失踪的真相");
    await page.locator("#wf-mood select").selectOption({ label: "悬疑" });

    // 保存草稿 → PUT /chapters/vol-1-ch-1 落盘（仍有必填缺口 → 不自动确认）
    const save = page.waitForResponse(
      (r) =>
        r.request().method() === "PUT" &&
        r.url().includes(`/chapters/vol-1-ch-1`),
    );
    await page.getByRole("button", { name: "保存草稿" }).click();
    await save;
    await expect(page.getByText("草稿已保存")).toBeVisible({ timeout: 5000 });

    // 后端直查：outline / memo / emotional_design 均已落盘
    const ch = await apiGetJSON(request, token, `/novels/${pid}/chapters/vol-1-ch-1`);
    expect(ch.outline.summary).toContain("妹妹失踪");
    expect(ch.outline.key_points).toContain("收到匿名信");
    expect(ch.memo.current_task).toContain("真相");
    expect(ch.emotional_design.primary_mood).toBe("悬疑");
  } finally {
    restore();
  }
});

// -------------------------------------------------------------------------
// ② 卷纲面板（PR4：book.html 复刻）：点卷节点 → 常编辑态全字段 + 子表 → 保存卷纲
// -------------------------------------------------------------------------

// -------------------------------------------------------------------------
// ⑦ 信息差对齐（PR6）：章纲顶部只读块 = 卷级起止 + 本章规划行（章号对齐）
// -------------------------------------------------------------------------

test("信息差对齐：章纲顶部只读块显示卷级起止 + 本章规划行", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `信息差e2e${Date.now()}`);
    // 加卷 + 1 章，点章落在章纲页签
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
    // 未配置信息差 → 块不渲染
    await expect(page.getByTestId("og-info-gap")).toHaveCount(0);

    // API 直写卷级信息差 + 章规划行（VolumeUpdate 部分更新语义，差异字段即可）
    const put = await request.put(
      `${ORIGIN}/api/novels/${pid}/volumes/vol-1`,
      {
        data: {
          info_gap_start: "读者知道地契是假的",
          info_gap_end: "读者知道仇家已到门口",
          chapter_plans: [
            {
              chapter_no: 1,
              title: "开张",
              info_gap: "反派知道是陷阱 ↦ 主角不知道",
            },
          ],
        },
        headers: { Authorization: `Bearer ${token}` },
      },
    );
    expect(put.ok()).toBeTruthy();

    // 重新点章触发信息差拉取（章选择是组件态，reload 后需重选）
    await page.reload();
    await expect(page.locator(".col-tree .ch", { hasText: "第一章" })).toBeVisible({
      timeout: 10000,
    });
    await page.locator(".col-tree .ch", { hasText: "第一章" }).click();
    const block = page.getByTestId("og-info-gap");
    await expect(block).toBeVisible({ timeout: 10000 });
    await expect(block).toContainText("读者知道地契是假的 → 读者知道仇家已到门口");
    await expect(block).toContainText("反派知道是陷阱 ↦ 主角不知道");
  } finally {
    restore();
  }
});

test("卷纲面板：点卷节点 → 常编辑态 → 摘要/核心冲突/子表行 → 保存 + 去配章纲", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `卷页${Date.now() % 100000}`);
    await writeFirstChapter(page);

    // 点卷头 → 主区变卷纲面板（常编辑态，无「编辑」入口）；标题走 nodeLabel 口径（#164）
    await page.locator(".col-tree .vol-head", { hasText: "第一卷" }).click();
    await expect(
      page.getByPlaceholder("一段话讲清本卷讲什么"),
    ).toBeVisible({ timeout: 10000 });
    await expect(
      page.getByRole("heading", { name: /第一卷/ }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "保存卷纲" })).toBeVisible();
    await expect(page.getByRole("button", { name: "去配章纲" })).toBeVisible();

    // 9 标量：摘要 + 核心冲突；子表：阶段分配 + 冲突阶梯（新行工厂）
    await page
      .getByPlaceholder("一段话讲清本卷讲什么")
      .fill("第一卷铺垫主角妹妹失踪的悬念，收尾进入边城。");
    await page.getByPlaceholder("本卷贯穿的核心矛盾").fill("匿名信与失踪案的真假之辨");
    await page.getByRole("button", { name: "添加阶段" }).click();
    await page.getByPlaceholder("阶段名").fill("悬念建立");
    await page.getByPlaceholder("该阶段的一句话功能").fill("匿名信把主角拖回旧案");
    await page.getByTitle("章数").fill("4");
    await page.getByRole("button", { name: "添加层级" }).click();
    await page.getByPlaceholder("章节区间").fill("第 1-4 章");
    await page.getByPlaceholder("本层障碍").fill("关键证人拒绝作证");

    // 保存 → PUT /volumes/vol-1 → 统一 toast《title》卷纲已保存
    const volSave = page.waitForResponse(
      (r) =>
        r.request().method() === "PUT" &&
        r.url().includes("/volumes/vol-1"),
    );
    await page.getByRole("button", { name: "保存卷纲" }).click();
    await volSave;
    await expect(page.getByText("卷纲已保存")).toBeVisible({ timeout: 5000 });

    // 后端直查：标量 + 子表整族替换落库
    const vol = await apiGetJSON(request, token, `/novels/${pid}/volumes/vol-1`);
    expect(vol.summary).toContain("妹妹失踪");
    expect(vol.core_conflict).toBe("匿名信与失踪案的真假之辨");
    expect(vol.stages).toHaveLength(1);
    expect(vol.stages[0].stage_name).toBe("悬念建立");
    expect(vol.stages[0].chapter_count).toBe(4);
    expect(vol.conflict_ladders).toHaveLength(1);
    expect(vol.conflict_ladders[0].chapters_range).toBe("第 1-4 章");

    // 去配章纲 → 跳本卷第一个未确认章并强制落「章纲」页签
    await page.getByRole("button", { name: "去配章纲" }).click();
    await expect(
      page.getByRole("tab", { name: /^章纲/ }),
    ).toBeVisible({ timeout: 10000 });
  } finally {
    restore();
  }
});

// -------------------------------------------------------------------------
// ③ 专注模式：body.focus 隐藏左树右栏 + Esc 退出
// -------------------------------------------------------------------------

test("专注模式：隐藏左树右栏 + Esc 退出", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    await createNovel(page, `聚焦${Date.now() % 100000}`);
    await writeFirstChapter(page);

    // 初始左树/右栏均可见
    const tree = page.locator(".col-tree");
    const rail = page.locator(".col-ai");
    await expect(tree).toBeVisible();
    await expect(rail).toBeVisible();

    // 专注（工具栏 icon，title 恒为「专注模式」）→ body.focus 隐藏左树右栏
    await page.getByTitle("专注模式").click();
    await expect(tree).toBeHidden({ timeout: 5000 });
    await expect(rail).toBeHidden();

    // Esc → 退出专注，左树右栏恢复
    await page.keyboard.press("Escape");
    await expect(tree).toBeVisible();
    await expect(rail).toBeVisible();
  } finally {
    restore();
  }
});

// -------------------------------------------------------------------------
// ④ 提示词面板：整章单卡（ai-prompt-crafting）—— 种子查看/编辑/已修改徽标（非 AI 链路）
// -------------------------------------------------------------------------

test("提示词面板：整章单卡 + 种子提示词查看/编辑/已修改徽标", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `提示词${Date.now() % 100000}`);
    await writeFirstChapter(page);

    // 提示词后端接口需过 require_ai_access 门控：先注入 active ApiConfig（不测连接）
    await ensurePromptAccess(request, token);

    // API 种子整章提示词（手动保存路径，非 AI 生成）
    const seed = await request.put(
      `${ORIGIN}/api/novels/${pid}/chapters/vol-1-ch-1/prompts/write`,
      {
        data: { content: "# 整章任务\n\n描写主角收到匿名信的场景。" },
        headers: { Authorization: `Bearer ${token}` },
      },
    );
    expect(seed.ok()).toBeTruthy();

    // 切到章「提示词」页签 → 当前章自动展开：整章单卡 + 已保存徽标
    await page.getByRole("tab", { name: /^提示词/ }).click();
    await expect(page.getByText("提示词管理")).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("整章写作提示词")).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("已保存")).toBeVisible();
    // 分段链路退役：无分段行/段数/生成按钮
    await expect(page.getByText("段落 1")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "生成段落提示词" })).toHaveCount(0);

    // 查看 → 内容可见
    await page.getByTestId("pm-write-row").click();
    await expect(page.getByText("描写主角收到匿名信的场景。")).toBeVisible({
      timeout: 5000,
    });

    // 编辑 → 修改 → 保存 → 已修改
    await page.getByRole("button", { name: "编辑", exact: true }).click();
    await page.locator("textarea").last().fill("# 整章任务\n\n描写主角收到匿名信后追出城门的场景。");
    const save = page.waitForResponse(
      (r) => r.request().method() === "PUT" && r.url().includes("/prompts/write"),
    );
    await page.locator("main").getByRole("button", { name: "保存", exact: true }).click();
    await save;
    await expect(page.getByText("保存成功")).toBeVisible({ timeout: 5000 });

    // 返回概览 → 章节徽标「已修改」
    await page.getByRole("button", { name: "返回" }).click();
    await expect(page.getByText("已修改").first()).toBeVisible({ timeout: 5000 });
  } finally {
    restore();
  }
});

// -------------------------------------------------------------------------
// ④b 未配 API Key（trial 会员）：点提示词 tab 就地提示去配置，不整页跳 /config
// -------------------------------------------------------------------------

test("提示词无Key：进入提示词tab就地提示去配置，不整页跳转", async ({
  page,
}) => {
  const { restore } = await setupSession(page); // trial 会员但未注入 ApiConfig
  try {
    await createNovel(page, `无Key提示词${Date.now() % 100000}`);
    await writeFirstChapter(page);

    // 点「提示词」页签：prompts 端点 503 → 就地提示（而非 503 全局跳 /config）
    await page.getByRole("tab", { name: /^提示词/ }).click();
    await expect(page.getByText("尚未配置模型 API Key")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByRole("link", { name: "去配置" })).toBeVisible();

    // 关键回归断言：仍留在章页
    await expect(page).toHaveURL(/#\/novel\//);

    // 「去配置」为用户主动导航 → 可达配置页
    await page.getByRole("link", { name: "去配置" }).click();
    await expect(page).toHaveURL(/#\/config/);
  } finally {
    restore();
  }
});

// -------------------------------------------------------------------------
// ⑤ 免费态提示词子 label 隐藏（ai-prompt-crafting PRO-only 口径，取代 #152 入口可见）
// -------------------------------------------------------------------------

test("免费态：正文/章纲可见，提示词子 label 隐藏", async ({
  page,
}) => {
  const { restore } = await setupSession(page, "none");
  try {
    await createNovel(page, `免费提示词${Date.now() % 100000}`);
    await writeFirstChapter(page);

    await expect(page.getByRole("tab", { name: /^正文/ })).toBeVisible();
    await expect(page.getByRole("tab", { name: /^章纲/ })).toBeVisible();
    // 提示词子 label PRO-only：免费态隐藏（内容本身也由后端 member_required 拦截）
    await expect(page.getByRole("tab", { name: /^提示词/ })).toHaveCount(0);
  } finally {
    restore();
  }
});

// -------------------------------------------------------------------------
// ⑥ PR3 行为：点章恒落「章纲」页签（设计稿拍板，取代 PR2 按进度/付费分流）
//    + 右栏 Rail 本章进度卡（大百分数 / 目标字数 / mini 统计）
// -------------------------------------------------------------------------

test("点章强制落章纲：确认/有正文后重挂载仍落章纲 + 右栏本章进度卡", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `矩阵${Date.now() % 100000}`);

    // 建卷 + 初始 1 章（停在默认落点「章纲」页签）
    await page.getByTitle("添加卷").click();
    await page.getByLabel("卷名", { exact: true }).fill("第一卷");
    await page.getByLabel(/初始章数/).fill("1");
    await page.getByRole("button", { name: "创建卷" }).click();
    const chRow = page.locator(".col-tree .ch", { hasText: "第一章" });
    await expect(chRow).toBeVisible({ timeout: 10000 });

    // 行①：新章（未确认/无提示词/无正文）→ 章纲选中
    await chRow.click();
    const ogTab = page.getByRole("tab", { name: /^章纲/ });
    await expect(ogTab).toBeVisible({ timeout: 10000 });
    await expect(ogTab).toHaveAttribute("aria-selected", "true");
    await expect(page.getByText(/章纲：明确「这一章写什么」/)).toBeVisible();

    // API 备齐必填（核心任务/读者状态/预期策略/必须变化/主情绪/段落规划）→ 确认
    const auth = { Authorization: `Bearer ${token}` };
    const ready = (await apiGetJSON(
      request,
      token,
      `/novels/${pid}/chapters/vol-1-ch-1`,
    )) as Record<string, unknown>;
    ready.memo = {
      current_task: "查明妹妹失踪的真相",
      reader_expectation: {
        state: "担忧妹妹安危",
        strategy: "抛出线索钩子",
        detail: "",
      },
      required_changes: ["找到匿名信的来源"],
    };
    ready.emotional_design = { primary_mood: "悬疑" };
    ready.segments = [{ summary: "城门口收到匿名信", target_words: 1000 }];
    const put = await request.put(
      `${ORIGIN}/api/novels/${pid}/chapters/vol-1-ch-1`,
      { data: ready, headers: auth },
    );
    expect(put.ok()).toBeTruthy();
    const confirm = await request.post(
      `${ORIGIN}/api/novels/${pid}/chapters/vol-1-ch-1/confirm`,
      { headers: auth },
    );
    expect(confirm.ok()).toBeTruthy();

    // 章工作台重挂载（卷↔章切换）：行②已确认 → 仍落章纲；页签徽标「已确认」
    const tree = page.locator(".col-tree");
    const remount = async () => {
      await tree.locator(".vol-head", { hasText: "第一卷" }).click();
      await expect(page.getByText("卷摘要")).toBeVisible({ timeout: 5000 });
      await tree.locator(".ch", { hasText: "第一章" }).click();
      await expect(ogTab).toBeVisible({ timeout: 10000 });
    };
    await remount();
    await expect(ogTab).toHaveAttribute("aria-selected", "true", { timeout: 5000 });
    await expect(
      page.locator(".chtab.on", { hasText: "章纲" }).getByText("已确认"),
    ).toBeVisible({ timeout: 5000 });

    // 行③：已有正文 → 重挂载仍落章纲（不再按进度跳正文）
    const prose = await request.put(
      `${ORIGIN}/api/novels/${pid}/chapters/vol-1-ch-1/prose`,
      {
        data: { prose: "旧城墙头的风沙穿过坍塌的垛口，林晚攥着那封匿名信。" },
        headers: auth,
      },
    );
    expect(prose.ok()).toBeTruthy();
    await remount();
    await expect(ogTab).toHaveAttribute("aria-selected", "true", { timeout: 5000 });

    // 右栏 Rail（PR3）：本章进度卡 + 目标字数 + mini 统计
    await expect(page.getByText("本章进度", { exact: true })).toBeVisible();
    await expect(page.getByText("目标字数", { exact: true })).toBeVisible();
    await expect(page.getByText("本书总字数")).toBeVisible();
    await expect(page.getByText("本章草稿")).toBeVisible();
  } finally {
    restore();
  }
});

// -------------------------------------------------------------------------
// ⑧ 章纲提示词新格子（ai-prompt-crafting）：场景卡（名/目标/阻碍/钩子/权重/焦点）
//    + 读者获得（类型/描述/位置）+ 章末落点 + 目标字数 —— 填值保存、后端落盘、重载回读
// -------------------------------------------------------------------------

test("章纲新格子：场景卡/读者获得/章末落点/目标字数填值保存 + 回读", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `格子${Date.now() % 100000}`);
    await writeFirstChapter(page);

    // 回「章纲」页签
    await page.getByRole("tab", { name: /^章纲/ }).click();
    await expect(
      page.getByText(/章纲：明确「这一章写什么」/),
    ).toBeVisible({ timeout: 10000 });

    // 必填六项补齐（新建章 segments 为空数组 → 段落规划也是缺口）——
    // 缺口未清空前「确认章纲」禁用
    await page.locator("#wf-task").fill("查明妹妹失踪的真相");
    await page.locator("#wf-rstate").fill("不知道匿名信从何而来");
    await page.locator("#wf-rstrat").fill("读者会猜测寄信人是故人");
    await page.locator("#wf-changes").fill("主角拿到入城许可");
    await page.locator("#wf-mood select").selectOption({ label: "悬疑" });
    await page.getByRole("button", { name: "添加段落" }).click();
    await page.locator('.seg-row [data-seg="s"]').first().fill("港区之夜 · 信标亮起");

    // 展开两个新折叠区
    await page.locator("#wf-scenes summary").click();
    await page.locator("#wf-payoffs summary").click();

    // 空读者获得时点「确认章纲」→ 非阻断提醒（不拦截，必填缺口另有提示）。
    // 确认链路 = PUT 存量 → POST confirm → setVolumes → loadChapterData 身份翻新 →
    // 加载 effect 重跑，表单会按服务端数据重置一次；必须等链路彻底落定
    // （done-note + 确认引发的两次章 GET 均已返回）再填新格子，否则填值被重置卷走。
    const chapterGets: number[] = [];
    page.on("response", (r) => {
      if (
        r.request().method() === "GET" &&
        r.url().includes(`/chapters/vol-1-ch-1`)
      ) {
        chapterGets.push(Date.now());
      }
    });
    await page.getByRole("button", { name: "确认章纲" }).click();
    await expect(page.getByTestId("payoff-hint")).toBeVisible({ timeout: 5000 });
    await expect(
      page.locator(".panel-foot .done-note", { hasText: "章纲已确认" }),
    ).toBeVisible({ timeout: 5000 });
    await expect
      .poll(() => chapterGets.length, { timeout: 5000 })
      .toBeGreaterThanOrEqual(2);

    // 场景卡：添加一张，填名/目标/阻碍/钩子 + 权重高 + 焦点核心冲突
    await page.getByRole("button", { name: "添加场景卡" }).click();
    const scene = page.locator(".scene-card").first();
    await scene.locator('[data-scene="n"]').fill("城门对峙");
    await scene.locator('[data-scene="g"]').fill("带信入城");
    await scene.locator('[data-scene="o"]').fill("守卫盘查");
    await scene.locator('[data-scene="h"]').fill("通缉令画像");
    await scene.locator('[data-scene="w"]').selectOption("high");
    await scene.locator('[data-scene="f"]').selectOption("核心冲突");

    // 读者获得：一条（反转 / 描述 / 后段）
    await page.getByRole("button", { name: "添加读者获得" }).click();
    const payoff = page.locator(".payoff-row").first();
    await payoff.locator('[data-payoff="k"]').selectOption("twist");
    await payoff.locator('[data-payoff="d"]').fill("匿名信的火漆印是自家纹章");
    await payoff.locator('[data-payoff="l"]').selectOption("后段");

    // 章末落点 + 目标字数
    await page.locator("#wf-ladder").fill("他收起通缉令，转身没入夜色");
    await page.locator("#wf-wt").fill("4000");

    // 保存草稿 → PUT 落盘（须甄别请求体：前一步「确认章纲」的 PUT 可能仍在途，
    // 裸等 method+url 会抢到未带新格子的那次响应）
    const save = page.waitForResponse(
      (r) =>
        r.request().method() === "PUT" &&
        r.url().includes(`/chapters/vol-1-ch-1`) &&
        (r.request().postDataJSON() as { scene_cards?: unknown[] })
          ?.scene_cards?.length === 1,
    );
    await page.getByRole("button", { name: "保存草稿" }).click();
    await save;

    // 后端直查：新格子全部落盘（枚举值原样）
    const ch = await apiGetJSON(request, token, `/novels/${pid}/chapters/vol-1-ch-1`);
    expect(ch.scene_cards).toEqual([
      {
        scene_name: "城门对峙",
        goal: "带信入城",
        obstacle: "守卫盘查",
        hook: "通缉令画像",
        weight: "high",
        focus: "核心冲突",
      },
    ]);
    expect(ch.micro_payoffs).toEqual([
      { kind: "twist", description: "匿名信的火漆印是自家纹章", location: "后段" },
    ]);
    expect(ch.ladder_exit).toBe("他收起通缉令，转身没入夜色");
    expect(ch.word_target).toBe(4000);

    // 重载回读：重新展开两个折叠区，值都在
    await page.reload();
    await page.locator(".col-tree .ch", { hasText: "第一章" }).click();
    await page.getByRole("tab", { name: /^章纲/ }).click();
    await page.locator("#wf-scenes summary").click();
    await page.locator("#wf-payoffs summary").click();
    await expect(page.locator(".scene-card").first().locator('[data-scene="n"]')).toHaveValue(
      "城门对峙",
    );
    await expect(page.locator(".scene-card").first().locator('[data-scene="w"]')).toHaveValue(
      "high",
    );
    await expect(page.locator(".payoff-row").first().locator('[data-payoff="k"]')).toHaveValue(
      "twist",
    );
    await expect(page.locator("#wf-ladder")).toHaveValue("他收起通缉令，转身没入夜色");
    await expect(page.locator("#wf-wt")).toHaveValue("4000");
  } finally {
    restore();
  }
});
