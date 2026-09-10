import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["list"], ["html", { outputFolder: "playwright-report" }]],
  // 整轮跑完清一次 e2e 残留（失败用例漏下的书 / 孤儿目录 / e2e 建的配置与用户）；
  // 本地 Node ≥22.5 才真扫，CI Node 20 会跳过并提示（见 e2e/global-teardown.ts）
  globalTeardown: "./e2e/global-teardown.ts",
  use: {
    // 默认连 docker 生产前端（nginx 托管 dist + /api 代理到 client-backend:8000）。
    // 本地 dev 可 E2E_BASE_URL=http://localhost:5173 覆盖。
    baseURL: process.env.E2E_BASE_URL || "http://localhost:5174/",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
