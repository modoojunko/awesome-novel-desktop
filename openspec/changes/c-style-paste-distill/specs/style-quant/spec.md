# style-quant Specification (Delta)

## RENAMED Requirements

- FROM: `### Requirement: 样本两路与区间校验`
- TO: `### Requirement: 样本三路与区间校验`

## MODIFIED Requirements

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
