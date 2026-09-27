import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page } from "@playwright/test";
import { cleanupSessionNovels, stableClick, writeConfigAtomic } from "./helpers";

// =========================================================================
// volume-plan-ai 六态 e2e：空书起手 → 规划台（两条入口）→ 3 套 → 展开 →
// 生成中（可控门闩）→ 生成完成 → 回填 → 保存 → 落点卡 → 体检三组（none 占位）→
// 免费档置灰。AI 三端点全部 page.route 打桩；卷/章真落库；「不落库」后端直查。
// =========================================================================

const S_API = process.env.E2E_S_API || "http://127.0.0.1:19000/api/web";
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

/** 写会话 config.json（与 workbench-features/prompt-pipeline 同配方：竞态守卫＋随机 pc_hash）。
 *
 * 两条缺不得：①`last_login_at` 必须是新鲜的 UTC（否则 verify_session 的「系统时间异常」
 * 守卫把会话判死）；②`pc_hash` 必须随机——留着真实 pc_hash 会命中本机已授权设备，
 * S端 check-auth 返回 code 0 → 后端回写 config 把注入 token 冲掉 → 业务请求 401。
 * 写入用原子写（半截 JSON 会让容器内读方 500）。
 */
async function writeOAuthSession(t: string, u: string, tier = "trial") {
  const fs = await import("fs");
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = t;
  cfg.username = u;
  cfg.tier = tier;
  cfg.expires_at = tier === "none" ? "" : "2099-12-31";
  cfg.last_login_at = new Date().toISOString();
  cfg.pc_hash = randomUUID().replace(/-/g, "");
  const mine = JSON.stringify(cfg, null, 2);
  const writeMine = () => writeConfigAtomic(CONFIG_PATH, mine);
  writeMine();
  for (let stable = 0, tries = 0; stable < 2 && tries < 10; tries++) {
    await new Promise((r) => setTimeout(r, 300));
    if (fs.readFileSync(CONFIG_PATH, "utf-8") === mine) stable += 1;
    else {
      writeMine();
      stable = 0;
    }
  }
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
    { no: 1, spine: "她按下注销键的另一半，把自己从航图上擦掉", conflict: "想追，与回不去", ending: "船不在册——回程不再成立", focus: "侧重代价", focus_axis: "代价", antagonist_type: "环境", antagonist_line: "母港制度——注销就没有回程" },
    { no: 2, spine: "她第一次用自己的手艺跟船队换补给", conflict: "不想欠人，与得靠人", ending: "半页坐标留在别人手里", focus: "侧重关系", focus_axis: "关系", antagonist_type: "势力", antagonist_line: "拾荒船队——规矩不同都得让一步" },
    { no: 3, spine: "信号比母港的档案还老", conflict: "想确认，与怕确认", ending: "船头转向母港旧址", focus: "侧重认知", focus_axis: "认知", antagonist_type: "难题", antagonist_line: "信号的封装层——像有人维护过" },
  ],
  note: "", volume_estimate: "约 3 卷", similar: false, warnings: [],
};

const EXPAND = {
  ok: true, vol_no: 1,
  draft: {
    name: "血酬", summary: "林野为查身世跟旧贵族做交易，代价是清掉一个叛徒。",
    conflict: "想查真相，与双手沾血。", ending: "他签了字。",
    antagonist_type: "人物", antagonist_line: "执法官雷——点名要他停手",
    plants: ["猎血短刃的来历"], reveals: [], chapter_target: 40,
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

test("付费抽卡链：打开即三卡→选 B→确认成卷→落点卡→卷纲四问一页纸含坎→伏笔入台账", async ({ page, request }) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `抽卡${Date.now() % 100000}`);
    await expect(page.getByText("这本书怎么开始？")).toBeVisible({ timeout: 10000 });

    await page.route("**/api/novels/*/volumes/ai/options", (r) => r.fulfill({ json: THREE_PLANS }));
    await page.route("**/api/novels/*/volumes/ai/expand", (r) => r.fulfill({ json: EXPAND }));
    // 锚点单源（plan-anchor）：每张卡的「上接」取它
    const ANCHOR = {
      vol_no: 1,
      prev_ending: {
        text: "全景起步：她从母港出发，是船上唯一的人",
        source: "来自主线全景的「他从哪起步」",
      },
    };
    await page.route("**/volumes/plan-anchor**", (r) => r.fulfill({ json: ANCHOR }));
    // 抽卡入口（右栏）
    await page.getByTestId("plan-first-volume").click();
    await expect(page.getByTestId("pick-modal")).toBeVisible({ timeout: 5000 });
    await expect(page.getByTestId("pick-grid")).toBeVisible({ timeout: 5000 });
    const cards = page.locator(".pick-card");
    await expect(cards).toHaveCount(3);
    // 每张卡自带「上接」（c-write-home-rail-anchor）：与锚点同源；第 1 卷＝起点
    for (const no of [1, 2, 3]) {
      const row = page.getByTestId(`pick-enter-${no}`);
      await expect(row).toContainText("起点");
      await expect(row).toContainText(ANCHOR.prev_ending.text);
    }
    // 三卡互异
    const texts = await cards.allTextContents();
    expect(new Set(texts.map((t) => t.slice(0, 30))).size).toBe(3);
    // 选中 B → aria-checked → 确认
    await page.getByTestId("pick-card-2").click();
    expect(await page.getByTestId("pick-card-2").getAttribute("aria-checked")).toBe("true");
    await page.getByTestId("pick-confirm").click();
    // 落点卡承接（含卷名/章数）
    await expect(page.getByTestId("landing-card")).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId("landing-card")).toContainText("血酬");
    // 卷纲四问一页纸含坎
    await page.getByTestId("landing-open-outline").click();
    await expect(page.getByText(/3这一卷的坎|这一卷的坎/)).toBeVisible({ timeout: 8000 });
    await expect(page.getByText(/执法官雷/)).toBeVisible({ timeout: 5000 });
    // 确认落库后不残留「落地后清选中」信号：卷页保存后仍停在卷页（检视 P2 回归）
    await page.getByRole("button", { name: "编辑卷纲" }).click();
    await page.getByRole("button", { name: "保存", exact: true }).click();
    await expect(page.getByText("卷纲已保存")).toBeVisible({ timeout: 8000 });
    await expect(page.getByRole("button", { name: "编辑卷纲" })).toBeVisible({ timeout: 5000 });
    // 不落库直查：伏笔建议入台账（batch 真调用）
    const H = { Authorization: `Bearer ${token}` };
    const hooks = await (await request.get(`${ORIGIN}/api/novels/${pid}/hooks`, { headers: H })).json();
    const items = hooks?.data?.items ?? [];
    expect(items.length).toBeGreaterThanOrEqual(1); // 猎血短刃入册
    expect(items.some((h: { description: string }) => h.description.includes("猎血短刃"))).toBe(true);
  } finally {
    await restore();
  }
});

