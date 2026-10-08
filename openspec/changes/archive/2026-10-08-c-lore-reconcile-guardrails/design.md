# c-lore-reconcile-guardrails 设计

## Context

lore 收尾链路（真机事故链，详见 proposal Why）：

- 提案生成：`archive/reconcile.py` `_collect_prompts` lore 段（:292-297）——现只有「识别新出现或变化的世界要素」一句＋「与之重复的不要提」软排重（world_block 只注入世界设定现值，:274）；名册注入只护已登记角色（:155-169，09-28 邵青梧/阿蓟事故后加）。
- 落行：`_run_async` parse 后原样 `_upsert_pending`（:245-258），无过滤、无上限。
- 采纳：`apply_accept` lore 分支（:353-388）→ `settings/world_model.py` `lore_apply_entries`（:232-272）——幂等键 history/extra=(key, origin)、factions=name、constraints=key；分格满员 `_SET_LIMITS`（history 100 / factions 6 / constraints 10 / extra 50，:30-39）抛 ValueError 整批失败。
- 同类先例：伏笔通道 #589（判据＋上限＋幂等）→ #592/#593（对账制），prompt 判据＋代码侧 `_norm` 归一化查重（`apply_accept` hooks 分支 :400-403）双层的做法已验证。

真机数据（演示栈 novel-dev.db，验收对照）：两章产 4 批 lore 提案，13 条入账——人物进 factions（银铎，cast 里有他、名册没有）、同键跨格双落（停战条款第三条：history＋factions 各一）、近键双落（染血即焚 vs 教团验心规）、情节拍点入 history（验心提前）；势力格 6/6 满。

## Goals / Non-Goals

Goals：lore 提案在「生成→落行→采纳」三段各加一层护栏；确定性护栏全部代码侧执行、pytest 可测；单 capability delta（world-settings），不动 archive-reconcile 的委托式条款。

Non-Goals：不改通用 `lore_apply_entries` 语义（设置页右栏建议路径不受影响）；不改满员整批转失败的诚实语义；不做「无卡人物改提案立角色卡」新通道（另立项）；势力软上限不做按书可配（另立项）；存量脏数据清理（手动另行执行）；零前端改动、零 DDL。

## Decisions

**D1 护栏双层：prompt 判据（软）＋代码过滤（硬），与伏笔通道同构。**
判据类规则（一次性情节/人物状态不提）无法代码判定，只能进 prompt；能确定性判定的（单批上限、cast 名目命中、势力满三新名目）必须代码执行——伏笔通道的教训是 prompt 判据挡不住模型发挥（#589 后仍 11 条/章），#592 补代码侧才收口。备选「只改 prompt」被否：本次事故的候选全是 prompt 有软口径（「与之重复的不要提」「拿不准用 extra」）情况下产出的。

**D2 人物判定＝候选名目命中本章出场角色名单（chapter.outline.characters），不引入 NER。**
银铎案的两道现有防线都漏：prompt 口径「人物归角色面板」被模型无视；名册（known_names）只含已登记角色，无卡人物不在册。cast 名单是章纲既有人物（手填或 AI 起草），命中即人物——零新依赖、确定性强。代价：作者章纲漏填的未登记人物仍可能漏入，由 prompt 软判据（「人名一律不提」）兜底，确认制终审。备选「名册＋cast 并集」即本方案；备选「NER 人名识别」被否（重依赖、中文人名误判率高）。

**D3 势力软上限＝新常量 3，不复用 FACTIONS_MAX=6。**
「先立两三个」是产品口径（前端势力格引导语 WorldSettingPanel.tsx:590），提案护栏应对齐 3；FACTIONS_MAX=6 是存储满员语义，若用 6 做护栏阈值，「3 真＋3 假占满」的本案路径照样发生。常量 `LORE_FACTION_SOFT_CAP = 3` 落 reconcile.py，注释注明与前端引导语同源口径。势力计数只统计名目非空的条目——v1 迁移可产出无名势力行 `{name:""}`（world_model.py:123-127、168），无名行既不计入 ≥3、也无法被「名目命中既有势力」放行。备选「按书可配」进非目标。

**D4 跨批排重源＝世界设定现值＋本书**其他章**pending lore 提案名目；待确认提案独立成块注入。**
真机跨章双落（第 2 批重复提第 1 批已提案条目）的根因是排重源不含未决提案。实现要点（评审 P0-2 定形）：查询 `chapter_reconcile`（本书、kind=lore、status=pending）时 **SHALL 排除本章行**（`chapter_id != 当前章`）——同章重复本由 `_upsert_pending` 覆盖语义兜住，注入含本章会自吞：重归档/重跑时旧同章行名目被注入「不要重复提」→ 新批省略这些条目 → 整行覆盖 → 作者未拍板的提案静默蒸发。注入为**独立 pending_block**（标题「以下名目已有提案待作者确认，不要重复提」、只列名目 ≤20 条），SHALL NOT 追加进 world_block——world_block 语义是既定设定，混入会让模型把未决提案当既有设定做「更新」或引用其归属（评审 P1-3）。查询照 roster/hooks_now 先例包 try/except 降级空串（评审 P2-1）。单飞语义（全局 `_job`）下查询与落行无并发竞态；采纳可与收尾并发，归并在采纳时重读世界现值是正确兜底。备选「仅同章 pending」被否：事故恰是跨章。

