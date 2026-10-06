import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page } from "@playwright/test";
import { cleanupSessionNovels, stableClick, writeConfigAtomic } from "./helpers";
import { entitlementFor } from "./tier-features";

// =========================================================================
// c-chapter-plan-ai 卷下拆章 e2e：中栏手写四段全链／右栏 AI 四态（打桩）／
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
  cfg.entitlement = entitlementFor(tier); // 快照单源（tier-features 6.2）
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

/** 卷纲页签 → 本卷章节页签（c-split-to-chapters-tab 起拆章入口住本页签） */
async function goChaptersTab(page: Page) {
  await page.getByRole("tab", { name: "本卷章节" }).click();
}

const DIRECTIONS = {
  ok: true,
  entry: { text: "她把信标藏进舱底夹层，签了那张登记单", source: "拟定，取自章纲落点" },
  directions: [
    { axis: "线索", title: "同名档案", plot: "她调出那份记录，最后一页被撕掉了", obstacle: "旧档堆不对活人开放",
      ending: "她把残角收进怀里", stage: "矛盾升级", cast: ["沉舟"], factions: [], places: [], why: "撕页钩子立住了", gap: "阻力偏程序化" },
    { axis: "关系", title: "船队的条件", plot: "船队长开价换航线", obstacle: "让出航线＝交出一半生存空间",
      ending: "她换来留在船上的许可", stage: "矛盾升级", cast: [], factions: [], places: [], why: "让出航线真的疼", gap: "结尾停在安全" },
    { axis: "危机", title: "突击清查", plot: "清查队登船前她带信标出逃", obstacle: "挨船搜舱，藏无可藏",
      ending: "信标暴露——全港都知道", stage: "重要转折", cast: [], factions: [], places: [], why: "外部事件当面压上来", gap: "" },
  ],
  grades: ["A", "B", "S"],
  checks: ["这一章把信标暴露提前了"],
  warnings: [],
  note: "",
};

