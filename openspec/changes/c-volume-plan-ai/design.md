## Context

C端 已有：`volumes` 表与卷纲字段集（`volumes/schemas.py`／`service.py`）、卷纲文本装配单源
（`volumes/render.py`，写正文时已在用）、章纲 AI 起草的成熟模式（`chapters/ai_draft.py`：草稿不落库＋
JSON 校验兜底＋失败重试）、AI 客户端与计量（`get_ai_client_for_novel`／`record_usage`）、
「判定/短答复类关闭思考」路径（`ai_client.py`）、库生命周期与世代迁移（`db_lifecycle.py` +
`schema_version.py` + `migration/`）、右栏卷域面板的预留位（`VolumeAssistPanel` 文件头写着
「卷域 AI 动作另行立项」）。提示词已用真书真模型实测（`docs/volume-plan-prompt-experiment/`）。

## Goals / Non-Goals

**Goals：** 把「主线 → 分卷 → 卷纲 → 验证」这条链补齐，且**全部长在既有骨架上**：不新建表、不建第二套
AI 注册表、不复制提示词装配；三个 AI 端点与三份提示词可被独立测试与回归。

**Non-Goals：**
- 不做「按卷纲补全本卷章纲」「生成卷末钩子建议」等卷域辅助动作（本 change 已从右栏撤掉，留待另立项）。
- 不做跨卷重排／骨架守护（高档位能力，见 `volume-plan-ai` 之外的后续 change）。
- 不做「对已写内容」的真检查（P0 只输出 `none` 占位；P1 读归档章）。
- 不改 entitlement 契约、不动 S端、不新增全书篇幅字段。

## Decisions

1. **三个端点落 `volumes/ai_plan.py`**（同族于 `chapters/ai_draft.py`），路由持 `APIRouter` 并在
   工作台路由处**显式 include**（#255 的 404 事故先例：ruff 会删「看起来没用」的副作用 import）。
   备选：塞进 `chapters/router.py`（否决：卷域 AI 与章域混居，且该文件已很长）。
2. **素材装配复用既有非章域单源**（**修正**：原写「从 `build_chapter_context` 取同源字段」不成立——它必须传
   chapter ref、角色取自本章章纲、伏笔按本章排除，0 章书根本用不了）：卷纲文本走 `volumes/render.py`；
   台账走 `prompt/context.py` 的台账块（编号口径同源）；世界摘要走 `settings/world_model.py` 的世界块
   （铁律全量）；主线走 `novels/router.py` 的 arc 归一；题材走 `genres/service.py` 的题材段；角色走
   `settings/characters` 的列表（主角＋点名人物＋本卷 cast）。备选：为卷域另写一套拼接（否决：必然漂移）。
3. **出稿不落库 + 代码侧校验兜底**：照 `ai_draft` 模式——不落库、返回结构化草稿、JSON 解析失败重试一次、
   再失败降级为纯文本提示。校验项见 `volume-plan-ai` 的提示词契约 requirement。
4. **三份提示词入 `prompts/`**（`volume_options` / `volume_expand` / `volume_check`），七条硬规则与体检判据
   **单源**：抽一份共享片段被两个模板引用，或加一条对拍测试断言两处都含规则清单（house 有
   `entitlement-defaults.json` 对拍先例）。备选：两处各写一份（否决：会漂移）。
5. **走「关闭思考」路径**（实验实测：不关思考时推理模型把预算全用在 thinking、响应无 text 块），
   `max_tokens` 显式传 **4096**（既有判定类先例：2048 偶发「无文本输出」，见 `settings/ai_router.py` 注释；
   未生成的预算不计费），并把「空文本」按既有 `_judge_chat` 口径重试一次。
6. **`volumes` 加一列 `plan_line`（可空）**：可空列属 **additive**，不升 `SCHEMA_VERSION`——登记进
   `main.py` 的 `ADDITIVE_COLUMNS`（现为空 dict）并补 DDL；**读写链**（`volumes/schemas.py` 的
   `VolumeCreate`/`VolumeUpdate` 增字段、`service.py` 的 `_DETAIL_SCALARS` 与写回、前端 payload 类型）
   SHALL 一并改（否则前端传参会被 `extra="ignore"` 静默丢弃）。注意既有隐患：`main.py` 的补列分支
   `except Exception: pass` 且指纹戳在补列前刷新，列缺失会被永久掩盖——本 change 顺手把 except 收窄到
   duplicate column 并加测试。备选：存 `story_arc.volumes` legacy 键（否决：KV 是并列的第二事实源、
   无卷号身份、形状固定为 title/conflict/chapters，不适合承载单卷字段——它本是留给本 change 的键，
   但我们不需要它，因为设计里没有持久草稿）。
7. **回填的实现形状**（不止「增量 append」一句话）：卷纲表单是整对象受控 + JSON 比较判脏，回填期间要保证
   「作者输入不被覆盖」：draft 由外层持有（`useVolumePlan` 挂在 NovelWorkspace，不在弹窗内），段 key 用固定块名
   （React 复用 DOM、焦点与选区不丢），填充只写「未被作者改过」的字段（`touched: Set`），回填期间挂起离开拦截
   （或提示「正在回填，离开会丢弃」）。空书采纳时先建卷行再进表单（见 spec 的存储与数据 requirement）。
