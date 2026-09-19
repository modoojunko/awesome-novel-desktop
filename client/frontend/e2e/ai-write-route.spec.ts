import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page } from "@playwright/test";
import { writeConfigAtomic, cleanupSessionNovels } from "./helpers";

// AI 生成正文路由契约（qa-night 2026-09-19 P1 回归守卫，真后端链路）：
//   write/router.py 的 prefix 已以 /write 结尾，装饰器再写 "/write" 会注册成
//   /write/write → 前端 streamChapterWrite 调 /write 恒 404、AI 生成正文不可用。
//   该缺陷 e2e 曾测不出（全打桩 spec 掩盖路由错位，runbook #17 教训）——本 spec
//   直打真后端：只断言「路由存在」，不依赖 AI 配置（403/409 都算注册成功，
//   唯独 404 是路由错位/丢失）。
const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
const S_API = process.env.E2E_S_API || "http://127.0.0.1:19000/api/web";
const CONFIG_PATH = path.join(process.cwd(), "..", "..", ".docker-data", "client", "config.json");

async function setupSession(page: Page) {
  const name = `e2e_wrt_${Date.now()}_${randomUUID().slice(0, 8)}`;
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
  const restore = async () => {
    await cleanupSessionNovels(ORIGIN, token);
    writeConfigAtomic(CONFIG_PATH, original);
  };
  return { token, restore };
}

test("AI 生成正文端点注册在 /write（非 404 即注册成功）", async ({ page }) => {
  test.setTimeout(120_000);
  const { token, restore } = await setupSession(page);
  try {
    // API 级直打真后端（经 nginx 同源入口，与前端请求同链路）
    const api = async (m: string, p: string, b?: unknown) => {
      const r = await page.request.fetch(`${ORIGIN}${p}`, {
        method: m,
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        data: b === undefined ? undefined : JSON.stringify(b),
      });
      return r;
    };

    const novel = await (await api("POST", "/api/novels", { name: `路由守卫${Date.now() % 10000}` })).json();
    const pid = novel.id as string;
    const v = await (await api("POST", `/api/novels/${pid}/volumes`, { title: "第一卷" })).json();
    const volRef = (v.ref as string) ?? "vol-1";
    await api("POST", `/api/novels/${pid}/volumes/${volRef}/chapters`, { title: "第一章" });

    // 路由契约本体：单段 /write 必须命中路由（403 免费无 Key / 409 门禁 / 200 流式
    // 都是「注册成功」的合法形态；404 = 路由错位回归）
    const r = await api("POST", `/api/novels/${pid}/chapters/${volRef}-ch-1/write`, {});
    expect(r.status(), `POST /write 不得 404（路由错位回归）: ${await r.text()}`).not.toBe(404);

    // 反向：双段 /write/write 必须不存在（曾把错误路径钉进测试的病灶）
    const rw = await api("POST", `/api/novels/${pid}/chapters/${volRef}-ch-1/write/write`, {});
    expect(rw.status()).toBe(404);
  } finally {
    await restore();
  }
});
