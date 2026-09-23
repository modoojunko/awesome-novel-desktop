import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page } from "@playwright/test";
import { cleanupSessionNovels, stableClick, writeConfigAtomic } from "./helpers";

// =========================================================================
// c-chapter-plan-ai 卷下拆章 e2e：中栏手写五段全链／右栏 AI 四态（打桩）／
// 落点卡三出口／派生视图／免费档锁定／删章守卫 409。
// AI 端点全部 page.route 打桩；章真落库；「不落库」后端直查。
// =========================================================================

// 隔离栈可参数化（per-session 规则：自己的 S端端口/数据目录）
const S_API = process.env.E2E_S_API || "http://127.0.0.1:19000/api/web";
const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
const CONFIG_PATH = path.join(
  process.env.E2E_CLIENT_DATA || path.join(process.cwd(), "..", "..", ".docker-data", "client"),
  "config.json",
);

async function sRegisterAndLogin() {
  const name = `e2e_cpa_${Date.now()}_${randomUUID().slice(0, 8)}`;
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
  cfg.expires_at = tier === "none" ? "" : "2099-12-31";
  // 会话三件套（既有 spec 同款）：fresh last_login_at＋随机 pc_hash——真设备哈希会 401
  cfg.last_login_at = new Date().toISOString();
  cfg.pc_hash = randomUUID().replace(/-/g, "");
  // 后端会用内存态回写 config.json（既有 spec 的稳定轮询：写到自己这版连续两次不被覆盖）
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

/** 建书 → 建第一卷（四问手写）→ 回写作视图（卷选中） */
async function createNovelWithVolume(page: Page, name: string): Promise<string> {
  await page.goto(`${ORIGIN}/#/novels`);
  await stableClick(page.getByRole("button", { name: "新建作品" }).first());
  await page.locator("input#bkTitle").fill(name);
  await page.getByRole("button", { name: "创建，去写简介" }).click();
  await page.waitForURL(/#\/novel\/[0-9a-fA-F-]+/);
  const m = page.url().match(/\/novel\/([0-9a-fA-F-]+)/);
  if (!m) throw new Error(`无法解析 novel id: ${page.url()}`);
  await page.getByRole("button", { name: /^写作/ }).click();
  // 空书起手卡先就位，再进规划台（右栏入口）
  await expect(page.getByText("这本书怎么开始？")).toBeVisible({ timeout: 15000 });
  await page.getByTestId("plan-first-volume").click();
  // PRO 档先进抽卡 → 切四问手写（免费档直接是四问页）
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
  return m[1];
}

const DIRECTIONS = {
  ok: true,
  entry: { text: "她把信标藏进舱底夹层，签了那张登记单", source: "拟定，取自章纲落点" },
  directions: [
    { axis: "线索", title: "同名档案", plot: "她调出那份记录，最后一页被撕掉了", obstacle: "旧档堆不对活人开放",
      ending: "她把残角收进怀里", acts: ["她：调档"], stage: "矛盾升级", cast: ["沉舟"], factions: [], places: [], why: "撕页钩子立住了", gap: "阻力偏程序化" },
    { axis: "关系", title: "船队的条件", plot: "船队长开价换航线", obstacle: "让出航线＝交出一半生存空间",
      ending: "她换来留在船上的许可", acts: ["船队长：开价"], stage: "矛盾升级", cast: [], factions: [], places: [], why: "让出航线真的疼", gap: "结尾停在安全" },
    { axis: "危机", title: "突击清查", plot: "清查队登船前她带信标出逃", obstacle: "挨船搜舱，藏无可藏",
      ending: "信标暴露——全港都知道", acts: ["清查队：搜舱"], stage: "重要转折", cast: [], factions: [], places: [], why: "外部事件当面压上来", gap: "" },
  ],
  grades: ["A", "B", "S"],
  checks: ["这一章把信标暴露提前了"],
  warnings: [],
  note: "",
};

test("手写路径全链：中栏拆下一章 → 五段 → 排上 → 落点卡（已带入 N 项＋还差 6 项＋三出口）", async ({ page, request }) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovelWithVolume(page, `拆章手写${Date.now() % 100000}`);
    await page.route("**/next-chapter-anchor", (r) =>
      r.fulfill({ json: { ok: true, text: "（第一卷第一章）", source: "本章是这一卷的第一章" } }));
    // 中栏入口（全档）
    await page.getByTestId("volume-split-manual").click();
    await expect(page.getByTestId("chapter-plan-modal")).toBeVisible({ timeout: 5000 });
    await expect(page.getByTestId("d-prev")).toBeVisible();
    await page.getByTestId("d-title").fill("信标进舱");
    await page.getByTestId("d-plot").fill("沉舟在废弃星港捡到信标，先藏了下来");
    await page.getByTestId("d-obstacle").fill("没人相信一个见习导航员");
    await page.getByTestId("d-ending").fill("她把信标藏进舱底夹层");
    await page.getByTestId("d-acts").fill("沉舟：藏信标");
    await page.getByTestId("split-adopt").click();
    // 落点卡（桥）
    await expect(page.getByTestId("chapter-landing-card")).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId("chapter-landing-card")).toContainText("还差 6 项才能开写");
    await expect(page.getByTestId("chapter-landing-outline")).toBeVisible();
    await expect(page.getByTestId("chapter-landing-next")).toBeVisible();
    await expect(page.getByTestId("chapter-landing-unsplit")).toBeVisible();
    // 不落库直查：五段真落库（章档案）
    const H = { Authorization: `Bearer ${token}` };
    const ch = await (await request.get(`${ORIGIN}/api/novels/${pid}/chapters/vol-1-ch-1`, { headers: H })).json();
    expect(ch?.data?.plot ?? ch?.plot ?? "").toContain("沉舟在废弃星港");
  } finally {
    await restore();
  }
});

