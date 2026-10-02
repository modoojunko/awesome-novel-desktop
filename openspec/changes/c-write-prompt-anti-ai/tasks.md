## 1. 模板：write_chapter.prompt

- [x] 1.1 头部 changelog 注释行追加 v4 条目（反AI结构红线进恒定层；说明 system 段首身份句机制不受影响）
- [x] 1.2 「## 输出契约」追加第 6 条结构强禁令（尾随标签/夹层——附替代写法「动作前置或裸台词」；「不是A是B」家族——直接写B；破折号零——逗号或句号断）
- [x] 1.3 「## 输出契约」第 5 条章末切点就地扩展尾块禁令（末句搭台/报账式详写/事后反刍三禁），保持 1-6 顺序
- [x] 1.4 「## 写法要求」节改为静态反AI结构红线清单（design.md D5 文案照抄：①信息装进对话 ②问答轮次上限 ③动作之后不翻译 ④汇报链家族 ⑤叙述句节奏默认 ⑥反过度），每条带 ❌→✅ 迷你示例（真实排版换行、合成示例标注「（合成）」），末尾加素材优先兜底行，删除 `{craft_rules}` 占位符

## 2. 模板：prompt_crafting.prompt

- [x] 2.1 头部注释行加修订说明（保持 <<system>>/<<user>> 分层）
- [x] 2.2 第 8 要素「不可违反规则」优先级栈插入「反AI结构红线」档（约束红线之后、字数之前），措辞与 prose-writing「反AI结构红线注入」同源
- [x] 2.3 第 9 要素质感要求补「信息优先装进对话」与「不为凑对话占比硬造台词」
- [x] 2.4 核对锚词契约不变（任务指示/红线/质感仍在产物要素中，validate_polished_prompt 无需改）

## 3. 组装代码

- [x] 3.1 `write/chapter_writer.py`：删除 values 中 `craft_rules` 键及注入语句（约 L601），`build_system_prompt` 其余逻辑不动
- [x] 3.2 确认 `render_template` 对无占位符键无副作用（顺序 replace 语义），必要处留一行说明

## 4. 测试

- [x] 4.1 `tests/test_prompt_layering.py` 全绿（两模板保持 <<system>>/<<user>> 分层）
- [x] 4.2 chapter_writer 组装测试补断言：`build_system_prompt` 产物含结构强禁令与红线清单特征串；同书两章 system 层逐字节一致的既有断言保持绿
- [x] 4.3 prompt_crafting 相关测试（润色校验/锚词）全绿
- [x] 4.4 跑 `client/backend` 相关 pytest 子集（chapter_writer/prompt/polish 相邻文件）

## 5. 验收与收尾

- [ ] 5.1 真机抽检：同一书任选 2-3 章（含首章）生成，先跑 grep 正则机器命中率（破折号/「不是…而是」/尾随标签/夹层/汇报链特征词），人工只看机器抓不到的（末句搭台/事后反刍），与改动前对比记录，结论回填 change 目录
- [x] 5.2 `openspec validate c-write-prompt-anti-ai --specs` 通过
- [ ] 5.3 提交＋PR（标题不带硬编码 PR 号），CI 判读
