# c-charlib-deconstruct-exit — 实现任务

## 1. 原型先行（已包含，偏差登记）

- [x] 场景④已在角色库原型中产出：`docs/design-c/drafts/ai-novel-c端-角色库-原型.src.html`（真「选择去向」弹窗实抓＋第三卡运行时挂载＋收录清单弹窗；自检全绿）。
- [x] ADJUSTMENTS 已登记第三卡与内联收录面板偏差（TaskDetailPage 节）。

## 2. 后端

- [x] `deconstruct/cards.py` 新模块（投影＋`card_to_book_payload`＋clean_para/role_normalize）；`apply.py` re-export 保旧符号（`_cards`/`_ROLE_MAP`/`_role_normalize`/`_clean_para`），建书循环改走 payload；存量拆书测试 85 例回归绿。
- [x] `import_from_deconstruct`（共享投影；身份键空名兜底；IntegrityError 回查幂等；rename 只碰名字/年龄；genre 继承产物；只写库）。
- [x] 两端点落地（候选带 collected；409/422/400 三分；归属校验）。
- [x] `to-library` 成功置 `exported_at`（路由层同 export 惯例）；建书不动（book_id 信号）；徽标回归用例过。
- [x] `test_charlib_deconstruct_exit.py` 9 例全绿（投影单源＋payload/幂等/rename/三状态码/exported_at/徽标/空名）；全量后端回归见汇总。

## 3. 前端

- [x] 第三卡落地（三选一；can_import=false 时面板显示原因不出清单）。
- [x] 收录面板（弹层内联，不叠第二层）：行＝名/定位/人设/性别年龄；默认全选未收录＋计数；换名开关默认勾选；成功 toast 含数量/跳过数。
- [x] 已收录行灰态禁用＋「已在库里」标注；can_import=false 显示 reason；清单唯一数据源＝候选端点（不解析 md）。
- [x] e2e UI 桩新增第 4 例（完成态→第三卡→清单灰态→关换名→提交参数断言），`e2e/character-library.spec.ts` **4/4 绿**；幂等「再次收录不新增」由后端用例覆盖（post 两次 created=0/skipped=2）。

## 4. 门禁与回归

- [x] 后端 9 新例＋全量回归（见汇总）；前端 toolsDetail 73 例／toolsApi 22 例全绿，全仓 1892 例、覆盖率四维 100%。
- [x] tsc 绿；build 绿；design:lint 唯一红＝preview.html ⚠ 存量；design:check 不覆盖 tools 页（既有口径），无新增差异面。
- [x] 文案核对过（「收进角色库」「已在库里」等，无内部术语）。
