# 任务：拆章抽卡章尾自然断点

## 1. 提示词模板

- [x] 1.1 `client/backend/prompts/chapter_split.prompt` 硬规则 4 改写为自然断点口径（写清章结束时事件到哪一步、谁在什么局面，断在事件半途、局面未定处；悬念留给读者想知道"然后呢"；禁止刻意悬念道具装"留伏笔"），末章例外（规则 5）不动；`ending` 字段定义的「停在场面状态上」呼应为「停在场面状态（剧情自然断点）」。验证：`grep -n "自然断点" chapter_split.prompt` 命中规则 4 与 ending 定义，且规则 4 行不再含「还没完」。
- [x] 1.2 `client/backend/prompts/chapter_selfcheck.prompt` 拉力问句（第 21 行）改为「结尾停没停在剧情自然断点（局面未定）？」口径。验证：`grep -n "拉力" chapter_selfcheck.prompt` 仅命中新问法与 JSON 键名行。

## 2. 测试

- [x] 2.1 新增模板对拍测试（`client/backend/tests/test_chapter_plan_ai_t3.py` 或就近文件）：断言 chapter_split 模板规则 4 行含「自然断点」与「悬念道具」禁令、不含「还没完」；chapter_selfcheck 拉力行为自然断点口径。验证：`pytest tests/ -q -k "ending_natural or template"` 相关用例绿。
- [x] 2.2 全量后端门禁。验证：`cd client/backend && python3 -m pytest tests/ -q --timeout=30` 全绿（存量基线照旧）。

## 3. 收尾

- [ ] 3.1 spec sync（归档时）：`openspec/specs/chapter-plan-ai/spec.md` 按 delta 落两处 MODIFIED。验证：`openspec validate --strict` 通过。
- [ ] 3.2 真 3 方向出卡人工抽检一次（隔离栈或主栈皆可）：章尾为局面句（谁在哪、事到哪一步），无神秘人／信物／异象式钩子；末章出卡时仍收在卷纲预期结局。验证：抽检记录贴进 change `evidence/`。
