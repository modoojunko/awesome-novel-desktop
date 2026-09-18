import { defineConfig } from "vitest/config";
import path from "path";

import { COVERAGE_CONTRACT_FILES } from "./src/coverage-contract";

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
      // 口径说明：语句/行/函数/分支均计 100%；分母**不含** `/* v8 ignore start|stop */`
      // 标注的 **8 处**不可达防御分支（AcctMenu 的 position refs 组合·菜单项数恒 ≥4·
      // 键盘查询 ?? []·409 空 message；RestoreModal 的 working 步二道锁；
      // ManuscriptDownloadModal 的 409 空 message（api.ts 已保证 message 非空）；nodeTitle 的
      // `title ?? ""`；ApiConfigForm 的编辑态 `if (isEdit) return`），每条注释都写了不可达理由。
      include: [...COVERAGE_CONTRACT_FILES],
      perFile: true, // 失败信息点名到具体文件（四项全 100 时与全局口径等价）
      thresholds: { statements: 100, lines: 100, functions: 100, branches: 100 },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
