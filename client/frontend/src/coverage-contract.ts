/**
 * 覆盖率契约的**单一事实源**：`vitest.config.ts` 的 `coverage.include` 与
 * `src/__tests__/coverageContract.test.ts` 都从这里取，避免"两个手写清单互相漂移"。
 * 新增交付批时只改这里；目录完整性由契约测试把守（api-config 目录不能漏文件）。
 */
export const COVERAGE_CONTRACT_FILES = [
  // c-chapter-plan-ai（卷下拆章：拆章弹窗/状态机/API 契约）
  "src/lib/chapterPlanApi.ts",
  "src/hooks/useChapterPlan.ts",
  "src/components/novel/workbench/ChapterPlanModal.tsx",
  // volume-plan-ai + c-volume-antagonist（分卷规划：抽卡/四问页/状态机/API 契约）
  "src/components/novel/workbench/PickCardsModal.tsx",
  "src/components/novel/volume/form.ts",
  "src/lib/volumePlanApi.ts",
  "src/hooks/useVolumePlan.ts",
  "src/components/novel/workbench/VolumePlanModal.tsx",
  "src/components/novel/workbench/VolumeAssistPanel.tsx",
  "src/lib/metrics.ts",
  // 批 0（#417/#418 交付触及的 5 个文件）
  "src/lib/api.ts",
  "src/lib/nodeTitle.ts",
  "src/components/novel/workbench/ManuscriptDownloadModal.tsx",
  "src/components/RestoreModal.tsx",
  "src/components/AcctMenu.tsx",
  // 批 1（风险优先：密钥/账号/路由面）
  "src/lib/selection.ts",
  "src/App.tsx",
  "src/components/auth/AuthGuard.tsx",
  "src/components/api-config/ApiConfigCard.tsx",
  "src/components/api-config/ApiConfigForm.tsx",
  "src/components/api-config/DeleteConfirmDialog.tsx",
  "src/components/api-config/MigrationBanner.tsx",
  "src/components/api-config/ProviderIcon.tsx",
  "src/components/api-config/UndoToast.tsx",
  "src/components/api-config/UsagePieChart.tsx",
  "src/components/api-config/UsageStatsCard.tsx",
  "src/components/api-config/ZhuquePanel.tsx",
  "src/hooks/useDeviceActivation.ts",
  // 批 1 第二波（页面面：模型配置页收口 + 到期提示条 + 落地页 + 工作台布局）
  "src/pages/ApiKeyConfigPage.tsx",
  "src/components/ExpiryNoticeBar.tsx",
  "src/pages/LandingPage.tsx",
  "src/pages/NovelLayout.tsx",
  // 批 1 收尾（pages 全量；此后 pages 目录完整性由契约测试的目录断言把守）
  "src/pages/LoginPage.tsx",
  "src/pages/NovelListPage.tsx",
] as const;