test("手写路径全链：中栏拆下一章 → 四段 → 排上 → 落点卡（已带入 N 项＋还差 2 项＋三出口）", async ({ page, request }) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovelWithVolume(page, `拆章手写${Date.now() % 100000}`);
    await page.route("**/next-chapter-anchor", (r) =>
      r.fulfill({ json: { ok: true, text: "（第一卷第一章）", source: "本章是这一卷的第一章" } }));
    // 中栏入口（全档；c-split-to-chapters-tab 起在本卷章节页签）
    await goChaptersTab(page);
    await page.getByTestId("volume-split-manual").click();
    await expect(page.getByTestId("chapter-plan-modal")).toBeVisible({ timeout: 5000 });
    // kicker 点名卷号与章号（照原型：卷＝汉字、章＝数字，X＝锚的 next_no）
    await expect(page.locator(".chapter-plan .kicker")).toHaveText("卷下拆章 · 第一卷 · 第1章");
    await expect(page.getByTestId("d-prev")).toBeVisible();
    await page.getByTestId("d-title").fill("信标进舱");
    await page.getByTestId("d-plot").fill("沉舟在废弃星港捡到信标，先藏了下来");
    await page.getByTestId("d-obstacle").fill("没人相信一个见习导航员");
    await page.getByTestId("d-ending").fill("她把信标藏进舱底夹层");
    await page.getByTestId("split-adopt").click();
    // 落点卡（桥）
    await expect(page.getByTestId("chapter-landing-card")).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId("chapter-landing-card")).toContainText("还差 2 项才能开写");
    await expect(page.getByTestId("chapter-landing-card")).not.toContainText("核心任务");
    await expect(page.getByTestId("chapter-landing-card")).not.toContainText("读者当前状态");
    // 逐项列出实际带入的四段（空项不冒充：这里填了 剧情/挑战/结尾 + 阶段默认值）
    await expect(page.getByTestId("chapter-landing-card")).toContainText("已带入 4 项");
    await expect(page.getByTestId("chapter-landing-card")).toContainText("本章剧情、碰到的挑战、本章结尾、阶段");
    await expect(page.getByTestId("chapter-landing-outline")).toBeVisible();
    await expect(page.getByTestId("chapter-landing-next")).toBeVisible();
    await expect(page.getByTestId("chapter-landing-unsplit")).toBeVisible();
    // 不落库直查：四段真落库（assemble 直出键 outline.summary／challenge／ladder_exit／plot_stage）
    // c-og-slim-v2：「本章行动」退役——载荷不再带该键、装配也不再输出
    const H = { Authorization: `Bearer ${token}` };
    const ch = await (await request.get(`${ORIGIN}/api/novels/${pid}/chapters/vol-1-ch-1`, { headers: H })).json();
    expect(ch?.outline?.summary ?? "").toContain("沉舟在废弃星港");
    expect(ch?.challenge ?? "").toContain("没人相信一个见习导航员");
    expect(ch?.ladder_exit ?? "").toContain("舱底夹层");
    expect(ch?.plot_stage ?? "").toContain("开局铺垫");
    expect(ch?.chapter_acts).toBeUndefined();
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
    // 右栏入口（PRO；随本卷章节页签出现）
    await goChaptersTab(page);
    await page.getByTestId("volume-split-ai").click();
    await expect(page.getByTestId("split-busy")).toBeVisible({ timeout: 5000 });
    // busy 态阶段列表（c-chapter-draw-retry-material）：三段在场、随等待推进
    await expect(page.getByTestId("split-steps")).toBeVisible();
    await expect(page.getByTestId("split-steps")).toContainText("读卷纲与设定");
    release();
    await expect(page.getByTestId("pick-grid")).toBeVisible({ timeout: 10000 });
    await expect(page.locator(".pick-card")).toHaveCount(3);
    // 三卡态底条＝换一批＋转手写（照原型：不出现「排上」死按钮）；进场行点名章号
    await expect(page.getByTestId("split-entry-line")).toContainText("第一章的 3 个剧情方向 · 进场已接上");
    await expect(page.getByTestId("split-redraw")).toBeVisible();
    await expect(page.getByTestId("split-adopt")).toHaveCount(0);
    await expect(page.getByTestId("pick-corner-3")).toContainText("S");
    await expect(page.getByTestId("pick-corner-3")).toContainText("最吸引");
    await expect(page.getByTestId("pick-read-1")).toContainText("剧情吸引力");
    await expect(page.getByTestId("split-checks")).toContainText("信标暴露");
    // 选 S 卡 → 弹窗切到本章卡（三卡收起，照原型「点卡进入本章卡」）→ 排上按钮点名章号
    await page.getByTestId("pick-card-3").click();
    await expect(page.getByTestId("chapter-card-grade")).toContainText("S");
    await expect(page.getByTestId("pick-grid")).toHaveCount(0);
    await expect(page.getByTestId("split-adopt")).toContainText("排上这一章（第 1 章）");
    // c-og-fields-slim 前身 #478：落地提示独立 hint 行
    await expect(page.locator(".chapter-plan .hint"))
      .toContainText("下一章的进场会自动接「信标暴露——全港都知道」");
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
    await goChaptersTab(page);
    await page.getByTestId("volume-split-ai").click();
    await expect(page.getByTestId("split-error")).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId("split-retry")).toBeVisible();
    await expect(page.getByTestId("split-to-manual")).toBeVisible();
    await expect(page.getByTestId("split-close")).toBeVisible();
    // 自己写这一章 → 手写四段
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
    await goChaptersTab(page);
    await page.getByTestId("volume-split-ai").click();
    await expect(page.getByTestId("split-note")).toContainText("只想出两套", { timeout: 10000 });
    await expect(page.locator(".pick-card")).toHaveCount(2);
  } finally {
    await restore();
  }
});

