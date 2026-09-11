# 世界设定 v2：五格改版 + 契约 v2 + lore-keeping

## Why

世界设定是创建期第 ③ 步，但现行面板还是旧「地理/政治/规则」10 字段表单 + 字段级 AI 弹窗：字段预设死板（史诗向预设强加给所有题材）、AI 只能按字段问答、写章注入会把设定截断、没有任何「随写作更新」的机制（lore-keeping 全缺）。产品侧已完成多轮收敛的前端评审稿（docs/design-c/drafts/world-setting-draft.html v2.7，前端已确认无意见）与后端架构规范（docs/design-c/drafts/world-setting-backend-architecture.md，含三方工程评审 P0-P2 全部结论），本 change 将其落地。

## What Changes

- **全新实现（不参考旧实现）**：世界设定面板、AI 端点与提示词按设计文档（前端评审稿 v2.7 + 后端架构规范）从零新建——不读取、不继承、不改造旧「地理/政治/规则」实现的任何代码路径；旧实现文件在本 change 内删除（清理清单见 tasks §9）。唯一的旧系统接口是**数据迁移**：老书已填的世界设定按映射表一次性转入新格式（保数据、不保代码）。
- **前端**：WorldSettingForm 重构为「五格 + 06 折叠组」——01 世界舞台（一段话，舞台底色继承题材目录）、02 力量体系（现实向开关可整格关闭）、03 力量的代价、04 势力（名字+一句话行）、05 世界铁律（约束类名目条目）；06 更多世界细节＝名目条目折叠组（历史与旧账独立区绑定 history 字段 + 自由名目 key:value）。右栏 AI 五行（采纳 · 覆盖 + 脚部回执一步撤销 + 每行最近 5 次生成历史）+ 一致性体检（简介 × 题材 × 世界三方对照，三态）。字段级「AI 帮我填」弹窗（AISuggestionModal 在世界页的用法）退役。
- **后端**：settings/world 契约 v2（`{ no_power, stage, power, cost, history:[{key,value,origin?}], factions:[{name,note}], constraints:[{key,value}], extra:[{key,value,origin?}] }`，**BREAKING**：替换旧 geography/politics/rules 十字段）；`WorldIn` 契约校验；读边界归一化 + `_legacy` 子树回滚（旧十字段按映射表搬入）；`readiness._check_world` 按新判据重写；`inject_world_setting` v2（铁律进红线块、整条截断）；AI 五行端点（stage/power/cost/factions）+ 一致性体检端点（注册在通用字段路由前、简介/题材缺失降级不 400）；`ai_prefill` 世界预填退役；lore-keeping 端点（lore-suggest stateless / lore-apply 人工确认入账，origin 幂等）。
- **测试**：后端 pytest（契约校验/迁移 roundtrip/注入渲染/no_power/体检归一化/lore 幂等）；前端 vitest；界面测试（playwright e2e）：旧世界 3 用例重写 + 新增 world-ai 全链路用例（AI 采纳/回执撤销/历史切回/体检/现实向开关/免费锁定）。

## Capabilities

### New Capabilities
- `world-settings`: 世界设定面板（五格 + 条目化 06 + 契约 v2 + 右栏 AI 五行 + 一致性体检 + lore-keeping 回写与注入）

### Modified Capabilities
- `readiness`: world 判据从「旧十字段子字段非空 ≥4」重写为「stage/power/cost 任一非空或任一条目有值」（intro-genre-settings 内无世界面板专属 requirement——世界面板行为由新 capability `world-settings` 全量承接；其左树顺序、切面板清回执等既有 requirement 不变）

## Impact

- **前端**：`client/frontend/src/components/novel/settings/WorldSettingForm.tsx`（重写）、`workbench/SettingsView.tsx`（world 分支接 AiWriterAssistant + onReceiptChange、DESCS.world 文案）、新增 `KvListEditor` 组件；e2e `settings-forms.spec.ts` 世界 3 用例重写、新增 `world-settings.spec.ts`
- **后端**：`client/backend/settings/router.py`、`settings/ai_router.py`（world 生成行 + 一致性体检 + lore 两端点）、`settings/world_model.py`（新：契约/归一化/渲染）、`workflow/readiness.py`、`prompt/context.py`（inject_world_setting v2）、`write/chapter_writer.py`（铁律红线块）、`ai_prefill.py`（世界预填退役）、`prompts/settings_world.prompt`（重写）+ 4 个新行模板、`archive/`（归档响应附 lore_suggestions）
- **API**：`PUT/GET /novels/{id}/settings/world`（v2 shape，**BREAKING**）、`POST /settings/ai/world/{stage|power|cost|factions}`、`POST /settings/ai/world/check`、`POST /settings/ai/world/lore-suggest`、`POST /settings/ai/world/lore-apply`
- **数据**：project_settings KV 值形状升级（零 DDL；读边界归一化 + `_legacy` 子树留一个版本周期回滚）
- **用户可见行为**：世界面板五格 + 一致性体检 + 采纳回执/历史；写章 prompt 的世界块与红线块格式变化（对作家透明，对生成质量是修复）

## Design Impact

- 受影响端：**C端**（S端无涉及）
- 受影响屏/弹层：工作台 → 设定视图 → 左树「世界」面板（含右栏 AI 助手卡）；无新弹层（AI 结果就地落格下、回执条在面板脚部）
- 对象状态（对照状态语言总表）：面板徽标三态（未填/已填/已确认）、AI 门控四态（ready/member_required/no_key/missing_model，复用 AiWriterAssistant）、体检三态（达标=ok / 风险=warn / 缺失=err）、生成中占位（aria-busy）、回执条（ok 语气 + 撤销动作）
- 共享段：**不触碰**两端共享 base.css 令牌与基础组件类；新增组件（KvListEditor）仅 C端
- 原型先行：已完成——设计侧会话产出 `docs/design-c/drafts/world-setting-draft.html`（v2.7，交互全演示）+ `world-setting-backend-architecture.md`（后端架构规范，含 D1-D12 拍板与迁移映射表）；实现侧按稿与规范自查
- 文案：按钮动词（采纳 · 覆盖/重试/存草稿/确认完成/加一条）、无内部术语、体检缺失项的补救句带可点出口（「去补简介」等跳转）；语气词仅 info/ok/warn/err
