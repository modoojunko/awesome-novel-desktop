import { test, expect, type Page } from "@playwright/test";
import { stubUpdateNotice } from "./helpers";

/**
 * client-update-notify：更新提示条三态交互（有更新 / 无更新 / 检测失败）。
 * 打桩口径与 helpers.stubUpdateNotice 一致；书架屏为居中变体。
 */

async function stubShell(page: Page) {
  // 书架屏最小启动集（与 design-parity.spec 同源）
  await page.addInitScript(() => {
    localStorage.setItem("auth_token", "update-notice-stub");
    localStorage.setItem("auth_username", "updater");
  });
  await page.route("**/api/novels", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/auth/verify", (r) =>
    r.fulfill({ json: { tier: "none", is_member: false, expired: false, trial_remaining_days: 0 } }),
  );
  await page.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 1 } }));
  await page.route("**/api/auth/config", (r) =>
    r.fulfill({ json: { has_api_key: true, portal_url: "" } }),
  );
  // 外链域名就地打桩，避免 e2e 真出网
  await page.route(/awesomenovel\.com\//, (r) => r.fulfill({ body: "stubbed" }));
}

test.describe("更新提示条", () => {
  test("有更新：呈现文案与三动作；「去下载」开外部页；「知道了」按版本关闭", async ({ page }) => {
    await stubShell(page);
    await stubUpdateNotice(page, "update");
    let dismissedBody: unknown = null;
    await page.route("**/api/update-check/dismiss", (r) => {
      dismissedBody = r.request().postDataJSON();
      return r.fulfill({ json: { dismissed: "ok" } });
    });

    await page.goto("/#/novels");
    const strip = page.locator(".update-strip .notice.info");
    await expect(strip).toBeVisible();
    await expect(strip).toContainText("发现新版本 v0.13（当前 v0.11）"); // rider 对照文案
    await expect(strip).toContainText("提升章纲 AI 起草的稳定性，修复若干问题");

    // 「去下载」→ target=_blank 锚点在弹出新页打开（pywebview 中即系统浏览器路径）
    const popupPromise = page.context().waitForEvent("page");
    await strip.getByRole("link", { name: "去下载" }).click();
    const popup = await popupPromise;
    await expect(popup).toHaveURL(/awesomenovel\.com\//);

    // 「知道了」→ 调 dismiss（载荷带版本号），提示条消失
    await strip.getByRole("button", { name: "知道了" }).click();
    await expect
      .poll(() => dismissedBody, { timeout: 5000 })
      .toEqual({ version: "0.13" });
    await expect(page.locator(".update-strip")).toHaveCount(0);
  });

  test("无更新：不渲染任何更新元素", async ({ page }) => {
    await stubShell(page);
    await stubUpdateNotice(page, "none");
    await page.goto("/#/novels");
    await page.waitForLoadState("networkidle");
    await expect(page.locator(".update-strip")).toHaveCount(0);
    // 页面本身功能不受影响：空书架正常呈现
    await expect(page.locator("h1", { hasText: "我的作品" })).toBeVisible();
  });

  test("检测失败（500）：静默降级不打扰", async ({ page }) => {
    await stubShell(page);
    await stubUpdateNotice(page, "fail");
    await page.goto("/#/novels");
    await page.waitForLoadState("networkidle");
    await expect(page.locator(".update-strip")).toHaveCount(0);
    await expect(page.locator("h1", { hasText: "我的作品" })).toBeVisible();
  });
});
