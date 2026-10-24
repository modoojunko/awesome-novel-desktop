# c-paper-empty-fill — 正文纸空章/短章也撑满可视桌面（查看态不再塌成纸边距一条）

## Why

用户反馈（2026-10-24，附截图）：空章正文页签里「纸」只剩一小条白条浮在桌面中央。病灶＝纸面高度随内容走，而「填屏」flex 链（10-08 用户反馈立起的 `c-prose-edit-fill-height`）只挂在**编辑态**（`.editor-wrap.editing`）——查看态的 wrap 不是 flex 容器，纸塌到只剩内容高：空章＝上下纸边距（56＋72px 的 padding）加零内容，约 130~190px 一条。这跟「纸是这张桌上的一张纸」的纸面隐喻相悖：真实的一张纸不会因为没写字就缩成纸屑。

与 2026-10-22 拍板的「纸型＝A 连续纸（纸随内容长）」不冲突：本 change 只给纸加**下限**（至少一屏桌面高），连续纸「随内容长、超屏照常滚动」的语义原样保留。

## What Changes

- **纸面最小高度（两态通用）**：查看态与编辑态，纸面（`.prose-paper`）SHALL 至少撑满正文列可视区——纸高＋上下纸外距＝正文列可视高；空章/短章不再塌条。实现＝「填屏」flex 链的 wrap／纸两级从 `.editing` 作用域上移为 base（`.editor-wrap` 恒纵向 flex、纸 `flex: 1 0 auto`）；编辑态专属的 host/editor 两级（纸作 flex 容器＋版心撑满可点击聚焦）原样保留。
- **明确不做**：不改纸宽/版心/纸边距任何横向语义；不改滚动容器（仍 `.editor-wrap`，续写滚动比例恢复、贴底自动滚、切章保持编辑态等既有行为不动）；不给查看态 editor 加撑满（纸内空白点击聚焦仍是编辑态专属语义）；不动人味边注层（absolute 定位，不受 flex 影响）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `workbench`：「正文区纸面呈现（桌面／纸／写字范围框）」新增「最小高度（填屏下限）」要求＋「空章纸不塌条」场景；两态通用，超屏滚动语义不变。

## Design Impact

- **受影响端**：C端 前端纯 CSS（`book.css` 一处作用域上移＋注释更新）；无数据、无接口、无 S端。
- **受影响屏**：章工作台正文页签（查看态/编辑态/生成中/历史旧稿支线同列共享，全部受益于同一填屏下限）。
- **共享段**：不触碰（不改 base.css 令牌与基础组件类）。
- **原型**：无需先行——纸面三层结构与连续纸语义均沿用已拍板原型（`docs/design-c/drafts/ai-novel-c端-正文纸张-原型.src.html`，2026-10-22 纸型＝A）；本 change 是该原型落实现后用户实测反馈的下限补丁。

## Impact

- `client/frontend/src/design/book.css`：`.editor-wrap` 基类加纵向 flex；新增 `.editor-wrap > .prose-paper { flex: 1 0 auto; }`；`.editor-wrap.editing` 的 wrap/纸两条上移后删除、注释随改。
- `client/frontend/e2e/paper-fill.spec.ts`（新增）：三态几何断言——空章（查看＋编辑两态纸撑满）/短章（撑满不塌）/长章（纸长过可视区＋滚动可达），真实布局量测（`getBoundingClientRect`）。
- 回归面：编辑器相关存量 e2e（free-writing-flow 等）＋前端全量单测；同栈 A/B 定罪与本改动无关的存量红。
