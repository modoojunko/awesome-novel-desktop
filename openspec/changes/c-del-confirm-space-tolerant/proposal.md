# c-del-confirm-space-tolerant

## Why

书架删除小说要求逐字输入书名确认；导入类书的标题（如 `soushu2025.com@【恐怖】《13路末班车》【作者：老八零】[搜书吧]`）全角括号字形自带留白，视觉上像空格而实际一个都没有，手敲几乎必然带入空白差异 → `input === confirmText` 恒不成立 →「确认删除」恒禁用，用户报「无法删除书」。2026-10-16 真实 UI 实勘复现：精确串按钮点亮、照视觉敲空格的两个变体恒灰（已在案）。

## What Changes

- 书架「删除小说」确认弹窗（`components/novel/DeleteConfirmModal`）比对口径改为**剥除全部空白后逐字相等**：空白差异（手敲空格／全角空格／首尾空白）不再拦删除，书名内容仍须逐字对上，防误删语义不变。
- 确认文案旁新增**「复制」**小按钮：一键复制原文书名，就地「已复制」短反馈；剪贴板失败给错误提示并带「重试」可点击出口（沿站内 `navigator.clipboard` 先例）。
- `ADJUSTMENTS.md` 应用侧扩展清单补登「删除小说确认弹窗」条目（该弹层本就不在 list.html parity 基线内，沿 ⋯ 菜单条目同口径）。

## Capabilities

### New Capabilities

- `novel-delete`: 书架删除小说的确认门禁行为——输入确认的空白容错比对口径、「复制」辅助、确认执行与取消路径。

### Modified Capabilities

（无——现存 specs 无任何 capability 覆盖书架删书确认，见 `openspec list --specs` 全量排查。）

## Impact

- `client/frontend/src/components/novel/DeleteConfirmModal.tsx`（唯一使用方 `NovelListPage.tsx:921`，`confirmText={deleteTarget.name}`）
- 新增 `client/frontend/src/__tests__/deleteConfirmModal.test.tsx`（现无该组件专属测试，list 页测试里是 mock）
- `docs/design-c/prototypes/ADJUSTMENTS.md`（应用侧扩展登记）
- 不触后端；不触两端共享段（复用既有 `btn btn-ghost btn-sm` 形态与 toast，无 base.css/令牌改动）

## Design Impact

- 受影响端：**C端 only**（S端 无书架删除弹层）。
- 受影响屏/弹层：书架 /novels「删除小说」确认弹窗（list.html 基线外的应用侧扩展，同 ⋯ 菜单口径）。
- 对象状态：无新增状态语言形态——复制钮沿用既有 `btn-ghost btn-sm` 形态＋「已复制」文案 swap（1.5s 自复）；错误提示走既有 toast（err 语气）＋「重试」action。
- 两端共享段：不触碰（无令牌/基础类/pill/notice/sk/panel/f-err 家族改动，免 design-cross）。
- 原型先行：**豁免**——弹层不在 parity 基线（ADJUSTMENTS「未动原型、只在应用侧扩展的」既有清单同族），以 ADJUSTMENTS 登记代替原型改动；设计工件由实现侧自查产出。
- 文案（design-language §13）：「复制」为动词✓；无内部术语✓；失败补救带可点击出口（「重试」）✓。
