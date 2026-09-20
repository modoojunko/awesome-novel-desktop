import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page } from "@playwright/test";
import { stubUpdateNotice, cleanupSessionNovels } from "./helpers";

/**
 * 书架工具栏（c-works-toolbar）：状态筛选分组（含已完结 409 透出）、搜索无果清除筛选、
 * 分页加载更多、回看一次性落点（预览）。
 * A/B/C 场景全打桩（runbook ③）；回看落预览走真实后端（落点判定依赖 workbench 真渲染，
 * 沿 landing-view.spec.ts 的会话注入模式）。
 */

const H = 3600_000;
const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
const S_API = process.env.E2E_S_API || "http://127.0.0.1:19000/api/web";
const CONFIG_PATH = path.join(process.cwd(), "..", "..", ".docker-data", "client", "config.json");

function novel(id: string, name: string, over: Record<string, unknown> = {}) {
  return {
    id,
    name,
    slug: id,
    current_phase: "write",
    total_volumes: 2,
    total_chapters: 6,
    total_archives: 0,
    word_count: 1000,
    genre: "玄幻",
    synopsis: "简介。",
    updated_at: new Date(Date.now() - H).toISOString(),
    finished_at: null,
    ...over,
  };
}

async function stubShell(page: Page, novels: unknown[]) {
  await page.addInitScript(() => {
    localStorage.setItem("auth_token", "shelf-toolbar-stub");
    localStorage.setItem("auth_username", "shelfer");
  });
  await page.route("**/api/novels", (r) => r.fulfill({ json: novels }));
  await page.route("**/api/auth/verify", (r) =>
    r.fulfill({ json: { tier: "monthly", is_member: true, expired: false, trial_remaining_days: 0 } }),
  );
  await page.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 1 } }));
  await page.route("**/api/auth/config", (r) =>
    r.fulfill({ json: { has_api_key: true, portal_url: "" } }),
  );
  await stubUpdateNotice(page, "none");
}

test.describe("书架工具栏（打桩）", () => {
  test("已完结 409：分组头去完本 → toast 透出服务端原因（rider F3.1）", async ({ page }) => {
    const ready = novel("t-ready", "沙漏之下", { total_archives: 6 });
    await stubShell(page, [ready]);
    await page.route("**/api/novels/t-ready/hooks", (r) =>
      r.fulfill({ json: { ok: true, data: { count: 0, items: [] } } }));
    await page.route("**/api/novels/t-ready/volumes", (r) => r.fulfill({ json: [] }));
    await page.route("**/api/novels/t-ready/finish", (r) =>
      r.fulfill({ status: 409, json: { detail: "这本书已完结，不用重复完本" } }));
    await page.goto("/#/novels");

    await page.locator('[data-od-id="filter-ready"]').click();
    await page.locator('[data-od-id="group-finish"]').click();
    await expect(page.locator(".modal")).toContainText("完结《沙漏之下》？");
    await page.locator(".modal").getByRole("button", { name: "完结这本书" }).click();
    // 服务端 detail 原样透出——不再是硬编码「先把主线章节全部归档」
    await expect(page.locator(".toast")).toContainText("这本书已完结，不用重复完本");
  });

  test("已完结＋搜索无果 → 清除筛选复原（chip/排序/搜索/列表四复原）", async ({ page }) => {
    const done = novel("t-done", "雾中法庭", {
      total_archives: 9,
      finished_at: new Date(Date.now() - 72 * H).toISOString(),
    });
    await stubShell(page, [done]);
    await page.goto("/#/novels");

    await page.locator('[data-od-id="filter-done"]').click();
    await page.locator('[data-od-id="works-sort"]').selectOption("words");
    await page.getByLabel("搜索书名").fill("不存在的书名");

    const empty = page.locator('[data-od-id="empty-state"]');
    await expect(empty).toContainText("没有找到符合条件的作品");
    await expect(empty).toContainText("换个关键词或状态再试试");

    await page.locator('[data-od-id="empty-clear"]').click();
    // 四复原：chip 回全部 / 排序回最近更新 / 搜索清空 / 列表回全量
    await expect(page.locator('[data-od-id="filter-all"]')).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator('[data-od-id="works-sort"]')).toHaveValue("recency");
    await expect(page.getByLabel("搜索书名")).toHaveValue("");
    await expect(page.locator(".book-card")).toHaveCount(1);
  });

  test("分页：显示更多按钮＋触底自动加载（两种路径每条 12/13→13）", async ({ page }) => {
    const books = Array.from({ length: 13 }, (_, i) =>
      novel(`t-p${i}`, `分页书${String(i).padStart(2, "0")}`, {
        total_archives: 2,
        updated_at: new Date(Date.now() - i * H).toISOString(),
      }),
    );
    await stubShell(page, books);
    await page.goto("/#/novels");

    // 勿断言「首屏恰 12 张卡」——触底自动加载（IO）会合法改变它；断言按钮计数（F23 口径）
    const more = page.locator('[data-od-id="load-more"]');
    await expect(more).toContainText("显示更多");
    await expect(more).toContainText("12 / 13");
    // 按钮路径用程序触发：Playwright 点击前会滚动到按钮 → 滚动即触发 IO 自动加载 →
    // 按钮在点击前卸载（F23 已知竞态）。程序 click 直测处理器；IO 路径见下。
    await more.evaluate((el: HTMLElement) => el.click());
    await expect(page.locator(".book-card")).toHaveCount(13);
    await expect(more).toHaveCount(0);

    // IO 冒烟：重载后把按钮滚入视口（rootMargin 160px）→ 自动加载至 13、按钮消失
    await page.reload();
    await expect(more).toContainText("12 / 13");
    await more.scrollIntoViewIfNeeded();
    await expect.poll(() => page.locator(".book-card").count(), { timeout: 10000 }).toBe(13);
    await expect(more).toHaveCount(0);
  });
});

