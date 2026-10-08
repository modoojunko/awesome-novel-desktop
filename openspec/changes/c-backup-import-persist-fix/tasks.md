## 1. 影响判定与基线

- [x] 1.1 双端影响判定：本变更为 C端 纯后端修复（backup/importer.py＋tests），不触任何 UI/设计词汇/共享段——design:lint、design:check、原型先行、design-cross 均不适用（依据 proposal「无 UI 改动」）。结论记入本任务勾选项即可
- [x] 1.2 基线：在 worktree 的 `client/backend` 下跑 `python -m pytest tests/test_backup_import.py -q` 确认存量全绿（解释器用主检出 `client/backend/.venv`；必须 cd 到 worktree 运行，防静默导主检出代码假绿）✓ 6 passed

## 2. 实现

- [x] 2.1 修 `_reattach_configs` unique_active 分支守卫属性笔误：`novel.api_config_id` → `novel.ai_config_id`（importer.py:938，仅此一处读取）；验证：grep 全 `backup/` 模块无 `api_config_id` 残留（`grep -rn "api_config_id" client/backend/backup/` 零命中）✓ exit=1 零命中
- [x] 2.2 `persist_package` 补显式提交——实现期实证推翻「单笔末尾 commit」（`async with db.begin()` 包裹下崩溃路径书仍被 SAVEPOINT-RELEASE 巧合提交），改为**逐书成功即 `await db.commit()`＋reattach 后收尾 commit（config-only 包也在此落库）**；失败路径不加 try/except（异常照旧冒泡）；验证：变异检查撤掉全部 commit → 挂回持久断言红 ✓

## 3. 回归钉子（tests/test_backup_import.py 新增 TestPersistDurability）

- [x] 3.1 「单配置恢复全链」用例：种 user＋恰好 1 个 active 非 朱雀 ApiConfig（vendor=deepseek、status="active"），以 `async with async_session()` 会话（不手动 commit，复刻 get_db 生命周期）调 `persist_package` 恢复最小单书包；断言返回 summary 的 reattach.mode=="unique_active" 且 attached==1 ✓
- [x] 3.2 同用例续：另开新会话断言 Novel 行存在且 `ai_config_id` 等于种子配置 id（挂回持久生效——修复前此断言红）✓
- [x] 3.3 「挂回异常书保持」用例（语义按实证修订：逐书 commit 下已落书保持，不再是零残留）：monkeypatch `_reattach_configs` 抛异常，断言 persist 冒泡且新会话中书仍在、`ai_config_id` 为空（置空待选）✓
- [x] 3.4 跑 `python -m pytest tests/test_backup_import.py -q` 全绿（含存量用例）✓ 8 passed；两条变异检查（笔误回插→FAILED／撤 commit→FAILED）证明钉子双向咬合

## 4. 回归与门禁

- [x] 4.1 全量后端套件：worktree `client/backend` 下 `python -m pytest -q`，对拍 main 基线无新增红（记录结论）✓ **2040 passed, 1 skipped**（origin/main 基线量级零新增红；2055 为在途 #736 分支口径）
- [x] 4.2 lint：`ruff check client/backend/backup client/backend/tests`（CI 钉 ruff==0.16.3 口径）零新增 ✓ ruff 0.16.3 All checks passed（修一处函数内 import 排序后）
- [x] 4.3 `openspec validate --change c-backup-import-persist-fix --strict` 通过 ✓ Change 'c-backup-import-persist-fix' is valid
- [ ] 4.4 真机冒烟（随发版）：单模型配置账号导出→导入→书架可见书且书内模型已接回；不阻塞合码
