## 1. 素材拼装（settings/ai_router.py）

- [x] 1.1 新写 `_arc_material(db, project)`，**只对 draft/calibrate 组装**（`_arc_context` 现在对所有 action 都跑；体检/基调不得因本 change 多查人物表与题材解析），产出与 `_arc_context` 合并的 ctx：既有 `title/synopsis/theme/theme_desc` ＋ `world`（`settings/world_model.world_summary_text(world_raw, None)`）＋ `genre_section`（`genres/service.resolve_genre_context(project.root_path, project.id)` + `build_genre_section`，None 时给空串）＋ `cast`（见 1.2）。验证：`client/backend/tests/test_story_arc.py` 新增 fixture 单测断言各键内容（不依赖模型）。
      **证据**：`test_story_arc.py::TestArcMaterial` 8 例全绿（`test_draft_material_full_and_passthrough` 断言三键内容）。
- [x] 1.2 人物块渲染器（**不复用** `volumes/ai_plan._book_material.cast_brief` 的 `persona[:80]` 截断）：对 `character_service.list_characters(db, project.id)` 全量角色输出——名字（含 aliases）＋类型＋**人设原文全文**＋档案八格原文（标签取 `character_model.DOSSIER_FIELDS`，只渲染已填格）；**认知六层逐格原文只对 `role ∈ {主角, 反派}` 输出**（标签取 `COG_LAYERS`，只渲染已填格）；主角置顶、其余按 seq；**空名占位卡（`\u0000<hex>`）按 `character_service._display_name` 显示「未命名」**；角色表为空 → 见 1.4 的指令式占位；块尾一行「（以上共 N 人；只点名与这条主线直接相关的人）」。验证：fixture 断言 300 字人设不被截、八格与别名在包、配角不带六层、素材不含 `\u0000`。
      **证据**：三处哨兵（81/150/300 字处）在包、别名「拾子」在包、`◇配角六层◇`不在包、`test_unnamed_card_shows_placeholder` 断言「未命名」在包且无 `\u0000`。
