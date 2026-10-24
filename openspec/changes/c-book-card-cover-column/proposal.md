## Why

「封面与角色头像」设计说明 §4.3 已拍板 C：书卡从「首字方块＋文字」改为「左侧 104×139 竖版封面（3:4）＋右侧信息」。但阶段 2（c-cover-avatar-ui）实现时只把封面入口（44×44 方块＋「换」角标）嫁接进了旧单列书卡，没有落书卡改版本体——当前书架上「有封面的书卡」与拍板原型（`docs/design-c/drafts/ai-novel-c端-封面与角色头像-原型.html` 屏① 书架）版式不一致：封面挤在顶行、无竖版占位、⋯ 菜单缺「封面…」入口、缺来源说明行。

## What Changes

- 书卡改两列网格：左列 104px 竖版封面（3:4，圆角 8px、克制投影，贯穿卡片主体高度），右列为信息列（题材/状态行、标题、简介、统计、分状态页脚）。
- 无封面占位升级：左列显示字标竖版占位块；**占位块本身是按钮**，有章节的书点它直接进封面工坊（CTA「生成封面」），0 章书弱化为不可点占位（「可稍后添加」，入口改走 ⋯ 菜单）。
- 有封面的书：悬浮/键盘聚焦封面时浮现「换封面」覆盖按钮；44×44 小方块与常驻「换/＋」圆形角标退役。
- 书卡 ⋯ 菜单第一项新增「封面…」（第二入口，全部书可见）。
- 卡片底部新增封面来源说明行：「AI 封面 · {画风}」/「本地上传」/无封面「封面位留给作者」。
- 响应式：窄屏（≤820px）封面列从 104px 缩到 88px。
- 原型先行：`docs/design-c/prototypes/list.html` 书卡同步为两列形态，`ADJUSTMENTS.md` 登记偏差。
- 不改工坊内部行为、后端接口与数据契约（cover DTO 的 `source`/`style_key` 已就地下发，够用）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `cover-avatar`: 新增「书卡封面版式」要求（两列网格/占位按钮/悬浮换封面/菜单第二入口/来源行/响应式）；「上传型封面/头像工坊」的上传入口场景措辞随入口形态更新（占位块/悬浮按钮/菜单三项入口）。

## Impact

- 前端：`client/frontend/src/pages/NovelListPage.tsx`（书卡结构重排）、`client/frontend/src/design/list.css`（书卡两列布局）、`client/frontend/src/design/image-assets.css`（封面列/占位/悬浮按钮/来源行，44px 旧样式退役）。
- 原型基线：`docs/design-c/prototypes/list.html` ＋ `ADJUSTMENTS.md`；设计事实源 drafts 原型已就位不改动。
- 测试：`novelListPage.test.tsx`、`e2e/image-workshop.spec.ts`（入口选择器）、design:lint / design parity 复跑。
- 后端：零改动。

## Design Impact

- 受影响端：仅 C端。
- 受影响屏：书架「我的作品」书卡（含全部状态书卡：设定中/写作中/待完本/已完结；零书空态不涉及）。
- 对象状态：沿用现有状态语言（状态胶囊 `.b` 设定中/写作中/待完本/已完结），无新增状态形态；新增的占位块/悬浮按钮/来源行为书卡屏级新词，只用真实 token，不重定义令牌、不新增胶囊形态。
- 两端共享段：不触碰（改动全部住在 list.css 屏级作用域与 image-assets.css，base.css 令牌与基础组件类零改动）。
- 原型先行：需要——`docs/design-c/prototypes/list.html` 先改，`ADJUSTMENTS.md` 登记后实现跟随；像素基准以拍板 C 的 drafts 原型为准。
- 设计工件：实现侧自查产出（版式、尺寸、文案均已由拍板原型与设计说明 §4.3 钉死，无需设计侧会话）。
- 文案口径：按钮词均为动词（「换封面」「生成封面」「封面…」）；「可稍后添加」「封面位留给作者」为非按钮占位文案，不出现内部术语。
