# c-intro-ai-draft — 简介步 AI 起草：题材已定、简介未写时的第一版底稿

## Why

#950（c-genre-first-order）把设定前两步翻转为「① 题材 → ② 简介」后，用户落到简介步时题材（含五格）已就绪，但简介步的 AI 三件套（体检/补缺失/润色）全部以「已有内容」为前提——空简介落地时 AI 完全帮不上忙，题材步的投入没有变现出口。题材既已定，简介完全可以由 AI 先起草一版给作家当底稿（用户 2026-10-28 拍板）。

**拍板冲突摆明**：现 spec 明文「简介三件套 SHALL NOT 注入题材——防『简介↔题材判定』成环」（2026-09-11，10-26 曾确认沿用）。该拍板的前提在 #950 后已消失：题材判定不再吃简介输入（空简介照常出候选），成环论证不存在了。本次将把该条款**收窄**至三件套（体检/补缺失/润色），起草显式例外——起草＝从题材正向长出简介，方向单一不回环。

## What Changes

- 简介 AI 写作助手三能力 → **四能力**：新增「**起草**」行（列首位），凭题材＋书名＋五格已填项从零出第一版底稿；采纳才写入、回执一步撤销、「换一个」重掷（沿用确认卡 D9/D14 交互，**不做多候选**）。
- **BREAKING（后端行为，向后兼容加法）**：`POST /settings/ai/intro/draft` 新 action——跳过三件套的「简介为空 400」；注入题材上下文（story.yaml 题材目录＋`_theme_anchor` 风格锚＋`get_novel_genre` 五格，候选 id 译回人类可读标签，未填项标「作者还没填」）；不吃已有简介（从零起，已有成稿走润色，职责分明）。
- spec 条款收窄：「三件套 SHALL NOT 注入题材」保留；起草显式注入并注明翻案理由与拍板日期。
- 提示词仓新增 `settings_intro_draft.prompt`（分层两段；六段骨架与 lib/introTemplate.ts 口径一致，产出可直接过体检）→ **需发一版提示词包**（新模板 key）。
- 门控零改动：沿用 `settings-ai-fields` feature key（标准档起，与题材四问、三件套同 key），权益表不动。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `specs/intro-genre-settings/spec.md`: 「创建期前两步」Requirement 的题材注入条款收窄至三件套＋起草例外；「简介 AI 写作助手」Requirement 由三能力改四能力（改名走 REMOVE+ADD），新增起草契约与两个场景。

## Impact

- 后端：`settings/ai_router.py`（INTRO_ACTIONS／_INTRO_PROMPTS／intro_ai draft 分支）。
- 前端：`lib/ai.ts`（IntroAiAction/Result 类型）、`SettingsView.tsx`（introAiRows 首位起草行＋runRequest 起草出卡分支）。
- 提示词仓：`prompts/settings_intro_draft.prompt`＋sync.py CURATED 登记＋manifest/README 重建；合入后发提示词包（min_client 不 bump）。
- 测试：后端 `test_ai_layers.py` 新增 TestIntroDraft＋门控回归；前端 `introAi.test.ts`/`SettingsView.introHandle.test.tsx`；e2e `genre-ai-settings.spec.ts` 空简介起草一条。
