# world-settings Specification

## Purpose
世界设定面板：以「五格 + 条目化细节」承接作家对小说世界的全部设定，作为「世界至今」事实源注入写章与一致性体检，并随章节归档持续生长（lore-keeping）。

## Requirements

### Requirement: 世界面板五格结构
- 世界面板 SHALL 呈现五个可见格：01 世界舞台（一段话：名称/时代/形态/主要地点）、02 力量体系、03 力量的代价、04 势力（名字+一句话，行可增删）、05 世界铁律（约束类名目条目）；另有折叠组「06 更多世界细节」承载名目条目，其内「历史与旧账」为独立区（绑定 history 字段）。
- 每格 SHALL 只包含一个问题与一个输入控件（文本框或条目列表），不混用胶囊/单选/填空。
- 「本书没有超自然力量（现实向）」开关 SHALL 持久化（no_power 字段）；开启时 02 主体与 03 整格收起、右栏对应能力行退场、写章注入跳过 power/cost、一致性体检换现实向检查项；已填文本 SHALL NOT 被清空。
- 舞台底色 SHALL 继承题材目录（不重复询问世界类型）；题材未确认时 SHALL 显示引导文案且不阻塞填写。
- 全页 SHALL 无必填：确认按钮永远可点，空内容确认由后端提示后停留本页。

#### Scenario: 现实向开关收起力量格且保留内容
- Given 作者在 02/03 已填写内容后打开「本书没有超自然力量」
- When 查看世界面板
- Then 02 只留开关一行、03 整格收起、右栏力量相关两行退场，且已填文本保留（关闭开关可找回）

#### Scenario: 题材未确认的降级提示
- Given 本书尚未确认题材
- When 打开世界面板
- Then 舞台底色条显示引导文案（先去题材页选底色，也可先写），填写不受阻塞

#### Scenario: 空内容确认不误标
- Given 世界面板全部为空
- When 作者点「确认完成」
- Then 后端返回未填写提示，面板停留且不标记已确认
### Requirement: 契约 v2 与读写归一化
- PUT /settings/world SHALL 校验 WorldIn 契约：stage/power/cost ≤300 字、条目 value ≤200 字、key ≤20 字、factions ≤6 条、constraints ≤10 条、extra ≤50 条、history ≤100 条、拒绝控制字符；违规 SHALL 返回 400 并指明字段。
- 唯一键口径（架构稿 §2.1 幂等键表【拍板】）：constraints 名目 SHALL 唯一（铁律是硬边界）；factions 仅对已命名势力查重（迁移映射的无名有注行豁免）；history/extra 名目 SHALL NOT 强制唯一（幂等靠 (key, origin)，同 key 不同来源合法并存）。
- GET /settings/world SHALL 永远返回归一化 v2 形状并剥离 `_legacy`；v1 旧数据在读边界自动归一化，原值 SHALL 存入 `_legacy` 供回滚（保留一个版本周期）。
- 旧十字段 SHALL 按映射表搬入且不丢字：geography.scenes→stage 段落并入；geography.climate/limits→extra「地理与风物」；politics.rule→extra「律法与刑罚」；politics.factions（自由文本）→factions[0]{name:"",note:原文}；politics.social→extra「社会与信仰」；politics.cost→extra「律法与刑罚」；rules.world→power；rules.society→extra「律法与刑罚」；rules.personal→cost。

#### Scenario: 旧书升级不丢字
- Given 一本旧书的世界 KV 为旧十字段
- When 打开世界面板
- Then 面板显示归一化后的 v2 内容，原文完整保留在 `_legacy`（可回滚）

#### Scenario: 违规条目被拒绝
- Given 一条铁律 value 超过 200 字
- When PUT /settings/world
- Then 返回 400 且错误指明该条目

#### Scenario: 铁律重复名目被拒绝
- Given constraints 里已有一条「不可推翻的事」
- When PUT 时 constraints 再带一条同名目
- Then 返回 400 且错误指明重复的名目

