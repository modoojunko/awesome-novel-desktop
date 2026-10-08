# tier-access Specification

## Purpose
TBD - created by archiving change 002-tier-free-bypass. Update Purpose after archive.

## Requirements

### Requirement: Tier bypass predicate

- The system SHALL provide `tier_bypass()` returning True exactly when the current user has no paid entitlement.
- A user has no paid entitlement when their tier is `none`, OR when `check_permission()` reports `allowed=False` (e.g. expired/invalid paid subscription, **trial without expiry in production——与过期同口径：allowed=False、免费基线，从而 tier_bypass=True 走免费旁路**).
- The predicate SHALL NOT be a bare string equality on tier alone; expired paid users SHALL be treated as free.
- `check_permission()` 的会员判定源 SHALL 为权益快照优先：完整快照下 `is_member` 由快照自证（features 非空或建书上限不限）、`project_limit` 取快照 `limits.max_projects`；无快照时按**档位目录缓存**兜底（目录亦无时按已知档兜底名单，须含 standard/trial/pro/max 及历史档位名 monthly/quarterly/yearly/lifetime）。
- **主判定分支 SHALL 为通用规则**：`none`/`free` 直接免费基线；**其余任何档名一律进入快照/目录判定**——档位枚举名单 SHALL NOT 作为快照存在时的准入闸（修正：原 FALLBACK_MEMBER_TIERS 名单在快照检查之前执行，导致名单外档位即使快照完整也被判免费）。
- 无快照且目录缓存命中时，SHALL 按目录行**合成 features**（该档标准权益），供 feature 门禁消费；SHALL NOT 只置 is_member 而不带 features。

#### Scenario: Free tier bypasses

- Given a local config with `tier: "none"`
- When tier_bypass is evaluated
- Then it is True

#### Scenario: Expired paid tier bypasses

- Given a local config with a paid tier whose `expires_at` is in the past
- When tier_bypass is evaluated
- Then it is True

#### Scenario: Active paid tier does not bypass

- Given a local config with an unexpired paid tier and a complete member snapshot
- When tier_bypass is evaluated
- Then it is False

#### Scenario: Normalized tier pro with snapshot is member

- Given 本地 tier 为 "pro" 且快照 features 非空、max_projects 为 null
- When check_permission is evaluated
- Then is_member is True and project_limit is None

#### Scenario: Normalized tier pro without snapshot falls back

- Given 本地 tier 为 "pro" 且无快照（旧服务端）
- When check_permission is evaluated
- Then is_member is True and project_limit is None

#### Scenario: Standard tier with snapshot is member（不再被名单拦截）

- Given 本地 tier 为 "standard" 且快照完整（features 含 ai-plan、max_projects=3）
- When check_permission is evaluated
- Then is_member is True、project_limit 为 3、tier_bypass 为 False

#### Scenario: Standard without snapshot synthesizes features from catalog

- Given 本地 tier 为 "standard"、无快照、档位目录缓存含 standard 行
- When check_permission is evaluated
- Then 判定按目录行合成 features（标准档 key 齐备），feature 门禁可正常消费

#### Scenario: Unknown tier name enters snapshot path

- Given 本地 tier 为一个新增档位键（代码不认识）且快照完整
- When check_permission is evaluated
- Then 判定按快照走（SHALL NOT 因名单不含该键而落免费基线）

#### Scenario: Trial without expiry is free in production

- Given tier 为 "trial"、expires_at 为空、且未设置开发/测试宽限环境变量
- When check_permission is evaluated
- Then allowed 为 False（与过期同口径）、is_member 为 False、project_limit 为 1，tier_bypass 为 True（走免费旁路）

### Requirement: Tier-or-gate wrapper

- The system SHALL provide `tier_or_gate(db, project, gate_fn, *args)` that delegates to `gate_fn(*args)` when `tier_bypass()` is False (PRO path).
- When `tier_bypass()` is True, it SHALL return `GateResult(valid=True, warnings=[], hard_block=False)` WITHOUT invoking `gate_fn`.
- The PRO path SHALL return the gate function's `GateResult` unchanged (hard_block semantics preserved).

