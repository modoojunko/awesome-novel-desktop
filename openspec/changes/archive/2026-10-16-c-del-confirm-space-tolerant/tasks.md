# c-del-confirm-space-tolerant · tasks

## 1. 原型先行（应用侧扩展登记）

- [x] 1.1 免原型 HTML：弹层不在 list.html parity 基线（`docs/design-c/prototypes/`无删除小说弹层）；在 `docs/design-c/prototypes/ADJUSTMENTS.md`「未动原型、只在应用侧扩展的」清单补登「删除小说确认弹窗——输入确认＋空白容错比对＋原文复制钮」条目。验证：条目可见且与 ⋯ 菜单条目同格式。

## 2. 组件实现

- [x] 2.1 `components/novel/DeleteConfirmModal.tsx`：比对改双方 `replace(/\s+/g,"")` 后相等；新增「复制」钮（btn-ghost btn-sm、type=button、aria-label=复制书名）——clipboard 写入→「已复制」1.5s swap→失败回退 execCommand→再失败 toast.error＋「重试」action。验证：`npx vitest run src/__tests__/deleteConfirmModal.test.tsx` 绿。

## 3. 测试

- [x] 3.1 新增 `src/__tests__/deleteConfirmModal.test.tsx`：精确输入点亮／带空格（半角·全角·首尾）点亮／内容不符禁用＋Enter 无效／复制写入剪贴板且不动输入框／剪贴板失败出重试出口／确认回调与取消回调。验证：同上命令绿，且 `novelListPage.test.tsx` 既有删除链用例不回归。

## 4. 门禁与回归

- [x] 4.1 门禁实跑：C端 `npm run design:lint`、`npm run design:check`（书架场景无新增红——弹层不在 parity 基线，存量红口径不变）、`tsc --noEmit`、相关 vitest 全绿；不触共享段免 design-cross（依据 proposal Design Impact）。验证：贴各命令实际结论。
- [x] 4.2 demo 栈抽检（本对话独立栈）：搜书吧导入书删除全链——照视觉敲空格可过门禁、复制钮粘贴可过、误输内容仍拦。验证：真机操作留痕。

### 回归实测（worktree ai-novel-wt-del-confirm，2026-10-16）

- `npx vitest run`：125 文件 / 1519 例全绿（含新增 deleteConfirmModal.test.tsx 9 例）。
- `npx tsc --noEmit`：exit 0。
- `npm run design:lint`：过（存量冻结观察口径不变）。
- `DESIGN_PARITY=1 playwright test e2e/design-parity*.spec.ts`：7 过 1 红——唯一红＝书架 quota 0.026927（2.693%），与既有存量红逐位吻合（光栅漂移，非本次引入；A/B 依据＝数值恒等＋弹层不入 parity 截图）。
- 真机抽检（vite dev 5175 → demo 后端 8000，书＝搜书吧导入书）：①照视觉空隙敲空格「确认删除」点亮（用户实报失败形态修复）；②缺字误输仍禁用＋Enter 无效；③复制钮：writeText 收到精确 40 字原文、「已复制」闪现 1.5s 回落；页面内全链断言过。剪贴板**读回**与宿主直写受 IAB 宿主策略所限（NotAllowedError）未能采样，成功路径以页面内 writeText 桩＋单测 writeText 断言双保险。
- 未实测项：打包壳（WebView2）真机点复制——Chromium 系 clipboard-write 对激活文档默认放行，随下一发版真机抽检兜底。

## 5. 收尾

- [x] 5.1 提交分支＋PR（openspec change 与实现同 PR）；合入后归档另起（沿惯例）。