test("自检：手写卡底条「AI 看一眼这一章」→ 三组（衔接/配额/四维短评）", async ({ page, request }) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovelWithVolume(page, `拆章自检${Date.now() % 100000}`);
    await page.route("**/next-chapter-anchor", (r) => r.fulfill({ json: { ok: true, text: "起点", source: "首卷" } }));
    await page.route("**/ai-selfcheck", (r) =>
      r.fulfill({
        json: {
          ok: true,
          link: { ok: true, text: "本章进场已自动接上上一章结尾" },
          quota: { ok: true, text: "第 1 章，本卷目标 6 章" },
          critiques: { 反转: "撕页立住了", 递增: "阻力偏程序化", 推进: "处境变了", 拉力: "停在决定上" },
          weakest: "递增",
        },
      }));
    await goChaptersTab(page);
    await page.getByTestId("volume-split-manual").click();
    await expect(page.getByTestId("d-title")).toBeVisible({ timeout: 10000 });
    await page.getByTestId("d-plot").fill("捡到信标");
    await page.getByTestId("selfcheck-run").click();
    const box = page.getByTestId("selfcheck");
    await expect(box).toContainText("衔接：本章进场已自动接上上一章结尾", { timeout: 10000 });
    await expect(box).toContainText("配额：第 1 章，本卷目标 6 章");
    await expect(box).toContainText("剧情吸引力 · 反转：撕页立住了");
    await expect(box).toContainText("最弱一维：递增");
    // 排上之前也能自检（章未落库）——真后端不许 404/422：卡面草稿随请求体走
    const r = await request.post(`${ORIGIN}/api/novels/${pid}/chapters/ai-selfcheck`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { vol_ref: "vol-1", entry_text: "", title: "信标进舱", plot: "捡到信标" },
    });
    // 200＝有模型；503＝未配模型的引导（设计如此，不 500）。404/422 即路径或请求体契约错
    expect([200, 503]).toContain(r.status());
  } finally {
    await restore();
  }
});

test("派生视图：排上后卷页「剧情推进（派生）」按章列出阶段", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    await createNovelWithVolume(page, `拆章派生${Date.now() % 100000}`);
    await page.route("**/next-chapter-anchor", (r) => r.fulfill({ json: { ok: true, text: "起点", source: "首卷" } }));
    await goChaptersTab(page);
    await page.getByTestId("volume-split-manual").click();
    await page.getByTestId("d-title").fill("信标进舱");
    await page.getByTestId("d-plot").fill("捡到信标");
    await page.getByTestId("d-stage").selectOption("开局铺垫");
    await page.getByTestId("split-adopt").click();
    await expect(page.getByTestId("chapter-landing-card")).toBeVisible({ timeout: 10000 });
    // 「补这 4 项，开始写」→ 落到这一章的章纲
    await page.getByTestId("chapter-landing-outline").click();
    await expect(page.getByTestId("og-edit")).toBeVisible({ timeout: 10000 });
    // 回卷页（左树点卷行）看派生块
    await page.locator(".vol-head .vt").first().click();
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
    // reload 后无选中节点 → 点左树卷行回卷纲视图（右栏才是卷语境）
    await page.locator(".vol-head .vt").first().click();
    // 锁定态（拆章 AI 行已迁本卷章节页签）
    await goChaptersTab(page);
    await expect(page.getByTestId("volume-split-ai")).toBeDisabled();
    await expect(page.getByTestId("volume-split-ai-locked")).toBeVisible();
    // 锁定态要有**可点的**升级出口（原实现把 onUpgrade 放在 disabled 按钮里＝死代码）
    await expect(page.getByTestId("volume-split-ai-upgrade")).toBeEnabled();
    // 手写照常
    await page.route("**/next-chapter-anchor", (r) => r.fulfill({ json: { ok: true, text: "起点", source: "首卷" } }));
    await page.getByTestId("volume-split-manual").click();
    await expect(page.getByTestId("d-plot")).toBeVisible({ timeout: 5000 });
  } finally {
    await restore();
  }
});

test("免费档自检拦截：点「AI 看一眼」走升级出口，selfcheck 零请求（c-tier-gating-completion）", async ({ page }) => {
  const { restore } = await setupSession(page, "none");
  try {
    await createNovelWithVolume(page, `自检拦截${Date.now() % 100000}`);
    await page.getByRole("button", { name: /^写作/ }).click();
    await page.locator(".vol-head .vt").first().click();
    await goChaptersTab(page);
    let selfcheckCalls = 0;
    await page.route("**/ai-selfcheck", (r) => {
      selfcheckCalls += 1;
      r.fulfill({ json: { ok: true } });
    });
    await page.route("**/next-chapter-anchor", (r) => r.fulfill({ json: { ok: true, text: "起点", source: "首卷" } }));
    await page.getByTestId("volume-split-manual").click();
    await expect(page.getByTestId("d-plot")).toBeVisible({ timeout: 5000 });
    // 免费档：胶囊在、点击不发请求、走全局升级引导（规格 SHALL NOT 发起调用）
    await expect(page.getByTestId("selfcheck-locked")).toBeVisible();
    await page.getByTestId("selfcheck-run").click();
    await expect(page.getByTestId("member-block-prompt")).toBeVisible();
    expect(selfcheckCalls).toBe(0);
  } finally {
    await restore();
  }
});