**D5 采纳归并落点＝reconcile `apply_accept` lore 分支，不动通用 `lore_apply_entries`；四个边界件（评审 P1-1/2/3/4 定形）。**
（a）**批内去重先行**：entries 按归一化名目去重保留首条——归并匹配的是采纳时刻既有条目集，批内同名目两条（set 各异）会双双无既有命中、双双落新格（停战条款案的批内变体）。（b）**重写用既有条目字面 key/origin/set**：幂等命中靠字面精确相等（world_model.py:260-264），既有 key 可能被 `[:KEY_MAX]` 截断或系作者手书异形，若用提案 key 重写则 dup 查不中、复活双落；factions 更新走 name/note。（c）**constraints 不进归并目标集**：铁律是作者手写硬边界，AI value 覆盖不可接受；prompt 侧 constraints 新提案仍按既有 key 幂等原地更新（world_model 既有语义），两者不冲突——归并命中既有铁律名目的提案按现行为落其 proposed set，作者手动归位。（d）**采纳侧 cast 复检**：对每条 entry 复做与提案侧同款的人物判定（ch 已在分支内加载、outline 现成）——兜存量未决行（本书现挂 1 条）与章纲漏填章的提案。归并发生的条目在 payload 标注归并目标（审计可测、前端零改动——ReconcilePane 只渲染 `key：value`，作者看不到「将覆盖既有条目」，标注留待后续立项展示）。过滤后整批为空 → 不落行也不覆盖既有未决行（评审 P1-4：计数按行不按条，空行＝「待确认 1（无明细）」假信号）。不改通用服务的理由：设置页右栏建议走同一 `lore_apply_entries`，但其出卡是模型对五格定向生成＋人工逐卡确认，乱投概率与事故形态不同；改通用语义会动 world-settings 既有幂等条款与设置页路径。代价：两路径归并口径短期不一致（收尾强、设置页维持 (key, origin)），接受并观察。归一化口径照抄伏笔 `_norm`（小写、去非字母数字非汉字，:400-403），不新造——delta 措辞已对齐其实际行为（不做全角折叠，评审 P1-5）。

**D6 单批上限截断在落行前（parse 后），不重试不报错；取值须防护。**
模型给出顺序即其重要性序（prompt 同步加「只挑对后续最重要的，≤4 条，宁缺勿滥」）；超限截断静默执行即可，行内条目变少不是错误。取 4 的依据：hooks 每类 ≤3，lore 一批覆盖四格取 4；真机两章 16 候选护栏后 ≤8。截断前取值按 `data.get("items") or []` ＋ isinstance 校验（`_parse_json_lenient` 可返回无 items 键的 dict），非 list 视同空批（评审 P2-7）。

**D7 满员语义不动（ValueError → 行置 failed 保留 payload 可重试）。**
护栏堵住「无脑灌满」源头后，满员=作者真实数据态；跳过满员条目会让作者以为采纳了实际没进（静默丢数据），整批 failed＋「X 格已满，请先清理」是诚实留痕。维持现状，不加场景。

**D8 prompt 重写的锚点与契约约束（评审 P0 实勘定形）。**
（a）**锚点清单**：lore 段首句「识别新出现或变化的世界要素」是 e2e 桩路由子串（reconcile.spec.ts:66）与 pytest 断言（test_reconcile.py:719）双重依赖——重写**逐字保留**该短语开头，桩与断言零改动；hooks 段锚点「对既有伏笔的兑现与推进」不涉本 change，hooks 段冻结。（b）**禁用子串**：dossier 桩分支「只输出一个 JSON 对象，四键齐全」是桩路由第一分支（reconcile.spec.ts:36），lore 段措辞 SHALL NOT 含该子串（现文「JSON 对象输出」恰好避开，重写勿「统一措辞」撞上）。（c）**契约加长度**：key ≤10 字、value 一句话 ≤60 字（对齐姊妹模板 world_lore_suggest.prompt:7 口径；无界 value 是 1600 输出预算截断 → JSON 断裂 → failed 行的直接通路，reconcile.py:224-225 注释记载过同形态事故）。（d）**evidence 可选子句（采纳）**：每条附正文原句 ≤40 字——解析/落行/前端三段零改动（apply 只取 key/value/set，payload 原样），约 300 token 在预算内，强制接地防脑补（先例 chapter_archive_extract.prompt「evidence 必须原句」）；对账页签不展示 evidence，想给作者看另立项。（e）**尾提醒**：正文后补一行「只输出上面的 JSON 对象」（lore 有 parse 事故史、hooks 没有，非对称加固有依据）。

## Risks / Trade-offs

- cast 名单不全 → 人物漏拦：软判据＋逐条确认终审兜底；后续可加「采纳时若名目与某角色卡名高度相似给提示」（非本次）。对称风险同样存在：**世界要素与出场角色同名（同字地名/人名互撞）会被人物护栏误拦**——归一化两侧同口径匹配放大该面，靠留痕（丢弃数与名目进日志/payload）与确认制兜底，单测覆盖两侧匹配行为（评审 P2-8）。
- 势力软上限 3 对多势力题材（史诗奇幻）偏紧：与当前产品口径一致，先收口再按需放开（另立项）。「不再提新势力」的 prompt 口径可能被模型绕路（新势力改放 extra）——prompt 显式封路＋代码过滤只堵 set=factions 的残差进确认制终审（评审 P1-1）。
- 归一化归并可能误合同名异物（两处「集市」）：与伏笔 planted 查重同风险、同口径，先例已接受；采纳时刻统一归并，ReconcilePane 只渲染 `key：value`，作者看不到归并目标——payload 已标注归并目标供审计（D5），给作者看另立项（评审 P2-5）。
- prompt 注入 pending 名目增加少量 token（≤20 名目约百字）：可忽略；独立成块避免与「现有世界设定」语义混淆（D4）。
