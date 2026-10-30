# c-library-avatar-gen — 实现任务

## 1. 原型/基线

- [x] 库页无 parity 基线（既有 ADJUSTMENTS 豁免口径）；头像生成入口属弹窗内小增件——实现期在 `docs/design-c/prototypes/ADJUSTMENTS.md` 追加登记（drafts 原型不追补：评审基线为已合入版）。

## 2. 后端

- [x] `image_assets/prompt_builder.py`：抽 `avatar_prompt_payload()`（字段级纯函数，书内/库卡共用）；`build_avatar_prompt()` 改读库后委托（行为零变化）；新增 `build_library_avatar_prompt()`（账号级默认图像配置＋本卡名/别名脱敏）。
- [x] `library/service.py`：`generate_avatar()`——取配置→组装 prompt→同步调 `generate_images`（120s 超时）→`normalize_image("avatar")`→写 blobs→bump rev；缺配置/供应商错误/超时/空结果全可读。
- [x] `library/router.py`：`POST /{id}/avatar/generate`（`ai_feature("image-generate")`＋`require_tier_access` PRO 门）；状态码映射 400/502。
- [x] 测试 `tests/test_library_avatar_gen.py` 7 例（prompt 脱敏/成功落图双档与 rev/缺配置 400/供应商 502/空结果 502/超时映射/无配置 prompt）。

## 3. 前端

- [x] `libraryApi.generateLibraryAvatar()`（信封解包）。
- [x] `CardEditorModal`：workingCard 工作态（新建先落卡再生成、转编辑态）＋「生成头像/重新生成头像」按钮（生成中禁用、PRO 门提示、失败可读、成功即刷新头像＋清缓存）。
- [x] 测试：`libraryAvatarGen.test.tsx` 6 例（已有卡/新建落卡/无名字/无 PRO/失败文案/非 Error 兜底）＋`libraryApi.test.ts` 增 generate 用例。

## 4. 门禁与回归

- [x] 前端 vitest 全仓 1961 例绿＋覆盖率契约四维 100%；tsc 绿。
- [x] 后端 ruff 绿；`test_library_avatar_gen`＋库域＋图像域 88 例回归绿。
- [x] e2e 不新增（生成需真实供应商/桩成本高，单测覆盖请求与状态；书内同能力已有真机路径）——记录为取舍。
- [x] 文案核对：按钮动词、无内部术语；失败文案带可读出口（缺配置指向模型配置）。
