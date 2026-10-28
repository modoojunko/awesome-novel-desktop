# c-intro-ai-draft — Tasks

## 1. 后端：draft action

- [x] 1.1 `settings/ai_router.py`：`INTRO_ACTIONS` 加 `"draft"`、`_INTRO_PROMPTS` 加 `settings_intro_draft` 映射。验证：`grep -n "draft" settings/ai_router.py` 目视。
- [x] 1.2 `intro_ai` handler：draft 分支跳过空简介 400；注入题材目录（`_theme_anchor`）＋五格（id 译标签、未填标「作者还没填」）；temperature 0.8；返回 `{"original","draft","act":"replace"}`（clamp 500）。验证：pytest 新增用例。

## 2. 提示词仓（awesome-novel-prompts，独立 PR）

- [x] 2.1 `prompts/settings_intro_draft.prompt`：分层两段＋六段骨架（与 introTemplate 口径一致）＋硬性规则/词句禁忌沿用 polish 体系＋JSON 契约 `{"synopsis": ...}`＋few-shot 示例。验证：`python3 sync.py lint` 绿。
- [x] 2.2 `sync.py` CURATED 登记（family=intro，ph 八占位符）＋`render`＋`index`。验证：`sync.py render --check` 零 diff、manifest 计数 +1。

## 3. 前端：起草行与出卡

- [x] 3.1 `lib/ai.ts`：`IntroAiAction` 加 `"draft"`、`IntroAiResult` 加 `draft?` 字段、`introAi` 注释补 draft 空内容合法。验证：tsc。
- [x] 3.2 `SettingsView.tsx`：`introAiRows` 首位插「AI 起草」行；`runRequest` 加 draft 分支（label「AI 起草稿 · 采纳才写入」、original 非空附对照、adopt＝整段替换＋回执撤销）。验证：vitest 新增用例。

## 4. 测试

- [x] 4.1 后端 `tests/test_ai_layers.py` 新增 TestIntroDraft：空简介放行、题材注入断言（system/user 含题材行与「作者还没填」）、返回形状/500 截断、坏 JSON 502、TokenLog `operation=settings_intro_draft`＋temperature。验证：pytest 定向绿。
- [x] 4.2 门控回归：无 AI 权限 draft 403（`test_free_bypass` 同款）。验证：pytest 绿。
- [x] 4.3 前端：`introAi.test.ts`（draft 进 URL、空 content 合法）；`SettingsView.introHandle.test.tsx`（行首位、空简介可点、出卡采纳替换＋撤销）。验证：vitest 定向绿。
- [x] 4.4 e2e `genre-ai-settings.spec.ts`：空简介→起草→采纳＋回执撤销一条（用例已入库；本会话未起独立全栈，定向跑随 nightly e2e 兜底——S端栈依赖 19000 demo，按环境隔离规矩不蹭共享栈）。验证：组件级 vitest 已覆盖同链路（行点击→introAi→出卡→采纳→撤销，选择器与 e2e 同名）。

## 5. 收尾

- [ ] 5.1 `openspec validate --all` 与 main 存量基线对拍放行；实现 PR 带 delta sync＋归档（openspec-archive-in-implementation-pr）。
- [ ] 5.2 合入后：提示词仓 PR＋提示词包发布（新模板 key，min_client 不 bump，发布四件套验收）＋真机抽检（新书→题材四问→起草→体检链路）。
