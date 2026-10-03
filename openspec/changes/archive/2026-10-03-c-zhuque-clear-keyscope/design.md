# Design：c-zhuque-clear-keyscope

## D1. 复合键（跨书隔离）

`useZhuqueCheck.ts` 模块级状态全部换 `${projectId}:${chapterRef}` 复合键：

- `stateByRef` / `inflight`（含 prev）/ `hydrated` / `hydrating` 四个仓同键；
- `keyOf(projectId, chapterRef)` 单源；对外签名不变——`runZhuqueCheck(projectId, chapterRef)`、`abortZhuque(...)` 改收双参（hook 内部 cleanup 与 AiAssistPanel 唯一直调点同批）；
- `zhuqueStoreGetState`/`zhuqueStoreReset`（测试辅助）：GetState 改双参，Reset 零参全清不变。
- 键取 `project_id + chapter_ref` 而非章 UUID：ref 书内唯一，复合即全局唯一；章 UUID 前端不持（消费点只有 projectId/chapterRef），后端端点本就以书为界解析 ref——DB 层 `zhuque_results` 仍按 chapter_id 主键，无需迁移。

## D2. 清除连档删

- 后端：`DELETE /api/novels/{pid}/chapters/{ref}/zhuque-result`（result_router 兄弟路由）：get_novel 属主校验＋ref 校验同 GET；删 `zhuque_results` 行（无行也 200 `{ok: true}` 幂等）；不触上游。
- 前端：hook `clear()` 改 async——先 `api.delete(.../zhuque-result, {quiet})`（成功/404 均视为已删），再 `setState(key, null)`；DELETE 失败（网络/非 404 错误）**不清会话态**（避免「屏上清了、重启复活」的割裂），错误经既有失败通道提示。
- strip 的「清除标注」按钮调 hook 的 clear（AiAssistPanel 转传）——确认其当前是直调 clear 回调（签名不变，内实现变 async）。

## D3. 测试

- 后端：DELETE 删行/幂等/属主 404；roundtrip 不受影响（备份不写已删档）。
- 前端 vitest：跨书同 ref 隔离（A 书 ok 态不顶 B 书 idle 水合）；清除调 DELETE 且成功后 idle；DELETE 失败保持 ok 态；既有用例键语义随双参签名更新。

## D4. 边界

- DELETE 与检测并发：在途检测成功后 upsert 可能在 DELETE 后落档——沿用「最后写赢」语义，spec 不加锁（桌面单用户，窗口毫秒级）。
- 水合水位复合键化后，同书同 ref 行为与现状全同。
