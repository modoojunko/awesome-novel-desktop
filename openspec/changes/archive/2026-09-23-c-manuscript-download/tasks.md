> 前置：`c-preview-reader` 已合入（预览三栏右栏存在、`prototypes/preview.html` 基线已入库）。未合入时第 0 组与 5.4 阻塞。

## 0. 原型先行（修订 preview 基线）

- [ ] 0.1 修订 `docs/design-c/prototypes/preview.html` 的下载弹层：删除 PDF 格式项（不占位）、全部「导出成稿 / 导出主线全稿」文案改「下载成稿 / 下载主线全稿」、右栏入口按钮改「下载成稿…」
- [ ] 0.2 在 `prototypes/ADJUSTMENTS.md` 登记本 change 偏差：PDF 缓办（首版无该项）、`.ex-*` 新组件词表（格式勾选行/位置行/进度清单/完成块）、后台运行与重开弹层读回已完成态的语义（设计稿 `exOpen` 把 done 重置回 form，按 spec 修正）、右栏入口进基线
- [ ] 0.3 `npm run design:lint` 通过（`strictGlobs` 已含 preview.html）；`design:check` 的 preview 场景像素确认仍 <0.2%

## 1. 任务机制抽取（先行，独立可回滚）

- [ ] 1.1 新增 `client/backend/job_runner.py`：抽出通用单飞任务（`_job`/锁/`start`/`status`/`set`/`phase`/错误归类），支持自定义 `kind` 与负载字段；status 快照 `deepcopy`（或以测试锁住「`_set` 只整值替换」纪律）
- [ ] 1.2 `backup/export.py` 改为薄适配（`start_backup_job`/`start_single_job`/`job_status` 对外签名不变，`books_total/current_book` 归 backup 私有负载），`pytest client/backend/tests -k backup` 全绿
- [ ] 1.3 409 响应 detail 结构化为 `{"message", "running_kind"}`（backup 与 download 路由同口径）；补后端用例断言该字段（现有 `test_backup_export.py` 声称覆盖单飞但实际无 409 断言，一并补上）；`AcctMenu` 的 `alert(res.text())` 适配结构化 detail

## 2. 内容装配与三格式渲染

