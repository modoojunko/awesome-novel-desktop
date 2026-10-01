# Tasks: s-code-issue

## 1. 双端影响判定（纯 S端 后端＋脚本，无 UI）

- [x] 1.1 判定登记：本 change 不含任何用户可见界面改动（S端 前端、C端 零触碰，无共享段、无组件词汇/状态档位变化）——依据 proposal「Design Impact」段；门禁义务仅剩双端 tsc 不适用（未触前端），设计 lint/check 不适用

## 2. 数据模型与 DDL

- [x] 2.1 ORM：`models/code.py` 新增 `CodeBatchORM`（code_batches：batch_id/tier/duration_days/count/channel/note/created_by/budget_consumed/created_at），`ActivationCodeORM` 加 `batch_id`（nullable，索引）；sqlite 侧随既有建表路径生效（pytest 现有 fixture 起库即建）
- [x] 2.2 pg 自检登记：`pg_schema.py` 表清单登记 `code_batches` 全列＋`codes` 列清单补 `batch_id`；跑 pg 自检相关单测确认无缺列告警（pytest -k pg_schema 绿）
- [x] 2.3 生产带外 DDL 操作单落 `docs/ops/`：建 code_batches＋ALTER codes ADD batch_id（含索引）＋global_config 播种 `codes.issue.budget` 两条 SQL＋执行核对清单（标注：生产无迁移链，人工执行并回读验证）

## 3. S端 摘除发码管理面

- [x] 3.1 删 `server/app/interfaces/admin_api/codes.py`（admin_api/__init__ 或 router 的 import 同步撤，admin_api 仅剩 deletion）；`dto.py` 删 `GenerateCodeRequest`/`QueryCodesRequest`；grep 全仓两符号零残留
- [x] 3.2 测试迁移：`server/tests/test_web_api.py` 发码用例（含错误 token 用例）删除或改为码表直灌种子；`conftest.py:94` 一带的 generate_code 种子改直灌 code_repo；`pytest server/tests` 全绿（确认无隐性依赖 admin 发码端点的用例存活）

## 4. 发码脚本 scripts/code_issue.py

- [x] 4.1 骨架：复用 `pg_http` PgRestClient（env：TCB_PG_ENV_ID/TCB_PG_API_KEY）＋`global_config` 表名常量；子命令框架 new-batch/show/show-code/list/revoke/set-budget；`--help` 即操作文档（每子命令带示例）
- [x] 4.2 new-batch：--tier 查 tiers 表校验（status=live，拒绝时列出可发档位）；--days 必填 1–365（>365 须 --force）；--count/--channel/--note；生成 `AC-` 码号＋批次单＋codes 行（source=admin、batch_id、duration_days）＋trade_events `codes:{batch_id}:issued`；预算 CAS 扣减失败→当场回收本批码行＋删批次单＋整体失败退出码非零
- [x] 4.3 revoke：WHERE 恒带 status='unused'＋--reason 必填；active 码请求拒绝并说明已绑定用户；作废结果回显批次三态变化
- [x] 4.4 show/list/show-code：单内三态计数＋明细＋对账不变式校验（count==budget_consumed==实插行数，不平输出 err 告警）＋「在外未兑 N 张/合计 X 天（分 tier）」负债行＋存量桶（batch_id 为空）单独列示；--csv 导出；show-code 按一枚码反查批次/状态/归属/激活时间
- [x] 4.5 脚本单测（MockTransport 直测 pg 分支，套路上同 s-security-hardening）：预算足够/不足整批拒绝且零残留/CAS 失配回补/对账不变式触发告警/revoke 收窄两态/档位校验拒绝/天数护栏与 --force/三态统计含存量桶（pytest -k code_issue 绿）

## 5. 回归与冒烟

- [x] 5.1 后端全量 `pytest server/tests` 全绿；S端 前端零改动故 vue-tsc/design:lint 不适用；design-cross 不适用（未触共享段，依据任务 1.1）
- [x] 5.2 隔离栈端到端冒烟（每会话独立环境，sqlite 后端 18901 全新库）：alembic 迁移 b5c6d7e8f9a0 真建 code_batches＋codes.batch_id（修一处迁移缺陷：sqlite 自增主键须 Integer variant，同 a002 套路）→按脚本同形态播种批次单＋2 枚码→S端 /api/pay/codes/redeem 兑换其一（小写归一化、顺延起算、CAS 落行）→三态翻转 1 active/1 unused、预算不被兑换消耗。**脚本对真 PostgREST 的请求形态已由 MockTransport 单测钉住（真客户端发真 HTTP）；生产 CloudBase 侧待带外 DDL 执行后按操作单回读＋list 冒烟收尾**。teardown 完成（端口清零）