// ─── 回看一次性落点（真实后端：落点判定依赖 workbench 真渲染）─────────────
async function setupSession(page: Page) {
  const name = `shelf-e2e-${Date.now() % 100000}`;
  const password = "Passw0rd!e2e";
  const H2 = { "Content-Type": "application/json" };
  await fetch(`${S_API}/register`, {
    method: "POST", headers: H2,
    body: JSON.stringify({ username: name, password, security_question: "q", security_answer: "a" }),
  });
  const login = await (await fetch(`${S_API}/login`, {
    method: "POST", headers: H2, body: JSON.stringify({ username: name, password }),
  })).json();
  const token = login.data.token as string;
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = token; cfg.username = name; cfg.tier = "trial";
  delete cfg.expires_at; cfg.pc_hash = randomUUID().replace(/-/g, "");
  const mine = JSON.stringify(cfg, null, 2);
  fs.writeFileSync(CONFIG_PATH, mine);
  // bind mount（virtiofs）上宿主机写入对容器内后端的可见性有抖动（rename 尤甚）——
  // 以真实 API 往返为判据重试：写入重放 + 300ms 间隔，直至业务端点识别该会话。
  let sessionOk = false;
  for (let i = 0; i < 10 && !sessionOk; i++) {
    const r = await fetch(`${ORIGIN}/api/novels`, { headers: { Authorization: `Bearer ${token}` } });
    sessionOk = r.ok;
    if (!sessionOk) {
      fs.writeFileSync(CONFIG_PATH, mine);
      await new Promise((res) => setTimeout(res, 300));
    }
  }
  expect(sessionOk, "config 注入后容器内后端未能识别会话（bind mount 可见性）").toBe(true);
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  await page.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 0, data: {} } }));
  const restore = async () => {
    await cleanupSessionNovels(ORIGIN, token);
    fs.writeFileSync(CONFIG_PATH, original);
  };
  return { token, restore };
}

test("回看一次性落点：待完本卡与已完结卡两入口都落预览", async ({ page }) => {
  test.setTimeout(180000);
  const { token, restore } = await setupSession(page);
  try {
    const api = async (m: string, p: string, b?: unknown) => {
      const r = await page.request.fetch(`${ORIGIN}${p}`, {
        method: m,
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        data: b === undefined ? undefined : JSON.stringify(b),
      });
      return { status: r.status(), json: await r.json().catch(() => ({})) };
    };

    // 备一本「待完本」：2 章全归档未完结
    const bookName = `书架回看${Date.now() % 10000}`;
    const created = await api("POST", "/api/novels", { name: bookName });
    const pid = created.json.id as string;
    const v = await api("POST", `/api/novels/${pid}/volumes`, { title: "第一卷" });
    const volRef = (v.json.ref as string) ?? "vol-1";
    for (const title of ["第一章", "第二章"]) {
      await api("POST", `/api/novels/${pid}/volumes/${volRef}/chapters`, { title });
    }
    for (const ch of ["ch-1", "ch-2"]) {
      await api("POST", `/api/novels/${pid}/chapters/${volRef}-${ch}/archive`, {
        full_text: "正文。" + "内容。".repeat(60),
      });
    }

    // ① 待完本卡「回看」→ 预览
    await page.goto(`${ORIGIN}/#/novels`);
    const readyCard = page.locator(".book-card", { hasText: bookName });
    await readyCard.waitFor({ state: "visible", timeout: 15000 });
    await expect(readyCard).toContainText("待完本");
    await readyCard.getByRole("button", { name: "回看" }).click();
    await page.locator(".mtab").first().waitFor({ state: "visible", timeout: 15000 });
    await expect(page.locator(".mtab.on")).toContainText("预览", { timeout: 10000 });

    // ② 完本（真实端点）→ 已完结卡「回看」→ 预览
    const fin = await api("POST", `/api/novels/${pid}/finish`);
    expect(fin.status).toBe(200);
    await page.goto(`${ORIGIN}/#/novels`);
    const doneCard = page.locator(".book-card", { hasText: bookName });
    await doneCard.waitFor({ state: "visible", timeout: 15000 });
    await expect(doneCard).toContainText("已完结");
    await doneCard.getByRole("button", { name: "回看" }).click();
    await page.locator(".mtab").first().waitFor({ state: "visible", timeout: 15000 });
    await expect(page.locator(".mtab.on")).toContainText("预览", { timeout: 10000 });
  } finally {
    await restore();
  }
});
