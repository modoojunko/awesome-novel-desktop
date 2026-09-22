# Proposal: c-empty-card-hierarchy

## Why

中栏默认页三张卡（起手卡／落点卡／书主页卡）**视觉层级倒挂**：实现把「眉标」放进了 `.be-k`（19px 展示体＋墨色），
真正的**主句**（「这本书怎么开始？」「开始写第一章？」「接着写第 N 章？」）被挤进 `.be-t`（13.5px muted），
说明句还挂着一个产品 CSS 里**从未定义**的 `.be-desc`。结果是三张卡都在「拿状态当标题、把提问写成灰小字」，
提问与说明同为灰色小字，读者读不出这一屏在问什么——最刺眼的一处是起手卡把「设定 0/7 已确认」做成了全屏最大的字。
原型（`.be-mark` 眉标／`.be-k` 主句／`.be-t` 说明）本身是对的，是实现的档位映射错位。

## What Changes

- **补齐 `.be-mark` 档**：`book.css` 的 `.e-empty` 段按原型补回眉标档（mono 10px／字距 .14em／`--accent`／margin 0 0 10px），
  并把该段注释写成四档角色（`.be-mark` 眉标 → `.be-k` 主句 → `.be-t` 说明 → `.be-acts` 动作）。
- **`.be-desc` 退役**：该类的元素一律改挂 `.be-t`（产品 CSS 从未定义 `.be-desc`，它与 `.be-t` 同效但少了 380 字宽与间距约束）。
- **三张卡同批改回档位**（起手卡 `book-empty`／落点卡 `landing-card`／书主页卡 `write-home`）：
  眉标 → `.be-mark`、提问 → `.be-k`、说明 → `.be-t`；书主页卡的 `home-progress` testid 保留在眉标上（测试断言不受影响）。
- 三张卡的面貌变化：眉标变小号强调字，**提问成为 19px 主句**。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `design-system`：登记中栏空态卡（`.e-empty` 家族）的四档组件词汇——新增 `.be-mark` 档、`.be-desc` 退役，
  并写明「哪些是眉标／主句／说明」（原样沿用既有共享令牌，不新增 token、不动两端共享段）。

## Impact

- **代码（C端 client/frontend）**：`src/design/book.css`（`.e-empty` 段补档＋注释）、
  `src/components/novel/NovelWorkspace.tsx`（三张卡的类名改挂）。
- **原型（设计事实源）**：无需改动——`drafts/ai-novel-c端-整书拆纲.html` 的三档本来就是对的口径，
  本次只同步了其中一行「实现侧类名角色」注释；`prototypes/ADJUSTMENTS.md` 新增一节登记问题、处置与影响面。
- **测试**：无断言依赖这些类名（vitest 754 passed 未改一行）；新增走查为**一次性**真实栈验证
  （三张卡档位顺序断言＋对照截图），未落成常驻用例（类名口径由 ADJUSTMENTS 与 design-system spec 承担）。
- **不触碰**：两端共享段（base.css 令牌与基础组件类一处未动）、后端（零改动）、S端（无涉及）。
  因未落任何阈值/词表档位，`design-vocab.mjs` 无需回填；未用 uikit 候选组件。

## Design Impact

- **受影响端**：仅 C端（`client/frontend` + `docs/design-c`）。
- **受影响的屏/弹层**：书工作台中栏**默认页三态**（起手卡／落点卡／书主页卡）——左树、顶栏、右栏、其它屏不变。
- **对象状态（对照 design-language §5 状态语言总表）**：**无新增状态**——四档是既有的版式层级（眉标／主句／说明／动作），
  不是新的交互态；按钮态（enabled/disabled）、加载态、空态语义均不变。
- **是否触碰两端共享段**：否（改的是 C端业务层 `book.css` 的 `.e-empty` 段与 workbench 组件类名挂载）。
- **是否需要原型先行**：原型无需改（原型即正确口径）；按仓规在 `ADJUSTMENTS.md` 登记本次偏差与处置。
- **设计工件由谁产出**：实现侧自查（对齐既有原型三档，不引入新形态）；无新组件词汇需要设计侧出稿。