#### Scenario: 历史允许同名目并存
- Given history 已有「大战与灾变」一条
- When PUT 追加另一条同名目（不同经过）
- Then 保存成功（200），两条并存；lore 幂等合并仍按 (key, origin)
- Given extra 中两条同名目条目
- When PUT /settings/world
- Then 返回 400 且错误指明重复的名目
### Requirement: 右栏 AI 五行
- 右栏 SHALL 提供**六行**能力（原文「五行」为存量口径漂移，实现与「29 行」清点均为六行）：世界舞台/力量体系/力量的代价/势力/世界铁律（各答各题）+ 一致性体检；每行 SHALL 注明输入来源（世界舞台＝书名+简介+题材、力量体系＝01+题材+简介、代价＝02+简介、势力＝简介+历史旧账（若已写）、铁律＝01-05 已填内容+简介、体检＝简介+题材+01-05）。
- 生成结果 SHALL 在**弹窗出卡**中呈现（文本/结构化卡；铁律与势力＝结构化卡），弹窗内「采纳 · 覆盖」（铁律/势力＝「采纳 · 合并」）才写回控件；确认后面板脚部 SHALL 出现回执（含差量文案）+ 一步撤销，回执只保留最后一次；面板内不再渲染格下结果区；**格头快捷钮（与右栏共用入口）结果去向相同**。弹窗内「换一个」SHALL 就地重新生成，**「最近 5 次」历史切换退役**。
- 一致性体检结果 SHALL 落弹窗体检报告卡（逐项三态行＋「关闭」「重新检查」，无采纳）；体检报告卡内的「AI 补」快捷链（体检项→调对应生成端点）SHALL 走「关报告卡→开对应生成卡」，**生成卡采纳后 SHALL 自动重开报告卡**（沿用上次 findings 并标注已处理项，「重新检查」才整卡刷新）——多缺口书可循清单逐项补而不丢报告、不重复计费。报告卡内「去补简介/去确认题材」跳转出口（关弹窗→切面板，遇脏表单走既有 dirty 确认）SHALL 保留。
- 生成中 SHALL 有弹窗内占位（prog 语气、aria-busy）与在途防抖（连点只发一次）。
- 现实向开关（no_power）SHALL 与在途生成互斥处置：power/cost 生成在途时切换现实向，弹窗化后 SHALL NOT 出现「出卡、采纳写入已隐藏格」——采纳时该两行不可达即提示先关现实向或换行。
- 门控 SHALL 走 ai_state：member_required 锁定提示；no_key/missing_model 分流跳转；ready 可用。

#### Scenario: 采纳覆盖与一步撤销
- Given 世界舞台已有作者手写内容
- When 弹窗内点「采纳 · 覆盖」
- Then 控件被覆盖且脚部出现回执；点撤销后恢复采纳前原文

#### Scenario: 未配置模型的分流
- Given 本书未选择模型
- When 点任一 AI 行
- Then 跳转模型设定并提示，不发 AI 请求

#### Scenario: 连点防抖
- Given 某 AI 行生成中
- When 快速连点该行
- Then 仅发起一次请求且弹窗占位可见

#### Scenario: 关闭即弃
- Given 势力建议已在弹窗内呈现
- When 作者未点采纳直接关闭弹窗
- Then 势力格保持原文，面板无残留

#### Scenario: 体检报告卡无写回
- Given 世界体检已出报告
- When 查看弹窗报告卡
- Then 为只读检查行＋关闭/重新检查，无采纳控件；「AI 补」快捷链触发的生成同样走弹窗出卡确认

#### Scenario: AI 补采纳后回报告卡
- Given 体检报告卡点名 3 个缺口，作者对第一个点「AI 补」并在生成卡采纳
- Then 报告卡自动重开，沿用上次 findings 且该项标注「已处理」；作者可继续补第二、三项，无需重新跑体检

#### Scenario: 报告卡跳转出口保留
- Given 体检报告卡「简介 × 世界」行缺失并给「去补简介」出口
- When 作者点该出口
- Then 报告卡关闭并切到简介面板（简介面板有未保存编辑时先走既有 dirty 确认）
### Requirement: 一致性体检
- 一致性体检 SHALL 以简介 + 题材 + 世界（01-05）为输入做三方对照，输出逐项三态检查行（达标=ok/风险=warn/缺失=err），只提醒不拦确认。
- 简介/题材缺失时 SHALL 将对应对照行置缺失态并给补填出口，SHALL NOT 整体报错（降级标记）。
- 体检 SHALL 可重跑；体检 SHALL NOT 占用生成历史条。

