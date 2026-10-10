# c-carry-degrade-remigrate — tasks

## 1. 引擎降级回迁（migration/engine.py）

- [x] 1.1 5.2 步：对 rows_missing>0 且登记表已声明列的表，集合式 CASE 改写缺行重插（`INSERT OR IGNORE`），重算 rows_missing
- [x] 1.2 降级明细实名：entry `rows_degraded`＋notes「N 行按新值域降级迁入（表.列），建议检查」；无登记/无命中＝空操作
- [x] 1.3 幂等与源只读不破（重跑零重复；降级只写目标库）

## 2. 部分迁移态与缺口端点（migration/router.py）

- [x] 2.1 candidates 载荷增 `carried_partial`（last.status==ok ∧ 非完整 ∧ 指纹命中；双形态对拍复用 #812 stamps）
- [x] 2.2 `GET /gaps`：白名单校验→WAL 源暂存读取→按在场判定缺书（id 对拍）与缺配置（名对拍）；无密钥材料；失败降级空清单
- [x] 2.3 preview/start 链不受影响（gaps 纯只读，不入 job_runner 单飞）

## 3. 前端三态与缺口清单

- [x] 3.1 类型：LegacyCandidate/CarryCandidate 增 `carried_partial?`
- [x] 3.2 NovelListPage：自动弹卡条件排除 partial；常驻行条件纳入 partial（含「迁移」出口＋「本版不再提醒」）
- [x] 3.3 CarryDialog 结果卡不完整变体：拉 `/gaps` 渲染缺口清单（失败安全不阻塞）

## 4. 测试

- [x] 4.1 引擎降级 e2e：目标 chapters 加 CHECK（重建表法），源含旧值域行→映射落库＋notes＋完整；无映射→缺行＋不完整
- [x] 4.2 candidates partial 单测（ok+不完整→true；无记录→false；完整→false）
- [x] 4.3 gaps 端点链（缺书实名/配置名/无密钥材料/已迁入不出现）
- [x] 4.4 前端：partial 不自动弹卡＋常驻行在；CarryDialog 缺口清单渲染
- [x] 4.5 登记表初始空（本 change 未新增映射条目）；#814 样本重放在全量套件内保持绿

## 5. 门禁

- [x] 5.1 pytest 全量＋ruff＋vitest＋tsc；openspec validate
- [x] 5.2 PR（叠 #812，合后 retarget）＋CI 绿
- [x] 5.3 真机验收：部分迁移后书架不再重弹整卡、提醒行可达、缺口清单可读
