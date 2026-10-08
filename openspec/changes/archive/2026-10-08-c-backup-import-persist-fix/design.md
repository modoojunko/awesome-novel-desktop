## Context

`persist_package`（`client/backend/backup/importer.py`）的现状事务形态：逐书 `db.begin_nested()`（SAVEPOINT）＋全程 `flush()`，整个 `backup/` 模块无一处 `db.commit()`。与之配套的两个实证事实（2026-10-08 排查，验证脚本镜像 `db.py` 引擎配置）：

- 书能落库靠 SQLite 方言巧合——外层无真 BEGIN 时 `RELEASE SAVEPOINT` 等价提交；一旦请求内书之前有别的写入先开真事务（如包内含配置块时 `_restore_config` 先 flush），同一形态变成整笔回滚。
- reattach 对 `novel.ai_config_id` 的赋值发生在全部 SAVEPOINT 之后，无 flush 无 commit，`get_db` 的 `async with` 关闭会话即丢弃——挂回永远不生效。

另：`_reattach_configs` 的 `unique_active` 分支守卫读 `novel.api_config_id`（不存在，模型字段为 `ai_config_id`，`models/project.py`），单 active 配置用户恢复含书包即 `AttributeError` → 500。两缺陷叠加，恢复导入对该形态自 9643b2bc 起从未可用。

测试基建（`tests/conftest.py`）：session 级 fixture 对真 `db.py` engine 建 `create_all`＋指纹戳＋钥匙初始化；现有 `test_backup_import.py` 已有最小单书包 zip 样板（project.yaml+volumes/chapters/versions）与 `_write_temp_zip` 落盘工具，可直接复用。

## Goals / Non-Goals

**Goals:**

- persist 成功返回前，书、配置、挂回三者确定性地持久化——不依赖 SQLite SAVEPOINT-RELEASE 方言行为。
- 挂回环节失败时整次恢复零残留（重试从零开始，不产生重复书）。
- 修掉 `unique_active` 守卫属性笔误。
- 用走 persist 全链、以「新开会话验证落库」为判据的回归测试钉死两处缺陷。

**Non-Goals:**

- 不改挂回策略（unique_active/by_model 判定逻辑照旧）、不改 export 侧、不改前端。
- 不追溯清理用户此前后台可能落下的重复书（书名带《（备份）》后缀者）。
- 不重构 `_import_single_book` 内部的 flush/SAVEPOINT 布局；不处理测试注释里登记的 assets 包 `book_dir` 前缀既有问题。

## Decisions

1. **显式提交＝逐书 commit＋reattach 后收尾 commit**（实现期实证修订，推翻最初设想的「单笔末尾 commit」）。实证：裸末尾 commit 兜不住「挂回异常零残留」——SQLite 下无真 BEGIN 时最外层 SAVEPOINT 的 RELEASE 即提交，且 `async with db.begin():` 显式包裹也拦不住（SQLAlchemy 对 SQLite 惰性发 BEGIN，savepoint 内 DML 绕过之，验证脚本 crash 路径书仍落库）；逐书 `await db.commit()` 让每本书的持久化成为显式事实、彻底不依赖语句顺序与方言行为，`begin_nested` 保留逐书原子（坏书回滚自身 savepoint 不拖别书）。收尾 commit 在 reattach 之后无条件执行，兜住 config-only 包（否则配置恢复永不落库）。对「书间独立失败可单独重试」无回归：失败书被 try/except 捕获标记，不入外层事务。挂回异常时已落书保持、挂回不生效（置空待选）——spec scenario「挂回异常书保持」按此修订。

2. **笔误修复只改一处读取**：`novel.api_config_id` → `novel.ai_config_id`；赋值行与 by_model 分支本就正确。不引入 getattr 兜底（宁可炸在测试里也不静默吞错）。

3. **回归钉子复刻 `get_db` 生命周期**：测试内 `async with async_session() as db` 调 `persist_package(db, ...)`——会话内不手动 commit，函数返回后会话即关闭；随后**另开新会话**断言 Novel 行存在且 `ai_config_id` 已挂。该判据在修复前天然双红（typo → 500；无 commit → 挂回丢失），是唯一直接对准 spec 新场景的写法；不采用依赖注入/TestClient 形态（现有 backup 测试均为直调函数风格，保持一致）。

4. **失败路径不新增 try/except**：异常继续冒泡给 router（现状 500），持久化语义由「只有成功路径才走到 commit」保证，router 的 422 映射（BadZipFile/KeyError/ValueError）不动。

## Risks / Trade-offs

- [挂回环节失败时已落书保持，用户重试会得到《书名（备份）》重复本] → 挂回本体仅两条 select＋属性赋值，typo 修复后可自然抛错的路径只剩基础设施故障（磁盘/锁超时），概率与代价均可接受；换取的是不依赖任何数据库方言巧合的确定性持久化。
- [显式 commit 使「带配置块时书曾整体回滚」的既有（错误）行为改变] → 该行为本身是 bug，spec 明文 persist 成功即应落库；发版说明提一句即可。
- [测试种子 ApiConfig 若缺 `status="active"` 或误用 zhuque vendor 会静默走不进 unique_active 分支，钉子假绿] → 种子显式 `status="active"`、vendor 用 deepseek；断言 `reattach.mode=="unique_active"` 前提成立。已另做两条变异检查（笔误回插→FAILED／撤全部 commit→挂回持久断言 FAILED）证明钉子双向咬合。

## Migration Plan

纯后端行为修复，无 schema/依赖变更，随下个 C端 发版带走；回滚即还原两处代码，无数据迁移。发版说明建议带一句「修复恢复导入在单模型配置下失败/挂回不生效」。

## Open Questions

（无）
