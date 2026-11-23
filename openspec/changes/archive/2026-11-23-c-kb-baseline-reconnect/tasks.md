## 1. 撤回机器收窄（revocation.py）

- [x] 1.1 `plan_revocations`：`baseline_ids` 选择收窄为 `pack_version < RECONNECT_PACK_VERSION`（常量=5，模块级＋注释串起「撤回四步」操作口径）；书级副本/晋升判定（REVOKED_SRC_KEYS/evidence）不动；验证＝单测「v5 行不进计划／<5 行进计划／撤回清单命中照旧」
- [x] 1.2 `_apply` 完成路径重构：真清了 <5 行才保留撤回语义（版本归零＋retired 戳）；没清行只更新 marker 为接回态（记录版本界/清理行数）；marker 幂等跳过条件改为版本界判定；验证＝单测「纯 v5 库 boot 后行数不变且 retired 未置位／含 <5 行库被清且照旧／marker 升级后幂等」
- [x] 1.3 三调用点继承验证（boot 钩子／迁移搬运后 force／恢复备份后 force）：验证＝单测三场景「v5 行全部存活＋<5 行被清」（force=True 路径单列）

## 2. 一次性接回过渡（main.py lifespan）

- [x] 2.1 boot 钩子前插接回过渡：`kb_baseline_retired==1` 且 `kb_baseline_reconnect_done` 未设 → 删 retired 键＋落接回标记（幂等直连写）；验证＝单测「存量 retired 库启动后戳清＋标记在／二次启动幂等／无戳库零动作」
- [x] 2.2 存量迁移形态兼容：marker 为撤回完成态（无版本界）时按版本界=4 读取；验证＝单测「撤回态 marker 首次 boot 重入 _apply 清 0 行并落新语义 marker」

## 3. 同步消费验收（baseline.py 不改逻辑）

- [x] 3.1 端到端签名包测试：CI 内联包口径构造带签名的 v5 形态 manifest/latest → sync 整层替换应用、pack_version=5 记账、status 报告 version/entries；验证＝pytest 全绿
- [x] 3.2 急刹回归：手动 retired=1 时 sync/probe 跳过口径不变；验证＝单测保留既有 retired 用例全绿
- [x] 3.3 迁移相关全量回归（#1124/#1125 后基线）；验证＝迁移相关 pytest 全绿＋ruff 绿

## 4. 回归

- [x] 4.1 后端全量门禁；验证＝pytest 全量（存量环境红单独列名定责）＋ruff 绿
- [ ] 4.2 e2e 受影响面核查（知识库页/官方精选层快照）；验证＝相关 spec 通过或列名存量红
- [ ] 4.3 review-agent 全量审查；验证＝findings 收口归档

## 5. 真机走查

- [ ] 5.1 本机 0.49.3 打含本 change 的试验包装机（同版号或 0.49.4）；验证＝boot 日志出现接回过渡＋无 retired 重盖
- [ ] 5.2 周期复查拉 v5：`/api/kb/baseline/status` version=5＋entries=8197；知识库页「官方精选」层内容重现；验证＝status 快照＋页面截图入账
- [ ] 5.3 撤回硬闸抽查：撤回清单不回充＋急刹口径（可 SQL 级验证不入库）；验证＝走查记录