test("删章守卫：非尾章 409（先删其后或重拆）", async ({ page, request }) => {
  test.setTimeout(60000); // 两轮拆章＋两发直查，30s 不够
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovelWithVolume(page, `拆章守卫${Date.now() % 100000}`);
    await page.route("**/next-chapter-anchor", (r) => r.fulfill({ json: { ok: true, text: "起点", source: "首卷" } }));
    // 排两章：首轮走中栏入口（本卷章节页签）；次轮由落点卡「继续拆下一章」打开手写卡（弹窗已开，别再点入口）
    await goChaptersTab(page);
    for (const [i, t] of ["第一章", "第二章"].entries()) {
      if (i === 0) await page.getByTestId("volume-split-manual").click();
      await expect(page.getByTestId("d-title")).toBeVisible({ timeout: 10000 });
      await page.getByTestId("d-title").fill(t);
      await page.getByTestId("d-plot").fill(`${t}的剧情`);
      await page.getByTestId("split-adopt").click();
      await expect(page.getByTestId("chapter-landing-card")).toBeVisible({ timeout: 10000 });
      if (i === 0) await page.getByTestId("chapter-landing-next").click();
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

test("换方向：点「换 3 个方向」重新出卡（第二次响应覆盖第一次）", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    await createNovelWithVolume(page, `拆章换向${Date.now() % 100000}`);
    let n = 0;
    await page.route("**/ai-directions", (r) => {
      n += 1;
      const alt = {
        ...DIRECTIONS,
        directions: DIRECTIONS.directions.map((d, i) => ({ ...d, title: `第二版${i + 1}` })),
        grades: ["B", "A", "S"],
      };
      return r.fulfill({ json: n === 1 ? DIRECTIONS : alt });
    });
    await goChaptersTab(page);
    await page.getByTestId("volume-split-ai").click();
    await expect(page.getByTestId("pick-card-1")).toContainText("同名档案", { timeout: 10000 });
    await page.getByTestId("split-redraw").click();
    await expect(page.getByTestId("pick-card-1")).toContainText("第二版1", { timeout: 10000 });
    await expect(page.locator(".pick-card")).toHaveCount(3);
    expect(n).toBe(2);
  } finally {
    await restore();
  }
});

test("双击幂等：提交中锁定＋同 client_token 重放返回同一章", async ({ page, request }) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovelWithVolume(page, `拆章幂等${Date.now() % 100000}`);
    await page.route("**/next-chapter-anchor", (r) => r.fulfill({ json: { ok: true, text: "起点", source: "首卷" } }));
    await goChaptersTab(page);
    await page.getByTestId("volume-split-manual").click();
    await expect(page.getByTestId("d-title")).toBeVisible({ timeout: 10000 });
    await page.getByTestId("d-title").fill("信标进舱");
    await page.getByTestId("d-plot").fill("捡到信标");
    await page.getByTestId("split-adopt").click();
    // 第二次点：提交中锁定（disabled 的按钮不派发 click 处理器）——force 绕过可点性检查仍落空
    await page.getByTestId("split-adopt").click({ force: true }).catch(() => {});
    await expect(page.getByTestId("chapter-landing-card")).toBeVisible({ timeout: 10000 });
    const H = { Authorization: `Bearer ${token}` };
    const d = await (await request.get(`${ORIGIN}/api/novels/${pid}/volumes/vol-1`, { headers: H })).json();
    expect((d?.chapters ?? []).length).toBe(1);

    // 服务端幂等（真断言）：同一 client_token 重放 → 同一章，不再建
    const body = { title: "重放章", plot: "重放", client_token: `e2e-tok-${Date.now()}` };
    const r1 = await request.post(`${ORIGIN}/api/novels/${pid}/volumes/vol-1/chapters`, { headers: H, data: body });
    const r2 = await request.post(`${ORIGIN}/api/novels/${pid}/volumes/vol-1/chapters`, { headers: H, data: body });
    expect(r1.ok() && r2.ok()).toBeTruthy();
    expect(r2.json().ref).toBe(r1.json().ref);
    const after = await (await request.get(`${ORIGIN}/api/novels/${pid}/volumes/vol-1`, { headers: H })).json();
    expect((after?.chapters ?? []).length).toBe(2); // 首次那章 + 重放章（不是 3）
  } finally {
    await restore();
  }
});

