## 1. 数据与提示词

- [ ] 1.1 `volumes` 加列 `plan_line`（可空，additive，不升 `SCHEMA_VERSION`）：登记进 `main.py` 的 `ADDITIVE_COLUMNS` 并补 DDL，同时把该分支的 `except Exception: pass` 收窄到 duplicate column；验证四条：**(a)** 断言 `ADDITIVE_COLUMNS` 含 `volumes.plan_line` 的 DDL；**(b)** 手造缺列旧库，经 `TestClient(app)` 真跑 lifespan 后 `PRAGMA table_info(volumes)` 可见该列；**(c)** 手造「metadata 之外多列」的 tolerant 库仍能补列；**(d)** 用 ORM 写入再回读 `plan_line`（只断 PRAGMA 会漏「列在但模型没映射」）
- [ ] 1.2 `plan_line` 读写链：`VolumeCreate`/`VolumeUpdate` 增字段（限长 300）＋`volumes/service.py` 的 `_DETAIL_SCALARS` 与写回＋前端 payload 类型；验证：单测断言 PUT 后 `GET /volumes/{ref}` 回显该字段（防 `extra="ignore"` 静默丢弃），且经建卷接口也能带上
- [ ] 1.3 三份提示词入 `prompts/`（`volume_options` / `volume_expand` / `volume_check`），素材块按端点分列；验证：pytest 对假客户端收到的 `system` 断言**块顺序 index 递增**与各块预算上限（不靠人读）
- [ ] 1.4 规则单源：七条硬规则抽一份片段文件（两个模板用占位符引用），配**逐字相等**对拍测试（改一处必红）＋「标记块存在」断言；界面上的七条（作家语言）声明为有意的第三份改写，不入对拍
- [ ] 1.5 `volumes/service.py` 新增 `resolve_prev_ending(prev_vol)`（事实优先：有归档章取该卷末章的摘要与末段，否则取上一卷卷纲的预期结局，首卷＝全景起步）；验证：单测覆盖「有归档 / 无归档 / 首卷」三分支

## 2. 三个端点

- [ ] 2.1 新增 `volumes/ai_plan.py` 与 `POST /api/novels/{id}/volumes/ai-options`（入参 `line?` ≤150 字，出参 2–3 套四字段 ＋ `note` ＋ `volume_estimate`）；路由持 `APIRouter` 并在 `main.py` 显式 include；验证：契约测试断言 200 与出参形状、`note` 在套数 <3 时必填、路由可达（防 #255 的 404 先例）
- [ ] 2.2 `POST /api/novels/{id}/volumes/ai-expand`（入参 `line` 或 `plan`，出参卷纲草稿 ＋ `cast`/`factions` 申报 ＋ `checks` ≤3）；验证：单测覆盖字段上限、checks 条数、**不落库**（调用前后 `GET /volumes` 与 DB 行数不变）
- [ ] 2.3 `POST /api/novels/{id}/volumes/{ref}/ai-check`（出参三组、状态 ok/warn/none、证据独立字段）；验证：单测断言三组名、无章节时第三组 `none` 占位、不落库；补一条「故意写歪的卷纲必须出 warn」的样本
- [ ] 2.4 三端点统一：显式 `max_tokens=4096`、走关思考路径、解析失败重试一次（把失败原因作为追加消息）后降级为纯文本；验证：单测断言假客户端收到 `max_tokens==4096`、解析失败时 chat 被调两次后返回降级文本（不 502）；用例内清空 `_THINKING_UNSUPPORTED_BASES` 防跨用例污染
- [ ] 2.4b **两个 api_format 分支各验一次**（anthropic 与 openai）：确认关思考在 openai 格式端点（如 GLM）上是否生效；若拿不到 text 块，登记为既有组件缺口并给出本 change 的兜底（按 `_judge_chat` 口径重试），验证：两个分支的单测各一条，含「空文本重试一次」断言
- [ ] 2.5 输出校验兜底（判据先写死再写测试）：套数 2–3、侧重**闭集枚举**去重后数量＝套数、走向两两 `difflib` 相似度 >0.6 触发一次复核、每套卷末非空、**实体集合差**（模型申报的 `cast`/`factions` 减去角色表 name+aliases 与世界势力名，差集非空回传 `warnings`——不 422）；验证：单测喂「三套同义」「含新造人名」两类固定样本，断言 warnings 内容
- [ ] 2.6 门禁与计量：三端点挂 AI 访问门（体检走只读例外通道，见 5.1）＋本书模型门；每次尝试（含失败）走 `record_usage`，operation 名 `volume_options`/`volume_expand`/`volume_check`（失败加 `_fail`）；错误语义 400/404/422（主线空）/502 对齐 `ai_draft`；验证：单测断言 TokenLog 计数与失败路径的 `_fail` 记录

## 3. 前端 · 右栏与规划台

- [ ] 3.1 `VolumeAssistPanel` 三态改造（空书＝规划入口＋分卷依据；写作默认页＝接着往下规划＋卷的验证；选中卷＝验证面板＋报告）；同步扩 props 与 `RailIdleData`（分卷依据 5 行 ＋ 已有卷列表含 `chapter_target`），`GET /volumes` 树接口补 `chapter_target`；面板 `key` 只按卷；验证：组件测试覆盖三态、**退役项缺席断言**（四页签统计卡与四格全书统计不再出现）、点验证行触发体检
- [ ] 3.2 新增 `VolumePlanModal` ＋ 外层 `useVolumePlan`（状态挂 NovelWorkspace，不在弹窗内）：材料、两条入口、3 套卡、生成中与生成完成、回填触发；验证：组件测试覆盖「输入空→展开禁用」「点 3 套→2–3 张四字段卡」「选一套→填入输入框并直接展开」「checks 让 AI 改／整体忽略」「生成中关弹窗→完成后自动回填」
- [ ] 3.3 「弹窗开着背景静止」；验证：组件测试断言生成期间中栏**不出现**生成中/生成完成文案、中栏节点引用不变（否定断言），关闭后才出现进度
- [ ] 3.4 中栏撤净 AI 入口 ＋ 起手卡文案改作家口径（眉标「设定 N/7 已确认」＋说明句＋双入口）；验证：断言中栏无 AI 动作按钮、起手卡文案逐字命中

