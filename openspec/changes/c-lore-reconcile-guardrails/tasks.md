# c-lore-reconcile-guardrails 任务清单

> 评审修订版（09-29，后端架构＋提示词工程双评审后）：锚点清单、排除本章、批内去重、字面值改写、采纳侧复检、空批不落行等边界件已烧进任务项，依据见 design.md D4/D5/D6/D8 与 Risks。
>
> 实现备注（09-30）：验证全绿——pytest 定向 105＋全量 1719；隔离栈 e2e reconcile.spec.ts＋chapter-dossier.spec.ts 4/4（桩锚点零改动）。3.3 真机验收待合流后演示栈换包执行。

## 1. 提案侧护栏（archive/reconcile.py）

- [x] 1.1 桩锚点复核（评审已实勘，改前复核一遍）：lore 首句「识别新出现或变化的世界要素」＝e2e 桩路由子串（`reconcile.spec.ts:66`）＋pytest 断言（`test_reconcile.py:719`）双重锚点；禁复用 dossier 桩第一分支子串「只输出一个 JSON 对象，四键齐全」（`reconcile.spec.ts:36`）；hooks 段锚点「对既有伏笔的兑现与推进」不涉本改、hooks 段冻结；验证：清单落在本 change 目录或 commit 说明
- [x] 1.2 重写 `_collect_prompts` lore 段（锚点首句逐字保留）：正反判据成对——应提「后文还会当既定设定引用的恒定世界事实」（长期规则/条约/戒律——哪怕本章才立下；首登场且后文复用的地点/组织/制度；世界层面恒定改变）＋可操作测试句「拿掉后文是否还会当既定设定引用」；不应提「情节经过与拍点、人物状态外貌、一次性场景」；「变化」限定为世界层面恒定改变；势力聚焦段（现有势力名单行＋已有 3 个及以上不再提新势力＋势力变化并进既有势力条目＋**禁止把新势力改放 extra/history 变相提交**——「拿不准用 extra」是现行后门）；人物排除限定 key（「名目不得是人名（含未登记人物）；value 陈述事实可提及人物」）；set 选项补 constraints（规则戒律类归 constraints）＋「同一要素已存在于设定或提案时沿用既有归属，不改换 set」；契约 key ≤10 字、value ≤60 字、evidence（正文原句 ≤40 字，可选子句）；尾提醒「只输出上面的 JSON 对象」；验证：pytest 断言锚点短语原文在 prompt 中＋新口径关键词逐项在
- [x] 1.3 pending 提案名目注入：查本书 `chapter_reconcile`（kind=lore、status=pending）payload 名目并集，**排除本章行**（`chapter_id != 当前章`——同章重复由覆盖语义兜住，注入含本章会自吞未决提案，评审 P0-2）；独立 pending_block（标题「以下名目已有提案待作者确认，不要重复提」，只列名目 ≤20 条，SHALL NOT 混进 world_block）；查询照 roster/hooks_now 先例包 try/except 降级空串；验证：单测断言注入含其他章 pending 名目、不含本章名目、查询炸时 lore 照常出 prompt
- [x] 1.4 新常量 `LORE_FACTION_SOFT_CAP = 3`（注释注明与势力格引导语「先立两三个」同源口径，不复用 FACTIONS_MAX）；势力计数只统计名目非空条目（v1 迁移可产无名势力行 `{name:""}`，无名行不计入也不放行）；验证：单测
- [x] 1.5 parse 后过滤函数（`_run_async` 落行前）：items 取值 `data.get("items") or []` ＋ isinstance 校验（缺键/非 list 视同空批）；单批截前 4 条（按模型顺序）；候选名目与 cast 名单**两侧同口径归一化**，命中 → 丢弃；势力计数 ≥3 时 set=factions 且名目非既有势力 → 丢弃（命中既有势力放行）；**过滤后整批为空 → 不落行、不覆盖既有未决行**（评审 P1-4：空行＝「待确认 1（无明细）」假信号）；验证：`tests/test_reconcile.py` 单测覆盖（含银铎案形状：cast 有名名册无卡；含非 list items；含整批为空分支）
- [x] 1.6 过滤留痕：被丢弃候选的名目与丢弃原因计数写进 payload 或日志（可观测、不静默蒸发；部分丢弃照常落行）；验证：单测断言留痕字段

## 2. 采纳侧归并＋复检（apply_accept lore 分支）

- [x] 2.1 归一化工具复用：把 hooks 分支 `_norm` 提为模块级函数（**行为不变**——小写化＋保留字母数字与汉字，不做全角折叠；spec delta 措辞已对齐该实际行为）；验证：既有 hooks 单测全绿不回退
- [x] 2.2 归并逻辑：entries 先按归一化名目**批内去重**（保留首条——归并匹配采纳时刻既有集，批内同名目 set 各异会双双落新格，停战条款案批内变体）；归一化命中 history/extra/factions 既有条目 → 用既有条目**字面 key/origin/set** 改写为更新（幂等命中靠字面精确相等，用提案 key 重写会 dup 查不中复活双落；factions 走 name/note）；**constraints 不进归并目标**（作者手写铁律不被 AI value 覆盖；prompt 侧 constraints 新提案仍按既有 key 幂等原地更新，不冲突）；将归并的条目在 payload 标注归并目标（审计可测、前端零改动）；验证：单测覆盖跨章同名目更新不新增、跨格双落拦截（停战条款案）、批内同名目只落一条、既有 key 被截断/异形时字面改写仍命中、constraints 不被改写
- [x] 2.3 采纳侧 cast 复检：apply_accept lore 分支对每条 entry 复做与 1.5 同款人物判定（ch 已在分支内加载、outline 现成）——兜存量未决行（本书现挂 1 条）与章纲漏填章的提案；验证：单测（存量 pending 行含人物名目 → 采纳时该条丢弃、其余照常、行置已采纳）
- [x] 2.4 通用 `lore_apply_entries` 不动（设置页路径语义不变）；验证：`tests/test_world_settings_v2.py` 既有 lore-apply 用例零改动全绿

## 3. 回归与验收

- [x] 3.1 pytest 定向：`tests/test_reconcile.py`（含 lore prompt 断言 :675 roster 尾句、:719 锚点——重写后应零改动通过）＋ `tests/test_world_settings_v2.py` 全绿；随后全量 pytest 无回归
- [x] 3.2 e2e：`reconcile.spec.ts`、`chapter-dossier.spec.ts` 中 lore 相关场景全绿（锚点保留后桩应零改动——若桩需改，回查 1.2 是否丢了锚点）；确认零前端改动（`client/frontend/src` 无 diff）
- [ ] 3.3 真机验收（演示栈换包后）：归档一章含新势力情节的正文 → 「设定」页签 lore 提案不含新势力名目/出场人物名目；本书势力 6/6 满状态下采纳含既有势力更新的提案不整批失败；存量那条 pending（含人物名目候选）采纳时被 2.3 复检拦截；对照提案内容与本 change 真机事故清单（13 条形态不再现）
