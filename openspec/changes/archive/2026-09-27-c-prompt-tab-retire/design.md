## Context

见 proposal.md。关键约束：弹窗（AiModal）已是两段式查看/编辑/润色/生成闭环，退役页签只需补「落库」
与「状态可见」两个缺口；`prompts/write` PUT 端点与 `polished` 语义既有；prompt-panel feature key
被后端 entitlement 快照消费（auth_local/service.py 下发列表含之），不得删。

## Decisions

- **D1 存稿行而非新弹窗**：AiModal 编辑框下方加「存为本章提示词」＋说明行
  「直接生成＝这一版只用于本次；存下来则本章以后每次生成都用它」——不复用已退役的 PromptManagementPage。
- **D2 状态进作用域行**：与字数/完成度同排（一行内），懒取 `GET prompts` + `prompt-sources`，
  失败降级「…」；随 `promptSavedSignal` 刷新（onRailData effect 依赖数组同步——实锤踩坑点）。
- **D3 chips 详情不迁移**：六来源明细清单（含未填标注）随页签退役——弹窗全文可核对内容，缺口在文中可辨；
  ADJUSTMENTS 登记。
- **D4 feature key 保留**：prompt-panel 仍在下发快照中；删它有契约成本、无收益。

## Risks / Trade-offs

- 「不想生成只看提示词」路径变深（须开弹窗再取消）——换来页签行净一层；用户口径已拍板。
- 多章提示词浏览（原整章单卡列表）退役——属提示词管理场景，写作工作台不再承载。

## Migration Plan

纯前端同批切换，无迁移。
