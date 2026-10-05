## Why

正文生成的反 AI 约束目前只有一句硬编码「质感要求」（chapter_writer.py 注入），AI 写作的结构性毛病——信息用旁白汇报、汇报链流水账、对话夹三明治、「不是A而是B」句式、破折号、章尾给钩子搭台——在生成期无人拦截，全部积压到写完后由作者人工或选区级去AI味补救。外部实测案例（30 章真书过朱雀检测的完整作战档案，含受控实验）证明：这些毛病可枚举、可禁令化，其中「信息装进对话」单项受控实验 Δ−0.53（conf 1.0→0.4655），「夹层/『是…不是』/破折号清零」单项 −50 点；且案例最终结论是生成端治本优于术后修窗——源头写对，后续去AI味的使用频次自然下降。

## What Changes

- `prompts/write_chapter.prompt` 的「写法要求」从一句占位注入（`{craft_rules}`）改为**模板静态文本的反AI结构红线清单**：信息装进对话（含正反迷你示例）、问答轮次上限与岔断、动作之后不翻译、汇报链家族禁令、叙述句节奏默认（逗号长句为默认、短句仅偶尔重拍、对话不受限）、反过度条款；末尾加「素材优先」兜底行。
- 「输出契约」补两条强禁令与章末扩展：尾随标签/夹层/「不是A是B」家族/破折号零（出现即禁的强特征，每项附替代写法）；章末切点补「尾块禁令」——SHALL NOT 为末句钩子排齐证据（搭台）、禁报账式详写（时间＋次数并置）、禁事后反刍（末句后的心理复盘）。
- `prompts/prompt_crafting.prompt` 提示词骨架同步：第 8 要素「不可违反规则」优先级栈插入「反AI结构红线」档（约束红线之后、字数之前）；第 9 要素质感要求补「信息优先装进对话」口径。
- `write/chapter_writer.py` 撤销 `craft_rules` 占位注入（内容上收为模板静态文本，恒定层逐章字节一致不破）。
- 明确不做：量化指标（句长/逗号密度/对话占比数字）不进红线清单——量化目标由 style-quant 六行基线承载；书级禁词仍走文风 KV 单源；选区级去AI味升级另案（c-deai-hot-segment）。

## Capabilities

### New Capabilities

（无——规则载体是既有生成/润色两模板，不新增独立能力面）

### Modified Capabilities

- `prose-writing`: 「system 恒定层组装」覆盖清单中「写法要求」的口径扩为反AI结构红线＋质感要求；新增「反AI结构红线注入」requirement（红线家族清单、正反示例随附、与文风 KV 禁令/量化基线的边界、恒定层逐章一致不破）。
- `prompt-crafting`: 「提示词内容骨架」第 8 要素优先级栈插入反AI结构红线档、第 9 要素质感要求补信息装进对话口径。

## Impact

- `client/backend/prompts/write_chapter.prompt`、`client/backend/prompts/prompt_crafting.prompt`（模板文本改动，`<<system>>/<<user>>` 分层不破）
- `client/backend/write/chapter_writer.py`（删一处占位注入）
- 无端点/前端/门禁/依赖变化；无用户可见界面改动（免原型与 Design Impact）
- 恒定层内容变更会使供应商提示词缓存失效一次（本书下次生成重建，可接受）
- 测试影响面：`tests/test_prompt_layering.py`（通用分层闸门，预期保持绿）；`tests/` 中 chapter_writer 组装相关断言需补红线特征串检查；e2e/vitest 无模板串钉子（已核）
