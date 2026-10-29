# c-modelconfig-help-guide 任务

## 1. 组件与文案

- [x] 1.1 `ConfigGuideModal.tsx`：文案常量表（GUIDE_TABS／GUIDE_CONTENT／OPENAI_KEY_SOURCES，逐字取原型）＋三页签＋四步＋FAQ＋固定 880×760。
- [x] 1.2 `guideTabForVendor` 映射（anthropic/opencode-go-claude→anthropic；gemini→google；余→openai）。
- [x] 1.3 `theme.css` 追加 `guide-*` 样式段（token 变量，无新颜色字面量）。

## 2. 入口

- [x] 2.1 `ApiKeyConfigPage.tsx`：页头「配置指南」副按钮（guide-actions 成组）。
- [x] 2.2 `ApiConfigForm.tsx`：`onOpenGuide` prop＋vgrid 下引导行；`onVendorChange` 上报选中供应商；页面侧定位打开。

## 3. 测试与质量

- [x] 3.1 `configGuideModal.test.tsx` 新用例（页签切换/映射矩阵/文案黑名单/地址表 8 家）。
- [x] 3.2 `apiConfigParts.test.tsx` 增补（引导行渲染/回调/未传不渲染）。
- [x] 3.3 `vitest run` 全量绿＋`tsc --noEmit`＋`ruff/py` 不涉及（纯前端）；`npm run build` 过 legacy-colors 扫描闸。

## 4. 归档与 PR

- [ ] 4.1 openspec validate 全绿；sync delta 入 `openspec/specs/model-api-config/spec.md`＋change 移档 `archive/2026-10-29-c-modelconfig-help-guide`。
- [ ] 4.2 原型四件（原型.html/.src.html/设计说明/captures）随 PR 入库。
- [ ] 4.3 提交（只挑本 change 文件）＋push＋`gh pr create`（标题带 change id）。