#### Scenario: Free bypasses gate without invoking it

- Given tier is none and a gate function that records invocations
- When tier_or_gate is called
- Then the gate function is not invoked and the result is valid with no warnings

#### Scenario: PRO runs the gate

- Given an unexpired paid member with a member snapshot
- When tier_or_gate is called
- Then the gate function runs and its GateResult is returned unchanged

### Requirement: Tier-aware phase transition

- The system SHALL provide `tier_phase_transition(project, new_phase)`.
- When `tier_bypass()` is True, the phase transition SHALL be forced: `current_phase` is set to `new_phase` WITHOUT validating `can_transition` (idempotent advance per O3).
- When `tier_bypass()` is False, it SHALL behave exactly like `update_phase` (validate `can_transition`, raise ValueError on illegal jump).

#### Scenario: Free archive does not raise
- Given a new novel whose current_phase is "settings" (no outline/prompt/write traversed)
- When archive calls tier_phase_transition(project, "archive") under free tier
- Then current_phase becomes "archive" and no ValueError is raised (fixes N9 500)

#### Scenario: PRO illegal jump still raises
- Given an unexpired paid tier and a novel whose current_phase is "settings"
- When tier_phase_transition(project, "archive") is called
- Then a ValueError is raised

### Requirement: Gate access points honor tier bypass

- The following access points SHALL route their gates through `tier_or_gate` and phase changes through `tier_phase_transition`:
  - `POST /volumes` (create_volume): `gate_settings_complete` via tier_or_gate.
  - `POST /chapters/{ref}/confirm` (confirm_chapter): `gate_chapter_ready` via tier_or_gate.
  - `POST /workflow/transition`: the settings/chapter-ready/prompts-exist hard gates via tier_or_gate; the phase change via tier_phase_transition.
  - `POST /chapters/{ref}/archive`: phase change via tier_phase_transition.
- Under free tier, the above SHALL succeed without the prerequisite files (memo/segments/prompts).

#### Scenario: Free confirms a sparse chapter
- Given a chapter with empty memo/segments under free tier
- When confirm_chapter is called
- Then it returns 200 and the chapter status becomes "confirmed"

#### Scenario: Free transitions without prompts
- Given a project under free tier with no prompt files
- When workflow transition targets "write"
- Then it returns 200 and the phase advances

### Requirement: Free phase-status reports bypass

- `GET /workflow/phase-status` under free tier SHALL return `tier_bypass: true` and all six phases `complete` (no phase pestering UI, N14).
- Under PRO, phase-status SHALL retain current behavior.

#### Scenario: Free phase-status is all-complete
- Given a free-tier project with an empty outline
- When phase-status is fetched
- Then response has tier_bypass true and every phase is "complete"

### Requirement: Archive is free

- 归档动作本身 SHALL NOT 挂会员门：`POST` 归档受理、`GET /archives`、`GET /archives/{filename}` 对免费档可用。
- 本书未配置模型时归档 SHALL 即刻生效（archived、无章档），摘要降级语义不变（正文前 200 字），SHALL NOT 500。
- 本书已配置模型时，归档 SHALL 以四域提取成功为生效前置（受理→后台提取→成功收口，见 chapter-dossier）；该提取调用 SHALL NOT 挂会员门（免费档配置模型即可用），失败按章档能力的重试/逃生阀语义处理。
- **归档收尾提案（伏笔登记/世界要素）SHALL 全档可用**：`/reconcile` 族端点与收尾触发闸 SHALL NOT 挂会员门（原 `ai_access_granted` 门退役），改挂模型就绪判定（`require_novel_model` 语义——未配模型即跳过收尾任务，不报错）。前端收尾面板 SHALL 对免费档渲染（原 isFree 整棵不渲染退役）。
- The archive gate SHALL check `.md` archive files (fixes B4), degrading to a file scan without 500 when the DB is unavailable.

#### Scenario: Free archive without API key

- Given a free-tier user with no API Key and a chapter with ≥100 chars prose
- When the chapter is archived
- Then the request accepts and archives immediately (no dossier rows), the summary is the first 200 chars, and no 500 is raised

