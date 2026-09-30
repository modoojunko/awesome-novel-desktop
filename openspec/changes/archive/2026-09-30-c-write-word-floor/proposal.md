# c-write-word-floor：正文字数要求改只设下限——写故事至少 X 字可多不可少，删「叙事完整性优先」逃生门（#621）

## Why
用户真机反馈（09-30）：正文生成提示词要求「约 2500 字（±10% 可接受，叙事完整性优先）」，实际稳定只出 1500 多字。三因合谋：①「叙事完整性优先」是明示逃生门——写完素材拍点即停是最省字的「完整」路径；②提示词只有超限策略（压缩低权重场景）没有不足策略，且字数行挂在「优先于字数与写法」的章级红线下；③完成时字数校验只提示不补救（below_limit 已算出但仅随 done 返回）。LLM 数不准中文字数，「约 2500 字」裸要求通常落在目标 60–85%，叠加逃生门稳定滑出下限。

## What Changes（#621=ec9c15d4，squash 上 main）
- 字数要求只设下限：`material_markdown`／`to_user_material` 两处字数行改「写故事至少 X 字，可以多，不可以少——低于 X×0.9 字即为不合格」＋扩写策略（情节拍点写完仍不足下限时，用对话交锋、感官细节、心理活动扩写既有场景补足，不得新增冲突事件、不得删改红线内容）；删「叙事完整性优先」逃生门，「压缩低权重场景」随「可以多」退役。
- 口径单源：新增 `word_target_floor()`（目标 ×0.9），提示词文案与 `_stream_chapter` 完成时校验（below_limit）共用同一函数，不再各自硬编码。
- 润色模板对齐（评审 P1）：`prompt_crafting.prompt` 十段描述要素 2 改下限＋扩写同族措辞，硬性纪律「不得在压缩时删除」改「不得删改」——否则润色链（有章纲章节的默认路径）会按模板旧描述把「约X字±10%＋压缩策略」拼回成品提示词，恰好复活本改要删的逃生门。
- 复发闸：新增 `test_craft_template_word_policy_synced_with_material` 钉模板侧口径（扩写策略在、压缩策略/±10% 不在），与素材侧骨架断言（test_chapter_writer_context）两头对拍。

## Capabilities
- prose-writing：MODIFIED「按目标字数生成」（±10% 弹性＋压缩策略 → 只设下限＋扩写策略＋口径单源）、「写完字数校验」（下限口径与提示词同源单源、达标场景措辞对齐）。
- prompt-crafting：MODIFIED「提示词内容骨架」（要素 2 任务指示段描述对齐下限＋扩写）。

## Impact
后端 5 文件（write/chapter_writer.py、write/router.py、prompts/prompt_crafting.prompt、tests/test_chapter_writer.py、tests/test_chapter_writer_context.py＋复发闸在 tests/test_write_prompt_polish.py，合计 6）。门禁：pytest -k write 142 绿（含钉文案断言同步更新与复发闸）、提示词分层闸门 1 绿、ruff 改动文件全绿（router.py:13-14 F401/F811 为存量告警未碰）；前端零改动，vitest/e2e 不受影响。非目标＝「不足自动续写一轮」兜底（真机验证后视需要另立项）；存量已润色 write-prompt 行仍是旧措辞，需「刷新提示词」/重新润色才带新要求。评审（review-agent）：1 个 P1（润色模板脱节），随同 PR 修复闭环（模板对齐＋复发闸）。CI 基建秒挂（CodeQL main 连续红）按先例 admin 合入。
