import { test, expect, type Page } from "@playwright/test";
import { stubUpdateNotice } from "./helpers";

/**
 * 底部状态条 + 版本可视性（c-version-account-visibility）。
 * 状态条挂 ClientShell 层：三态（登录/未登录/工作台）常驻、落地页 `/` 豁免、
 * dev 文案「开发版 dev」、失败静默「版本未知」；书架 © 页脚并入状态条（单底条）。
 * 全部走 /api/update-check 打桩，不打真实后端。
 */

async function stubShell(page: Page, username = "writer01") {
  await page.addInitScript((u) => {
    localStorage.setItem("auth_token", "statusbar-stub");
    localStorage.setItem("auth_username", u);
  }, username);
  await page.route("**/api/novels", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/auth/verify", (r) =>
    r.fulfill({ json: { tier: "member", is_member: true, expired: false, trial_remaining_days: 0 } }),
  );
  await page.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 1 } }));
  await page.route("**/api/auth/config", (r) =>
    r.fulfill({ json: { has_api_key: true, portal_url: "" } }),
  );
}

async function stubWorkspaceMiss(page: Page) {
  // 工作台：novel 详情打桩失败 → project=null 不崩溃，壳层（含状态条）照常呈现
  await page.route("**/api/novels/*", (r) => r.fulfill({ status: 500, json: { detail: "stub" } }));
}

test.describe("底部状态条", () => {
  test("登录态书架：常驻可见且含当前版本号", async ({ page }) => {
    await stubShell(page);
    await stubUpdateNotice(page, "none", "0.15.1");
    await page.goto("/#/novels");
    const bar = page.locator('[data-od-id="app-status-bar"]');
    await expect(bar).toBeVisible();
    await expect(bar).toContainText("v0.15.1");
    await expect(bar).toContainText("© 2026 爱小说");
  });

  test("未登录登录页：状态条仍常驻；顶栏不新增版本元素", async ({ page }) => {
    await page.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 1 } }));
    await stubUpdateNotice(page, "none", "0.15.1");
    await page.goto("/#/login");
    await expect(page.locator('[data-od-id="app-status-bar"]')).toBeVisible();
    await expect(page.locator('[data-od-id="app-status-bar"]')).toContainText("v0.15.1");
    await expect(page.locator("header.appbar, .appbar").first()).not.toContainText("v0.15.1");
  });

  test("工作台：壳层状态条仍常驻（详情失败不崩溃）", async ({ page }) => {
    await stubShell(page);
    await stubWorkspaceMiss(page);
    await stubUpdateNotice(page, "none", "0.15.1");
    await page.goto("/#/novel/parity-x");
    await expect(page.locator('[data-od-id="app-status-bar"]')).toBeVisible();
    await expect(page.locator('[data-od-id="app-status-bar"]')).toContainText("v0.15.1");
  });

  test("落地页豁免：`/` 不呈现状态条", async ({ page }) => {
    await page.route("**/api/auth/check-auth", (r) => r.fulfill({ json: { code: 1 } }));
    await stubUpdateNotice(page, "none", "0.15.1");
    await page.goto("/#/"); // 未登录 → LandingPage
    await expect(page).not.toHaveURL(/novels|login/);
    await expect(page.locator('[data-od-id="app-status-bar"]')).toHaveCount(0);
  });

  test("dev 构建：显「开发版 dev」，不渲染「vdev」", async ({ page }) => {
    await stubShell(page);
    await stubUpdateNotice(page, "none", "dev");
    await page.goto("/#/novels");
    const bar = page.locator('[data-od-id="app-status-bar"]');
    await expect(bar).toContainText("开发版 dev");
    await expect(bar).not.toContainText("vdev");
  });

  test("获取失败：静默显「版本未知」，无错误 toast", async ({ page }) => {
    await stubShell(page);
    await stubUpdateNotice(page, "fail");
    await page.goto("/#/novels");
    await expect(page.locator('[data-od-id="app-status-bar"]')).toContainText("版本未知");
    await expect(page.locator(".toast-wrap .toast")).toHaveCount(0);
  });

  test("页脚并入：书架底部只有状态条这一条常驻条", async ({ page }) => {
    await stubShell(page);
    await stubUpdateNotice(page, "none", "0.15.1");
    await page.goto("/#/novels");
    await expect(page.locator(".pagefoot")).toHaveCount(0);
    await expect(page.locator('[data-od-id="app-status-bar"]')).toHaveCount(1);
  });
});

test.describe("版本行与账号行（设置弹窗）", () => {
  test("全局偏好弹窗：账号行「用户名 · 套餐」同屏 + 底部版本行（吃缓存零新请求）", async ({
    page,
  }) => {
    await stubShell(page, "writer01");
    await stubUpdateNotice(page, "none", "0.15.1");
    await page.goto("/#/novels");
    await expect(page.locator('[data-od-id="app-status-bar"]')).toBeVisible(); // 状态条先触发一次取版本（缓存建立）

    await page.getByRole("button", { name: "设置", exact: true }).click();
    const dlg = page.getByRole("dialog");
    await expect(dlg.getByRole("heading", { name: "设置 · 写作偏好" })).toBeVisible();
    await expect(dlg.locator('[data-od-id="pref-account"]')).toHaveText("writer01 · PRO 会员");
    await expect(dlg.locator('[data-od-id="pref-version"]')).toHaveText("v0.15.1"); // 弹窗吃缓存不发新请求
  });

  test("长用户名：截断不撑破行布局，悬停 title 见全文", async ({ page }) => {
    const longName = "w".repeat(38) + "-end"; // 42 字符
    await stubShell(page, longName);
    await stubUpdateNotice(page, "none", "0.15.1");
    await page.goto("/#/novels");

    await page.getByRole("button", { name: "设置", exact: true }).click();
    const account = page.locator('[data-od-id="pref-account"]');
    await expect(account).toBeVisible();
    await expect(account).toHaveAttribute("title", longName);
    const style = await account.evaluate((el) => {
      const s = getComputedStyle(el);
      return { overflow: s.overflow, textOverflow: s.textOverflow, whiteSpace: s.whiteSpace };
    });
    expect(style.textOverflow).toBe("ellipsis");
    expect(style.whiteSpace).toBe("nowrap");
    // 行不撑破：账号行宽度不超过弹窗体宽度
    const box = await account.boundingBox();
    const body = await page.getByRole("dialog").boundingBox();
    expect(box!.width).toBeLessThan(body!.width);
  });
});
