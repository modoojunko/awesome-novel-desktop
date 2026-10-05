import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page } from "@playwright/test";
import { cleanupSessionNovels, stableClick, writeConfigAtomic } from "./helpers";
import { entitlementFor } from "./tier-features";

// =========================================================================
// c-character-intro 盘点出场人物 e2e：免费盘点零新增／多缺人写入回程（含回执
// 两分支）／抽卡打桩 S-A-B→建卡并写入（PUT 名单＋建卡扩参载荷）／手填空格
// 形态（免费不露 AI 预填、无返回换一张）／换一批 exclude 请求体（组合禁令）／
// 抽卡失败三出口。AI 端点 page.route 打桩；名单真落库。
// =========================================================================

const S_API = process.env.E2E_S_API || "http://127.0.0.1:19000/api/web";
const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
const CONFIG_PATH = path.join(
  process.env.E2E_CLIENT_DATA || path.join(process.cwd(), "..", "..", ".docker-data", "client"),
  "config.json",
);

async function sRegisterAndLogin() {
  const name = `e2e_cast_${Date.now()}_${randomUUID().slice(0, 8)}`;
  const password = "Test" + "Pass789!";
  const reg = await fetch(`${S_API}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: name, password, security_question: "最喜欢的颜色", security_answer: "蓝色" }),
  });
  const rb = await reg.json();
  if (rb.code !== 0) throw new Error(`S端 register 失败: ${JSON.stringify(rb)}`);
  const login = await fetch(`${S_API}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: name, password }),
  });
  const lb = await login.json();
  if (lb.code !== 0) throw new Error(`S端 login 失败: ${JSON.stringify(lb)}`);
  return { token: lb.data.token as string, username: name };
}

async function writeOAuthSession(t: string, u: string, tier = "trial") {
  const fs = await import("fs");
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = t;
  cfg.username = u;
  cfg.tier = tier;
  cfg.entitlement = entitlementFor(tier); // 快照单源（tier-features 6.2）
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
  return { restore: async () => fs.writeFileSync(CONFIG_PATH, original) };
}

async function setupSession(page: Page, tier = "trial") {
  const { token, username } = await sRegisterAndLogin();
  const { restore } = await writeOAuthSession(token, username, tier);
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  await page.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 0, data: {} } }));
  const restoreAndCleanup = async () => {
    await cleanupSessionNovels(ORIGIN, token);
    await restore();
  };
  return { restore: restoreAndCleanup, token };
}

