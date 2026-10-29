# c-intro-draft-interview — Tasks

## 1. 后端：answers 入参＋三候选出参

- [x] 1.1 `settings/ai_router.py` draft 分支：读 `body.answers`（protagonist/taste/musts，各 ≤200；空→「（作者跳过了，按题材典型盘）」）；`content` 仍不作模型输入。验证：`test_draft_passes_answers_into_prompt`。
- [x] 1.2 出参归一：`{"candidates":[{label≤12,synopsis≤500}]}`（最多 3、空候选 502）；旧单稿形态包 1 条（label「候选 1」）。验证：`test_draft_*` / `test_draft_legacy_single_shape_wrapped` / `test_draft_empty_candidates_502`。
- [x] 1.3 temperature 0.8→0.9（三条差异）；docstring 口径更新。验证：`test_draft_empty_content_allowed` 断言 0.9。

## 2. 提示词仓 v4（独立 PR）

- [x] 2.1 `prompts/settings_intro_draft.prompt` v4：三候选 JSON 契约＋「作者补充优先」＋「三条故事核必须不同」＋自检⑦；世界体系一致性与双示例沿用 v3。验证：`sync.py lint` 绿（12 占位符对拍）。
- [x] 2.2 CURATED：desc/layer/三个新占位（protagonist_hint/taste_hint/musts_hint）；render＋index。验证：`render --check` 零 diff。

## 3. 前端：三段式交互

- [x] 3.1 `lib/ai.ts`：`DraftAnswers` 类型＋`IntroAiResult.candidates`；`introAi` draft 带 `answers`。验证：`introAi.test.ts`。
- [x] 3.2 `SettingsView.tsx`：`DraftInterviewForm`（三问，均可跳过）＋`DraftCandidatePicker`（三卡默认选第一条）；runAi 起草无缓存→开表单、有缓存→开缓存；「换一个」带答案重出；卡内「改一下问题」回表单保留答案；行描述改口径。验证：组件级测试。
- [x] 3.3 采纳＝所选整段替换＋回执一步撤销（标签进回执文案）。

## 4. 测试

- [x] 4.1 后端 TestIntroDraft 重写：三候选/答案注入/占位/旧单稿包裹/空候选 502/温度/500 clamp；全量 2887 绿（存量 2 环境红对拍一致）。
- [x] 4.2 前端：组件级 6 例（表单先出不发请求/答案随请求/三卡选填/全跳过/旧稿替换撤销/改问题保留答案）＋请求形态；全量 1894 绿、tsc 绿。
- [x] 4.3 e2e `genre-ai-settings.spec.ts` 起草链路改写（三问→三卡→选第二条→填入→撤销；随 nightly 兜底）。

## 5. 收尾

- [x] 5.1 openspec change 四件套＋validate；delta sync 进主 spec；归档随 PR（2026-10-29-c-intro-draft-interview）。
- [x] 5.2 提示词包 2026.10.29-2 发布（四档冒烟/CEK/翻 latest/tag）；mac dev 包重建重装供真机验证。
