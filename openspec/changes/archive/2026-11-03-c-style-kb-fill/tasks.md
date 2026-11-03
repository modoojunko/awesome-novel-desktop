## 1. 建书种子瘦身

- [x] 1.1 `reference/writing-style.yaml.template`：三区留空（role/rules/craft/few_shot_examples/style_samples），只留 banned_words 37＋tic_patterns 8；旧键退出
- [x] 1.2 `tests/test_db_storage.py`：断言新书种子形状（三区空＋护栏在位、无 core_principles）

## 2. 知识库草稿端点

- [x] 2.1 `settings/style_kb.py`：按题材查基线（同题材优先＋跨题材通用），槽位映射、去重、上限、counts、身份兜底
- [x] 2.2 `kb/snapshot.py`：`build_members` 增补 `severity`（apply_members 行为不变）
- [x] 2.3 `settings/router.py`：`GET /settings/style/kb-draft`（只读；无题材返回空草稿）
- [x] 2.4 `tests/test_style_kb_draft.py`：无题材/全槽位/通用兜底/场景与别题材与 archived 排除/身份兜底/上限
- [x] 2.5 官方基线并入：`kb.merged.load_baseline_entries`（hide 排除 / edit 副本生效）＋两条基线用例

## 3. 前端

- [x] 3.1 `lib/styleApi.ts`：`StyleKbDraft` 类型＋`styleKbApi.draft`
- [x] 3.2 `SettingsView.tsx`：右栏首行「按题材填文风」（ungated）＋进面板摘要查询＋footNote
- [x] 3.3 `StyleSettingForm.tsx`：`runAi("kb")` 取草稿、`AiCardModal` 勾选卡、默认勾选、身份可改、组头全选
- [x] 3.4 `adoptKb`：三区替换 / 护栏合并、回执＋撤销、切回文字页签、toast
- [x] 3.5 文案与徽标三态（未填 / 未改动 / 已自定义·N 处）
- [x] 3.6 单测 `StyleSettingForm.kbFill.test.tsx`（7 例）＋ fewShots 徽标测试更新
- [x] 3.7 e2e `settings-forms.spec.ts` 新增「按题材填文风」用例（独立栈跑过）

## 4. 后端回归

- [x] 4.1 `tests/test_readiness.py`：新书 style 未就绪；写 role 后可确认
- [x] 4.2 `tests/test_deconstruct_api.py`：空文风产物＝原样保留（三区空、护栏在位）

## 5. 文档

- [x] 5.1 openspec change（proposal/design/tasks＋specs delta）
- [x] 5.2 `docs/design-c/prototypes/style-settings.html` 同步＋`ADJUSTMENTS.md` 登记

## 6. 验证

- [x] 6.1 后端定制用例与全量 pytest（2807 passed）
- [x] 6.2 前端 `tsc --noEmit`＋全量 vitest（2144 passed）
- [x] 6.3 e2e（settings-forms 16/16；creation-flow 5/6，余 1 例为存量 hooks 确认不前进，非本改动）
- [ ] 6.4 真机手工走查（新书→定题材→右栏行→勾选→采纳→撤销→保存）
