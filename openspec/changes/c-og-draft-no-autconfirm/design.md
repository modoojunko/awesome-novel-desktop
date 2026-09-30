## Context

- 自动确认现状：`handleSaveDraft`（ChapterWorkspace.tsx:484-494）保存成功后 `ogGaps(ogForm).length === 0 && ogStatus !== "confirmed"` 时调 `outline.confirmChapter`。PR 3 时代登记（ADJUSTMENTS「仅显式保存草稿/确认章纲触发自动确认」）；c-og-slim-v2 必填 4→2 后无缺口几乎恒成立，行为冲突暴露。
- 确认态形状：后端 `POST /chapters/{ref}/confirm`（router.py:313）置 `chapter["status"]="confirmed"`＋row 三写（status/outline_status/confirmed_at）；`save_chapter` 统一写入口 `status = data.get("status") or row.status`（store.py:620）——撤回＝显式传 `status: "draft"` 即走既有白名单派生，outline_status 经 `_derive_outline_status` 回 `unfilled`/`in_progress`（有正文时）。
- 确认态消费面（撤回的安全边界）：树徽标/确认计数（前端 list_volumes 的 status）、OgPane 徽标与按钮禁用、`settings/ai_router.py:1306` 的 `outline_status != "unfilled"`（已写章纲判定，撤回后有正文仍算 in_progress 不掉）——撤回不触任何破坏性链路；归档态章不提供撤回（页签只读，无入口）。

## Goals / Non-Goals

- Goals：保存草稿语义＝字面（只保存）；已确认章有后悔药；两个 e2e 旧断言口径矫正。
- Non-Goals：不动确认 gate（必填两项）；不动 3s 自动保存（本就不改状态）；不做「确认历史」；不动「去写正文」路径（它调 saveOg 但从不确认，本就语义干净）。

## Decisions

- **D1 前端删自动确认段，不挪去确认按钮**：`handleSaveDraft` 缩成 `saveOg→toast`；「确认章纲」已是完整显式路径，无需补。
- **D2 撤回端点 `POST /chapters/{ref}/unconfirm`**：load_chapter→`chapter["status"]="draft"`→save_chapter（统一写入口，白名单/派生/快照链全复用）→row.status="draft"、confirmed_at=None（outline_status 不手写，等 store 派生）；409 守卫＝已归档章拒撤（归档态经 unarchive 路径，语义不同）；已草稿章幂等返回 ok。与 confirm 对称放 router.py。
- **D3 撤回入口放查看态「已确认」徽标旁**：`done-note` 行内 ghost 小按钮「撤回确认」→ confirm 弹窗（复用既有弹层形态，info 语气，双出口「保留确认/撤回」）→ 调端点 → reloadStatus 刷新徽标＋refetchTree 刷计数。编辑态不出现（先取消编辑再撤）。
- **D4 toast 口径**：保存草稿恒「草稿已保存」；撤回成功「已撤回确认，章纲回到草稿态」。
- **D5 useOutline 加 `unconfirmChapter`**：与 confirmChapter 同层（api.post＋错误 toast），保持 store 单源。

## Risks / Trade-offs

- 行为变更（保存草稿不再顺手确认）：e2e 两处断言改口径（outline-ai-draft:174、workbench-features:193），断言改的是**预期行为本身**——无静默收窄。
- 撤回后树上计数回落依赖 refetchTree：与既有改名/建章刷新链同源，无新机制。

## Migration Plan

无数据迁移；已确认存量章不受影响（保持确认，等作者自行决定撤回）。

## Open Questions

（无——方案 A 已拍板。）