- [x] 1.3 排除边界：确认素材全文不含已拆卷清单、伏笔台账、文风段、人物关系、无卡名单（用户 2026-09-27 拍板口径）。验证：fixture 断言素材不含卷号行、伏笔标记（如「[H-」）、文风段标记。
      **证据**：`test_draft_material_excludes_other_domains`（各域埋唯一串后逐条断言不在包＋`[H-` 不在包）。
- [x] 1.4 空设定＝指令式占位（不是名词短语）：`world` 缺 → 「（世界设定：未填——不要为它补写，也不要在产出里提到它）」；`cast` 缺 → 「（角色表：无——需要人物处用通称）」；并在模板任务区加一句「标为『未填』的块＝作者还没写，不要替它补、不要提它」。验证：fixture 双路径断言（空设定路径命中占位原文）。
      **证据**：`test_empty_settings_are_instruction_placeholders`（占位原文在包＋全空素材仍 400）。
- [x] 1.5 世界铁律只走一条通道：确认拼装未额外读 `constraints` 字符串（避免 v1 字符串／v2 列表双形状重复注入）。验证：同一本书的 arc 素材里「世界铁律·」行数与 `render_red_lines` 输出行数相等（fixture 断言）。
      **证据**：实现只用 `world_summary_text(world_raw, None)`（其内部即 `render_world_block` + `render_red_lines`），未读 `constraints`；真书对拍 6 条铁律行与红线口径一致（见 material-check.md）。
- [x] 1.6 硬约束与产出义务的**文本单源**：三条硬约束（红线／只用已有专名＋关系延伸或通称出路／冲突以设定为准）住 `prompts/arc_hard_rules.prompt`（剥 `## ` 头后作 `{hard_rules}` 值），**draft/calibrate 共用**；产出义务（主角与主要对抗者真名出现、势力名照原文）住 `arc_draft.prompt`（校准无 fullstory 出口，故不共用）；验证：格式化后 prompt 逐字包含该段（断言）＋旧句「不要发明与它们冲突的新设定」不再出现（负向断言）。
      **证据**：`test_draft_material_full_and_passthrough`（`不要起新专名`／`以铁律为准顺势化解` 在包）、`test_calibrate_material_and_note_channel`（校准带同一片段）、`test_templates_scope`（旧句已删）。
      **注**：本条原文写「产出义务也共同引用」，实现按语义分置（校准只回三问，产出义务无落点）——口径未变，仅归属修正。
- [x] 1.7 改写 `_arc_context` 的误导注释（现写「世界/角色由 prompt 引导 AI 概括，避免超长」——该机制不存在）；验证：注释与 design.md D1/D10 逐条对得上（人工比对，写入 PR 说明）。
      **证据**：`_arc_context` docstring 改为「轻量上下文；本书世界/人物/题材全字段由 `_arc_material` 对起草/校准单独组装；体检/基调维持轻量」。

## 2. 模板（prompts/arc_draft.prompt · arc_calibrate.prompt）

- [x] 2.1 `arc_draft.prompt` 按**固定顺序**重排加块：书名 → 简介 →【题材与节奏】(`{genre_section}`，题材目录锚 `{theme_desc}` 保留) →【世界观】(`{world}`) →【人物档案】(`{cast}`) → 作者散想法(`{input}`) → 当前主线 → **任务＋硬约束＋只输出 JSON（压尾）**；素材区开头加边界声明；任务句逐块引用素材＋产出义务＋负面句；JSON 示例保持双层花括号。验证：单测对「满设定」与「全空设定」两条 ctx 各跑 `template.format(**ctx)` 不抛错，且顺序断言。
      **证据**：两条路径均经端点跑通（`test_draft_material_full_and_passthrough`／`test_empty_settings_are_instruction_placeholders`）；顺序断言（【人物档案】< 任务：；硬约束 < 只输出 JSON；末行以「只输出 JSON」开头）。
- [x] 2.2 `arc_calibrate.prompt` 同批加块与约束句，并把 `note` 扩为冲突出口（「三问改动说明；若发现主线全文与世界/人物/题材冲突也在这里点一句，≤30 字，只提醒，不改主线全文」）；验证：同 2.1 的 format 双路径冒烟＋note 措辞逐字断言。
      **证据**：`test_calibrate_material_and_note_channel`（铁律与主角名在包、`在 note 里点一句` 与作者补充说明在包）。
- [x] 2.3 不动 `arc_check.prompt` 与 `arc_tone.prompt`；验证：断言两模板既无新占位符也无新块文本（字面检查），且 check/tone 调用路径不组装 `cast`/`genre_section`。
      **证据**：`test_templates_scope`（占位符字面检查）＋`test_check_tone_do_not_assemble_material`（把 `_arc_material` 猴补成抛异常，check/tone 仍 200，且 prompt 无【人物档案】与铁律/势力文本）。

## 3. 测试与契约

- [x] 3.1 `test_story_arc.py` 素材 fixture 断言（打桩 `_FakeAI.calls` 捕获 prompt 原文）：世界三势力名字与注记全部（全文不含「从略」）＋铁律原文＋9 名角色全在包且主角置顶＋**不截断哨兵**＋**原样透传哨兵**（persona 与某世界条目含 `{}`、引号、反斜杠）＋配角不带六层（配角的六层哨兵串不在包）＋素材不含「未填」噪音格与 `\u0000`。验证：pytest 该文件绿。
      **证据**：`test_draft_material_full_and_passthrough`＋`test_unnamed_card_shows_placeholder`（8 例全绿）。
- [x] 3.2 同源断言（design Goal「同一零件给同一文本」）：同一 fixture 下 `_arc_material(...)["world"] == volumes/ai_plan._book_material(...)["world_brief"]`，题材段同串；验证：pytest 绿（不一致即零件漂移）。
      **证据**：`test_material_same_source_as_volume_pack` 绿。
- [x] 3.3 降级与门槛回归：世界/角色全空但有简介 → 调用正常发起（200）且命中指令式占位；无散想法且无简介且主线全空 → 仍 400 中文提示（存量断言不回归）；验证：pytest 该文件绿。
      **证据**：`test_empty_settings_are_instruction_placeholders`＋存量 `test_empty_material_400`／`test_draft_material_accepts_synopsis` 保持绿。
- [x] 3.4 计费与调用参数回归：draft/calibrate 的 `operation`、模型别名、温度不变；验证：既有记账/别名断言（usage 记 `arc_{action}`、`fake.calls[0]["model"]`）保持绿。
      **证据**：`test_arc_ai_uses_supported_model_alias` 与记账断言全绿（未改调用参数）。
- [x] 3.5 卷/章链路不受影响：`volumes/ai_plan._book_material` 的 80 字一行卡与「全名单」口径保持原样（本 change 只加不删）；验证：`test_volume_plan_ai` / `test_chapter_plan_*` 绿。
      **证据**：全量 `pytest tests/` 1534 passed（含两套件）。

## 4. 回归与收尾

- [x] 4.1 后端门禁：worktree 独立栈跑 `pytest`（含 settings/arc、volume/chapter plan 相关套件）＋ `ruff` 零新增；验证：命令输出结论写在 checkbox 下。
      **证据**：`pytest tests/` → **1534 passed**；`ruff check settings/ai_router.py tests/test_story_arc.py` → 1 error（`PLW0127`，style 蒸馏段 line 1870），与 `git show HEAD:` 版本逐同，**零新增**。本机跑测（client/backend/.venv，Python 3.12.13），未用共享容器栈。
- [x] 4.2 前端门禁判定：本 change 无 UI 改动（proposal「Design Impact」判定：仅 `client/backend`），`design:lint` / `design:check` / `design-cross` 不适用；验证：在 change 的回归小结引用该判定并注明「前端零改动」。
      **证据**：本 change 零前端文件改动（`git status` 仅 `client/backend/…`＋`openspec/…`），故三项前端门禁不适用。
- [x] 4.3 真书人工 A/B（验收本体）：活库快照副本上跑素材装配并落证据；**模型在环已在自建隔离栈跑通真调用**（`arc-e2e-client-backend:local`，独立容器/端口/数据副本；共享栈零触碰）。验证：素材全文与产出摘要贴进 change 目录或 PR。
      **证据**：`material-check.md`——素材侧（世界 1058 字无「从略」/三势力全在、铁律 6 条、题材全文、人物档案八格＋主角六层、素材总 3231 字）＋模型在环（同书同操作 token 对照 **846 → 2687**；产出 13 个专名逐一在素材中、**零自造**；铁律以「畏光减轻＝主角异变」顺写未违反；未逐个介绍人物）。隔离栈已拆除、含密钥的副本已删除。
- [x] 4.4 收尾：`openspec validate c-arc-draft-material --strict` 通过；spec delta 与实现逐条对拍（含「不改 check/tone」「已拆卷/伏笔/文风不进」「旧句已删」三组反证）；确认与未归档的 `c-plan-material-fullinfo` 无 delta 重叠（可各自归档）。
      **证据**：validate --strict 通过；三组反证分别在 `test_check_tone_do_not_assemble_material`／`test_draft_material_excludes_other_domains`／`test_templates_scope`；`c-plan-material-fullinfo` 的 delta 覆 volume-plan-ai＋chapter-plan-ai 两能力，本 change 覆 storyline-settings，无重叠。
