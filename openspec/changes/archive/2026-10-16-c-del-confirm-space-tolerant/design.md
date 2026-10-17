# c-del-confirm-space-tolerant · design

## Context

见 proposal。组件现状：`components/novel/DeleteConfirmModal.tsx` 用 `input === confirmText` 严格相等点亮「确认删除」；唯一使用方 `NovelListPage.tsx`（书架，`confirmText={deleteTarget.name}`）。弹层不在 list.html parity 基线内（ADJUSTMENTS「应用侧扩展」清单同族）。剪贴板站内先例：`navigator.clipboard?.writeText(...)`＋`.catch`（NovelListPage:605、PromptPackCard 等）。

## Goals / Non-Goals

- Goals：手敲带入空白仍可确认；原文可一键复制；门禁防误删语义（内容逐字对上）不放松。
- Non-Goals：不改工作台/模型配置两处无输入确认的删除弹窗；不做「输入别名/短口令」等替代门禁；不动后端删除接口；不改 Modal 基座与共享段。

## Decisions

1. **比对口径＝`s.replace(/\s+/g, "")` 双方剥除后严格相等**。
   备选：仅 `trim()`（不解决文中空格，否）；unicode 归一化 NFKC（会吞全角/半角差异，误删面变大，否）。JS `\s` 覆盖 U+0020/U+3000/U+00A0/\uFEFF 等，正好覆盖「视觉空隙→手敲空格」的全部现实污染源；U+200B 零宽空格不在 `\s`——它不产生视觉空隙，不在本防御范围。
2. **复制钮＝`btn btn-ghost btn-sm`，紧随原文 `<b>` 之后**，`type="button"`＋`aria-label="复制书名"`；点击 `navigator.clipboard.writeText(confirmText)`，成功就地「已复制」1.5s 文案 swap；失败回退 `document.execCommand("copy")` 隐藏 textarea 老路，再失败 `toast.error("复制失败，请手动选择书名复制", { action: { label: "重试", onClick } })`（err 语气＋可点击出口，符合 §13）。
   备选：toast 告知成功（多一条漂浮物，弹窗内就地反馈更轻，否）。
3. **「已复制」反馈用组件内 useState＋setTimeout 自复**，不新增 pill/徽标形态（语气词表零新增）。
4. **ADJUSTMENTS 登记代替原型改动**：书架删除弹窗与 ⋯ 菜单同族（基线外应用侧扩展，不进 parity 截图），在「未动原型、只在应用侧扩展的」清单补一行，写明输入确认＋空白容错＋复制钮三点。

## Risks / Trade-offs

- [剥空白后两本仅空白差异的书互认] → 现实中书名以内容字符区分；确认弹窗一次只针对一本（`deleteTarget` 单值），无交叉误删路径。
- [execCommand 已废弃] → 仅作 clipboard API 失败后的回退（桌面 WebView/localhost 均为安全上下文，主路几乎恒成）；回退再失败仍有重试出口。
- [容错被理解为「门禁放松」] → 空白本就不构成身份差异（视觉欺骗恰来自空白），内容逐字比对保留，防误删语义不变；spec Scenario 钉死「内容不符恒禁用」。

## Migration Plan

纯前端组件改动，随下一发版走；无数据迁移。回滚＝还原单文件。

## Open Questions

无。
