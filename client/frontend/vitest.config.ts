import { defineConfig } from "vitest/config";
import path from "path";

export default defineConfig({
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    globals: true,
    include: ["src/**/*.test.{ts,tsx}"],
    exclude: ["node_modules", "e2e"],
    coverage: {
      provider: "v8",
      // 覆盖率契约只锁「本次交付动过的文件」——不是整仓阈值（存量无关 UI 不在账上）。
      // 口径说明：语句/行/函数计 100%；分母**不含** `/* v8 ignore start|stop */` 标注的
      // 两处不可达防御分支（AcctMenu 的 position refs 组合、菜单项数恒 ≥4）。
      // 分支覆盖率未锁（未命中多为 `??`/`?.`/`||` 短路的另一半与 jsdom 不可达组合）。
      include: [
        "src/lib/api.ts",
        "src/lib/nodeTitle.ts",
        "src/components/novel/workbench/ManuscriptDownloadModal.tsx",
        "src/components/RestoreModal.tsx",
        "src/components/AcctMenu.tsx",
      ],
      thresholds: { statements: 100, lines: 100, functions: 100 },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
