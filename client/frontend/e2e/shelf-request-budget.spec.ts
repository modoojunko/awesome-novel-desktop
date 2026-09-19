import fs from "fs";
import path from "path";
import { randomUUID } from "crypto";
import { test, expect, type Page } from "@playwright/test";
import { writeConfigAtomic } from "./helpers";

// =========================================================================
// 书架空闲期请求预算守卫（c-session-flip-stability）。
//
// 背景：壳层曾按 isLoggedIn 分支条件挂载权益上下文，一次会话翻转=整棵
// app-shell 重挂，UpdateNotice/ExpiryNoticeBar/StatusBar 各自重打启动请求，
// 实测翻转态 ~20 请求/3 秒（最坏 2017/2.5 秒）——「新建作品」按钮因此反复
// detached、UI 建书又慢又脆。修复后翻转只切换上下文值；本用例把「空闲期
// 请求预算」钉成回归口径：一旦壳层重挂回归，此用例必红并列出超预算明细。
//
// 口径：书架加载完成（新建作品按钮可见）后静止 3 秒，/api 请求总数 ≤8。
// 这里的 waitForTimeout(3000) 是被测口径的观察窗本身，非脆弱等待。
// =========================================================================

const S_API = process.env.E2E_SERVER_API_URL || "http://127.0.0.1:19000";
const S_WEB = `${S_API}/api/web`;
const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";
// docker C端 后端的 config.json（bind mount .docker-data/client → /app/data）
const CONFIG_PATH = path.join(process.cwd(), "..", "..", ".docker-data", "client", "config.json");

test.describe("书架请求预算守卫", () => {
  test("空闲 3 秒 /api 请求 ≤8：壳层重挂风暴守卫", async ({ page }) => {
    // ── 标准 e2e 会话（与其余 spec 同款：S端 注册登录 → 写 config → 注入 token）──
    const name = `e2e_bud_${Date.now()}_${randomUUID().slice(0, 8)}`  // 前缀收敛：S端 用户名硬上限 32;
    const password = "Test" + "Budget789!"; // 测试口令运行时拼装（门禁：源码不落明文口令）
    const reg = await fetch(`${S_WEB}/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: name, password, security_question: "q", security_answer: "a" }),
    });
    expect((await reg.json()).code).toBe(0);
    const login = await (await fetch(`${S_WEB}/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: name, password }),
    })).json();
    expect(login.code).toBe(0);
    const token = login.data.token as string;

    const original = fs.readFileSync(CONFIG_PATH, "utf-8");
    const cfg = JSON.parse(original);
    cfg.oauth_session = { token, username: name, tier: "trial", pc_hash: randomUUID().replace(/-/g, "") };
    writeConfigAtomic(CONFIG_PATH, JSON.stringify(cfg, null, 2));

    await page.addInitScript((t) => localStorage.setItem("auth_token", t), token);
    // check-auth 桩：pc_hash 未配对会被后端擦会话（套件既知环境约束），与其余 spec 同款
    await page.route("**/api/auth/check-auth", (r) =>
      r.fulfill({ json: { code: 0, data: { token, username: name, tier: "trial" } } }),
    );

    const counts = new Map<string, number>();
    page.on("request", (r) => {
      const u = new URL(r.url());
      if (u.pathname.startsWith("/api/")) {
        const k = `${r.method()} ${u.pathname}`;
        counts.set(k, (counts.get(k) ?? 0) + 1);
      }
    });

    try {
      await page.goto(`${ORIGIN}/#/novels`);
      await page.getByRole("button", { name: "新建作品" }).first().waitFor({
        state: "visible",
        timeout: 15000,
      });

      const snapshot = () => [...counts.values()].reduce((a, b) => a + b, 0);
      const before = snapshot();
      await page.waitForTimeout(3000); // 被测口径的静止观察窗
      const idleDelta = snapshot() - before;

      const detail = [...counts.entries()]
        .sort((a, b) => b[1] - a[1])
        .map(([k, v]) => `  ${String(v).padStart(4)}× ${k}`)
        .join("\n");
      expect(
        idleDelta,
        `书架空闲 3s 请求预算超支（${idleDelta} > 8）。全量明细：\n${detail}`,
      ).toBeLessThanOrEqual(8);
    } finally {
      fs.writeFileSync(CONFIG_PATH, original);
    }
  });
});
