# plot-sim Specification

## Purpose

按回合剧情推演契约（storyline.html 四期尾）：AI 以上一章结尾为起点、按本章章纲关键事件把本章推演成 2-4 个回合（每回合含顺、拗两条走法结果句）；AI 不可用时回落原型同款确定性推演。产物只返回不落库；「收进章纲」由前端把走法行写入本章「预期策略」字段。

## ADDED Requirements

### Requirement: 推演端点与素材口径

- 系统 SHALL 提供 `POST /api/novels/{project_id}/chapters/{chapter_ref}/simulate`，产物为 `{ok, source, entry, exit, prev_label, cast, rounds}` 结构：`rounds` 每回合含 `n/beat/who/place/time/at/shift/moves`，`moves` 恰两条（`k=顺 tone=ok` / `k=拗 tone=warn`，`label` 与 `out` 由服务端定形）。
- 推演素材 SHALL 取：本章章纲（概要/关键事件/场景/出场角色/核心任务/预期策略/主情绪/必须维持悬念/必须完成的变化）与上一章结尾（正文末段优先、章纲概要兜底；无上一章时用「开书第一章」固定句）。
- `entry` SHALL 为上一章结尾处境（正文末 60 字内或上一章概要），`exit` SHALL 取本章「必须完成的变化」首条（缺省回落章纲概要）。`prev_label` 取「第 N 章」或「开书」。
- 端点 SHALL 挂 AI 门控（PRO 与本书模型就绪双门控，与全站 AI 端点同口径）；拦截时 SHALL NOT 发生任何模型调用。
- 调用已发生（成功或失败）SHALL 按既有记账契约留痕；模型未就绪（调用未发生）SHALL NOT 记账。

#### Scenario: 推演出结构化回合
- **WHEN** PRO 用户对一章（有章纲、有上一章）发起推演
- **THEN** 返回 2-4 个回合，每回合含关键事件、在场（角色·地点·时间）、本回合落下与顺/拗两条走法；回合按章纲关键事件顺序推进，首回合起点承接上一章结尾

#### Scenario: 免费档拦截
- **WHEN** 免费档用户发起推演
- **THEN** 返回 403（会员门控），且没有任何模型调用发生

### Requirement: AI 产物清洗与确定性兜底

- 服务端 SHALL 对 AI 产物做结构清洗：`beat/ok/warn` 三者缺一即丢整回合；回合数上限 4；文本字段去空白并截断超长。
- AI 调用失败（超时/异常）或产物清洗后为零回合时，端点 SHALL 回落原型同款确定性推演：关键事件环（章纲关键事件截取前 4；缺失回落核心任务，再回落固定句）＋模板走法（顺＝事件按章纲落地、主情绪不变；拗＝多出一次波折并压紧悬念）＋预期策略/必须完成的变化承接，并以 `source=fallback` 标注；AI 产物合格时 `source=ai`。
- 兜底 SHALL 保证弹窗永远可用——端点 SHALL NOT 因 AI 失败对用户报错。

#### Scenario: AI 产物不可解析时回落
- **WHEN** 模型返回非 JSON 文本
- **THEN** 返回 200 且 `source=fallback`，回合由章纲关键事件确定性生成

#### Scenario: 回合数上限
- **WHEN** AI 返回超过 4 个合格回合
- **THEN** 只保留前 4 个