test("重拆整卷：盘点确认 → 拟定章清空、卷纲保留、可重新拆", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    await createNovelWithVolume(page, `拆章重拆${Date.now() % 100000}`);
    await page.route("**/next-chapter-anchor", (r) => r.fulfill({ json: { ok: true, text: "起点", source: "首卷" } }));
    await goChaptersTab(page);
    for (const [i, t] of ["第一章", "第二章"].entries()) {
      if (i === 0) await page.getByTestId("volume-split-manual").click();
      await expect(page.getByTestId("d-title")).toBeVisible({ timeout: 10000 });
      await page.getByTestId("d-title").fill(t);
      await page.getByTestId("d-plot").fill(`${t}的剧情`);
      await page.getByTestId("split-adopt").click();
      await expect(page.getByTestId("chapter-landing-card")).toBeVisible({ timeout: 10000 });
      if (i === 0) await page.getByTestId("chapter-landing-next").click();
    }
    // 落点卡占着中栏（桥）——先走「补这 4 项，开始写」消解，再回卷纲
    await page.getByTestId("chapter-landing-outline").click();
    await expect(page.getByTestId("og-edit")).toBeVisible({ timeout: 10000 });
    // 回卷纲 → 重拆本卷：盘点列出将被移除的拟定章
    await page.locator(".vol-head .vt").first().click();
    await page.getByTestId("volume-resplit").click();
    await expect(page.getByTestId("resplit-list")).toContainText("第1章 第一章");
    await expect(page.getByTestId("resplit-list")).toContainText("第2章 第二章");
    await page.getByTestId("resplit-confirm").click();
    await expect(page.getByText(/已清掉 2 章拟定章/)).toBeVisible({ timeout: 10000 });
    // 派生视图归零；卷纲保留（四问原文还在）；重拆入口随拟定章清零消失
    await expect(page.getByTestId("vol-plot-progress")).toContainText("0 章");
    await expect(page.getByText("沉舟捡到一枚不属于人类纪元的导航信标")).toBeVisible();
    await expect(page.getByTestId("volume-resplit")).toHaveCount(0);
    // 可重新拆：章号从 1 复用（不留空洞）；入口在本卷章节页签
    await goChaptersTab(page);
    await page.getByTestId("volume-split-manual").click();
    await page.getByTestId("d-title").fill("重拆后第一章");
    await page.getByTestId("split-adopt").click();
    await expect(page.getByTestId("chapter-landing-card")).toContainText("重拆后第一章", { timeout: 10000 });
  } finally {
    await restore();
  }
});

test("非末端卷：拆章两入口置灰并指向写作位所在卷", async ({ page, request }) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovelWithVolume(page, `拆章末端${Date.now() % 100000}`);
    await page.route("**/next-chapter-anchor", (r) => r.fulfill({ json: { ok: true, text: "起点", source: "首卷" } }));
    // 用产品接口垫第 2 卷并在那里排一章 → 写作位落到第 2 卷
    const H = { Authorization: `Bearer ${token}` };
    const v2 = await request.post(`${ORIGIN}/api/novels/${pid}/volumes`, {
      headers: H,
      data: {
        title: "第二卷",
        summary: "信标把她引向母港旧址",
        core_conflict: "要查清，与母港不认她",
        ending: "她站在母港旧址的闸门前",
      },
    });
    expect(v2.ok()).toBeTruthy();
    const ch = await request.post(`${ORIGIN}/api/novels/${pid}/volumes/vol-2/chapters`, {
      headers: H,
      data: { title: "第2卷第一章", plot: "她抵近母港" },
    });
    expect(ch.ok()).toBeTruthy();
    // 回第 1 卷卷纲：两个入口都置灰
    await page.reload();
    await page.getByRole("button", { name: /^写作/ }).click();
    await page.locator(".vol-head .vt").first().click();
    await goChaptersTab(page);
    await expect(page.getByTestId("volume-split-manual")).toBeDisabled();
    await expect(page.getByTestId("volume-split-blocked")).toContainText("写作位在第2卷");
    await expect(page.getByTestId("volume-split-ai")).toBeDisabled();
    await expect(page.getByTestId("volume-split-ai-blocked")).toContainText("先去那一卷拆章");
  } finally {
    await restore();
  }
});