/** 建书→建卷→手写拆一章→开章纲（复用 plot.spec 同款链路） */
async function createNovelWithChapter(page: Page, name: string): Promise<string> {
  await page.goto(`${ORIGIN}/#/novels`);
  await stableClick(page.getByRole("button", { name: "新建作品" }).first());
  await page.locator("input#bkTitle").fill(name);
  await page.getByRole("button", { name: "创建，去写简介" }).click();
  await page.waitForURL(/#\/novel\/[0-9a-fA-F-]+/);
  const m = page.url().match(/\/novel\/([0-9a-fA-F-]+)/);
  if (!m) throw new Error(`无法解析 novel id: ${page.url()}`);
  await page.getByRole("button", { name: /^写作/ }).click();
  await expect(page.getByText("这本书怎么开始？")).toBeVisible({ timeout: 15000 });
  await page.getByTestId("plan-first-volume").click();
  await expect(
    page.getByTestId("pick-modal").or(page.getByTestId("volume-plan-modal")),
  ).toBeVisible({ timeout: 10000 });
  if (await page.getByTestId("pick-modal").count()) {
    await page.getByText("自己答四个问题").first().click();
  }
  await expect(page.getByTestId("volume-plan-modal")).toBeVisible({ timeout: 10000 });
  await page.getByTestId("q-what").fill("沉舟捡到一枚不属于人类纪元的导航信标");
  await page.getByTestId("q-conflict").fill("想自己查清，与得靠船队");
  await page.getByTestId("q-ant-type").selectOption("环境");
  await page.getByTestId("q-ant-line").fill("母港制度——信标要登记");
  await page.getByTestId("q-ending").fill("船头转向母港旧址");
  await page.getByTestId("desk-create").click();
  await expect(page.getByTestId("landing-card")).toBeVisible({ timeout: 10000 });
  await page.getByTestId("landing-open-outline").click();
  // 拆章入口已迁本卷章节页签（c-split-to-chapters-tab）
  await page.getByRole("tab", { name: "本卷章节" }).click();
  await page.getByTestId("volume-split-manual").click();
  await expect(page.getByTestId("chapter-plan-modal")).toBeVisible({ timeout: 5000 });
  await page.getByTestId("d-title").fill("信标进舱");
  await page.getByTestId("d-plot").fill("沉舟在废弃星港捡到信标，先藏了下来");
  await page.getByTestId("d-obstacle").fill("没人相信一个见习导航员");
  await page.getByTestId("d-ending").fill("她把信标藏进舱底夹层");
  await page.getByTestId("split-adopt").click();
  await expect(page.getByTestId("chapter-landing-card")).toBeVisible({ timeout: 10000 });
  await page.getByTestId("chapter-landing-outline").click();
  await expect(page.getByTestId("og-edit")).toBeVisible({ timeout: 10000 });
  await page.getByTestId("og-edit").click();
  await expect(page.locator("#wf-summary")).not.toHaveValue("", { timeout: 15000 });
  return m[1];
}

// ── 打桩载荷（与冻结契约逐字对齐）────────────────────────────
const REVIEW_TWO_GAPS = {
  rows: [
    { idx: 0, echo: "沉舟在废弃星港捡到信标，先藏了下来", verdict: "老角色能演", who: ["沉舟"], as: "", why: "主角独处戏", gap: null, defaulted: false },
    { idx: 1, echo: "得有人认得信标上的旧制刻印", verdict: "缺一个新角色", who: [], as: "", why: "船上没人懂旧制", gap: { need: "认得旧制刻印的鉴定人", why_not_old: "船队里没有懂旧制的", suggest: "加人" }, defaulted: false },
    { idx: 2, echo: "稽查艇临检，交半张禁航图换夜航窗口", verdict: "缺一个新角色", who: [], as: "", why: "换图得有个中间人", gap: { need: "敢接禁航图的黑市中间人", why_not_old: "沉舟自己出面会暴露", suggest: "延后" }, defaulted: false },
  ],
  quota: { named_count: 1, regime: "open" },
  hints: [],
};
const REVIEW_ZERO = {
  rows: [
    { idx: 0, echo: "沉舟在废弃星港捡到信标，先藏了下来", verdict: "老角色能演", who: ["沉舟"], as: "", why: "独处戏", gap: null, defaulted: false },
    { idx: 1, echo: "她把信标藏进舱底夹层", verdict: "不起名也行", who: [], as: "值夜水手", why: "过场", gap: null, defaulted: false },
  ],
  quota: { named_count: 1, regime: "open" },
  hints: [],
};
const CARDS = {
  cards: [
    { axis: "功能", name: "顾先生", persona: "船上古董商，认旧制刻印如数家珍", entrance: "闻讯来验货", exit_kind: "本卷退场", exit_note: "把命搭在下一单上", grade: "S", ranks: { "合不合适": 1, "差别在哪": 2, "好不好落地": 1 }, reasons: { "合不合适": "正是缺的鉴定人", "差别在哪": "与老船医一商一医", "好不好落地": "登船验货顺理成章" }, duty: "旧制刻印鉴定", why_not_old: "船队里没有懂旧制的" },
    { axis: "关系", name: "阿苓", persona: "黑市中间人学徒，急着证明自己", entrance: "半路截图", exit_kind: "章内退场", exit_note: "收钱走人", grade: "A", ranks: { "合不合适": 2, "差别在哪": 1, "好坏落地": 3 }, reasons: { "合不合适": "能递话但资历浅", "差别在哪": "与全船老人相对", "好不好落地": "出场偏顺" } },
    { axis: "身份", name: "老摆渡", persona: "港区老引航，黑白都敬三分", entrance: "引航时搭话", exit_kind: "申请常驻", exit_note: "留作后手", grade: "B", ranks: { "合不合适": 3, "差别在哪": 3, "好不好落地": 2 }, reasons: { "合不合适": "离鉴定隔一层", "差别在哪": "身份正面", "好不好落地": "常驻占额度" } },
  ],
  note: "",
};

test.describe.configure({ timeout: 90000 }); // 建书链路慢栈预算（默认 30s 不够六步断言）

test("盘点零新增一行收场（盘点收标准档，种 standard）", async ({ page }) => {
  const { restore } = await setupSession(page, "standard");
  try {
    await createNovelWithChapter(page, `e2e 零新增 ${Date.now()}`);
    await page.route("**/cast/ai-review", (r) => r.fulfill({ json: REVIEW_ZERO }));
    await stableClick(page.getByTestId("og-cast-review"));
    await expect(page.getByText("不用加人", { exact: false })).toBeVisible({ timeout: 15000 });
    await expect(page.locator(".cr-gap")).toHaveCount(0);
  } finally {
    await restore();
  }
});

test("抽卡→建卡并写入全链：PUT 名单＋建卡扩参载荷＋三处落账回执", async ({ page }) => {
  const { restore } = await setupSession(page, "trial");
  try {
    await createNovelWithChapter(page, `e2e 建卡写入 ${Date.now()}`);
    await page.route("**/cast/ai-review", (r) => r.fulfill({ json: REVIEW_TWO_GAPS }));
    const drawBodies: unknown[] = [];
    await page.route("**/cast/ai-draw", async (r) => {
      drawBodies.push(r.request().postDataJSON());
      return r.fulfill({ json: CARDS });
    });
    const posts: unknown[] = [];
    await page.route("**/api/novels/*/characters", async (r) => {
      if (r.request().method() === "POST") {
        posts.push(r.request().postDataJSON());
        return r.fulfill({ json: { ok: true, data: { id: "c-new", name: "顾先生", role: "配角" } } });
      }
      return r.continue();
    });
    await stableClick(page.getByTestId("og-cast-review"));
    await expect(page.locator(".cr-gap").first()).toBeVisible({ timeout: 15000 });
    await page.getByTestId("cr-draw").click();
    await expect(page.getByTestId("cr-pick-card-1")).toBeVisible({ timeout: 15000 });
    await page.getByTestId("cr-pick-card-1").click();
    await expect(page.getByTestId("cr-write")).toBeVisible({ timeout: 10000 });
    await page.getByTestId("cr-write").click();
    // 回执：建卡版三处落账＋多缺人回程回结果页
    await expect(page.getByText("角色表多一卡", { exact: false }).first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/还有\s*1\s*个缺的人/).first()).toBeVisible({ timeout: 10000 });
    // 建卡扩参载荷：persona/prefill 到位
    expect(posts.length).toBeGreaterThanOrEqual(1);
    const body = posts[0] as Record<string, unknown>;
    expect(body.name).toBe("顾先生");
    expect(String(body.persona ?? "")).toContain("古董商");
    const prefill = body.prefill as Record<string, string> | undefined;
    expect(prefill?.plot ?? "").toContain("鉴定");
    // 名单真落库：PUT 后再读表单名单含新名字
    await page.waitForTimeout(3500);
    const chars = await page.locator("#wf-chars").inputValue();
    expect(chars).toContain("顾先生");
  } finally {
    await restore();
  }
});

