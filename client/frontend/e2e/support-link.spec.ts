import { test, expect } from "@playwright/test";

// 控制中心面板「联系客服」外跳入口（contact-support-page / c-account-control-center）：
// 顶栏常驻按钮已收敛为头像胶囊，客服入口在面板「支持」组。
// 地址 = portal_url 去尾斜杠拼 /support；取不到门户地址时菜单项不渲染（不出死链）。
async function stubShell(page: import("@playwright/test").Page, portalUrl: string) {
  await page.addInitScript(() => {
    localStorage.setItem("auth_token", "support-e2e-stub");
    localStorage.setItem("auth_username", "support-e2e");
  });
  await page.route("**/api/novels", (r) => r.fulfill({ json: [] }));
  await page.route(
    "**/api/auth/verify",
    (r) => r.fulfill({ json: { tier: "pro", is_member: true, expired: false, trial_remaining_days: 0 } }),
  );
  await page.route("**/api/auth/config", (r) => r.fulfill({ json: { has_api_key: true, portal_url: portalUrl } }));
  await page.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 1 } }));
}

async function openPanel(page: import("@playwright/test").Page) {
  await page.locator('[data-od-id="acct-trigger"]').click();
  await expect(page.locator('[data-od-id="acct-menu"]')).toBeVisible();
}

test.describe("控制中心面板联系客服", () => {
  test("有门户地址（带尾斜杠）：面板项外跳 <portal>/support，新窗口锚点", async ({ page }) => {
    await stubShell(page, "https://www.awesomenovel.com/");
    await page.goto("/#/novels");
    // 顶栏不再有客服常驻按钮
    await expect(page.locator("header.appbar a.btn", { hasText: "联系客服" })).toHaveCount(0);
    await openPanel(page);
    const item = page.locator('[data-od-id="acct-menu-support"]');
    await expect(item).toBeVisible();
    // 尾斜杠被剥后拼路径
    await expect(item).toHaveAttribute("href", "https://www.awesomenovel.com/support");
    // pywebview cocoa 只认锚点 target=_blank，禁编程式 window.open
    await expect(item).toHaveAttribute("target", "_blank");
    await expect(item).toHaveAttribute("rel", "noreferrer");
  });

  test("门户地址为空：面板项不渲染，无死链", async ({ page }) => {
    await stubShell(page, "");
    await page.goto("/#/novels");
    await openPanel(page);
    await expect(page.locator('[data-od-id="acct-menu-support"]')).toHaveCount(0);
  });

  test("未登录：顶栏只有登录入口，无头像触发钮与客服项", async ({ page }) => {
    await page.route("**/api/novels", (r) => r.fulfill({ json: [] }));
    await page.route(
      "**/api/auth/verify",
      (r) => r.fulfill({ json: { tier: "none", is_member: false, expired: false, trial_remaining_days: 0 } }),
    );
    await page.route("**/api/auth/config", (r) => r.fulfill({ json: { has_api_key: true, portal_url: "https://www.awesomenovel.com" } }));
    await page.goto("/#/novels");
    await expect(page.locator('[data-od-id="acct-trigger"]')).toHaveCount(0);
    await expect(page.locator('[data-od-id="acct-menu-support"]')).toHaveCount(0);
    await expect(page.locator("header.appbar a.btn", { hasText: "登录" })).toBeVisible();
  });
});
