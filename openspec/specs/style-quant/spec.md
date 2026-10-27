# style-quant Specification

## Purpose
量化参数层：把作者认可的文章（3,000–10,000 字样本）经三步蒸馏学成可执行的量化基线（awesome-novel 九维的合并视图），供写章提示词按「约 X（±容差）」注入；免费版不蒸馏也能完整写作（文字文风三区恒生效）。

## Requirements

### Requirement: 量化层独立存储与写边界

- 量化层 SHALL 存储于独立 KV（key `style-quant`），SHALL NOT 写入 `settings/writing-style.yaml`（style KV 为整文件覆盖语义，混存会被表单保存回踩只读基线）。
- `style-quant` SHALL 含：`version`、`baseline`（六行，每行 `{value, tolerance, locked}`；存储按九维逐字段归档于 `details`）、`details`（九维全量）、`portrait`（作者画像文本）、`confidence`（1–100 整数；0/缺失＝未蒸馏）、`sample_chars`、`history`（版本快照数组，每项含基线全文＋时间＋样本量＋source 标注）、`draft`（蒸馏中间态）。
- 通用 `PUT /settings/{type}` SHALL 拒绝 `style-quant` 类型；专用 `GET /settings/style-quant` 返回全文；`PUT /settings/style-quant` 仅受理「行级 locked 切换」，基线数值字段为服务端只写（前端传数值一律忽略）。
- 导出备份 SHALL 自动包含 style-quant（全 KV 树打包路径），不要求 FORMAT_VERSION 升版。

#### Scenario: 表单保存不回踩基线

- **WHEN** 用户在文字文风页签修改硬约束并保存（PUT /settings/style）
- **THEN** style-quant 中的基线数值与锁定态保持不变

#### Scenario: 锁定切换是唯一前端写入口

- **WHEN** 前端 PUT style-quant 只带某行 locked 布尔
- **THEN** 该行锁定态更新，其余字段（含数值）不变；PUT 带基线数值时该数值被忽略且不报错

#### Scenario: 未蒸馏项目导出导入不丢

- **WHEN** 某书已蒸馏（含 history 与锁定行）后走导出→删库→导入回环
- **THEN** style-quant 全文（含 history 与锁定态）逐字段相等

### Requirement: 样本三路与区间校验

- 样本列表端点 SHALL 返回两路样本：项目 `novel-samples/` 目录下的 `.md/.txt` 文件（名称＋去空白字数）与已归档章节（章号＋标题＋字数）。
- 蒸馏样本 SHALL 支持第三路「粘贴文本」：step1 请求带非空 `text` 时，SHALL 只按该文本装配样本（忽略文件与章节勾选），样本来源记为「粘贴文本」，归档章数计 0。`text` SHALL 为字符串；非字符串入参 SHALL 返回 400 且不产生任何写入。
- 蒸馏前置校验 SHALL 合计样本字数（去空白字符数）并判区间：`<3,000` 拒绝并提示「统计噪声大，再补一些」；`>10,000` 拒绝并提示「挑最有代表性的几章」；区间内放行。粘贴文本与文件/章节两路适用同一区间与同一文案。
- 样本文件读取 SHALL 限定项目 `novel-samples/` 目录内并做路径穿越校验。

#### Scenario: 样本不足拒绝蒸馏

- **WHEN** 用户勾选样本合计 2,100 字并点开始蒸馏
- **THEN** 返回 400，文案含「再补」；style-quant.draft 不产生任何写入

#### Scenario: 两路样本混合计数

- **WHEN** novel-samples/ 有 4,102 字文件且勾选 3 个已归档章节共 3,112 字
- **THEN** 样本列表合计 7,214 字且通过区间校验

#### Scenario: 粘贴文本受理

- **WHEN** step1 请求带 3,000–10,000 字（去空白计数）的 `text`
- **THEN** 样本只取该粘贴文本（忽略文件/章节勾选），样本来源记「粘贴文本」、归档章数计 0，蒸馏照常逐步产出