test("手填空格形态：不露 AI 预填、无「返回换一张」（种 standard，盘点可开）", async ({ page }) => {
  const { restore } = await setupSession(page, "standard");
  try {
    await createNovelWithChapter(page, `e2e 手填形态 ${Date.now()}`);
    await page.route("**/cast/ai-review", (r) => r.fulfill({ json: REVIEW_TWO_GAPS }));
    await stableClick(page.getByTestId("og-cast-review"));
    await expect(page.getByTestId("cr-fill-manual")).toBeVisible({ timeout: 15000 });
    await page.getByTestId("cr-fill-manual").click();
    await expect(page.getByTestId("cr-write")).toBeVisible({ timeout: 10000 });
    // 空格表单：称呼格为空、无返回换一张
    await expect(page.getByTestId("claim-name")).toHaveValue("");
    await expect(page.getByTestId("cr-back-cards")).toBeHidden();
    await expect(page.getByTestId("cr-draw-locked").or(page.getByTestId("cr-write")).first()).toBeVisible();
  } finally {
    await restore();
  }
});

test("换一批 exclude 请求体带（轴＋称呼＋人设）组合", async ({ page }) => {
  const { restore } = await setupSession(page, "trial");
  try {
    await createNovelWithChapter(page, `e2e 换一批 ${Date.now()}`);
    await page.route("**/cast/ai-review", (r) => r.fulfill({ json: REVIEW_TWO_GAPS }));
    const drawBodies: unknown[] = [];
    await page.route("**/cast/ai-draw", async (r) => {
      drawBodies.push(r.request().postDataJSON());
      return r.fulfill({ json: CARDS });
    });
    await stableClick(page.getByTestId("og-cast-review"));
    await expect(page.getByTestId("cr-draw")).toBeVisible({ timeout: 15000 });
    await page.getByTestId("cr-draw").click();
    await expect(page.getByTestId("cr-redraw")).toBeVisible({ timeout: 15000 });
    await page.getByTestId("cr-redraw").click();
    await expect(page.getByTestId("cr-pick-card-1")).toBeVisible({ timeout: 15000 });
    expect(drawBodies.length).toBeGreaterThanOrEqual(2);
    const second = drawBodies[drawBodies.length - 1] as { exclude?: Array<Record<string, string>> };
    const excl = second.exclude ?? [];
    expect(excl.length).toBeGreaterThanOrEqual(3);
    expect(excl[0]).toHaveProperty("axis");
    expect(excl[0]).toHaveProperty("name");
    expect(excl[0]).toHaveProperty("persona");
  } finally {
    await restore();
  }
});

