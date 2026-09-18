## 1. 修复与回归

- [x] 1.2 行为用例（先红后绿，隔离 CONFIG_FILE→tmp + monkeypatch env + `_reset_config_cache`）：① env 变更 → config 对齐并落盘（旧逻辑必红：保持旧值）② env 稳定 → 幂等不重写 ③ env 未设置 → config 手工值保留 ④ 全新文件 + env → 种子为 env 值——验证：`pytest tests/test_server_api_sync.py -q` 先红后绿
- [x] 1.1 `load_or_create_config` 同步块改「env 显式设置且 ≠ config 即对齐持久化」（幂等）——验证：1.2 全绿
- [x] 1.3 回归：`test_auth_url.py`、`test_auth_middleware_session.py`、`test_auth_local_deletion.py`——验证：全绿（config 解析链变更不扰既有断言）

## 2. 门禁

- [x] 2.1 cwd=`client/backend`：`ruff check .` 与全量 `pytest tests/ -q` 全绿
- [x] 2.2 `openspec validate c-server-api-sync --strict` 通过（skip_specs 声明下零 delta 亦 valid）