#### Scenario: Free archive with configured model

- Given a free-tier user who has configured a model
- When the chapter is archived and extraction succeeds
- Then the chapter is archived and dossier rows are produced, without any membership gate

#### Scenario: Free reconcile proposals

- Given a free-tier user who has configured a model
- When the chapter is archived and 收尾提案生成
- Then reconcile 面板对免费档可见可确认（accept/reject/run 不挂会员门），未配模型时收尾任务静默跳过

#### Scenario: Archive list readable for free

- Given a free-tier user
- When GET /archives and GET /archives/{filename} are called
- Then both return 200

### Requirement: AI settings field generation gated

- `POST /settings/ai/{stype}/{field}` SHALL be gated by feature key `settings-ai-fields`（标准档起发放；`require_ai_access` 的 feature 化形态）。
- Calling it without an API Key under free/expired tier SHALL return 403/503 (gate), not 500 or bypass；标准及以上档位命中该 key 时放行。

#### Scenario: Free field generation rejected

- Given a free-tier user with no API Key
- When POST /settings/ai/world/tech_level is called
- Then the response is 403 (or 503), not 500 and not a generated value

#### Scenario: Standard field generation allowed

- Given a standard-tier user whose snapshot contains "settings-ai-fields" and an active API Key
- When POST /settings/ai/{stype}/{field} is called with valid premise
- Then it proceeds（标准档即放行，无需 PRO）

#### Scenario: PRO field generation unaffected

- Given a user with an active API Key and paid entitlement
- When POST /settings/ai/{stype}/{field} is called with valid premise
- Then it proceeds as before

### Requirement: 端点门禁对拍守卫

门禁对拍测试 SHALL 真实枚举全部已注册路由上的 feature key 标注并双向断言，SHALL NOT 因框架路由表的懒加载包装而空扫通过：

- 扫描 SHALL 穿透框架懒路由包装（starlette ≥1.6 的 `_IncludedRouter` 等形态），枚举结果 MUST 非空（现状仓库 ≥40 个挂 key 端点，随功能增长只增不减）；
- 已挂 key 的端点 SHALL 同时挂载**与其 key 相称**的 AI 门禁——key 标注不得成为无门死标注，也不得错挂门型。两种门分工：`require_ai_access`＝会员＋档位＋已配写作大模型 Key，为 LLM 类 key 的唯一合法门；`require_tier_access`＝会员＋档位（Key 由作者自持），**仅**白名单 key（`ai-detect`／`prompt-panel`）可用——白名单外的 key 若只剩键自持门即判失败（防「生成类端点错挂键自持门」把未配模型的作者放行到业务深处）；
- 端点声明的 key MUST ∈ 门禁 key 词汇表（含 AI 的档位 key 全集，免费键除外）；
- 关键档位 key（`chapter-review`、`style-quant`、`ai-plot`、`ai-polish`、`ai-detect`、`ai-generate`、`prompt-panel`、`ai-plan`、`settings-ai-fields`、`style-suggest`）SHALL 各有至少一个真实端点消费点。

#### Scenario: 扫描穿透懒路由包装

- **GIVEN** 框架以懒包装形态暴露路由表（顶层非可直接识别的端点对象）
- **WHEN** 门禁对拍测试运行
- **THEN** 全部已挂 key 的端点被枚举（结果非空），并与登记消费点清单一致——SHALL NOT 空扫通过

#### Scenario: 死标注被拒

- **GIVEN** 某端点挂了 feature key 但未挂任一 AI 门依赖
- **WHEN** 门禁对拍测试运行
- **THEN** 测试失败并点名该端点，提示补相称的门或移除标注

#### Scenario: 错挂门型被拒

- **GIVEN** 某 LLM 类 key（如 `ai-generate`）的端点只挂了 `require_tier_access`（或反之：白名单外的 key 用键自持门）
- **WHEN** 门禁对拍测试运行
- **THEN** 测试失败并点名该端点与 key——未配写作大模型的作者 SHALL NOT 因此被放行到业务深处才失败

#### Scenario: 白名单自身失效被拒

