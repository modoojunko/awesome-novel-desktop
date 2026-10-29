# c-charlib-deconstruct-exit — 设计

## Context

见 proposal.md「Why」。现状：拆书完成详情「选择去向」弹层二选一（建书/存本地文件夹）；建书消费 `deconstruct/apply.py` 的 `_cards` 投影（证据剥除、persona 兜底合成、role 白名单归一、跨批同名合并、路人过滤）与 `settings_map` 清洗；任务徽标口径＝进行中＋排队中＋已完成未取结果（`exported_at` 为唯一写点）。角色库（c-character-library）提供账号级库表与七端点。

## Goals / Non-Goals

**Goals**：第三出口最小侵入地接进既有弹层；收录与建书共用同一投影（单源）；幂等；三出口统一「已取结果」口径。

**Non-Goals**：关系边入库；收录时选分类；从库反查任务回写；批量跨任务收录。

## Decisions

**D1 投影单源（含扁平格→dossier 组装）**：把 `apply.py:_cards`（及其依赖 `settings_map.clean_settings_text`）与建书循环里的 `card_to_book_payload`（name/role/persona/aliases/扁平 plot/background/faction/look/speech/gender/age/race → 书内 dossier 组装）一并提为 `deconstruct/cards.py`，建书与收录共用；`apply.py` 保留 re-export，`scripts/deconstruct_product_check.py` 与 `tests/test_deconstruct_resilience.py` 的 import 同批改。理由：只统一清洗层而让收录另写映射，仍会出现「清单有、入库变形」。附带口径：投影丢弃路人（`_cards` 现有过滤），清单与收录同口径剥掉 confidence。

**D2 收录幂等靠 provenance**：`src_kind=deconstruct`＋`src_ref=task_id`＋`src_character_id`（源角色在产物中的身份键＝归一后名字，任务内唯一）＋部分唯一索引；重复收录返回已有卡。清单行「已收录」态由库侧一次性查询该任务的收录集合。

**D3 出口语义与端点**：`GET /tasks/{id}/library-candidates`（投影候选＋已收录集合＋can_import/reason——前端清单只消费它，禁止解析 md）；`POST /tasks/{id}/to-library`（任务未完成 409、characters 产物缺失 422、picks 为空 400；身份键空名兜底；`ON CONFLICT DO NOTHING` 回查幂等）；成功后置 `exported_at`——注意徽标是双信号口径（建书靠 `book_id`、导出与收录靠 `exported_at`），建书出口不改。弹层第三卡与既有两卡同形（`.ex-fmt`），三选一互斥；「收进角色库」不受结果目录文件勾选集约束（按角色维度消费，清单内独立勾选）。收录不挂档位门：拆书完成页本身已在 PRO 门后（记录为豁免理由，与 export 端点的 require 不冲突）。

**D4 门禁**：拆书完成页本身已在 PRO 门后（`deconstruct` 档），收录不另挂档位（design 记录豁免理由：消费对象是任务产物，入口已有门）；记录「不新增售卖面」以便后续审计。

## Risks / Trade-offs

- [_cards 提取触碰建书路径（回归面）] → 纯函数搬移＋两处调用点同批替换；收录/建书同输入输出一致性用例钉住（golden 对照）。
- [产物里同一角色名在不同批次写法不一] → 复用 `_dedupe_cards` 合并规则；身份键取合并后的主名，幂等键稳定。
- [勾选与「换名换龄」组合导致同名] → 姓氏池随机＋库内允许重名（来源区分）；无需额外去重。

## Migration Plan

无数据迁移；新端点与 UI 随版本发布。回滚＝移除第三卡与端点（库表留存无影响）。

## Open Questions

- 收录清单是否显示「已收录」灰态并默认不勾——实现期按 TaskDetailPage 现有清单组件能力定，行为已在 spec 钉（幂等返回已有卡）。
