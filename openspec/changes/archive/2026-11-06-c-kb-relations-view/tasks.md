# c-kb-relations-view · Tasks

## 1. 后端（小改）

- [x] 1.1 `kb/organize.py` `entry_relations` 加 `status: str = "all"` 入参（`"active"` 只回 active 行）；构造行时剔除「对端缺失或对端 status=archived」的死链行；验证：单测覆盖 active 入参过滤、归档对端剔除、缺失对端剔除、正常 out/in 双向（照 test_kb_organize.py 既有 async 模式）
- [x] 1.2 `kb/router.py` `entry_relations_api` 透传 `status` query 参数（默认 "all" 不改现行为）；验证：接口测试断言 `?status=active` 与默认两条路径（TestClient 架子照 test_novel_list_enrichment.py）

## 2. 前端

- [x] 2.1 `src/lib/kbRelations.ts`：六类标签（refines=**细化**，contradicts=相冲/depends_on=依赖/instance_of=属于/derived_from=源自/applies_to=适用于）＋按类出入向句式函数（出向「适用于 B」式、入向「B 适用于本知识」式，contradicts 对称「与 B 相冲」）；`KbOrganizePanel` 标签改 import 同源（词不变，纯重构）；`kbRelations.ts` 登记 coverage-contract；验证：tsc 过、整理面板测试照旧绿、契约自检绿
- [x] 2.2 `kbApi.ts` `entryRelations` 加 `status` 可选参数；验证：tsc 过
- [x] 2.3 `KbEntryRelations.tsx` 改造：取数传 `status=active`＋防御过滤；rel_type 渲染中文标签＋按类句式（替换英文裸键＋箭头「←」）；新可选 prop `onOpenKnowledge?(id)` 对端名可点（不传保持纯文本）；「这条不对」按钮与 merged 追溯保留不动；段落标题/提示语口径「来自知识整理」；验证：`kbEntryRelations.test.tsx` 断言改写（句式逐类、active 过滤、点跳回调触发、feedback 照旧）
- [x] 2.4 `KnowledgeBasePage.tsx` 知识视图抽屉「其他字段」段之后渲染 `<KbEntryRelations entryId={selected.id} onOpenKnowledge={...}>`（死导入转正；基线代理条目查无关系整段自然不出）；点跳回调＝selected 切换；验证：`knowledgeBasePage.test.tsx` 补渲染断言（mock entryRelations 照 vi.hoisted 局部 mock 惯例；kbBaselinePage 等同抽屉用例如触发新请求须同批补 mock 防 unhandled rejection）

## 3. 回归与验收

- [x] 3.1 后端相关 `pytest` 绿＋`ruff check` 过
- [x] 3.2 前端 `npm run coverage` 绿（组件契约数值核对；新句式分支纳入断言）；文案自查：关系句式像人话（逐类默读）、按钮动词、无内部术语、词表与整理面板同源
- [x] 3.3 真机走查项挂账随发版：点跳手感、句式可读性、整理面板→视图联动
