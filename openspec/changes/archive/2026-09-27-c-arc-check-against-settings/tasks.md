## 1. 素材与提示词

- [x] 1.1 `settings/ai_router.py`：`_arc_material` 的组装 gate 由 `("draft", "calibrate")` 扩为含 `check`；注释同批改（体检＝校验型拿设定全量）。验证：`test_story_arc.py` 中体检提示词含世界观/人物档案内容。
      **证据**：`test_check_assembles_material_tone_does_not`（spy 断言 check 调 `_arc_material`、prompt 含【人物档案】/血族议会/铁律原文）。
- [x] 1.2 `prompts/arc_check.prompt` 重写：素材区（书名/简介/题材锚/【题材与节奏】/【世界观】/【人物档案】/主线全文/三问）＋边界声明＋**五条检查线**（前四条原文保留，第五条 name 逐字「和世界/人物对得上」，口径含「名字以设定原文为准／违反铁律／与人物档案定位硬冲突／设定为空给 miss＋『设定还没填，先补再查更准』」）＋「前四条只看主线自身、第五条以设定为对照」的作用域句＋「只输出 JSON」压尾；不引用 `{hard_rules}`。验证：单测断言五条 name 逐字在模板中、JSON 示例双层花括号、`template.format(**ctx)` 双路径（满/空设定）不抛错。
      **证据**：`test_check_prompt_five_lines_and_empty_fallback`（五条 name 逐字＋空设定占位＋JSON 压尾）＋真机双跑（见 `real-machine-check.md`）。
      **注**：设计 D1 决定体检不引用 `{hard_rules}`（写作约束片段，体检只判断不创作）——`test_templates_scope` 锁死。

## 2. 测试

- [x] 2.1 翻转旧断言：`test_check_tone_do_not_assemble_material` 改为「check 组装素材、tone 不组装」——check 的 prompt 含世界观势力名与主角名；tone 的 prompt 仍不含【世界观】/【人物档案】。验证：pytest 该文件绿。
      **证据**：改名 `test_check_assembles_material_tone_does_not`，monkeypatch spy 断言调用次数（check＝1、tone 仍＝1）。
- [x] 2.2 新增体检素材断言：真书式 fixture（三势力＋铁律＋9 人）下 check 的 captured prompt 含三势力名字与注记全部（无「从略」）、铁律原文、人物档案（主角＋反派六层在包、配角不带）。验证：pytest 绿。
      **证据**：`test_draft_material_full_and_passthrough` 的 fixture 复用（同 `_seed_full`）＋ 2.1 的 check prompt 断言（三势力名/铁律）；全套 1535 passed。
- [x] 2.3 空设定双路径：世界/角色全空 → check 正常 200，prompt 含指令式占位，且模板第五条含「先补再查更准」；门槛不变（全空素材仍按既有 400 口径只拦 draft/calibrate）。验证：pytest 绿。
      **证据**：`test_check_prompt_five_lines_and_empty_fallback`（200＋两处占位原文＋模板含降级文案）＋存量 `test_empty_settings_are_instruction_placeholders`（400 只拦 draft）。
- [x] 2.4 契约不变反证：check 的 `operation`/温度/别名/信封不变（既有断言保持绿）；draft/calibrate 素材断言不受影响。验证：pytest 该文件＋相关套件绿。
      **证据**：`test_arc_ai_uses_supported_model_alias` 与全套 1535 passed（未改调用参数与信封）。

## 3. 回归与收尾

- [x] 3.1 后端门禁：`pytest tests/`（全量，含 volume/chapter plan 套件）＋ `ruff` 零新增；验证：命令输出结论写在 checkbox 下。
      **证据**：`pytest tests/` → **1535 passed**；`ruff` → 1 error（`PLW0127`，style 蒸馏段 line 1874，存量）零新增。
- [x] 3.2 前端门禁判定：无 UI 改动（proposal Design Impact：前端 `checks.map` 动态渲染，条数不写死），design 三项不适用；验证：`git status` 仅 `client/backend/` 与 `openspec/`。
      **证据**：改动面＝`settings/ai_router.py`＋`prompts/arc_check.prompt`＋`tests/test_story_arc.py`＋change 目录；`StoryArcForm.tsx:164-169` 以 `checks.map` 渲染（实读确认）。
- [x] 3.3 真机抽查（隔离栈，沿 c-arc-draft-material 配方）：在真书上点一次「主线体检」，核对第五条是否指名到具体专名/条款、是否只提醒；把 prompt 的 token 与产出摘要落证据。验证：证据文件贴进 change 目录。
      **证据**：`real-machine-check.md`——冲突版（主线塞设定外组织「铁血兄弟会」→ 第五条 warn 指名该组织并列出设定里真实三势力）；对照组（删掉该组织 → 第五条不再报冲突，改指出「血族长老属哪派」「未饮血即推进夜行阶」两处可对照条款名的真问题）；token 2354/2367。
- [x] 3.4 收尾：`openspec validate c-arc-check-against-settings --strict`；spec delta 与实现逐条对拍（含「tone 仍轻量」「素材边界仍四件套」「判据前四条逐字未改」三组反证）。
      **证据**：validate --strict 通过；三组反证分别在 `test_check_assembles_material_tone_does_not`／`test_draft_material_excludes_other_domains`／`test_check_prompt_five_lines_and_empty_fallback`（前四条 name 逐字断言）。隔离栈已拆、含密钥副本已删。
