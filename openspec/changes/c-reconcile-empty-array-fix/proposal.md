# c-reconcile-empty-array-fix

## Why

真机实锤（2026-09-29，归档第 2 章）：世界要素（lore）收尾提示词自相矛盾——要求输出形如 `{"items": [...]}` 的 JSON 对象，又写「JSON 数组输出」「没有则输出空数组」。本章没有新世界要素时模型照字面回了 `[]`，解析器 `_parse_json_lenient` 只认对象（按 `{`/`}` 截取），落成失败行；「疑似被输出预算截断」的判据（结尾非 `}`）又对这段完整短输出误诊。重试重跑同一份提示词，该章无新要素时必复现——用户被永久挂着一个修不掉的「失败 1」。

## What Changes

- lore 收尾提示词统一输出契约：唯一形状为 JSON 对象 `{"items": [...]}`；无新要素指示输出 `{"items": []}`；移除「JSON 数组输出」「没有则输出空数组」两处歧义措辞（保住 e2e 桩锚点短语「识别新出现或变化的世界要素」）。
- hooks 收尾提示词同口径顺手理顺：「JSON 数组输出」→「JSON 对象输出」（planted 空数组语义不变，e2e 桩锚点短语「对既有伏笔的兑现与推进」不动）。
- 解析兜底：`_parse_json_lenient` 对合法 JSON 裸数组也接受——仅 lore 语义按 `{"items": <数组>}` 包装；hooks 的输出契约是对象三键，裸数组仍按解析失败落失败行。
- 失败诊断修正：「疑似被输出预算截断」仅在输出结尾既非 `}` 也非 `]` 时给出；`[]` 这类完整短输出不得再被误报为截断。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `archive-reconcile`: 新增一条 Requirement「收尾产出输出契约与解析兜底」——lore 输出形状唯一化、裸数组兜底按世界要素 items 处理、截断诊断不误报完整短输出。既有 Requirement（生命周期/页签展示/采纳写回）不动。

## Design Impact

- 受影响端：无界面结构改动——本改全落 C端 后端（`client/backend/archive/reconcile.py`）＋一条失败原因文案的口径（用户可见文本，属错误诊断信息，非屏/弹层/组件改动）。
- 受影响的屏/弹层：无；工作台「设定」页签的世界要素提案区只读渲染既有字段，不改。
- 对象状态：不新增；失败行「重试」链路照旧。
- 两端共享段：不触碰（无样式/令牌/组件词汇改动）。
- 原型先行：免（无用户可见界面改动，判定依据如上）。
- 设计工件：无需求；实现侧自查。

## Impact

- `client/backend/archive/reconcile.py`：`_collect_prompts` 两段提示词、`_parse_json_lenient` 裸数组兜底、失败 hint 判据（`endswith("}")` → `endswith(("}", "]"))`）。
- `client/backend/tests/test_reconcile.py`：新增用例（lore 回 `[]` 不落失败行、`[]` 失败行无截断误报、截断提示判据、lore 提示词形状唯一断言）；既有「截断诊断」用例喂的是断在半句无收尾括号的输出，新判据下仍绿。
- `client/frontend/e2e/reconcile.spec.ts`：桩匹配短语两处锚点保留即可，桩返回值不变；存量用例应全绿。
- 存量数据：用户机上已落的 lore 失败行，重试即走新提示词＋新解析，可清。
