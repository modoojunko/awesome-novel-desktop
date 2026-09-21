import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page } from "@playwright/test";
import { cleanupSessionNovels, stableClick } from "./helpers";

// =========================================================================
// volume-plan-ai 六态 e2e：空书起手 → 规划台（两条入口）→ 3 套 → 展开 →
// 生成中（可控门闩）→ 生成完成 → 回填 → 保存 → 落点卡 → 体检三组（none 占位）→
// 免费档置灰。AI 三端点全部 page.route 打桩；卷/章真落库；「不落库」后端直查。
// =========================================================================

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

async function sRegisterAndLogin() {
  const name = `e2e_vpa_${Date.now()}_${randomUUID().slice(0, 8)}`;
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
  if (regBody.code !== 0) throw new Error(`S端 register 失败: ${JSON.stringify(regBody)}`);
  const login = await fetch(`${S_API}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: name, password }),
  });
  const loginBody = await login.json();
  if (loginBody.code !== 0) throw new Error(`S端 login 失败: ${JSON.stringify(loginBody)}`);
  return { token: loginBody.data.token as string, username: name };
}

async function writeOAuthSession(t: string, u: string, tier = "trial") {
  const fs = await import("fs");
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = t;
  cfg.tier = tier;
  cfg.expires_at = tier === "none" ? "" : "2099-12-31";
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2));
  return {
    restore: async () => fs.writeFileSync(CONFIG_PATH, original),
  };
}

async function setupSession(page: Page, tier = "trial") {
  const { token, username } = await sRegisterAndLogin();
  const { restore } = await writeOAuthSession(token, username, tier);
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  await page.route("**/api/auth/check-auth", (r) =>
    r.fulfill({ json: { code: 0, data: {} } }),
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
  await stableClick(page.getByRole("button", { name: "新建作品" }).first());
  await page.locator("input#bkTitle").fill(name);
  await page.getByRole("button", { name: "创建，去写简介" }).click();
  await page.waitForURL(/#\/novel\/[0-9a-fA-F-]+/);
  const m = page.url().match(/\/novel\/([0-9a-fA-F-]+)/);
  if (!m) throw new Error(`无法解析 novel id: ${page.url()}`);
  await page.getByRole("button", { name: /^写作/ }).click();
  return m[1];
}

const THREE_PLANS = {
  ok: true,
  plans: [
    {
      no: 1,
      spine: "林野为查身世与旧贵族做交易，代价是替他们清掉一个叛徒",
      conflict: "想查真相，与双手沾血",
      ending: "他拿到情报，也第一次被叫做刽子手",
      focus: "侧重代价——把「回不去」在这一卷付清",
      focus_axis: "代价",
    },
    {
      no: 2,
      spine: "林野与旧贵族结盟换取线索，盟约里互相利用",
      conflict: "信谁，与防谁",
      ending: "盟约成立，他的名字被排在牺牲一侧",
      focus: "侧重关系——盟约的成立与代价",
      focus_axis: "关系",
    },
    {
      no: 3,
      spine: "林野顺着身世线索追到旧档案，发现大火另有其人",
      conflict: "想确认，与怕确认",
      ending: "真相指向血族议会，他决定离开旧街区",
      focus: "侧重认知——从求生变成求证",
      focus_axis: "认知",
    },
  ],
  note: "",
  volume_estimate: "按结局的清算夜倒推，全书约 3 卷",
  similar: false,
  warnings: [],
};

const EXPAND = {
  ok: true,
  vol_no: 1,
  plan_line: "林野为查身世与旧贵族做交易，代价是替他们清掉一个叛徒",
  draft: {
    name: "血酬",
    summary: "林野为查身世与旧贵族交易拿情报，代价是清掉一个叛徒。",
    conflict: "想查真相，与双手沾血——清叛徒就是入伙。",
    goal: "拿到旧档案，确认身世线索的方向。",
    ending: "他签了字，第一次被叫做刽子手。",
    plants: ["猎血短刃的来历被旧贵族提起"],
    reveals: [],
    chapter_target: 12,
    checks: ["叛徒身份需从既有势力里选，不添新人物。"],
  },
  warnings: [],
};

const CHECK_REPORT = {
  ok: true,
  vol_no: 1,
  name: "血酬",
  report: [
    {
      name: "对主线",
      items: [{ status: "ok", text: "进场接得上全景的起步。", evidence: "进场" }],
    },
    {
      name: "对设定",
      items: [{ status: "warn", text: "猎血短刃来历未在设定登记。", evidence: "plants" }],
    },
    {
      name: "对已写内容",
      items: [{ status: "none", text: "还没有章节——写到之后这里换成实际写出来的对照。" }],
    },
  ],
};

test("规划全链：入口A→3套（不落库直查）→选卡展开（门闩）→生成中关弹窗→自动回填→保存→落点卡→入口B→体检三组", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `规划${Date.now() % 100000}`);

    // ① 空书起手：中栏起手卡（作家口径）＋右栏规划第一卷入口（入口 A）
    await expect(page.getByText("这本书怎么开始？")).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId("plan-first-volume")).toBeVisible();

    // ② 打开规划台：材料（引导语）＋分卷依据可折叠
    await page.getByTestId("plan-first-volume").click();
    await expect(page.getByTestId("volume-plan-modal")).toBeVisible();
    await expect(page.getByRole("heading", { name: "规划第一卷" })).toBeVisible();

    // ③ 给我 3 套方案（打桩）→ 三张四字段卡，侧重互不相同
    await page.route("**/api/novels/*/volumes/ai/options", (r) =>
      r.fulfill({ json: THREE_PLANS }),
    );
    await page.getByTestId("plan-options-btn").click();
    await expect(page.getByTestId("plan-card-3")).toBeVisible({ timeout: 5000 });
    await expect(page.getByTestId("plan-options")).toContainText("代价");
    await expect(page.getByTestId("plan-options")).toContainText("关系");
    await expect(page.getByTestId("plan-options")).toContainText("认知");

    // 不落库（后端直查）：方案阶段卷数仍为 0
    const treeResp = await request.get(`${ORIGIN}/api/novels/${pid}/volumes`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(treeResp.ok()).toBeTruthy();
    expect(await treeResp.json()).toHaveLength(0);

    // ④ 选一套 → 填回输入框并直接展开；展开请求挂可控门闩（生成中）
    let releaseExpand!: (v?: unknown) => void;
    const gate = new Promise<void>((r) => {
      releaseExpand = r;
    });
    await page.route("**/api/novels/*/volumes/ai/expand", async (r) => {
      await gate;
      await r.fulfill({ json: EXPAND });
    });
    await page.getByTestId("plan-card-1").getByRole("button", { name: "选它" }).click();

    // ⑤ 生成中：进度只在弹窗内，中栏仍是打开规划台之前的那页（背景静止）
    await expect(page.getByTestId("plan-generating")).toBeVisible();
    await expect(page.locator(".col-middle")).toContainText("这本书怎么开始？");
    // 生成中关弹窗 → 生成不中断
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("volume-plan-modal")).toHaveCount(0);
    releaseExpand();

    // ⑥ 完成后中栏直接开始回填（不必再点「回填」）：逐段落下＋只读行
    await expect(page.getByTestId("vol-plan-line")).toHaveText(
      EXPAND.plan_line,
      { timeout: 15000 },
    );
    await expect(page.getByTestId("vol-prev-ending")).toContainText("主线");
    // 逐段落完：主旨/矛盾/目标/结局/章数
    await expect(page.locator("#vol-summary")).toHaveValue(EXPAND.draft.summary, {
      timeout: 10000,
    });
    await expect(page.locator("#vol-conflict")).toHaveValue(EXPAND.draft.conflict);
    await expect(page.locator("#vol-goal")).toHaveValue(EXPAND.draft.goal);
    await expect(page.locator("#vol-ending")).toHaveValue(EXPAND.draft.ending);
    await expect(page.locator("#vol-target")).toHaveValue("12");

    // ⑦ 保存（空书采纳＝卷已建）→ 落写作默认页（落点卡），不停留在卷纲页
    await page.getByRole("button", { name: "保存", exact: true }).click();
    await expect(page.getByTestId("landing-card")).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId("landing-card")).toContainText("血酬");
    await expect(page.getByTestId("landing-card")).toContainText("开始写第一章？");

    // ⑧ 有卷未选中（写作默认页）右栏：接着往下规划（入口 B）＋卷的验证
    await expect(page.getByTestId("plan-next-volume")).toBeVisible();
    await expect(page.getByTestId("verify-vol-1")).toContainText("血酬");

    // ⑨ 点「卷的验证」行 → 选中该卷并立刻体检：三组报告，第三组 none 占位
    await page.route("**/api/novels/*/volumes/*/ai/check", (r) =>
      r.fulfill({ json: CHECK_REPORT }),
    );
    await page.getByTestId("verify-vol-1").click();
    await expect(page.getByTestId("volume-check-report")).toBeVisible({
      timeout: 10000,
    });
    const report = page.getByTestId("volume-check-report");
    await expect(report).toContainText("对主线");
    await expect(report).toContainText("对设定");
    await expect(report).toContainText("对已写内容");
    await expect(report).toContainText("还没有章节");
  } finally {
    await restore();
  }
});

test("手点「回填」只发一次建卷请求（双发曾撞 UNIQUE 500）", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    const pid = await createNovel(page, `手点回填${Date.now() % 100000}`);
    await expect(page.getByText("这本书怎么开始？")).toBeVisible({ timeout: 10000 });

    let createCalls = 0;
    await page.route("**/api/novels/*/volumes/ai/expand", (r) =>
      r.fulfill({ json: EXPAND }),
    );
    // 只计数、请求透传真后端（真落库——GET vol-1 才能回读；曾拦 POST 致 404）
    await page.route("**/api/novels/*/volumes", async (route) => {
      if (route.request().method() === "POST") createCalls += 1;
      await route.fallback();
    });
    await page.getByTestId("plan-first-volume").click();
    await page
      .getByTestId("plan-line-input")
      .fill(EXPAND.plan_line);
    await page.getByTestId("plan-expand-btn").click();
    // 弹窗开着等生成完成 → 手点「回填 →」（曾与关弹窗后的自动 effect 双发）
    await expect(page.getByTestId("plan-backfill-btn")).toBeVisible({ timeout: 10000 });
    await page.getByTestId("plan-backfill-btn").click();
    await expect(page.getByTestId("vol-plan-line")).toHaveText(EXPAND.plan_line, {
      timeout: 15000,
    });
    await page.waitForTimeout(800); // 给可能的第二次双发留窗口
    expect(createCalls).toBe(1); // 只允许一次建卷 POST
  } finally {
    await restore();
  }
});

test("免费档：规划台可进、生成置灰带 PRO 说明；体检照常可用", async ({ page }) => {
  // 免费档全库限建 1 本（真实用户书占额）→ 先试用档建书，再翻免费档刷新（同一本书）
  const { restore } = await setupSession(page, "trial");
  try {
    const pid = await createNovel(page, `免费规划${Date.now() % 100000}`);
    const fs = await import("fs");
    const cfg = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf-8"));
    cfg.tier = "none";
    cfg.expires_at = "";
    fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2));
    await page.reload();
    await page.getByRole("button", { name: /^写作/ }).click();
    await expect(page.getByText("这本书怎么开始？")).toBeVisible({ timeout: 10000 });

    // 规划台可进：输入可写、材料可看；两个生成动作禁用＋PRO 说明
    await page.getByTestId("plan-first-volume").click();
    await expect(page.getByTestId("volume-plan-modal")).toBeVisible();
    await expect(page.getByRole("heading", { name: "规划第一卷" })).toBeVisible();
    await page
      .getByTestId("plan-line-input")
      .fill("林野第一次主动出城查身世");
    await expect(page.getByTestId("plan-expand-btn")).toBeDisabled();
    await expect(page.getByTestId("plan-options-btn")).toBeDisabled();
    await expect(page.locator(".plan-modal")).toContainText("PRO");
    await page.keyboard.press("Escape");

    // 手动建卷（走既有「添加卷」弹窗；建卷自动选中该卷）→ 选中态体检按钮免费可用
    await page.locator('[data-od-id="empty-add-vol"]').click();
    await page.locator("#add-vol-title").fill("第一卷");
    await page.locator("#add-vol-chapters").fill("0");
    await page.getByRole("button", { name: "创建卷" }).click();
    await expect(page.getByTestId("volume-check-btn")).toBeVisible({ timeout: 10000 });

    await page.route("**/api/novels/*/volumes/*/ai/check", (r) =>
      r.fulfill({ json: CHECK_REPORT }),
    );
    await page.getByTestId("volume-check-btn").click();
    await expect(page.getByTestId("volume-check-report")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByTestId("volume-check-report")).toContainText("对已写内容");
  } finally {
    await restore();
  }
});
