## Context

实测证据（2026-09-19 深夜，同数据双侧截图＋DOM 逐项测量）：5174 容器代码不旧（含 #440 全部四态文案）、parity 四场景全绿也真实——差异根因是晋级基线 `prototypes/list.html` 与实现**双侧同错**（都是 48/36/1em），works.html 草稿的 40/26/0 没被抄进来。各屏间距现状（原型侧）：list/backup-restore 48/36、model-config 44/28（model-config.css 以 `.pg-config` 屏级类实现，注释明写「屏级节奏与 list.html 有意不同」）、works 草稿 40/26。`base.css:88-91` 是全站共享壳（书架/模型配置等同用），`.sub` 的 `margin-bottom:1em` 系 #181 复刻旧原型时把未重置的 UA `p` margin 显式写死——旧原型无 `p{margin:0}` 重置，「意外」同值故 parity 从未报警。

## Goals / Non-Goals

**Goals:**

- 书架屏与 `drafts/works.html` 逐像素一致（桌面三值＋窄屏断点），parity 回 <0.2%。
- 改动最小化：其余屏与其原型的既有节奏零影响。

**Non-Goals:**

- 不全局改 `base.css` 壳值、不动 `.sub` 全局 1em（其余屏与其原型现状「意外一致」，动了反而制造新差异）。
- 不处理 ⋯ 卡片菜单（换代节 #4 登记的有意偏差）、更新条按钮组（notes_url 驱动）、状态栏版本号——非缺陷。
- 不动 `docs/ux/design-language.html`（§「padding 48/32/80」是通用基线描述；屏级差异以原型＋ADJUSTMENTS 登记为准，model-config 先例）。
- 移动端 `.update-strip` 窄屏 padding（works.html 16px 16px 0）：属全局壳层非书架屏内元素，无法屏级作用域，不入本批（登记为已知微差）。

## Decisions

1. **屏级作用域 `.pg-works`，而非全局对齐**。理由：a) 各屏节奏本就不同是设计线既定事实（model-config 44/28），全局改 40/26 会把模型配置屏改得偏离它自己的原型、破坏其 parity；b) `.pg-config` 先例证明屏级类模式成熟（挂法 `<main className="main pg-config">`、list.css 在 base.css 之后装载、同特异性靠级联顺序取胜）。备选「全局改＋所有原型同批改」被否：牵连 backup-restore/book 等全部壳层屏，且与「以原型为准」矛盾（各屏原型值本就不同）。
2. **`prototypes/list.html` 采用 works.html 值的方式**：`.main` padding 48→40、`.page-head` mb 36→26、`.page-head .sub` 显式补 `margin-bottom: 0`（不给 list.html 加 `p{margin:0}` 全局重置——避免波及原型内其他 `p` 元素，如 `fin-t p` 等已带显式 margin 的规则）；窄屏媒体查询同步三值。
3. **实现侧 CSS 落笔形状**（list.css 追加，注释注明口径与先例）：
   ```css
   .pg-works { padding-top: 40px; }
   .pg-works .page-head { margin-bottom: 26px; }
   .pg-works .page-head .sub { margin-bottom: 0; }
   @media (max-width: 480px) {
     .pg-works { padding: 28px 16px 64px; }
     .pg-works .page-head { gap: 14px; margin-bottom: 22px; }
   }
   ```
   `NovelListPage.tsx` 根元素 `<main className="main">`→`<main className="main pg-works">`，其余 JSX 零改动。
4. **验证路径**：容器跑的是构建产物，改完须按 works-finish-flow 收官配方「烘镜像进主栈」重建 `ai-novel-client-frontend` 后再跑 `design:check`（books/empty/quota/finish 四场景，双侧同值应回 0 差异量级）；vitest 不涉 CSS 逻辑，跑 NovelListPage 相关用例确认无 DOM 断言破坏（新增类名不进断言路径）。

## Risks / Trade-offs

- **级联顺序依赖**：`.pg-works` 与 base.css `.main` 同特异性，靠 main.tsx 装载顺序（base→list）取胜——与 `.pg-config` 同款既定模式，风险可忽略；若未来调整装载顺序会静默失效，list.css 注释中标注。
- **e2e 位置敏感断言**：若有用例断言书架元素坐标/高度（排查未见，workbench/works-finish-flow spec 均为行为断言），31px 位移会使其失败——tasks 中跑相关 e2e 兜底。
- **ADJUSTMENTS 登记迟于原型改动**：按 design-system 流程要求原型与登记同任务落笔（tasks #1），不留裸改窗口。
