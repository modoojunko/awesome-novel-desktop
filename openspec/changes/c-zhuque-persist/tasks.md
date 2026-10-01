# Tasks：c-zhuque-persist

## 1. 后端：表＋端点

- [x] 1.1 `models/zhuque.py`：`zhuque_results`（chapter_id PK＋FK CASCADE、prose_hash、result TEXT、checked_at）；确认 PRAGMA foreign_keys 与子表同配置
- [x] 1.2 `zhuque/service.py`：成功路径 upsert（重检覆盖一行）＋响应加 `checked_at`；`get_stored_result(db, project_id, chapter_ref)` 章属主校验读取
- [x] 1.3 `zhuque/router.py`：`GET .../zhuque-result`（200 `{stored:false}`／`{stored:true, prose_hash, result, checked_at}`）；错误映射表不动
- [x] 1.4 pytest：落库/读回/覆盖一行/删章级联/未存档 stored:false/响应 checked_at；FK 级联按既有子表测试先例

## 2. 后端：备份导出/导入

- [x] 2.1 `backup/export.py`：章循环内有档写 `zhuque/{ref}.json`、无档不写
- [x] 2.2 `backup/importer.py`：`zhuque/*.json` 经 ref_to_id upsert；坏 JSON/章缺失 → warning 跳过不中断
- [x] 2.3 pytest：导出 namelist 断言（有档两章＋无档一章）；导入新章 id 恢复＋checked_at 保真＋坏档 warning

## 3. 前端：水合＋时间戳

- [x] 3.1 `useZhuqueCheck`：`checkedAt` 字段；水合（仓无该章状态→GET 单飞→setState ok／stored:false 维持 idle；失败静默；inflight 竞争守卫）
- [x] 3.2 `ProsePane`：存档水合完成的一次性 live 指纹评估（`docToProse+fingerprint→evaluateStale`）；实时失效链不动
- [x] 3.3 `zhuqueHeadStrip`：结果态免责行尾「· MM-DD 检测」（muted；无 checkedAt 不显示；stale 态不显示）
- [x] 3.4 vitest：水合填空/不覆盖已有状态/stored:false/时间戳渲染/stale 不渲染/既有回归

## 4. 验收

- [x] 4.1 `openspec validate c-zhuque-persist --strict` 过；pytest/vitest/tsc/build 全绿（存量红除外）
- [x] 4.2 真机：检测→重启→恢复彩色＋「09-30 检测」；改一字→置灰＋重检恢复；备份导出→导入新库→结果在
