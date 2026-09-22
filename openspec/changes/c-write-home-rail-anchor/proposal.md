# Proposal: c-write-home-rail-anchor

## Why

整书拆卷（volume-plan-ai）已经能用，但「拆卷 → 写」这条动线上有三处细节把作者卡住：

1. **点「写作」回不到书主页**：现在点「写作」不重置选中，人在章页就还是章页、在卷页就还是卷页——想建一卷、排一章、看一眼全书进度，得先自己找路回到「没有选中节点」的那一页。
2. **右栏 AI 在卷页不随页签变**：章页右栏随八个页签换内容，卷页（卷纲／本卷章节／角色关系／伏笔）四个页签却是同一张「卷的验证」，与「AI 辅助都收在右栏、跟着当前页面变」的口径不符。
3. **抽卡时看不到上一卷的结尾**：规划台顶部有「上一卷的结尾」锚点块，但滚到 3 套卡片处已看不见；判断哪一套接得上上一卷，只能来回滚。

三处都是口径级细节，不改数据模型、不新增 AI 端点，改完动线才顺。

## What Changes

1. **三个页签各自回默认主页**：书内三个页签点下去 SHALL 落各自的默认落点，**BREAKING（交互口径）**，不再停在上次那一步：

   | 页签 | 默认落点 | 现在的问题 |
   |---|---|---|
   | 写作 | 书主页（清当前选中） | 保留上次选中的章/卷；从设定/预览切回也停在那里 |
   | 设定 | 默认面板（第一项「简介」） | 从别处进来本就是默认面板；**已在设定时再点「设定」不回位** |
   | 预览 | 全书首章 | 继承写作视图当前章；**已在预览时再点「预览」不回位** |

   「任何入口」都成立：顶栏页签、设定左栏完成卡的「去写作」、预览空书出口的「去写作」都回默认主页。默认页三态（空书／有卷未排章／已排过章）统一给出「＋ 新增一卷」「＋ 新增一章」两个建书入口（建卷走**同一个规划流**：付费＝三选一抽卡、免费＝四问手写页——c-volume-antagonist 起「添加卷」独立弹窗已退役），并给「续写」主入口回到主线端点章（与顶栏同源）。离开前守卫：卷纲表单有未保存修改、设定表单有未保存修改、或正文 AI 正在流式生成时，先二次确认。
2. **右栏跟着卷页签变（不新增 AI 能力）**：卷选中态右栏仍是「卷的验证」（体检这一卷，免费只读），但随卷页签重排：「当前页签」显示真实页签名（卷纲／本卷章节／角色关系／伏笔）、引导语按页签换、体检报告三组按页签把相关一组前置（卷纲→对主线，本卷章节→对已写内容，角色关系／伏笔→对设定）；卷纲页签另给「重新规划这一卷（AI）」入口（复用规划台与既有两个生成端点）。**不复活** volume-plan-ai 已退役的「卷选中态四页签统计卡」与卷域动作清单。
3. **抽卡卡片自带「上接」**：三选一抽卡的每张方案卡在卡首加一条「上接」，内容＝这一卷的进场（第二卷起＝上一卷的结尾；首卷＝全景起点），两行内截断、悬停看全文；取数沿用后端 `GET /volumes/plan-anchor` 单源（事实优先）——后端零改动、不参与提示词与去重。

## Capabilities

### New Capabilities

（无新增 capability）

### Modified Capabilities

- `workbench`：新增「页签回默认主页（写作／设定／预览）」行为需求（三个页签各自回默认落点、重复点同样回默认、离开守卫）；修改「EmptyState without settings gating (N4)」（默认页恒有建书入口 + 书主页卡）；修改「右栏『AI 辅助』面板（随页签切换，动作全部落地）」中卷选中态一条（由「单一验证面板」改为「随卷页签重排的验证面板」＋卷纲页签规划入口）。
- `preview-reader`：新增「预览定档＝全书首章」需求（进入与重复点「预览」都落首章；不再继承写作视图当前章）。
- `volume-plan-ai`：新增「抽卡卡片自带进场（上接）」需求；卷纲体检需求补「随卷页签重排 + 卷纲页签重新规划入口」。

