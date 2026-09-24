## Context

现有文件出口只有系统数据备份：`client/backend/backup/export.py` 的线程单飞任务（`_job` 全局 + `_job_lock` + `start_*_job` 返回 None → 路由 409）+ `/backup/export/start|status`，前端 `AcctMenu.runBackup` 走壳桥 `pick_folder` 后本机直写、无进度条。壳桥 `NativeBridge`（`client/packaging/build/pywebview_app.py`）已有 `pick_folder` / `pick_save_file` / `pick_open_file`。`/backup/export/status` 前端零消费（唯一消费方是 `test_backup_export.py`，只读 `state` 字段）——抽取的兼容冻结面 = `state` 枚举 + 端点存在性 + backup 测试。

内容来源：`Chapter` 行（`ref/title/status/word_count/has_prose/ghost_of`，见 `models/chapter.py`）；**正文不在 Chapter 行上**，在 `ChapterContent.prose`（经 `Chapter.content` relationship 取）。主线判定唯一入口是 `chapters/scope.py::mainline_stmt`（`ghost_of IS NULL`，模块契约要求新增消费面必须登记）；旧稿支线有两种形态——重写型（ref 变 `-r{8hex}`）与回退型（**ref 不变**，仅置 `ghost_of`），因此**按 ref 形态过滤不成立**，必须走 mainline_stmt。排序字段：`Volume.volume_no` + `Chapter.chapter_no`（`dump_book_into` 有先例）。

约束：C端生产是本机单后端（SQLite），后端进程与用户同机——直写用户所选目录是既有模式，不需要浏览器下载路径。

## Goals / Non-Goals

**Goals:**
- 一条与备份并列的读者成稿出口：md / txt / docx，多格式各出一文件，本机直写。
- 弹层四态（表单 / 进度 / 后台运行 / 完成）+ 失败可读可重试。
- 任务与备份共用同一套单飞与状态查询机制，不造第二套。

**Non-Goals:**
- PDF 生成（另立版本；见 proposal「首版不含 PDF」）。
- 长图/封面/EPUB、按卷分包、云端上传。
- 备份/恢复链路的任何行为改动（本 change 只对齐文案）。

## Decisions

**1. 任务机制：抽取 `job_runner`，而不是把新 kind 塞进 backup 模块。**
把 `backup/export.py` 里的通用部分（`_job`/`_job_lock`/`_start`/`job_status`/`_set`/`_phase`/错误归类）抽成 `client/backend/job_runner.py`，支持带 `job_kind` 的通用负载；`backup/export.py` 改为薄适配（对外函数签名不变，路由与既有测试不受影响），`manuscript/` 走同一 runner 注册 `kind: "download"`。`books_total/current_book` 等 backup 专属字段降级为 backup 适配层的私有负载。status 快照必须深拷贝（`deepcopy`）或维持「`_set` 只整值替换」纪律并写测试锁住——泛化负载后浅拷贝 `dict(_job)` 会泄漏嵌套可变状态。`archive/reconcile.py` 是同一 `_job` 模式的第三份拷贝，本 change 不并入，但 design 留出口：后续可迁到 job_runner。
替代方案 A：在 backup 模块加 `kind: "manuscript"` 分支——被否，命名与职责错位，日后备份契约演进容易波及下载。
替代方案 B：另写一套线程管理——被否，状态语义会分叉（错误码、phase 命名、单飞规则），前端要写两套轮询。

**2. 单飞是全局的（备份与下载互斥），拒绝原因要区分。**
沿用全局 `_job`：任一任务在跑时新请求返回 None → 409。响应 detail 用结构化 `{"message", "running_kind"}`，前端按 kind 说人话（「已有备份在进行」/「已有下载在进行」）；`AcctMenu` 现在直接 `alert(res.text())`，需同步适配读结构化 detail（否则裸显 JSON）。理由：同一时刻并发写盘会让进度与错误归因混乱，且这是单用户桌面应用，互斥没有体验代价。

**3. 内容装配单点：`manuscript/content.py::build_manuscript(db, project) -> Manuscript{volumes:[{title, chapters:[{title, prose}]}]}`。**
三种渲染器只消费 `Manuscript` 结构，不各自查库。主线章经 `chapters/scope.py::mainline_stmt` 取（`ghost_of IS NULL`——同时排除重写型 `-r{8hex}` 与回退型保原 ref 两种旧稿），并在 `scope.py` 消费面登记表登记第 6 项；只收 `has_prose` 为真的章（与前端摘要口径同源）；排序 = `Volume.volume_no` + `Chapter.chapter_no`。
替代方案：渲染器各自遍历 ORM 行——被否，内容边界（哪些章算数）会三处各写一遍，最容易在这里出 sneaky bug。

