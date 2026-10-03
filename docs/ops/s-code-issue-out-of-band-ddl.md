# 带外 DDL 操作单：s-code-issue（发码批次单）

> 生产（DB_BACKEND=pg_http）无迁移链，DDL 为人工带外执行（既有做法，三视角体检 P1 挂账在案）。
> 本单为 s-code-issue 的一次性操作单：建 `code_batches` 表＋`codes` 加 `batch_id` 列＋预算种。
> 执行后回读验证；`code_batches` 已登记 pg_schema 自检清单（缺表/缺列/缺默认值会被 pg 自检门禁抓出）。

> **✅ 执行记录（2026-10-03，v0.26 发布前置，经 `tcb db execute` 完成＋回读验证过＋§4 杀连接）**。
> 教训一条：`budget_consumed` 初版按 `DEFAULT '0'`（字符串字面量）建列，pg_gate 判
> server_default 漂移中止部署——门禁比对的是网关 OpenAPI 归一化形态（int→str），生产
> 实际回读 `'0'::bigint` ≠ 期望 `"0"`。下文 DDL 已改为整数裸字面量 `DEFAULT 0`（回读
> 形态=`0`，与门禁期望逐字对上）。任何 numeric 列带外建列都用裸字面量，别抄 ORM 的引号。

## 1. 建 code_batches

```sql
CREATE TABLE IF NOT EXISTS code_batches (
  id              bigserial PRIMARY KEY,
  batch_id        text NOT NULL UNIQUE,
  tier            text NOT NULL,
  duration_days   bigint NOT NULL,
  count           bigint NOT NULL,
  channel         text NOT NULL DEFAULT '',
  note            text NOT NULL DEFAULT '',
  created_by      text NOT NULL DEFAULT '',
  budget_consumed bigint NOT NULL DEFAULT 0,
  created_at      timestamp DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_code_batches_batch_id ON code_batches (batch_id);
```

## 2. codes 加 batch_id（历史行为 NULL＝历史存量桶）

```sql
ALTER TABLE codes ADD COLUMN IF NOT EXISTS batch_id text;
CREATE INDEX IF NOT EXISTS ix_codes_batch_id ON codes (batch_id);
```

## 3. 预算种（剩余可发张数；加预算=显式改此值）

```sql
INSERT INTO global_config (key, value) VALUES ('codes.issue.budget', '0')
ON CONFLICT (key) DO NOTHING;
```

> 初值 0＝发码通道默认关闭；每次发放前由运营显式 set-budget 加额度（不能无限发码的执行点）。

## 4. 回读验证清单

- [ ] `\d code_batches`：列/默认值与上表一致（channel/note/created_by=''，budget_consumed='0'）
- [ ] `\d codes`：batch_id 列存在
- [ ] `SELECT value FROM global_config WHERE key='codes.issue.budget'` 返回一行
- [ ] S端 pg 自检探针通过（启动日志无 code_batches/codes 缺列告警）