8. **AI 入口只留右栏**：中栏不放 AI 按钮；规划台是弹出页（复用 `components/design/Modal`，`wbStyle` +
   `width≈720`）。**生成/方案/回填状态 SHALL 挂在 NovelWorkspace（弹窗之外）**——Modal 关闭 200ms 后卸载子树，
   状态放弹窗内会随关闭丢失（违反「关掉不中断」）。「弹窗开着时背后页面静止」的正确落法是**中栏分支不读生成态**
   （而不是去冻结它）；只有回填阶段开始后才驱动中栏。
9. **体检按需现算、不落库**（与既有体检族同口径）；写作默认页的「卷的验证」卡点一行＝选中该卷并立刻体检。
10. **上一卷结尾取数收敛成一个函数**（`resolve_prev_ending(prev_vol)`：有归档章节取实际收尾，否则取上一卷
    卷纲的预期结局），不散落在 prompt 拼接里。
11. **门禁（已拍板 2026-09-20）**：生成类复用 `ai-generate`（PRO）；**体检免费**——开一条只读例外通道
    （后端 AI 访问门对卷纲体检放行、前端同一判定）。这与产品既有文案「免费版：体检与建议只读」一致，
    但既有章级 `ai-check` 实际是 403（既有口径不一致，本 change 只为自己这条通道负责，不动章级既有行为，
    也不改套餐档位）。免费档未配模型时给出「先接一个模型」的引导，不报 500。

12. **前端状态**：不引入 `selVol`——「写作默认页」用派生分支（卷数 > 0 且章节总数 = 0 且 `selectedId` 为空）
    判定，与 `useWorkbench` 的选中单源保持一致；`createVolume` 的「建卷后强制选中」副作用 SHALL 在采纳路径上
    让位（否则落点卡被顶回卷纲页）。
13. **右栏取数**：`VolumeAssistPanel` 的 props 与 `RailIdleData` SHALL 扩展（分卷依据 5 行 + 已有卷列表含
    `chapter_target`）；`GET /volumes` 的树接口目前不返回 `chapter_target`，SHALL 补字段或改走行级详情接口；
    面板的 `key` SHALL 只按卷（不按页签），否则切页签会吞掉体检报告。

## Risks / Trade-offs

- [三套方案退化成三个同义包装] → prompt 明写「结构上真的不同，想不出三套给两套」＋要求每套给「侧重」＋
  代码侧校验（侧重去重后数量＝套数；走向两两相似度过高则标记）。实验实测两轮相似度 0.15–0.29。
- [编造设定里没有的人物/势力] → 规则 1 明写「只用出现过的」＋**实体名对拍**（输出里的专有名词必须能在
  角色表/世界设定/全景里找到）。注：n-gram 启发式已实测全是误报，不采用。
- [推理模型上拿不到 JSON] → 关思考路径 + 端点拒绝时去掉重试 + 解析失败降级（见 Decision 5）。
- [回填期间吞掉作者输入] → 增量 append（Decision 7）。
- [子路由未被 include 导致 404] → 显式 include（Decision 1）。
- [加列踩到世代迁移的 fail-open 隐患] → 迁移走既有路径并补对拍测试；不新增迁移机制。
- [主线很薄时质量下降] → 3 套允许只给 2 套（`note` 写明原因）；把「主线薄」样本列入 P1 回归集。
- [提示词回归在 CI 里天天红] → 真模型断言只做「硬不变量 + 每模板 3 次取多数」，且只在手动/夜间 lane 跑；
  确定性的部分（模板结构、占位符、规则清单、块顺序、解析与校验函数）做成 pytest 进门禁。
- [新前端文件不入覆盖率契约] → `VolumePlanModal` 等新文件 SHALL 登记进 `src/coverage-contract.ts`，
  否则 `vitest --coverage` 门禁会红。
- [OpenAI 格式端点上「关思考」可能静默失效] → `ai_client` 的 thinking 注入只在 anthropic 分支，OpenAI 分支走
  `extra_body` 且**没有「端点拒绝就去掉重试」**；用户若配 GLM 这类 openai 格式端点，预算可能全烧在思考上而
  拿不到 text。本 change 的三端点 SHALL 在两个分支各验证一次；若确认失效，在 `ai_client` 层补同款去掉重试
  （属既有组件加固，改动面写进 design 的 Open Question，不在本 change 顺手重构）。

## Migration Plan

1. 加列 `volumes.plan_line`（可空）：新库 create_all 自然带上；旧库走既有升级路径；无历史数据回填需求。
2. 回滚：该列可空且旧代码不读，直接忽略即可（无需回滚迁移）。
3. 前端无灰度：右栏三态与落点页直接替换（本仓库无存量用户，见项目记忆的零基线口径）。

## Open Questions

- 卷数估计（「这本书大约 4 卷」）是否在 P1 变成作者可编辑的输入（目前是 AI 明示假设）？
- 体检报告要不要缓存到库（当前每次现算；长书多卷时成本可忽略，暂不缓存）？
- 卷域辅助动作（按卷纲补全本卷章纲／生成卷末钩子建议）何时立项？
