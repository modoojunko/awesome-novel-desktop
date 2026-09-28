import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page, type APIRequestContext } from "@playwright/test";
import { addFirstChapterViaTree, cleanupSessionNovels, stableClick, writeFirstChapter } from "./helpers";

// =========================================================================
// 工作台非 AI 功能 E2E（PR3 book.html 复刻后适配：章对象三页签 / 卷纲面板 / 专注 / 提示词）
//   ① 章纲：选中章 →「章纲」页签 → OgPane 平面全字段表单编辑 + 保存草稿
//   ② 卷纲（c-volume-antagonist）：点卷节点 → 四问一页纸查看态 → 编辑态四问＋坎 → 保存卷纲
//   ③ 专注模式：body.focus 隐藏左树右栏 + Esc 退出
//   ④ 提示词：页签退役（c-prompt-tab-retire）——弹窗查看/编辑/存为本章提示词
//   ⑤ 提示词页签全档退役（含免费态）；无Key 走弹窗就地报错
//   ⑧ 章纲提示词格子：读者获得 + 章末落点 + 目标字数（c-og-slim-v2：场景卡退役）
//   ⑥ PR3 行为：点章恒落「章纲」页签（设计稿拍板，取代 PR2 按进度分流）+ 右栏本章进度卡
// =========================================================================
// 与 creation-flow.spec.ts 共享鉴权手法：S端 真实注册登录 → 写 docker 容器的
// config.json（tier="trial" 为 PRO）→ localStorage 注入 auth_token。
// 提示词后端接口经 require_ai_access 门控（需存在 active ApiConfig）：
// ④ 内先 POST /api/v1/api-configs 注入假配置（仅过门控，不测真实连接）。

// 隔离栈可参数化（per-session 规则：自己的 S端端口/数据目录；默认仍是主栈口径）
const S_API = process.env.E2E_S_API || "http://127.0.0.1:19000/api/web";
const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
// docker C端 后端的 config.json（bind mount .docker-data/client → /app/data）
const CONFIG_PATH = path.join(
  process.env.E2E_CLIENT_DATA || path.join(process.cwd(), "..", "..", ".docker-data", "client"),
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
// ① 章纲：OgPane 留存格子表单（概要/出场角色/必须完成的变化/主情绪）→ 保存草稿
// -------------------------------------------------------------------------

test("章纲：OgPane 真实表单编辑 + 保存草稿（概要/出场角色/必须完成的变化/主情绪）", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `章纲${Date.now() % 100000}`);
    await writeFirstChapter(page);

    // 回「章纲」页签（writeFirstChapter 停在正文）：默认查看态（一页纸只读）+ 必填缺口 chip
    await page.getByRole("tab", { name: /^章纲/ }).click();
    await expect(page.getByTestId("og-edit")).toBeVisible({ timeout: 10000 });
    await expect(page.locator(".gap-chip").first()).toBeVisible();

    // 进编辑态（c-ch-og-readonly），填 4 个代表字段（概要 / 出场角色 / 必须完成的变化 / 主情绪选择）
    await page.getByTestId("og-edit").click();
    await expect(
      page.getByText(/章纲：明确「这一章写什么」/),
    ).toBeVisible({ timeout: 10000 });
    await page.locator("#wf-summary").fill("主角在边境城邦发现妹妹失踪的线索");
    await page.locator("#wf-chars").fill("林晚");
    await page.locator("#wf-changes").fill("主角拿到入城许可");
    await page.locator("#wf-mood select").selectOption({ label: "悬疑" });

    // 保存草稿 → PUT /chapters/vol-1-ch-1 落盘（必填两项已齐 → 自动确认，toast 分口径）
    const save = page.waitForResponse(
      (r) =>
        r.request().method() === "PUT" &&
        r.url().includes(`/chapters/vol-1-ch-1`),
    );
    await page.getByRole("button", { name: "保存草稿" }).click();
    await save;
    await expect(page.getByText("已保存并确认章纲")).toBeVisible({ timeout: 5000 });

    // 后端直查：outline / memo / emotional_design 均已落盘（退役键不在结果里）
    const ch = await apiGetJSON(request, token, `/novels/${pid}/chapters/vol-1-ch-1`);
    expect(ch.outline.summary).toContain("妹妹失踪");
    expect(ch.outline.characters).toEqual(["林晚"]);
    expect(ch.memo.required_changes).toEqual(["主角拿到入城许可"]);
    expect(ch.emotional_design.primary_mood).toBe("悬疑");
    for (const dead of ["key_points", "location", "time", "narrative_pov"]) {
      expect(ch.outline[dead]).toBeUndefined();
    }
    expect(ch.memo.reader_expectation).toBeUndefined();
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// ② 卷纲（c-volume-antagonist 四问一页纸）：点卷节点 → 查看态 → 编辑态 → 保存卷纲
// -------------------------------------------------------------------------

// -------------------------------------------------------------------------
// ⑦ 信息差对齐块：随卷纲换代退役（c-volume-view-storyline，ADJUSTMENTS ⑤）
// -------------------------------------------------------------------------

test("信息差对齐块已退役：章纲页签不再出现 og-info-gap", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    await createNovel(page, `信息差退役${Date.now()}`);
    await writeFirstChapter(page);
    // 旧块消费的 info_gap_start/end 与 chapter_plans 已随卷纲换代退役
    await expect(page.getByTestId("og-info-gap")).toHaveCount(0);
  } finally {
    await restore();
  }
});

