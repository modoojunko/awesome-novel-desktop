## Context

见 proposal.md。三条约束：右栏数据通道被多处消费（换装不撤通道）；`onRailData` effect 前科（身份抖动
死循环，本次不动该链）；卷域「体检免费可用、生成归 PRO」与章域「整卡 PRO 门控」语义不同（换装不得抹平）。

## Decisions

- **D1 ra-* 全局化而非复制**：类名家族从 `.settings-v` 前缀提升（删前缀），写作域同名旧基线移除；
  不新建第二套类。
- **D2 内容槽保留**：报告组（rp-*）、分卷依据（dep-row）、卷的验证（ledger）作为 `children` 挂在能力行
  与 ra-foot 之间——造型统一、内容各域自定（用户口径原话）。
- **D3 门控分域不改语义**：章面板 isPro→ready/member_required（整卡 locked＋点击统一升级）；
  卷面板 aiState＝ready（体检免费），仅「拆下一章」等 PRO 行单独 disabled/hint。
- **D4 busyRef 互斥沿用模板**：ra-step 点击经模板 busyRef 串行，单测连点需 await act（既有模板行为）。
- **D5 testid 双锚**：能力行沿用旧按钮 testid（ai-write-btn/og-ai-draft/volume-check-btn…）；
  卷验证面板根节点补 `data-testid=volume-verify-panel`（模板加该 prop）。

## Risks / Trade-offs

- 写作域右栏与原型 `.col-ai` 差异扩大（主动偏离）→ ADJUSTMENTS 登记，parity 基线待原型同批更新。
- 免费态从「置灰禁点」改「可点但拦下」：真实点击行为等价（原 CSS pointer-events 拦截），
  且测试以 disabled 表达更严格；e2e 免费锁定断言同批改整卡口径。

## Migration Plan

纯前端同批切换，无迁移。
