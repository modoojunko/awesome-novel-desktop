# 任务：dev 哨兵分流件纳入迁入候选

## 1. 形状枚举

- [x] 1.1 `client/backend/schema_version.py`：新增 `SENTINEL_DISPOSED_RE`（`^novel-dev\.db\.(mismatch|corrupt)-[0-9TZ:._-]+$`），`parse_db_filename` 在 gen0 判断后、`_DISPOSED_RE` 前插入分支——mismatch → `DBName("mismatch")`（version/generation 均 None），corrupt → `DBName("corrupt")`。验证：`python3 -c` 直调 parse 断言三形状（dev mismatch/dev corrupt/残件 None）。
- [x] 1.2 既有 `novel-v{X}` 路径回归：`_DISPOSED_RE`/`_NOVEL_V_RE` 行为零变化。验证：`pytest tests/test_db_lifecycle.py -q` 全绿。

## 2. 测试

- [x] 2.1 `tests/test_db_lifecycle.py` 新增：parse 三例单测＋scan 集成用例（tmp 目录造含 1 书的 `novel-dev.db.mismatch-<stamp>` → `scan_migration_candidates` 命中且 book_count=1；空壳分流件不进候选；`novel-dev.db.corrupt-*` 不进候选）。验证：新用例绿。
- [x] 2.2 全量后端门禁。验证：`cd client/backend && <venv-python> -m pytest tests/ -q` 全绿。

## 3. 收尾

- [x] 3.1 spec sync（归档时）：`openspec/specs/db-generation/spec.md` 按 delta 落两处 MODIFIED（「迁入候选与找回向导」白名单条款＋「库文件版本命名与首启状态机」分流形状条款）。验证：`openspec validate --strict` 通过。（2026-09-28 归档批执行：openspec archive 随档落 sync，validate --strict 全绿）
- [ ] 3.2 真机演练（可选，不拦合入）：dev 容器造旧指纹哨兵库→首启分流→向导可见→一键带回。验证：演练记录贴 `evidence/`。
