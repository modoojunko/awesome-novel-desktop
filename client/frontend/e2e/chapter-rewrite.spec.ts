import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page, type APIRequestContext } from "@playwright/test";
import { cleanupSessionNovels, stableClick } from "./helpers";
import { entitlementFor } from "./tier-features";

// =========================================================================
// 重写这一章 E2E（chapter-rewrite，全链真后端）：
//   ① 已归档章「重写这一章」→ 影响面确认 → 旧稿入支线（-r{hash} ref）＋本章解锁
//   ② 下游章挂「基于旧设定」角标（树行）
//   ③ 下游章自身改写（自动保存）→ 角标消失
//   ④ 旧稿支线可点开只读查看
// 手法与 plot-sim.spec.ts 一致：S端 真注册登录 + config.json 注入。
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
const TEST_PASSWORD = ["TestPass", "789!"].join("");

async function sRegisterAndLogin() {
  const name = `e2e_rw_${Date.now()}_${randomUUID().slice(0, 8)}`;
  const reg = await fetch(`${S_API}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: name,
      password: TEST_PASSWORD,
      security_question: "最喜欢的颜色",
      security_answer: "蓝色",
    }),
  });
  const regBody = await reg.json();
  if (regBody.code !== 0) throw new Error(`S端 register 失败: ${JSON.stringify(regBody)}`);
  const login = await fetch(`${S_API}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: name, password: TEST_PASSWORD }),
  });
  const loginBody = await login.json();
  if (loginBody.code !== 0) throw new Error(`S端 login 失败: ${JSON.stringify(loginBody)}`);
  return { token: loginBody.data.token as string, username: name };
}