test("抽卡失败三出口（重试/自己填/先不抽了）", async ({ page }) => {
  const { restore } = await setupSession(page, "trial");
  try {
    await createNovelWithChapter(page, `e2e 抽卡失败 ${Date.now()}`);
    await page.route("**/cast/ai-review", (r) => r.fulfill({ json: REVIEW_TWO_GAPS }));
    await page.route("**/cast/ai-draw", (r) => r.fulfill({ status: 502, json: { detail: "AI 调用失败" } }));
    await stableClick(page.getByTestId("og-cast-review"));
    await expect(page.getByTestId("cr-draw")).toBeVisible({ timeout: 15000 });
    await page.getByTestId("cr-draw").click();
    await expect(page.getByTestId("cr-draw-error")).toBeVisible({ timeout: 20000 });
    const errBlock = page.getByTestId("cr-draw-error");
    await expect(errBlock.getByRole("button", { name: "重试" })).toBeVisible();
    await expect(errBlock.getByRole("button", { name: "自己填一个" })).toBeVisible();
    await expect(errBlock.getByRole("button", { name: "先不抽了" })).toBeVisible();
  } finally {
    await restore();
  }
});

test("多缺人回程：写完一个回结果页，第二个继续可处理", async ({ page }) => {
  const { restore } = await setupSession(page, "trial");
  try {
    await createNovelWithChapter(page, `e2e 多缺人 ${Date.now()}`);
    await page.route("**/cast/ai-review", (r) => r.fulfill({ json: REVIEW_TWO_GAPS }));
    await page.route("**/cast/ai-draw", (r) => r.fulfill({ json: CARDS }));
    await page.route("**/api/novels/*/characters", async (r) => {
      if (r.request().method() === "POST")
        return r.fulfill({ json: { ok: true, data: { id: "c-new", name: "顾先生", role: "配角" } } });
      return r.continue();
    });
    await stableClick(page.getByTestId("og-cast-review"));
    await expect(page.getByTestId("gap-active")).toBeVisible({ timeout: 15000 });
    await page.getByTestId("cr-draw").click();
    await expect(page.getByTestId("cr-pick-card-1")).toBeVisible({ timeout: 15000 });
    await page.getByTestId("cr-pick-card-1").click();
    await expect(page.getByTestId("cr-write")).toBeVisible({ timeout: 10000 });
    await page.getByTestId("cr-write").click();
    // 写入后回结果页：弹窗不关、该缺口转已处理、第二个缺口仍可抽卡
    await expect(page.locator('[data-testid="gap-written"]').or(page.getByText("已写入", { exact: false })).first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("cr-draw").or(page.getByText("延后", { exact: false })).first()).toBeVisible({ timeout: 10000 });
  } finally {
    await restore();
  }
});
