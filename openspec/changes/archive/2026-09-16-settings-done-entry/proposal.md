# settings-done-entry

## Why

设定页左栏的「设定完成 · 去写作」入口现状是一颗全宽普通主按钮（`btn-primary`）直接插在进度条与导航项之间：和「保存」长得一样、没有里程碑完成的分量、完成后永久挂着与导航抢视觉。用户反馈「设计的很难看」，并拍板与「设定 8/8」进度行**合一**——同一元素两状态：日常是进度行，8/8 完成瞬间整行升级为完成卡，不再另叠第二块。

## What Changes

- **完成态合一**：`done === total` 时进度行本体升级为完成卡——行头对勾图标＋「设定完成 8/8」＋「全部就绪」徽标，整块 ok-soft 底＋ok 描边（状态语言 §5：完成=ok 绿），进度条转满格绿，块内展开主 CTA「去写作」（唯一行动点）＋小字「写作时也能回来改设定，不冲突」
- **旧按钮退役**：全宽普通主按钮「设定完成 · 去写作」从左栏移除；「去写作」只从完成卡进入；`onGoWrite` 行为不变（切换到写作视图）
- **未完成态零变化**：`done < total` 时进度行保持原样（无完成卡）；本轮不做「下一步引导条」（non-goal）
- **词表登记**：`settings-progress.done` 变体＋`.pb-check/.pb-badge/.done-btn/.done-foot`，ADJUSTMENTS 登记后入 book.css settings-v 段
- 明确不做（non-goals）：7/8 引导条（下一批可议）；「设定完成」卡在中栏的镜像；自动跳转写作视图（仍需作者点击）

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `character-settings` 不涉及；`creation-flow`：设定全部确认后，左栏 SHALL 出现完成卡（对勾＋设定完成 8/8＋全部就绪徽标＋去写作 CTA），点击「去写作」SHALL 切换到写作视图——替代原全宽按钮
- `design-system`: 新增设定完成入口词表（settings-progress.done 变体、pb-check/pb-badge/done-btn/done-foot），复用既有 ok 状态语言与 btn-primary 档位，不新增胶囊/徽标形态

## Impact

- **C端前端** `client/frontend`：`components/novel/workbench/SettingsView.tsx`（done 分支渲染改造，约 20 行）；`design/book.css`（done 变体样式）；`e2e/creation-flow.spec.ts`（设定全确认用例尾部断言完成卡与去写作跳转）
- **C端后端**：零改动（纯展示层）
- **迁移**：无；`onGoWrite` 契约不变
- **设计工件**：设计稿 `docs/design-c/drafts/ai-novel-c端-设定完成去写作.html`（v2 合一版，用户已过目）转正 `docs/design-c/prototypes/settings-done-entry.html` 并登记 ADJUSTMENTS

## Design Impact

- 受影响端：**C端**
- 受影响屏：设定页左栏「设定进度」行（完成态变体）；无新弹层
- 对象状态（§5）：完成=ok 绿（对勾＋「全部就绪」徽标＋满格绿条）；主 CTA 沿 accent 主按钮档位
- 触碰两端共享段：否（settings-v 作用域变体类）
- 原型先行：是——设计稿转正 prototypes 并登记 ADJUSTMENTS 后再动实现
- 设计工件来源：设计侧会话（用户已拍板合一方案）
