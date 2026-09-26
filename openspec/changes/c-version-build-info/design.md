## Context

现状数据链（单源自上而下）：

1. **CI 烘焙**：`client-package.yml` Generate release.json 步骤——tag 构建写 `client_version` = tag 去 `v` 前缀，PR/手动构建写 `dev`；
2. **运行时注入**：`pywebview_app.start_server` 的 `_env_with_release` 把 release.json 键注入 env（`CLIENT_VERSION` 等），缺省回落 `dev`；
3. **后端自报**：`update_check.get_client_version()` → `schema_version.app_version()`（env `CLIENT_VERSION` > `"dev"`），`/api/update-check` 载荷 `{current, latest}`；`app_version()` 同时是 c-db-per-version 库文件名派生单源（`db_filename_for`）；
4. **前端单源**：`lib/version.ts` 的 `formatVersion`（null→「版本未知」/ `"dev"`→「开发版 dev」/ 其余→`v{current}`）＋ `useClientVersion`（React Query 应用级缓存，staleTime Infinity），消费方 StatusBar / AcctMenu / BookPrefsModal / UpdateNotice 四处。

约束：`app_version()` 的返回值直接决定库文件名，绝不能被分支/commit 污染；docker e2e 镜像 `.dockerignore` 排除 `.git`，e2e 后端永远取不到 git；CI 的 `pull_request` 事件里 `GITHUB_REF_NAME` 形如 `123/merge`，不能原样当分支名展示。

## Goals / Non-Goals

**Goals:**

- dev 构建与本地开发的版本展示精确到「分支@commit前5位」，正式包维持 `v{X.Y.Z}` 不变；
- 构建信息独立成字段贯穿烘焙→注入→自报→展示，任何一环缺失都静默降级到现状文案；
- 三处版本行消费方一次改单源全部跟随。

**Non-Goals:**

- 不改库文件名派生、更新检测、版本比较、dismiss 记忆（`current` 语义零变化）；
- 不给 tag 构建追加 commit 展示；
- 不做「点版本号看构建详情」之类的交互（版本行保持纯文本不可交互）。

## Decisions

**D1：构建信息走独立字段 `build`，不并入 `current`。**
`/api/update-check` 载荷扩为 `{current, latest, build}`，`build = {branch, commit} | null`（仅 dev 态非空）。备选方案是把 dev 版本号本身改成 `dev+main.f456e`——被否：`current` 会流进 `is_valid_version`/更新比较/库文件名派生等所有消费 `app_version()` 的路径，污染面大且要逐处加过滤。独立字段零侵入。

**D2：commit 存储宽容、展示钉死前 5 位。**
本地开发 `git rev-parse --short=5 HEAD`——语义是「**至少** 5 位」，前缀碰撞的仓库 git 会自动加长到 6~40 位；CI 烘焙 `GITHUB_SHA` 前 5 位（PR 事件是 merge commit sha，但能唯一标识本次构建产物，报障定位够用）。校验与存储统一宽容到 `[0-9a-f]{5,40}`（合法 sha 缩写全集），**展示端 `formatVersion` 统一截前 5 位**——三处口径由「截断在展示层钉死」收敛，不再要求各来源恰好 5 位。备选「全链严格 5 位」被否：会把合法 git 输出静默打成 `build=null`。

**D3：分支名清洗规则（按来源分治）。**
CI：`pull_request` 事件映射 `refs/pull/N/merge` → `pr-N`；其余事件直接用 `GITHUB_REF_NAME`。**env/烘焙路径**清洗为 `A-Za-z0-9._-`（非法字符替换 `-`，与既有 tag 清洗同一手法）——此为纵深防御，防烘焙侧脏串。**本地 git 路径不清洗**（该字符集不含 `/`，`feature/foo` 会被洗成 `feature-foo`）：仅截断 40 字符＋剥离控制字符，保留本地分支名可读性。前端不二次清洗（信任后端单源；React 文本插值自动转义，无 XSS 向量）。

**D4：构建信息读取——dev 总闸前置，独立叶子模块。**
读取逻辑独立成 `client/backend/build_info.py`（与 schema_version.py 并列的零依赖叶子）：`update_check.py` 已肩负外呼检测/节流/出站校验，再塞 git subprocess 会职责过载，独立叶子也让测试免 import fastapi/httpx。计算入口整体前置 **dev 总闸**：`app_version()!="dev"` 直接返回 null——env 路径也在闸内，tag 构建即使机器上有杂散 `CLIENT_BUILD_*` 也满足 spec「tag 构建构建信息为空」。闸内优先级：`CLIENT_BUILD_BRANCH`/`CLIENT_BUILD_COMMIT` **两键都非空才用 env**（单键缺失按 null 是有意为之——展示格式 `{branch}@{commit}` 需要成对，不引入"只显分支"的第二种 UI 口径）；否则惰性读一次 git（subprocess 显式钉 cwd、超时 2s、捕 `OSError`/`SubprocessError` 各留 debug 日志——Windows 未装 git 是立即 `FileNotFoundError` 不会挂起，无需区分"未装"与"超时"；detached HEAD 显示 `HEAD@{sha}` 可接受）。**模块级缓存必须做成可被 `monkeypatch.setattr` 整体替换的变量**——pytest 进程非 frozen 且仓库有 `.git`，先跑的用例会把真实 git 信息带进后面打桩的用例，出顺序依赖的假绿假红；`test_update_check.py` 的 autouse fixture 同批复位缓存＋删除两个新 env。冻结包（PyInstaller）不尝试读 git。`/api/update-check` 两条返回路径（has-update 字面量与 `_payload`）同批加 `build` 键，保持 shape 一致。