**4. 文件名与路径安全：复用备份先例的单一 sanitize。**
以 `backup/export.py::sanitize_book_filename` 为基底（剥非法字符与 `\r\n`、rstrip 点空格、60 字上限），补 `\`（Windows 分隔符）；空则回落「书名 · 主线全稿」；同名文件按覆盖处理（用户已选定的目标，覆盖优于静默改名）。扩展名由渲染器决定（`.md` / `.txt` / `.docx`）。

**5. 写盘策略：先写 `*.part` 再 rename，失败清理。**
注意：备份现状**没有**失败清理（失败时 `.part` 遗留），新模块是净新增清理逻辑，不与备份「保持一致」。任一格式失败 → 任务 state=error、已完成文件保留、未完成 part 删除。错误映射在 job_runner 统一为一套：errno 28→`disk_full`、13/30→`permission_denied`、ENOENT/NotADirectoryError→`invalid_path`、其余→`io_error`（修正 backup 里 single 线程把一切 OSError 归 `io_error` 的旧口径）；前端展示失败格式行（格式行状态含「失败」+ per-format error）并给「重试」。

**6. Word 渲染复用既有 `python-docx` 依赖。**
`requirements.txt` 已有 `python-docx>=1.1.0`（`novels/importer.py` 惰性使用，含 ImportError 兜底先例）——本 change **零新增依赖**。渲染器惰性 import，ImportError → 任务错误（不崩进程）；打包侧 `build.spec` hiddenimports 无 docx，现状靠 modulegraph 跟随惰性 import 收集，验证方式 = 冻结环境内真跑一次 `render_docx`（lxml 二进制依赖才是常见失败点）。中文字体不在 docx 内嵌，交由阅读端渲染，避免包体膨胀。
替代方案：手写 OOXML zip——被否，维护成本与格式风险不成比例。

**7. 前端弹层挂书工作台壳层，轮询跨视图保活。**
新组件 `ManuscriptDownloadModal`：表单 / 运行 / 完成三态内部管理，`setInterval` 轮询 `/manuscript/download/status`；「后台运行」= 关闭弹层但继续轮询，完成 toast 提示；关闭弹层（点遮罩/取消）在运行中按「后台运行」处理，不做隐式取消。**弹层挂载在 `NovelWorkspace` 壳层（照 `UpgradeModal` 模式），不挂在条件渲染的 PreviewView 内**——预览视图切去写作/设定即卸载，挂那里会丢 toast 与会话记忆（保存目录/文件名/格式的会话记忆随壳层存活）。
替代方案：复用 `AcctMenu` 的「发起即忘」模式——被否，设计稿要求进度可见。

**8. 壳桥新增 `open_folder(path)` 与 `default_dirs()`。**
`open_folder`：macOS 用 `open`、Linux 用 `xdg-open`（判 returncode）；**Windows 用 `os.startfile` 且不判 returncode**（explorer 成功也常返回 exit code 1，按 returncode 判定会假报失败）；失败静默降级为 toast（完成页仍显示完整路径）。`default_dirs()`：返回系统文稿/桌面/下载目录（`Path.home()` 派生），供弹层常用位置快捷项；无壳环境下该组按钮不出现。

**9. 无壳降级：入口可见、点击说明「下载成稿需要桌面版应用」。**
不伪装浏览器下载（会产出与「本机直写 + 目录选择」语义不一致的文件），并在文案中给出可点击出口（下载桌面版）。

## Risks / Trade-offs

- [抽取 job_runner 会碰到备份链路的既有测试] → 对外签名（`start_backup_job` / `start_single_job` / `job_status`）保持不变；pytest 里 `backup` 相关用例全量回归，抽取单独成一个 commit 便于回滚。
- [docx 依赖增加打包体积与打包失败面] → 依赖仅 `python-docx`（纯 Python + lxml 已有）；打包脚本加 hiddenimports 检查项，缺依赖时任务报 err 而不是崩溃。
- [磁盘满时多格式半途失败] → part+rename + 失败清理已定义；`disk_full` 错误码单独映射，前端文案提示清理空间后重试。
- [覆盖同名文件可能覆盖用户既有文件] → 完成页明确列出每个产出文件名与所在目录；v1 不提供「自动改名」，保持可预期。
- [中文文件名在 macOS 的 NFD 归一化造成「看起来同名却两个文件」] → 只做写入不做存在性判断，不依赖名字比对；如后续加「已存在」提示需显式处理归一化。

## Migration Plan

**前置：`c-preview-reader` 先行落地**（下载入口挂在三栏右栏；preview.html 基线先建立，本 change 才能在其上做「删 PDF 项 + 下载文案」的原型修订与 ADJUSTMENTS 登记）。实现顺序：

1. 提取 `job_runner` 并让 `backup/export.py` 适配（pytest 全量回归；409 detail 结构化 + AcctMenu 消费适配）。
2. 新增 `manuscript/`（content + 三渲染器 + router；scope.py 消费面登记第 6 项）。
3. 壳桥 `open_folder`/`default_dirs` + 冻结环境验证 docx 渲染。
4. 原型修订（删 PDF、下载文案）+ ADJUSTMENTS 登记 → 前端弹层（挂壳层）+ 预览右栏入口 + `AcctMenu` 文案收紧；e2e 打桩。
5. 回滚：删除 `/manuscript/*` 路由与前端入口即可；`job_runner` 抽取保持向后兼容，回滚不需要动备份链路。

## Open Questions

无。首版范围、术语与格式集合均已拍板（PDF 缓办）。