test("卷视图：点卷节点 → 四页签 → 卷纲两态编辑保存 → 进度线与右栏卷语境", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `卷视图${Date.now() % 100000}`);
    await writeFirstChapter(page);

    // 点卷头 → 中栏卷视图：头部（卷 · 分卷计划）＋四页签，默认查看态
    await page.locator(".col-tree .vol-head", { hasText: "第一卷" }).click();
    await expect(page.getByText("卷 · 分卷计划")).toBeVisible({ timeout: 10000 });
    for (const name of ["卷纲", "本卷章节", "角色关系", "伏笔"]) {
      await expect(page.getByRole("tab", { name })).toBeVisible();
    }
    await expect(page.getByRole("button", { name: "编辑卷纲" })).toBeVisible();
    await expect(page.getByRole("heading", { name: /第一卷/ })).toBeVisible();

    // 编辑态（c-volume-antagonist 四问一页纸）：主旨/冲突必填；坎＝类型＋一句话；卷末
    await page.getByRole("button", { name: "编辑卷纲" }).click();
    await expect(page.getByText("正在编辑卷纲")).toBeVisible();
    await page.getByLabel("本卷主旨").fill("第一卷铺垫主角妹妹失踪的悬念，收尾进入边城。");
    await page.getByLabel("核心矛盾").fill("匿名信与失踪案的真假之辨");
    await page.getByLabel("坎的类型").selectOption("人物");
    await page.getByLabel("坎的一句话").fill("执法官雷——点名要他停手");
    await page.getByLabel("卷末结局").fill("内鬼浮出水面");
    await page.getByLabel("章数目标").fill("12");
    // 伏笔不在卷纲里手写——住台账（本卷的伏笔指向「伏笔」页签）
    await expect(page.getByText(/住在台账里/)).toBeVisible();
    await expect(page.getByLabel(/本卷埋下伏笔/)).toHaveCount(0);
    // 保存 → PUT /volumes/vol-1 → 统一 toast《title》卷纲已保存
    const volSave = page.waitForResponse(
      (r) =>
        r.request().method() === "PUT" &&
        r.url().includes("/volumes/vol-1"),
    );
    await page.getByRole("button", { name: "保存", exact: true }).click();
    await volSave;
    await expect(page.getByText("卷纲已保存")).toBeVisible({ timeout: 5000 });

    // 后端直查：四问字段集落库；退役键（goal/plants/reveals/plan_line）不出现在契约里
    const vol = await apiGetJSON(request, token, `/novels/${pid}/volumes/vol-1`);
    expect(vol.summary).toContain("妹妹失踪");
    expect(vol.core_conflict).toBe("匿名信与失踪案的真假之辨");
    expect(vol.antagonist_type).toBe("人物");
    expect(vol.antagonist_line).toBe("执法官雷——点名要他停手");
    expect(vol.ending).toBe("内鬼浮出水面");
    expect(vol.chapter_target).toBe(12);
    for (const k of ["goal", "plants", "reveals", "plan_line", "template_name"]) {
      expect(vol[k]).toBeUndefined();
    }
    // 本卷角色＝聚合只读（第一章未登记出场 → 空态文案）
    expect(vol.cast_members).toEqual([]);

    // 查看态回显（四问一页纸）＋进度线（writeFirstChapter 仅开编辑器未写正文 → 该章=拟定；frontier 定位待写）
    await expect(page.getByText("第一卷铺垫主角妹妹失踪的悬念，收尾进入边城。")).toBeVisible();
    await expect(page.getByText("人物 · 执法官雷——点名要他停手")).toBeVisible();
    const progress = page.getByTestId("vol-progress");
    await expect(progress).toContainText("已归档");
    await expect(progress).toContainText("拟定")
    await expect(progress).toContainText("第 1 章");

    // 右栏卷语境（volume-plan-ai）：选中卷＝验证面板（免费、只读；四页签统计卡退役）
    await expect(page.getByText("AI 助手")).toBeVisible();
    await expect(page.getByTestId("volume-verify-panel")).toBeVisible();
    await expect(page.getByTestId("volume-check-btn")).toBeVisible();
    // 右栏随卷页签（c-write-home-rail-anchor）：当前页签＝真实页签名；卷纲页签多一个重新规划入口
    await expect(page.getByTestId("volume-rail-tab")).toHaveText("卷纲");
    await expect(page.getByTestId("volume-replan")).toBeVisible();
    await page.getByRole("tab", { name: "本卷章节" }).click();
    await expect(page.getByTestId("volume-rail-tab")).toHaveText("本卷章节");
    await expect(page.getByTestId("volume-rail-lead")).toContainText("已写内容与卷纲的出入");
    await expect(page.getByTestId("volume-replan")).toHaveCount(0);
    // 台账行（章纲一句话列）＋点行跳章
    const row = page.locator(".vol-chrow", { hasText: "第一章" });
    await expect(row).toBeVisible();
    await row.click();
    await expect(page.getByRole("tab", { name: /^章纲/ })).toBeVisible({
      timeout: 10000,
    });
  } finally {
    await restore();
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
    await restore();
  }
});

