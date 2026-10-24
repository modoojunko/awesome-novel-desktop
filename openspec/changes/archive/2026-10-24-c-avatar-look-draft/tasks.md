> 双仓改动（C端＋提示词仓）；套 c-cover-scene-extract 成熟范式，免原型（既有工坊内增按钮）。

## 1. 提示词仓

- [x] 1.1 `prompts/image_avatar_look.prompt`（system 硬约束：只写外貌服饰/服装无字/头肩构图/无专名/不编造素材外特征＋JSON 契约单花括号；user 五素材占位符）＋ sync.py CURATED（family=image）＋ publish.py TIER_PRO_ONLY——验证：`sync.py all`＋`lint`＋`pytest` 全绿（77 模板）

## 2. 后端

- [x] 2.1 `cover_extract.py`：`collect_avatar_material`（角色卡白名单五素材截断）＋`extract_avatar_look`（角色归属校验→load_layers→json_mode→严格 parse_look，坏 JSON/空 look 502）＋`_chat_json`/`_record` 与封面提取复用；LOOK_MAX=140 与组装截断对齐——验证：单测
- [x] 2.2 端点 `POST .../characters/{cid}/image-prompt/look-extract`：`@ai_feature("image-generate")`＋`require_tier_access`＋端点内直调 `ensure_novel_model_ready`＋`svc._owned_character` 归属校验——验证：门控/归属用例
- [x] 2.3 用例：happy path（素材进 prompt、json_mode、草稿不落库）/坏 JSON 502/别人的角色 400（前两条 needs_prompts）＋parse 守卫钉（LOOK_MAX==140＋满长零切尾）——验证：pytest 绿

## 3. 前端

- [x] 3.1 `ImageWorkshopModal` 头像分支：头像描述行加「AI 起草」按钮（免费置灰；成功填 textarea＋toast）；`draftAvatarLook`；保存提示文案 kind 感知；label→div（同封面 D5 判例）——验证：vitest
- [x] 3.2 `imageApi.extractAvatarLook`＋测试 mock＋按钮用例（免费置灰/PRO 填草稿）——验证：tsc＋vitest 绿

## 4. 交割

- [x] 4.1 后端全量 pytest＋ruff；前端 tsc＋vitest 全量；openspec validate——验证：命令实际输出结论
- [x] 4.2 真机抽检：头像工坊「AI 起草」出稿可改可存、生成链冒烟——验证：真机截图/录屏
  - 2026-10-24 demo 栈（c6a7a/0.40）真机全过：API 层 look-extract 200（1.9s，草稿与角色卡逐项对拍——21 岁/夜巡短斗篷/猎血短刃全出自卡，无专名无字声明；usage 落 image_avatar_look|deepseek-flash 397/120）＋cover-extract 200（1.9s）＋未绑模型书 503 missing_model 正确引导；UI 层 Playwright 真走工作台→设定→角色→林野→印章开头像工坊，「AI 起草」按钮可见、点后草稿填入 textarea、两 toast（草稿已填入＋图像设置已保存）先后弹出（/tmp/p6-1-workshop.png、/tmp/p6-2-saved.png）
- [x] 4.3 实现按仓库规矩 `openspec-archive-in-implementation-pr`：合入前 sync delta＋移档 archive，随实现 PR 同批——验证：PR 内含归档移动，`openspec validate` 绿
