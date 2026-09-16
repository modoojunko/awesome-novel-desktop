# style-quant 变更（增量）

## Purpose

量化参数层：把作者认可的文章（3,000–10,000 字样本）经三步蒸馏学成可执行的量化基线（awesome-novel 九维的合并视图），供写章提示词按「约 X（±容差）」注入；免费版不蒸馏也能完整写作（文字文风三区恒生效）。

## ADDED Requirements

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

### Requirement: 样本两路与区间校验

- 样本列表端点 SHALL 返回两路样本：项目 `novel-samples/` 目录下的 `.md/.txt` 文件（名称＋去空白字数）与已归档章节（章号＋标题＋字数）。
- 蒸馏前置校验 SHALL 合计样本字数并判区间：`<3,000` 拒绝并提示「统计噪声大，再补一些」；`>10,000` 拒绝并提示「挑最有代表性的几章」；区间内放行。
- 样本文件读取 SHALL 限定项目 `novel-samples/` 目录内并做路径穿越校验。

#### Scenario: 样本不足拒绝蒸馏

- **WHEN** 用户勾选样本合计 2,100 字并点开始蒸馏
- **THEN** 返回 400，文案含「再补」；style-quant.draft 不产生任何写入

#### Scenario: 两路样本混合计数

- **WHEN** novel-samples/ 有 4,102 字文件且勾选 3 个已归档章节共 3,112 字
- **THEN** 样本列表合计 7,214 字且通过区间校验

### Requirement: 蒸馏三步端点与 draft 续跑

- 蒸馏 SHALL 拆为三个请求内端点 `POST /settings/ai/style-distill/step1|step2|step3`＋`POST /settings/ai/style-distill/commit`：step1 逐段标注、step2 统计写法习惯、step3 归纳九维＋作者画像＋禁用词候选。
- 每步产物 SHALL 写入 `style-quant.draft`（含已完成步骤标记）；中断后重新调用 SHALL 从 draft 已有产物续跑（已完成的步骤不再重复调用 LLM）。
- 「不像，再学一次」SHALL 只重跑 step3（保留 step1/2 产物）。
- `commit` SHALL：draft → 正式区＋`history` 追加快照＋`confidence` 落定＋`draft` 清空＋把禁用词候选**服务端** append 进 anti-ai 面板并归一去重（半/全角、大小写归一后去重）；commit 幂等（重复 commit 同一 draft 不产生重复快照）。
- 所有蒸馏端点 SHALL 挂会员门控（免费 403 `member_required`）与本书模型就绪依赖（无 Key/未选模型给结构化错误）。

#### Scenario: 中断后按 draft 续跑

- **WHEN** step1、step2 已完成（draft 有产物）后用户中断，再次点开始蒸馏
- **THEN** 系统跳过 step1/2 直接执行 step3，总耗时只含未完成步骤

#### Scenario: commit 并入禁用词且去重

- **WHEN** 蒸馏产出禁用词「突然」，anti-ai 面板已有「突然」
- **THEN** commit 后 anti-ai 面板该词只有一条；蒸馏独有的新词被追加

#### Scenario: 免费用户被门控

- **WHEN** 免费用户调用任一蒸馏端点
- **THEN** 返回 403 member_required，style-quant 无任何写入

### Requirement: 基线只读与作者画像确认

- 基线数值对前端 SHALL 只读：界面不提供数值编辑入口；重蒸馏是基线变更的唯一路径；锁定行在重蒸馏时 SHALL 跳过（保留上一版值），未锁定行被新值覆盖，版本快照 SHALL 如实记录混合来源。
- 落卡前 SHALL 展示「作者画像」确认卡：开头定位声明（「以下是你文风在 AI 眼里的理解——不是文学评价，AI 会照着这个写。哪里不对直接说。」）＋写作特点/规矩/量化感觉/典型句子＋结尾确认问句；用户确认（commit）或反馈（重跑 step3）前 SHALL NOT 写正式区。
- 量化页签对未蒸馏/免费用户 SHALL 显示空态：说明文字＋PRO 标识＋「去蒸馏」入口；蒸馏进行中 SHALL 展示三步进度（已完成步骤打勾）。

#### Scenario: 锁定行跨版本保留

- **WHEN** v2 基线中「篇幅配比」行已锁定，用户重新蒸馏出 v3
- **THEN** v3 的篇幅配比保持 v2 值，其他行取 v3 新值，history 最新快照记录「篇幅配比来源=v2（锁定）」的混合事实

#### Scenario: 未确认不落正式区

- **WHEN** step3 完成但用户未点「落卡」
- **THEN** style-quant 正式区（baseline/confidence/history）不变，产物只在 draft

### Requirement: 量化基线注入写章提示词

- `confidence > 0` 时，写章提示词 SHALL 注入量化基线段：六行基线以「约 X（±容差）执行，可按本章剧情在容差内自行调节」口径渲染；`confidence = 0` 或缺失时 SHALL NOT 注入该段（文字文风三区恒生效兜底）。
- 容差 SHALL 由 confidence 分档：≥70→±10%、≥50→±20%、其余→±30%。
- 伏笔注入 SHALL 为「计划收束章等于当前章」的活跃伏笔追加「建议本章收束」派生标记（纯派生，不改存储）。

#### Scenario: 蒸馏后提示词含基线段

- **WHEN** 某书 confidence=82 且组装某章提示词
- **THEN** 提示词含量化基线段（含「约 48%」（±10%）形态的对话占比等条目与「按本章剧情在容差内自行调节」指令）

#### Scenario: 未蒸馏不注入量化段

- **WHEN** 某书无 style-quant 或 confidence=0
- **THEN** 提示词无量化基线段，文字文风三区照常注入

#### Scenario: 本章该还的伏笔被点名

- **WHEN** 某活跃伏笔 planned_chapter_id 等于当前写作章 id
- **THEN** 该伏笔注入行带「建议本章收束」标记；其他活跃伏笔不带