// -------------------------------------------------------------------------
// ④ 提示词（c-prompt-tab-retire）：页签退役；弹窗查看/编辑/存稿；状态行收编正文页签
// -------------------------------------------------------------------------

test("提示词：页签退役；生成正文弹窗查看/编辑/存为本章提示词", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `提示词${Date.now() % 100000}`);
    await writeFirstChapter(page);

    // 提示词后端接口需过 require_ai_access 门控：先注入 active ApiConfig（不测连接）
    await ensurePromptAccess(request, token);

    // c-prompt-tab-retire：提示词页签全档退役（PRO 也没有）
    await expect(page.getByRole("tab", { name: /^提示词/ })).toHaveCount(0);
    await expect(page.getByRole("tab", { name: /^正文/ })).toBeVisible();

    // 正文页签右栏状态行：本章提示词 自动组装（尚未落库）
    await page.getByRole("tab", { name: /^正文/ }).click();
    await expect(page.locator(".ai-target")).toContainText("本章提示词", { timeout: 10000 });
    await expect(page.locator(".ai-target")).toContainText("自动组装");

    // 打开「生成正文」弹窗＝查看最新提示词（每开必重新组装）
    await page.getByTestId("ai-write-btn").click();
    const ai = page.getByRole("dialog", { name: "AI 生成正文" });
    const ta = ai.getByTestId("ai-prompt");
    await expect(ta).toBeEnabled({ timeout: 10000 });

    // 编辑 → 存为本章提示词 → PUT prompts/write 落库 + toast
    await ta.fill("# 整章任务\n\n描写主角收到匿名信后追出城门的场景。");
    const save = page.waitForResponse(
      (r) => r.request().method() === "PUT" && r.url().includes("/prompts/write"),
    );
    await ai.getByTestId("ai-prompt-save").click();
    await save;
    await expect(page.getByText("已存为本章提示词")).toBeVisible({ timeout: 5000 });

    // 关闭 → 状态行转「已自定义」（promptSavedSignal 刷新）
    await ai.getByRole("button", { name: "取消" }).click();
    await expect(page.locator(".ai-target")).toContainText("已自定义", { timeout: 10000 });

    // 重开弹窗：内容＝存下的那一版（存量稿，无「AI 润色」按钮）
    await page.getByTestId("ai-write-btn").click();
    const ai2 = page.getByRole("dialog", { name: "AI 生成正文" });
    await expect(ai2.getByTestId("ai-prompt")).toHaveValue(/追出城门的场景/, {
      timeout: 10000,
    });
    await expect(ai2.getByTestId("ai-polished-tag")).toBeVisible();
    await expect(ai2.getByTestId("ai-polish")).toHaveCount(0);
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// ④b 未配 API Key（trial 会员）：点提示词 tab 就地提示去配置，不整页跳 /config
// -------------------------------------------------------------------------