- **GIVEN** 键自持门白名单为空、或含不在门禁词汇表内的 key
- **WHEN** 门禁对拍测试运行
- **THEN** 测试失败（守卫不得退化成「任何门都算」）

#### Scenario: 拼错或未登记 key 被拒

- **GIVEN** 某端点声明的 key 不在门禁词汇表内
- **WHEN** 门禁对拍测试运行
- **THEN** 测试失败并点名该端点与 key（防「快照发了 key、端点没挂门」与拼错 key 静默开洞）

### Requirement: 导入回填 AI 步骤门禁

导入回填流程中真调 AI 的两个步骤（`POST /api/novels/{id}/ai-backfill/step1`、`step2`）SHALL 按 feature key `ai-plan` 门禁（标准档起发放）；纯状态读写的 `status`/`confirm` SHALL NOT 挂会员门。

#### Scenario: 免费档调用被拒

- **GIVEN** 免费档用户
- **WHEN** `POST /ai-backfill/step1` 或 `step2` 被调用
- **THEN** 返回 403（`member_required`，带升级出口语义），SHALL NOT 执行任何 AI 提取

#### Scenario: 标准档及以上放行

- **GIVEN** 权益快照含 `ai-plan` 的档位（标准/PRO/MAX/trial）且已配模型
- **WHEN** `POST /ai-backfill/step1` 或 `step2` 被调用
- **THEN** 过档位门，行为与既有回填流程一致（模型未就绪按既有 503 引导口径）

#### Scenario: 状态端点不设门

- **GIVEN** 任意档位
- **WHEN** `GET /ai-backfill/status` 或 `PUT /ai-backfill/confirm` 被调用
- **THEN** 不因档位被拦截（仅既有登录与项目归属校验）

### Requirement: 按 feature key 的 AI 门禁

全部 AI 调用端点 SHALL 声明所需 feature key 并按「key ∈ 权益快照 features」判定（守门函数保持模块级单符号，key 经路由装饰器元数据标注；SHALL NOT 使用按端点生成新依赖对象的工厂形态——保留测试 dependency_overrides 兼容）。端点→key 的归类以词汇表为准（tier-gating），撤门项除外。

403 契约双层：非会员命中任意 AI 门 → `{"reason":"member_required", message}`（兼容保留）；是会员但档位不含该 key → `{"reason":"feature_required", "feature":<key>, "tier_required":<standard|pro|max>, message}`。`ai_state` 下发 SHALL 透传 features 数组供前端分档。

#### Scenario: 免费命中任意 AI 门

- Given a free-tier user
- When POST /write（ai-generate 门）被调用
- Then 403 reason=member_required（升级引导语义不变）

#### Scenario: 标准档命中 PRO 门

- Given a standard-tier user（features 含 ai-plan、不含 ai-generate）
- When POST /write/continue 被调用
- Then 403 reason=feature_required、feature=ai-generate、tier_required=pro

#### Scenario: 标准档过流程门

- Given a standard-tier user
- When POST /volumes/ai/options（ai-plan 门）被调用
- Then 放行（标准档即享流程 AI）

#### Scenario: 剧情推演仅 MAX

- Given a pro-tier user（features 不含 ai-plot）
- When POST /chapters/{ref}/simulate 被调用
- Then 403 reason=feature_required、tier_required=max

#### Scenario: 朱雀后端真门（留 PRO，2026-10-05 拍板）

- Given a standard-tier user（features 不含 ai-detect）
- When POST /zhuque-check 或 zhuque config/test 端点被调用
- Then 403 feature_required（tier_required=pro）；pro 及以上与 trial 放行

#### Scenario: 现状免费只读收进标准

- Given a free-tier user
- When 卷体检（ai-plan）/章自检短评（chapter-review）/人物盘点（ai-plan）被调用
- Then 403 member_required（原「免费只读例外」上移至标准档）

#### Scenario: 门禁映射有对拍守卫

- When CI 运行端点 key 对拍测试
- Then 每个挂 AI 门的端点声明的 key ∈ features.ts 词汇表（防「快照发了 key、端点没挂门」与拼错 key 静默开洞）
