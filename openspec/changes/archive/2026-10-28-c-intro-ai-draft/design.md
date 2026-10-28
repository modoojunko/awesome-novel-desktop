# c-intro-ai-draft — Design

## Context

简介右栏 AI 三件套共用 `POST /settings/ai/intro/{action}` 一个端点（`ai_router.py` intro_ai），三种动作共享门控（`@ai_feature("settings-ai-fields")`）、模型解析（`get_ai_client_for_novel`）、记账与失败留痕。前端右栏行（introAiRows）→ `introRef.runAi(action)` → `runRequest` 出卡，确认卡交互（D9 缓存/D14 占位/回执撤销）按 action 分支渲染。题材上下文的现成取数路径在 `generate_field` 的 genre 分支（story.yaml 题材目录＋`_theme_anchor`＋候选池）。

## Goals / Non-Goals

**Goals**
- 空简介落地即可一键起草第一版；题材五格已填项必须用上。
- 采纳/撤销/重掷与三件套同一套确认卡交互，零新增交互面。
- 提示词产出按六段骨架组织（可直接过体检）。

**Non-Goals**
- 不做多候选批量出稿（单稿＋「换一个」重掷，沿用 D9）。
- 不动三件套的注入口径（仍不注入题材）与守卫（体检要内容、补缺失要先体检）。
- 不动权益表（起草与三件套同 key `settings-ai-fields`，标准档起）。

## Decisions

**D1. 端点内加第 4 个 action，不新开端点。**
`INTRO_ACTIONS` 加 `"draft"`、`_INTRO_PROMPTS` 加映射；门控/模型解析/记账/失败留痕全部由现 handler 兜底，路由注册顺序不变（intro 专用路由本就在 `/ai/{stype}/{field}` 通配之前）。替代案（独立 `/ai/intro-draft` 路由）被否：同族能力分家后门控与记账要再抄一遍，无收益。

**D2. 起草注入题材、不吃已有简介。**
题材上下文＝story.yaml 的 genre/sub_genre（`_theme_anchor` 出解读与案例当风格锚）＋`get_novel_genre` 五格：已填的注入原文（forbidden/battlefield 候选 id 经 VOCAB_PRESETS 译回标签——起草只要模型读懂语义，不需要它回 id），未填的标「（作者还没填）」；题材本身未定时标「（作者还没填）」，模板指示凭书名写通用盘。请求体的 `content` 在 draft 分支不作为输入——从零起草吃题材，已有成稿的加工是润色的职责，两不混。

**D3. 前端复用润色的采纳形态，单稿＋重掷。**
返回 `{"original","draft","act":"replace"}`；出卡 label「AI 起草稿 · 采纳才写入」，original 非空时附原稿对照行；adopt＝整段替换＋recordChange 回执一步撤销（照抄 polish 采纳块）。不做多候选：一次调用一条稿，「换一个」重掷（D9 缓存语义照旧——重开同一行展示缓存、换一个才重新生成）。替代案（一次出 2-3 条挑选）被否：调用成本×3 且与既有交互不一致。

**D4. 提示词仓新模板 `settings_intro_draft`，需发提示词包。**
六段骨架与 `lib/introTemplate.ts`/体检白名单逐字同口径（产出直接可过体检）；硬性规则与词句禁忌沿用 polish 模板体系（钩子开头/短句/≤500 字/不写死结局）。本地与测试走 `PROMPT_PACK_DEV_DIR` 不依赖发包；合入后随发布链发一版（新模板 key，min_client 不 bump——后端消费模板，老客户端无感）。

**D5. spec 改名走 REMOVE+ADD。**
「简介 AI 写作助手（三能力，Pro）」→「（四能力，标准档起）」：Requirement 改名按判例用 REMOVE+ADD（MODIFIED 改名会被拒）；顺带修正标题里过时的「Pro」档位表述（tier-plan-four-tiers v2 后 `settings-ai-fields`＝标准档起）。

## Risks / Trade-offs

- 翻案 10-26 刚重申的「不注入题材」条款：收窄而非废除，三件套口径不变；理由（成环前提消失）在 spec 与本 design 双落。
- 弱模型忽略六段骨架 → 体检四段缺失：模板自检第①条硬性要求＋few-shot 示例锚形态；体检本身只提醒不拦确认，风险可控。
