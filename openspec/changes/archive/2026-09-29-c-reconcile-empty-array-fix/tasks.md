# c-reconcile-empty-array-fix · Tasks

## 实现（纯后端，无界面改动——Design Impact 判定免原型先行）

- [x] 1. `client/backend/archive/reconcile.py` lore 提示词：删「JSON 数组输出」「没有则输出空数组」，统一为「JSON 对象输出…没有新世界要素则输出 `{"items": []}`」；保住桩锚点短语「识别新出现或变化的世界要素」与「不要作为世界要素提案」。
- [x] 2. 同文件 hooks 提示词：「JSON 数组输出，形如…」→「JSON 对象输出，形如…」；保住桩锚点短语「对既有伏笔的兑现与推进」与「planted 输出空数组」「resolved、advanced、planted 各最多 3 条」。
- [x] 3. `_parse_json_lenient` 增加裸数组兜底（参数开关只对 lore 开启，包装为 `{"items": list}`；解析对象语义优先不变）。
- [x] 4. 失败 hint 判据：`not text.rstrip().endswith("}")` → `not text.rstrip().endswith(("}", "]"))`。

## 测试

- [x] 5. `tests/test_reconcile.py` 新增用例：
  - lore 桩回 `[]` → 跑 `_run_async` 后不落失败行（有旧失败行时被清）；
  - lore 桩回含条目裸数组 → pending 行 items 为该数组（apply 侧语义不改，断言 payload 即可）；
  - 失败行摘录为 `[]` 时 error 不含「疑似被输出预算截断」、含「parse」；
  - 既有截断用例（断在半句）仍含「疑似被输出预算截断」（回归钉）；
  - lore 提示词含 `{"items": []}`、不含「JSON 数组输出」「没有则输出空数组」。
- [x] 6. grep 全仓：旧措辞零残留；e2e 桩锚点短语（`client/frontend/e2e/reconcile.spec.ts` 两处）完好。

## 回归

- [x] 7. `cd client/backend && python -m pytest tests/test_reconcile.py -q` 全绿（含既有截断/名册/对账用例）。
- [x] 8. 前端零改动 → `design:lint`/`design:check`/`tsc` 免跑（Design Impact：无界面结构改动、不触共享段）；`e2e/reconcile.spec.ts` 存量跑绿（桩返回值未变，仅确认提示词措辞改动未破坏桩匹配）。（归档时补跑：隔离栈 rg-a607 于合后 main 795c9b63 上 2/2 绿）
- [ ] 9. 真机收尾（留待作者机上一步手工动作）：该章 lore 失败行点一次「重试」→ 转「待确认」或直接清，不再复现「失败 1」。