#### Scenario: 粘贴超限拒绝且零写入

- **WHEN** step1 请求带 2,100 字或 12,000 字的 `text`
- **THEN** 分别返回 400 且文案含「再补」/「挑最有代表性」；style-quant.draft 不产生任何写入

#### Scenario: text 非字符串拒绝

- **WHEN** step1 请求的 `text` 为数字、列表等非字符串
- **THEN** 返回 400；style-quant.draft 不产生任何写入

### Requirement: 蒸馏三步端点与 draft 续跑

- 蒸馏 SHALL 拆为三个请求内端点 `POST /settings/ai/style-distill/step1|step2|step3`＋`POST /settings/ai/style-distill/commit`：step1 逐段标注、step2 统计写法习惯、step3 归纳九维＋作者画像＋禁用词候选。
- 每步产物 SHALL 写入 `style-quant.draft`（含已完成步骤标记）；中断后重新调用 SHALL 从 draft 已有产物续跑（已完成的步骤不再重复调用 LLM）。
- step1 请求带非空 `text` 时 SHALL 视为**新一次蒸馏**：SHALL 清空 draft 全部旧产物后按粘贴文本重跑；粘贴路径 MUST NOT 走续跑短路（否则新样本会被旧产物吞掉）。`text` 缺省或为空时续跑语义 SHALL 保持与历史版本一致。
- 粘贴蒸馏链失败后的重试 SHALL 继续按同一粘贴文本重跑（重试请求持续携带 `text`），MUST NOT 因重试漂移为文件/章节装配路。
- 「不像，再学一次」SHALL 只重跑 step3（保留 step1/2 产物）。
- `commit` SHALL：draft → 正式区＋`history` 追加快照＋`confidence` 落定＋`draft` 清空＋把禁用词候选**服务端** append 进文风 KV 的 `banned_words` 并归一去重（半/全角、大小写归一后跨词表去重）；commit 幂等（重复 commit 同一 draft 不产生重复快照）。
- 所有蒸馏端点 SHALL 挂会员门控（免费 403 `member_required`）与本书模型就绪依赖（无 Key/未选模型给结构化错误）。
- 前端蒸馏进度 UI SHALL 反映**本轮**进度：显式重启（粘贴链带 `text` 从 step1 起跑）时进度状态 SHALL 同步归零——上一轮/旧 draft 的已完成步数 MUST NOT 冒充本轮（否则进度条恒「已完成」、按钮恒「继续蒸馏」）；重启在飞期 SHALL 以三步全未开始呈现。进度归零 MUST NOT 把粘贴链重试拦死：活动粘贴样本存在时「样本不齐」门槛 SHALL NOT 禁用重试按钮。进度 UI 复位 SHALL NOT 改变「关弹窗保留草稿、重开按 draft 续跑」的既有语义。

#### Scenario: 中断后按 draft 续跑

- **WHEN** step1、step2 已完成（draft 有产物）后用户中断，再次点开始蒸馏
- **THEN** 系统跳过 step1/2 直接执行 step3，总耗时只含未完成步骤

#### Scenario: 粘贴重启旧产物作废

- **WHEN** draft 已有 step1/step2 产物，且 step1 请求带新的粘贴 `text`
- **THEN** draft 旧产物被清空，本次及后续步骤只基于粘贴文本重新产出，旧样本的标注与统计不再复用

#### Scenario: 无 text 时续跑不受影响

- **WHEN** step1 请求不带 `text` 且 draft 已有 step1 产物
- **THEN** 返回续跑结果（不重复调用 LLM），行为与历史版本完全一致

#### Scenario: 粘贴失败重试不丢样本

- **WHEN** 粘贴蒸馏的 step1 返回 502，用户点重试
- **THEN** 重试请求仍携带同一粘贴文本并重跑成功；不出现按空文件/章节装配的「样本合计 0 字」错误

#### Scenario: commit 并入禁用词且去重