- [ ] 2.1 新增 `manuscript/content.py`：`build_manuscript(db, project)` 经 `chapters/scope.py::mainline_stmt` 取主线章（**禁止按 ref 形态过滤**——回退型旧稿 ref 不变仅置 `ghost_of`），并在 `scope.py` 消费面登记表登记第 6 项；只收 `has_prose` 为真的章（正文经 `Chapter.content` relationship 取 `ChapterContent.prose`）；排序 `Volume.volume_no` + `Chapter.chapter_no`；`pytest` 断言内容边界（空章跳过、**重写型与回退型两种旧稿都不进产物**、章序正确）
- [ ] 2.2 渲染器 `render_md` / `render_txt`：卷标题与章题层级、段落空行；`pytest` 断言产物结构与边界（空段落、含 markdown 特殊字符的正文不被破坏）
- [ ] 2.3 渲染器 `render_docx`：复用既有 `python-docx>=1.1.0` 依赖（零新增），惰性 import + ImportError→任务错误（`novels/importer.py` 有兜底先例）；`pytest` 打开产物断言标题层级与段落数
- [ ] 2.4 文件名 sanitize 以 `backup/export.py::sanitize_book_filename` 为基底（剥 `\r\n`、rstrip 点空格、60 字上限）并补 `\`；写盘策略 `*.part` → rename + **失败清理 part（净新增，备份现状无清理）**；错误映射统一（errno 28→`disk_full`、13/30→`permission_denied`、ENOENT/NotADirectory→`invalid_path`、其余→`io_error`），用例覆盖各映射

## 3. 下载路由与任务

- [ ] 3.1 新增 `manuscript/router.py`：`POST /api/manuscript/download/start`（target_dir/filename/formats/book_id）与 `GET /api/manuscript/download/status`，走 `job_runner`（kind=download）；格式白名单校验（md/txt/docx）未知格式 422；**发起时校验书归属（book_id→Novel.user_id），非法 404**
- [ ] 3.2 后台线程逐格式推进：每格式写一个文件、逐格式状态写入 job 负载（等待/下载中/完成/**失败 + per-format error**）与 `files` 列表；`pytest` 覆盖多格式全成、单格式失败中断且已完成文件保留、失败行带可读原因
- [ ] 3.3 单飞与错误语义用例：任务进行中再发起 → 409 + `running_kind`；**备份进行中发起下载 → 409 且 running_kind=backup**；目录不可写 → error.code=`permission_denied` 且消息含目标路径

## 4. 桌面壳桥

- [ ] 4.1 `client/packaging/build/pywebview_app.py` 的 `NativeBridge` 新增 `open_folder(path)`（macOS `open` / Linux `xdg-open` 判 returncode；**Windows 用 `os.startfile` 不判 returncode**——explorer 成功也返回 1）与 `default_dirs()`（文稿/桌面/下载，`Path.home()` 派生），失败返回 False 且不抛
- [ ] 4.2 打包链路验证：**冻结环境内真跑一次 `render_docx`**（lxml 二进制依赖才是常见失败点）；`--smoke` 通过

## 5. 前端弹层与入口

- [ ] 5.1 新增 `workbench/ManuscriptDownloadModal.tsx`（**挂 `NovelWorkspace` 壳层，照 `UpgradeModal` 模式**——预览视图条件挂载，挂预览内切视图会丢轮询/toast/会话记忆）：表单态（保存位置 + 原生选目录 + 常用位置 chip【上次保存目录 + `default_dirs()`】+ 文件名 + 格式勾选 + 摘要）、进度态（总进度 + 逐格式行【等待/下载中/完成/失败】+ 后台运行）、完成态（产出文件列表 + 打开文件夹）、失败态（可读原因 + 重试）；`data-od-id` 按 `download-*` 命名
- [ ] 5.2 轮询与后台运行：`setInterval` 查 `/manuscript/download/status`；运行中关弹层 = 后台运行不取消；完成 toast；**切视图保活**（弹层挂壳层天然满足，测试覆盖「切到写作再切回」）；重开弹层读回状态与上次目录/文件名/格式（会话内记忆）
- [ ] 5.3 无壳降级：探不到 `window.pywebview.api` 时按钮点击呈现「下载成稿需要桌面版应用」+ 可点击出口，不发起请求
- [ ] 5.4 预览右栏挂入口「下载成稿…」（前置：c-preview-reader 已合入）；`design/book.css` 新增 `.ex-*` 类（勾选行/位置行/进度清单/完成块），配色全走 token
- [ ] 5.5 术语分离：`AcctMenu` 备份 hint「选择文件夹导出」→「选择文件夹保存」，**同批改 parity 基线原型 `prototypes/list.html` 与 `book.html` 的同款文案** + ADJUSTMENTS 登记（改实现不改原型 = parity 漂移）；确认「下载成稿」链路无「导出」字样（系统数据域「备份/恢复/导出/导入」豁免）
- [ ] 5.6 `__tests__` 覆盖弹层三态、无壳降级、409 `running_kind` 两分支文案（下载在跑/备份在跑）；`npx vitest run` 与 `npx tsc --noEmit` 全绿

## 6. 端到端与门禁

- [ ] 6.1 e2e：`addInitScript` 注入 pywebview 桩（`pick_folder` 返回临时目录、`open_folder` 记录调用、`default_dirs` 返回桩目录）+ 路由拦截后端 start/status，断言完整链路：开弹层 → 选格式 → 发起 → 进度推进 → 完成页 → 打开文件夹被调用；**切到写作再切回弹层态不丢**
- [ ] 6.2 e2e 失败场景：目录不可写（桩返回权限错）呈现 err 文案与重试出口；未选格式主按钮禁用；409（备份在跑）文案正确
- [ ] 6.3 本机 docker 栈跑受影响 e2e 全量 + 后端 `pytest` 全量；`npm run design:lint` / `design:check` 通过（下载弹层与入口的基线已随第 0 组落位）
