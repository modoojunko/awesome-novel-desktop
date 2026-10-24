## Context

v0.39 封面/头像生成链（c-cover-avatar＋c-image-generation）把「种子」做成了用户可填设置。实勘结论：种子只影响可复现性，而 `_derive_seed(kind, id)` 已提供同书恒定的确定性种子；「换个构图」的正确入口是改画面描述/画风（改任一都会改 prompt/hash），手填种子没有用户故事。同时封面 prompt 的书级素材面太窄：只读 `story.yaml` 的 genre/sub_genre＋`novel_genre.core_promise`＋世界舞台第一句；主线 `story_arc.fullstory`（建书/主线面板已沉淀，≤2000 字）与一句话故事 `promise_note` 未参与——封面画面与书脱节。

## Goals / Non-Goals

- Goals：界面零困惑（种子消失）；封面画面吃满书级白名单素材（选题/主线/世界观）；用户始终掌控最终画面（草稿可改）。
- Non-Goals：不做自动提取（生成时偷偷调 LLM 隐藏计费）；不做提取结果缓存列；不改 `prompt_builder` 的组装模板（`PROMPT_TEMPLATE_VERSION` 不 bump）；头像描述不做 AI 提取（角色卡本身即素材，另行立项）。

## Decisions

### D1. 提取走提示词仓模板，AI 草稿落「画面描述」输入框（先行编辑流）

沿用 `settings_characters_persona` 的成熟范式：`load_layers` → `prompt.format` → `json_mode=True` → 严格 `_parse_json`（坏 JSON 502 可重试，不自动重试）。产出 `{"scene": "80-140字"}`，**只填前端 textarea**，用户点「保存设置」才走既有 PATCH 落库——与「起草角色提示词先行编辑流」同构：AI 出稿、用户可改、按最终稿执行。代价：提取与保存是两步；收益：零新状态、零缓存失效问题、计费可见（点按钮才调）。

### D2. 门控：`@ai_feature("image-generate")` ＋ `require_tier_access` ＋ 端点内直调 `ensure_novel_model_ready`

提取本质是 AI 生成链路的前置（要花钱调文本模型），与生成同门（PRO/试用以上）；路由路径参数是 `novel_id` 而非 `project_id`，DI 版 `require_novel_model` 绑不上，按其 docstring 认可的形态在端点内直调判定核心（兼做属主校验 404）。未配书模型 → 503 `reason` 与前端 `ai_state` 同枚举。

### D3. 模板硬约束：无字、剪影、单焦点、无专名、不剧透

封面底图必须无字（书名由程序叠加，negative 已禁文字载体）；人物只作剪影/背影/远景——画图模型不知道主角的长相，清晰面部特写必错；输出禁书名/角色名/势力名（用通称），防招牌化与剧透。`prompt_builder` 的 `_redact`（书名→此地、角色名→人物）在组装时仍兜底一道——模板约束管生成面，脱敏管兜底面，双保险不互替。

### D4. 种子退役走「列删除＋交集搬行」，迁移样本入册

本项目每版新建库文件、无 DDL 迁移；carry 引擎按「目标列 ∩ 源列」搬行，删列天然安全（源多列进 `skipped_src`）。按 c-legacy-drill-gate 纪律把 v0.39 形态（`book_image_settings.cover_seed`/`character_image_settings.seed` 在册）补进 `legacy_samples.py`（只增不减）：重放断言设置行零损失、prompt 原样、新 schema 无种子列、源库零接触。备份 v7 manifest 同步去键；旧包多键导入静默忽略（importer 按 key 显式取值，多余键天然无视）。

### D5. 前端「画面描述」字段从 label 改 div

「AI 提取」按钮不能嵌在 `<label>` 里：一是 label 激活行为会把点击转发给 textarea，二是 dom-accessibility-api 会把按钮的可访问名算成整个 label 文本，`getByRole(name)` 失配（实测）。改 `div.img-field`＋textarea `aria-label`，按钮独立可点。

## Risks / Trade-offs

- 提示词包未发布前，线上点「AI 提取」会得到 503 `prompts_missing`（既有全局四态卡兜底）——发布顺序：C端合入先，提示词包随下批发布补齐；dev/demo 栈 `PROMPT_PACK_DEV_DIR` 立即可用。
- 主线全文（≤2000 字，截 1200）进 LLM 输入：与 arc_draft/characters_cog 同水位，均为用户自有数据、本地后端直连自备 key，无新增泄露面。
- 老客户端升级到新版后：其本地旧库由 carry 迁入新 schema（种子值弃）；其后老客户端降级回旧版会因 fingerprint 漂移走 mismatch 重定位（既有行为，与历次删列同）。

## Open Questions

- 无——三拍板（头像种子一并删/PRO 门控/按钮手动触发）已在立项时确认。