async function writeOAuthSession(t: string, u: string, tier = "trial") {
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = t;
  cfg.username = u;
  cfg.tier = tier;
  cfg.entitlement = entitlementFor(tier); // 快照单源（tier-features 6.2）
  delete cfg.expires_at;
  cfg.last_login_at = new Date().toISOString();
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

async function setupSession(
  page: Page,
  tier = "trial",
): Promise<{ restore: () => void; token: string }> {
  const { token, username } = await sRegisterAndLogin();
  const restoreConfig = await writeOAuthSession(token, username, tier);
  const restore = async () => {
    await cleanupSessionNovels(ORIGIN, token);
    restoreConfig();
  };
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  await page.route("**/api/auth/check-auth", (r) =>
    r.fulfill({ json: { code: 0, data: {} } }),
  );
  return { restore, token };
}

/** 建书 + 一卷两章，返回 project id；第 1、2 章均写好正文并归档（API 直备料）。 */
async function seedTwoArchivedChapters(
  page: Page,
  request: APIRequestContext,
  token: string,
  name: string,
) {
  await page.goto(`${ORIGIN}/#/novels`);
  await stableClick(page.getByRole("button", { name: "新建作品" }).first());
  await page.locator("input#bkTitle").fill(name);
  await page.getByRole("button", { name: "创建，去写简介" }).click();
  await page.waitForURL(/#\/novel\/[0-9a-fA-F-]+/);
  const pid = page.url().match(/#\/novel\/([0-9a-fA-F-]+)/)![1];

  const base = `${ORIGIN}/api/novels/${pid}`;
  const auth = { Authorization: `Bearer ${token}` };
  // 建卷 + 两章（API 备料，绕过排队门禁的顺序限制：直接建章）
  await request.post(`${base}/volumes`, {
    data: { title: "第一卷" },
    headers: auth,
  });
  for (const no of (["1", "2"] as const)) {
    const rc = await request.post(`${base}/volumes/vol-1/chapters`, {
      data: { title: `第${no}章` },
      headers: auth,
    });
    expect(rc.ok()).toBeTruthy();
    const ref = `vol-1-ch-${no}`;
    const text = `第${no}章的正文内容，足够长以通过归档校验。`.repeat(8);
    const rp = await request.put(`${base}/chapters/${ref}/prose`, {
      data: { prose: text },
      headers: auth,
    });
    expect(rp.ok()).toBeTruthy();
    const ra = await request.post(`${base}/chapters/${ref}/archive`, {
      data: { full_text: text },
      headers: auth,
    });
    expect(ra.ok()).toBeTruthy();
  }
  return pid;
}

test("重写已归档章：旧稿入支线＋下游角标＋改写后角标消失", async ({
  page,
  request,
}) => {
  test.setTimeout(90_000); // 全链用例（备料+重写+改写+刷新回读）超过默认 30s
  const { restore, token } = await setupSession(page);
  try {
    await seedTwoArchivedChapters(page, request, token, `e2e-rw-${Date.now()}`);
    await page.reload();
    // 全归档书落点默认「预览」→ 切回写作视图（按原型落点规则）
    await page.locator(".mtab", { hasText: "写作" }).click();
    const chRows = page.locator(".col-tree .ch");
    await expect(chRows.first()).toBeVisible({ timeout: 10000 });
    // 章节行序 = 章号升序；第 1 章 = first，第 2 章 = nth(1)
    await chRows.first().click();
    await expect(page.getByRole("tab", { name: /^章纲/ })).toBeVisible({
      timeout: 10000,
    });

    // ① 操作页签：重写卡 → 影响面确认
    await page.getByRole("tab", { name: /^操作/ }).click();
    const rewriteBtn = page.getByTestId("rewrite-btn");
    await expect(rewriteBtn).toBeVisible({ timeout: 10000 });
    await rewriteBtn.click();
    const rwList = page.locator(".rw-list");
    await expect(rwList.getByText(/转入旧稿支线/)).toBeVisible();
    await page.getByTestId("rewrite-confirm").click();
    await expect(page.getByText(/旧稿已留存/)).toBeVisible({ timeout: 10000 });

    // 本章解锁：落在正文页签且可编辑
    await expect(page.locator(".editor")).toBeVisible({ timeout: 10000 });
    await expect(page.locator(".editor")).toHaveAttribute("contenteditable", "true");

    // ② 旧稿支线出现（ghost 分组）＋第 2 章挂「基于旧设定」角标
    await expect(page.locator(".ghost-group").first()).toBeVisible({ timeout: 10000 });
    const stale2 = chRows.nth(1).locator('[data-testid="ch-stale"]');
    await expect(stale2).toHaveCount(1, { timeout: 10000 });

    // ③′ 归档（重写后的）本章 → 提示点名下游角标（spec：存在下游「基于旧设定」时追加）
    const onDlg = (d: import("@playwright/test").Dialog) => d.accept();
    page.on("dialog", onDlg);
    // 归档入口在操作页签（2026-09-27 自头部移入）
    await page.getByRole("tab", { name: /^操作/ }).click();
    await page.getByRole("button", { name: "归档本章" }).click();
    // 归档弹窗：受理制预告＋收尾计划（c-chapter-dossier：两件 PRO 提案＋变化全档说明）
    const plan = page.getByTestId("archive-plan");
    await expect(plan).toBeVisible();
    await expect(plan.getByText(/随归档自动提取/)).toBeVisible();
    await expect(plan).toContainText("登记伏笔");
    await expect(plan).toContainText("随归档自动提取");
    await page.getByTestId("arch-confirm").click();
    try {
      await expect(page.getByText(/下游章节标记「基于旧设定」/)).toBeVisible({
        timeout: 10000,
      });
    } finally {
      page.off("dialog", onDlg);
    }

    // ④ 旧稿可点开只读查看（点旧稿→切正文；重挂竞态用重试吸收）
    await page.locator(".ghost-group .ghost-row").first().click();
    await expect(async () => {
      await page.getByRole("tab", { name: /^正文/ }).click();
      await expect(page.locator(".editor")).toBeVisible({ timeout: 1500 });
    }).toPass({ timeout: 20000 });
    await expect(page.locator(".editor")).toHaveAttribute("contenteditable", "false", {
      timeout: 10000,
    });

    // ③ 回第 2 章改写 → 角标消失（点章回落章纲页签，重试式切正文）
    await chRows.nth(1).click();
    await expect(async () => {
      await page.getByRole("tab", { name: /^正文/ }).click();
      await expect(page.locator(".editor")).toBeVisible({ timeout: 1500 });
    }).toPass({ timeout: 20000 });
    await page.getByTestId("prose-edit").click(); // c-prose-edit-gate：先进编辑态
    await page.locator(".editor").click();
    await page.keyboard.type("补写一段。");
    await expect(page.getByText("已自动保存").first()).toBeVisible({ timeout: 8000 });
    await expect(stale2).toHaveCount(0, { timeout: 10000 });

    // 刷新后仍无角标、旧稿仍在（全书归档 → 落预览，先切回写作视图）
    await page.reload();
    await page.locator(".mtab", { hasText: "写作" }).click();
    await expect(page.locator(".ghost-group").first()).toBeVisible({ timeout: 10000 });
    await expect(chRows.nth(1).locator('[data-testid="ch-stale"]')).toHaveCount(0);
  } finally {
    await restore();
  }
});
