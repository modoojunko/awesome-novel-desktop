# world-setting-v2 任务清单

> 依据：前端评审稿 `docs/design-c/drafts/world-setting-draft.html`（v2.7）+ 后端架构规范 `docs/design-c/drafts/world-setting-backend-architecture.md`（D1-D12）。测试任务（后端 pytest / 前端 vitest / 界面 e2e）为一等任务，随各组实现同行，不后置。

## 1. 后端·契约 v2 与迁移（T1-T3）

- [x] 1.1 新建 `settings/world_model.py`：WorldIn 校验（stage/power/cost ≤300 字；kv value ≤200、key ≤20；factions ≤6、constraints ≤10、extra ≤50、history ≤100；拒绝重复 key/空 key/控制字符，400 指明字段）——验证：pytest 契约校验用例（超长/超条数/重复/空 key/控制字符各一例）
- [x] 1.2 `normalize_world()` 读边界归一化：识别 v1 十字段按映射表搬入、`_legacy` 存原文、GET 剥 `_legacy`、缺省补 v2 空形状——验证：迁移 roundtrip 测试（旧十字段原文可从归一化结果+映射复原，断言不丢字）
- [x] 1.3 `PUT/GET /settings/world` 接入 WorldIn 与归一化（PUT 写 v2+`_legacy`，GET 剥 `_legacy`）——验证：pytest 读写用例 + 旧书 GET 归一化用例
- [x] 1.4 迁移演练：本地构造旧十字段 KB → 走 GET/PUT/确认全流程 → 断言原文在 `_legacy` 且面板可确认——验证：演练脚本或 e2e 一条（删库救回演练同规格）

## 2. 后端·readiness 与注入消费方（T4-T6）

- [x] 2.1 `workflow/readiness.py::_check_world` 重写：stage/power/cost 任一非空或任一条目 value 非空即 pass（legacy 先归一化再判）——验证：pytest 重写 readiness 世界用例（旧 shape 归一化后不误报）
- [x] 2.2 `prompt/context.py::inject_world_setting` v2 渲染（舞台/力量/代价段落 + 势力/历史/extra 摘要；no_power 跳过 power/cost）——验证：pytest v2 渲染快照用例
- [x] 2.3 `write/chapter_writer.py` 铁律红线块：constraints 逐条完整进红线区（独立预算 ≤300 字）、世界块不含铁律、截断改整条从略——验证：pytest「10 条铁律全量出现在红线区」用例 + 600 字预算用例改造
- [x] 2.4 `ai_prefill` 世界预填退役（移除 novels/service.py 调用点）+ `prompts/settings_world.prompt` 重写为五问模板——验证：建书流程回归（无旧键写入）+ pytest ai_prefill 用例更新
- [x] 2.5 `story/engine.py` 最小修复：terrain 改读 stage——验证：pytest story engine 用例更新

## 3. 后端·AI 五行与一致性体检（T7-T8）

- [x] 3.1 ~~字段级四端点~~（实现演进）→ 通用起草端点 `POST /settings/ai/world/draft`（topic+shape: text/kv/faction；后端不枚举主题，任何世界要素可起草；`world_draft_topic.prompt` 动态拼 topic 口径行；题材锚走运行时 `_theme_anchor`；现实向书拒绝力量主题 400）——验证：pytest draft shape 矩阵 + no_power 400 + 已有世界设定进 prompt 断言（评审回归钉）
- [x] 3.2 出参归一化 `_normalize_draft_value`（text clamp ≤300=PARAGRAPH_MAX 防采纳后保存 400；kv → key≤20/value≤200 ≤10 条、空 key 回退；faction → name/note ≤6 条）+ topic 消毒（去控制字符与花括号）+ 计量 `settings_world_draft_{topic}`——验证：pytest 归一化与消毒用例
- [x] 3.3 一致性体检端点 `POST /settings/ai/world/check`（注册在通配字段路由**之前**）：七项白名单（CHECK_ITEMS_POWER/REAL 同源）、`_judge_chat` json_mode、三态白名单归一 + 名称归一匹配（×/x/空格写岔不丢项）、简介/题材缺失降级（D7 拍板：缺输入行直接置 miss 不烧 AI 调用，简介+题材全空→整次免调用；响应带 degraded_reasons）——验证：pytest 体检归一化 + 降级矩阵 + 双缺失免调用 + 名称归一回归用例

## 4. 后端·lore-keeping（T9）

- [x] 4.1 `POST /settings/ai/world/lore-suggest`（stateless）+ `archive_chapter` 响应附 `lore_suggestions`（两路归一化共用 `world_model.parse_lore_suggestions`，白名单同源 SET_NAMES）：输入=章节归档内容 + 当前 world 摘要，输出 `[{key,value,set}]` 建议集（不落库），覆盖 history/extra/factions/constraints——验证：pytest 建议生成与失败静默降级用例
- [x] 4.2 `POST /settings/ai/world/lore-apply`：人工确认写入，`(key, origin)` 幂等合并（factions 按 name），返回整包归一化 world——验证：pytest 幂等用例（同 origin 重复 apply 不重复追加）+ 丢弃不入账用例
- [x] 4.3 lore 与 `ai_summary` 偏好解耦——验证：pytest 关摘要时 lore-suggest 仍可用的用例

