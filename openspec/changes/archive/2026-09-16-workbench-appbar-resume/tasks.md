## 1. 原型先行（C端）

- [x] 1.1 依 storyline.html 顶栏段重写 `docs/design-c/prototypes/book.html` 壳层与顶栏段样式：双行头并单行 48px（logo 即返回·书名·题材·bar-here·账户）、响应式三档、`updateBarHere()` 渲染主线端点＋卷进度；`ADJUSTMENTS.md` **#23** 登记（含「返回链接/free-hint/升级钮退役」清单与 retired 类名）；#367 实现合并
- [x] 1.2 原型补草稿徽与「续写」CTA（`.bh-tag/.bh-tag-live` 收编 storyline `.tag/.tag-live` 改名避让 `details.cfg .tag`；CTA 演示语义＝选中当前主线章落正文）；`ADJUSTMENTS.md` **#26** 登记口径边界（队列门禁语义不覆盖）；#370 实现合并
- [x] 1.3 证据：`npm run design:lint` 通过（book.html 在 strictGlobs 内，新增类均屏级作用域）

## 2. 实现（C端 client/frontend）

- [x] 2.1 `components/Navbar.tsx`：书内变体退役（`/novel/*` 返回 null，避免双头）；`components/novel/NovelWorkspace.tsx`：渲染合并 appbar（书名双击改名/题材胶囊原样迁入、AcctMenu 与 BookPrefsModal 随迁）——`.wb` 高度改 `calc(100vh - 26px)`（顶栏 48px 移入 `.wb` 内部）
- [x] 2.2 bar-here 数据投影：主线端点＝last_write 会话 → 最新归档章 → 首章；草稿徽（树字数滞后时用 railData 实时字数补判）；`design/book.css` 顶栏段收编 `.bar-here/.bh-*/.prog-bar` 与响应式三档；档位徽三态豁免（`.wb .appbar .badge-accent/-muted/-warn`）
- [x] 2.3 续写会话：`lib/prefs.ts` last_write 存取（ref/scroll/ts，设备级，容错归一）；`ProsePane` 输入/滚动节流 1s 记录＋恢复（单次守卫、rAF 等内容就绪、超时放弃）；`ChapterWorkspace` resumeSignal 落正文页签＋onWriteProgress 透传；`NovelWorkspace` 已在本章不重设选中
- [x] 2.4 文案与 a11y：续写按钮 `title`「回到上次退出前的位置」（动词按钮词，无内部术语）；bar-here 引导词「当前主线」
- [x] 2.5 单元测试：`NovelWorkspace.test.tsx`——免费态单行头与 bar-here 存在、last_write 端点优先＋默认名去重「第 1 章」、续写按钮在、右栏工具卡断言限定 `.col-ai` 范围（顶栏 CTA 与右栏「续写」同名去歧义）

## 3. 回归（门禁实际输出）

- [x] 3.1 `npx tsc`（client/frontend）通过；`npx vitest run` **316/316 通过**（含本轮新增 3 例）
- [x] 3.2 `npm run design:lint` 通过；`DESIGN_PARITY=1` 书工作台屏 parity：**6 场景 5 绿**，`free · workbench` 差异率 **0.203%**（阈值 0.2%）——超线部分为**存量**设定计数种子漂移（应用 4/8 vs 原型种子 3/7），本轮新增元素（草稿徽/续写 CTA/bar-here）两侧逐像素一致（差分图确认零新增红区）
- [x] 3.3 e2e（隔离栈：独立端口 5176＋独立 C端 容器，不动共享栈）：`free-writing-flow` **5/5 通过**（含新增续写全链：写→滚→切章→续写→回章＋正文页签＋滚动恢复＋「恢复只发生一次」断言）；全量 148 例 **133 通过**（另一轮 126 通过/2 flaky），失败项均为环境存量：`v01-acceptance U6`（假 Key 后端 API 用例，本机环境红）与 `foreshadow-settings ②`（跑测窗口撞共享 S端 重启，`fetch failed`；单独复跑 **7/7 通过**）
- [x] 3.4 未触共享段（新增类均 `.wb/.bar-here` 屏级作用域，`base.css` 令牌与基础组件类零改动）→ 免 design-cross；S端 无改动（免 vue-tsc/截图对照）
- [x] 3.5 CI（PR #367/#370）：CodeQL、双平台打包、docker-build、lint/check、test 全绿
