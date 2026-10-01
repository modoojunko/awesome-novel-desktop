## REMOVED Requirements

### Requirement: 章纲 AI 起草端点

**Reason**：功能与既有链路重复——卷纲「拆章」已按卷纲＋设定产出章纲四段直接排上，「补全缺失字段」按缺口清单补齐其余格子，整份起草的产出被两者覆盖；2026-10-01 用户拍板撤掉右栏「AI 起草」入口，端点随之退役（本地板单用户应用，无外部 API 消费方）。

**Migration**：起草章纲走「卷纲拆章」（volume-plan-ai / chapter-plan-ai）排上四段后，用保留的「补全缺失字段」（fill-gaps 端点，见本能力下方保留 requirement）补齐其余格子；既有端点调用方（C端 `draftOutline`）同批删除。

### Requirement: 草稿不落库

**Reason**：随「章纲 AI 起草端点」退役——起草动作不复存在，「草稿只返回不落库」的语义失去载体。

**Migration**：无。「补全缺失字段」沿用同款「产物不落库、前端表单承接后走既有保存链」语义（其 requirement 内已自带）。

### Requirement: 素材汇集

**Reason**：素材包只服务起草端点；「有现有章纲」判定（含拆章两格覆盖）的唯一消费方是起草的改写基底，随端点一并退役。拆章成果的防覆盖由章纲表单整表回传契约（chapter-data）继续保障，写正文素材含挑战/阶段两块的消费链路保留（chapter-data）。

**Migration**：无。前端覆盖确认判定 `ogHasDraftContent` 同批删除（唯一消费方是起草入口）。

### Requirement: 输出校验与兜底

**Reason**：草稿清洗/骨架校验只服务起草端点响应，随端点退役。

**Migration**：无。fill-gaps 保留自己的 `_sanitize_fills` 白名单收口与 502 语义。

### Requirement: 用量计量

**Reason**：`outline_draft`/`outline_draft_fail` 记账随起草调用退役；`outline_fill_gaps`/`outline_fill_gaps_fail` 记账保留。

**Migration**：无。token_log 既有 outline_draft 历史记录只读留存。
