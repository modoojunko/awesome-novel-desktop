## 1. 裁决清单（先出后改）

- [ ] 1.1 对 4 例 diff 图做分带统计，逐密集区打开原型 DOM 与实现 DOM 对比，产出裁决清单（每区：差异描述｜以谁为准｜依据｜改动面）。验证＝清单覆盖 4 例的全部密集差异带（分带统计数据附后）
- [ ] 1.2 裁决清单里「原型为准→改实现」的命中项，逐条标注影响面与回归依据；命中为零则登记为零

## 2. 基线重录（free·workbench 主例先行）

- [ ] 2.1 按裁决清单改 `docs/design-c/prototypes/book.html` 工作台屏（书主页卡/三页签/章纲 13 格/信息差块/落点卡 2 项/弹窗三态等），每区保留可回滚的编辑边界。验证＝Playwright 打开 book.html 零 console 错误
- [ ] 2.2 `DESIGN_PARITY=1` 重跑 `design-parity-book.spec.ts`：`free · workbench` 转绿（像素差 <0.2%），新基线三图落 `docs/design-c/baselines/`
- [ ] 2.3 弹窗三例（modal-delete/prefs/upgrade）按同流程转绿；弹窗本体如仍有差按 D4 单独裁决后重录

## 3. 登记与回归

- [ ] 3.1 `ADJUSTMENTS.md` 汇总登记：替代 #465 的存量漂移登记条目，逐区列「以谁为准」；文案例（如有「原型为准→改实现」）逐条补实现说明
- [ ] 3.2 若命中「原型为准→改实现」项：同步实现侧改动＋相关单测；验证＝vitest 相关文件绿
- [ ] 3.3 门禁：`design-parity-book.spec.ts` 4 例全绿；`npm run design:lint` 与 `npm run design:check`（design-parity + preview）不回归；`npx tsc --noEmit` 0 error
