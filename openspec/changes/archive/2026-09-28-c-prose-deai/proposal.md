# c-prose-deai

## Why

正文页签右栏的选区变换三件套（润色/扩写/压缩）里，「段落润色」的目标是含糊的「提升表达质量」——
对 AI 写作产品来说这是错位的：作者选一段去处理，痛点几乎从来不是「不够顺」，而是「一眼机器腔」
（排比堆叠、「不是……而是……」模板句、段尾强行升华、等长句群打拍子）。用户拍板（2026-09-28）：
正文 tab 下的段落润色，文案与功能整体改成「去AI味」。

## What Changes

- **提示词整体换目标**（`prompts/polish_text.prompt` v3.1，经提示词工程评审修复）：system＝
  「资深小说编辑专治 AI 腔」＋定义过的操作集（删/换/拆/并/调标点节奏）＋四条铁律（信息量定义含
  「空转总结不算信息量」、篇幅单向上限 110%/缩至 70% 正常、不新增剧情设定、完整输出契约——
  保持段落划分与换行、对话引号内字句原样、不含边界标记、不包裹输出）＋**恒定检查清单 0–8**
  （第 0 条＝无命中句子原样保留；四字堆叠/破折分号阈值/对仗句保后半改直陈/空泛「仿佛宛如」删
  具体比喻留/段尾升华整句删/段内长短错落/保留口语癖好＋顺手修错字/优先级全序）；user＝文风参考＋
  禁止规则（`anti_ai_rules` 单源，未配置「（无）」）＋**边界标记包裹的待处理文本**＋标注
  「禁止改写输出」的上下文语境＋检查清单指针。原「润色要求」（流畅度/语法/表达质量）退役。
- **`write/auxiliary.py` `polish_text`**：`anti_ai_rules` 空值兜底「（无）」＋`writing_style`
  空值兜底「（未配置，以原文自身文风为准）」＋分层缺失时的 system 兜底文案对齐新角色；
  端点 `/write/polish`、请求/响应形状、记账 operation=polish 全部不变。
- **前端文案**（内部标识 `mode: "polish"` 不动）：右栏行「段落润色/选中段落出润色稿」→「去AI味/选中
  段落去掉机器腔」；对照弹窗标题「段落润色」→「去AI味」、右栏标签「润色后」→「去AI味后」；采纳
  toast「已应用润色」→「已去AI味」；页脚注与注释同步。
- **测试**：后端 `test_write_transform_modes.py` 补 `TestPolish`（/write/polish 此前无直接测试）——
  200 路径锚定 v3.1 提示词（system 含「AI 腔」＋检查清单、user 含边界标记＋禁用规则「（无）」兜底）
  ＋记账；缺 selected_text 400。前端两单测断言与 e2e `prompt-pipeline.spec.ts`（去AI味采纳＝范围
  事务替换）按钮名同步。
- **specs**：prose-writing「选区变换」Requirement 改名＋去AI味口径入文（v3.1 口径：检查清单/单向上限/
  输出契约/优先级全序）；workbench 四处提及（动作清单/AI 入口唯一化/编辑态/编辑器契约）、
  prompt-crafting 辅助链提及、frontend-auth-heal 401 场景提及同步换词。
- **非目标**：AiModal 的「AI 润色」（整章提示词润色链）与设定页「润色文字文风」「简介润色」是另外
  三条同名链路，全部不动；扩写/压缩提示词不动；端点与内部 mode/operation 标识不改名；role 双注入
  （`writing_style` 叙事身份＋system 尾部「叙事角色定位」拼两次，compress/expand 同款）与长选区
  max_tokens=2048 截断风险——评审点名但涉三端点共享写法，另立小批处理。

## Capabilities

- `prose-writing`（MODIFIED＋RENAMED）：选区变换之 `/write/polish` 口径＝去AI味，注入禁用词句单源。
- `workbench`（MODIFIED×4）：右栏动作清单与三处家族提及换词。
- `prompt-crafting`（MODIFIED）：辅助链提及换词。
- `frontend-auth-heal`（MODIFIED）：非流式 401 场景提及换词。
