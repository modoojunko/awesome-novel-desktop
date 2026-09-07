# entitlement-sync 生产上线脚本与发版清单（c-s-entitlement-sync）

> 执行前提：用户拍板发版。所有命令在生产 PG（CloudBase）控制台/MCP `managePgDatabase`（execute 需 confirm=true）执行。
> 顺序铁律：**DDL → 种子 → pg_gate 验证 → S端 部署 → C端 发版**。新代码对缺列容忍（读不到走 DEFAULTS），但 pg_gate/启动自检会因 REQUIRED 缺列拦部署——所以 DDL 必须先行。

## 1. DDL（加列）

```sql
ALTER TABLE tiers ADD COLUMN entitlement TEXT NOT NULL DEFAULT '{}';
```

## 2. 种子（pro 档位权益；max 留 '{}' 走 DEFAULTS）

```sql
UPDATE tiers SET entitlement = '{"features":["settings-ai-fields","outline-advanced-fields","ai-generate","prompt-panel","ai-model"],"limits":{"max_projects":null}}'
 WHERE key = 'pro';
```

对拍（应返回 1 行且内容一致）：

```sql
SELECT key, entitlement FROM tiers WHERE key = 'pro';
```

## 3. pg_gate 验证

```bash
# 容器/本机带 TCB_PG_ENV_ID / TCB_PG_API_KEY 执行（REQUIRED 含 tiers.entitlement 后，缺列会 FAIL）
python scripts/pg_gate.py
```

预期：success（tiers 列对拍含 entitlement，EXPECTED_DEFAULTS 对拍含 `"{}"`）。

## 4. S端 部署

tag v* 或 workflow_dispatch（s-server-deploy 门禁线）。部署后探活：

```bash
curl -s "https://www.awesomenovel.com/api/check-auth?pc_hash=probe" | head -c 200
# 预期 code=1（未授权）——证明服务活着即可；entitlement 在 code=0 才出现
```

真值验证（可选，MCP 设备码登录后）：

```bash
# 用已授权 pc_hash 调 check-auth，data 应含 "entitlement":{"v":1,...}
```

## 5. C端 发版（闭环必要条件）

打 tag 走 client 打包通道（-a 带附注，格式见 tag-annotation-format）。**老 C端 收到新字段无感，但仍判免费——用户侧真正解锁靠新版 C端。**

## 6. 回滚

- 代码回退：纯新增字段，revert 后老代码忽略列，无副作用
- 列保留无害，无需 DROP（若坚持清理：`ALTER TABLE tiers DROP COLUMN entitlement;`——不建议，会再触发一次 schema 变更风险）

## 7. 本地 docker S端（sqlite）对齐

```bash
docker exec ai-novel-server-backend python -c "
from app.models.base import engine
from sqlalchemy import text
try:
    engine.execute(text(\"ALTER TABLE tiers ADD COLUMN entitlement TEXT NOT NULL DEFAULT '{}'\"))
    print('column added')
except Exception as e:
    print('skip:', e)"
```

（SQLAlchemy 2.x 用 `with engine.begin() as c: c.execute(text(...))`；列已存在则 skip。）
