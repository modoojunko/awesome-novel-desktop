# c-write-word-floor Tasks

## 1. 字数要求只设下限（write/chapter_writer.py）

- [x] 1.1 新增 `word_target_floor()`（目标 ×0.9）单源；`material_markdown`／`to_user_material` 两处字数行改「写故事至少 X 字，可以多，不可以少——低于下限不合格」＋扩写策略，删「叙事完整性优先」逃生门与超限压缩策略。完成证据＝diff 上 main（#621=ec9c15d4）。
- [x] 1.2 `_stream_chapter` 完成时校验（below_limit）改用 `word_target_floor`，与提示词文案同口径。完成证据＝同上。

## 2. 润色模板对齐与复发闸（评审 P1）

- [x] 2.1 `prompts/prompt_crafting.prompt` 要素 2 改下限＋扩写同族措辞；硬性纪律「不得在压缩时删除」随压缩策略退役改「不得删改」。完成证据＝同上。
- [x] 2.2 新增复发闸 `test_craft_template_word_policy_synced_with_material`：钉模板侧「扩写策略」在、「压缩策略」「±10%」不在，与素材侧骨架断言两头对拍。完成证据＝pytest tests/test_write_prompt_polish.py 13 例绿。

## 3. 门禁与交付

- [x] 3.1 pytest -k write 142 绿（钉文案断言同步更新：test_chapter_writer／test_chapter_writer_context）；提示词分层闸门 1 绿；ruff 改动文件全绿。完成证据＝各命令实际输出结论。
- [x] 3.2 评审（review-agent）：1 个 P1（润色模板脱节），随同 PR 修复闭环（模板对齐＋复发闸）；其余消费路径（validate_polished_prompt 锚、legacy 三锚判定、e2e 桩、前端 word_check）核实不受影响。
- [x] 3.3 PR #621 admin squash 合入（CI 基建秒挂按先例）；本地 main 对齐 ec9c15d4；归档时 sync prose-writing／prompt-crafting MODIFIED。
