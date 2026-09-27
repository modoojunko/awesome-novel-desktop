## 1. 提示词口径（prompts/arc_draft.prompt）

- [x] 1.1 块标题改口径：「【当前主线（未填部分用（未填）标注）】」→「【作者已写在主线框里的内容（没写全很正常：可能是散想法、半成品或已成形草稿；空白处标注为（未填））】」；`{input}` 槽改称「【作者这次的补充说明（通常为空）】」并移到主线框块之后；任务句「把简介与散想法扩写」→「把简介与主线框里已有的内容扩写」；要求句改为「主线框里已写的内容（含散记、半成品）就是本次起草的输入——顺着它扩写，里面的关键词与显式要求尽量吸收，不要原样复述」。验证：模板口径断言（新标题/新要求句在、旧标题不在）＋`template.format(**ctx)` 双路径不抛错（既有用例覆盖）。
      **证据**：`test_draft_notes_in_box_wording`（新标题/吸收句在、旧标题不在、顺序与压尾）＋既有 format 双路径用例保持绿。
- [x] 1.2 其余口径零改：硬约束片段、产出义务、压尾顺序、空设定占位、JSON 双层花括号不动。验证：既有 `TestArcMaterial` 用例保持绿（顺序/哨兵/同源断言）。
      **证据**：全量 1536 passed，`TestArcMaterial` 全部用例未改仍绿。

## 2. 测试

- [x] 2.1 `test_story_arc.py` 增 `test_draft_notes_in_box_wording`：新块标题与「关键词与显式要求尽量吸收」在模板、旧标题不在、主线框块在补充说明行之前、末行仍「只输出 JSON」。验证：pytest 该文件绿。
      **证据**：`tests/test_story_arc.py` → 37 passed。
- [x] 2.2 契约反证：体检/校准/基调素材口径不受本 change 影响（体检仍拿设定全量、tone 仍轻量、calibrate 仍吃主线全文）。验证：本文件既有用例与全量套件绿。
      **证据**：`test_check_assembles_material_tone_does_not`／`test_calibrate_material_and_note_channel` 等保持绿；全量 1536 passed。

## 3. 回归与收尾

- [x] 3.1 后端门禁：`pytest tests/`（全量）＋ `ruff` 零新增；验证：命令输出结论写在 checkbox 下。
      **证据**：`pytest tests/` → **1536 passed**；`ruff check settings/ai_router.py tests/test_story_arc.py` → 1 error（`PLW0127`，存量）零新增。
- [x] 3.2 前端门禁判定：零前端改动（proposal Design Impact：右栏描述「散着说想法也行」在本口径下由虚转实，无需改字），design 三项不适用；验证：`git status` 仅 `client/backend/prompts/arc_draft.prompt`、`tests/test_story_arc.py` 与 `openspec/`。
      **证据**：改动面＝`prompts/arc_draft.prompt`＋`tests/test_story_arc.py`＋change 目录（无 `client/frontend` 文件）。
- [x] 3.3 真机复核：把散记写进主线框点起草，核对关键词/显式要求被吸收且未原样复述（本 change 已用隔离栈跑过一轮，见 `real-machine-check.md`；本任务＝按新提示词再跑一轮复核口径生效）。验证：证据追加到 `real-machine-check.md`。
      **证据**：`real-machine-check.md` 两轮 A/B——轮次 A（旧模板，能力已有）三点全吸收；轮次 B（新模板）三点仍全吸收且**散记框词「兜住/三个点」零出现**（不复述）；两轮均按设定原文用专名与铁律。隔离栈已拆、含密钥副本已删。
- [x] 3.4 收尾：`openspec validate c-arc-notes-in-box --strict`；spec delta 与实现逐条对拍（含「不改前端」「不改门槛判定集合」「校准/体检口径不动」三组反证）。
      **证据**：validate --strict 通过；三组反证分别在 Design Impact 判定＋`git status`／门槛措辞条款（判定集合未变，仅措辞对齐）／`test_check_assembles_material_tone_does_not`。
