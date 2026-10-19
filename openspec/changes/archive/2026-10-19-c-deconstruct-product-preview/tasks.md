# 拆书结果目录只读预览 — 实施任务

## 1. 前端预览

- [x] 1.1 `deconstructApi` 增加 `getDeconstructProduct(id, filename)`（复用既有
      `GET /deconstruct/tasks/{id}/products/{filename}`，文件名 `encodeURIComponent`）。
      验证：`toolsApi.test.ts` 既有契约不回归（请求封装走 `request()` 单源）。
- [x] 1.2 `TaskDetailPage` 完成态结果目录行重构：`label` 整行 → `div` 行（行点击仍切换勾选），
      文件名改文本按钮（`stopPropagation`，点击不波及勾选），勾选框点击 `stopPropagation`
      防双触发。验证：既有「默认全选、下限 1」用例不回归＋新增「点文件名勾选不被动」断言。
- [x] 1.3 预览弹窗（scrim＋`mcard.rd-style`）：加载中 → 全文 pre-wrap（超长滚动）；
      失败 toast 报错并收起；✕／脚部「关闭」／scrim 三路可关。验证：`toolsDetail.test.tsx`
      预览三态用例（成功＋加载中／失败 Error 与非 Error 两臂／三种关闭）。
- [x] 1.4 文案翻面：底部提示改「点文件名可预览（只读）；应用内不编辑拆解产物」；目录树头补
      「点文件名可预览」。验证：页面无「应用内不预览」残留字样。
- [x] 1.5 样式：`index.css` `.fd-name`（文本按钮形态，悬停 accent 下划线）；
      `design/base.css`【C端 本地段】`.mcard.rd-style`＋`.preview-md`。验证：
      `npm run check:inline-colors` 与 `design:lint` 通过（仅引用令牌，未触共享段）。

## 2. 后端

- [x] 2.1 `router.get_product` docstring 口径更新（预览与导出共用）；零行为改动。
- [x] 2.2 端点行为钉（此前无直接测试）：清单内回全文；清单外文件名与 `..%2F` 穿越名一律 404。
      验证：`uv run pytest client/backend/tests/test_deconstruct_api.py -q` 全绿。

## 3. openspec 与设计工件

- [x] 3.1 本变更 proposal／tasks／spec delta（MODIFIED「结果目录与出口勾选」，预览翻面）。
      验证：`openspec validate c-deconstruct-product-preview --strict` 通过。
- [x] 3.2 原型补注：`docs/design-c/drafts/ai-novel-c端-拆书.html` 完成态目录树加文件名可点
      与预览弹层；`docs/design-c/prototypes/ADJUSTMENTS.md` 登记条目。
- [x] 3.3 归档联动：`c-deconstruct-book` 先归档（使主 specs 存在 `deconstruct-book`），
      再归档本变更；届时 `c-deconstruct-resilience` 若仍未归档，顺序不冲突（不同 requirement）。