**D5：前端缓存对象扩展，`formatVersion` 签名扩展为可容忍裸串。**
React Query 缓存从 `string` 换为 `{current: string; build: BuildInfo | null}`（缺 `current` 仍 throw 不缓存，语义不变；queryClient 无持久化中间件，queryKey 无需 bump）。`formatVersion(info: ClientVersionInfo | string | null | undefined)`：裸串视为 `{current: s, build: null}`——UpdateNotice 只拿到 `state.current`，继续传裸串，行为不变（dev 态 `has_update=False` 提示条根本不渲染，裸串路径在 dev 下不可达）。`formatVersion` 内部做两道防御：`build.commit` 统一截前 5 位（D2 口径的展示落点）；`branch`/`commit` 任一为空视为 build 不可用走兜底（防渲染出 `@f456e` / `main@`）。三个 UI 消费方（StatusBar/AcctMenu/BookPrefsModal）本就是 `formatVersion(version)` 透传，**代码零改动**，类型随 hook 返回值自然收窄。渲染优先级：`current` 缺失→「版本未知」；`current=="dev"` 且 `build` 可用→`{branch}@{commit前5位}`；`current=="dev"` 无 build→「开发版 dev」；其余→`v{current}`。

**D6：release.json 新键带 `client_` 前缀，生成逻辑抽脚本，断言缺省容忍。**
键名定 `client_build_branch`/`client_build_commit`——与既有 `client_version`/`client_update_url` 风格一致、与 env `CLIENT_BUILD_*` 直接对应（烘进产物后再改键名就贵了，现在零成本）。生成逻辑（含 PR 事件分支映射）从 workflow heredoc 抽成 committed 脚本 `scripts/release_json_generate.py`（仓库既有惯例：`release_components.py`/`release_json_assert.py` 皆脚本化），workflow 调用之——三事件 dry-run 验证才有可执行载体。`release_json_assert.py` 存在新键时校验安全字符集与 commit 形态（宽容 `[0-9a-f]{5,40}`）；键不存在不断言（tag 构建、旧产物兼容）。

## Risks / Trade-offs

- **[PR 构建的 sha 是 merge commit，与源分支 HEAD 不同]** → 展示目的是标识"这次构建产物"，merge commit 唯一对应一次 CI 构建，定位去 Actions 查即达；不改用 head sha（需要额外 API 步骤，收益低）。
- **[本地开发分支名可能是功能分支长名]** → 截断 40 字符；状态条 muted 小字右对齐，左版权行有压缩空间，极端长名不破坏布局（`.sb-ver` 无固定宽）。
- **[git 读取拖慢启动]** → 仅 dev 态、惰性首查、2s 超时、进程级缓存一次；打包态直接跳过。
- **[e2e 断言路径]**：`statusbar.spec.ts` 通篇走浏览器网络层 stub（`page.route` 拦 `/api/update-check`），后端 env 注入对它无效——UI 形态断言走 **stub 扩展**（`stubUpdateNotice` 加可选 `build` 参数）；env→后端→载荷真链的覆盖归 pytest（2.1/2.2），docker e2e 栈**不注 env**（env 全局注入会把同栈的「开发版 dev」断言打红，单栈前提下两者互斥）。docker 镜像无 `.git` 且连 git 二进制都没有 → `build=null` → 兜底「开发版 dev」，`statusbar.spec.ts` 既有断言不改仍绿。但**本地 dev e2e**（`E2E_BASE_URL=localhost:5173` 直连 git 检出后端）会拿到非空 build，打红 `modals-pr5.spec.ts` 的版本行正则——该正则本 change 内同批扩展为也接受 `{分支}@{commit前5位}` 形态。
- **[文案混排]**：`main@f456e` 与 `v0.25` 同槽位展示，均为纯 ASCII muted 小字，无字体/溢出风险；parity 基线若截图含状态条文本区域，按 ADJUSTMENTS 登记处理（像素 diff 仅文案宽度差，预期 <0.2% 阈值内需实跑确认）。

## Migration Plan

纯增量字段＋文案分支，无数据迁移、无 schema 变更、无破坏性契约变化。后端对旧前端（无 `build` 字段消费方）完全兼容（多余字段被忽略）；新前端对旧后端（无 `build` 键）走兜底「开发版 dev」。发布顺序无要求，随下个安装包版本自然带出。回滚＝还原本次提交即可；已烘进旧包的 `client_build_*` 键在回滚代码下是惰性残留（`load_release_overrides` 只回白名单键、注入段只读已知键），无残留状态。

## Open Questions

（无——格式 `{分支}@{commit前5位}`、commit 位数 5、降级链均按用户给定口径与既有单源约束定死。）
