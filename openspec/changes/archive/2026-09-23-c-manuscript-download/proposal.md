## Why

用户完书后拿不到「能给人看的东西」：现在唯一的文件出口是系统数据备份（整库/单书的资产包 zip），那是给灾备与换机用的内部结构，不是读者会读的成稿。需要一条独立的「下载成稿」出口——把主线正文导出成 md / txt / docx，存到用户选的本地目录，用来投稿、打印、分享或自己存档。

## What Changes

- **预览右栏新增「下载成稿」入口**（属 `c-preview-reader` 的右栏，本 change 提供弹层与链路；**落地顺序在该 change 之后**），弹层含：保存位置（原生文件夹选择 + 常用位置快捷项【上次保存目录 + 系统文稿目录】+ 可编辑路径）、文件名、格式勾选（**Markdown / 纯文本 / Word 可多选**）。
- **下载内容 = 读者读到的东西**：仅正文（题名 + 正文段落），按卷/章顺序，**不含**章纲、版本历史、旧稿支线、归档版本、设定与提示词；仅收**有正文的章节**。
- **后台下载**：发起后本机后端直接写入所选目录（不走浏览器下载、不弹浏览器另存为），弹层显示进度条与逐格式状态；支持「后台运行」收起，完成后 toast 提示并可从完成页**打开文件夹**。
- **首版不含 PDF（已拍板缓办）**：设计稿的 PDF 选项在首版不出现于格式列表；PDF 依赖阅读排版还原的渲染管线（读览器 DOM 参数 → PDF），另立 change。
- **术语分离（本次拍板）**：面向读者的成稿动作统一叫「**下载**」；系统数据资产的动作叫「**备份**」（现状）与「导出 / 导入」（现状）。顺手把 `AcctMenu` 里备份项提示文案「选择文件夹**导出**」改为「选择文件夹**保存**」，避免两套动作撞词。
- 复用既有基建，不新造：备份导出的「单飞后台任务 + phase/pct 状态查询」（`backup/export.py`）与壳层原生目录桥（`NativeBridge.pick_folder`）；新增壳桥 `open_folder`（打开文件夹出口）与 `default_dirs`（常用位置）。
- `python-docx` 为**既有依赖**（`requirements.txt` 已有，`novels/importer.py` 惰性使用），本 change 零新增依赖。

## Capabilities

### New Capabilities

- `manuscript-download`: 下载成稿的行为契约——内容边界（主线正文、仅有正文的章节、不含内部资料）、格式集合与首版范围（md/txt/docx，PDF 缓办）、弹层交互（位置/文件名/多选格式/进度/后台运行/完成出口）、后端本机直写与任务状态查询、无壳环境降级。

### Modified Capabilities

- `design-system`: 新增弹层组件词汇（`.ex-fmt` 格式勾选行、`.ex-path` 位置行、`.ex-steps` 进度清单、`.ex-done` 完成块）与「打开文件夹」出口的登记。
- `backup-restore`: 备份导出与恢复导入的叫法保持「备份 / 恢复」，其入口提示不再使用「导出」动词；同屏需与「下载成稿」在文案上互不混淆（一句话区分：备份＝换机救数据，下载＝拿成稿给人看）。

## Design Impact

- 受影响端：**仅 C端**（`client/frontend` + 桌面壳 `client/packaging`）。
- 受影响屏/弹层：预览视图右栏入口 + 新弹层「下载成稿」；`AcctMenu` 仅改提示文案。
- 对象状态（对照状态语言总表）：新增任务态两级词汇——任务级 state（idle/running/done/error）与格式行展示态（等待/下载中/完成/失败）；完成态用 ok 语气，失败态用 err 语气并提供重试出口；无新增状态词。
- 是否触碰两端共享段：**否**（新增类只进 `book.css`；壳桥在 desktop 包，不属两端 CSS 契约）。
- 是否需要原型先行：**要**（`prototypes/preview.html` 基线建立后，本 change 修订其下载弹层：删 PDF 项、文案改「下载成稿」、右栏入口进基线；偏差在 ADJUSTMENTS 登记）。
- 设计工件产出者：设计侧会话已产出 `drafts/preview.html`；实现侧负责收编修订与登记。

## Impact

- 前端：新弹层组件（`workbench/` 下，挂书工作台壳层）、`PreviewView` 右栏入口、原生桥调用（`window.pywebview.api.pick_folder` / `open_folder` / `default_dirs`）。
- 后端：新模块 `client/backend/manuscript/`（内容装配 + 三格式渲染）+ 路由（start / status）；**零新增依赖**（`python-docx` 已有）；主线判定接入 `chapters/scope.py` 消费面登记表（第 6 项）。
- 桌面壳：`NativeBridge.open_folder` / `default_dirs`（reveal 与常用位置）。
- 术语：`AcctMenu` 备份项 hint 文案 + parity 基线原型 `list.html`/`book.html` 同款文案；设计文档 `docs/ux/design-language.html` §13 术语表补「下载 / 备份」二分（如标准层接受）。
- 测试：后端 pytest（内容边界含两种旧稿形态 + 三格式 + 任务状态 + 跨类单飞）、前端 vitest（弹层三态 + 409 分支）、e2e（打桩 bridge 的下载链路）。
