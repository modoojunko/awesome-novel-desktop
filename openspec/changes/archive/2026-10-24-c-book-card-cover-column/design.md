## Context

拍板 C 的版式已由 drafts 原型（`ai-novel-c端-封面与角色头像-原型.html` 屏①）钉死：`.book-card` 两列 grid（`104px + 1fr`、gap 16、padding 16、align-items:start），左列 `.gl-book-cover` 3:4 竖版（圆角 8、克制投影、hover 浮现「换封面」），无封面为字标占位块（有章节＝按钮 CTA「生成封面」，0 章＝不可点「可稍后添加」），右列 `.gl-book-main` 顶行只放胶囊＋菜单按钮，底部有来源说明行；≤820px 封面列收 88px。当前实现是旧单列卡＋44×44 封面方块（`list.css:58`＋`image-assets.css:2-6`），DTO 已就地携带 `cover.source`/`cover.style_key`（`imageApi.ts:46`），后端零改动。

## Goals / Non-Goals

**Goals:**
- 书卡（全部状态）切到拍板 C 两列版式，像素基准＝drafts 原型；`list.html` parity 基线同步到同形态。
- 封面三入口收口：占位块（无封面有章节）、悬浮「换封面」（有封面）、⋯ 菜单「封面…」（全量第二入口）。
- 键盘可达：悬浮按钮走 focus-within，占位按钮天然可 Tab。

**Non-Goals:**
- 工坊内部（上传/候选/采用/撤销/PRO 门）与后端接口、DTO、备份格式不动。
- 书架三列栅格断点（`list.css` .cards 900/600）不动；只改卡内布局。
- drafts 原型文件不动（它是事实源）。

## Decisions

1. **像素基准取 drafts 原型，`list.html` 反向同步**。两个原型此前打架（drafts＝拍板 C 两列，list.html＝嫁接形态），实现曾跟错边；本 change 以拍板记录为准，list.html 作为 parity 基线更新到两列形态并在 ADJUSTMENTS.md 登记。备选「以 list.html 为准维持 44px」违背拍板 C，否决。
2. **类名跟原型语义、去 demo 前缀**：`.book-cover`（封面列）、`.cover-empty`（占位，`is-later` 修饰 0 章）、`.cover-act`（悬浮换封面）、`.cover-meta`（来源行）；布局住在 `image-assets.css`（封面域）＋ `list.css` 仅改 `.book-card` 容器两列与右列节奏（h3 21→19px、summary/stats/foot 间距按原型收紧）。44px 的 `.cover-wrap/.cover-edit/.book-cover-img` 全链退役。新词过 design:lint；不新增胶囊/状态形态。
3. **0 章书占位不可点**：照拍板「弱化为可稍后添加」，上传入口由 ⋯ 菜单「封面…」承接（原型菜单对全量书含该项）。备选「0 章也可点占位」与拍板文案冲突，否决。
4. **来源行字段映射**：`cover.source === "upload"` →「本地上传」；其余 →「AI 封面 · {画风名}」，画风名由 `style_key` 查画风词表，未知/缺失降级为「AI 封面」；无封面 →「封面位留给作者」。画风词表（水墨/电影写实/国漫/木刻版画/极简）现为 `ImageWorkshopModal.tsx:14` 私有常量——**导出为共享词表**（随工坊模块导出 `IMAGE_STYLES`），书卡与工坊单一来源，防两处漂移。
5. **e2e/测试入口选择器换名**：`添加封面` aria 退役，改按「生成封面」（占位）、「换封面」（悬浮）、「封面…」（菜单）定位；占位/悬浮/菜单点击一律 `stopPropagation` 防误触开书（沿用现 `.cover-edit` 的 stopPropagation 模式）。
6. **右列可能高于封面列**（长简介＋待完本双按钮页脚）：`align-items:start`，右列内部 `stats`/`foot` 保持现有 `margin-top`/`margin-top:auto` 节奏；卡片高度由右列决定，封面列不拉伸图片（3:4 固定）。

## Risks / Trade-offs

- 卡内密度略降（padding 22→16、字号收紧）是拍板 C 已接受的代价（设计说明 §4.3 决策表：一屏仍可 3–6 本）。
- parity 书架场景基线重录后，其余场景应零漂移；若 design:check 出非书架红，按存量对拍处理（先 A/B 定罪再动）。
- `novelListPage.test.tsx` 现断言围绕 44px 形态（cover-edit/mono），需同批改钉，防旧形态回归钉子残留。