test("无Key：生成正文弹窗就地报错，不整页跳转", async ({
  page,
}) => {
  const { restore } = await setupSession(page); // trial 会员但未注入 ApiConfig
  try {
    await createNovel(page, `无Key提示词${Date.now() % 100000}`);
    await writeFirstChapter(page);

    // 点正文页签 → 生成正文：write/prompt 503 → 弹窗就地显示错误（而非全局跳 /config）
    await page.getByRole("tab", { name: /^正文/ }).click();
    await page.getByTestId("ai-write-btn").click();
    const ai = page.getByRole("dialog", { name: "AI 生成正文" });
    await expect(ai.getByText(/API Key/)).toBeVisible({ timeout: 10000 });
    // 错误态：生成按钮不可点
    await expect(ai.getByTestId("ai-confirm")).toBeDisabled();

    // 关键回归断言：仍留在章页（未整页跳 /config）
    await expect(page).toHaveURL(/#\/novel\//);
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// ⑤ 免费态提示词子 label 隐藏（ai-prompt-crafting PRO-only 口径，取代 #152 入口可见）
// -------------------------------------------------------------------------

test("免费态：正文/章纲可见，提示词页签不存在", async ({
  page,
}) => {
  const { restore } = await setupSession(page, "none");
  try {
    await createNovel(page, `免费提示词${Date.now() % 100000}`);
    await writeFirstChapter(page);

    await expect(page.getByRole("tab", { name: /^正文/ })).toBeVisible();
    await expect(page.getByRole("tab", { name: /^章纲/ })).toBeVisible();
    // c-prompt-tab-retire：提示词页签全档退役（提示词从「生成正文」弹窗查看/编辑）
    await expect(page.getByRole("tab", { name: /^提示词/ })).toHaveCount(0);
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// ⑥ PR3 行为：点章恒落「章纲」页签（设计稿拍板，取代 PR2 按进度/付费分流）
//    + 进度信息收编头部徽章行（c-rail-ai-only：右栏本章进度卡退役，右栏只剩 AI）
// -------------------------------------------------------------------------

test("点章强制落章纲：确认/有正文后重挂载仍落章纲 + 头部徽章行收编进度信息", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `矩阵${Date.now() % 100000}`);

    // 建卷 + 排 1 章（停在默认落点「章纲」页签）
    await addFirstChapterViaTree(page);
    const chRow = page.locator(".col-tree .ch", { hasText: "第一章" });

    // 行①：新章（未确认/无提示词/无正文）→ 章纲选中
    await chRow.click();
    const ogTab = page.getByRole("tab", { name: /^章纲/ });
    await expect(ogTab).toBeVisible({ timeout: 10000 });
    await expect(ogTab).toHaveAttribute("aria-selected", "true");
    // 默认查看态（c-ch-og-readonly）：「编辑章纲」在＝查看态已载入
    await expect(page.getByTestId("og-edit")).toBeVisible({ timeout: 10000 });

    // API 备齐必填（必须完成的变化/主情绪，c-og-slim-v2 两项）→ 确认
    const auth = { Authorization: `Bearer ${token}` };
    const ready = (await apiGetJSON(
      request,
      token,
      `/novels/${pid}/chapters/vol-1-ch-1`,
    )) as Record<string, unknown>;
    ready.memo = { required_changes: ["找到匿名信的来源"] };
    ready.emotional_design = { primary_mood: "悬疑" };
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
      await expect(
        page.getByRole("button", { name: "编辑卷纲" }),
      ).toBeVisible({ timeout: 5000 });
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

    // 右栏 Rail 收敛为纯 AI 助手（c-rail-ai-only）：进度卡退役，信息在头部徽章行
    await expect(page.getByText("本章进度", { exact: true })).toHaveCount(0);
    const meta = page.locator(".e-meta");
    await expect(meta).toContainText("完成度");
    await expect(meta).toContainText("本书总字数");
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// ⑧ 章纲提示词格子：读者获得（类型/描述）+ 章末落点 + 目标字数
//    —— 填值保存、后端落盘、重载回读（c-og-slim-v2：场景卡与位置档退役）
// -------------------------------------------------------------------------

test("章纲格子：读者获得/章末落点/目标字数填值保存 + 回读", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `格子${Date.now() % 100000}`);
    await writeFirstChapter(page);

    // 回「章纲」页签，进编辑态（c-ch-og-readonly）
    await page.getByRole("tab", { name: /^章纲/ }).click();
    await page.getByTestId("og-edit").click();
    await expect(
      page.getByText(/章纲：明确「这一章写什么」/),
    ).toBeVisible({ timeout: 10000 });

    // 必填两项补齐（c-og-slim-v2：预期策略/段落规划退役）——缺口未清空前「确认章纲」禁用
    await page.locator("#wf-changes").fill("主角拿到入城许可");
    await page.locator("#wf-mood select").selectOption({ label: "悬疑" });

    // 展开提示词格子折叠区
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

    // 读者获得：一条（反转 / 描述；位置档已退役）
    await page.getByRole("button", { name: "添加读者获得" }).click();
    const payoff = page.locator(".payoff-row").first();
    await payoff.locator('[data-payoff="k"]').selectOption("twist");
    await payoff.locator('[data-payoff="d"]').fill("匿名信的火漆印是自家纹章");

    // 章末落点 + 目标字数
    await page.locator("#wf-ladder").fill("他收起通缉令，转身没入夜色");
    await page.locator("#wf-wt").fill("4000");

    // 保存草稿 → PUT 落盘（须甄别请求体：前一步「确认章纲」的 PUT 可能仍在途，
    // 裸等 method+url 会抢到未带新格子的那次响应）
    const save = page.waitForResponse(
      (r) =>
        r.request().method() === "PUT" &&
        r.url().includes(`/chapters/vol-1-ch-1`) &&
        (r.request().postDataJSON() as { micro_payoffs?: unknown[] })
          ?.micro_payoffs?.length === 1,
    );
    await page.getByRole("button", { name: "保存草稿" }).click();
    await save;

    // 后端直查：格子落盘（读者获得无位置档；场景卡不在结果里）
    const ch = await apiGetJSON(request, token, `/novels/${pid}/chapters/vol-1-ch-1`);
    expect(ch.micro_payoffs).toEqual([
      { kind: "twist", description: "匿名信的火漆印是自家纹章" },
    ]);
    expect(ch.ladder_exit).toBe("他收起通缉令，转身没入夜色");
    expect(ch.word_target).toBe(4000);
    expect(ch.scene_cards).toBeUndefined();
    expect(ch.segments).toBeUndefined();

    // 重载回读：展开折叠区，值都在
    await page.reload();
    await page.locator(".col-tree .ch", { hasText: "第一章" }).click();
    await page.getByRole("tab", { name: /^章纲/ }).click();
    await page.getByTestId("og-edit").click();
    await page.locator("#wf-payoffs summary").click();
    await expect(page.locator(".payoff-row").first().locator('[data-payoff="k"]')).toHaveValue(
      "twist",
    );
    await expect(page.locator("#wf-ladder")).toHaveValue("他收起通缉令，转身没入夜色");
    await expect(page.locator("#wf-wt")).toHaveValue("4000");
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// ⑨ 右栏 AI 辅助随页签切换（workbench-storyline-ai-panel，storyline col-ai 口径）
// -------------------------------------------------------------------------
test("右栏 AI 辅助随页签切换：引导语/统计卡/动作清单（动作全部落地）", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    await ensurePromptAccess(request, token);
    await createNovel(page, `e2e-rail-${Date.now()}`);
    await writeFirstChapter(page);
    // 显式切回章纲并等查看态就绪（点章落章纲的回落竞态结算）
    await page.getByRole("tab", { name: /^章纲/ }).click();
    await expect(page.getByTestId("og-edit")).toBeVisible({ timeout: 10000 });
    // 章纲页签：面板随页签切换；动作全部落地（占位机制已退役，不再有「规划中」）
    await expect(page.getByText("AI 助手 · 章纲")).toBeVisible({ timeout: 10000 });
    const railCard = page.locator(".rail-assist");
    await expect(railCard.getByRole("button", { name: /剧情推演/ })).toBeEnabled();
    await expect(railCard.getByRole("button", { name: /补全缺失字段/ })).toBeEnabled();
    await expect(railCard.getByText("规划中")).toHaveCount(0);
    // 正文页签：面板切到正文（统计正文字数）；压缩需选中才可点
    await page.getByRole("tab", { name: /^正文/ }).click();
    await expect(page.getByText("AI 助手 · 正文")).toBeVisible();
    await expect(railCard.getByRole("button", { name: /压缩啰嗦段落/ })).toBeDisabled();
    // 提示词页签退役（c-prompt-tab-retire）：组装来源统计随状态收编正文页签作用域行
    await expect(page.getByRole("tab", { name: /^提示词/ })).toHaveCount(0);
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// ⑩ 章内「伏笔」页签（workbench-storyline-hooks）：全档位只读台账投影
// -------------------------------------------------------------------------
test("伏笔页签：台账投影渲染（空态文案与汇总）", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    await createNovel(page, `e2e-hooks-${Date.now()}`);
    await writeFirstChapter(page);
    await page.getByRole("tab", { name: /^伏笔/ }).click();
    await expect(page.locator('[data-od-id="hooks-pane"]')).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("全书统一维护 · 记下埋点与回收章 · 本章条目高亮")).toBeVisible();
    await expect(
      page.getByText("还没有伏笔条目。到「设定 · 伏笔」里登记第一条。"),
    ).toBeVisible();
  } finally {
    await restore();
  }
});

// -------------------------------------------------------------------------
// ⑨ 预览阅读器（preview-reader，c-preview-reader）：三栏 + 目录切章 + 跨卷翻页
//    + 阅读配置持久化（离开再进仍在）+ 写作视图选中章不变（ADJUSTMENTS #13）
// -------------------------------------------------------------------------

test("预览阅读器：三栏/跨卷翻页/配置持久化/写作选中不变", async ({ page, request }) => {
  const { restore, token } = await setupSession(page, "trial");
  try {
    const pid = await createNovel(page, `预览器${Date.now() % 100000}`);
    const editor = await writeFirstChapter(page);
    await editor.fill("第一卷第一章的正文，用于预览通读验证字数与状态标签。".repeat(4));
    await expect(page.getByText("已自动保存").first()).toBeVisible({ timeout: 8000 });

    // API 备料：vol-1 第二章 + 第二卷（含一章）→ 跨卷翻页样本
    const post = async (path: string, data: unknown) => {
      const r = await request.post(`${ORIGIN}/api/novels/${pid}${path}`, {
        data,
        headers: { Authorization: `Bearer ${token}` },
      });
      expect(r.ok()).toBeTruthy();
      return r.json().catch(() => ({}));
    };
    await post("/volumes/vol-1/chapters", { title: "渡口" });
    const v2 = await post("/volumes", { title: "第二卷" });
    const v2Ref = (v2.data?.ref ?? v2.ref ?? "vol-2") as string;
    await post(`/volumes/${v2Ref}/chapters`, { title: "归航" });
    // 刷新树（API 备料后写作树是事件增量，保险起见整页重进）
    await page.reload();
    await expect(page.locator(".three-col .ch", { hasText: "归航" })).toBeVisible({
      timeout: 10000,
    });

    // ── 进预览：三栏可见 + 目录头计数 + 定档＝首章（不继承写作页当前章）──
    await page.locator(".mtab", { hasText: "预览" }).click();
    await expect(page.locator(".pv-tree")).toBeVisible();
    await expect(page.locator(".pv-read")).toBeVisible();
    await expect(page.locator(".pv-side")).toBeVisible();
    await expect(page.getByTestId("pv-count")).toContainText("主线 3 章 · 2 卷 · 不含旧稿");
    await expect(page.getByTestId("pv-chapter")).toContainText("第一章");
    // 概览：3 章 · 已归档 0（trial 未归档）· 草稿 1 · 拟定 2
    await expect(page.locator(".pv-side .stat-line").first()).toContainText("章节 3");
    await expect(page.locator(".pv-side .stat-line").first()).toContainText("草稿 1 · 拟定 2");

    // ── 下一章跨卷：第一章 → 第二章（卷内）→ 第三卷? 第三章（第二卷）──
    await page.getByTestId("pv-next").click();
    await expect(page.getByTestId("pv-chapter")).toContainText("第二章 · 渡口");
    await page.getByTestId("pv-next").click();
    // 章号卷内编号（第二卷首章 = 第一章 · 归航）
    await expect(page.getByTestId("pv-chapter")).toContainText("第一章 · 归航");
    await expect(page.getByTestId("pv-chapter").locator(".pv-voltag")).toHaveText("第二卷");
    // 末章禁用 + 上一章回跨
    await expect(page.getByTestId("pv-next")).toHaveAttribute("aria-disabled", "true");
    await page.getByTestId("pv-prev").click();
    await expect(page.getByTestId("pv-chapter")).toContainText("第二章 · 渡口");
    // 目录直切
    await page.locator(".pv-ch", { hasText: "归航" }).click();
    await expect(page.getByTestId("pv-chapter")).toContainText("第一章 · 归航");

    // ── 阅读配置：夜间 + 小号立即生效并落 localStorage ──
    await page.getByRole("group", { name: "主题" }).locator("button", { hasText: "夜间" }).click();
    await page.getByRole("group", { name: "字号" }).locator("button", { hasText: "小" }).click();
    await expect(page.locator(".view.preview-v")).toHaveClass(/pv-theme-night/);
    const readTheme = await page.evaluate(
      (k) => localStorage.getItem(k),
      `pref.book.${pid}.read.theme`,
    );
    expect(readTheme).toBe("night");

    // ── 回写作：落书主页卡（页签回默认主页）；续写仍指向最初的第一章（预览切章不回写写作视图）──
    await page.locator(".mtab", { hasText: "写作" }).click();
    await expect(page.getByTestId("write-home")).toBeVisible({ timeout: 10000 });
    await page.getByTestId("home-resume").click();
    // PR3 口径：点章/重挂载默认落「章纲」页签 → 先切「正文」再看编辑器
    await page.getByRole("tab", { name: /^正文/ }).click();
    await expect(page.locator(".editor")).toBeVisible({ timeout: 10000 });
    await expect(page.locator(".col-editor .e-title")).toContainText("第一章");

    // ── 再进预览：阅读配置仍在（书级持久化）──
    await page.locator(".mtab", { hasText: "预览" }).click();
    await expect(page.locator(".view.preview-v")).toHaveClass(/pv-theme-night/);
    await expect(page.getByTestId("pv-chapter")).toContainText("第一章");
  } finally {
    await restore();
  }
});

test("页签回默认主页：点「写作」落书主页卡（建书入口在场），删空后仍是主页卡", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `主页${Date.now() % 100000}`);
    await writeFirstChapter(page);

    // 有章 → 点「写作」回书主页（清选中）：进度眉标 + 续写 + 建书双入口
    await page.locator(".mtab", { hasText: "写作" }).click();
    await expect(page.getByTestId("write-home")).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId("home-progress")).toContainText("1 卷 · 1 章");
    await expect(page.getByTestId("home-add-volume")).toBeVisible();
    await expect(page.getByTestId("home-add-chapter")).toBeVisible();

    // 续写回到该章（主线端点）
    await page.getByTestId("home-resume").click();
    await expect(page.getByRole("tab", { name: /^章纲/ })).toBeVisible({
      timeout: 10000,
    });
    // 重复点「写作」仍回主页（不是无操作）
    await page.locator(".mtab", { hasText: "写作" }).click();
    await expect(page.getByTestId("write-home")).toBeVisible({ timeout: 10000 });

    // 删空最后一章：仍见书主页卡与建书入口（判据＝曾排过章）
    const del = await request.delete(
      `${ORIGIN}/api/novels/${pid}/chapters/vol-1-ch-1`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    expect(del.ok()).toBeTruthy();
    await page.reload();
    await page.locator(".mtab", { hasText: "写作" }).click();
    await expect(page.getByTestId("write-home")).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId("home-progress")).toContainText("0 章");
    await expect(page.getByTestId("home-add-chapter")).toBeVisible();
  } finally {
    await restore();
  }
});

test("页签回默认主页守卫：卷纲未保存先确认（取消留卷页 / 确认回主页）", async ({
  page,
}) => {
  const { restore } = await setupSession(page);
  try {
    await createNovel(page, `守卫${Date.now() % 100000}`);
    await writeFirstChapter(page);
    // 点卷头 → 卷视图 → 进编辑态弄脏
    await page.locator(".col-tree .vol-head", { hasText: "第一卷" }).click();
    await expect(page.getByRole("tab", { name: "卷纲" })).toBeVisible({
      timeout: 10000,
    });
    await page.getByRole("button", { name: "编辑卷纲" }).click();
    await page.getByLabel("本卷主旨").fill("守卫用主旨，未保存。");

    // 取消分支：confirm dismiss → 留在卷纲编辑态，输入保留
    let dialogText = "";
    page.once("dialog", (d) => {
      dialogText = d.message();
      void d.dismiss();
    });
    await page.locator(".mtab", { hasText: "写作" }).click();
    await expect(page.getByTestId("write-home")).toHaveCount(0);
    expect(dialogText).toContain("卷信息有未保存的修改");
    await expect(page.getByText("正在编辑卷纲")).toBeVisible();
    await expect(page.getByLabel("本卷主旨")).toHaveValue("守卫用主旨，未保存。");

    // 确认分支：accept → 回书主页
    page.once("dialog", (d) => void d.accept());
    await page.locator(".mtab", { hasText: "写作" }).click();
    await expect(page.getByTestId("write-home")).toBeVisible({ timeout: 10000 });
  } finally {
    await restore();
  }
});
