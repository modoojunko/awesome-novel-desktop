## Why

C端 右下角状态条的版本展示目前区分不出"是哪一个构建"：正式安装包显示 `v0.24` 没问题，但 dev 构建与本地开发一律显示「开发版 dev」——并行会话各起各的栈、报障截图、验证"容器里跑的是不是我这版"时，都无法从界面上确认具体来源（哪个分支、哪个 commit）。tag 发布版继续显示版本号，非 tag 构建改为显示"分支＋commit 前 5 位"，让每个窗口都能自证身份。

## What Changes

- **版本文案口径扩展（单源 `formatVersion`）**：
  - tag 构建（有真实版本号）：`v{X.Y.Z}`——现状不变（如 `v0.25`）；
  - dev 构建＋构建信息可用：显示 `{分支}@{commit 前 5 位}`（如 `main@f456e`）；「开发版 dev」退役为降级兜底文案（仅当构建信息取不到时保留）；
  - 版本获取失败：「版本未知」——现状不变。
- **后端 `/api/update-check` 载荷新增 `build` 字段**：`{branch, commit} | null`；`current` 字段口径完全不动（c-db-per-version 的库文件名派生不得被污染）。
- **构建信息数据链路（两来源，均失败则 `build=null`）**：
  - 打包态：CI 非 tag 构建把分支名与 commit 短串烘进 release.json 新键（`build_branch` / `build_commit`），`pywebview_app` 沿既有 `_env_with_release` 模式注入 env；tag 构建不烘（展示用不到）；
  - 本地开发态：后端直接读 git（惰性缓存一次），git 不可用（如 docker e2e 镜像无 `.git`）则 `build=null`。
- **消费方**：窗口底部状态条、控制中心面板、本书偏好弹窗三处版本行同批跟随（单源自动覆盖）；UpdateNotice 提示条仅在正式版出现更新时渲染「当前 v{X}」，行为不变。
- 非目标：不在 tag 构建上追加 commit 展示；不改库文件名派生、更新检测与版本比较逻辑。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `client-update`：
  - 「版本自报」requirement 扩展：dev 态额外自报构建信息（分支＋commit 短串，取不到时为空），`current` 与库文件名派生口径不变；
  - 「版本号常驻展示（窗口底部状态条）」requirement：dev 构建文案从固定「开发版 dev」改为 `{分支}@{commit前5位}`（构建信息可用时），「开发版 dev」降级为构建信息缺失时的兜底文案；
  - 「控制中心面板版本行」requirement：文案口径描述跟随新口径。

## Impact

- **后端**：新增零依赖叶子模块 `client/backend/build_info.py`（构建信息读取：dev 总闸前置 → env 优先 → dev 态读 git，不塞 update_check 以免职责过载）；`client/backend/update_check.py`（`/api/update-check` 两条返回路径同批加 `build` 键）；`client/backend/config.py`（`RELEASE_OVERRIDE_KEYS` 白名单追加新键——`load_release_overrides` 只返回白名单内键，漏登记则打包链整条静默失效，评审 P0 实锤）；`client/backend/schema_version.py` 不动（`app_version()` 口径保持纯净）。
- **打包链**：新增脚本 `client/backend/scripts/release_json_generate.py`（release.json 生成含 PR 事件分支映射，从 workflow heredoc 抽脚本化——仓库既有惯例，dry-run 才有载体）；`.github/workflows/client-package.yml`（Generate 步骤改调脚本；非 tag 构建烘 `client_build_branch`/`client_build_commit`，键名带 `client_` 前缀与既有键风格一致）；`client/packaging/build/pywebview_app.py`（两键 env 注入）；`client/backend/scripts/release_json_assert.py`（新键形态断言，缺省容忍）。
- **前端**：`client/frontend/src/lib/version.ts`（缓存对象扩展＋`formatVersion` 扩展：commit 统一截前 5 位、branch/commit 任一空视为不可用走兜底）；`StatusBar.tsx` / `AcctMenu.tsx` / `BookPrefsModal.tsx` 三处为透传**零改动**；`UpdateNotice.tsx` 裸串传参不动；豁免：`LandingPage.tsx` 的 `useBakedVersion` 直读 `/update-check` 自渲染 `v{ver}`，不消费 build、不受影响（评审确认的第五个读取方）。
- **测试**：`version.test.tsx`（对象场景＋截断/半残 build 用例）、`AcctMenu.test.tsx`（mock 改对象形态）、`test_update_check.py`（新矩阵：env 半配置/frozen 跳过/tag 态 null/git 打桩＋缓存复位＋fixture 删新 env）、config.py 白名单单测、e2e `statusbar.spec.ts`（stub 加 build 形态断言）/ `modals-pr5.spec.ts`（版本行正则同批扩展，覆盖本地 dev e2e 路径）。
- **纯文案与数据链路改动**：不改样式、不加组件形态，不触碰两端共享段（base.css 令牌/语义类零变化）。

## Design Impact

- **受影响端**：仅 C端（S端 无版本状态条，不涉及）。
- **受影响屏/弹层**：窗口底部状态条（书架/登录/工作台三态常驻）、控制中心面板底部版本行、工作台本书偏好弹窗底部版本行。均为既有元素的**文案内容**变化，无布局/层级变化。
- **对象状态**：无新增对象状态（状态语言总表零变化）——版本行仍是 muted 小字静态文本，不可交互，语气词表不涉及。
- **两端共享段**：不触碰（无新类、无令牌变化、无语义类增删）。
- **原型先行**：需要——C端 用户可见改动按硬性流程先改原型。涉及 `prototypes/` 中带状态条的屏（list/book 等）右下角版本文案示例值更新＋`ADJUSTMENTS.md` 登记（登记项：dev 态示例文案由「开发版 dev」改为 `{分支}@{commit前5位}`，属文案内容更新非视觉偏差）。
- **设计工件产出方**：实现侧自查（纯文本内容替换，无视觉决策）。
