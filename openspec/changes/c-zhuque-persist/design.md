# Design：c-zhuque-persist

## D1. 表与模型（走 Base.metadata，不做带外 DDL）

新模型 `models/zhuque.py`：`ZhuqueResult` → 表 `zhuque_results`：

- `chapter_id` VARCHAR PK，`ForeignKey("chapters.id", ondelete="CASCADE")`（同 `chapter_reconcile` 子表形态）；
- `prose_hash` VARCHAR(64) NOT NULL、`result` TEXT NOT NULL（完整响应 JSON）、`checked_at` DATETIME NOT NULL。

建表机制（实勘）：C 端一代一库＋指纹门禁（c-db-per-version）——打包版随下一代库 create_all 自然建表；dev 哨兵库加表后指纹失配走既有 dev 分流语义（候选可带回）。**显式不做带外 DDL**（aab9296 前车之鉴）。本表零存量迁移（新表起空）。

## D2. 服务与端点（zhuque/service.py＋router.py）

- `check_chapter` 成功路径尾部 upsert（INSERT OR REPLACE 语义＝同章一行；`checked_at=datetime.now(UTC)`），响应加 `checked_at`；失败路径不落库。
- `GET /api/novels/{pid}/chapters/{ref}/zhuque-result`（挂 get_current_user＋章属主校验，复用 check 端点的章解析）：无档 `{stored: false}`；有档 `{stored: true, prose_hash, result(JSON 反序列化), checked_at}`。只读，零额度。
- 删章级联：FK CASCADE 兜底（SQLite 需确认 PRAGMA foreign_keys 与既有子表同配置——chapter_reconcile 同款即成立）。

## D3. 备份导出/导入（用户拍板：备份＝完整资料迁移）

- **导出**（`backup/export.py dump_book_into`）：卷/章循环内，有档章写 `zhuque/{ch.ref}.json`（`{contract?, prose_hash, result, checked_at}`）；无档不写（与 settings 树「非空才写」同口径）。归档循环解耦纪律不涉及（本表天然章粒度）。
- **导入**（`backup/importer.py _import_single_book`）：扫 `zhuque/*.json`，经既有 `ref_to_id` 重映射 upsert（章不存在→warning 跳过）；坏 JSON→warning 跳过不中断（SHALL）。配置包（config zip）不含检测数据。

## D4. 前端：水合＋载入即失效评估＋时间戳

- **水合**（`useZhuqueCheck`）：hook 首次订阅且 `stateByRef` 无该章状态时 GET 一次（模块级 in-flight 防抖，跨消费点单飞）；`stored: true` → `setState(ref, {status:"ok", result, proseHash, stale:false, checkedAt})`；`stored: false`/请求失败 → 维持 idle（失败静默，不打扰）。会话仓仍是运行期单源——水合只填空，不覆盖已有状态（正在 running/已有 ok 均不动）。
- **载入即 stale 评估**（ProsePane）：现有失效链只挂在 docChanged 事务上；补一个「存档水合完成后」的一次性评估——`zqState.status==="ok"` 且来自水合（checkedAt 有值即可作为信号）时，用现有 `docToProse+fingerprint` 算 live 指纹调 `evaluateStale`。指纹一致 → 彩色恢复；不一致 → 置灰。实时编辑失效链不动。
- **`ZhuqueState` 增 `checkedAt?: string`**；`run()` 成功后从响应 `checked_at` 填充。
- **结果条时间戳**（`zhuqueHeadStrip`）：结果态免责行尾加 `· MM-DD 检测`（muted；MM-DD 取本地时区；无 checkedAt 不显示）。stale 态不显示时间（置灰语义优先）。

## D5. 边界与错误

- GET 失败/超时 → 静默降级为无存档（检测功能不受影响，控制台 warning）。
- 存档 result 与当前后端响应字段演进：水合按现有消费字段读（summary/segments/prose_hash），多余/缺失字段容忍（JSON 原样存取，不重编码）。
- 会话内重检（running 中切走再回来）：既有 prev 恢复逻辑不变；水合不与 inflight 竞争（水合前查 inflight）。

## D6. 测试

- 后端：落库/读回/重检覆盖（一行断言）/删章级联/响应含 checked_at；备份含 `zhuque/*.json`（namelist 计数，zip 同名断言教训）＋无档不写；导入重映射（新章 id）＋坏 JSON 跳过 warning＋章缺失跳过。
- 前端 vitest：水合填空（仓空→GET→ok）、仓有状态不覆盖、stored:false 维持 idle、checkedAt 渲染「MM-DD 检测」、stale 态不渲染时间、既有用例回归。
- e2e 不新增（恢复链路 vitest＋真机覆盖）。