- **WHEN** 蒸馏产出禁用词「突然」，文风 KV 的 banned_words 已有「突然」
- **THEN** commit 后 banned_words 该词只有一条；蒸馏独有的新词被追加

#### Scenario: 免费用户被门控

- **WHEN** 免费用户调用任一蒸馏端点
- **THEN** 返回 403 member_required，style-quant 无任何写入

#### Scenario: 粘贴重启进度复位

- **WHEN** 旧 draft 停在 step2（进度条显示两步已完成、按钮「继续蒸馏」），用户粘贴新样本重启
- **THEN** 进度条归零——三步呈现为未开始并随本轮推进（不再显示上一轮「已完成」），按钮在飞期显示「蒸馏中…」、失败后回「开始蒸馏」

#### Scenario: 进度复位不改变续跑语义

- **WHEN** 粘贴重启失败后用户「取消」关闭蒸馏面板，再次打开
- **THEN** 仍按 draft 续跑（旧语义不变）——进度复位只作用于显式重启的那一轮

#### Scenario: 复位不拦死粘贴重试

- **WHEN** 本书样本合计不足区间、用户走粘贴链且首试失败（step1 502）
- **THEN** 按钮保持可用（粘贴文本供样本，不受「样本不齐」门槛拦截），重试仍携带同一粘贴文本重跑

### Requirement: 基线只读与作者画像确认

- 基线数值对前端 SHALL 只读：界面不提供数值编辑入口；重蒸馏是基线变更的唯一路径；锁定行在重蒸馏时 SHALL 跳过（保留上一版值），未锁定行被新值覆盖，版本快照 SHALL 如实记录混合来源。
- 落卡前 SHALL 展示「作者画像」确认卡：开头定位声明（「以下是你文风在 AI 眼里的理解——不是文学评价，AI 会照着这个写。哪里不对直接说。」）＋写作特点/规矩/量化感觉/典型句子＋结尾确认问句；确认卡 SHALL 同时展示六行基线预览（每行「行名＋约 X（±容差）」口径），行值与容差取自服务端同一构建产物（draft 内落卡行）；对已锁定行，预览 SHALL 显示落卡将保留的上一版值并明确标记，其余行显示新蒸馏值——预览与随后落卡写入正式区的六行 SHALL 逐行一致；用户确认（commit）或反馈（重跑 step3）前 SHALL NOT 写正式区。
- 量化页签对未蒸馏/免费用户 SHALL 显示空态：说明文字＋PRO 标识＋蒸馏入口；空态 SHALL 以「粘贴文本蒸馏」为首选入口并保留「从文件/章节选样本」入口；样本选择页 SHALL 提供粘贴入口。
- 粘贴弹窗 SHALL 实时显示去空白字数与区间状态；区间外 SHALL 禁用提交并给出补救提示（不足→提示还差多少字；超限→提示挑最有代表性的几章）。
- 蒸馏进行中 SHALL 展示三步进度（已完成步骤打勾）。

#### Scenario: 锁定行跨版本保留

- **WHEN** v2 基线中「篇幅配比」行已锁定，用户重新蒸馏出 v3
- **THEN** v3 的篇幅配比保持 v2 值，其他行取 v3 新值，history 最新快照记录「篇幅配比来源=v2（锁定）」的混合事实

#### Scenario: 未确认不落正式区

- **WHEN** step3 完成但用户未点「落卡」
- **THEN** style-quant 正式区（baseline/confidence/history）不变，产物只在 draft

#### Scenario: 确认卡可见六行预览

- **WHEN** step3 完成进入确认卡
- **THEN** 作者能看到六行基线预览（行名＋约 X（±容差））

#### Scenario: 锁定行预览如实显示保留值

- **WHEN** step3 完成进入确认卡，且当前正式区存在锁定行
- **THEN** 预览中该行显示落卡将保留的上一版值并带「保留上一版」标记，其余行显示新蒸馏值；点「落卡」后正式区六行与预览逐行一致