#### Scenario: 题材承诺缺土壤
- Given 题材主打以弱破强而力量体系未写等级差
- When 运行体检
- Then 「题材 × 世界」行输出风险及补法，确认按钮仍可用

#### Scenario: 简介缺失的降级
- Given 本书尚未填写简介
- When 运行体检
- Then 「简介 × 世界」等对照行置缺失态并提示先补简介，不返回错误
### Requirement: 写章注入
- 写章 prompt 的世界背景 SHALL 按 v2 渲染（舞台/力量/代价段落 + 势力/历史/extra 摘要），截断 SHALL 以整条为单元并显式标注从略数量。
- 世界铁律 SHALL 注入进红线区（最高优先级、独立预算、逐条完整），SHALL NOT 参与世界块的截断。
- no_power=true 时 SHALL 跳过 power/cost 注入。

#### Scenario: 铁律不被截断
- Given 已写 10 条铁律
- When 组装写章 prompt
- Then 10 条铁律全部完整出现在红线区，世界块不含铁律重复内容
### Requirement: 免费版界面等价
- 免费版（无套餐）SHALL 看到完整五格与全部字段，可手填；右栏 AI 卡可见+锁定（降透明+锁徽），点击给统一升级提示；字段填写能力 SHALL 无任何差别。

#### Scenario: 免费版手填与锁定
- Given 免费版作者
- When 填写任意格并点右栏 AI 行
- Then 字段保存正常，AI 行给出升级提示且不发起请求
### Requirement: lore-keeping 随归档生长（提案制）

- 归档章节时系统 SHALL 产出世界要素建议，**经后台收尾提案制落 `chapter_reconcile` 待确认行（kind=lore）**——覆盖 history/extra/factions/constraints 条目集（`set` 归属随建议给出，缺失/非法回落 extra；规则戒律类 SHALL 归 constraints——姊妹模板与事故实勘：三选项口径是「同一教规两格双落」的成因之一）；段落型 01-03 SHALL NOT 被改写；人物变化 SHALL 由收尾的出场引用状态变化承载（char_states），不在本建议内。
- 建议 SHALL NOT 随归档响应即焚、SHALL NOT 进入任何面板暂存区：归档响应不再携带建议列表；采纳统一在「设定」页签的收尾提案区逐条确认（展示位置见 archive-reconcile「提案展示各归各的页签」）。
- 建议条目 SHALL 带章节来源 origin；采纳经 `POST .../reconcile/{id}/accept` 走 lore-apply 幂等合并（同一 origin 重复归档/重跑 SHALL NOT 产生重复条目，同章同类未决提案 SHALL 覆盖而非堆积）。
- lore 建议 SHALL 与「归档生成章节摘要」偏好互相独立（均只看会员门控）。
- 产出判据（c-lore-reconcile-guardrails）：建议 SHALL 只含「后续章节还会当既定设定引用的恒定世界事实」（正反判据成对：长期有效的规则/条约/戒律——哪怕本章才立下——SHALL 提；本章情节经过与拍点、人物状态与外貌、一次性场景细节 SHALL NOT 提）。prompt SHALL 注入现有势力名单（聚焦口径：势力先立两三个，已有 ≥3 不再提新势力，势力相关变化并进既有势力条目，且 SHALL NOT 把新势力改放 extra/history 变相提交）与**本书其他章**待确认提案名目——待确认提案 SHALL 独立成块、只列名目，SHALL NOT 混入「现有世界设定」块（未决提案不是既定设定）；排除本章：同章重复由覆盖语义兜住。排重源＝世界设定现值＋其他章待确认提案，SHALL NOT 只对现值排重。
- 产出护栏 SHALL 代码侧确定性执行（不依赖模型自觉）：单批候选超过 4 条时按模型给出顺序截取前 4 条；候选名目与出场角色名单两侧同口径归一化，命中 SHALL 丢弃；世界设定势力已 ≥3（只统计有名目条目）时 set=factions 的新名目候选 SHALL 丢弃（名目命中既有势力的候选不受限）；过滤后整批为空 SHALL NOT 落行、SHALL NOT 覆盖既有未决行；产出护栏同样作用于采纳时（存量未决行采纳前逐条复检）。
- 采纳归并：同批内归一化同名目先去重（保留首条）；归一化名目（口径同伏笔查重：小写化、去空白与标点，不做全角折叠）命中 history/extra/factions 既有条目时，采纳 SHALL 用该既有条目的**字面** key/origin/set 改写为更新（保留原格与原 origin——若该格条目带 origin——替换 value/note），SHALL NOT 因跨章来源或 `set` 归属不同而新增第二条或落入另一格；constraints 条目集 SHALL NOT 被归并改写（作者手写铁律 SHALL NOT 被 AI value 覆盖）。

