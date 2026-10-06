import { test, expect } from "@playwright/test";

// 大屏自适应（large-screen-scale）：桌面壳窗口 = 屏幕宽-80，4K/超宽屏下 CSS 视口可达
// 2500~3800px，而全站是 1440 基准的 px 设计——不缩放时正文 14px 在大屏上只有 1440 屏
// 约 1/2.6 的角高（用户现场：2560 宽浏览器里「界面很小」）。现按视口宽度整体等比放大
// （--ui-zoom，见 src/design/large-screen.css）。
//
// 两条边界都必须钉住：
//  ① ≥2000px 真的放大，且壳层（状态条贴底、无纵向溢出）不被 zoom 的 vh 放大带偏；
//  ② ≤1920px 恒不缩放——1440×900 的像素基线（design-parity）与 1440/1920 的
//     尺寸断言（ui-spec-parity / settings-forms）都建在这条线上，动了就是全量假红。
//
// 落地页 `/` 不挂状态条（营销页豁免），故用 /login 这条无会话也能进、且带壳层的路由。
const ORIGIN = process.env.E2E_BASE_URL || "http://localhost:5174";

async function shellMetrics(page: import("@playwright/test").Page) {
  return page.evaluate(() => {
    const de = document.documentElement;
    const sb = document.querySelector(".statusbar")!.getBoundingClientRect();
    const spacer = document.querySelector(".statusbar-spacer")!.getBoundingClientRect();
    return {
      zoom: parseFloat(getComputedStyle(de).zoom || "1"),
      scrollH: de.scrollHeight,
      innerH: window.innerHeight,
      sbBottom: sb.bottom,
      sbH: sb.height,
      spacerH: spacer.height,
    };
  });
}

test("大屏等比放大：2000px 起生效，壳层仍精确铺满视口", async ({ page }) => {
  await page.setViewportSize({ width: 2560, height: 1400 });
  await page.goto(`${ORIGIN}/#/login`);
  await expect(page.locator(".statusbar")).toBeVisible();

  const m = await shellMetrics(page);
  // 2560 → 1.28 倍（2000px 基准线性放大）
  expect(m.zoom).toBeGreaterThan(1.2);
  // 状态条贴视口底，且垫片与状态条同高（不同高＝底部内容被遮或留白）
  expect(Math.abs(m.sbBottom - m.innerH)).toBeLessThan(2);
  expect(Math.abs(m.sbH - m.spacerH)).toBeLessThan(0.5);
  // 壳层高度补偿的判据：/login 自带 48px（app px）固有溢出 → 缩放后约 61px；
  // 若 .auth-wrap / #root 的 calc(100vh / var(--ui-zoom)) 漏补偿，这里会变成
  // (100vh-26px)×1.28 ≈ 450px 的纵向溢出，断言即刻变红。
  expect(m.scrollH - m.innerH).toBeLessThan(100);
});

test("≤1920px 不缩放：既有像素基线不受影响", async ({ page }) => {
  for (const width of [1440, 1920]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`${ORIGIN}/#/login`);
    await expect(page.locator(".statusbar")).toBeVisible();
    const m = await shellMetrics(page);
    expect(m.zoom).toBe(1);
    expect(m.scrollH - m.innerH).toBeLessThan(80);
  }
});