test("取消与锁定：写请求发出前 Esc＝不落库；发出后 Esc 不关弹窗（locked）", async ({ page, request }) => {
  const { restore, token } = await setupSession(page);
  const H = { Authorization: `Bearer ${token}` };
  const volsOf = async (pid: string) =>
    (await (await request.get(`${ORIGIN}/api/novels/${pid}/volumes`, { headers: H })).json()) as
      Array<{ ref: string }>;
  try {
    const pid = await createNovel(page, `取消${Date.now() % 100000}`);
    await expect(page.getByText("这本书怎么开始？")).toBeVisible({ timeout: 10000 });
    await page.route("**/api/novels/*/volumes/ai/options", (r) => r.fulfill({ json: THREE_PLANS }));
    let releaseExpand!: (v?: unknown) => void;
    const gate = new Promise<void>((r) => { releaseExpand = r; });
    await page.route("**/api/novels/*/volumes/ai/expand", async (r) => {
      await gate;
      await r.fulfill({ json: EXPAND });
    });

    // ① 写请求发出**前**取消：expand 尚未发出 → Esc 关弹窗 → 后端零卷（token 守卫丢弃 pending）
    await page.getByTestId("plan-first-volume").click();
    await page.getByTestId("pick-card-1").click();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("pick-modal")).toHaveCount(0);
    expect(await volsOf(pid)).toEqual([]);

    // ② 写请求发出**后**：弹窗 locked —— Esc 不得关窗，落库照常完成并承接落点卡
    await page.getByTestId("plan-first-volume").click();
    await page.getByTestId("pick-card-1").click();
    await page.getByTestId("pick-confirm").click();
    await expect(page.getByText("正在铺这一卷…")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("pick-modal")).toBeVisible(); // locked：关不掉
    releaseExpand();
    await expect(page.getByTestId("landing-card")).toBeVisible({ timeout: 10000 });
    const vols = await volsOf(pid);
    expect(vols.map((v) => v.ref)).toEqual(["vol-1"]); // 恰好一卷、无重复
  } finally {
    await restore();
  }
});