#### Scenario: 归档产生提案行（不随响应即焚）
- Given 会员用户归档第 12 章且本书模型就绪
- When 后台收尾完成
- Then 世界要素建议以 kind=lore 的待确认行出现在该章「设定」页签；归档响应本身不含建议列表

#### Scenario: 采纳入账幂等
- Given 一条 kind=lore 待确认提案（origin=第 12 章）
- When 作者点「采纳」，随后同名目同来源的条目再次入账
- Then 世界设定仅一条该条目（(key, origin) 幂等），提案行标记已采纳

#### Scenario: 驳回不入账且留痕
- Given 一条 kind=lore 待确认提案
- When 作者点「驳回」
- Then 世界设定不变、后续写章不引用该条；提案行标记已驳回（留痕，不再出现待确认计数）

#### Scenario: 单批候选超限截断
- Given 收尾模型单批返回 6 条候选（真机实锤：首章一批 8 条全数入账）
- When 提案落待确认行
- Then 行内只保留按模型给出顺序的前 4 条，其余丢弃

#### Scenario: 出场人物名目被丢弃
- Given 本章出场角色名单含「银铎」，世界设定与角色名册均无该名目条目
- When 收尾返回 key=银铎 的候选（无论 set 归属）
- Then 该候选不出现在待确认行内容中（人物归角色域，无卡人物也不入世界要素）；若该批仅此一条（过滤后为空），本章不落世界要素待确认行、既有未决行不被覆盖

#### Scenario: 势力聚焦——三势力后不提新势力
- Given 世界设定已有 3 个势力条目（含手写）
- When 收尾返回 set=factions 且名目为现有势力之外的新候选
- Then 该候选被丢弃；set=factions 且名目命中既有势力的候选不受限（照常更新该势力）

#### Scenario: 整批过滤为空不落行
- Given 本章候选经护栏过滤后为空（如全部为出场人物名目）
- When 收尾完成
- Then 本章不产生世界要素待确认行、既有未决行不被空批覆盖，「待确认」计数不因此增加

#### Scenario: 跨章同名目归并不双落
- Given history 已有「停战条款第三条」（origin=第 1 章）
- When 作者采纳第 2 章提案中归一化同名目、但 `set` 归属为 factions 的条目
- Then 既有 history 条目更新 value（用既有条目字面 key/origin 改写，保留原格与原 origin=第 1 章），factions SHALL NOT 出现该名目（真机实锤：该条款曾双落于两格）

#### Scenario: 批内同名目只落一条
- Given 同一提案批内含归一化同名目两条、`set` 归属各异（真机实锤形态：停战条款第三条一批内 history/factions 各一条）
- When 作者采纳该批
- Then 仅首条按归并口径入账，后续同名目丢弃，SHALL NOT 双落

#### Scenario: 存量未决行采纳前复检
- Given 一条护栏上线前的存量 kind=lore 未决提案，其中含名目为出场人物（或现无卡人物）的候选
- When 作者点「采纳」
- Then 人物类候选被丢弃不入账，其余候选照常归并入账，行正常置「已采纳」
