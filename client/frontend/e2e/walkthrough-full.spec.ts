import { test, expect, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "path";

// 从 chat-dock.spec 复用 setup 模式
const S_API = process.env.E2E_S_API || "http://127.0.0.1:19001/api/web";
const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5199";
const CONFIG_PATH = path.join(
  process.env.E2E_CLIENT_DATA || path.join(process.cwd(), "..", "..", "docker-data-e2e", "client"),
  "config.json",
);

const OUT = "/tmp/walkthrough-full";
let step = 0;
function shot(p: Page, name: string) {
  step += 1;
  p.screenshot({ path: `${OUT}/s${String(step).padStart(2, "0")}-${name}.png` });
  console.log(`[shot] s${step}-${name}`);
}

async function setupSession(page: Page, tier = "max") {
  const uname = `walk-full-${Date.now()}`;
  await fetch(`${S_API}/register`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: uname, password: "walk-test-1" }) });
  const login = await fetch(`${S_API}/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: uname, password: "walk-test-1" }) });
  const loginBody = await login.json();
  const token = loginBody.data.token as string;
  const original = fs.readFileSync(CONFIG_PATH, "utf-8");
  const cfg = JSON.parse(original);
  cfg.token = token;
  cfg.username = uname;
  cfg.tier = tier;
  cfg.last_login_at = new Date().toISOString();
  cfg.pc_hash = crypto.randomUUID().replace(/-/g, "");
  const fd = fs.openSync(CONFIG_PATH, "r+");
  fs.ftruncateSync(fd, 0);
  fs.writeFileSync(fd, JSON.stringify(cfg, null, 2));
  fs.fsyncSync(fd);
  fs.closeSync(fd);
  await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
  await page.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 0, data: {} } }));
  return { token, restore: () => { fs.writeFileSync(CONFIG_PATH, original); } };
}

function sse(events: string[]): string {
  return events.map((e) => `data: ${e}\n\n`).join("");
}
const runStart = (id: string) => JSON.stringify({ type: "run_start", runId: id });
const runEnd = (id: string) => JSON.stringify({ type: "run_end", runId: id, steps: 1, toolCalls: 0 });
const narr = (text: string) => JSON.stringify({ type: "narration", text });
const artifact = (id: string, cardId: string, kind: string, payload: unknown) =>
  JSON.stringify({ type: "artifact", runId: id, cardId, kind, payload });

async function mockChat(page: Page, script: string[][]) {
  let call = 0;
  await page.route("**/api/novels/*/assistant/session*", (r) =>
    r.fulfill({ json: { sessionId: "s-walk", pageCursor: "", grants: {}, messages: [] } }),
  );
  await page.route("**/api/novels/*/assistant/chat", async (r) => {
    const events = script[Math.min(call, script.length - 1)];
    call += 1;
    await new Promise((res) => setTimeout(res, 200));
    r.fulfill({ status: 200, contentType: "text/event-stream", body: sse(events) });
  });
}

async function sendViaDock(page: Page, text: string) {
  const box = page.getByTestId("aui2-dock").getByRole("textbox");
  await box.fill(text);
  await box.press("Enter");
}

const crypto = { randomUUID: () => "xxxx".replace(/x/g, () => Math.floor(Math.random() * 16).toString(16)) };

test.describe("全场景走查", () => {
  test("A-dock布局＋开场白", async ({ page }) => {
    const { token } = await setupSession(page, "max");
    const r = await fetch(`${ORIGIN}/api/novels`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ name: `walk-a-${Date.now()}`, source: "manual" }) });
    const bid = (await r.json()).id;
    await page.goto(`${ORIGIN}/#/novel/${bid}`);
    await page.locator(".mtab", { hasText: "写作" }).click();
    await page.waitForSelector('[data-testid="aui2-dock"]', { timeout: 20000 });
    await page.waitForTimeout(1500);
    shot(page, "A1-dock-greeting");
    await expect(page.getByTestId("aui2-chip-draft_volume_expand")).toBeVisible();
    await expect(page.getByTestId("aui2-mode-chip")).toBeVisible();
    await expect(page.getByText(/铺/)).toBeVisible();
  });

  test("B-授权芯片三档", async ({ page }) => {
    const { restore, token } = await setupSession(page, "max");
    const r = await fetch(`${ORIGIN}/api/novels`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ name: `walk-b-${Date.now()}`, source: "manual" }) });
    const bid = (await r.json()).id;
    await page.goto(`${ORIGIN}/#/novel/${bid}`);
    await page.locator(".mtab", { hasText: "写作" }).click();
    await page.waitForSelector('[data-testid="aui2-mode-chip"]');
    await shot(page, "B1-mode-chip-visible");
    await page.click('[data-testid="aui2-mode-chip"]');
    await page.waitForTimeout(300);
    shot(page, "B2-mode-dropdown");
    await page.click('[data-testid="aui2-mode-item-allow_book"]');
    await page.waitForTimeout(500);
    shot(page, "B3-mode-switched");
    await expect(page.getByTestId("aui2-mode-chip")).toContainText("本书内放行");
    // 切回
    await page.click('[data-testid="aui2-mode-chip"]');
    await page.click('[data-testid="aui2-mode-item-confirm_each"]');
    await page.waitForTimeout(300);
    await expect(page.getByTestId("aui2-mode-chip")).toContainText("每写必确认");
    await restore();
  });

  test("C-对话回复＋容量条", async ({ page }) => {
    const { restore, token } = await setupSession(page, "max");
    const r = await fetch(`${ORIGIN}/api/novels`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ name: `walk-c-${Date.now()}`, source: "manual" }) });
    const bid = (await r.json()).id;
    await page.route("**/api/novels/*/assistant/session*", (r2) => r2.fulfill({ json: { sessionId: "s", pageCursor: "", grants: {}, messages: [] } }));
    await page.route("**/api/novels/*/assistant/chat", async (r2) => {
      await new Promise((res) => setTimeout(res, 200));
      r2.fulfill({ status: 200, contentType: "text/event-stream", body: sse([runStart("r1"), narr("我是写作助手，管卷纲章纲伏笔这些事。"), runEnd("r1")]) });
    });
    await page.goto(`${ORIGIN}/#/novel/${bid}`);
    await page.locator(".mtab", { hasText: "写作" }).click();
    await page.waitForSelector('[data-testid="aui2-dock"]');
    await sendViaDock(page, "你是谁");
    await page.waitForTimeout(2000);
    shot(page, "C1-chat-reply");
    await expect(page.getByText("写作助手")).toBeVisible();
    await restore();
  });

  test("D-写授权卡＋预览", async ({ page }) => {
    const { restore, token } = await setupSession(page, "max");
    const r = await fetch(`${ORIGIN}/api/novels`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ name: `walk-d-${Date.now()}`, source: "manual" }) });
    const bid = (await r.json()).id;
    await page.route("**/api/novels/*/assistant/session*", (r2) => r2.fulfill({ json: { sessionId: "s", pageCursor: "", grants: {}, messages: [] } }));
    await page.route("**/api/novels/*/assistant/chat", async (r2) => {
      await new Promise((res) => setTimeout(res, 200));
      r2.fulfill({ status: 200, contentType: "text/event-stream", body: sse([
        runStart("r1"),
        JSON.stringify({ type: "permission_required", gateId: "gw1", preview: { tool: "confirm_chapter", args: { chapter_ref: "vol-1-ch-1" } }, humanOnly: false }),
      ]) });
    });
    await page.goto(`${ORIGIN}/#/novel/${bid}`);
    await page.locator(".mtab", { hasText: "写作" }).click();
    await page.waitForSelector('[data-testid="aui2-dock"]');
    await sendViaDock(page, "确认第一章");
    await page.waitForSelector('[data-testid="aui2-gate-approve"]');
    shot(page, "D1-write-auth-card");
    await expect(page.getByText(/confirm_chapter/)).toBeVisible();
    await page.click('[data-testid="aui2-gate-approve"]');
    await page.waitForTimeout(1000);
    shot(page, "D2-approved");
    await restore();
  });

  test("E-记忆remember＋跨页签", async ({ page }) => {
    const { restore, token } = await setupSession(page, "max");
    const r = await fetch(`${ORIGIN}/api/novels`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ name: `walk-e-${Date.now()}`, source: "manual" }) });
    const bid = (await r.json()).id;
    await page.route("**/api/novels/*/assistant/session*", (r2) => r2.fulfill({ json: { sessionId: "s", pageCursor: "", grants: {}, messages: [] } }));
    await page.route("**/api/novels/*/assistant/chat", async (r2) => {
      await new Promise((res) => setTimeout(res, 100));
      r2.fulfill({ status: 200, contentType: "text/event-stream", body: sse([runStart("r1"), narr("记住了：全程第一人称。"), runEnd("r1")]) });
    });
    await page.goto(`${ORIGIN}/#/novel/${bid}`);
    await page.locator(".mtab", { hasText: "写作" }).click();
    await page.waitForSelector('[data-testid="aui2-dock"]');
    await sendViaDock(page, "记住：全程第一人称");
    await page.waitForTimeout(2000);
    shot(page, "E1-remember-reply");
    await expect(page.getByText(/记住了：全程第一人称/)).toBeVisible();
    // 切页签
    await page.locator(".mtab", { hasText: "设定" }).click();
    await page.waitForTimeout(500);
    shot(page, "E2-switched-to-settings");
    await expect(page.getByText(/记住了：全程第一人称/)).toBeHidden();
    await restore();
  });

  test("F-停止", async ({ page }) => {
    const { restore, token } = await setupSession(page, "max");
    const r = await fetch(`${ORIGIN}/api/novels`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ name: `walk-f-${Date.now()}`, source: "manual" }) });
    const bid = (await r.json()).id;
    await page.route("**/api/novels/*/assistant/session*", (r2) => r2.fulfill({ json: { sessionId: "s", pageCursor: "", grants: {}, messages: [] } }));
    await page.route("**/api/novels/*/assistant/chat", async (r2) => {
      // 永不收口的慢流
      await new Promise((res) => setTimeout(res, 100));
      r2.fulfill({ status: 200, contentType: "text/event-stream", body: sse([runStart("rX")]) });
    });
    await page.goto(`${ORIGIN}/#/novel/${bid}`);
    await page.locator(".mtab", { hasText: "写作" }).click();
    await page.waitForSelector('[data-testid="aui2-dock"]');
    await sendViaDock(page, "一直说");
    await page.waitForSelector('[data-testid="chat-stop"]', { timeout: 5000 });
    shot(page, "F1-stop-visible");
    await page.click('[data-testid="chat-stop"]');
    await page.waitForTimeout(1000);
    shot(page, "F2-stopped");
    await expect(page.getByTestId("chat-stop")).toBeHidden();
    await restore();
  });

  test("G-error-card", async ({ page }) => {
    const { restore, token } = await setupSession(page, "max");
    const r = await fetch(`${ORIGIN}/api/novels`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ name: `walk-g-${Date.now()}`, source: "manual" }) });
    const bid = (await r.json()).id;
    await page.route("**/api/novels/*/assistant/session*", (r2) => r2.fulfill({ json: { sessionId: "s", pageCursor: "", grants: {}, messages: [] } }));
    await page.route("**/api/novels/*/assistant/chat", async (r2) => {
      await new Promise((res) => setTimeout(res, 100));
      // 流断开（无终态）→ 前端判死出错误卡
      r2.fulfill({ status: 200, contentType: "text/event-stream", body: sse([runStart("rX")]) });
    });
    await page.goto(`${ORIGIN}/#/novel/${bid}`);
    await page.locator(".mtab", { hasText: "写作" }).click();
    await page.waitForSelector('[data-testid="aui2-dock"]');
    await sendViaDock(page, "触发一个错误");
    await page.waitForSelector('[data-testid="chat-error"]', { timeout: 8000 });
    shot(page, "G1-error-card");
    await restore();
  });

  test("H-系统gate引导", async ({ page }) => {
    const { restore, token } = await setupSession(page, "max");
    const r = await fetch(`${ORIGIN}/api/novels`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ name: `walk-h-${Date.now()}`, source: "manual" }) });
    const bid = (await r.json()).id;
    await page.route("**/api/novels/*/assistant/session*", (r2) => r2.fulfill({ json: { sessionId: "s", pageCursor: "", grants: {}, messages: [] } }));
    await page.route("**/api/novels/*/assistant/chat", async (r2) => {
      await new Promise((res) => setTimeout(res, 100));
      r2.fulfill({ status: 200, contentType: "text/event-stream", body: sse([
        JSON.stringify({ type: "gate", reason: "no_key", message: "这本书还没绑定 AI 模型——到设定 · AI 模型配置绑一次就能开跑。" }),
      ]) });
    });
    await page.goto(`${ORIGIN}/#/novel/${bid}`);
    await page.locator(".mtab", { hasText: "写作" }).click();
    await page.waitForSelector('[data-testid="aui2-dock"]');
    await sendViaDock(page, "帮我起草");
    await page.waitForTimeout(2000);
    shot(page, "H1-no-key-guide");
    await expect(page.getByText(/这本书还没绑定 AI 模型/)).toBeVisible();
    await expect(page.getByTestId("aui2-auth-card")).toBeHidden();
    await restore();
  });

  test("I-跨天标记", async ({ page }) => {
    const { restore, token } = await setupSession(page, "max");
    const r = await fetch(`${ORIGIN}/api/novels`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ name: `walk-i-${Date.now()}`, source: "manual" }) });
    const bid = (await r.json()).id;
    const now = new Date();
    const yesterday = new Date(now.getTime() - 24 * 3600 * 1000);
    await page.route("**/api/novels/*/assistant/session*", (r2) =>
      r2.fulfill({ json: { sessionId: "s", pageCursor: "", grants: {}, messages: [
        { id: "m1", seq: 1, role: "user", content: "昨天的话", page: "volume", cardKind: "", status: "done", payload: {}, createdAt: yesterday.toISOString() },
        { id: "m2", seq: 2, role: "assistant", content: "昨天的答", page: "volume", cardKind: "", status: "done", payload: {}, createdAt: yesterday.toISOString() },
        { id: "m3", seq: 3, role: "user", content: "今天的话", page: "chapters", cardKind: "", status: "done", payload: {}, createdAt: now.toISOString() },
        { id: "m4", seq: 4, role: "assistant", content: "今天的答", page: "chapters", cardKind: "", status: "done", payload: {}, createdAt: now.toISOString() },
      ] } }),
    );
    await page.goto(`${ORIGIN}/#/novel/${bid}`);
    await page.locator(".mtab", { hasText: "写作" }).click();
    await page.waitForSelector('[data-testid="aui2-dock"]');
    await page.waitForTimeout(2000);
    shot(page, "I1-cross-day-marker");
    await expect(page.getByText(/时间跳到/)).toBeVisible();
    await restore();
  });

  test("J-记忆工具四操作", async ({ page }) => {
    const { restore, token } = await setupSession(page, "max");
    const r = await fetch(`${ORIGIN}/api/novels`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ name: `walk-j-${Date.now()}`, source: "manual" }) });
    const bid = (await r.json()).id;
    await page.route("**/api/novels/*/assistant/session*", (r2) => r2.fulfill({ json: { sessionId: "s", pageCursor: "", grants: {}, messages: [] } }));
    await page.route("**/api/novels/*/assistant/chat", async (r2) => {
      await new Promise((res) => setTimeout(res, 100));
      r2.fulfill({ status: 200, contentType: "text/event-stream", body: sse([runStart("r1"), narr("记下了：全程第一人称。"), runEnd("r1")]) });
    });
    await page.goto(`${ORIGIN}/#/novel/${bid}`);
    await page.locator(".mtab", { hasText: "写作" }).click();
    await page.waitForSelector('[data-testid="aui2-dock"]');
    await sendViaDock(page, "记住：全程第一人称");
    await page.waitForTimeout(2000);
    shot(page, "J1-remember");
    await expect(page.getByText(/记下了：全程第一人称/)).toBeVisible();
    await restore();
  });
});

const _orig = Symbol("orig");