test("未配模型：出卡失败给「去接一个模型」的就地引导（不报 500）", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    await createNovelWithVolume(page, `拆章缺模${Date.now() % 100000}`);
    // 本栈未配模型：真打端点 → 503 前置 → 卡片给可操作引导（不是通用「出卡失败」）
    await goChaptersTab(page);
    await page.getByTestId("volume-split-ai").click();
    await expect(page.getByTestId("split-error")).toContainText("还没接模型", { timeout: 10000 });
    await expect(page.getByTestId("split-retry")).toBeVisible();
    await expect(page.getByTestId("split-to-manual")).toBeVisible();
  } finally {
    await restore();
  }
});

test("回改结尾：上一章落点改了 → 不静默（提示下一章进场会变）", async ({ page, request }) => {
  test.setTimeout(60000);
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovelWithVolume(page, `拆章回改${Date.now() % 100000}`);
    await page.route("**/next-chapter-anchor", (r) => r.fulfill({ json: { ok: true, text: "起点", source: "首卷" } }));
    // 排两章（第 1 章落点＝旧落点）
    await goChaptersTab(page);
    for (const [i, t] of ["第一章", "第二章"].entries()) {
      if (i === 0) await page.getByTestId("volume-split-manual").click();
      await expect(page.getByTestId("d-title")).toBeVisible({ timeout: 10000 });
      await page.getByTestId("d-title").fill(t);
      await page.getByTestId("d-plot").fill(`${t}的剧情`);
      if (i === 0) await page.getByTestId("d-ending").fill("旧落点：她把信标藏进夹层");
      await page.getByTestId("split-adopt").click();
      await expect(page.getByTestId("chapter-landing-card")).toBeVisible({ timeout: 10000 });
      if (i === 0) await page.getByTestId("chapter-landing-next").click();
    }
    // 落点卡占着中栏：先「补这 4 项，开始写」进第二章，再从树里回第一章
    await page.getByTestId("chapter-landing-outline").click();
    await expect(page.getByTestId("og-edit")).toBeVisible({ timeout: 10000 });

    // 回第 1 章改落点 → 3s 静默自动保存承接（查看态先进编辑；落点组默认折叠，先展开）
    await page.locator(".col-tree .ch", { hasText: "第一章" }).click();
    await page.getByRole("tab", { name: /^章纲/ }).click();
    await page.getByTestId("og-edit").click();
    await page.locator("#wf-payoffs > summary").click();
    const savedOutline = page.waitForResponse(
      (x) => x.request().method() === "PUT" && x.url().includes("/chapters/vol-1-ch-1"),
      { timeout: 20000 },
    );
    await page.locator("#wf-ladder").fill("新落点：她烧掉了那张登记单");
    expect((await savedOutline).ok()).toBeTruthy();
    // 不静默：下一章已排上 → 就地提示「下一章的进场会跟着变」
    await expect(page.getByText(/下一章的进场会跟着变/)).toBeVisible({ timeout: 10000 });
    // 落点真落库（下一章「基于旧设定」标记的置位由后端章保存事务完成——
    // 需下一章已有正文才置位，正文受 frontier 排队门禁约束，故该分支由 pytest 覆盖：
    // tests/test_chapter_plan_ai_t3.py::TestStaleSecondTrigger）
    const vols = await (
      await request.get(`${ORIGIN}/api/novels/${pid}/volumes`, {
        headers: { Authorization: `Bearer ${token}` },
      })
    ).json();
    expect(vols[0]?.chapters?.[0]?.ref).toBe("vol-1-ch-1");
    const ch = await (
      await request.get(`${ORIGIN}/api/novels/${pid}/chapters/vol-1-ch-1`, {
        headers: { Authorization: `Bearer ${token}` },
      })
    ).json();
    expect(ch?.ladder_exit).toContain("烧掉了那张登记单");
  } finally {
    await restore();
  }
});

