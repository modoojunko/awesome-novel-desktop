import { test, expect } from "@playwright/test";
import { url } from "./helpers";

/**
 * 会话失效（账号已注销，account-deletion tasks 5.2）：
 * check-auth 返回结构化失效信号 → C端 清凭据回登录入口、提示作品保留；
 * 重新登录（第二次 check-auth 恢复正常）后进入工作台，且无循环请求。
 */
test.describe("会话失效处理", () => {
  test("失效信号：清凭据回登录入口，提示已持久化（tasks 5.2）", async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem("auth_token", "stale-token");
      localStorage.setItem("auth_username", "gone-user");
    });
    await page.route("**/api/novels", (r) => r.fulfill({ json: [] }));
    await page.route("**/api/auth/check-auth", (r) =>
      r.fulfill({
        json: {
          code: 1,
          data: {
            session_invalid: true,
            deleted: true,
            message: "登录状态已失效（账号可能已注销）。你设备上的作品仍完好保留。",
          },
        },
      }),
    );

    await page.goto("/#/novels");
    // heal：清凭据 + 回登录页（LoginPage 是失效提示的消费方，读后即焚展示）
    await expect(page.getByRole("button", { name: "打开浏览器登录" })).toBeVisible({ timeout: 15000 });
    expect(await page.evaluate(() => localStorage.getItem("auth_token"))).toBeNull();
    expect(await page.evaluate(() => localStorage.getItem("auth_username"))).toBeNull();
    // 失效提示必达：展示在登录页（持久化只是手段，用户看得见才是契约）
    await expect(page.getByRole("status")).toContainText("作品仍完好保留", { timeout: 10000 });
    expect(page.url()).toContain("/#/login");
  });

  test("重新登录后进入工作台且无循环请求（tasks 5.2）", async ({ page }) => {
    let checkAuthCalls = 0;
    await page.route("**/api/auth/check-auth", (r) => {
      checkAuthCalls += 1;
      return r.fulfill({
        json: {
          code: 0,
          data: {
            token: "fresh-token",
            username: "gone-user",
            tier: "trial",
            expires_at: new Date(Date.now() + 5 * 86400000).toISOString(),
          },
        },
      });
    });
    // heal 写回凭据后，工作台 shell 会用这个假 token 打真实端点——401 拦截器
    // 会清 token 硬跳回 /#/login（曾把本用例打成「停不回工作台」）。桩掉这些
    // 只读端点，场景就只剩「heal 写回 → 停稳」本身。
    await page.route("**/api/novels", (r) => r.fulfill({ json: [] }));
    await page.route("**/api/auth/devices/current", (r) =>
      r.fulfill({ json: { enrolled: true, activated: true } }),
    );
    await page.route("**/api/auth/config", (r) =>
      r.fulfill({ json: { code: 0, data: {} } }),
    );

    await page.goto("/#/novels");
    // heal 写回新凭据 → 稳定停留工作台；无登出循环、无 request 风暴
    await page.waitForTimeout(2500);
    await page.goto("/#/novels");
    await page.waitForTimeout(1000);
    expect(page.url()).toContain("/#/novels");
    expect(await page.evaluate(() => localStorage.getItem("auth_token"))).toBe("fresh-token");
    // 两次 boot 各 1-3 次 check-auth 属正常；死循环会是几十次
    expect(checkAuthCalls).toBeLessThanOrEqual(6);
  });
});
