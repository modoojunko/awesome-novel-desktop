## Context

角色 v2 已落真表四表＋单格 PATCH（`_PATCH_ROOTS = {name, aliases, role, persona}` ＋ `dossier.*`/`cog.*`，CAS 乐观锁）；右栏四行走 `POST /settings/ai/characters/{id}/draft|check`（`require_ai_access`＋`require_novel_model` 门控，`json_mode` 出稿、只返回建议不落库、采纳由前端逐格 PATCH）。四行 prompt 均以 `name=ch.name or "未命名"` 为输入，产不出名字。简介存 `story.yaml.synopsis`（自由文本，六段模板第一段「主角身份」）。readiness `_check_characters` 现为「存在任意一张卡」，readiness spec 的 characters 行仍是 v2 之前的六项旧口径——已与实现漂移。

## Goals / Non-Goals

- Goals：首次进角色页不再重复劳动；名字可由 AI 从简介提出；采纳路径零新增写面；门控/记账/只补空格纪律全保留；readiness 收紧且口径归位。
- Non-Goals：不做零点击静默 AI 调用；不改简介/题材/世界既有契约；不做关系、合并、撤销语义变更；不动 S端；不做 v1 角色 yaml 兼容（已退役）。

## Decisions

1. **bootstrap 是书级新端点，不塞进既有按卡端点**：`POST /settings/ai/characters/bootstrap`，body 可选 `character_id`（主角待立时带上，用于「只补空格」的空值基准）。放在 `settings/characters_ai.py` 新函数 `bootstrap_protagonist`，路由挂 `settings/ai_router.py`（与四行同处）。理由：四行端点语义是「对这张卡补」，bootstrap 是「书还没有主角时立一个」，按卡路由表达不了空态。
2. **后端只出稿，不建卡**：响应 `{name, aliases, persona, cells:[{path,value}], skipped}`。理由：建卡交给前端既有 `create`（含占位名/重名/主角唯一逻辑），复用即零新增写面；后端不引入「draft 顺带落库」的第二种写语义。
3. **采纳编排在前端，两条分支**：空态＝`create(name, "主角")` → 逐格 PATCH（persona、aliases、cells）；主角待立＝PATCH `name`（仅当现名空）＋persona（仅当空）＋cells。`rev` 沿用 `revRef` 递增惯例（照 `adoptSink`）。性别/年龄由后端 allowed 键集合硬挡（`DOSSIER_FILL_KEYS` 本就排除 author_only 的性别年龄；bootstrap 额外把 name/aliases/persona 走独立字段，不入 fills 白名单）。
4. **prompt 单文件** `prompts/settings_characters_bootstrap.prompt`：口径对齐 dossier/persona（禁编造、不得引用材料外名词、只输出 JSON、性别年龄禁令、某格无从下笔就不出现该键）；名称必答（简介里确实没有时给出贴合题材的建议名并在 `skipped` 说明依据）。parity 不涉前端镜像常量，无 parity 测试义务。
5. **前端入口两处、同一执行路径**：`CharacterManager.runAi("bootstrap")` 放宽「无卡即返回」守卫（bootstrap 允许无卡）；空态引导卡按钮与 `CharsAiRail` 条件行（`ctx?.role === "主角" && !ctx.name` 时插入第五行）都经 SettingsView `runCharsAi` 透传。草稿预览：卡在时复用 `AiSink`（`sink` 增加可选 `name/aliases` 展示行）；空态用独立 `bootstrapSink` 状态渲染同款预览卡。简介就绪判据＝`settingsStatus?.synopsis`，由 SettingsView 传 `introReady` prop 下沉。
6. **首卡默认主角**：`addCharacter` 改为 `create(projectId, "", list.length === 0 ? "主角" : "配角")`。不改后端默认值（API 层默认配角保持，避免影响其它调用方）。
7. **readiness 收紧**：`_check_characters` 查询加 `name` 非空且非 `\u0000` 占位（`func.trim(Character.name) != ""` ＋ `~Character.name.like("\u0000%")`）。docstring 同步钉死「readiness 只判内容非空；两档门禁在 confirm」。
8. **记账与失败口径照抄四行**：operation `settings_char_bootstrap[_fail]`、超时 502「AI 服务响应超时」、空产出 502「AI 没给出可用的内容」。

## Risks / Trade-offs

- readiness 收紧可能影响存量 e2e/测试里「建空卡即绿」的断言 → 实施时先 grep `readiness` 相关断言，随本 change 一并改（属语义修正，非回归）。
- AI 提名可能给出生僻名 → 名称始终走预览采纳，作者可改；prompt 要求贴合简介与题材、禁编造。
- 空态期间用户点「添加角色」与 bootstrap 并发 → 采纳时若列表已非空，走「主角待立」分支（按当前列表状态分支，而非发起时快照）。

## Migration / Rollout

无数据迁移。feature 无开关——出稿必过目，风险面即 AI 一次调用。

## Open Questions

（无——范围与两处入口已由用户 2026-09-14 拍板。）
