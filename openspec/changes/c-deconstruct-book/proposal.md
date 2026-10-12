# 拆书（写作工具任务）

## Why

作者需要从他人的成熟作品中「逆向学习」：把一本整本小说拆成设定与技法材料，供自己写书时参考与借鉴。
目前这条链路只能靠作者手工+AI 会话拼凑（参照 `~/Downloads/反Ai案例/.../对标/*/拆文报告.md` 的人工拆书实战产物），
没有产品化。拆书与既有「导入稿子→建书」不同：导入是把稿子变成**自己的书**，拆书是把别人的书变成
**参考材料**（事实源=任务，不落书库）。交互设计稿已定稿
`docs/design-c/drafts/ai-novel-c端-拆书.html`（v9，六态，含四方评审修订与用户红批注修订）。

## What Changes

- 顶栏新增「写作工具 ▾」下拉（任务清单 / 拆书 / 更多工具占位），书列表页可见；书内态行头不放入口。
- 新增拆书任务流：创建任务（上传整本 txt → 本地解析回填书名/字数/章节 → 选拆解模型与拆解范围 →
  探针门 → 创建进队列）→ 任务清单（纯清单多行：拆解中/排队中/已完成/已失败/需重传）→
  任务详情（进行中：十维进度；完成：结果目录树+勾选+出口二选一；失败：错误面板+断点续拆）→
  出口二选一（建书：勾中的设定项灌入新书设定页；存本地文件夹：勾中的产物+README 导出）。
- 产物＝10 份 Markdown（简介/题材/世界设定/角色设定/人物关系与势力/主线剧情/章卷结构/写作文风/写作技法/伏笔）；
  事实源=任务行 products JSON，盘上只有导出物化与临时分块（staging 完成即清）。
- 10 个维度的提示词模板进提示词仓（ai-novel-prompts），随分层包 CDN 发布；本仓不落 .prompt 源。
- 调度独立于 job_runner 全局单飞槽（不与备份/成稿下载互斥），独立任务表+私有串行 worker+启动恢复 sweep。
- 不做：维度并行、格级续拆、epub/docx 输入（留格式占位）、产物应用内预览/编辑、PRO 门禁（全用户自备 key）。

## Capabilities

### New Capabilities
- `deconstruct-book`: 拆书任务全链路——创建（上传/编码探测/解析/模型选择/探针/范围勾选）、
  串行队列与进度、十维度 AI 管线与断点续拆、结果目录与勾选出口（建书/导出）、失败与取消。

### Modified Capabilities
<!-- 无：不改变既有 capability 的需求。建书复用 novels/settings 既有域服务；提示词经既有
     prompt-pack 分发机制；顶栏下拉为新增组件不触令牌/词表。 -->

## Impact

- 后端（client/backend）：新增 `deconstruct/` 域（router/service/pipeline）+ 全局库
  `deconstruct_jobs` 表 + 独立串行 dispatcher；`importer` 抽出可复用的文本解析（编码探测/分卷分章）；
  建 book 复用 `novels/service.py` 与 settings 域服务（world/characters/story_arc/style/hooks 清洗护栏）。
- 前端（client/frontend）：新增 `/tools` 任务清单页与创建/详情页；顶栏「写作工具 ▾」下拉；
  任务轮询 hook 与 queryKeys 任务键族；复用 ImportUploadZone 解析口径、ModelPicker、AcctMenu 交互纪律。
- 提示词仓（awesome-novel-prompts）：新增 `deconstruct-*.prompt` 10 份 + 登记 TIER_FREE（兑现不分档）；
  发布顺序＝本仓合码 → 提示词仓合入+发包 → 用户更新客户端（缺包=功能内 503 引导文案，不崩）。
- 设计稿：`docs/design-c/drafts/ai-novel-c端-拆书.html`（v9）为实现视觉真值。
- 风险已评审（四方会审 2026-10-12）：50MB 上限流式、GBK 编码探测、取消端点、factions≤6 clamp、
  同名角色 409 去重、新书无章伏笔 FK 置空、缺包 503 引导。