## 4. 前端 · 落点页 / 卷纲表单 / 回填

- [ ] 4.1 「写作默认页」落点卡：判据＝卷数 >0 且**章节总数 = 0** 且未选中；保存卷纲后落在这里，`createVolume` 的强制选中副作用在采纳路径上让位；验证：组件测试「保存后中栏为落点卡」「曾排过章后删空仍显示选章引导」（对齐既有 e2e 断言）
- [ ] 4.2 卷纲表单段序（进场→展开依据→本卷剧情→冲突→卷末结局→卷基础信息→登场人物→关键剧情节点→伏笔）＋「进场」「展开依据」两行只读（含「写到那里之后换成实际收尾」来源说明与无记录占位）；验证：组件测试断言段序、两行只读、`plan_line` 保存后重开卷纲显示当时那一句
- [ ] 4.3 回填：外层 draft ＋固定段 key ＋`touched` 集合（只填未改过的字段）＋回填期挂起离开拦截；验证：组件测试用**时序夹具**——先在表单打字、再释放回填，断言原输入仍在且段数递增、保存按钮在回填期禁用
- [ ] 4.4 空书采纳：回填前先建卷行（卷名取 AI 建议或「第N卷」兜底，建卷接口要求名称非空）→ 进卷纲表单 → 整表写回（含 `plan_line`）；章数目标取 AI 建议；验证：组件测试「0 卷 → 采纳 → 左树出现该卷且卷纲含展开依据」

## 5. 门禁与口径

- [ ] 5.1 免费档：体检走只读例外通道可用（后端门控放行 ＋ 前端同一判定），生成类保持 PRO 置灰；免费档未配模型时体检给「先接一个模型」的引导而非 500；验证：组件测试与后端单测各覆盖一条
- [ ] 5.2 主线全景为空时不生成（动作变「先补主线」并指向主线设定）；验证：组件测试覆盖该分支
- [ ] 5.3 文案与纪律：新增文案走作家口径（grep 断言不含「判据／落库／排布层／链路／子集」）；grep 断言 `story_arc.volumes` 与篇幅字段零命中；`data-od-id` 冻结（`book-empty`/`empty-cta-ch`/`empty-cta-vol`/`tree-create`）
- [ ] 5.4 存量断言清算：随改造更新 `NovelWorkspace.test.tsx`（起手卡文案、`idle-rail-stats` 四格、`.rail-stats`/`.rail-assist` 纪律）、`volumeWorkspace.test.tsx`、`e2e/workbench-features.spec.ts`（`volume-rail-stats`）、`e2e/creation-flow.spec.ts`、`e2e/free-writing-flow.spec.ts`（选章引导）；验证：三条命令全绿
- [ ] 5.5 新前端文件登记进 `src/coverage-contract.ts`（`VolumePlanModal`、`useVolumePlan` 等）；验证：`vitest run --coverage` 不因未登记文件变红

## 6. 端到端与回归

- [ ] 6.1 e2e 六态（隔离栈，AI 三端点全部 `page.route` 打桩、卷/章真落库）：空书起手 → 规划台（两条入口各一条用例）→ 3 套 → 展开 → 生成中（可控门闩，不按墙钟等）→ 生成完成 → 回填（段序与内容）→ 保存 → 落点卡 → 体检三组（含 `none` 占位）→ 免费档置灰；「不落库」用后端直查断言；验证：新增 e2e spec 全绿（本机隔离栈）
- [ ] 6.2 提示词回归三层：**T1 确定性（进门禁）**＝把 `docs/volume-plan-prompt-experiment/out/*.txt` 转 fixtures，直接 import 生产的解析/校验函数，坏样本（三套同义／新造人名／卷末空／1 套／带围栏 JSON／纯文本降级）逐条断言；**T2 真模型不变量（手动/夜间 lane，非阻塞）**＝固定素材快照 ＋ 固定模型 ＋ 每模板 3 次，断言硬不变量（JSON 可解析、套数 2–3、侧重去重、卷末非空、字段上限、实体差集为空），任一次违例才判红，附原始输出；**T3 发版前人工评审集**＝补「主线很薄」「故意写歪的卷纲」两档样本；验证：T1 进 CI 毫秒级通过；T2 输出留档
- [ ] 6.3 全量门禁（逐条留输出）：后端 `python -m pytest tests/ -q` ＋ `ruff check .`；前端 `npx tsc --noEmit` ＋ `npx vitest run --coverage` ＋ `npm run build`；`openspec validate c-volume-plan-ai --strict`；`npm run design:lint` 与 `design:check`（若纳入像素门禁）；e2e 全量在本机隔离栈（CI 只跑每日定时兜底）；验证：各命令输出全绿
- [ ] 6.4 UI 变更纪律：把 `docs/design-c/drafts/ai-novel-c端-整书拆纲.html` 按仓库流程收编（原型入 `prototypes/` 并在 `ADJUSTMENTS.md` 登记，或明确本 change 不走 parity 基线并写明理由）；验证：设计门禁命令通过或登记条目可见
