## 1. 原型先行（C端 硬性流程）

- [x] 1.1 更新 `docs/design-c/prototypes/` 中带状态条的屏（list/book 等）右下角版本文案示例值：「开发版 dev」示例旁补 `{分支}@{commit前5位}` 形态示例（如 `main@f456e`），验证：原型 HTML 打开目测状态条两形态并存合理、muted 小字无溢出
- [x] 1.2 在 `prototypes/ADJUSTMENTS.md` 登记：dev 态版本行文案更新为构建信息形态、「开发版 dev」降级为兜底——属文案内容更新非视觉偏差，无样式/类名变化；验证：登记条目与实改文件对得上

## 2. 后端构建信息自报

- [x] 2.1 新增零依赖叶子 `client/backend/build_info.py`：dev 总闸前置（`app_version()!="dev"` 直接 None——env 路径也在闸内）；闸内 env `CLIENT_BUILD_BRANCH`/`CLIENT_BUILD_COMMIT` 两键都非空才用 env（单键缺失按 null 是有意）；否则惰性读 git（`--short=5`＋`--abbrev-ref`，subprocess 钉 cwd、2s 超时、捕 OSError/SubprocessError 留 debug 日志，frozen 包跳过）；模块级缓存做成可被 `monkeypatch.setattr` 整体替换的变量；`schema_version.py` 不动；验证：pytest 新增用例矩阵全绿——env 注入态 / env 半配置态 / git 打桩态 / 双缺失态 / frozen 跳过态 / tag 态（CLIENT_VERSION=0.24＋杂散 build env → build=null，钉死 dev 总闸）
- [x] 2.2 `/api/update-check` 两条返回路径（has-update 字面量与 `_payload`）同批加 `build: {branch, commit} | null`，shape 一致（`current`/`latest`/检测跳过逻辑零变化）；`test_update_check.py` 的 autouse fixture 同批删两个新 env＋复位 build_info 缓存变量（防跨用例缓存污染出顺序依赖假绿假红）；验证：pytest 契约断言新增键、`current` 仍为 `dev` 或真实版本串、库文件名派生 `db_filename_for(app_version())` 回归用例不变绿、随机序重跑无顺序依赖
- [x] 2.3 校验按来源分治：env/烘焙路径清洗 `A-Za-z0-9._-`（非法替换 `-`，纵深防御防烘焙脏串）；git 路径**不清洗**（字符集不含 `/`，`feature/foo` 会洗坏）仅截断 40＋剥控制字符；commit 校验统一宽容 `[0-9a-f]{5,40}`（`--short=5` 是「至少 5 位」语义，碰撞仓库会输出更长合法值）；验证：pytest 用例（脏 env 分支名 / 含 `/` 的 git 分支保持原样 / 6~40 位 commit 合法 / None）全绿

## 3. 打包链烘焙

- [x] 3.1 新增 `client/backend/scripts/release_json_generate.py`：release.json 生成从 workflow heredoc 抽成可执行脚本（既有惯例 release_components.py/release_json_assert.py 皆脚本化），非 tag 构建写入 `client_build_branch`（`pull_request` 事件映射 `pr-N`，其余用 `GITHUB_REF_NAME`，清洗后写入）/`client_build_commit`（`GITHUB_SHA` 前 5），tag 构建不写；`client-package.yml` Generate 步骤改调脚本；验证：脚本 dry-run 直跑核三事件形态（pull_request→pr-N / push tags→不写 / workflow_dispatch→分支名）＋workflow yaml safe_load 过
- [x] 3.2 `client/backend/config.py` 的 `RELEASE_OVERRIDE_KEYS` 白名单追加 `client_build_branch`/`client_build_commit`（`load_release_overrides` 只返回白名单内键——漏登记则整条打包链静默失效）；`client/packaging/build/pywebview_app.py` 沿 `_env_with_release` 模式补 `CLIENT_BUILD_BRANCH`/`CLIENT_BUILD_COMMIT` 注入（缺省空串）；验证：假 release.json 实跑注入段确认 env 出现（**必选**，不留 code review 逃生门）＋「假 release.json → load_release_overrides 返回新键」白名单单测绿
- [x] 3.3 `client/backend/scripts/release_json_assert.py`：新键存在时校验安全字符集与 commit 形态（宽容 `[0-9a-f]{5,40}`），缺键容忍；验证：脚本正/负例手跑（带新键合法/带新键非法/不带新键三例）

## 4. 前端单源与消费方

- [x] 4.1 `client/frontend/src/lib/version.ts`：缓存对象扩为 `{current, build}`（缺 `current` 仍 throw；queryClient 无持久化中间件，queryKey 不用 bump）；`formatVersion` 扩展接收 `ClientVersionInfo | string | null | undefined`（裸串视为 build=null），内部两道防御——`build.commit` 统一截前 5 位、`branch`/`commit` 任一为空视为 build 不可用走兜底（防渲染 `@f456e`/`main@`）；渲染优先级＝版本未知 > dev＋build（`{branch}@{commit前5位}`）> dev 无 build（「开发版 dev」）> `v{current}`；验证：`vitest src/__tests__/version.test.tsx` 全场景绿（含裸串兼容/超长 commit 截断/半残 build 兜底）
- [x] 4.2 确认 StatusBar / AcctMenu / BookPrefsModal 三处为 `formatVersion(version)` 透传**零改动**（仅 hook 返回类型自然收窄）；UpdateNotice 维持裸串传参不动（dev 态 `has_update=False` 提示条不渲染，裸串路径不可达）；`AcctMenu.test.tsx` 模块 mock 从裸串改对象形态 `{current:"0.19", build:null}`（不改则对象路径在测试里永远走不到，验证信号失真）；验证：`npx tsc --noEmit` 零错＋`vitest src/__tests__/AcctMenu.test.tsx` 绿
- [x] 4.3 确认无版本文案散点：`grep -rn "开发版\|版本未知" client/frontend/src` 仅 version.ts 命中；另点名确认 `LandingPage.tsx` 的 `useBakedVersion`（第五个 `/update-check` 读取方，自带请求渲染 `v{ver}`）不消费 build、无需改动——豁免判断记录在案；验证：grep 输出＋豁免结论贴任务下

