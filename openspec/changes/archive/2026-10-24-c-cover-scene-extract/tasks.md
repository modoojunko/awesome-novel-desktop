> 双仓改动（C端＋提示词仓），涉及界面（工坊侧栏）与 DB schema（删列）；
> 前端回归含 vitest/tsc，后端含 pytest/ruff＋迁移重放；免原型（既有工坊内增删控件，无新页面/新布局形态）。

## 1. 种子退役（后端）

- [x] 1.1 `models/image_asset.py` 删 `BookImageSettings.cover_seed`、`CharacterImageSettings.seed` 两列；docstring 同步——验证：模型 import 烟测
- [x] 1.2 `image_assets/schemas.py` 两 body 删字段；`service.py` 删 seed 分支/响应键/`put_character_settings` seed 参；`router.py` 删 PUT「未显式提交 cover_seed 保留旧值」特判与角色 PUT seed 实参——验证：pytest 设置用例绿
- [x] 1.3 `prompt_builder.py` seed 恒走 `_derive_seed`（cover/avatar 两路），`seed_source` 恒 `derived`，模块契约注释同步——验证：prompt 用例断言 seed_source/候选 seed 关系
- [x] 1.4 `backup/export.py`+`importer.py` 删两键（旧包多键静默忽略）——验证：备份 roundtrip 用例断言 manifest 无键
- [x] 1.5 老客户端残留提交容错钉：PUT 带 `cover_seed: -1` → 200 且响应无该键（Pydantic ignore）——验证：`test_image_validation_and_non_ascii_signature` 改钉

## 2. 画面 AI 提取（后端＋提示词仓）

- [x] 2.1 提示词仓新增 `prompts/image_cover_scene.prompt`（system 硬约束：无字/剪影/单焦点/无专名/不剧透＋JSON 契约；user 五素材占位符）＋ `sync.py` CURATED（新 family `image`）＋ `publish.py` TIER_PRO_ONLY——验证：`sync.py all`＋`lint`＋`pytest tests/` 全绿（118 passed）
- [x] 2.2 `image_assets/cover_extract.py`：`collect_material`（story.yaml genre/sub_genre/synopsis/story_arc.fullstory[:1200]＋promise_note＋world stage[:300]，白名单截断）＋ `extract_cover_scene`（load_layers → get_ai_client_for_novel → json_mode → 严格 parse_scene，坏 JSON/空 scene 502 可重试）＋ usage 记账（成功/失败双路）——验证：单测
- [x] 2.3 端点 `POST /api/novels/{id}/image-prompt/cover-extract`：`@ai_feature("image-generate")`＋`require_tier_access`＋端点内直调 `ensure_novel_model_ready`（兼属主 404）——验证：门控 503/404 用例
- [x] 2.4 提取用例四条：happy path（素材进 prompt、json_mode、scene 回显）/坏 JSON 502/书模型未就绪 503/别人的书 404（前两条 `@needs_prompts`）——验证：pytest 绿

## 3. 前端工坊

- [x] 3.1 `ImageWorkshopModal.tsx`：删封面/头像种子输入框、state、校验、save payload；「画面描述」标签行加「AI 提取」按钮（免费置灰＋PRO title；成功填 textarea＋toast「草稿已填入，可修改后保存」）；字段容器 label→div（label 嵌按钮的语义/可访问名坑，见 design D5）——验证：vitest
- [x] 3.2 `imageApi.ts`：`BookImageSettings`/`CharacterImageSettings` 删两键；新增 `extractCoverScene`——验证：tsc --noEmit 绿
- [x] 3.3 用例：AI 提取免费置灰/PRO 填草稿、种子框退役钉、既有 4 条回归——验证：vitest 全量 1783 绿

## 4. 迁移与回归

- [x] 4.1 `legacy_samples.py` 新增样本 `v039-image-seed-columns`（novel-v0.39.db：图像设置带种子列）入册＋BASELINE 补键——验证：只增不减断言绿
- [x] 4.2 重放断言：设置行零损失、cover_prompt/avatar_prompt 原样、新 schema 无种子列、源库零接触——验证：`test_legacy_replay_gate.py` 3 绿
- [x] 4.3 后端全量 pytest 绿（带 PROMPT_PACK_DEV_DIR）＋`ruff check` 显式跑绿——验证：命令实际输出结论（2026-10-24：2761 passed, 1 skipped；ruff All checks passed；前端 vitest 1783 绿＋tsc 绿）
- [ ] 4.4 真机抽检：工坊删种子框后封面/头像设置保存回读正常；「AI 提取」出稿可改可存、预览 hash 随画面变——验证：真机截图/录屏

## 5. 交割

- [ ] 5.1 提示词仓同批独立 PR（分支 `c-cover-scene-extract`），commit 互引本 change id；生产生效随下个提示词包发布（publish.py 本地链）——验证：两 PR 互链
- [x] 5.2 实现按仓库规矩 `openspec-archive-in-implementation-pr`：合入前 sync 本 delta＋移档 archive，随实现 PR 同批——验证：PR 内含归档移动，`openspec validate` 绿
