# Tasks：c-zhuque-clear-keyscope

## 1. 后端：DELETE 端点

- [x] 1.1 `zhuque/router.py`：`DELETE .../zhuque-result`（属主校验＋幂等删行）；service 增 `delete_stored_result`
- [x] 1.2 pytest：删行/幂等/他书 404

## 2. 前端：复合键＋清除连档删

- [x] 2.1 `useZhuqueCheck.ts`：`keyOf` 复合键单源，四仓（stateByRef/inflight/hydrated/hydrating）同批换键；`abortZhuque`/`zhuqueStoreGetState` 改双参；对外其余签名不变
- [x] 2.2 `clear()` 改 async：先 DELETE 存档（成功/404 视为已删）→ 清会话态；失败保态
- [x] 2.3 vitest：跨书同 ref 隔离、清除调 DELETE 成功后 idle、DELETE 失败保态；既有用例签名适配

## 3. 验收

- [x] 3.1 `openspec validate c-zhuque-clear-keyscope --strict` 过；pytest/vitest/tsc/build 全绿（存量红除外）