## 5. e2e 与回归

- [x] 5.1 e2e 新断言走 **stub 路径**（`statusbar.spec.ts` 通篇 `page.route` 拦 `/api/update-check`，后端 env 到不了前端）：扩展 `stubUpdateNotice` 支持可选 `build`，加「dev＋build 呈 `main@f456e`、不出现开发版 dev」用例；docker e2e 栈**不注 env**（env 真链覆盖归 2.1/2.2 的 pytest）；`modals-pr5.spec.ts` 版本行正则同批扩展为也接受 `{分支}@{commit前5位}` 形态——本地 dev e2e（`E2E_BASE_URL=localhost:5173` 直连 git 检出后端）会拿到非空 build，不改必红；既有 docker 无 git 的「开发版 dev」断言不动仍绿；验证：`npx playwright test e2e/statusbar.spec.ts e2e/modals-pr5.spec.ts` 全绿（docker 与本地两路径各跑一次）
- [x] 5.2 全量门禁：`npm run design:lint`（C端）→ `npm run design:check`（预期状态条文案像素差在 <0.2% 阈值内；若基线含该区域文字光栅差按 ADJUSTMENTS 登记处理）→ `tsc --noEmit` → pytest/vitest 全量；验证：各命令输出结论贴任务下
- [x] 5.3 不触两端共享段判定复核：无新类/无令牌变化，`scripts/design-cross.mjs` 免跑（依据 proposal Design Impact 判定）；验证：判定理由引用落任务下——已复核：零新增 CSS 类/令牌/语义类，diff 仅 HTML 注释与文案逻辑，免跑判定成立
  - 证据（5.1）：statusbar.spec 11 passed（含新增「dev＋build 呈 main@f456e」用例，纯 stub）；modals-pr5.spec 4 passed（隔离 docker 栈＋真后端＋真 S端 注册流）；另做**容器真链实证**：client-backend 注入 CLIENT_BUILD_BRANCH=main/CLIENT_BUILD_COMMIT=f456e 后 /api/update-check 返回 `"build":{"branch":"main","commit":"f456e"}`——env→后端→载荷全链走通
  - 附带（5.1）：modals-pr5 CONFIG_PATH 改为 E2E_CLIENT_CONFIG_PATH 可覆盖（缺省不变）——per-session 隔离栈数据目录不在共享路径所必需，沿用 E2E_BASE_URL 同款 env 模式
  - 证据（5.2）：tsc --noEmit 零错；design:lint 0 违规（存量分布行不变）；vitest 全量 874 passed（86 文件）；pytest 全量 1526 passed（本 change 相关 5 套件 53 条全绿；首跑 13 条挂为临时 venv 缺 pytest-asyncio，补装后清零且经干净 main 对照确认非本 change 引入）；design:check＝7 绿＋list.empty 1 红（像素差 0.292%）
  - design:check 红项判定：干净 origin/main 同场景同为 0.292%（stash 后复跑逐位同值）＝存量光栅/文案漂移，非本 change 回归（与既往「main 本机 parity 漂移」记录一致）

## 6. CI 实证（打包链真跑）

- [ ] 6.1 手动 dispatch 一次非 tag 打包构建，下载产物解包验 release.json 含 `client_build_branch`/`client_build_commit` 且安装包状态条（或冒烟日志）呈现 `{分支}@{commit前5位}`；验证：Actions run 链接＋产物特征串核验（「容器里的东西确实是自己的构建」纪律）
  - 本地等效验证已完成（09-27，macOS）：`release_json_generate.py` 以真实分支/commit 烘 release.json（`feat-c-version-build-info`/`0bf87`＝PR 提交指纹）→ PyInstaller 冻结 `.app` → `release_json_assert.py` 产物断言过 → `--smoke` 冻结态 `/api/update-check` 返回 `"build":{"branch":"feat-c-version-build-info","commit":"0bf87"}`——烘焙→打包→冻结自报全链实证（DATA_ROOT 重定向临时目录，真实 appdata 零触碰）
- [ ] 6.2 tag 干跑核验（可用既有 v0.24 产物回归读）：tag 产物无新键、状态条仍 `v{X.Y.Z}`；验证：对拍记录贴任务下
  - 本地等效验证已完成（09-27）：冻结态以 `CLIENT_VERSION=0.25`＋杂散 `CLIENT_BUILD_*` env 启动 → 载荷 `current=0.25`、`build:null`（dev 总闸冻结态成立）；tag 形态不烘新键由 generate 脚本 dry-run（push tags 形态）覆盖；顺带实证冻结包真实外呼更新检测（latest=0.23 ≤ 0.25 不提示）
  - 仍属 CI-only 的残余：Windows exe（Inno）路径与 workflow 在真 runner 上的 env 接线——下次真实 dispatch/打版时顺带核验即可，无需单独烧额度