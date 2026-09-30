# c-char-list-sync-on-save Tasks

## 1. 保存落库后同步角色树（CharacterManager.tsx）

- [x] 1.1 `flushQueue` 成功排空保存队列后补 `await reloadList()`，内层 try/catch 吞列表同步失败（不翻转已成功的保存态）；deps 补 `reloadList`。完成证据＝diff 上 main（#618=644efe3a）。

## 2. 回归测试

- [x] 2.1 新增 `CharacterManager.roleRegroup.test.tsx` 两例：①配角→反派落库后行归入反派组、配角组清零，断言列表接口二次调用（首载＋落库后同步）；②改名后左侧行名同步。均走真实防抖时序（600ms 防抖，waitFor 3s 余量）。完成证据＝vitest 该文件 2 例绿。

## 3. 门禁与交付

- [x] 3.1 CharacterManager 四测试文件 22 例绿；`tsc` 零错误；全量 vitest 1009 绿（余 3 红＝已知存量红 `CharacterManager.adopt×3`，合流后复核仍红，与本改无关）。完成证据＝各命令实际输出结论。
- [x] 3.2 评审（review-agent）：零 finding；残余风险（在途列表 GET 与删除/合并 reload 乱序需百毫秒级人手时序、`doDelete` 既有双取同款竞态）低于处置门槛，登记不修。
- [x] 3.3 PR #618 admin squash 合入（CI 基建秒挂按先例）；本地 main 对齐 644efe3a；归档时 sync character-settings MODIFIED。