test("AI 四态：正在想 → 三卡（角标＋剧情吸引力）→ 选卡 → 排上", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    await createNovelWithVolume(page, `拆章AI${Date.now() % 100000}`);
    let release!: (v?: unknown) => void;
    const gate = new Promise<void>((r) => { release = r; });
    await page.route("**/ai-directions", async (r) => { await gate; await r.fulfill({ json: DIRECTIONS }); });
    // 右栏入口（PRO）
    await page.getByTestId("volume-split-ai").click();
    await expect(page.getByTestId("split-busy")).toBeVisible({ timeout: 5000 });
    release();
    await expect(page.getByTestId("pick-grid")).toBeVisible({ timeout: 10000 });
    await expect(page.locator(".pick-card")).toHaveCount(3);
    await expect(page.getByTestId("pick-corner-3")).toContainText("S");
    await expect(page.getByTestId("pick-corner-3")).toContainText("最吸引");
    await expect(page.getByTestId("pick-read-1")).toContainText("剧情吸引力");
    await expect(page.getByTestId("split-checks")).toContainText("信标暴露");
    // 选 S 卡 → 本章卡（角标跟到卡上）→ 排上
    await page.getByTestId("pick-card-3").click();
    await expect(page.getByTestId("chapter-card-grade")).toContainText("S");
    await page.getByTestId("split-adopt").click();
    await expect(page.getByTestId("chapter-landing-card")).toBeVisible({ timeout: 10000 });
  } finally {
    await restore();
  }
});

test("AI 失败三出口：重试／自己写这一章／先不拆", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    await createNovelWithVolume(page, `拆章失败${Date.now() % 100000}`);
    await page.route("**/ai-directions", (r) => r.fulfill({ status: 500, json: { detail: "boom" } }));
    await page.getByTestId("volume-split-ai").click();
    await expect(page.getByTestId("split-error")).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId("split-retry")).toBeVisible();
    await expect(page.getByTestId("split-to-manual")).toBeVisible();
    await expect(page.getByTestId("split-close")).toBeVisible();
    // 自己写这一章 → 手写五段
    await page.getByTestId("split-to-manual").click();
    await expect(page.getByTestId("d-plot")).toBeVisible();
  } finally {
    await restore();
  }
});

