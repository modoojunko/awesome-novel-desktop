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
- 右栏 SHALL 提供五行能力：世界舞台/力量体系/力量的代价/势力（各答各题）+ 一致性体检；每行 SHALL 注明输入来源（书名+简介+题材、01+题材+简介、02+简介、简介+历史旧账（若已写）、简介+题材+01-05）。
- 生成结果 SHALL 落对应格下方；「采纳 · 覆盖」才写回控件；采纳后面板脚部 SHALL 出现回执（含差量文案）+ 一步撤销，回执只保留最后一次；每行 SHALL 保留最近 5 次生成结果并可切回采纳。
- 生成中 SHALL 有行级占位（aria-busy）与在途防抖（连点只发一次）。
- 门控 SHALL 走 ai_state：member_required 锁定提示；no_key/missing_model 分流跳转；ready 可用。

#### Scenario: 采纳覆盖与一步撤销
- Given 世界舞台已有作者手写内容
- When 采纳 AI 结果
- Then 控件被覆盖且脚部出现回执；点撤销后恢复采纳前原文

#### Scenario: 未配置模型的分流
- Given 本书未选择模型
- When 点任一 AI 行
- Then 跳转模型设定并提示，不发 AI 请求

#### Scenario: 连点防抖
- Given 某 AI 行生成中
- When 快速连点该行
- Then 仅发起一次请求且占位可见

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

### Requirement: lore-keeping 随归档生长
- 归档章节时系统 SHALL 产出世界要素建议（lore-suggest，stateless 不落库），覆盖 history/extra/factions/constraints 四条目集；段落型 01-03 SHALL NOT 被改写；人物变化 SHALL 仅提示路由到角色面板。
- 建议条目 SHALL 带章节来源 origin，人工确认（lore-apply）后才写入；同一 origin 重复归档 SHALL NOT 产生重复条目。
- lore 建议 SHALL 与「归档生成章节摘要」偏好互相独立。

#### Scenario: 归档产生建议且幂等
- Given 第 12 章首次归档产生 2 条世界建议
- When 第 12 章重新归档
- Then 建议仍为同样的 2 条（origin 去重）

#### Scenario: 丢弃建议不入账
- Given 一条 lore 建议
- When 作者丢弃它（产品口径：不采纳即丢弃——无独立丢弃按钮，建议停留在暂存不被采纳就不入账；采纳是唯一入账出口，暂存随标签页会话清理）
- Then 世界设定不变，后续写章不引用该条

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
