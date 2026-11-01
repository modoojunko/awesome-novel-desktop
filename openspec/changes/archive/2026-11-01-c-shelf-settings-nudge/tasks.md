## 1. 原型先行

- [x] 1.1 `docs/design-c/prototypes/list.html`：设定态书卡 CTA「继续创作」→「去补设定」（按 state 分支）；0 章占位「可稍后添加」→「可在 ⋯ 菜单添加」。验证：`npm run design:lint` 绿（存量 preview.html emoji 红对拍 main 放行，A/B 定罪）。

## 2. 实现

- [x] 2.1 `NovelListPage.tsx`：页脚 setting 态 CTA「继续创作」→「去补设定」（writing 恒「继续创作」不变）；0 章无封面占位「可稍后添加」→「可在 ⋯ 菜单添加」。零逻辑/零样式改动。验证：`tsc --noEmit` 绿。

## 3. 测试

- [x] 3.1 vitest 文案断言更新（`novelListPage.test.tsx` 3 处触点）；覆盖率分支保持 100%。验证：页面 vitest 79/79 绿＋`npm run coverage` 全仓 100%（NovelListPage 四列 100）。
- [x] 3.2 e2e `image-workshop.spec.ts`「可稍后添加」钉改写为新文案＋加钉设定态 CTA。验证：隔离栈（18991/5194 专属端口＋专属 DATA_ROOT）本地 3/3 绿。

## 4. 收尾

- [ ] 4.1 `openspec validate` 零新增红；PR：实现＋openspec sync 归档同 PR。验证：CI 双绿合入。