test("只出两套：降级说明＋两张卡", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    await createNovelWithVolume(page, `拆章两套${Date.now() % 100000}`);
    await page.route("**/ai-directions", (r) =>
      r.fulfill({ json: { ...DIRECTIONS, directions: DIRECTIONS.directions.slice(0, 2), grades: ["A", "B"], note: "另两个走向太接近" } }));
    await page.getByTestId("volume-split-ai").click();
    await expect(page.getByTestId("split-note")).toContainText("只想出两套", { timeout: 10000 });
    await expect(page.locator(".pick-card")).toHaveCount(2);
  } finally {
    await restore();
  }
});

test("派生视图：排上后卷页「剧情推进（派生）」按章列出阶段", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    await createNovelWithVolume(page, `拆章派生${Date.now() % 100000}`);
    await page.route("**/next-chapter-anchor", (r) => r.fulfill({ json: { ok: true, text: "起点", source: "首卷" } }));
    await page.getByTestId("volume-split-manual").click();
    await page.getByTestId("d-title").fill("信标进舱");
    await page.getByTestId("d-plot").fill("捡到信标");
    await page.getByTestId("d-stage").selectOption("开局铺垫");
    await page.getByTestId("split-adopt").click();
    await expect(page.getByTestId("chapter-landing-card")).toBeVisible({ timeout: 10000 });
    await page.getByTestId("chapter-landing-outline").click();
    await expect(page.getByTestId("vol-plot-progress")).toContainText("开局铺垫", { timeout: 10000 });
    await expect(page.getByTestId("vol-plot-progress")).toContainText("信标进舱");
  } finally {
    await restore();
  }
});

test("免费档：右栏 AI 入口锁定（PRO 说明），中栏手写照常可用", async ({ page }) => {
  const { restore } = await setupSession(page, "trial");
  try {
    await createNovelWithVolume(page, `拆章免费${Date.now() % 100000}`);
    const fs = await import("fs");
    const cfg = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf-8"));
    cfg.tier = "none"; cfg.expires_at = "";
    fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2));
    await page.reload();
    await page.getByRole("button", { name: /^写作/ }).click();
    // 锁定态
    await expect(page.getByTestId("volume-split-ai")).toBeDisabled();
    await expect(page.getByTestId("volume-split-ai-locked")).toBeVisible();
    // 手写照常
    await page.route("**/next-chapter-anchor", (r) => r.fulfill({ json: { ok: true, text: "起点", source: "首卷" } }));
    await page.getByTestId("volume-split-manual").click();
    await expect(page.getByTestId("d-plot")).toBeVisible({ timeout: 5000 });
  } finally {
    await restore();
  }
});

test("删章守卫：非尾章 409（先删其后或重拆）", async ({ page, request }) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovelWithVolume(page, `拆章守卫${Date.now() % 100000}`);
    await page.route("**/next-chapter-anchor", (r) => r.fulfill({ json: { ok: true, text: "起点", source: "首卷" } }));
    // 排两章
    for (const t of ["第一章", "第二章"]) {
      await page.getByTestId("volume-split-manual").click();
      await page.getByTestId("d-title").fill(t);
      await page.getByTestId("d-plot").fill(`${t}的剧情`);
      await page.getByTestId("split-adopt").click();
      await expect(page.getByTestId("chapter-landing-card")).toBeVisible({ timeout: 10000 });
      await page.getByTestId("chapter-landing-next").click();
    }
    const H = { Authorization: `Bearer ${token}` };
    const r = await request.delete(`${ORIGIN}/api/novels/${pid}/chapters/vol-1-ch-1`, { headers: H });
    expect(r.status()).toBe(409);
    const r2 = await request.delete(`${ORIGIN}/api/novels/${pid}/chapters/vol-1-ch-2`, { headers: H });
    expect(r2.status()).toBe(200);
  } finally {
    await restore();
  }
});
