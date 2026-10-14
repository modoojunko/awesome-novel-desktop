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
- 产物＝10 份 Markdown（简介/题材/世界设定/角色设定/人物关系与势力/主线剧情/章卷结构/写作文风/写作技法/伏笔）
  ＋ 知识图谱三件套：图谱.json（契约 deconstruct-graph/6＝唯一正身）、图谱.html（离线单文件四视图：章链/地点树/关系网/场景图）、
  图谱.svg（静态一张：全网＋地点账）；事实源=任务行 products/cards JSON，图谱=导出时刻代码投影，
  盘上只有导出物化与临时分块（staging 完成即清）。
- 图谱纪律（三路评审 2026-10-14＋用户令定版）：边只挂封闭关系类型 enum（五组 19 型，动作词归事件）；
  地点以归属树表达、逐章在场 presence（where 可 null＝未知区）；坐标入独立 layout 块；视图分工——
  关系网不表达地点；数据门禁三条＋quote 原文回验＋三级降级（图谱不全不拖垮 md 出口）。
- 10 个维度的提示词模板进提示词仓（ai-novel-prompts），随分层包 CDN 发布；本仓不落 .prompt 源。
- 调度独立于 job_runner 全局单飞槽（不与备份/成稿下载互斥），独立任务表+私有串行 worker+启动恢复 sweep。
- 不做：维度并行、格级续拆、epub/docx 输入（留格式占位）、产物应用内预览/编辑、PRO 门禁（全用户自备 key）。

## Capabilities

### New Capabilities
- `deconstruct-book`: 拆书任务全链路——创建（上传/编码探测/解析/模型选择/探针/范围勾选）、
  串行队列与进度、十维度 AI 管线与断点续拆、结果目录与勾选出口（建书/导出）、失败与取消；
  含知识图谱导出（graph/6 契约、装配投影、四视图查看器、数据门禁与降级）。

### Modified Capabilities
<!-- 无：不改变既有 capability 的需求。建书复用 novels/settings 既有域服务；提示词经既有
     prompt-pack 分发机制；顶栏下拉为新增组件不触令牌/词表。 -->

## Impact

- 后端（client/backend）：新增 `deconstruct/` 域（router/service/pipeline）+ 全局库
  `deconstruct_jobs` 表 + 独立串行 dispatcher；`importer` 抽出可复用的文本解析（编码探测/分卷分章）；
  建 book 复用 `novels/service.py` 与 settings 域服务（world/characters/story_arc/style/hooks 清洗护栏）。
- 前端（client/frontend）：新增 `/tools` 任务清单页与创建/详情页；顶栏「写作工具 ▾」下拉；
  任务轮询 hook 与 queryKeys 任务键族；复用 ImportUploadZone 解析口径、ModelPicker、AcctMenu 交互纪律。
- 提示词仓（awesome-novel-prompts）：`deconstruct-*.prompt` 13 份（card＋十维度＋reduce＋place 归并）；
  card 契约扩展 places/presence 抽取；关系/地点同义归并专款进归并模板；登记 TIER_FREE（兑现不分档）。
  发布顺序＝本仓合码 → 提示词仓合入+发包 → 用户更新客户端；老包（无 presence 键）以 min_pack_version
  门槛禁开图谱出口并给升级引导（防“合法契约但空图谱”静默劣化）。
- 设计稿：`docs/design-c/drafts/ai-novel-c端-拆书.html`（v9）＝任务流视觉真值；
  `ai-novel-c端-拆书知识图谱-原型-v7.html`（v1–v7 演进留档）＝图谱查看器视觉与交互真值（数据契约 graph/6）。
- 风险已评审（四方会审 2026-10-12＋三路评审 2026-10-14）：50MB 上限流式、GBK 编码探测、取消端点、
  factions≤6 clamp、同名角色 409 去重、新书无章伏笔 FK 置空、缺包 503 引导；图谱侧：卡片膨胀遥测门槛
  （presence 覆盖率≥97%）、地点别名宁留两户不错并、parent 禁位移句推断、导出覆盖 sha256 保护、
  规模阅读过滤器（300 章不糊线团）。
