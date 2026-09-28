# Tasks

## 1. 后端（提示词换目标）

- [x] 1.1 `prompts/polish_text.prompt` 重写 v3：system＝去AI味编辑角色＋四铁律＋输出契约；user＝文风参考＋禁止规则（`{anti_ai_rules}`）＋待处理文本＋上下文＋「去AI味要求」清单；验证：分层标记在位（`test_prompt_layering` 名单内）、占位符与 ctx 键一致
- [x] 1.2 `write/auxiliary.py` `polish_text`：`anti_ai_rules` 空值兜底「（无）」＋分层缺失 system 兜底对齐新角色；验证：通读 diff，端点/记账不动
- [x] 1.3 `tests/test_write_transform_modes.py` 补 `TestPolish`：200 锚定「去AI味要求」＋「（无）」＋system「AI 腔」＋operation=polish；缺 selected_text 400；验证：pytest 该文件全绿

## 2. 前端（文案）

- [x] 2.1 `AiAssistPanel.tsx`：行名「去AI味」＋desc「选中段落去掉机器腔，对照预览后替换」＋页脚注＋注释；验证：grep 段落润色 零残留
- [x] 2.2 `ContrastPreviewModal.tsx`：标题「去AI味」、对照标签「去AI味后」、头注释；`ProsePane.tsx`：toast「已去AI味」＋两处注释；验证：grep 润色 仅剩 AiModal/设定页等他链
- [x] 2.3 断言同步：`AiAssistPanel.test.tsx`、`NovelWorkspace.test.tsx` 按钮 name；e2e `prompt-pipeline.spec.ts` 用例名＋按钮；验证：vitest 两文件绿（e2e 待栈）

## 3. specs 与门禁

- [x] 3.1 delta 四件：prose-writing（RENAMED＋MODIFIED，去AI味口径入文＋新场景）、workbench×4、prompt-crafting、frontend-auth-heal；验证：`openspec validate c-prose-deai --strict`
- [x] 3.2 门禁：pytest 相关子集（transform/layering/routes_contract/write_regressions/prose_pipeline）＋vitest 相关子集（AiAssistPanel/NovelWorkspace）全绿；全量 e2e 与真机验证待合入后另跑
