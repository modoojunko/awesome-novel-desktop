import { defineConfig } from "vitest/config";
import path from "path";

import { COVERAGE_CONTRACT_FILES } from "./src/coverage-contract";

export default defineConfig({
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    globals: true,
    // scripts/ 下的构建期工具（如旧内核颜色兼容表生成器）与业务单测同批跑：
    // 它们是发布产物的一部分，错了同样要让 CI 红。
    include: ["src/**/*.test.{ts,tsx}", "scripts/**/*.test.mjs"],
    exclude: ["node_modules", "e2e"],
    coverage: {
      provider: "v8",
      // 覆盖率契约只锁「本次交付动过的文件」——不是整仓阈值（存量无关 UI 不在账上）。
      // 口径说明：语句/行/函数/分支均计 100%；分母**不含** `/* v8 ignore start|stop */`
      // 与 `/* v8 ignore next */` 标注的 **23 处**不可达/死码分支：
      //   AcctMenu 4（position refs 组合·菜单项数恒 ≥4·键盘查询 ?? []·409 空 message）
      //   RestoreModal 1（working 步二道锁）· ManuscriptDownloadModal 1（409 空 message）
      //   nodeTitle 1（`title ?? ""`）· ApiConfigForm 1（编辑态 `if (isEdit) return`）
      //   ExpiryNoticeBar 1（dismiss 的 `!notice`）· ApiKeyConfigPage 2（`!deleteTarget`·`!undoToast`）
      //   LoginPage 2（轮询重入守卫·「重新检测」的 spinner 臂——按钮要求 error 非空而两个 handler
      //     入口都 setError("")，进入 loading 时按钮已卸载）· NovelListPage 2（`!deleteTarget`·`!renameTarget`）
      //   VolumeAssistPanel 7（拆章行/节奏三行的防御 onClick——行必 disabled，React 吞 disabled click；
      //     节奏编辑态空 handler（恒 disabled）；节奏采纳二函数的 kind 守卫（按钮只在对应预览块渲染））
      //   PickCardsModal 1（确认时选中的卡必在 plans 里（选中与批次同生命周期）→ `if (card)` 恒真）
      // 每条注释都写了不可达理由；若相关可达性前提被改（如 LoginPage 移除 disabled/setError），须复核。
      // KbEntryGraphView 5（mount effect 的 `await import("force-graph")` 在 jsdom 挂起，后段不可达；
      //   装配链提取 lib/kbEntryGraph.ts 直测锁——该文件 v8 ignore 标注整体不生效，故以 lib 锁替代组件行锁）
      // lib/kbEntryGraph.ts 1（initEntryGraph 内的同一动态 import——挂起段随函数体整体 ignore；
      //   mountEntryGraph 直测覆盖装配链，lib 内 init 函数的其余行为由组件测试断言）
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