#### Scenario: 短文本弹窗禁提交

- **WHEN** 弹窗内粘贴 2,100 字
- **THEN** 提交按钮禁用并提示还差约 900 字；补到区间内后提交可用

### Requirement: 量化基线注入写章提示词

- `confidence > 0` 时，写章提示词 SHALL 注入量化基线段：六行基线以「约 X（±容差）执行，可按本章剧情在容差内自行调节」口径渲染；`confidence = 0` 或缺失时 SHALL NOT 注入该段（文字文风三区恒生效兜底）。
- 容差 SHALL 由 confidence 分档：≥70→±10%、≥50→±20%、其余→±30%。
- 注入 SHALL 应用本章文风影子（若存在）：被影子命中的行 SHALL 以「约 X（本章覆盖：理由）」替换该行基线值渲染；未命中的行 SHALL 按基线渲染；影子为空/缺失/非对象时输出 SHALL 与无影子行为逐字节一致。
- 伏笔注入 SHALL 为「计划收束章等于当前章」的活跃伏笔追加「建议本章收束」派生标记（纯派生，不改存储）。

#### Scenario: 蒸馏后提示词含基线段

- **WHEN** 某书 confidence=82 且组装某章提示词
- **THEN** 提示词含量化基线段（含「约 48%」（±10%）形态的对话占比等条目与「按本章剧情在容差内自行调节」指令）

#### Scenario: 本章影子按行覆盖
- **WHEN** 某章存在影子行（如句法＝「短句为主」，理由「打斗章节奏」）
- **THEN** 提示词对应行渲染为「约 短句为主（本章覆盖：打斗章节奏）」，其余行按基线渲染

#### Scenario: 未蒸馏不注入量化段

- **WHEN** 某书无 style-quant 或 confidence=0
- **THEN** 提示词无量化基线段，文字文风三区照常注入

#### Scenario: 本章该还的伏笔被点名

- **WHEN** 某活跃伏笔 planned_chapter_id 等于当前写作章 id
- **THEN** 该伏笔注入行带「建议本章收束」标记；其他活跃伏笔不带

### Requirement: 本章文风影子

- 系统 SHALL 以 `chapters.style_shadow`（JSON 文本列，原表加列）存储每章的覆盖行：`{行名: {value, reason}}`；损坏值 SHALL 按空影子处理，不阻塞章读取。
- 系统 SHALL 提供三端点：`GET .../chapters/{ref}/style-shadow/baseline`（全书六行基线（含 locked/容差/画像/置信度）＋本章影子现状）、`PUT .../style-shadow`（专用小端点：`{rows}` 形状清洗——非对象行与非对象 rows 丢弃、值与理由全空白行丢弃、维度名与值字符串化保留原样（不脱空格）、响应回读清洗结果）、`POST .../style-shadow/suggest`（AI 建议：读基线＋本章章纲，产出行级建议并记账，不落库）。
- PUT SHALL NOT 挂 AI 门控——**免费档可写影子（2026-09-17 拍板定案：手工覆盖行与全书文风三区同权，非「现状锁定」）**；suggest SHALL 挂 PRO 与本书模型双门控（与全站 AI 端点同口径），未蒸馏基线时 SHALL 返回 409（含「蒸馏」出口文案），模型未就绪（调用未发生）SHALL NOT 记账。
- suggest 产物清洗 SHALL 按六行白名单过滤：非白名单行、空值行丢弃；理由 SHALL 截断至 200 字；非法 JSON/非列表 SHALL 返回空建议。
- 影子行 SHALL 随章档案导出/导入（chapter-data 侧同步登记）；SHALL NOT 影响全书基线。

#### Scenario: 写入并回读影子
- **WHEN** 作者对某章 PUT 影子行（如句法覆盖）
- **THEN** 响应与后续 GET baseline 均返回该清洗后的影子行

#### Scenario: 免费档可写影子（拍板定案）
- **WHEN** 免费档用户经工作台手工添加覆盖行
- **THEN** PUT 影子端点放行并落库（随后 GET baseline 可见），不收会员门控