test("回改：左树 hover「改这一章」→ 同一张卡面（预填四段）→ 保存不新建", async ({ page, request }) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovelWithVolume(page, `拆章回改面${Date.now() % 100000}`);
    await page.route("**/next-chapter-anchor", (r) => r.fulfill({ json: { ok: true, text: "起点", source: "首卷" } }));
    // 先排一章（四段齐）
    await goChaptersTab(page);
    await page.getByTestId("volume-split-manual").click();
    await expect(page.getByTestId("d-title")).toBeVisible({ timeout: 10000 });
    await page.getByTestId("d-title").fill("信标进舱");
    await page.getByTestId("d-plot").fill("捡到信标");
    await page.getByTestId("d-obstacle").fill("没人信她");
    await page.getByTestId("d-ending").fill("藏进夹层");
    await page.getByTestId("d-stage").selectOption("重要转折");
    await page.getByTestId("split-adopt").click();
    await expect(page.getByTestId("chapter-landing-card")).toBeVisible({ timeout: 10000 });
    await page.getByTestId("chapter-landing-outline").click();
    await expect(page.getByTestId("og-edit")).toBeVisible({ timeout: 10000 });

    // 左树章行 hover 动作「改这一章」→ 同一张卡面（预填）
    const chRow = page.locator(".col-tree .ch", { hasText: "第一章" });
    await chRow.hover();
    await chRow.getByTestId("ch-edit").click();
    await expect(page.getByTestId("chapter-plan-modal")).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId("d-title")).toHaveValue("信标进舱", { timeout: 10000 });
    await expect(page.getByTestId("d-plot")).toHaveValue("捡到信标");
    await expect(page.getByTestId("d-obstacle")).toHaveValue("没人信她");
    await expect(page.getByTestId("d-ending")).toHaveValue("藏进夹层");
    await expect(page.getByTestId("d-stage")).toHaveValue("重要转折");
    await expect(page.getByTestId("split-adopt")).toContainText("保存这一章");

    // 改两段 → 保存：走章保存链（不新建章），改后回读一致
    await page.getByTestId("d-ending").fill("改过的落点：她烧掉了登记单");
    await page.getByTestId("d-stage").selectOption("高潮爆发");
    await page.getByTestId("split-adopt").click();
    await expect(page.getByTestId("chapter-plan-modal")).toHaveCount(0, { timeout: 10000 });
    const H = { Authorization: `Bearer ${token}` };
    const ch = await (await request.get(`${ORIGIN}/api/novels/${pid}/chapters/vol-1-ch-1`, { headers: H })).json();
    expect(ch?.ladder_exit).toContain("烧掉了登记单");
    expect(ch?.plot_stage).toBe("高潮爆发");
    const vols = await (await request.get(`${ORIGIN}/api/novels/${pid}/volumes/vol-1`, { headers: H })).json();
    expect((vols?.chapters ?? []).length).toBe(1); // 回改不新建
  } finally {
    await restore();
  }
});

test("回改入口三处：派生视图行也可点开同一张卡面", async ({ page }) => {
  const { restore } = await setupSession(page);
  try {
    await createNovelWithVolume(page, `拆章回改派生${Date.now() % 100000}`);
    await page.route("**/next-chapter-anchor", (r) => r.fulfill({ json: { ok: true, text: "起点", source: "首卷" } }));
    await goChaptersTab(page);
    await page.getByTestId("volume-split-manual").click();
    await expect(page.getByTestId("d-title")).toBeVisible({ timeout: 10000 });
    await page.getByTestId("d-title").fill("信标进舱");
    await page.getByTestId("d-plot").fill("捡到信标");
    await page.getByTestId("split-adopt").click();
    await expect(page.getByTestId("chapter-landing-card")).toBeVisible({ timeout: 10000 });
    await page.getByTestId("chapter-landing-outline").click();
    await expect(page.getByTestId("og-edit")).toBeVisible({ timeout: 10000 });
    await page.locator(".vol-head .vt").first().click();
    // 派生视图行 → 同一张卡面
    await page.getByTestId("vol-plot-row-1").click();
    await expect(page.getByTestId("chapter-plan-modal")).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId("d-title")).toHaveValue("信标进舱", { timeout: 10000 });
    await expect(page.getByTestId("split-adopt")).toContainText("保存这一章");
  } finally {
    await restore();
  }
});
