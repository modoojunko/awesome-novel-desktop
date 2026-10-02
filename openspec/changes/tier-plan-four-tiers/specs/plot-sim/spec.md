## MODIFIED Requirements

### Requirement: 推演端点与素材口径

- 系统 SHALL 提供 `POST /api/novels/{project_id}/chapters/{chapter_ref}/simulate`，产物为 `{ok, source, entry, exit, prev_label, cast, rounds}` 结构：`rounds` 每回合含 `n/beat/who/place/time/at/shift/moves`，`moves` 恰两条（`k=顺 tone=ok` / `k=拗 tone=warn`，`label` 与 `out` 由服务端定形）。
- 推演素材 SHALL 取：本章章纲留存字段（概要/碰到的挑战/本章在卷剧情里的位置/剧情条目/出场角色/主情绪/必须维持悬念/必须完成的变化）与上一章结尾（正文末段优先、章纲概要兜底；无上一章时用「开书第一章」固定句）。**已退役字段（关键事件/地点/时间/预期策略/预期细节/场景卡/本章行动/段落规划）SHALL NOT 进入素材；此前素材中的「场景」行（地点/时间）随之出局，章面处境由剧情条目与概要承载。**
- `entry` SHALL 为上一章结尾处境（正文末 60 字内或上一章概要），`exit` SHALL 取本章「必须完成的变化」首条（缺省回落章纲概要）。`prev_label` 取「第 N 章」或「开书」。
- 端点 SHALL 挂 feature key `ai-plot`（仅 MAX 发放——剧情规划上收 MAX，2026-09-30 拍板）＋本书模型就绪双门控（403 feature_required 契约见 tier-access）；拦截时 SHALL NOT 发生任何模型调用。
- 调用已发生（成功或失败）SHALL 按既有记账契约留痕；模型未就绪（调用未发生）SHALL NOT 记账。

#### Scenario: 推演出结构化回合
- **WHEN** MAX 用户对一章（有章纲、有上一章）发起推演
- **THEN** 返回 2-4 个回合，每回合含关键事件、在场（角色·地点·时间）、本回合落下与顺/拗两条走法；回合按本章剧情条目顺序推进，首回合起点承接上一章结尾

#### Scenario: 免费档拦截
- **WHEN** 非 MAX 档位用户（免费/试用/标准/PRO）发起推演
- **THEN** 返回 403 feature_required（tier_required=max），且没有任何模型调用发生

#### Scenario: 退役字段不入素材
- **WHEN** 某章历史数据里存有关键事件或预期策略，发起推演
- **THEN** 模型素材与响应均不含这些退役字段的内容
