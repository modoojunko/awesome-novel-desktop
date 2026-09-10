import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page } from "@playwright/test";
import { writeConfigAtomic } from "./helpers";

// 打开书的默认落点（用户 2026-09-10 拍板）：
//   第一次创建的书（无章节）→ 设定；写完第一个章节后（有章节未全归档）→ 写作；
//   小说写完后（全部章节已归档）→ 预览。
// 判据只看章节（不看 current_phase——那只是「最近一次操作」的记账）。
const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
const S_API = process.env.E2E_S_API || "http://127.0.0.1:19000/api/web";
const CONFIG_PATH = path.join(process.cwd(), "..", "..", ".docker-data", "client", "config.json");

async function setupSession(page: Page) {
  const name = `e2e_land_${Date.now()}_${randomUUID().slice(0, 8)}`;
  const password = "Test" + "Pass789!";
  const H = { "Content-Type": "application/json" };
  await fetch(`${S_API}/register`, {
    method: "POST", headers: H,
    body: JSON.stringify({ username: name, password, security_question: "q", security_answer: "a" }),
  });
  const login = await (await fetch(`${S_API}/login`, {
    method: "POST", headers: H, body: JSON.stringify({ username: name, password }),
  })).json();
  const token = login.data.token as string;
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = token; cfg.username = name; cfg.tier = "trial";
  delete cfg.expires_at; cfg.pc_hash = randomUUID().replace(/-/g, "");
  writeConfigAtomic(CONFIG_PATH, JSON.stringify(cfg, null, 2));
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  await page.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 0, data: {} } }));
  return { token, restore: () => writeConfigAtomic(CONFIG_PATH, original) };
}

/** 走真实入口：书架 → 点开书（组件重新挂载，落点才会重新判定）。 */
async function openFromShelf(page: Page, pid: string) {
  await page.goto(`${ORIGIN}/#/novels`);
  await page.waitForTimeout(600);
  await page.goto(`${ORIGIN}/#/novel/${pid}`);
  await page.waitForTimeout(2200);
}

test("默认落点：空书→设定 / 有章节→写作 / 全归档→预览", async ({ page }) => {
  test.setTimeout(180000);
  const { token, restore } = await setupSession(page);
  try {
    await page.setViewportSize({ width: 1440, height: 900 });
    const api = async (m: string, p: string, b?: unknown) => {
      const r = await page.request.fetch(`${ORIGIN}${p}`, {
        method: m,
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        data: b === undefined ? undefined : JSON.stringify(b),
      });
      return { status: r.status(), json: await r.json().catch(() => ({})) };
    };

    const novel = await api("POST", "/api/novels", { name: `落点${Date.now() % 10000}` });
    const pid = novel.json.id as string;

    // ① 第一次创建（0 章）→ 设定
    await openFromShelf(page, pid);
    await expect(page.locator(".mtab.on")).toContainText("设定");
    // 已在设定页 → 不再叠「开始设定」引导卡（卡片唯一作用就是把人送到这里）
    await expect(page.getByText("你的第一本书从设定开始")).toHaveCount(0);

    // ② 建卷 + 建章（有章节未归档）→ 写作
    const v = await api("POST", `/api/novels/${pid}/volumes`, { title: "第一卷" });
    const volRef = (v.json.ref as string) ?? "vol-1";
    const ch = await api("POST", `/api/novels/${pid}/volumes/${volRef}/chapters`, {
      title: "第一章",
    });
    const ref = (ch.json.ref as string) ?? `${volRef}-ch-1`;
    await openFromShelf(page, pid);
    await expect(page.locator(".mtab.on")).toContainText("写作");

    // ③ 全部章节归档（写完）→ 预览
    await api("POST", `/api/novels/${pid}/chapters/${ref}/archive`, {
      full_text: "第一章正文。" + "内容。".repeat(60),
      ai_summary: false,
    });
    await openFromShelf(page, pid);
    await expect(page.locator(".mtab.on")).toContainText("预览");

    // ④ 用户手动切回写作 → 不被落点拽回去（落点只在首次加载判一次）
    await page.locator(".mtab", { hasText: "写作" }).click();
    await page.waitForTimeout(600);
    await expect(page.locator(".mtab.on")).toContainText("写作");
  } finally {
    restore();
  }
});