#### Scenario: 脏形状被清洗
- **WHEN** PUT 的 rows 含非对象行、全空白行
- **THEN** 这些行被丢弃，其余行按字符串化原样保留

#### Scenario: 未蒸馏时拒绝建议
- **WHEN** 本书 confidence=0（未蒸馏）时发起 AI 建议
- **THEN** 返回 409 并提示先完成蒸馏；无模型调用

#### Scenario: 建议白名单清洗
- **WHEN** AI 建议含六行之外的维度或空取值
- **THEN** 这些条目被丢弃，理由超长截断至 200 字

### Requirement: 文字层提取步与分段落卡

- 蒸馏 SHALL 在既有三步之后增加第四请求内端点 `POST /settings/ai/style-distill/step4`（文字层提取），对同一份已装配样本提取两层草稿：
  - 三区草稿：`role`（叙事身份一句话）＋`rules`（可执行写作规则条目）＋`craft`（表现手法条目）；样本中「刻意避免的写法」SHALL 转「避免…」句式并入 rules 草稿；
  - 示范段：0–6 条**逐字原文段**（单条 ≤200 字，样本不足时可以少；样本中对话与叙述两种形态皆存在时，示范段 SHALL 各覆盖至少一条；只取样本原文，禁止自造、改写或删节拼接）。
- step4 的样本供给 SHALL 由请求重供：前端每次调用 step4 SHALL 随请求携带样本上下文（粘贴 `text` 或文件/章节勾选，与 step1 同一 body）。step4 的 `text` 参数 SHALL 只作样本供给，MUST NOT 触发 step1 的「`text` 非空＝清空 draft 重启」语义（同名参数、语义相异，SHALL 进钉子测试）；draft 无 step1 产物或样本不可供时 SHALL 返回 400（文案指向先完成第一步）。
- step4 产物 SHALL 写入 `style-quant.draft` 并按既有续跑语义执行：中断后重开 SHALL 跳过已完成步骤；存量 draft（无 step4 产物）续跑时 SHALL 补跑 step4；粘贴重启清空 draft 的语义对 step4 同样适用。
- step4 SHALL 挂与三步同款的会员门控（免费 403 `member_required`）与本书模型就绪依赖；step4 失败 SHALL 可单独重试且 MUST NOT 影响已完成的 step1–3 产物。
- 本机已装提示词包缺 `style_learn_extract` 模板时（客户端新于包的版本斜坡窗口），step4 SHALL 返回结构化错误（提示联网更新提示词包），SHALL NOT 以 500 形态暴露；确认卡文字层段 SHALL 呈现降级文案，三步基线路径与落卡 MUST NOT 受影响。
- step4 SHALL 支持 force 重提（保留 step1–3 产物，仅重产文字层草稿）；确认卡文字层段 SHALL 提供「重新提取」入口，与 step3「不像，再学一次」互不影响。
- 确认卡 SHALL 在六行基线预览之外分段呈现文字层：三区草稿（可编辑：身份一句＋规则列表＋手法列表）与示范段（只读段落＋可删条目）；用户 SHALL 对「基线」「三区草稿」「示范段」三段各自独立采纳或弃采，未采纳段 SHALL 零写回。
- 采纳写边界：三区草稿采纳 SHALL 经文风 KV 白名单写（role/rules/craft 替换，编辑后的 taboo「避免…」行随 rules），示范段采纳 SHALL 写 `style_samples`（≤6 条、单条截 500 字、替换语义）；两段采纳 SHALL 在写前回读文风 KV 合并（MUST NOT 覆盖用户未保存的禁用词/句式编辑），并 SHALL 挂回执可一键撤销；采纳 SHALL 同步表单态并重置脏快照基线（避免后续表单保存回踩采纳值或误报脏）；基线采纳走既有 commit，语义不变。
- 「不像，再学一次」重跑 step3 时，SHALL NOT 自动清掉已采纳的文字层（采纳发生在文风 KV，与 draft 生命周期解耦）。
- 基线落卡 SHALL 连 draft（含文字层草稿）一并清空：文字层草稿存在且未采纳时，落卡前系统 SHALL 给显式丢弃确认（说明丢弃后果与恢复代价＝同一样本完整重蒸馏），用户确认后方可落卡；已采纳（本卡内）或无文字层草稿时 SHALL NOT 出现该确认。