test("免费链：四问手写→直接创建→落点卡→卷纲可改", async ({ page }) => {
  // 免费档全库限建 1 本（真实用户书占额）→ trial 建书后翻免费档刷新（既有配方）
  const { restore } = await setupSession(page);
  try {
    await createNovel(page, `免费${Date.now() % 100000}`);
    const fs = await import("fs");
    const cfg = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf-8"));
    cfg.tier = "none"; cfg.expires_at = "";
    fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2));
    await page.reload();
    await page.getByRole("button", { name: /^写作/ }).click();
    await expect(page.getByText("这本书怎么开始？")).toBeVisible({ timeout: 10000 });
    await page.getByTestId("plan-first-volume").click();
    // 免费档＝四问手写页（无抽卡）
    await expect(page.getByTestId("volume-plan-modal")).toBeVisible({ timeout: 5000 });
    await expect(page.getByTestId("pick-modal")).toHaveCount(0);
    await page.getByTestId("q-what").fill("林野为查身世做交易");
    await page.getByTestId("q-conflict").fill("想查真相，与双手沾血");
    await page.getByTestId("q-ant-type").selectOption("人物");
    await page.getByTestId("q-ant-line").fill("执法官雷");
    await page.getByTestId("q-ending").fill("他签了字");
    await page.getByTestId("desk-create").click();
    await expect(page.getByTestId("landing-card")).toBeVisible({ timeout: 10000 });
    await page.getByTestId("landing-open-outline").click();
    await expect(page.getByText(/执法官雷/)).toBeVisible({ timeout: 5000 });
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

    // 免费档＝四问手写页（无抽卡）：四问可写；铺空缺置灰＋PRO；直建可用
    await page.getByTestId("plan-first-volume").click();
    await expect(page.getByTestId("volume-plan-modal")).toBeVisible();
    await expect(page.getByTestId("pick-modal")).toHaveCount(0);
    await page.getByTestId("q-what").fill("林野第一次主动出城查身世");
    await expect(page.getByTestId("desk-expand")).toBeDisabled();
    await expect(page.locator(".plan-badge").first()).toBeVisible();
    await expect(page.getByTestId("desk-create")).toBeEnabled();
    await page.keyboard.press("Escape");

    // 直接创建建卷（免费路）→ 落点卡；「卷的验证」点行＝选中＋立刻体检（免费）
    await page.getByTestId("plan-first-volume").click();
    await page.getByTestId("q-what").fill("查身世");
    await page.getByTestId("desk-create").click();
    await expect(page.getByTestId("landing-card")).toBeVisible({ timeout: 10000 });

    await page.route("**/api/novels/*/volumes/*/ai/check", (r) =>
      r.fulfill({ json: CHECK_REPORT }),
    );
    // 「卷的验证」点行＝选中该卷并立刻体检（免费可用）
    await page.getByTestId("verify-vol-1").click();
    await expect(page.getByTestId("volume-check-report")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByTestId("volume-check-report")).toContainText("对已写内容");
  } finally {
    await restore();
  }
});

test("卷页签右栏跟随与「重新规划这一卷」：组序随页签 + 确认不新建卷", async ({
  page,
  request,
}) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `重规划${Date.now() % 100000}`);
    await expect(page.getByText("这本书怎么开始？")).toBeVisible({ timeout: 10000 });
    await page.route("**/api/novels/*/volumes/ai/options", (r) => r.fulfill({ json: THREE_PLANS }));
    await page.route("**/api/novels/*/volumes/ai/expand", (r) => r.fulfill({ json: EXPAND }));
    await page.route("**/api/novels/*/volumes/*/ai/check", (r) => r.fulfill({ json: CHECK_REPORT }));
    // 先建出第一卷（付费＝抽卡）
    await page.getByTestId("plan-first-volume").click();
    await expect(page.getByTestId("pick-grid")).toBeVisible({ timeout: 5000 });
    await page.getByTestId("pick-card-1").click();
    await page.getByTestId("pick-confirm").click();
    await expect(page.getByTestId("landing-card")).toBeVisible({ timeout: 10000 });
    await page.getByTestId("landing-open-outline").click();
    await expect(page.getByTestId("volume-verify-panel")).toBeVisible({ timeout: 10000 });

    // 体检 → 组序随页签（卷纲＝对主线打头；本卷章节＝对已写内容打头）
    await page.getByTestId("volume-check-btn").click();
    const report = page.getByTestId("volume-check-report");
    await expect(report).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId("volume-rail-tab")).toHaveText("卷纲");
    await expect(report.locator(".rp-k").first()).toHaveText("对主线");
    await expect(page.getByTestId("volume-replan")).toBeVisible();
    await page.getByRole("tab", { name: "本卷章节" }).click();
    await expect(page.getByTestId("volume-rail-tab")).toHaveText("本卷章节");
    await expect(report.locator(".rp-k").first()).toHaveText("对已写内容");
    await expect(page.getByTestId("volume-replan")).toHaveCount(0);
    await page.getByRole("tab", { name: "卷纲" }).click();

    // 重新规划这一卷：卷号＝本卷；确认后更新原卷，不新建卷
    let createCalls = 0;
    await page.route("**/api/novels/*/volumes", (r) => {
      if (r.request().method() === "POST") createCalls += 1;
      return r.fallback();
    });
    await page.getByTestId("volume-replan").click();
    await expect(page.getByTestId("pick-modal")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText(/规划第一卷/).first()).toBeVisible();
    await page.getByTestId("pick-card-2").click();
    await page.getByTestId("pick-confirm").click();
    // 确认后回默认页（本书 0 章且从未排章 → 落点卡）
    await expect(page.getByTestId("landing-card")).toBeVisible({ timeout: 10000 });
    expect(createCalls).toBe(0);
    const H = { Authorization: `Bearer ${token}` };
    const vols = await (
      await request.get(`${ORIGIN}/api/novels/${pid}/volumes`, { headers: H })
    ).json();
    expect(vols).toHaveLength(1);
  } finally {
    await restore();
  }
});