## Impact

- **代码（C端 client/frontend）**：`components/novel/NovelWorkspace.tsx`（三个页签的回默认动作与守卫、书主页卡、`initialRef` 继承下线）、`hooks/useWorkbench.ts`（清选中复用）、`components/novel/workbench/SettingsView.tsx`（回默认面板信号）、`components/novel/workbench/PreviewView.tsx`（回首章信号）、`components/novel/workbench/VolumeAssistPanel.tsx`（卷右栏随页签）、`components/novel/workbench/VolumePlanModal.tsx`（卡片「上接」）、`components/novel/workbench/Rail.tsx`（卷语境传页签）、`src/design/book.css`（默认页与「上接」行的既有类微调）。
- **原型（设计事实源，先行）**：`docs/design-c/drafts/storyline.html`（卷页签右栏段 `aiVolHTML` 收窄为「验证面板随页签」）＋ `docs/design-c/drafts/ai-novel-c端-整书拆纲.html`（默认页④与 cand 卡「上接」）＋ `docs/design-c/prototypes/ADJUSTMENTS.md` 登记。`prototypes/book.html` 不动（本 change 不改其 parity case「默认章工作台」的版式）。
- **测试**：vitest（NovelWorkspace / volumePlan / VolumeAssistPanel / previewReader 相关用例）＋ e2e（`volume-plan.spec.ts`、`workbench-features.spec.ts`、`settings-forms.spec.ts` 等 20 余处「点写作」的既有用例需按新口径补一步选章/续写，预览定档与页签回位补新断言）。
- **不触碰**：两端共享段（base.css 令牌与基础组件类、pill/notice/sk/panel 家族）——改动落 book.css 业务层与 workbench 组件；后端零改动（不新增/不改端点）；S端 无关。

## Design Impact

- **受影响端**：仅 C端（`client/frontend` + `docs/design-c/drafts` 两份原型）。
- **受影响的屏/弹层**：写作页（默认页三态＝空书起手卡／落点卡／新的书主页卡；右栏卷语境四页签）；设定页（重复点「设定」把面板拨回默认项，面板自身版式不变）；预览页（定档改为首章，三栏与阅读配置不变）；规划台弹窗（`cand` 卡片首行「上接」）。左树、顶栏、章页右栏不动。
- **对象状态（对照 design-language §5 状态语言总表）**：只复用既有态——按钮 enabled／disabled（PRO 置灰、生成中禁用）、loading（「体检中…」）、empty（默认页引导文案）、只读（体检报告）；**无新增档位、无新增语气词（仍限 info/ok/warn/err）、无第四种胶囊形态**、不引入新组件词汇。
- **是否触碰两端共享段**：否——改动全部落 C端 业务层（`book.css` 的 wb 段与 workbench 组件），不触 `base.css` 令牌与基础组件类，故 S端 无同批改动、无需 `design-cross` 基线。
- **是否需要原型先行**：需要（写作页与规划台有用户可见版式改动）——先改 `drafts/storyline.html`（卷右栏段）与 `drafts/ai-novel-c端-整书拆纲.html`（默认页④、cand 卡「上接」），并在 `ADJUSTMENTS.md` 登记「验证面板随页签重排／卡片带上接／默认页建书入口」三处偏差；设定与预览的回默认**只改落点、不改版式**，按一条行为口径登记、不动原型。`prototypes/book.html` 与 parity 基线不动。
- **设计工件由谁产出**：实现侧自查（沿用既有词汇与版式：`.e-empty/.be-k/.be-t/.be-acts`、`.cand-line/.cand-k`、`.pa-*`、`.pv-entry/.rail-assist`；无新形态，不需要设计侧出稿）。文案按 §13：按钮词为动词（「＋ 新增一卷」「＋ 新增一章」「续写」「重新规划这一卷」），不出现内部术语。