#### Scenario: 学全三层落卡

- **WHEN** 用户粘贴 5,000 字参考书文本完成蒸馏，确认卡上依次采纳基线、三区草稿（微调两条规则）、示范段（删 1 条留 4 条）
- **THEN** 量化正式区出 v(N+1) 快照；文风 KV 的 role/rules/craft 为编辑后草稿；style_samples 为余下 4 条；三条 ChangeReceipt 均可分别撤销

#### Scenario: 只采纳示范段

- **WHEN** 用户对基线点「不落卡」、三区草稿弃采，仅采纳示范段
- **THEN** style-quant 正式区与文风三区零变化，仅 style_samples 被替换；draft 照常保留（基线可稍后单独落卡）

#### Scenario: 三区替换可撤销

- **WHEN** 本书原三区为手写内容，用户采纳三区草稿后点回执撤销
- **THEN** role/rules/craft 恢复采纳前内容，撤销动作有 toast 确认

#### Scenario: 采纳不覆盖未保存的禁用词

- **WHEN** 用户在表单态改了禁用词未保存，随即采纳三区草稿
- **THEN** 采纳写回基于服务端最新文风 KV 合并，未保存的禁用词编辑不被覆盖丢失

#### Scenario: 存量 draft 补跑 step4

- **WHEN** 旧 draft 停在 step3 完成（无 step4 产物），用户重开蒸馏面板
- **THEN** 系统只跑 step4（不重复调用 step1–3），确认卡照常呈现文字层两段

#### Scenario: step4 失败不影响基线落卡

- **WHEN** step4 返回 502，用户重试一次仍失败，随后直接落卡基线
- **THEN** 基线照常 commit 成功；step4 可稍后单独重试，重试只产文字层草稿

#### Scenario: 粘贴重启清空文字层草稿

- **WHEN** draft 已含 step4 产物，用户粘贴新文本重启蒸馏
- **THEN** draft 全部旧产物（含 step4）清空，文字层草稿按新样本重新提取

#### Scenario: step4 的 text 不触发清空重启

- **WHEN** draft 已有 step1–3 产物，前端携带与 step1 相同的粘贴 `text` 调用 step4
- **THEN** draft 旧产物原样保留、只新增 step4 草稿；样本不足区间或非字符串的 400 行为与 step1 同口径但不产生任何清空

#### Scenario: 未采纳文字层先落卡须确认

- **WHEN** 确认卡上有文字层草稿且未点过「采纳到文风设定」，用户点「就是这样，落卡」
- **THEN** 先弹显式丢弃确认（说明落卡将丢弃草稿、恢复需完整重蒸馏）；取消则留在确认卡；确认丢弃后方才落卡；本卡已采纳过或无文字层草稿时，落卡不出现该确认

#### Scenario: 旧包缺模板降级

- **WHEN** 本机提示词包为旧版（无 style_learn_extract），用户点「学文字层」
- **THEN** 文字层段呈现「更新提示词包后可用」降级文案；step1–3 与基线落卡照常可用，SHALL NOT 出现 500

#### Scenario: force 重提只重摇文字层

- **WHEN** 用户对文字层草稿不满意点「重新提取」
- **THEN** 仅 step4 重跑（step1–3 产物与已落卡基线不动），确认卡文字层两段刷新

#### Scenario: 免费用户与未配模型

- **WHEN** 免费用户或未配模型的本书调用 step4
- **THEN** 分别返回 403 member_required 与结构化模型错误，文风 KV 与 style-quant 均零写入
