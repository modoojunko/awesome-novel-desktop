# Design — c-hooks-advance-ledger

## 关键决策

### D1 零 DDL：复用 mentioned_chapter_id，不加「最近推进」新列

本库库文件治理**没有代内补列路径**（main.py lifespan：「指纹不符→改名 mismatch，书架空一轮，
候选带回走 migration 端点」）。加列＝库换代＝用户数据迁移，成本远超一列的价值。

`models/hook.py` 对 mentioned_chapter_id 的注释本就预留：「不参与注入与门禁判定，本期只迁
不增（**归档 UI 归写作期 change**）」。本期即写作期 change：语义扩为「最近一次被收尾认定
相关（埋/推进/收）的章」——mark_hooks_mentioned 的埋点回填（introduced==本章）维持不变，
accept 的 advanced/resolved 分支另行回填本章；两者天然幂等兼容。

### D2 payload 形状与向后兼容

```json
{
  "planted":  [{"description": "…", "evidence": "…"}],
  "resolved": [{"ref": "#H-0003", "note": "怎么收的", "evidence": "…"}],
  "advanced": [{"ref": "#H-0001", "note": "一句推进说明", "evidence": "…"}]
}
```

- ref 解析：`#H-%04d` → seq → (novel_id, seq) 唯一定位；解析失败/行不存在 → 跳过该条目
  （不 409 不中断——模型幻觉编号不应毁掉整批采纳）。
- 兼容：resolved 条目无 ref 有 description → 旧「描述包含」匹配（存量 pending 行仍可采纳，
  e2e 桩旧回复不炸）。advanced 无 ref → 忽略该条目（旧格式无此键，天然不触发）。
- planted 走既有 create_hook＋归一化查重（#589 B），不变。

### D3 prompt 对账段形态（reconcile.py hooks yield）

台账注入升级为对账块（带编号＋计划收束章），替换 #589 的纯排重列表：

```
本书已有伏笔台账（先对账：判断本章是否兑现或推进了其中条目，按编号引用；
相同或高度相似的不要重复登记为新埋）：
- #H-0003 猎血短刃来历不明（计划收束：第 4 章）
```

产出指令三段式：resolved ≤3（兑现，ref+note+evidence）→ advanced ≤3（推进=部分揭示/
强化未收，ref+note+evidence）→ planted ≤3（真新伏笔；**本章没有新悬念就输出空数组**，
宁缺勿滥）。e2e 桩依赖短语「埋下或收束了哪些伏笔」保留在首句。

### D4 「该收了」口径

- 工作台投影：planned_chapter_id 解析出的章号 ≤ 当前查看章号（卷域投影用卷末章号）。
- 设定页：≤ 主线最新章号（从 vols 树取 max(chapter)，空树不标）。
- 纯前端派生（字段已有、章号可解析），后端不出新端点字段。
- planned_chapter_id 指向的章被删（SET NULL）→ 字段空 → 不标（自然回落）。

### D5 展示位

- 设定页台账行 meta：`最近推进 · 第 N 章`＋`计划收 · 第 N 章`＋`该收了` 小标（红点/描边，
  复用 .hk-* 既有档位；不新增颜色 token）。
- 伏笔卡：卡面 meta 同步两行信息（收束记录区不动）。
- 工作台投影行：状态列前置 `最近推进 · 第 N 章 ·`（有且晚于埋点才显）＋`该收了` 标。

## 风险

- 模型把「推进」滥用为「复述剧情」→ prompt 明确「推进=对悬念的实质揭示/强化，纯提及不算」，
  evidence 强制；采纳前人审（提案制本身是闸门）。
- 编号幻觉 → D2 跳过策略＋vitest 覆盖。
- mentioned 语义被别处消费？grep 全仓仅 hooks_to_dict 输出与归档回填两处，前端未读——安全。
