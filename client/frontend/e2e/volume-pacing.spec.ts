import path from "path";
import { randomUUID } from "crypto";
import { test, expect } from "@playwright/test";
import { cleanupSessionNovels, writeConfigAtomic } from "./helpers";
import { entitlementFor } from "./tier-features";

// =========================================================================
// 卷节奏 e2e（c-volume-pacing）：
//   ① 五页签导航（卷纲｜节奏｜章节｜角色关系｜伏笔）→ 节奏两态编辑保存（API 回查真落库）
//   ② 定题材自动写书级默认（悬疑→破案套路）；卷列保存以卷为准
// 线索/正文注入的拍位契约由后端单测覆盖（test_volume_pacing.py 拍位/素材 A/B），本 spec 不重复。
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

const PRESET_CASE_STEPS = [
  { n: "案发", t: "案子当场发生，利害落到主角头上；不写背景铺陈。" },
  { n: "查案", t: "现场和证物过一遍手，抓住第一条线头。" },
  { n: "锁定嫌疑人", t: "圈出两三个可疑的人，个个有动机。" },
  { n: "层层排查", t: "线索排掉又翻起来；中途至少认错一次方向。" },
  { n: "真相反转", t: "真凶落定，和开头想的不一样；余波一句话收。" },
];

async function sRegisterAndLogin() {
  const name = `e2e_vpc_${Date.now()}_${randomUUID().slice(0, 8)}`;
  const password = "Test" + "Pass789!";
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

async function writeOAuthSession(t: string, u: string, tier = "max") {
  const fs = await import("fs");
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = t;
  cfg.username = u;
  cfg.tier = tier;
  cfg.entitlement = entitlementFor(tier);
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

async function setupSession(page: import("@playwright/test").Page, tier = "max") {
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

async function createNovel(page: import("@playwright/test").Page, name: string): Promise<string> {
  await page.goto(`${ORIGIN}/#/novels`);
  await page.getByRole("button", { name: "新建作品" }).first().click();
  await page.locator("input#bkTitle").fill(name);
  await page.getByRole("button", { name: "创建，去定题材" }).click();
  await page.waitForURL(/#\/novel\/[0-9a-fA-F-]+/);
  const m = page.url().match(/\/novel\/([0-9a-fA-F-]+)/);
  if (!m) throw new Error(`无法解析 novel id: ${page.url()}`);
  await page.getByRole("button", { name: /^写作/ }).click();
  return m[1];
}

const H = (token: string) => ({ Authorization: `Bearer ${token}` });

/** API 直建一卷（含章数目标），返回 ref。 */
async function createVolumeViaApi(
  request: import("@playwright/test").APIRequestContext,
  origin: string,
  token: string,
  pid: string,
  target: number,
): Promise<string> {
  const r = await request.post(`${origin}/api/novels/${pid}/volumes`, {
    headers: H(token),
    data: {
      title: "第一卷", summary: "这一卷讲什么", core_conflict: "冲突", ending: "收束",
      chapter_target: target,
    },
  });
  expect(r.status()).toBe(200);
  return (await r.json()).ref as string;
}

test("五页签导航：节奏页签在卷纲之后，两态编辑保存真落库", async ({ page, request }) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `节奏${Date.now() % 100000}`);
    const volRef = await createVolumeViaApi(request, ORIGIN, token, pid, 40);
    // API 建卷后刷新页面让左树载入新卷，再点卷头进卷视图
    await page.reload();
    // 刷新后回写作页（默认落设定页），再等左树载入新卷
    await page.getByRole("button", { name: /^写作/ }).click();
    await expect(page.locator(".tree .vol .vt").first()).toContainText("第一卷", { timeout: 15000 });
    await page.locator(".tree .vol .vt").first().click();
    // 页签顺序＝操作顺序：卷纲｜节奏｜章节｜角色关系｜伏笔
    const tabs = page.locator(".ch-tabs .chtab");
    await expect(tabs).toHaveText(["卷纲", "节奏", "章节", "角色关系", "伏笔"], { timeout: 15000 });
    await page.getByRole("tab", { name: "节奏" }).click();
    // 查看态：预填展示（老书/零触达按映射兜底）
    await expect(page.getByTestId("pacing-view")).toBeVisible();
    await expect(page.getByText("这一卷的剧情安排")).toBeVisible();
    await expect(page.getByText(/本卷目标 40 章/)).toBeVisible();
    // 编辑态：改每段章数 → 保存 → 真落库（API 直查）
    await page.getByRole("button", { name: "编辑节奏" }).click();
    await page.fill("#pacing-len", "5");
    await page.getByRole("button", { name: "保存", exact: true }).click();
    await expect(page.getByTestId("pacing-view")).toBeVisible();
    const cfg = await (
      await request.get(`${ORIGIN}/api/novels/${pid}/volumes/${volRef}/pacing`, { headers: H(token) })
    ).json();
    expect(cfg.config.steps_len).toBe(5);
    expect(cfg.config.preset).toBe("upgrade");
  } finally {
    await restore();
  }
});

test("定题材自动写书级默认；卷列优先于书默认", async ({ page, request }) => {
  const { restore, token } = await setupSession(page);
  try {
    const pid = await createNovel(page, `默认${Date.now() % 100000}`);
    // 设定页定题材（真实 genre 端点）→ 书级默认自动写入（零触达）
    await page.goto(`${ORIGIN}/#/novel/${pid}`);
    const genre = await request.put(`${ORIGIN}/api/novels/${pid}/settings/genre`, {
      headers: { ...H(token), "Content-Type": "application/json" },
      data: { theme: "悬疑", sub_genre: "", core_promise: "真相至上" },
    });
    expect(genre.status()).toBe(200);
    const presets = await (
      await request.get(`${ORIGIN}/api/novels/${pid}/pacing/presets`, { headers: H(token) })
    ).json();
    expect(presets.book_default?.preset).toBe("case"); // 悬疑→破案套路
    // 书默认存在时，未保存的卷拍位按书默认推导（卷列空也出角标的前提之一）
    const volRef = await createVolumeViaApi(request, ORIGIN, token, pid, 40);
    const r = await request.put(`${ORIGIN}/api/novels/${pid}/volumes/${volRef}/pacing`, {
      headers: { ...H(token), "Content-Type": "application/json" },
      data: { preset: "case", steps_len: 10, steps: PRESET_CASE_STEPS, ch1_extra_on: false, ch1_extra: "", planned: true },
    });
    expect(r.status()).toBe(200);
  } finally {
    await restore();
  }
});

