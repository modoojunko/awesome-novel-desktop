# Tasks

## 1. 后端单源与模板

- [x] 1.1 `settings/character_model.py`：`DOSSIER_FIELDS` 撤 `author_only` 标志（机制整体退役），`DOSSIER_FILL_KEYS`＝`DOSSIER_KEYS` 全 8 键；`apply_character_fills` 删 author_only 拒写分支；`compute_targets` docstring 同步
- [x] 1.2 `prompts/settings_characters_dossier.prompt`：删性别/年龄禁令；补性别、年龄每格口径；种族口径放宽（优先世界已有，没写按题材惯例给一个）；输出示例补 gender/age
- [x] 1.3 `prompts/settings_characters_bootstrap.prompt`：同上四点
- [x] 1.4 `settings/characters_ai.py`：模块/bootstrap docstring 与 `_BOOTSTRAP_FILL_KEYS` 注释去掉「性别/年龄不代填」口径（逻辑零改动，键集单源派生自然跟进）

## 2. 前端镜像与文案

- [x] 2.1 `lib/characterModel.ts`：撤 `author_only`（interface 字段＋定义＋filter），`DOSSIER_FILL_KEYS`＝`DOSSIER_KEYS`
- [x] 2.2 `AiWriterAssistant.tsx`：路人行/主行档案计数上限 6→8；「从简介立主角」「基础信息补充」desc 与 footNote 撤「性别、年龄不代填」，基础信息补充改为「含性别、年龄、种族」
- [x] 2.3 `CharacterManager.tsx`：出卡弹窗脚注撤「；性别、年龄不代填」

## 3. 测试翻转

- [x] 3.1 `test_character_model.py`：`len(DOSSIER_FILL_KEYS)==8`；删 `test_author_only_fields`；apply 用例改断言性别照写
- [x] 3.2 `test_characters_ai.py`：draft 用例断言 targets/cells 含 gender/age、越界键仍丢、personality 卫生断言保留；bootstrap `test_gender_age_never_enter_cells`→`test_gender_age_enter_cells`
- [x] 3.3 `CharacterManager.bootstrap.test.tsx`：mock dossierGap 6→8

## 4. 门禁

- [x] 4.1 pytest：`test_character_model.py`＋`test_characters_ai.py`＋`test_shared_constants_parity.py`＋`test_prompt_layering.py` 全绿
- [x] 4.2 vitest：CharacterManager 相关批全绿（AiAssistPanel/AiWriterAssistant/bootstrap/cogHints 41 例）
