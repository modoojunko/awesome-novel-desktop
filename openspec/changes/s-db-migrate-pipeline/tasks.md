## 1. 双端影响判定与前置核查

- [x] 1.1 双端影响判定：本 change 纯 S端 后端（迁移链/启动/CI），不触前端、不触共享段、无用户可见界面改动——proposal 的 Design Impact 判定为「不适用」，无需原型先行（对照 openspec/config.yaml tasks 规则）
- [x] 1.2 全仓检索 `c4d5e6f7a8b9`、`a1b2c3d4e5f6`、`upgrade <revision>` 的引用（脚本/文档/runbook），列出需要同批更新的位置——`grep -rn` 结果贴进 change 目录

## 2. 迁移链线性化

- [x] 2.1 `a1b2c3d4e5f6_users_deletion.py` 的 `down_revision` 改为 `e8f2a4b6c8d0`，`alembic heads` 输出恰一个 head——命令输出贴进 change 目录
- [x] 2.2 新增迁移可升级性测试（fresh sqlite `upgrade head` 后逐表逐列对拍 `Base.metadata`），断言 users 含注销四列、codes 含 refund_requested——`pytest server/tests/ -k upgrade` 绿
- [x] 2.3 反向验证：临时把 2.1 的 down_revision 改回旧值跑 2.2 的测试，确认测试变红（证明测试真能拦住顺序错误）——红→绿过程记录在 change 目录

## 3. sqlite 启动迁移 fail-closed

- [x] 3.1 `server/app/main.py` 迁移失败分支由 warning+create_all 改为 error 日志 + 拒绝启动；`create_all` 仅在迁移成功后保留——代码 diff 与启动日志样例贴进 change 目录
- [x] 3.2 新增/更新测试：注入迁移失败（monkeypatch upgrade 抛异常）断言启动被拒绝——`pytest` 绿
- [x] 3.3 正常路径验证：fresh sqlite 启动照常（日志含迁移结果），既有 server 测试全量 `pytest server/tests` 绿

## 4. 生产 DDL 单源

- [x] 4.1 新增 `pg_schema.REQUIRED` ↔ `Base.metadata` 对拍测试（模型有而清单无即红，豁免须显式登记）——`pytest` 绿；首次跑出的漏项清单贴进 change 目录并逐项补齐或登记豁免
- [x] 4.2 新增生成脚本（`server/scripts/`）：按缺失项输出 `ALTER TABLE ... ADD COLUMN` / `CREATE TABLE` DDL（元数据类型编译）——脚本对一条真实缺失项产出可执行语句，输出样例贴进 change 目录
- [x] 4.3 部署门禁恢复路径文档更新（`s-server-deploy.yml` 注释/runbook 指向生成脚本），不再提手写等价 SQL——diff 贴进 change 目录

## 5. CI 门禁

- [x] 5.1 `server-backend-ci` 路径过滤纳入 `server/alembic/**`——workflow diff 贴进 change 目录
- [x] 5.2 新增 `alembic heads` 单头断言步骤（恰一个 head，否则失败）——本地模拟多 head 验证断言会红，记录贴进 change 目录

## 6. 时间口径清理（S端）

- [x] 6.1 `refund_flow.py`（4 处）与 `interfaces/web_api/payments.py`（1 处）的 `datetime.utcnow()` 改为 `datetime.now(UTC).replace(tzinfo=None)`——`grep -rn "utcnow" server/app` 零命中
- [x] 6.2 时间口径抗性测试回归：`pytest server/tests/test_timezone_discipline.py` 绿

## 7. 回归

- [x] 7.1 `pytest server/tests`（全量）输出结论贴进 change 目录
- [x] 7.2 `ruff check server` 输出结论贴进 change 目录
- [x] 7.3 本 change 无前端改动，`npm run design:lint`/`design:check`/`vue-tsc` 不适用（判定依据见 1.1）
