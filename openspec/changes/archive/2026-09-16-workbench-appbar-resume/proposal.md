## Why

书内顶栏此前是三行堆叠（全局 appbar「爱小说｜← 我的小说｜账户」＋ novelbar「书名·题材·免费提示/升级」＋ modnav），顶栏吃掉一整条正文垂直空间；而写作导航最需要的信息——「当前主线写到哪、我上次写到哪」——界面上没有位置安放，作者每次回到书里都要自己翻找上次停笔处。storyline.html 写作工作台原型给出了目标形态（书内单行头＋当前主线定位＋续写），本次按原型收口，顺带把「续写」的语义按用户拍板定为「回到上次退出前的进度」。

## What Changes

- **行头归一（用户可见的顶栏结构变化）**：书内页双行头并成**单行 48px**——logo（即返回入口，「← 我的小说」链接退役）｜书名（双击改名）｜题材胶囊｜**当前主线定位 bar-here**｜账户胶囊（档位徽）。免费态标识由顶栏 free-hint 与「升级 PRO」钮收敛到账户档位徽；升级入口保留在右栏 locked 卡与本书偏好弹窗（可达路径不减少）。modnav 不动，工作台可用高度多出一整条。
- **bar-here 主线定位**：显示主线章（`第 N 章` ＋题；默认序号名不重复拼接）、「草稿」徽（目标章有正文未归档）、卷面进度（`第X卷 · 已归档/总章` ＋进度条）；响应式三档随原型（≤1320 藏题材、≤1180 藏进度、≤920 折行）。
- **续写＝回到上次退出前的进度**：按书在本机（设备级 localStorage）记录上次写作会话（章 ref ＋编辑器滚动比例，输入/滚动节流写入）；点「续写」跳回该章、落正文页签、内容就绪后恢复滚动；**恢复只应用一次**（之后作者自己的输入/滚动不被拽回）。主线端点优先取该会话，无记录回落最新归档章，再回落首章。
- 原型与登记同步：`prototypes/book.html` 顶栏段重写＋bar-here 渲染/草稿徽/续写演示；`ADJUSTMENTS.md` #23（行头归一）与 #26（续写会话）登记。

## Capabilities

### New Capabilities

（无——本次不引入新 capability，全部行为落在既有 workbench 契约内。）

### Modified Capabilities

- `workbench`:　「NovelBar with advanced-config entry (N3)」更名并重写为「书内顶栏（行头归一：单行 appbar）」；新增「续写＝上次写作会话恢复」。

## Design Impact

- **受影响端**：C端（书工作台屏）。
- **受影响屏/弹层**：书工作台顶栏（写作/设定/预览三视图共用）；「本书偏好」弹窗入口随账户胶囊迁入（弹窗本身不变）。
- **对象状态**：新增「草稿」标签＝章节有正文未归档（中性 fg 标签，沿用既有 `.arch-tag`/`.defer-tag` 家族形态，**不新增语气档**）；「当前主线」＝最新归档章（无归档落首章），续写会话为其设备本机覆盖层。
- **共享段**：未触碰（新增类全部为 `.wb .appbar` / `.bar-here` 屏级作用域，`base.css` 令牌与基础组件类零改动）→ 免 design-cross。
- **原型先行**：已由实现侧完成（storyline.html 顶栏段 → `book.html`），ADJUSTMENTS #23/#26 登记。

## Impact

- 代码：`client/frontend` 的 `components/Navbar.tsx`（书内变体退役）、`components/novel/NovelWorkspace.tsx`（合并顶栏＋bar-here＋续写 CTA）、`components/novel/workbench/ProsePane.tsx`（会话记录/恢复）、`components/novel/workbench/ChapterWorkspace.tsx`（信号透传）、`lib/prefs.ts`（last_write 会话存取）、`design/book.css`（顶栏段样式）；原型 `docs/design-c/prototypes/book.html`＋`ADJUSTMENTS.md`。
- 数据/接口：零后端改动、零 API 变更（会话为设备本机偏好，不入库、不随导出包）。
- 兼容性：顶栏视觉与入口位变化属用户可见结构变化；无数据迁移。