## 5. 前端·五格面板与 KvListEditor

- [x] 5.1 新建 `KvListEditor` 组件（受控 rows + suggests(button.cap) + key/value 占位 + maxItems + 删除）；04 `FactionRows`（name+note 行、4 行软提示）——验证：vitest 组件用例（增/删/建议置灰/恢复/上限禁增）
- [x] 5.2 新建世界面板组件（全新文件，按评审稿从零实现；不读旧 WorldSettingForm 代码）：五格布局（01 一段话/02 单框/03 单框/04 势力行/05 铁律条目/06 折叠组=历史独立区+自由名目）、inherit-line 题材继承（含未确认降级态）、契约 v2 读写接 `normalize`——验证：vitest 表单读写与加载归一化用例
- [x] 5.3 现实向开关状态机：no_power 入 payload 记 dirty；收起 02 主体/03 整格/右栏两行为同一派生态；不清空文本——验证：vitest 开关联动用例
- [x] 5.4 徽标/脚部/文案对齐：徽标三态走服务端 settingsStatus、`DESCS.world` 新文案、lock-note/回写说明文案、面板脚部 存草稿+确认完成——验证：vitest 徽标三态用例
- [x] 5.5 界面规范自查：oklch token、无 emoji、SVG 走 icons.tsx 注册表、建议名目 button.cap、focus 态、design:lint——验证：`npm run design:lint` 全绿

## 6. 前端·右栏 AI 五行与回执/历史

- [x] 6.1 `SettingsView` world 分支接 `AiWriterAssistant` 五行（输入来源文案按稿）+ `runWorldAi` 句柄 + `onReceiptChange` 接线 + `DESCS`/rail 注释更新——验证：vitest world 分支渲染用例
- [x] 6.2 AI 五行结果落格下 AiSink：「采纳 · 覆盖」写回 + 面板脚部回执（差量文案）+ 一步撤销（ref 取即时值）+ 生成历史最近 5 次可切回——验证：vitest 采纳/撤销/切回用例
- [x] 6.3 生成中占位（aria-busy）+ 在途防抖（连点一次）+ 门控四态分流（no_key→模型配置 / missing_model→本书模型 / member_required 锁定提示）——验证：vitest 门控与防抖用例
- [x] 6.4 窄屏格头「AI 帮填」快捷钮与右栏同入口（ref 转发，不绕 guard）——验证：vitest 快捷钮转发用例

## 7. 界面测试（playwright e2e）

- [x] 7.1 重写 `settings-forms.spec.ts` 世界 3 用例（旧十字段/阈值口径 → 五格口径：填写/徽标三态/确认即前进/空确认停留）——验证：本地 docker 栈 e2e 通过
- [x] 7.2 新增 `world-settings.spec.ts`（全 mock，照 genre-ai-settings 模式）：AI 五行采纳/回执撤销/历史切回/体检三态与降级/现实向开关联动/免费锁定拦截——验证：本地 e2e 全绿
- [x] 7.3 lore-apply 界面用例（~~e2e~~ 收敛为 vitest：暂存写入 → 世界页 06 挂载即出现建议条目 → 采纳入账（先落库再入账）→ 清掉本条）——验证：WorldSettingPanel.test.tsx「lore 建议」用例
- [x] 7.4 密闭性验证：停外部依赖复跑本 spec，确认全 mock 无外呼——验证：e2e 复跑绿

## 9. 旧实现删除与替换验证

> 9.1/9.2 与 §5.2/§6.1 同一提交落地（新面板接线即删旧文件，不后置）；9.3 为收尾核对。

- [x] 9.1 删除旧世界面板文件 `settings/WorldSettingForm.tsx` 及其全部引用（SettingsView 改接 5.2 新组件）——验证：全局 grep 无 `WorldSettingForm`/`geography`/`politics.`/`rules.world` 残留，tsc/vitest 绿
- [x] 9.2 移除世界页字段级 AI 弹窗路径与旧 AI 字段集（scenes/climate/limits/rule/factions/social/cost/world/society/personal）——验证：前后端 grep 无旧字段集残留，pytest/audit 用例更新后绿
- [x] 9.3 删除确认：旧 prompt 旧版与 ai_prefill 世界预填已随 §2.4 移除——验证：grep 无 `prefill_world_setting`/`settings_world`（旧版）残留

## 8. 收尾验证

- [x] 8.1 后端全量 pytest + ruff 全绿（含新增契约/迁移/注入/体检/lore 用例）
- [x] 8.2 前端 vitest 全绿 + tsc --noEmit + design:lint + design:check
- [x] 8.3 本地 docker 栈全量 e2e（含重写的世界用例与新增 world spec）
- [x] 8.4 存量旧书演练：旧十字段 KV 书打开世界页→填写→确认→归档→写一章，验证迁移/注入/lore 全链
